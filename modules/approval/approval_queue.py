"""
LADA Approval Queue

Manages pending approval requests with:
- Durable token-based approvals
- Timeout handling
- Multi-party approvals
- Approval history/audit
"""

import os
import json
import uuid
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum

from modules.approval.policy_engine import (
    ActionSeverity,
    ApprovalType,
    PolicyMatch,
)

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Approval request status."""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalDecision:
    """A single approval decision."""
    approver_id: str
    approved: bool
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    pin_verified: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approver_id": self.approver_id,
            "approved": self.approved,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "pin_verified": self.pin_verified,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalDecision":
        return cls(
            approver_id=data["approver_id"],
            approved=data["approved"],
            reason=data.get("reason", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            pin_verified=data.get("pin_verified", False),
        )


@dataclass
class ApprovalRequest:
    """
    A pending approval request.
    
    Supports:
    - Single approver (default)
    - Multi-party approval (require N of M approvers)
    - Timeout expiration
    - Durable persistence
    """
    id: str  # UUID
    token: str  # Short token for resume
    
    # Action context
    action: str
    command: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    
    # Requestor context
    agent_id: str = "default"
    session_id: Optional[str] = None
    channel_type: Optional[str] = None
    requestor_id: Optional[str] = None
    
    # Policy match that triggered this
    severity: ActionSeverity = ActionSeverity.DANGEROUS
    approval_type: ApprovalType = ApprovalType.EXPLICIT
    requires_pin: bool = False
    
    # Request details
    message: str = ""  # Why approval is needed
    preview: str = ""  # What will happen
    
    # Multi-party approval
    required_approvers: int = 1
    allowed_approvers: Set[str] = field(default_factory=set)  # Empty = anyone
    
    # State
    status: ApprovalStatus = ApprovalStatus.PENDING
    decisions: List[ApprovalDecision] = field(default_factory=list)
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str = ""
    resolved_at: Optional[str] = None
    
    # Callback context
    task_id: Optional[str] = None
    flow_id: Optional[str] = None
    step_id: Optional[str] = None
    callback_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_resolved(self) -> bool:
        return self.status != ApprovalStatus.PENDING
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except ValueError:
            return False
    
    @property
    def approval_count(self) -> int:
        return sum(1 for d in self.decisions if d.approved)
    
    @property
    def denial_count(self) -> int:
        return sum(1 for d in self.decisions if not d.approved)
    
    @property
    def is_approved(self) -> bool:
        """Check if enough approvals received."""
        return self.approval_count >= self.required_approvers
    
    def add_decision(self, decision: ApprovalDecision) -> bool:
        """
        Add an approval decision.
        Returns True if this resolves the request.
        """
        # Check if approver is allowed
        if self.allowed_approvers and decision.approver_id not in self.allowed_approvers:
            return False
        
        # Check for duplicate decisions
        for d in self.decisions:
            if d.approver_id == decision.approver_id:
                return False
        
        self.decisions.append(decision)
        
        # Check if resolved
        if not decision.approved:
            # Any denial = denied
            self.status = ApprovalStatus.DENIED
            self.resolved_at = datetime.now().isoformat()
            return True
        
        if self.is_approved:
            self.status = ApprovalStatus.APPROVED
            self.resolved_at = datetime.now().isoformat()
            return True
        
        return False
    
    def expire(self):
        """Mark request as expired."""
        self.status = ApprovalStatus.EXPIRED
        self.resolved_at = datetime.now().isoformat()
    
    def cancel(self, reason: str = ""):
        """Cancel the request."""
        self.status = ApprovalStatus.CANCELLED
        self.resolved_at = datetime.now().isoformat()
        if reason:
            self.message = f"Cancelled: {reason}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "token": self.token,
            "action": self.action,
            "command": self.command,
            "params": self.params,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "channel_type": self.channel_type,
            "requestor_id": self.requestor_id,
            "severity": self.severity.value,
            "approval_type": self.approval_type.value,
            "requires_pin": self.requires_pin,
            "message": self.message,
            "preview": self.preview,
            "required_approvers": self.required_approvers,
            "allowed_approvers": list(self.allowed_approvers),
            "status": self.status.value,
            "decisions": [d.to_dict() for d in self.decisions],
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "resolved_at": self.resolved_at,
            "task_id": self.task_id,
            "flow_id": self.flow_id,
            "step_id": self.step_id,
            "callback_data": self.callback_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRequest":
        decisions = [ApprovalDecision.from_dict(d) for d in data.get("decisions", [])]
        return cls(
            id=data["id"],
            token=data["token"],
            action=data["action"],
            command=data.get("command", ""),
            params=data.get("params", {}),
            agent_id=data.get("agent_id", "default"),
            session_id=data.get("session_id"),
            channel_type=data.get("channel_type"),
            requestor_id=data.get("requestor_id"),
            severity=ActionSeverity(data.get("severity", "dangerous")),
            approval_type=ApprovalType(data.get("approval_type", "explicit")),
            requires_pin=data.get("requires_pin", False),
            message=data.get("message", ""),
            preview=data.get("preview", ""),
            required_approvers=data.get("required_approvers", 1),
            allowed_approvers=set(data.get("allowed_approvers", [])),
            status=ApprovalStatus(data.get("status", "pending")),
            decisions=decisions,
            created_at=data.get("created_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at", ""),
            resolved_at=data.get("resolved_at"),
            task_id=data.get("task_id"),
            flow_id=data.get("flow_id"),
            step_id=data.get("step_id"),
            callback_data=data.get("callback_data", {}),
        )


class ApprovalQueue:
    """
    Queue for managing pending approval requests.
    
    Features:
    - Durable persistence
    - Token-based lookup
    - Expiration handling
    - Callback notifications
    """
    
    DEFAULT_DIR = "data/approvals"
    PENDING_FILE = "pending.json"
    HISTORY_FILE = "history.json"
    MAX_HISTORY = 1000
    DEFAULT_TIMEOUT_SECONDS = 86400  # 24 hours
    
    def __init__(self, approvals_dir: Optional[str] = None):
        self.approvals_dir = Path(
            approvals_dir or os.getenv("LADA_APPROVALS_DIR", self.DEFAULT_DIR)
        )
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory state
        self._pending: Dict[str, ApprovalRequest] = {}  # id -> request
        self._tokens: Dict[str, str] = {}  # token -> id
        self._history: List[Dict[str, Any]] = []
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Callbacks
        self._on_resolved: List[Callable[[ApprovalRequest], None]] = []
        
        # Load state
        self._load_pending()
        self._load_history()
        
        logger.info(f"[ApprovalQueue] Initialized (pending: {len(self._pending)})")
    
    # ========================================================================
    # Request Creation
    # ========================================================================
    
    def create_request(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: str = "default",
        session_id: Optional[str] = None,
        channel_type: Optional[str] = None,
        requestor_id: Optional[str] = None,
        policy_match: Optional[PolicyMatch] = None,
        message: str = "",
        preview: str = "",
        timeout_seconds: Optional[int] = None,
        required_approvers: int = 1,
        allowed_approvers: Optional[Set[str]] = None,
        task_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        step_id: Optional[str] = None,
        callback_data: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Create a new approval request."""
        request_id = str(uuid.uuid4())
        token = str(uuid.uuid4())[:8]  # Short token
        
        # Get values from policy match or defaults
        severity = ActionSeverity.DANGEROUS
        approval_type = ApprovalType.EXPLICIT
        requires_pin = False
        timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS
        
        if policy_match:
            severity = policy_match.severity
            approval_type = policy_match.approval_type
            requires_pin = approval_type == ApprovalType.EXPLICIT_PIN
            if policy_match.timeout_seconds:
                timeout = policy_match.timeout_seconds
            if not message and policy_match.message:
                message = policy_match.message
        
        expires_at = (datetime.now() + timedelta(seconds=timeout)).isoformat()
        
        request = ApprovalRequest(
            id=request_id,
            token=token,
            action=action,
            command=command,
            params=params or {},
            agent_id=agent_id,
            session_id=session_id,
            channel_type=channel_type,
            requestor_id=requestor_id,
            severity=severity,
            approval_type=approval_type,
            requires_pin=requires_pin,
            message=message,
            preview=preview,
            required_approvers=required_approvers,
            allowed_approvers=allowed_approvers or set(),
            expires_at=expires_at,
            task_id=task_id,
            flow_id=flow_id,
            step_id=step_id,
            callback_data=callback_data or {},
        )
        
        with self._lock:
            self._pending[request_id] = request
            self._tokens[token] = request_id
            self._persist_pending()
        
        logger.info(f"[ApprovalQueue] Created request: {request_id} (token: {token})")
        return request
    
    # ========================================================================
    # Request Lookup
    # ========================================================================
    
    def get(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get request by ID."""
        with self._lock:
            return self._pending.get(request_id)
    
    def get_by_token(self, token: str) -> Optional[ApprovalRequest]:
        """Get request by short token."""
        with self._lock:
            request_id = self._tokens.get(token)
            if request_id:
                return self._pending.get(request_id)
        return None
    
    def list_pending(
        self,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[ApprovalRequest]:
        """List pending requests with optional filters."""
        with self._lock:
            results = []
            for request in self._pending.values():
                if request.status != ApprovalStatus.PENDING:
                    continue
                if agent_id and request.agent_id != agent_id:
                    continue
                if session_id and request.session_id != session_id:
                    continue
                if action and request.action != action:
                    continue
                results.append(request)
            return results
    
    def count_pending(self, agent_id: Optional[str] = None) -> int:
        """Count pending requests."""
        with self._lock:
            if agent_id:
                return sum(
                    1 for r in self._pending.values()
                    if r.status == ApprovalStatus.PENDING and r.agent_id == agent_id
                )
            return sum(
                1 for r in self._pending.values()
                if r.status == ApprovalStatus.PENDING
            )
    
    # ========================================================================
    # Approval Actions
    # ========================================================================
    
    def approve(
        self,
        request_id_or_token: str,
        approver_id: str,
        reason: str = "",
        pin: Optional[str] = None,
    ) -> Optional[ApprovalRequest]:
        """
        Approve a request.
        
        Returns the request if resolved, None if more approvals needed.
        """
        with self._lock:
            request = self.get(request_id_or_token) or self.get_by_token(request_id_or_token)
            if not request:
                return None
            
            if request.is_resolved:
                return request
            
            # Check expiration
            if request.is_expired:
                request.expire()
                self._finalize_request(request)
                return request
            
            # Verify PIN if required
            pin_verified = False
            if request.requires_pin:
                if not pin:
                    logger.warning(f"[ApprovalQueue] PIN required but not provided")
                    return None
                # PIN verification would happen here (hash check)
                pin_verified = True
            
            decision = ApprovalDecision(
                approver_id=approver_id,
                approved=True,
                reason=reason,
                pin_verified=pin_verified,
            )
            
            resolved = request.add_decision(decision)
            
            if resolved:
                self._finalize_request(request)
            else:
                self._persist_pending()
            
            return request
    
    def deny(
        self,
        request_id_or_token: str,
        approver_id: str,
        reason: str = "",
    ) -> Optional[ApprovalRequest]:
        """Deny a request."""
        with self._lock:
            request = self.get(request_id_or_token) or self.get_by_token(request_id_or_token)
            if not request:
                return None
            
            if request.is_resolved:
                return request
            
            decision = ApprovalDecision(
                approver_id=approver_id,
                approved=False,
                reason=reason,
            )
            
            request.add_decision(decision)
            self._finalize_request(request)
            
            return request
    
    def cancel(
        self,
        request_id_or_token: str,
        reason: str = "",
    ) -> Optional[ApprovalRequest]:
        """Cancel a pending request."""
        with self._lock:
            request = self.get(request_id_or_token) or self.get_by_token(request_id_or_token)
            if not request:
                return None
            
            if request.is_resolved:
                return request
            
            request.cancel(reason)
            self._finalize_request(request)
            
            return request
    
    # ========================================================================
    # Expiration
    # ========================================================================
    
    def expire_stale(self) -> int:
        """Expire all stale requests. Returns count expired."""
        expired = 0
        with self._lock:
            for request in list(self._pending.values()):
                if request.status == ApprovalStatus.PENDING and request.is_expired:
                    request.expire()
                    self._finalize_request(request, persist=False)
                    expired += 1
            
            if expired > 0:
                self._persist_pending()
        
        if expired > 0:
            logger.info(f"[ApprovalQueue] Expired {expired} stale requests")
        
        return expired
    
    # ========================================================================
    # Callbacks
    # ========================================================================
    
    def on_resolved(self, callback: Callable[[ApprovalRequest], None]):
        """Register callback for when requests are resolved."""
        self._on_resolved.append(callback)
    
    def _notify_resolved(self, request: ApprovalRequest):
        """Notify callbacks of resolved request."""
        for callback in self._on_resolved:
            try:
                callback(request)
            except Exception as e:
                logger.error(f"[ApprovalQueue] Callback error: {e}")
    
    # ========================================================================
    # History
    # ========================================================================
    
    def get_history(
        self,
        limit: int = 100,
        agent_id: Optional[str] = None,
        status: Optional[ApprovalStatus] = None,
    ) -> List[Dict[str, Any]]:
        """Get approval history."""
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
    
    # ========================================================================
    # Persistence
    # ========================================================================
    
    def _finalize_request(self, request: ApprovalRequest, persist: bool = True):
        """Move request from pending to history."""
        # Remove from pending
        self._pending.pop(request.id, None)
        self._tokens.pop(request.token, None)
        
        # Add to history
        self._history.append(request.to_dict())
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]
        
        if persist:
            self._persist_pending()
            self._persist_history()
        
        # Notify callbacks
        self._notify_resolved(request)
        
        logger.info(f"[ApprovalQueue] Resolved request {request.id}: {request.status.value}")
    
    def _persist_pending(self):
        """Save pending requests to disk."""
        try:
            filepath = self.approvals_dir / self.PENDING_FILE
            data = {rid: r.to_dict() for rid, r in self._pending.items()}
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[ApprovalQueue] Failed to persist pending: {e}")
    
    def _load_pending(self):
        """Load pending requests from disk."""
        try:
            filepath = self.approvals_dir / self.PENDING_FILE
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for rid, rdata in data.items():
                    request = ApprovalRequest.from_dict(rdata)
                    self._pending[rid] = request
                    self._tokens[request.token] = rid
        except Exception as e:
            logger.error(f"[ApprovalQueue] Failed to load pending: {e}")
    
    def _persist_history(self):
        """Save history to disk."""
        try:
            filepath = self.approvals_dir / self.HISTORY_FILE
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2)
        except Exception as e:
            logger.error(f"[ApprovalQueue] Failed to persist history: {e}")
    
    def _load_history(self):
        """Load history from disk."""
        try:
            filepath = self.approvals_dir / self.HISTORY_FILE
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
        except Exception as e:
            logger.error(f"[ApprovalQueue] Failed to load history: {e}")


# ============================================================================
# Singleton
# ============================================================================

_queue_instance: Optional[ApprovalQueue] = None
_queue_lock = threading.Lock()


def get_approval_queue() -> ApprovalQueue:
    """Get singleton ApprovalQueue instance."""
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = ApprovalQueue()
    return _queue_instance
