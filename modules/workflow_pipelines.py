"""
Workflow Pipelines - Lobster-style deterministic multi-step pipeline system.

Built with composable pipeline architecture. Replaces token-expensive
sequential LLM calls with single deterministic operations gated by human approval
checkpoints. Steps execute in strict order, piping output forward (stdin/stdout
pattern), and the entire pipeline can pause at ApprovalGates, persist its state to
disk, and resume later with a durable token.

Usage:
    pipeline = (PipelineBuilder("deploy-staging")
        .step("test", exec="pytest tests/ -q")
        .step("review", approval=True, message="Tests passed. Deploy to staging?")
        .step("deploy", exec="./deploy.sh staging", condition="review.approved")
        .build())

    runner = PipelineRunner()
    result = runner.run(pipeline)
    if result.status == PipelineStatus.AWAITING_APPROVAL:
        # later ...
        result = runner.resume(result.resume_token, approved=True)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_APPROVAL_TIMEOUT_MS = 24 * 60 * 60 * 1000  # 24 hours
DEFAULT_STEP_TIMEOUT_MS = 120_000                    # 2 minutes
PIPELINE_STORE_DIR = Path(os.environ.get(
    "JARVIS_PIPELINE_DIR",
    str(Path(__file__).resolve().parent.parent / "config" / "pipelines"),
))

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StepType(str, Enum):
    EXEC = "exec"
    FUNCTION = "function"
    AI_PROMPT = "ai_prompt"
    APPROVAL = "approval"
    CONDITION = "condition"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_APPROVAL = "awaiting_approval"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """Captures the outcome of a single pipeline step."""

    step_id: str
    status: StepStatus = StepStatus.PENDING
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    return_value: Any = None
    duration_ms: float = 0.0
    success: bool = False
    approved: Optional[bool] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "step_id": self.step_id,
            "status": self.status.value if isinstance(self.status, StepStatus) else self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "approved": self.approved,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        # return_value only when JSON-serialisable
        try:
            json.dumps(self.return_value)
            data["return_value"] = self.return_value
        except (TypeError, ValueError):
            data["return_value"] = str(self.return_value) if self.return_value is not None else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResult":
        data = dict(data)
        if "status" in data and isinstance(data["status"], str):
            data["status"] = StepStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PipelineStep:
    """Definition of a single step inside a pipeline."""

    id: str
    step_type: StepType
    command: Optional[str] = None
    function_name: Optional[str] = None
    ai_prompt: Optional[str] = None
    approval_message: Optional[str] = None
    stdin_source: Optional[str] = None          # e.g. "fetch.stdout"
    condition: Optional[str] = None             # e.g. "approve.approved"
    timeout_ms: int = DEFAULT_STEP_TIMEOUT_MS
    env: Optional[Dict[str, str]] = None
    continue_on_error: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["step_type"] = self.step_type.value if isinstance(self.step_type, StepType) else self.step_type
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineStep":
        data = dict(data)
        if "step_type" in data and isinstance(data["step_type"], str):
            data["step_type"] = StepType(data["step_type"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Pipeline:
    """An ordered sequence of PipelineSteps with metadata."""

    name: str
    steps: List[PipelineStep] = field(default_factory=list)
    pipeline_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    fail_fast: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    # -- helpers --------------------------------------------------------------

    def step_index(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        raise KeyError(f"Step '{step_id}' not found in pipeline '{self.name}'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pipeline_id": self.pipeline_id,
            "description": self.description,
            "fail_fast": self.fail_fast,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pipeline":
        data = dict(data)
        steps_raw = data.pop("steps", [])
        steps = [PipelineStep.from_dict(s) for s in steps_raw]
        return cls(steps=steps, **{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        logger.info("Pipeline '%s' saved to %s", self.name, path)
        return path

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Pipeline":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


@dataclass
class PipelineResult:
    """Aggregate result returned after running (or partially running) a pipeline."""

    pipeline_id: str
    pipeline_name: str
    status: PipelineStatus
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    resume_token: Optional[str] = None
    current_step: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status.value,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "resume_token": self.resume_token,
            "current_step": self.current_step,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    @property
    def success(self) -> bool:
        return self.status == PipelineStatus.COMPLETED

    @property
    def final_stdout(self) -> str:
        """The stdout of the last successfully completed step."""
        for sr in reversed(list(self.step_results.values())):
            if sr.success and sr.stdout:
                return sr.stdout
        return ""

# ---------------------------------------------------------------------------
# PipelineStore  --  durable persistence for paused pipelines
# ---------------------------------------------------------------------------

class PipelineStore:
    """Persists paused pipeline state to disk so it survives process restarts."""

    def __init__(self, store_dir: Optional[Union[str, Path]] = None):
        self._dir = Path(store_dir) if store_dir else PIPELINE_STORE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, token: str) -> Path:
        return self._dir / f"{token}.pipeline.json"

    def save_state(self, token: str, state: Dict[str, Any]) -> None:
        with self._lock:
            self._path(token).write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        logger.debug("Pipeline state saved: %s", token)

    def load_state(self, token: str) -> Dict[str, Any]:
        path = self._path(token)
        if not path.exists():
            raise FileNotFoundError(f"No paused pipeline for token '{token}'")
        return json.loads(path.read_text(encoding="utf-8"))

    def remove(self, token: str) -> None:
        with self._lock:
            path = self._path(token)
            if path.exists():
                path.unlink()
        logger.debug("Pipeline state removed: %s", token)

    def list_tokens(self) -> List[str]:
        return [p.stem.replace(".pipeline", "") for p in self._dir.glob("*.pipeline.json")]

    def list_pending(self) -> List[Dict[str, Any]]:
        pending: List[Dict[str, Any]] = []
        for token in self.list_tokens():
            try:
                state = self.load_state(token)
                pending.append({
                    "token": token,
                    "pipeline_name": state.get("pipeline", {}).get("name", "unknown"),
                    "paused_at_step": state.get("paused_at_step"),
                    "approval_message": state.get("approval_message", ""),
                    "paused_at": state.get("paused_at"),
                    "expires_at": state.get("expires_at"),
                })
            except Exception:
                logger.warning("Corrupt pipeline state file for token %s", token)
        return pending


# ---------------------------------------------------------------------------
# ApprovalGate
# ---------------------------------------------------------------------------

class ApprovalGate:
    """Manages creation and validation of approval pause-points."""

    def __init__(self, store: PipelineStore):
        self._store = store

    def create(
        self,
        pipeline: Pipeline,
        step: PipelineStep,
        step_results: Dict[str, StepResult],
        timeout_ms: int = DEFAULT_APPROVAL_TIMEOUT_MS,
    ) -> str:
        token = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        expires = now + timedelta(milliseconds=timeout_ms)
        state = {
            "token": token,
            "pipeline": pipeline.to_dict(),
            "step_results": {k: v.to_dict() for k, v in step_results.items()},
            "paused_at_step": step.id,
            "approval_message": step.approval_message or "Approval required to continue.",
            "paused_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "timeout_ms": timeout_ms,
        }
        self._store.save_state(token, state)
        logger.info("Approval gate created: token=%s step=%s", token, step.id)
        return token

    def validate_token(self, token: str) -> Dict[str, Any]:
        state = self._store.load_state(token)
        expires_at = datetime.fromisoformat(state["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            self._store.remove(token)
            raise TimeoutError(
                f"Approval token '{token}' expired at {state['expires_at']}"
            )
        return state

    def consume(self, token: str) -> Dict[str, Any]:
        state = self.validate_token(token)
        self._store.remove(token)
        return state


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def _interpolate(template: str, results: Dict[str, StepResult]) -> str:
    """Replace {step_id.field} placeholders with values from prior step results."""
    import re

    def _replacer(match: "re.Match[str]") -> str:
        ref = match.group(1)
        parts = ref.split(".", 1)
        if len(parts) != 2:
            return match.group(0)
        step_id, attr = parts
        sr = results.get(step_id)
        if sr is None:
            return match.group(0)
        value = getattr(sr, attr, match.group(0))
        return str(value) if value is not None else ""

    return re.sub(r"\{(\w+\.\w+)\}", _replacer, template)


def _evaluate_condition(condition: str, results: Dict[str, StepResult]) -> bool:
    """
    Evaluate a simple condition like 'approve.approved' or 'test.success'.
    Returns True when the referenced attribute is truthy.
    Supports negation via '!' prefix: '!deploy.success'.
    """
    negate = False
    cond = condition.strip()
    if cond.startswith("!"):
        negate = True
        cond = cond[1:].strip()

    parts = cond.split(".", 1)
    if len(parts) != 2:
        logger.warning("Malformed condition: '%s'", condition)
        return False

    step_id, attr = parts
    sr = results.get(step_id)
    if sr is None:
        logger.warning("Condition references unknown step '%s'", step_id)
        return False

    value = getattr(sr, attr, None)
    result = bool(value)
    return (not result) if negate else result


# ---------------------------------------------------------------------------
# Built-in step handlers
# ---------------------------------------------------------------------------

def _handle_exec(step: PipelineStep, stdin_data: Optional[str], _results: Dict[str, StepResult]) -> StepResult:
    """Execute a shell command via subprocess."""
    sr = StepResult(step_id=step.id, status=StepStatus.RUNNING, started_at=datetime.now(timezone.utc).isoformat())
    t0 = time.monotonic()
    try:
        env = None
        if step.env:
            env = {**os.environ, **step.env}
        timeout_s = step.timeout_ms / 1000.0

        command = _interpolate(step.command, _results) if step.command else ""
        input_data = stdin_data.encode("utf-8") if stdin_data else None

        proc = subprocess.run(
            command,
            shell=True,
            input=input_data,
            capture_output=True,
            timeout=timeout_s,
            env=env,
            cwd=None,
        )
        sr.stdout = proc.stdout.decode("utf-8", errors="replace")
        sr.stderr = proc.stderr.decode("utf-8", errors="replace")
        sr.exit_code = proc.returncode
        sr.success = proc.returncode == 0
        sr.status = StepStatus.SUCCEEDED if sr.success else StepStatus.FAILED
    except subprocess.TimeoutExpired:
        sr.error = f"Step '{step.id}' timed out after {step.timeout_ms}ms"
        sr.status = StepStatus.FAILED
        sr.success = False
    except Exception as exc:
        sr.error = f"Step '{step.id}' exec error: {exc}"
        sr.status = StepStatus.FAILED
        sr.success = False
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        sr.finished_at = datetime.now(timezone.utc).isoformat()
    return sr


def _handle_function(step: PipelineStep, stdin_data: Optional[str], _results: Dict[str, StepResult]) -> StepResult:
    """Call a registered Python callable."""
    # The actual callable is injected by PipelineRunner via the registry.
    # This default handler exists only as a fallback.
    sr = StepResult(step_id=step.id, status=StepStatus.FAILED)
    sr.error = f"No callable registered for function step '{step.id}' (name={step.function_name})"
    return sr


def _handle_ai_prompt(step: PipelineStep, stdin_data: Optional[str], results: Dict[str, StepResult]) -> StepResult:
    """
    Placeholder handler for AI prompt steps.
    In production, replace via runner.register_step_handler("ai_prompt", your_fn).
    The prompt text is interpolated and returned as stdout so downstream steps
    can consume it.
    """
    sr = StepResult(step_id=step.id, status=StepStatus.RUNNING, started_at=datetime.now(timezone.utc).isoformat())
    t0 = time.monotonic()
    try:
        prompt = _interpolate(step.ai_prompt or "", results)
        if stdin_data:
            prompt = f"{prompt}\n\n{stdin_data}"
        # Default: echo prompt as stdout (override with a real LLM handler)
        sr.stdout = prompt
        sr.success = True
        sr.status = StepStatus.SUCCEEDED
    except Exception as exc:
        sr.error = f"AI prompt step '{step.id}' failed: {exc}"
        sr.status = StepStatus.FAILED
        sr.success = False
    finally:
        sr.duration_ms = (time.monotonic() - t0) * 1000
        sr.finished_at = datetime.now(timezone.utc).isoformat()
    return sr


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------

class PipelineRunner:
    """Executes Pipeline objects step-by-step with support for approval pauses."""

    def __init__(self, store: Optional[PipelineStore] = None):
        self._store = store or PipelineStore()
        self._gate = ApprovalGate(self._store)
        self._handlers: Dict[str, Callable] = {
            StepType.EXEC.value: _handle_exec,
            StepType.FUNCTION.value: _handle_function,
            StepType.AI_PROMPT.value: _handle_ai_prompt,
        }
        self._functions: Dict[str, Callable] = {}
        self._lock = threading.Lock()

    # -- public API -----------------------------------------------------------

    def register_step_handler(self, step_type: str, handler_fn: Callable) -> None:
        """Register (or override) a handler for a given step type."""
        self._handlers[step_type] = handler_fn
        logger.info("Registered step handler for '%s'", step_type)

    def register_function(self, name: str, fn: Callable) -> None:
        """Register a Python callable that can be invoked by function steps."""
        self._functions[name] = fn
        logger.info("Registered pipeline function '%s'", name)

    def run(self, pipeline: Pipeline) -> PipelineResult:
        """Execute a pipeline from the beginning."""
        logger.info("Starting pipeline '%s' (%s)", pipeline.name, pipeline.pipeline_id)
        return self._execute(pipeline, start_index=0, prior_results={})

    def resume(self, token: str, approved: bool = True) -> PipelineResult:
        """Resume a pipeline that is paused at an approval gate."""
        state = self._gate.consume(token)

        pipeline = Pipeline.from_dict(state["pipeline"])
        step_results: Dict[str, StepResult] = {
            k: StepResult.from_dict(v) for k, v in state["step_results"].items()
        }

        paused_step_id = state["paused_at_step"]
        paused_idx = pipeline.step_index(paused_step_id)

        # Record the approval decision on the gate step.
        gate_result = step_results.get(paused_step_id, StepResult(step_id=paused_step_id))
        gate_result.approved = approved
        gate_result.success = approved
        gate_result.status = StepStatus.SUCCEEDED if approved else StepStatus.FAILED
        gate_result.finished_at = datetime.now(timezone.utc).isoformat()
        step_results[paused_step_id] = gate_result

        if not approved:
            logger.info("Pipeline '%s' approval rejected at step '%s'", pipeline.name, paused_step_id)
            return PipelineResult(
                pipeline_id=pipeline.pipeline_id,
                pipeline_name=pipeline.name,
                status=PipelineStatus.CANCELLED,
                step_results=step_results,
                current_step=paused_step_id,
                error="Approval rejected by user.",
            )

        logger.info("Resuming pipeline '%s' after approval at step '%s'", pipeline.name, paused_step_id)
        return self._execute(pipeline, start_index=paused_idx + 1, prior_results=step_results)

    def cancel(self, token: str) -> None:
        """Cancel a paused pipeline and remove its stored state."""
        try:
            self._store.remove(token)
            logger.info("Pipeline cancelled: token=%s", token)
        except Exception as exc:
            logger.error("Failed to cancel pipeline token=%s: %s", token, exc)
            raise

    def list_pending(self) -> List[Dict[str, Any]]:
        """Return metadata about all pipelines currently awaiting approval."""
        return self._store.list_pending()

    # -- internal execution ---------------------------------------------------

    def _execute(
        self,
        pipeline: Pipeline,
        start_index: int,
        prior_results: Dict[str, StepResult],
    ) -> PipelineResult:
        step_results = dict(prior_results)
        result = PipelineResult(
            pipeline_id=pipeline.pipeline_id,
            pipeline_name=pipeline.name,
            status=PipelineStatus.RUNNING,
            step_results=step_results,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        for idx in range(start_index, len(pipeline.steps)):
            step = pipeline.steps[idx]
            result.current_step = step.id

            # -- Condition check -------------------------------------------------
            if step.condition:
                if not _evaluate_condition(step.condition, step_results):
                    logger.info("Step '%s' skipped (condition '%s' not met)", step.id, step.condition)
                    sr = StepResult(
                        step_id=step.id,
                        status=StepStatus.SKIPPED,
                        success=True,
                        started_at=datetime.now(timezone.utc).isoformat(),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    )
                    step_results[step.id] = sr
                    continue

            # -- Approval gate ---------------------------------------------------
            if step.step_type == StepType.APPROVAL:
                sr = StepResult(
                    step_id=step.id,
                    status=StepStatus.AWAITING_APPROVAL,
                    started_at=datetime.now(timezone.utc).isoformat(),
                )
                step_results[step.id] = sr

                token = self._gate.create(
                    pipeline=pipeline,
                    step=step,
                    step_results=step_results,
                    timeout_ms=step.timeout_ms or DEFAULT_APPROVAL_TIMEOUT_MS,
                )
                result.status = PipelineStatus.AWAITING_APPROVAL
                result.resume_token = token
                logger.info(
                    "Pipeline '%s' paused at approval gate '%s' (token=%s)",
                    pipeline.name, step.id, token,
                )
                return result

            # -- Condition-only step (pure branching) ----------------------------
            if step.step_type == StepType.CONDITION:
                cond_met = True
                if step.condition:
                    cond_met = _evaluate_condition(step.condition, step_results)
                sr = StepResult(
                    step_id=step.id,
                    status=StepStatus.SUCCEEDED,
                    success=cond_met,
                    return_value=cond_met,
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                step_results[step.id] = sr
                continue

            # -- Resolve stdin ---------------------------------------------------
            stdin_data: Optional[str] = None
            if step.stdin_source:
                stdin_data = self._resolve_ref(step.stdin_source, step_results)

            # -- Dispatch to handler ---------------------------------------------
            handler = self._handlers.get(step.step_type.value)
            if handler is None:
                sr = StepResult(
                    step_id=step.id,
                    status=StepStatus.FAILED,
                    error=f"No handler registered for step type '{step.step_type.value}'",
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                step_results[step.id] = sr
                if pipeline.fail_fast:
                    result.status = PipelineStatus.FAILED
                    result.error = sr.error
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return result
                continue

            # Function steps: inject the callable from the registry.
            if step.step_type == StepType.FUNCTION:
                sr = self._run_function_step(step, stdin_data, step_results)
            else:
                sr = handler(step, stdin_data, step_results)

            step_results[step.id] = sr
            logger.info(
                "Step '%s' finished: status=%s duration=%.1fms",
                step.id, sr.status.value, sr.duration_ms,
            )

            # -- Fail-fast -------------------------------------------------------
            if not sr.success and not step.continue_on_error:
                if pipeline.fail_fast:
                    result.status = PipelineStatus.FAILED
                    result.error = sr.error or f"Step '{step.id}' failed"
                    result.finished_at = datetime.now(timezone.utc).isoformat()
                    return result

        # -- All steps completed -------------------------------------------------
        any_failure = any(
            sr.status == StepStatus.FAILED for sr in step_results.values()
        )
        result.status = PipelineStatus.FAILED if any_failure else PipelineStatus.COMPLETED
        result.finished_at = datetime.now(timezone.utc).isoformat()
        if any_failure:
            failed_ids = [sid for sid, sr in step_results.items() if sr.status == StepStatus.FAILED]
            result.error = f"Steps failed: {', '.join(failed_ids)}"
        logger.info("Pipeline '%s' finished: %s", pipeline.name, result.status.value)
        return result

    def _run_function_step(
        self,
        step: PipelineStep,
        stdin_data: Optional[str],
        results: Dict[str, StepResult],
    ) -> StepResult:
        """Execute a registered Python function step."""
        sr = StepResult(step_id=step.id, status=StepStatus.RUNNING, started_at=datetime.now(timezone.utc).isoformat())
        t0 = time.monotonic()
        fn_name = step.function_name or step.id
        fn = self._functions.get(fn_name)
        if fn is None:
            sr.status = StepStatus.FAILED
            sr.error = f"Function '{fn_name}' not registered. Use runner.register_function(name, fn)."
            sr.duration_ms = (time.monotonic() - t0) * 1000
            sr.finished_at = datetime.now(timezone.utc).isoformat()
            return sr
        try:
            ret = fn(stdin_data, results)
            if isinstance(ret, str):
                sr.stdout = ret
            elif isinstance(ret, dict):
                sr.stdout = json.dumps(ret, default=str)
                sr.return_value = ret
            else:
                sr.return_value = ret
                sr.stdout = str(ret) if ret is not None else ""
            sr.success = True
            sr.status = StepStatus.SUCCEEDED
        except Exception as exc:
            sr.error = f"Function '{fn_name}' raised: {exc}"
            sr.status = StepStatus.FAILED
            sr.success = False
        finally:
            sr.duration_ms = (time.monotonic() - t0) * 1000
            sr.finished_at = datetime.now(timezone.utc).isoformat()
        return sr

    @staticmethod
    def _resolve_ref(ref: str, results: Dict[str, StepResult]) -> Optional[str]:
        """Resolve a reference like 'step_id.stdout' to a string value."""
        parts = ref.split(".", 1)
        if len(parts) != 2:
            return None
        step_id, attr = parts
        sr = results.get(step_id)
        if sr is None:
            return None
        value = getattr(sr, attr, None)
        return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# PipelineBuilder  --  fluent API
# ---------------------------------------------------------------------------

class PipelineBuilder:
    """Fluent builder for constructing Pipeline objects."""

    def __init__(self, name: str, description: str = ""):
        self._name = name
        self._description = description
        self._steps: List[PipelineStep] = []
        self._fail_fast = True
        self._metadata: Dict[str, Any] = {}

    def step(
        self,
        step_id: str,
        *,
        exec: Optional[str] = None,
        function: Optional[str] = None,
        ai_prompt: Optional[str] = None,
        approval: bool = False,
        message: Optional[str] = None,
        stdin: Optional[str] = None,
        condition: Optional[str] = None,
        timeout_ms: int = DEFAULT_STEP_TIMEOUT_MS,
        env: Optional[Dict[str, str]] = None,
        continue_on_error: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "PipelineBuilder":
        """Add a step to the pipeline."""
        if approval:
            step_type = StepType.APPROVAL
            timeout_ms = timeout_ms if timeout_ms != DEFAULT_STEP_TIMEOUT_MS else DEFAULT_APPROVAL_TIMEOUT_MS
        elif exec is not None:
            step_type = StepType.EXEC
        elif function is not None:
            step_type = StepType.FUNCTION
        elif ai_prompt is not None:
            step_type = StepType.AI_PROMPT
        else:
            step_type = StepType.CONDITION

        ps = PipelineStep(
            id=step_id,
            step_type=step_type,
            command=exec,
            function_name=function,
            ai_prompt=ai_prompt,
            approval_message=message,
            stdin_source=stdin,
            condition=condition,
            timeout_ms=timeout_ms,
            env=env,
            continue_on_error=continue_on_error,
            metadata=metadata or {},
        )
        self._steps.append(ps)
        return self

    def fail_fast(self, enabled: bool = True) -> "PipelineBuilder":
        self._fail_fast = enabled
        return self

    def continue_on_error(self) -> "PipelineBuilder":
        self._fail_fast = False
        return self

    def with_metadata(self, **kwargs: Any) -> "PipelineBuilder":
        self._metadata.update(kwargs)
        return self

    def build(self) -> Pipeline:
        if not self._steps:
            raise ValueError("Pipeline must contain at least one step.")
        # Validate step IDs are unique.
        ids = [s.id for s in self._steps]
        dupes = [sid for sid in ids if ids.count(sid) > 1]
        if dupes:
            raise ValueError(f"Duplicate step IDs: {set(dupes)}")
        return Pipeline(
            name=self._name,
            description=self._description,
            steps=list(self._steps),
            fail_fast=self._fail_fast,
            metadata=self._metadata,
        )


# ---------------------------------------------------------------------------
# File-based pipeline loading / saving
# ---------------------------------------------------------------------------

def load_pipeline(path: Union[str, Path]) -> Pipeline:
    """Load a pipeline from a .pipeline.json file."""
    return Pipeline.load(path)


def save_pipeline(pipeline: Pipeline, path: Union[str, Path]) -> Path:
    """Save a pipeline to a .pipeline.json file."""
    return pipeline.save(path)


def list_pipeline_files(directory: Optional[Union[str, Path]] = None) -> List[Path]:
    """List all .pipeline.json files in a directory."""
    d = Path(directory) if directory else PIPELINE_STORE_DIR
    if not d.exists():
        return []
    return sorted(d.glob("*.pipeline.json"))


# ---------------------------------------------------------------------------
# Convenience: run a pipeline from a JSON file
# ---------------------------------------------------------------------------

def run_pipeline_file(
    path: Union[str, Path],
    runner: Optional[PipelineRunner] = None,
) -> PipelineResult:
    """Load and execute a pipeline from a .pipeline.json file."""
    pipeline = load_pipeline(path)
    runner = runner or PipelineRunner()
    return runner.run(pipeline)


# ---------------------------------------------------------------------------
# Module-level quick-start helpers
# ---------------------------------------------------------------------------

_default_runner: Optional[PipelineRunner] = None
_runner_lock = threading.Lock()


def get_runner() -> PipelineRunner:
    """Return (or create) a module-level default PipelineRunner."""
    global _default_runner
    with _runner_lock:
        if _default_runner is None:
            _default_runner = PipelineRunner()
        return _default_runner


def quick_run(pipeline: Pipeline) -> PipelineResult:
    """Run a pipeline using the module-level default runner."""
    return get_runner().run(pipeline)


def quick_resume(token: str, approved: bool = True) -> PipelineResult:
    """Resume a paused pipeline using the module-level default runner."""
    return get_runner().resume(token, approved=approved)


# ---------------------------------------------------------------------------
# Self-test / demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Demonstrate pipeline construction, execution, and approval flow."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    runner = PipelineRunner()

    # Register a sample function.
    def count_lines(stdin_data: Optional[str], _results: Dict[str, StepResult]) -> str:
        lines = (stdin_data or "").strip().splitlines()
        return json.dumps({"line_count": len(lines), "lines": lines})

    runner.register_function("count_lines", count_lines)

    # Build a pipeline with an approval gate.
    pipeline = (
        PipelineBuilder("demo-pipeline", description="Shows exec, function, approval, and conditional steps")
        .step("list_dir", exec='python -c "import sys; sys.stdout.reconfigure(encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56)); import os; print(chr(10).join(os.listdir(chr(46))))"')
        .step("count", function="count_lines", stdin="list_dir.stdout")
        .step("confirm", approval=True, message="Proceed with processing {count.stdout}?")
        .step("final", exec='python -c "print(chr(80)+chr(105)+chr(112)+chr(101)+chr(108)+chr(105)+chr(110)+chr(101)+chr(32)+chr(99)+chr(111)+chr(109)+chr(112)+chr(108)+chr(101)+chr(116)+chr(101)+chr(33))"', condition="confirm.approved")
        .build()
    )

    # Save and reload to prove serialisation round-trip.
    temp_path = PIPELINE_STORE_DIR / "demo.pipeline.json"
    pipeline.save(temp_path)
    pipeline = Pipeline.load(temp_path)
    temp_path.unlink(missing_ok=True)

    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("--- Running pipeline ---")
    result = runner.run(pipeline)
    print(f"Status: {result.status.value}")

    for sid, sr in result.step_results.items():
        out = (sr.stdout[:80] if sr.stdout else sr.error or "").replace("\n", " ")
        print(f"  [{sr.status.value:>18}] {sid}: {out}")

    if result.status == PipelineStatus.AWAITING_APPROVAL:
        print(f"\nApproval required. Token: {result.resume_token}")
        print("Resuming with approval=True ...")
        result = runner.resume(result.resume_token, approved=True)
        print(f"Status after resume: {result.status.value}")
        for sid, sr in result.step_results.items():
            out = (sr.stdout[:80] if sr.stdout else sr.error or "").replace("\n", " ")
            print(f"  [{sr.status.value:>18}] {sid}: {out}")

    print(f"\nFinal stdout: {result.final_stdout.strip()}")


if __name__ == "__main__":
    _demo()
