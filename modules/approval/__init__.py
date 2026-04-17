"""
LADA Approval Engine

Centralized approval system with:
- Policy-based action classification
- Scope-aware permission checks
- Multi-tier approval workflows
- Durable approval tokens
- Audit logging
"""

from modules.approval.policy_engine import (
    ActionPolicy,
    PolicyRule,
    PolicyMatch,
    ActionSeverity,
    ApprovalType,
    PolicyEngine,
    get_policy_engine,
)

from modules.approval.approval_queue import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalDecision,
    ApprovalQueue,
    get_approval_queue,
)

from modules.approval.approval_hooks import (
    ApprovalHook,
    ApprovalHookRegistry,
    get_hook_registry,
    require_approval,
    check_and_request_approval,
    ApprovalRequiredException,
)

__all__ = [
    # Policy types
    'ActionPolicy',
    'PolicyRule',
    'PolicyMatch',
    'ActionSeverity',
    'ApprovalType',
    'PolicyEngine',
    'get_policy_engine',
    # Queue types
    'ApprovalRequest',
    'ApprovalStatus',
    'ApprovalDecision',
    'ApprovalQueue',
    'get_approval_queue',
    # Hooks
    'ApprovalHook',
    'ApprovalHookRegistry',
    'get_hook_registry',
    'require_approval',
    'check_and_request_approval',
    'ApprovalRequiredException',
]
