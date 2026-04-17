"""
LADA Approval Hooks

Provides integration hooks for requiring approvals at execution points.

Features:
- Decorator-based approval requirements
- Pre-execution approval checks
- Async approval flow support
- Integration with task registry
"""

import functools
import logging
import threading
from typing import Optional, Dict, Any, Callable, List, TypeVar, Union
from dataclasses import dataclass, field
from datetime import datetime

from modules.approval.policy_engine import (
    PolicyEngine,
    PolicyMatch,
    ActionSeverity,
    ApprovalType,
    get_policy_engine,
)

from modules.approval.approval_queue import (
    ApprovalQueue,
    ApprovalRequest,
    ApprovalStatus,
    get_approval_queue,
)

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable)


@dataclass
class ApprovalHook:
    """
    A hook that intercepts execution and requires approval.
    
    Can be registered for:
    - Specific actions/commands
    - Pattern matches
    - Pre-execution checks
    """
    id: str
    name: str
    description: str = ""
    
    # Matching
    action_patterns: List[str] = field(default_factory=list)
    command_patterns: List[str] = field(default_factory=list)
    
    # Approval config
    severity: ActionSeverity = ActionSeverity.DANGEROUS
    approval_type: ApprovalType = ApprovalType.EXPLICIT
    timeout_seconds: int = 86400
    message_template: str = "Approval required for: {action}"
    preview_template: str = ""
    
    # Scope
    agent_ids: List[str] = field(default_factory=list)  # Empty = all
    channel_types: List[str] = field(default_factory=list)  # Empty = all
    
    # State
    enabled: bool = True
    priority: int = 0
    
    def matches(
        self,
        action: str,
        command: str = "",
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> bool:
        """Check if this hook matches the context."""
        if not self.enabled:
            return False
        
        # Check action patterns
        action_match = False
        if not self.action_patterns:
            action_match = True
        else:
            import re
            for pattern in self.action_patterns:
                # Simple glob-to-regex
                regex = pattern.replace("*", ".*").replace("?", ".")
                if re.match(f"^{regex}$", action, re.IGNORECASE):
                    action_match = True
                    break
        
        if not action_match:
            return False
        
        # Check command patterns
        if self.command_patterns and command:
            import re
            command_match = False
            for pattern in self.command_patterns:
                regex = pattern.replace("*", ".*").replace("?", ".")
                if re.search(regex, command, re.IGNORECASE):
                    command_match = True
                    break
            if not command_match:
                return False
        
        # Check scope
        if self.agent_ids and agent_id and agent_id not in self.agent_ids:
            return False
        
        if self.channel_types and channel_type and channel_type not in self.channel_types:
            return False
        
        return True
    
    def format_message(self, action: str, params: Dict[str, Any]) -> str:
        """Format approval message."""
        try:
            return self.message_template.format(action=action, **params)
        except (KeyError, ValueError):
            return self.message_template.format(action=action)
    
    def format_preview(self, action: str, params: Dict[str, Any]) -> str:
        """Format preview message."""
        if not self.preview_template:
            return ""
        try:
            return self.preview_template.format(action=action, **params)
        except (KeyError, ValueError):
            return self.preview_template.format(action=action)


class ApprovalHookRegistry:
    """
    Registry for approval hooks.
    
    Manages hooks and provides check methods for executors.
    """
    
    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        approval_queue: Optional[ApprovalQueue] = None,
    ):
        self._policy_engine = policy_engine or get_policy_engine()
        self._approval_queue = approval_queue or get_approval_queue()
        
        self._hooks: Dict[str, ApprovalHook] = {}
        self._lock = threading.RLock()
        
        logger.info("[ApprovalHookRegistry] Initialized")
    
    def register(self, hook: ApprovalHook) -> bool:
        """Register an approval hook."""
        with self._lock:
            self._hooks[hook.id] = hook
        logger.info(f"[ApprovalHookRegistry] Registered hook: {hook.id}")
        return True
    
    def unregister(self, hook_id: str) -> bool:
        """Unregister a hook."""
        with self._lock:
            if hook_id in self._hooks:
                del self._hooks[hook_id]
                return True
        return False
    
    def get(self, hook_id: str) -> Optional[ApprovalHook]:
        """Get hook by ID."""
        with self._lock:
            return self._hooks.get(hook_id)
    
    def list_hooks(self) -> List[ApprovalHook]:
        """List all hooks."""
        with self._lock:
            return list(self._hooks.values())
    
    def find_matching_hook(
        self,
        action: str,
        command: str = "",
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> Optional[ApprovalHook]:
        """Find first matching hook for context."""
        with self._lock:
            # Sort by priority (descending)
            sorted_hooks = sorted(
                self._hooks.values(),
                key=lambda h: h.priority,
                reverse=True,
            )
            
            for hook in sorted_hooks:
                if hook.matches(action, command, agent_id, channel_type):
                    return hook
        
        return None
    
    def check_approval_required(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check if approval is required for an action.
        
        Returns dict with:
        - required: bool
        - severity: str
        - approval_type: str
        - message: str
        - source: "hook" | "policy" | None
        """
        params = params or {}
        
        # Check hooks first
        hook = self.find_matching_hook(action, command, agent_id, channel_type)
        if hook:
            return {
                "required": hook.approval_type not in (ApprovalType.NONE, ApprovalType.IMPLICIT),
                "severity": hook.severity.value,
                "approval_type": hook.approval_type.value,
                "message": hook.format_message(action, params),
                "preview": hook.format_preview(action, params),
                "timeout_seconds": hook.timeout_seconds,
                "source": "hook",
                "hook_id": hook.id,
            }
        
        # Check policy engine
        policy_match = self._policy_engine.evaluate(
            action=action,
            command=command,
            params=params,
            agent_id=agent_id,
            channel_type=channel_type,
        )
        
        if policy_match.is_forbidden:
            return {
                "required": False,
                "forbidden": True,
                "severity": ActionSeverity.FORBIDDEN.value,
                "message": policy_match.message or f"Action '{action}' is forbidden",
                "source": "policy",
            }
        
        if policy_match.requires_approval:
            return {
                "required": True,
                "severity": policy_match.severity.value,
                "approval_type": policy_match.approval_type.value,
                "message": policy_match.message or f"Approval required for: {action}",
                "timeout_seconds": policy_match.timeout_seconds,
                "source": "policy",
                "rule_id": policy_match.rule.id if policy_match.rule else None,
            }
        
        return {
            "required": False,
            "severity": policy_match.severity.value,
            "source": None,
        }
    
    def request_approval(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: str = "default",
        session_id: Optional[str] = None,
        channel_type: Optional[str] = None,
        requestor_id: Optional[str] = None,
        message: Optional[str] = None,
        preview: Optional[str] = None,
        task_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        step_id: Optional[str] = None,
        callback_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[ApprovalRequest]:
        """
        Create an approval request if needed.
        
        Returns ApprovalRequest if approval is required, None if allowed.
        """
        params = params or {}
        
        check = self.check_approval_required(
            action=action,
            command=command,
            params=params,
            agent_id=agent_id,
            channel_type=channel_type,
        )
        
        if check.get("forbidden"):
            # Create a rejected request for audit
            request = self._approval_queue.create_request(
                action=action,
                command=command,
                params=params,
                agent_id=agent_id,
                session_id=session_id,
                channel_type=channel_type,
                requestor_id=requestor_id,
                message=check.get("message", "Forbidden action"),
            )
            request.status = ApprovalStatus.DENIED
            return request
        
        if not check.get("required"):
            return None
        
        # Create approval request
        policy_match = self._policy_engine.evaluate(
            action=action,
            command=command,
            params=params,
            agent_id=agent_id,
            channel_type=channel_type,
        )
        
        request = self._approval_queue.create_request(
            action=action,
            command=command,
            params=params,
            agent_id=agent_id,
            session_id=session_id,
            channel_type=channel_type,
            requestor_id=requestor_id,
            policy_match=policy_match,
            message=message or check.get("message", ""),
            preview=preview or check.get("preview", ""),
            timeout_seconds=check.get("timeout_seconds", 86400),
            task_id=task_id,
            flow_id=flow_id,
            step_id=step_id,
            callback_data=callback_data,
        )
        
        return request
    
    def wait_for_approval(
        self,
        request: ApprovalRequest,
        timeout_seconds: Optional[int] = None,
    ) -> ApprovalStatus:
        """
        Block until approval is resolved or timeout.
        
        For async flows, use request.token to check status later.
        """
        import time
        
        timeout = timeout_seconds or request.timeout_seconds
        start = datetime.now()
        
        while True:
            # Refresh request
            current = self._approval_queue.get(request.id)
            if not current:
                return ApprovalStatus.CANCELLED
            
            if current.is_resolved:
                return current.status
            
            if current.is_expired:
                return ApprovalStatus.EXPIRED
            
            # Check timeout
            elapsed = (datetime.now() - start).total_seconds()
            if elapsed >= timeout:
                return ApprovalStatus.EXPIRED
            
            time.sleep(0.5)


# ============================================================================
# Singleton
# ============================================================================

_registry_instance: Optional[ApprovalHookRegistry] = None
_registry_lock = threading.Lock()


def get_hook_registry() -> ApprovalHookRegistry:
    """Get singleton ApprovalHookRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = ApprovalHookRegistry()
    return _registry_instance


# ============================================================================
# Decorator
# ============================================================================

def require_approval(
    action: Optional[str] = None,
    severity: ActionSeverity = ActionSeverity.DANGEROUS,
    approval_type: ApprovalType = ApprovalType.EXPLICIT,
    message: str = "Approval required",
    timeout_seconds: int = 86400,
) -> Callable[[F], F]:
    """
    Decorator to require approval before function execution.
    
    Usage:
        @require_approval(action="delete_file", severity=ActionSeverity.DANGEROUS)
        def delete_file(filepath: str) -> bool:
            ...
    
    The decorated function will:
    1. Check if approval is required
    2. If yes, create approval request and raise ApprovalRequiredException
    3. If no, execute normally
    
    For sync execution, catch ApprovalRequiredException to get the token.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_action = action or func.__name__
            
            registry = get_hook_registry()
            check = registry.check_approval_required(
                action=func_action,
                params=kwargs,
            )
            
            if check.get("forbidden"):
                raise PermissionError(f"Action '{func_action}' is forbidden")
            
            if check.get("required"):
                request = registry.request_approval(
                    action=func_action,
                    params=kwargs,
                    message=message,
                )
                if request:
                    raise ApprovalRequiredException(request)
            
            return func(*args, **kwargs)
        
        return wrapper  # type: ignore
    
    return decorator


class ApprovalRequiredException(Exception):
    """Raised when approval is required before execution."""
    
    def __init__(self, request: ApprovalRequest):
        self.request = request
        self.token = request.token
        super().__init__(f"Approval required (token: {request.token})")


# ============================================================================
# Integration Helper
# ============================================================================

def check_and_request_approval(
    action: str,
    command: str = "",
    params: Optional[Dict[str, Any]] = None,
    agent_id: str = "default",
    session_id: Optional[str] = None,
    auto_approve_safe: bool = True,
) -> Union[Dict[str, Any], ApprovalRequest]:
    """
    Helper function to check and optionally create approval request.
    
    Returns:
    - Dict with "allowed": True if no approval needed
    - Dict with "allowed": False, "reason" if forbidden
    - ApprovalRequest if approval needed
    """
    registry = get_hook_registry()
    
    check = registry.check_approval_required(
        action=action,
        command=command,
        params=params,
        agent_id=agent_id,
    )
    
    if check.get("forbidden"):
        return {
            "allowed": False,
            "reason": check.get("message", "Action is forbidden"),
        }
    
    if not check.get("required"):
        return {
            "allowed": True,
            "severity": check.get("severity", "safe"),
        }
    
    # Create approval request
    request = registry.request_approval(
        action=action,
        command=command,
        params=params,
        agent_id=agent_id,
        session_id=session_id,
    )
    
    return request
