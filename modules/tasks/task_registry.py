"""
LADA Task Registry

Central registry for all tasks with durable persistence, status tracking,
and support for multiple execution models.

Features:
- Typed task IDs (OpenClaw-style) with UUID fallback
- 9-state task lifecycle (matching task_orchestrator)
- Step-level results and progress tracking
- JSON persistence to disk (active + history)
- Resume tokens for paused tasks
- Agent-aware task namespacing
- Thread-safe operations
"""

import os
import json
import uuid
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

TASK_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
TASK_ID_PREFIXES: Dict[str, str] = {
    "bash": "b",
    "shell": "b",
    "agent": "a",
    "remote_agent": "r",
    "teammate": "t",
    "workflow": "w",
    "mcp_monitor": "m",
    "dream": "d",
}


def generate_task_id(task_type: str) -> str:
    """Generate OpenClaw-style task IDs with typed prefixes."""
    prefix = TASK_ID_PREFIXES.get((task_type or "").strip().lower(), "x")
    random_bytes = os.urandom(8)
    suffix = "".join(TASK_ID_ALPHABET[b % len(TASK_ID_ALPHABET)] for b in random_bytes)
    return f"{prefix}{suffix}"


# ============================================================================
# Enums
# ============================================================================

class TaskStatus(str, Enum):
    """Task lifecycle states (union of all existing modules)"""
    PENDING = "pending"           # Created, not yet queued
    QUEUED = "queued"             # In queue, waiting for worker
    RUNNING = "running"           # Currently executing
    COMPLETED = "completed"       # Successfully finished
    FAILED = "failed"             # Execution failed
    CANCELLED = "cancelled"       # Manually cancelled
    PAUSED = "paused"             # Paused, can resume
    WAITING = "waiting"           # Waiting for dependencies
    AWAITING_APPROVAL = "awaiting_approval"  # Human approval needed


class TaskPriority(str, Enum):
    """Task execution priority"""
    CRITICAL = "critical"     # Immediate execution
    HIGH = "high"             # Above normal
    NORMAL = "normal"         # Default
    LOW = "low"               # Below normal
    BACKGROUND = "background" # When resources available


class StepStatus(str, Enum):
    """Individual step states"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_APPROVAL = "awaiting_approval"


class StepType(str, Enum):
    """Step execution type"""
    EXEC = "exec"           # Run shell command
    FUNCTION = "function"   # Call Python function
    AI_PROMPT = "ai_prompt" # Send to AI model
    APPROVAL = "approval"   # Wait for human approval
    CONDITION = "condition" # Conditional branching


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class StepResult:
    """Result from a single step execution."""
    step_id: str
    status: StepStatus = StepStatus.PENDING
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    return_value: Any = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    approved: Optional[bool] = None  # For approval steps
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "return_value": self.return_value,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "approved": self.approved,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResult":
        return cls(
            step_id=data["step_id"],
            status=StepStatus(data.get("status", "pending")),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code"),
            return_value=data.get("return_value"),
            duration_ms=data.get("duration_ms", 0.0),
            error=data.get("error"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            approved=data.get("approved"),
        )


@dataclass
class TaskStep:
    """A single step within a task."""
    id: str
    name: str = ""
    step_type: StepType = StepType.FUNCTION
    action: str = ""  # Command, function name, or prompt
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Execution control
    timeout_seconds: int = 300
    retries: int = 3
    continue_on_error: bool = False
    condition: Optional[str] = None  # Execute only if condition met
    
    # Dependencies (for DAG execution within task)
    dependencies: List[str] = field(default_factory=list)
    
    # Data flow
    stdin_source: Optional[str] = None  # Step ID to get stdin from
    env: Optional[Dict[str, str]] = None
    
    # Approval
    approval_message: Optional[str] = None
    
    # Runtime
    result: Optional[StepResult] = None
    
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
            "env": self.env,
            "approval_message": self.approval_message,
            "result": self.result.to_dict() if self.result else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        result = None
        if data.get("result"):
            result = StepResult.from_dict(data["result"])
        
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
            env=data.get("env"),
            approval_message=data.get("approval_message"),
            result=result,
        )


@dataclass
class RegistryTask:
    """
    Central task representation combining features from all existing modules.
    
    Supports:
    - Simple single-action tasks
    - Multi-step sequential tasks
    - DAG-based parallel execution
    - Approval gates
    """
    
    # Identity
    id: str  # UUID
    name: str
    description: str = ""
    
    # Ownership
    agent_id: str = "default"
    session_id: Optional[str] = None
    created_by: Optional[str] = None  # User/system that created
    
    # Execution config
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: float = 3600.0
    max_retries: int = 3
    
    # Simple action (for single-step tasks)
    action: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    
    # Multi-step (for complex tasks)
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    
    # Dependencies (for DAG scheduling)
    dependencies: List[str] = field(default_factory=list)  # Task IDs
    
    # State
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    retry_count: int = 0
    
    # Results
    result: Any = None
    error: Optional[str] = None
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Resume support
    resume_token: Optional[str] = None
    paused_at_step: Optional[str] = None
    expires_at: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    @property
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
    
    @property
    def is_active(self) -> bool:
        """Check if task is currently active."""
        return self.status in (TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.WAITING)
    
    @property
    def can_resume(self) -> bool:
        """Check if task can be resumed."""
        return self.status in (TaskStatus.PAUSED, TaskStatus.AWAITING_APPROVAL)
    
    @property
    def total_steps(self) -> int:
        """Total number of steps in task."""
        return len(self.steps) if self.steps else 1
    
    @property
    def progress_percent(self) -> int:
        """Progress as integer percentage."""
        return int(self.progress * 100)
    
    def update_progress(self):
        """Update progress based on step completion."""
        if not self.steps:
            self.progress = 1.0 if self.is_terminal else 0.0
            return
        
        completed = sum(
            1 for s in self.steps 
            if s.result and s.result.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED)
        )
        self.progress = completed / len(self.steps)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "created_by": self.created_by,
            "priority": self.priority.value,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "action": self.action,
            "params": self.params,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "progress": self.progress,
            "retry_count": self.retry_count,
            "result": self.result,
            "error": self.error,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "created_at": self.created_at,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "resume_token": self.resume_token,
            "paused_at_step": self.paused_at_step,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryTask":
        """Deserialize from dictionary."""
        steps = [TaskStep.from_dict(s) for s in data.get("steps", [])]
        step_results = {
            k: StepResult.from_dict(v) 
            for k, v in data.get("step_results", {}).items()
        }
        
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            agent_id=data.get("agent_id", "default"),
            session_id=data.get("session_id"),
            created_by=data.get("created_by"),
            priority=TaskPriority(data.get("priority", "normal")),
            timeout_seconds=data.get("timeout_seconds", 3600.0),
            max_retries=data.get("max_retries", 3),
            action=data.get("action"),
            params=data.get("params", {}),
            steps=steps,
            current_step_index=data.get("current_step_index", 0),
            dependencies=data.get("dependencies", []),
            status=TaskStatus(data.get("status", "pending")),
            progress=data.get("progress", 0.0),
            retry_count=data.get("retry_count", 0),
            result=data.get("result"),
            error=data.get("error"),
            step_results=step_results,
            created_at=data.get("created_at", datetime.now().isoformat()),
            queued_at=data.get("queued_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            resume_token=data.get("resume_token"),
            paused_at_step=data.get("paused_at_step"),
            expires_at=data.get("expires_at"),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )


# ============================================================================
# Task Registry
# ============================================================================

class TaskRegistry:
    """
    Central registry for all LADA tasks.
    
    Features:
    - In-memory active task tracking
    - Durable persistence (active + history)
    - Resume token management
    - Agent-aware namespacing
    - Thread-safe operations
    """
    
    DEFAULT_DIR = "data/tasks"
    ACTIVE_FILE = "active_tasks.json"
    HISTORY_FILE = "task_history.json"
    PAUSED_DIR = "paused"
    MAX_HISTORY = 1000
    
    def __init__(self, tasks_dir: Optional[str] = None, use_typed_ids: bool = True):
        self.tasks_dir = Path(tasks_dir or os.getenv("LADA_TASKS_DIR", self.DEFAULT_DIR))
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.use_typed_ids = use_typed_ids
        
        self.paused_dir = self.tasks_dir / self.PAUSED_DIR
        self.paused_dir.mkdir(exist_ok=True)
        
        # In-memory state
        self._tasks: Dict[str, RegistryTask] = {}
        self._history: List[Dict[str, Any]] = []
        self._resume_tokens: Dict[str, str] = {}  # token -> task_id
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Callbacks
        self._listeners: List[Callable[[RegistryTask, str], None]] = []
        
        # Load persisted state
        self._load_active()
        self._load_history()
        self._load_paused()
        
        logger.info(f"[TaskRegistry] Initialized (dir: {self.tasks_dir}, active: {len(self._tasks)}, history: {len(self._history)})")
    
    # ========================================================================
    # Task CRUD
    # ========================================================================
    
    def create(
        self,
        name: str,
        action: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        steps: Optional[List[TaskStep]] = None,
        dependencies: Optional[List[str]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_seconds: float = 3600.0,
        agent_id: str = "default",
        session_id: Optional[str] = None,
        created_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> RegistryTask:
        """Create and register a new task."""
        task_type = (action or (metadata or {}).get("task_type") or "").strip().lower()
        task_id = str(uuid.uuid4())
        if self.use_typed_ids and task_type:
            with self._lock:
                candidate = generate_task_id(task_type)
                while candidate in self._tasks:
                    candidate = generate_task_id(task_type)
                task_id = candidate
        
        task = RegistryTask(
            id=task_id,
            name=name,
            action=action,
            params=params or {},
            steps=steps or [],
            dependencies=dependencies or [],
            priority=priority,
            timeout_seconds=timeout_seconds,
            agent_id=agent_id,
            session_id=session_id,
            created_by=created_by,
            metadata=metadata or {},
            tags=tags or [],
        )
        
        with self._lock:
            self._tasks[task_id] = task
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Created task: {task_id} ({name})")
        self._notify_listeners(task, "created")
        return task
    
    def get(self, task_id: str) -> Optional[RegistryTask]:
        """Get task by ID."""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_by_name(self, name: str, agent_id: Optional[str] = None) -> List[RegistryTask]:
        """Get tasks by name (optionally filtered by agent)."""
        with self._lock:
            results = []
            for task in self._tasks.values():
                if task.name == name:
                    if agent_id is None or task.agent_id == agent_id:
                        results.append(task)
            return results
    
    def list_tasks(
        self,
        agent_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        active_only: bool = False,
        tag: Optional[str] = None,
    ) -> List[RegistryTask]:
        """List tasks with optional filters."""
        with self._lock:
            results = []
            for task in self._tasks.values():
                if agent_id and task.agent_id != agent_id:
                    continue
                if status and task.status != status:
                    continue
                if active_only and not task.is_active:
                    continue
                if tag and tag not in task.tags:
                    continue
                results.append(task)
            return results
    
    def count(self, agent_id: Optional[str] = None) -> int:
        """Count tasks (optionally for specific agent)."""
        with self._lock:
            if agent_id:
                return sum(1 for t in self._tasks.values() if t.agent_id == agent_id)
            return len(self._tasks)
    
    def update(self, task: RegistryTask) -> bool:
        """Update task in registry."""
        with self._lock:
            if task.id not in self._tasks:
                return False
            self._tasks[task.id] = task
            self._persist_active()
        
        self._notify_listeners(task, "updated")
        return True
    
    def delete(self, task_id: str) -> bool:
        """Delete task from registry."""
        with self._lock:
            task = self._tasks.pop(task_id, None)
            if not task:
                return False
            
            # Remove resume token if exists
            if task.resume_token:
                self._resume_tokens.pop(task.resume_token, None)
                self._remove_paused_state(task.resume_token)
            
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Deleted task: {task_id}")
        self._notify_listeners(task, "deleted")
        return True
    
    # ========================================================================
    # Task Lifecycle
    # ========================================================================
    
    def queue(self, task_id: str) -> bool:
        """Queue task for execution."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status != TaskStatus.PENDING:
                return False
            
            task.status = TaskStatus.QUEUED
            task.queued_at = datetime.now().isoformat()
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Queued task: {task_id}")
        self._notify_listeners(task, "queued")
        return True
    
    def start(self, task_id: str) -> bool:
        """Mark task as started."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status not in (TaskStatus.QUEUED, TaskStatus.WAITING):
                return False
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Started task: {task_id}")
        self._notify_listeners(task, "started")
        return True
    
    def complete(self, task_id: str, result: Any = None) -> bool:
        """Mark task as completed."""
        notification_payload = None
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            task.result = result
            task.completed_at = datetime.now().isoformat()
            
            # Move to history
            self._add_to_history(task)
            notification_payload = (
                task.id,
                "completed",
                f"Task '{task.name}' completed",
                result,
                self._build_usage_metrics(task),
            )
            
            self._persist_active()
        
        self._publish_task_notification(*notification_payload)
        logger.info(f"[TaskRegistry] Completed task: {task_id}")
        self._notify_listeners(task, "completed")
        return True
    
    def fail(self, task_id: str, error: str) -> bool:
        """Mark task as failed."""
        notification_payload = None
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.now().isoformat()
            
            self._add_to_history(task)
            notification_payload = (
                task.id,
                "failed",
                f"Task '{task.name}' failed",
                error,
                self._build_usage_metrics(task),
            )
            self._persist_active()
        
        self._publish_task_notification(*notification_payload)
        logger.info(f"[TaskRegistry] Failed task: {task_id}: {error}")
        self._notify_listeners(task, "failed")
        return True
    
    def cancel(self, task_id: str, reason: Optional[str] = None) -> bool:
        """Cancel task."""
        notification_payload = None
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.is_terminal:
                return False
            
            task.status = TaskStatus.CANCELLED
            task.error = reason or "Cancelled by user"
            task.completed_at = datetime.now().isoformat()
            
            self._add_to_history(task)
            notification_payload = (
                task.id,
                "killed",
                f"Task '{task.name}' cancelled",
                task.error,
                self._build_usage_metrics(task),
            )
            self._persist_active()
        
        self._publish_task_notification(*notification_payload)
        logger.info(f"[TaskRegistry] Cancelled task: {task_id}")
        self._notify_listeners(task, "cancelled")
        return True
    
    def pause(self, task_id: str, step_id: Optional[str] = None, expires_hours: int = 24) -> Optional[str]:
        """
        Pause task and generate resume token.
        Returns the resume token or None if pause failed.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            if task.status not in (TaskStatus.RUNNING, TaskStatus.WAITING):
                return None
            
            # Generate resume token
            token = str(uuid.uuid4())[:8]  # Short token
            expires = datetime.now() + timedelta(hours=expires_hours)
            
            task.status = TaskStatus.PAUSED
            task.resume_token = token
            task.paused_at_step = step_id
            task.expires_at = expires.isoformat()
            
            # Register token
            self._resume_tokens[token] = task_id
            
            # Persist paused state
            self._save_paused_state(task)
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Paused task: {task_id} (token: {token})")
        self._notify_listeners(task, "paused")
        return token
    
    def await_approval(self, task_id: str, step_id: str, message: str, expires_hours: int = 24) -> Optional[str]:
        """
        Set task to awaiting approval state.
        Returns the resume token for approval.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            
            token = str(uuid.uuid4())[:8]
            expires = datetime.now() + timedelta(hours=expires_hours)
            
            task.status = TaskStatus.AWAITING_APPROVAL
            task.resume_token = token
            task.paused_at_step = step_id
            task.expires_at = expires.isoformat()
            task.metadata["approval_message"] = message
            
            self._resume_tokens[token] = task_id
            self._save_paused_state(task)
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Task awaiting approval: {task_id} (token: {token})")
        self._notify_listeners(task, "awaiting_approval")
        return token
    
    def resume(self, token: str, approved: bool = True) -> Optional[RegistryTask]:
        """
        Resume a paused/awaiting_approval task by token.
        Returns the task if resumed successfully.
        """
        with self._lock:
            task_id = self._resume_tokens.get(token)
            if not task_id:
                # Try loading from disk
                task = self._load_paused_state(token)
                if not task:
                    return None
                task_id = task.id
                self._tasks[task_id] = task
            else:
                task = self._tasks.get(task_id)
            
            if not task or not task.can_resume:
                return None
            
            # Check expiration
            if task.expires_at:
                expires = datetime.fromisoformat(task.expires_at)
                if datetime.now() > expires:
                    task.status = TaskStatus.CANCELLED
                    task.error = "Resume token expired"
                    self._add_to_history(task)
                    self._cleanup_resume(task)
                    return None
            
            # Record approval decision
            if task.status == TaskStatus.AWAITING_APPROVAL:
                task.metadata["approved"] = approved
                if task.paused_at_step:
                    step_result = task.step_results.get(task.paused_at_step)
                    if step_result:
                        step_result.approved = approved
            
            if not approved:
                task.status = TaskStatus.CANCELLED
                task.error = "Approval denied"
                self._add_to_history(task)
                self._cleanup_resume(task)
                logger.info(f"[TaskRegistry] Task approval denied: {task_id}")
                return task
            
            # Resume execution
            task.status = TaskStatus.RUNNING
            self._cleanup_resume(task)
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Resumed task: {task_id}")
        self._notify_listeners(task, "resumed")
        return task
    
    def retry(self, task_id: str) -> bool:
        """Retry a failed task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status != TaskStatus.FAILED:
                return False
            if task.retry_count >= task.max_retries:
                return False
            
            task.status = TaskStatus.PENDING
            task.retry_count += 1
            task.error = None
            task.result = None
            task.started_at = None
            task.completed_at = None
            
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Retrying task: {task_id} (attempt {task.retry_count})")
        self._notify_listeners(task, "retrying")
        return True
    
    # ========================================================================
    # Step Progress
    # ========================================================================
    
    def update_step(self, task_id: str, step_id: str, result: StepResult) -> bool:
        """Update a step's result."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            task.step_results[step_id] = result
            
            # Update step in steps list
            for step in task.steps:
                if step.id == step_id:
                    step.result = result
                    break
            
            # Update overall progress
            task.update_progress()
            
            # Update current step index
            if result.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED):
                for i, step in enumerate(task.steps):
                    if step.id == step_id:
                        task.current_step_index = i + 1
                        break
            
            self._persist_active()
        
        return True
    
    # ========================================================================
    # Dependency Checking
    # ========================================================================
    
    def check_dependencies(self, task_id: str) -> bool:
        """Check if all task dependencies are complete."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            for dep_id in task.dependencies:
                dep = self._tasks.get(dep_id)
                if not dep or dep.status != TaskStatus.COMPLETED:
                    return False
            
            return True
    
    def get_ready_tasks(self, agent_id: Optional[str] = None) -> List[RegistryTask]:
        """Get tasks that are ready to execute (dependencies met)."""
        with self._lock:
            ready = []
            for task in self._tasks.values():
                if agent_id and task.agent_id != agent_id:
                    continue
                if task.status == TaskStatus.PENDING and self.check_dependencies(task.id):
                    ready.append(task)
            return ready
    
    # ========================================================================
    # History
    # ========================================================================
    
    def get_history(
        self,
        agent_id: Optional[str] = None,
        limit: int = 100,
        status: Optional[TaskStatus] = None,
    ) -> List[Dict[str, Any]]:
        """Get task history with optional filters."""
        with self._lock:
            results = []
            for entry in reversed(self._history):
                if agent_id and entry.get("agent_id") != agent_id:
                    continue
                if status and entry.get("status") != status.value:
                    continue
                results.append(entry)
                if len(results) >= limit:
                    break
            return results
    
    def _add_to_history(self, task: RegistryTask):
        """Add task to history (thread-unsafe, call within lock)."""
        self._history.append(task.to_dict())
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]
        self._persist_history()
    
    # ========================================================================
    # Listeners
    # ========================================================================
    
    def add_listener(self, callback: Callable[[RegistryTask, str], None]):
        """Add state change listener."""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[RegistryTask, str], None]):
        """Remove state change listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def _notify_listeners(self, task: RegistryTask, event: str):
        """Notify all listeners of state change."""
        for listener in self._listeners:
            try:
                listener(task, event)
            except Exception as e:
                logger.error(f"[TaskRegistry] Listener error: {e}")

    def _build_usage_metrics(self, task: RegistryTask) -> Dict[str, int]:
        """Build minimal usage metrics for task notifications."""
        duration_ms = 0
        try:
            if task.started_at and task.completed_at:
                duration_ms = int(
                    (datetime.fromisoformat(task.completed_at) - datetime.fromisoformat(task.started_at)).total_seconds() * 1000
                )
            elif task.created_at and task.completed_at:
                duration_ms = int(
                    (datetime.fromisoformat(task.completed_at) - datetime.fromisoformat(task.created_at)).total_seconds() * 1000
                )
        except Exception:
            duration_ms = 0

        return {
            "total_tokens": int(task.metadata.get("total_tokens", 0) or 0),
            "tool_uses": int(task.metadata.get("tool_uses", 0) or 0),
            "duration_ms": duration_ms,
        }

    def _publish_task_notification(
        self,
        task_id: str,
        status: str,
        summary: str,
        result: Any,
        usage: Dict[str, int],
    ) -> None:
        """Publish task lifecycle notifications in OpenClaw-compatible XML."""
        try:
            from modules.tasks.task_notifications import create_task_notification_xml

            result_text = None if result is None else str(result)
            notification = create_task_notification_xml(
                task_id=task_id,
                status=status,
                summary=summary,
                result=result_text,
                usage=usage,
            )
            logger.info(f"[TaskRegistry] Task notification: {notification}")
        except Exception as exc:
            logger.error(f"[TaskRegistry] Failed to publish task notification: {exc}")
    
    # ========================================================================
    # Persistence
    # ========================================================================
    
    def _persist_active(self):
        """Save active tasks to disk."""
        try:
            filepath = self.tasks_dir / self.ACTIVE_FILE
            data = {tid: task.to_dict() for tid, task in self._tasks.items()}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to persist active tasks: {e}")
    
    def _load_active(self):
        """Load active tasks from disk."""
        try:
            filepath = self.tasks_dir / self.ACTIVE_FILE
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for tid, task_data in data.items():
                    self._tasks[tid] = RegistryTask.from_dict(task_data)
                logger.info(f"[TaskRegistry] Loaded {len(self._tasks)} active tasks")
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to load active tasks: {e}")
    
    def _persist_history(self):
        """Save history to disk."""
        try:
            filepath = self.tasks_dir / self.HISTORY_FILE
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to persist history: {e}")
    
    def _load_history(self):
        """Load history from disk."""
        try:
            filepath = self.tasks_dir / self.HISTORY_FILE
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
                logger.info(f"[TaskRegistry] Loaded {len(self._history)} history entries")
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to load history: {e}")
    
    def _save_paused_state(self, task: RegistryTask):
        """Save paused task state for durable resume."""
        if not task.resume_token:
            return
        try:
            filepath = self.paused_dir / f"{task.resume_token}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to save paused state: {e}")
    
    def _load_paused_state(self, token: str) -> Optional[RegistryTask]:
        """Load paused task from disk."""
        try:
            filepath = self.paused_dir / f"{token}.json"
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return RegistryTask.from_dict(data)
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to load paused state: {e}")
        return None
    
    def _load_paused(self):
        """Load all paused tasks from disk."""
        try:
            for filepath in self.paused_dir.glob("*.json"):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                token = filepath.stem
                task = RegistryTask.from_dict(data)
                if task.id not in self._tasks:
                    self._tasks[task.id] = task
                self._resume_tokens[token] = task.id
            logger.info(f"[TaskRegistry] Loaded {len(self._resume_tokens)} paused tasks")
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to load paused tasks: {e}")
    
    def _remove_paused_state(self, token: str):
        """Remove paused state file."""
        try:
            filepath = self.paused_dir / f"{token}.json"
            if filepath.exists():
                filepath.unlink()
        except Exception as e:
            logger.error(f"[TaskRegistry] Failed to remove paused state: {e}")
    
    def _cleanup_resume(self, task: RegistryTask):
        """Clean up resume token after resume or cancel."""
        if task.resume_token:
            self._resume_tokens.pop(task.resume_token, None)
            self._remove_paused_state(task.resume_token)
            task.resume_token = None
            task.paused_at_step = None
            task.expires_at = None
    
    # ========================================================================
    # Maintenance
    # ========================================================================
    
    def reconcile(self) -> Dict[str, int]:
        """
        Reconcile task state after restart.
        - Move stale RUNNING tasks to PENDING
        - Clean expired paused tasks
        - Return counts of actions taken
        """
        counts = {"stale_reset": 0, "expired_cancelled": 0}
        now = datetime.now()
        
        with self._lock:
            for task in list(self._tasks.values()):
                # Reset stale running tasks (no heartbeat mechanism yet)
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PENDING
                    task.started_at = None
                    counts["stale_reset"] += 1
                
                # Cancel expired paused/approval tasks
                if task.status in (TaskStatus.PAUSED, TaskStatus.AWAITING_APPROVAL):
                    if task.expires_at:
                        expires = datetime.fromisoformat(task.expires_at)
                        if now > expires:
                            task.status = TaskStatus.CANCELLED
                            task.error = "Resume token expired"
                            self._cleanup_resume(task)
                            self._add_to_history(task)
                            counts["expired_cancelled"] += 1
            
            self._persist_active()
        
        logger.info(f"[TaskRegistry] Reconciled: {counts}")
        return counts
    
    def cleanup_completed(self, older_than_hours: int = 24) -> int:
        """Remove completed tasks older than threshold."""
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        removed = 0
        
        with self._lock:
            for task_id in list(self._tasks.keys()):
                task = self._tasks[task_id]
                if task.is_terminal and task.completed_at:
                    completed = datetime.fromisoformat(task.completed_at)
                    if completed < cutoff:
                        del self._tasks[task_id]
                        removed += 1
            
            if removed > 0:
                self._persist_active()
        
        logger.info(f"[TaskRegistry] Cleaned up {removed} completed tasks")
        return removed


# ============================================================================
# Singleton
# ============================================================================

_registry_instance: Optional[TaskRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> TaskRegistry:
    """Get singleton TaskRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = TaskRegistry()
    return _registry_instance
