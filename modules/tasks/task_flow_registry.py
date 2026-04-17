"""
LADA Task Flow Registry

Manages multi-step task flows with:
- Sequential and parallel execution modes
- Step dependency DAG resolution
- Approval gates
- Durable state for resume
- Flow templates for reuse
"""

import os
import json
import uuid
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from modules.tasks.task_registry import (
    TaskRegistry,
    RegistryTask,
    TaskStep,
    TaskStatus,
    TaskPriority,
    StepStatus,
    StepResult,
    StepType,
    get_registry,
)

logger = logging.getLogger(__name__)


class FlowStatus(str, Enum):
    """Flow execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"


class ExecutionMode(str, Enum):
    """How flow steps are executed."""
    SEQUENTIAL = "sequential"  # One after another
    PARALLEL = "parallel"      # All at once
    DAG = "dag"               # Based on dependencies


@dataclass
class FlowStepConfig:
    """Configuration for a step in a flow."""
    id: str
    name: str
    step_type: StepType = StepType.FUNCTION
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    retries: int = 3
    continue_on_error: bool = False
    condition: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    stdin_source: Optional[str] = None
    approval_message: Optional[str] = None
    
    def to_task_step(self) -> TaskStep:
        """Convert to TaskStep for registry."""
        return TaskStep(
            id=self.id,
            name=self.name,
            step_type=self.step_type,
            action=self.action,
            parameters=self.parameters,
            timeout_seconds=self.timeout_seconds,
            retries=self.retries,
            continue_on_error=self.continue_on_error,
            condition=self.condition,
            dependencies=self.dependencies,
            stdin_source=self.stdin_source,
            approval_message=self.approval_message,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "step_type": self.step_type.value,
            "action": self.action,
            "parameters": self.parameters,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "continue_on_error": self.continue_on_error,
            "condition": self.condition,
            "dependencies": self.dependencies,
            "stdin_source": self.stdin_source,
            "approval_message": self.approval_message,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowStepConfig":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            step_type=StepType(data.get("step_type", "function")),
            action=data.get("action", ""),
            parameters=data.get("parameters", {}),
            timeout_seconds=data.get("timeout_seconds", 300),
            retries=data.get("retries", 3),
            continue_on_error=data.get("continue_on_error", False),
            condition=data.get("condition"),
            dependencies=data.get("dependencies", []),
            stdin_source=data.get("stdin_source"),
            approval_message=data.get("approval_message"),
        )


@dataclass
class FlowTemplate:
    """Reusable flow definition template."""
    id: str
    name: str
    description: str = ""
    steps: List[FlowStepConfig] = field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    timeout_seconds: int = 3600
    stop_on_failure: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "execution_mode": self.execution_mode.value,
            "timeout_seconds": self.timeout_seconds,
            "stop_on_failure": self.stop_on_failure,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowTemplate":
        steps = [FlowStepConfig.from_dict(s) for s in data.get("steps", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            execution_mode=ExecutionMode(data.get("execution_mode", "sequential")),
            timeout_seconds=data.get("timeout_seconds", 3600),
            stop_on_failure=data.get("stop_on_failure", True),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class TaskFlow:
    """
    An executing flow instance.
    
    Links to a RegistryTask but provides flow-specific metadata.
    """
    id: str  # Same as underlying task_id
    template_id: Optional[str] = None  # If created from template
    name: str = ""
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    status: FlowStatus = FlowStatus.PENDING
    stop_on_failure: bool = True
    
    # Step tracking
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    current_step_id: Optional[str] = None
    
    # Results
    outputs: Dict[str, Any] = field(default_factory=dict)  # Step outputs for piping
    error: Optional[str] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_terminal(self) -> bool:
        return self.status in (FlowStatus.COMPLETED, FlowStatus.FAILED, FlowStatus.CANCELLED)
    
    @property
    def progress_percent(self) -> int:
        if self.total_steps == 0:
            return 0
        return int((self.completed_steps + self.skipped_steps) / self.total_steps * 100)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "template_id": self.template_id,
            "name": self.name,
            "execution_mode": self.execution_mode.value,
            "status": self.status.value,
            "stop_on_failure": self.stop_on_failure,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "current_step_id": self.current_step_id,
            "outputs": self.outputs,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskFlow":
        return cls(
            id=data["id"],
            template_id=data.get("template_id"),
            name=data.get("name", ""),
            execution_mode=ExecutionMode(data.get("execution_mode", "sequential")),
            status=FlowStatus(data.get("status", "pending")),
            stop_on_failure=data.get("stop_on_failure", True),
            total_steps=data.get("total_steps", 0),
            completed_steps=data.get("completed_steps", 0),
            failed_steps=data.get("failed_steps", 0),
            skipped_steps=data.get("skipped_steps", 0),
            current_step_id=data.get("current_step_id"),
            outputs=data.get("outputs", {}),
            error=data.get("error"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


class TaskFlowRegistry:
    """
    Registry for task flows and templates.
    
    Works alongside TaskRegistry for underlying task storage,
    adding flow-specific tracking and template management.
    """
    
    DEFAULT_DIR = "data/flows"
    TEMPLATES_FILE = "flow_templates.json"
    FLOWS_FILE = "active_flows.json"
    
    def __init__(
        self,
        flows_dir: Optional[str] = None,
        task_registry: Optional[TaskRegistry] = None,
    ):
        self.flows_dir = Path(flows_dir or os.getenv("LADA_FLOWS_DIR", self.DEFAULT_DIR))
        self.flows_dir.mkdir(parents=True, exist_ok=True)
        
        self._task_registry = task_registry or get_registry()
        
        # In-memory state
        self._templates: Dict[str, FlowTemplate] = {}
        self._flows: Dict[str, TaskFlow] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Step handlers
        self._step_handlers: Dict[StepType, Callable] = {}
        
        # Load persisted state
        self._load_templates()
        self._load_flows()
        
        logger.info(f"[TaskFlowRegistry] Initialized (templates: {len(self._templates)}, flows: {len(self._flows)})")
    
    # ========================================================================
    # Templates
    # ========================================================================
    
    def create_template(
        self,
        name: str,
        steps: List[FlowStepConfig],
        description: str = "",
        execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        timeout_seconds: int = 3600,
        stop_on_failure: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FlowTemplate:
        """Create a new flow template."""
        template_id = str(uuid.uuid4())[:12]
        
        template = FlowTemplate(
            id=template_id,
            name=name,
            description=description,
            steps=steps,
            execution_mode=execution_mode,
            timeout_seconds=timeout_seconds,
            stop_on_failure=stop_on_failure,
            metadata=metadata or {},
        )
        
        with self._lock:
            self._templates[template_id] = template
            self._save_templates()
        
        logger.info(f"[TaskFlowRegistry] Created template: {template_id} ({name})")
        return template
    
    def get_template(self, template_id: str) -> Optional[FlowTemplate]:
        """Get template by ID."""
        with self._lock:
            return self._templates.get(template_id)
    
    def list_templates(self) -> List[FlowTemplate]:
        """List all templates."""
        with self._lock:
            return list(self._templates.values())
    
    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        with self._lock:
            if template_id in self._templates:
                del self._templates[template_id]
                self._save_templates()
                logger.info(f"[TaskFlowRegistry] Deleted template: {template_id}")
                return True
            return False
    
    # ========================================================================
    # Flow Creation
    # ========================================================================
    
    def create_flow(
        self,
        name: str,
        steps: List[FlowStepConfig],
        execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        stop_on_failure: bool = True,
        agent_id: str = "default",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskFlow:
        """Create a new flow with inline step definitions."""
        # Create underlying task in registry
        task = self._task_registry.create(
            name=name,
            steps=[s.to_task_step() for s in steps],
            priority=TaskPriority.NORMAL,
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata,
        )
        
        # Create flow wrapper
        flow = TaskFlow(
            id=task.id,
            name=name,
            execution_mode=execution_mode,
            stop_on_failure=stop_on_failure,
            total_steps=len(steps),
            metadata=metadata or {},
        )
        
        with self._lock:
            self._flows[flow.id] = flow
            self._save_flows()
        
        logger.info(f"[TaskFlowRegistry] Created flow: {flow.id} ({name}, {len(steps)} steps)")
        return flow
    
    def create_flow_from_template(
        self,
        template_id: str,
        agent_id: str = "default",
        session_id: Optional[str] = None,
        override_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[TaskFlow]:
        """Create a flow from a template."""
        template = self.get_template(template_id)
        if not template:
            return None
        
        # Apply parameter overrides
        steps = []
        for step_config in template.steps:
            step = FlowStepConfig(
                id=step_config.id,
                name=step_config.name,
                step_type=step_config.step_type,
                action=step_config.action,
                parameters={**step_config.parameters, **(override_params or {})},
                timeout_seconds=step_config.timeout_seconds,
                retries=step_config.retries,
                continue_on_error=step_config.continue_on_error,
                condition=step_config.condition,
                dependencies=step_config.dependencies,
                stdin_source=step_config.stdin_source,
                approval_message=step_config.approval_message,
            )
            steps.append(step)
        
        flow = self.create_flow(
            name=template.name,
            steps=steps,
            execution_mode=template.execution_mode,
            stop_on_failure=template.stop_on_failure,
            agent_id=agent_id,
            session_id=session_id,
            metadata={"template_id": template_id, **template.metadata},
        )
        flow.template_id = template_id
        
        return flow
    
    # ========================================================================
    # Flow Operations
    # ========================================================================
    
    def get_flow(self, flow_id: str) -> Optional[TaskFlow]:
        """Get flow by ID."""
        with self._lock:
            return self._flows.get(flow_id)
    
    def get_task(self, flow_id: str) -> Optional[RegistryTask]:
        """Get underlying task for flow."""
        return self._task_registry.get(flow_id)
    
    def list_flows(
        self,
        agent_id: Optional[str] = None,
        status: Optional[FlowStatus] = None,
        active_only: bool = False,
    ) -> List[TaskFlow]:
        """List flows with optional filters."""
        with self._lock:
            results = []
            for flow in self._flows.values():
                if status and flow.status != status:
                    continue
                if active_only and flow.is_terminal:
                    continue
                
                # Filter by agent via underlying task
                if agent_id:
                    task = self._task_registry.get(flow.id)
                    if not task or task.agent_id != agent_id:
                        continue
                
                results.append(flow)
            return results
    
    def start_flow(self, flow_id: str) -> bool:
        """Start flow execution."""
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            if flow.status != FlowStatus.PENDING:
                return False
            
            flow.status = FlowStatus.RUNNING
            flow.started_at = datetime.now().isoformat()
            
            # Queue underlying task
            self._task_registry.queue(flow_id)
            self._task_registry.start(flow_id)
            
            # Set first step
            task = self._task_registry.get(flow_id)
            if task and task.steps:
                flow.current_step_id = task.steps[0].id
            
            self._save_flows()
        
        logger.info(f"[TaskFlowRegistry] Started flow: {flow_id}")
        return True
    
    def complete_step(
        self,
        flow_id: str,
        step_id: str,
        result: StepResult,
    ) -> Optional[str]:
        """
        Record step completion and determine next step.
        Returns next step ID or None if flow complete.
        """
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return None
            
            task = self._task_registry.get(flow_id)
            if not task:
                return None
            
            # Update step result
            self._task_registry.update_step(flow_id, step_id, result)
            
            # Update flow counters
            if result.status == StepStatus.SUCCEEDED:
                flow.completed_steps += 1
                if result.return_value is not None:
                    flow.outputs[step_id] = result.return_value
                elif result.stdout:
                    flow.outputs[step_id] = result.stdout
            elif result.status == StepStatus.FAILED:
                flow.failed_steps += 1
                if flow.stop_on_failure:
                    flow.status = FlowStatus.FAILED
                    flow.error = result.error
                    flow.completed_at = datetime.now().isoformat()
                    self._task_registry.fail(flow_id, result.error or "Step failed")
                    self._save_flows()
                    return None
            elif result.status == StepStatus.SKIPPED:
                flow.skipped_steps += 1
            
            # Find next step
            next_step_id = self._get_next_step(flow, task, step_id)
            
            if next_step_id:
                flow.current_step_id = next_step_id
            else:
                # Flow complete
                if flow.failed_steps > 0 and flow.stop_on_failure:
                    flow.status = FlowStatus.FAILED
                else:
                    flow.status = FlowStatus.COMPLETED
                flow.completed_at = datetime.now().isoformat()
                self._task_registry.complete(flow_id, flow.outputs)
            
            self._save_flows()
            return next_step_id
    
    def pause_flow(self, flow_id: str, step_id: Optional[str] = None) -> Optional[str]:
        """Pause flow and get resume token."""
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return None
            
            flow.status = FlowStatus.PAUSED
            flow.current_step_id = step_id
            
            token = self._task_registry.pause(flow_id, step_id)
            self._save_flows()
            
            return token
    
    def await_approval(
        self,
        flow_id: str,
        step_id: str,
        message: str,
    ) -> Optional[str]:
        """Set flow to awaiting approval."""
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return None
            
            flow.status = FlowStatus.AWAITING_APPROVAL
            flow.current_step_id = step_id
            
            token = self._task_registry.await_approval(flow_id, step_id, message)
            self._save_flows()
            
            return token
    
    def resume_flow(self, token: str, approved: bool = True) -> Optional[TaskFlow]:
        """Resume a paused flow."""
        task = self._task_registry.resume(token, approved)
        if not task:
            return None
        
        with self._lock:
            flow = self._flows.get(task.id)
            if flow:
                if task.status == TaskStatus.RUNNING:
                    flow.status = FlowStatus.RUNNING
                elif task.status == TaskStatus.CANCELLED:
                    flow.status = FlowStatus.CANCELLED
                    flow.error = task.error
                self._save_flows()
            
            return flow
    
    def cancel_flow(self, flow_id: str, reason: Optional[str] = None) -> bool:
        """Cancel a flow."""
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            
            flow.status = FlowStatus.CANCELLED
            flow.error = reason
            flow.completed_at = datetime.now().isoformat()
            
            self._task_registry.cancel(flow_id, reason)
            self._save_flows()
        
        logger.info(f"[TaskFlowRegistry] Cancelled flow: {flow_id}")
        return True
    
    # ========================================================================
    # Step Handlers
    # ========================================================================
    
    def register_step_handler(
        self,
        step_type: StepType,
        handler: Callable[[TaskStep, Dict[str, Any]], StepResult],
    ):
        """Register a handler for a step type."""
        self._step_handlers[step_type] = handler
    
    def get_step_handler(self, step_type: StepType) -> Optional[Callable]:
        """Get handler for step type."""
        return self._step_handlers.get(step_type)
    
    # ========================================================================
    # Internal
    # ========================================================================
    
    def _get_next_step(
        self,
        flow: TaskFlow,
        task: RegistryTask,
        completed_step_id: str,
    ) -> Optional[str]:
        """Determine next step to execute."""
        if flow.execution_mode == ExecutionMode.SEQUENTIAL:
            # Find current step index and return next
            for i, step in enumerate(task.steps):
                if step.id == completed_step_id:
                    if i + 1 < len(task.steps):
                        return task.steps[i + 1].id
                    return None
        
        elif flow.execution_mode == ExecutionMode.DAG:
            # Find steps whose dependencies are all complete
            completed_ids = set(
                sid for sid, result in task.step_results.items()
                if result.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED)
            )
            
            for step in task.steps:
                if step.id in completed_ids:
                    continue
                if step.id in task.step_results:
                    continue  # Already running/failed
                
                # Check dependencies
                deps_met = all(dep in completed_ids for dep in step.dependencies)
                if deps_met:
                    return step.id
        
        return None
    
    # ========================================================================
    # Persistence
    # ========================================================================
    
    def _save_templates(self):
        """Save templates to disk."""
        try:
            filepath = self.flows_dir / self.TEMPLATES_FILE
            data = {tid: t.to_dict() for tid, t in self._templates.items()}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TaskFlowRegistry] Failed to save templates: {e}")
    
    def _load_templates(self):
        """Load templates from disk."""
        try:
            filepath = self.flows_dir / self.TEMPLATES_FILE
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for tid, tdata in data.items():
                    self._templates[tid] = FlowTemplate.from_dict(tdata)
        except Exception as e:
            logger.error(f"[TaskFlowRegistry] Failed to load templates: {e}")
    
    def _save_flows(self):
        """Save active flows to disk."""
        try:
            filepath = self.flows_dir / self.FLOWS_FILE
            data = {fid: f.to_dict() for fid, f in self._flows.items()}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TaskFlowRegistry] Failed to save flows: {e}")
    
    def _load_flows(self):
        """Load active flows from disk."""
        try:
            filepath = self.flows_dir / self.FLOWS_FILE
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for fid, fdata in data.items():
                    self._flows[fid] = TaskFlow.from_dict(fdata)
        except Exception as e:
            logger.error(f"[TaskFlowRegistry] Failed to load flows: {e}")


# ============================================================================
# Singleton
# ============================================================================

_flow_registry_instance: Optional[TaskFlowRegistry] = None
_flow_registry_lock = threading.Lock()


def get_flow_registry() -> TaskFlowRegistry:
    """Get singleton TaskFlowRegistry instance."""
    global _flow_registry_instance
    if _flow_registry_instance is None:
        with _flow_registry_lock:
            if _flow_registry_instance is None:
                _flow_registry_instance = TaskFlowRegistry()
    return _flow_registry_instance
