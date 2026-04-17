"""
LADA Subagent Runtime

Manages subagent lifecycle: spawn, execution, termination.

Features:
- Spawn subagents with isolated context
- Track hierarchy (parent/child relationships)
- Timeout handling with graceful termination
- Result aggregation
"""

import os
import uuid
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class SubagentStatus(str, Enum):
    """Subagent execution status."""
    PENDING = "pending"
    SPAWNING = "spawning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SubagentConfig:
    """
    Configuration for spawning a subagent.
    """
    # Identity
    agent_type: str                      # e.g., "research", "code", "planning"
    task_description: str                # What the subagent should do
    
    # Hierarchy
    parent_id: Optional[str] = None      # Parent subagent ID (None for root)
    session_id: Optional[str] = None     # Session to associate with
    
    # Resources
    timeout_seconds: int = 300           # Max execution time (5 min default)
    max_tokens: int = 4096               # Max tokens for response
    model_tier: str = "balanced"         # Model tier to use
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    
    # Behavior
    allow_subagents: bool = True         # Can spawn nested subagents
    inherit_context: bool = True         # Inherit parent context
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "task_description": self.task_description,
            "parent_id": self.parent_id,
            "session_id": self.session_id,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
            "model_tier": self.model_tier,
            "context": self.context,
            "tools": self.tools,
            "allow_subagents": self.allow_subagents,
            "inherit_context": self.inherit_context,
        }


@dataclass
class SubagentResult:
    """
    Result from subagent execution.
    """
    success: bool
    output: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Metrics
    tokens_used: int = 0
    duration_ms: int = 0
    
    # Error info
    error: Optional[str] = None
    error_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "error_type": self.error_type,
        }


@dataclass
class SubagentState:
    """
    Runtime state of a subagent.
    """
    # Identity
    subagent_id: str
    config: SubagentConfig
    
    # Hierarchy
    depth: int = 0
    children: List[str] = field(default_factory=list)
    
    # Status
    status: SubagentStatus = SubagentStatus.PENDING
    result: Optional[SubagentResult] = None
    
    # Timing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Internal
    _future: Optional[Future] = field(default=None, repr=False)
    _cancelled: bool = field(default=False, repr=False)
    
    @property
    def is_terminal(self) -> bool:
        """Check if subagent is in a terminal state."""
        return self.status in (
            SubagentStatus.COMPLETED,
            SubagentStatus.FAILED,
            SubagentStatus.TIMEOUT,
            SubagentStatus.CANCELLED,
        )
    
    @property
    def id(self) -> str:
        """Alias for subagent_id for API compatibility."""
        return self.subagent_id
    
    @property
    def name(self) -> str:
        """Get subagent name from config."""
        return self.config.agent_type
    
    @property
    def parent_id(self) -> Optional[str]:
        """Get parent ID from config."""
        return self.config.parent_id
    
    @property
    def context(self) -> Dict[str, Any]:
        """Get context from config."""
        return self.config.context
    
    @property
    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds."""
        if not self.started_at:
            return 0
        
        start = datetime.fromisoformat(self.started_at)
        if self.completed_at:
            end = datetime.fromisoformat(self.completed_at)
        else:
            end = datetime.now()
        
        return int((end - start).total_seconds() * 1000)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subagent_id": self.subagent_id,
            "config": self.config.to_dict(),
            "depth": self.depth,
            "children": self.children,
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_ms": self.elapsed_ms,
        }


# ============================================================================
# Subagent Runtime
# ============================================================================

class SubagentRuntime:
    """
    Runtime for spawning and managing subagents.
    
    Features:
    - Spawn subagents with isolated context
    - Track parent/child hierarchy
    - Enforce depth and concurrency limits
    - Handle timeouts gracefully
    """
    
    def __init__(
        self,
        max_depth: int = 5,
        max_concurrent: int = 10,
        max_total: int = 50,
        executor_fn: Optional[Callable[[SubagentConfig], Awaitable[SubagentResult]]] = None,
    ):
        """
        Initialize subagent runtime.
        
        Args:
            max_depth: Maximum nesting depth
            max_concurrent: Maximum concurrent subagents
            max_total: Maximum total subagents per session
            executor_fn: Function to execute subagent tasks
        """
        self._max_depth = max_depth
        self._max_concurrent = max_concurrent
        self._max_total = max_total
        
        self._subagents: Dict[str, SubagentState] = {}
        self._session_counts: Dict[str, int] = {}  # session_id -> count
        
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._executor_fn = executor_fn or self._default_executor
        
        self._lock = threading.RLock()
        
        logger.info(
            f"[SubagentRuntime] Initialized: "
            f"max_depth={max_depth}, max_concurrent={max_concurrent}"
        )
    
    def spawn(
        self,
        config: Optional[SubagentConfig] = None,
        *,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SubagentState:
        """
        Spawn a new subagent.
        
        Args:
            config: Subagent configuration (full config object)
            name: Agent type/name (used if config not provided)
            parent_id: Parent agent ID
            context: Initial context
            **kwargs: Additional config options
        
        Returns:
            SubagentState object
        
        Raises:
            DepthLimitExceeded: If nesting too deep
            ConcurrencyLimitExceeded: If too many concurrent subagents
        """
        from modules.subagents.limits import (
            DepthLimitExceeded,
            ConcurrencyLimitExceeded,
        )
        
        # Build config from simple args if not provided
        if config is None:
            config = SubagentConfig(
                agent_type=name or "default",
                task_description=kwargs.get("task", ""),
                parent_id=parent_id,
                context=context or {},
                **{k: v for k, v in kwargs.items() if k in SubagentConfig.__dataclass_fields__},
            )
        
        with self._lock:
            # Calculate depth
            depth = 0
            if config.parent_id and config.parent_id in self._subagents:
                parent = self._subagents[config.parent_id]
                depth = parent.depth + 1
                
                # Check if parent allows subagents
                if not parent.config.allow_subagents:
                    raise DepthLimitExceeded(
                        f"Parent {config.parent_id} does not allow subagents"
                    )
            
            # Check depth limit
            if depth >= self._max_depth:
                raise DepthLimitExceeded(
                    f"Depth {depth} exceeds limit {self._max_depth}"
                )
            
            # Check concurrency limit
            running = len([s for s in self._subagents.values() if s.status == SubagentStatus.RUNNING])
            if running >= self._max_concurrent:
                raise ConcurrencyLimitExceeded(
                    f"Concurrent limit {self._max_concurrent} reached"
                )
            
            # Check session total limit
            session_id = config.session_id or "default"
            session_count = self._session_counts.get(session_id, 0)
            if session_count >= self._max_total:
                raise ConcurrencyLimitExceeded(
                    f"Session total limit {self._max_total} reached"
                )
            
            # Create subagent
            subagent_id = f"sub_{uuid.uuid4().hex[:12]}"
            
            # Inherit context from parent if configured
            if config.inherit_context and config.parent_id:
                parent = self._subagents.get(config.parent_id)
                if parent:
                    inherited_context = dict(parent.config.context)
                    inherited_context.update(config.context)
                    config.context = inherited_context
            
            state = SubagentState(
                subagent_id=subagent_id,
                config=config,
                depth=depth,
                status=SubagentStatus.SPAWNING,
            )
            
            self._subagents[subagent_id] = state
            self._session_counts[session_id] = session_count + 1
            
            # Add to parent's children
            if config.parent_id and config.parent_id in self._subagents:
                self._subagents[config.parent_id].children.append(subagent_id)
            
            # Start execution
            future = self._executor.submit(self._execute, subagent_id)
            state._future = future
            
            logger.info(
                f"[SubagentRuntime] Spawned {subagent_id}: "
                f"type={config.agent_type}, depth={depth}"
            )
            
            return subagent_id
    
    def spawn_and_get(
        self,
        config: Optional[SubagentConfig] = None,
        *,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SubagentState:
        """
        Spawn a new subagent and return the state object.
        
        Same as spawn() but returns SubagentState instead of ID string.
        Useful for API endpoints that need the full state.
        """
        subagent_id = self.spawn(config, name=name, parent_id=parent_id, context=context, **kwargs)
        return self.get(subagent_id)
    
    def get(self, subagent_id: str) -> Optional[SubagentState]:
        """Get subagent state."""
        with self._lock:
            return self._subagents.get(subagent_id)
    
    def cancel(self, subagent_id: str) -> bool:
        """
        Cancel a subagent and its children.
        
        Returns:
            True if cancelled, False if not found or already terminal
        """
        with self._lock:
            state = self._subagents.get(subagent_id)
            if not state:
                return False
            
            if state.is_terminal:
                return False
            
            # Mark as cancelled
            state._cancelled = True
            state.status = SubagentStatus.CANCELLED
            state.completed_at = datetime.now().isoformat()
            state.result = SubagentResult(
                success=False,
                error="Cancelled by user",
                error_type="CancellationError",
            )
            
            # Cancel children recursively
            for child_id in state.children:
                self.cancel(child_id)
            
            logger.info(f"[SubagentRuntime] Cancelled {subagent_id}")
            return True
    
    def wait(
        self,
        subagent_id: str,
        timeout: Optional[float] = None,
    ) -> Optional[SubagentResult]:
        """
        Wait for subagent to complete.
        
        Args:
            subagent_id: Subagent to wait for
            timeout: Max time to wait (uses config timeout if None)
        
        Returns:
            SubagentResult or None if not found
        """
        state = self.get(subagent_id)
        if not state:
            return None
        
        if state.is_terminal:
            return state.result
        
        wait_timeout = timeout or state.config.timeout_seconds
        
        try:
            if state._future:
                state._future.result(timeout=wait_timeout)
        except Exception:
            pass
        
        # Refresh state
        state = self.get(subagent_id)
        return state.result if state else None
    
    def list_subagents(
        self,
        session_id: Optional[str] = None,
        status: Optional[SubagentStatus] = None,
        parent_id: Optional[str] = None,
    ) -> List[SubagentState]:
        """List subagents with optional filtering."""
        with self._lock:
            result = list(self._subagents.values())
        
        if session_id:
            result = [s for s in result if s.config.session_id == session_id]
        
        if status:
            result = [s for s in result if s.status == status]
        
        if parent_id:
            result = [s for s in result if s.config.parent_id == parent_id]
        
        return result
    
    def get_children(self, subagent_id: str) -> List[SubagentState]:
        """Get direct children of a subagent."""
        state = self.get(subagent_id)
        if not state:
            return []
        
        return [
            self._subagents[child_id]
            for child_id in state.children
            if child_id in self._subagents
        ]
    
    def get_tree(self, subagent_id: str) -> Dict[str, Any]:
        """Get subagent tree structure."""
        state = self.get(subagent_id)
        if not state:
            return {}
        
        return {
            "subagent": state.to_dict(),
            "children": [
                self.get_tree(child_id)
                for child_id in state.children
            ],
        }
    
    def cleanup_session(self, session_id: str) -> int:
        """
        Clean up all subagents for a session.
        
        Returns:
            Number of subagents cleaned up
        """
        with self._lock:
            to_remove = [
                sid for sid, state in self._subagents.items()
                if state.config.session_id == session_id
            ]
            
            for sid in to_remove:
                self.cancel(sid)
                del self._subagents[sid]
            
            if session_id in self._session_counts:
                del self._session_counts[session_id]
            
            return len(to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        with self._lock:
            by_status = {}
            for state in self._subagents.values():
                status = state.status.value
                by_status[status] = by_status.get(status, 0) + 1
            
            return {
                "total": len(self._subagents),
                "by_status": by_status,
                "sessions": len(self._session_counts),
                "limits": {
                    "max_depth": self._max_depth,
                    "max_concurrent": self._max_concurrent,
                    "max_total": self._max_total,
                },
            }
    
    def set_executor(
        self,
        executor_fn: Callable[[SubagentConfig], Awaitable[SubagentResult]],
    ) -> None:
        """Set the executor function for subagent tasks."""
        self._executor_fn = executor_fn
    
    def _execute(self, subagent_id: str):
        """Execute subagent task (runs in thread pool)."""
        import time
        
        state = self.get(subagent_id)
        if not state:
            return
        
        start_time = time.time()
        
        with self._lock:
            state.status = SubagentStatus.RUNNING
            state.started_at = datetime.now().isoformat()
        
        try:
            # Check for cancellation
            if state._cancelled:
                return
            
            # Run executor
            if asyncio.iscoroutinefunction(self._executor_fn):
                # Run async executor in new event loop
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        asyncio.wait_for(
                            self._executor_fn(state.config),
                            timeout=state.config.timeout_seconds,
                        )
                    )
                finally:
                    loop.close()
            else:
                result = self._executor_fn(state.config)
            
            # Check for cancellation again
            if state._cancelled:
                return
            
            duration_ms = int((time.time() - start_time) * 1000)
            result.duration_ms = duration_ms
            
            with self._lock:
                state.status = SubagentStatus.COMPLETED
                state.result = result
                state.completed_at = datetime.now().isoformat()
            
            logger.info(
                f"[SubagentRuntime] Completed {subagent_id}: "
                f"success={result.success}, duration={duration_ms}ms"
            )
            
        except asyncio.TimeoutError:
            with self._lock:
                state.status = SubagentStatus.TIMEOUT
                state.result = SubagentResult(
                    success=False,
                    error=f"Timeout after {state.config.timeout_seconds}s",
                    error_type="TimeoutError",
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                state.completed_at = datetime.now().isoformat()
            
            logger.warning(f"[SubagentRuntime] Timeout {subagent_id}")
            
        except Exception as e:
            with self._lock:
                state.status = SubagentStatus.FAILED
                state.result = SubagentResult(
                    success=False,
                    error=str(e),
                    error_type=type(e).__name__,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                state.completed_at = datetime.now().isoformat()
            
            logger.error(f"[SubagentRuntime] Failed {subagent_id}: {e}")
    
    async def _default_executor(self, config: SubagentConfig) -> SubagentResult:
        """Default executor (placeholder)."""
        # In real implementation, this would call the AI provider
        return SubagentResult(
            success=True,
            output=f"Executed task: {config.task_description}",
            data={"agent_type": config.agent_type},
        )
    
    def shutdown(self):
        """Shutdown the runtime."""
        # Cancel all running subagents
        with self._lock:
            for subagent_id in list(self._subagents.keys()):
                self.cancel(subagent_id)
        
        # Shutdown executor
        self._executor.shutdown(wait=False)
        
        logger.info("[SubagentRuntime] Shutdown complete")
    
    # ─── API Helper Methods ─────────────────────────────────────────────
    
    def list_agents(self) -> List[SubagentState]:
        """Alias for list_subagents() for API compatibility."""
        return self.list_subagents()
    
    def get_agent(self, agent_id: str) -> Optional[SubagentState]:
        """Alias for get() for API compatibility."""
        return self.get(agent_id)
    
    def send_message(
        self,
        agent_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a running subagent.
        
        This is a placeholder for async communication with subagents.
        In full implementation, would use message queues/events.
        """
        state = self.get(agent_id)
        if not state:
            return {"success": False, "error": f"Subagent '{agent_id}' not found"}
        
        if state.status != SubagentStatus.RUNNING:
            return {"success": False, "error": f"Subagent is {state.status.value}, not running"}
        
        # Store message in state for subagent to process
        if not hasattr(state, 'pending_messages'):
            state.pending_messages = []
        
        state.pending_messages.append({
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        })
        
        return {"success": True, "queued": True}


# ============================================================================
# Singleton
# ============================================================================

_runtime_instance: Optional[SubagentRuntime] = None
_runtime_lock = threading.Lock()


def get_subagent_runtime() -> SubagentRuntime:
    """Get singleton SubagentRuntime instance."""
    global _runtime_instance
    if _runtime_instance is None:
        with _runtime_lock:
            if _runtime_instance is None:
                # Depth defaults to 1 to enforce non-recursive task delegation.
                _runtime_instance = SubagentRuntime(
                    max_depth=int(os.getenv("LADA_SUBAGENT_MAX_DEPTH", "1")),
                    max_concurrent=int(os.getenv("LADA_SUBAGENT_MAX_CONCURRENT", "10")),
                    max_total=int(os.getenv("LADA_SUBAGENT_MAX_TOTAL", "50")),
                )
    return _runtime_instance
