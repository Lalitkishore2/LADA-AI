"""
LADA Gateway Protocol Validator

Validates incoming WebSocket frames against the protocol schema.
Provides:
- Frame structure validation
- Message type validation
- Operation authorization (scope checking)
- Idempotency key management
"""

from __future__ import annotations

import json
import logging
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.gateway_protocol.schema import (
    PROTOCOL_VERSION,
    Role,
    Scope,
    MessageType,
    ProtocolError,
    VersionMismatchError,
    RoleNotAllowedError,
    ScopeNotAllowedError,
    InvalidFrameError,
    IdempotencyError,
    ConnectRequest,
    ConnectResponse,
    ProtocolMessage,
    check_version_compatible,
    get_granted_scopes,
    scope_for_operation,
    can_perform_operation,
)

logger = logging.getLogger(__name__)

# Operations that have side effects and require idempotency keys
SIDE_EFFECT_OPERATIONS: Set[str] = {
    # Task operations
    "tasks.create",
    "tasks.cancel",
    "tasks.retry",
    "flows.create",
    "flows.cancel",
    
    # System commands
    "system.command",
    "comet.execute",
    
    # Plugin operations
    "plugins.install",
    "plugins.uninstall",
    
    # Agent operations
    "agents.spawn",
    "agents.terminate",
    
    # Config operations
    "config.set",
    
    # Approval operations
    "approvals.decide",
    
    # Admin operations
    "admin.shutdown",
    "admin.restart",
}


@dataclass
class SessionState:
    """
    State for an authenticated session.
    """
    session_id: str
    role: Role
    granted_scopes: Set[Scope]
    client_id: str
    connected_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_activity_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    client_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class IdempotencyCache:
    """
    Thread-safe cache for idempotency key deduplication.
    
    Stores processed idempotency keys with TTL to prevent duplicate
    processing of side-effect operations.
    """
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, Tuple[int, Any]] = OrderedDict()
        self._max_size = max_size
        self._ttl_ms = ttl_seconds * 1000
        self._lock = threading.RLock()
    
    def check_and_set(self, key: str, response: Any = None) -> Tuple[bool, Optional[Any]]:
        """
        Check if key exists (duplicate) and set if not.
        
        Returns:
            (is_duplicate, cached_response)
            - (False, None) if new key, now cached
            - (True, response) if duplicate, returns cached response
        """
        now = int(time.time() * 1000)
        
        with self._lock:
            self._cleanup_expired(now)
            
            if key in self._cache:
                _, cached_response = self._cache[key]
                # Move to end (LRU)
                self._cache.move_to_end(key)
                return (True, cached_response)
            
            # Add new key
            self._cache[key] = (now, response)
            
            # Evict oldest if over capacity
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
            
            return (False, None)
    
    def update_response(self, key: str, response: Any) -> None:
        """Update cached response for a key."""
        with self._lock:
            if key in self._cache:
                timestamp, _ = self._cache[key]
                self._cache[key] = (timestamp, response)
    
    def _cleanup_expired(self, now: int) -> None:
        """Remove expired entries."""
        expired = []
        for key, (timestamp, _) in self._cache.items():
            if now - timestamp > self._ttl_ms:
                expired.append(key)
            else:
                # OrderedDict is ordered by insertion, so we can stop
                break
        
        for key in expired:
            del self._cache[key]
    
    def clear(self) -> None:
        """Clear all cached keys."""
        with self._lock:
            self._cache.clear()
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


@dataclass
class ValidationResult:
    """Result of frame validation."""
    valid: bool
    error: Optional[ProtocolError] = None
    message: Optional[ProtocolMessage] = None
    is_duplicate: bool = False
    cached_response: Optional[Any] = None


class ProtocolValidator:
    """
    Validates WebSocket frames against the LADA gateway protocol.
    
    Handles:
    - Connect handshake validation
    - Frame structure validation
    - Operation authorization
    - Idempotency enforcement
    """
    
    def __init__(
        self,
        require_idempotency: bool = True,
        idempotency_ttl: int = 3600,
        max_frame_size: int = 65536,
    ):
        self._sessions: Dict[str, SessionState] = {}
        self._sessions_lock = threading.RLock()
        self._idempotency_cache = IdempotencyCache(ttl_seconds=idempotency_ttl)
        self._require_idempotency = require_idempotency
        self._max_frame_size = max_frame_size
    
    def validate_connect(self, raw_data: Any) -> Tuple[ConnectResponse, Optional[SessionState]]:
        """
        Validate a connect handshake request.
        
        Returns:
            (response, session_state)
            - On success: (success response, new session state)
            - On failure: (error response, None)
        """
        # Parse raw data
        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as e:
                return (
                    ConnectResponse(
                        success=False,
                        error=InvalidFrameError(f"Invalid JSON: {e}"),
                    ),
                    None,
                )
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            return (
                ConnectResponse(
                    success=False,
                    error=InvalidFrameError("Expected JSON object"),
                ),
                None,
            )
        
        # Parse connect request
        try:
            request = ConnectRequest.from_dict(data)
            request.validate()
        except ProtocolError as e:
            return ConnectResponse(success=False, error=e), None
        except Exception as e:
            return (
                ConnectResponse(
                    success=False,
                    error=InvalidFrameError(str(e)),
                ),
                None,
            )
        
        # Check protocol version
        if not check_version_compatible(request.protocol_version):
            return (
                ConnectResponse(
                    success=False,
                    error=VersionMismatchError(request.protocol_version, PROTOCOL_VERSION),
                ),
                None,
            )
        
        # Determine granted scopes
        granted = get_granted_scopes(request.role, request.requested_scopes)
        
        # Create session
        from modules.gateway_protocol.schema import _new_id
        session_id = _new_id("session")
        
        session = SessionState(
            session_id=session_id,
            role=request.role,
            granted_scopes=set(granted),
            client_id=request.client_id,
            client_info=request.client_info,
        )
        
        # Store session
        with self._sessions_lock:
            self._sessions[session_id] = session
        
        response = ConnectResponse(
            success=True,
            session_id=session_id,
            granted_scopes=granted,
            server_info={
                "name": "LADA",
                "version": "9.0",
                "protocol_version": PROTOCOL_VERSION,
            },
        )
        
        logger.info(
            f"Session {session_id} connected: role={request.role.value}, "
            f"scopes={[s.value for s in granted]}"
        )
        
        return response, session
    
    def validate_frame(
        self,
        raw_data: Any,
        session: SessionState,
    ) -> ValidationResult:
        """
        Validate a protocol frame.
        
        Returns ValidationResult with:
        - valid=True, message=parsed if valid
        - valid=False, error=error if invalid
        - is_duplicate=True if idempotency key was seen before
        """
        # Size check
        if isinstance(raw_data, str) and len(raw_data) > self._max_frame_size:
            return ValidationResult(
                valid=False,
                error=InvalidFrameError(
                    f"Frame too large: {len(raw_data)} > {self._max_frame_size}"
                ),
            )
        
        # Parse JSON
        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    valid=False,
                    error=InvalidFrameError(f"Invalid JSON: {e}"),
                )
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            return ValidationResult(
                valid=False,
                error=InvalidFrameError("Expected JSON object"),
            )
        
        # Parse message
        try:
            message = ProtocolMessage.from_dict(data)
            message.validate()
        except ProtocolError as e:
            return ValidationResult(valid=False, error=e)
        except Exception as e:
            return ValidationResult(
                valid=False,
                error=InvalidFrameError(str(e)),
            )
        
        # Update session activity
        session.last_activity_ms = int(time.time() * 1000)
        
        # Skip authorization for non-request messages
        if message.message_type != MessageType.REQUEST:
            return ValidationResult(valid=True, message=message)
        
        # Check scope authorization
        if not can_perform_operation(list(session.granted_scopes), message.operation):
            required = scope_for_operation(message.operation)
            return ValidationResult(
                valid=False,
                error=ScopeNotAllowedError(
                    scope=required.value if required else "admin",
                    role=session.role.value,
                    operation=message.operation,
                ),
            )
        
        # Check idempotency for side-effect operations
        if message.operation in SIDE_EFFECT_OPERATIONS:
            if self._require_idempotency and not message.idempotency_key:
                return ValidationResult(
                    valid=False,
                    error=IdempotencyError(
                        key=None,
                        reason=f"idempotency_key required for operation: {message.operation}",
                    ),
                )
            
            if message.idempotency_key:
                # Check for duplicate
                is_dup, cached = self._idempotency_cache.check_and_set(
                    message.idempotency_key
                )
                if is_dup:
                    logger.debug(
                        f"Duplicate idempotency key: {message.idempotency_key}"
                    )
                    return ValidationResult(
                        valid=True,
                        message=message,
                        is_duplicate=True,
                        cached_response=cached,
                    )
        
        return ValidationResult(valid=True, message=message)
    
    def record_response(self, idempotency_key: str, response: Any) -> None:
        """Record response for idempotency key."""
        if idempotency_key:
            self._idempotency_cache.update_response(idempotency_key, response)
    
    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get session by ID."""
        with self._sessions_lock:
            return self._sessions.get(session_id)
    
    def remove_session(self, session_id: str) -> None:
        """Remove session on disconnect."""
        with self._sessions_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session {session_id} disconnected")
    
    def list_sessions(self) -> List[SessionState]:
        """List all active sessions."""
        with self._sessions_lock:
            return list(self._sessions.values())
    
    def session_count(self) -> int:
        """Get active session count."""
        with self._sessions_lock:
            return len(self._sessions)


# Singleton validator instance
_validator: Optional[ProtocolValidator] = None
_validator_lock = threading.Lock()


def get_validator() -> ProtocolValidator:
    """Get the singleton protocol validator."""
    global _validator
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                _validator = ProtocolValidator()
    return _validator


def validate_handshake(raw_data: Any) -> Tuple[ConnectResponse, Optional[SessionState]]:
    """Convenience function to validate connect handshake."""
    return get_validator().validate_connect(raw_data)


def validate_message(
    raw_data: Any,
    session: SessionState,
) -> ValidationResult:
    """Convenience function to validate a message frame."""
    return get_validator().validate_frame(raw_data, session)
