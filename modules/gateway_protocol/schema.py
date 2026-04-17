"""
LADA Gateway Protocol v1.0 Schema

Defines the typed protocol contract for WebSocket communication:
- Protocol version and compatibility
- Connect roles: operator and node
- Permission scopes
- Message frame structure
- Handshake sequence

Built for LADA gateway/protocol patterns.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# Protocol version
PROTOCOL_VERSION = "1.0"
PROTOCOL_VERSION_MAJOR = 1
PROTOCOL_VERSION_MINOR = 0


class Role(str, Enum):
    """
    Connection roles in the LADA gateway.
    
    OPERATOR: Human user or primary control interface (desktop, web, CLI).
              Has elevated permissions for configuration and approval.
              
    NODE: Automated sidecar, messaging connector, or remote agent node.
          Limited permissions, cannot approve dangerous actions.
    """
    OPERATOR = "operator"
    NODE = "node"


class Scope(str, Enum):
    """
    Permission scopes granted to connections.
    
    Scopes control what operations a connection can perform.
    """
    # Core operations
    CHAT = "chat"                    # Send/receive chat messages
    SYSTEM = "system"                # System commands (volume, brightness, etc.)
    TASKS = "tasks"                  # Create/manage background tasks
    
    # Elevated operations (operator-only by default)
    APPROVE = "approve"              # Approve dangerous actions
    CONFIG = "config"                # Modify configuration
    PLUGINS = "plugins"              # Install/manage plugins
    AGENTS = "agents"                # Spawn/manage subagents
    
    # Admin operations
    ADMIN = "admin"                  # Full administrative access
    AUDIT = "audit"                  # View audit logs


# Default scopes by role
ROLE_SCOPES: Dict[Role, Set[Scope]] = {
    Role.OPERATOR: {
        Scope.CHAT,
        Scope.SYSTEM,
        Scope.TASKS,
        Scope.APPROVE,
        Scope.CONFIG,
        Scope.PLUGINS,
        Scope.AGENTS,
        Scope.AUDIT,
    },
    Role.NODE: {
        Scope.CHAT,
        Scope.SYSTEM,
        Scope.TASKS,
    },
}

# Operations that require specific scopes
SCOPE_OPERATIONS: Dict[str, Scope] = {
    # Chat operations
    "chat.send": Scope.CHAT,
    "chat.stream": Scope.CHAT,
    "conversations.list": Scope.CHAT,
    "conversations.get": Scope.CHAT,
    
    # System operations
    "system.command": Scope.SYSTEM,
    "system.status": Scope.SYSTEM,
    "comet.execute": Scope.SYSTEM,
    
    # Task operations
    "tasks.create": Scope.TASKS,
    "tasks.cancel": Scope.TASKS,
    "tasks.list": Scope.TASKS,
    "tasks.get": Scope.TASKS,
    "flows.create": Scope.TASKS,
    "flows.cancel": Scope.TASKS,
    
    # Approval operations
    "approvals.decide": Scope.APPROVE,
    "approvals.list": Scope.APPROVE,
    
    # Config operations
    "config.get": Scope.CONFIG,
    "config.set": Scope.CONFIG,
    
    # Plugin operations
    "plugins.install": Scope.PLUGINS,
    "plugins.uninstall": Scope.PLUGINS,
    "plugins.list": Scope.PLUGINS,
    
    # Agent operations
    "agents.spawn": Scope.AGENTS,
    "agents.terminate": Scope.AGENTS,
    "agents.list": Scope.AGENTS,
    
    # Admin operations
    "admin.shutdown": Scope.ADMIN,
    "admin.restart": Scope.ADMIN,
    
    # Audit operations
    "audit.query": Scope.AUDIT,
    "audit.export": Scope.AUDIT,
}

# Message types
class MessageType(str, Enum):
    """Protocol message types."""
    # Connection lifecycle
    CONNECT = "connect"
    CONNECTED = "connected"
    DISCONNECT = "disconnect"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    
    # Request/response
    REQUEST = "request"
    RESPONSE = "response"
    
    # Events
    EVENT = "event"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


# Protocol errors
class ProtocolError(Exception):
    """Base protocol error."""
    
    def __init__(self, code: str, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"{code}: {message}")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class VersionMismatchError(ProtocolError):
    """Protocol version mismatch."""
    
    def __init__(self, client_version: str, server_version: str):
        super().__init__(
            code="VERSION_MISMATCH",
            message=f"Protocol version mismatch: client={client_version}, server={server_version}",
            details={
                "client_version": client_version,
                "server_version": server_version,
                "supported_versions": [PROTOCOL_VERSION],
            },
        )


class RoleNotAllowedError(ProtocolError):
    """Role not allowed for this connection."""
    
    def __init__(self, role: str, reason: str = ""):
        super().__init__(
            code="ROLE_NOT_ALLOWED",
            message=f"Role '{role}' not allowed: {reason}" if reason else f"Role '{role}' not allowed",
            details={"role": role, "allowed_roles": [r.value for r in Role]},
        )


class ScopeNotAllowedError(ProtocolError):
    """Scope not allowed for this role/operation."""
    
    def __init__(self, scope: str, role: str, operation: str = ""):
        msg = f"Scope '{scope}' not allowed for role '{role}'"
        if operation:
            msg += f" (operation: {operation})"
        super().__init__(
            code="SCOPE_NOT_ALLOWED",
            message=msg,
            details={"scope": scope, "role": role, "operation": operation},
        )


class InvalidFrameError(ProtocolError):
    """Invalid message frame."""
    
    def __init__(self, reason: str, frame_preview: str = ""):
        super().__init__(
            code="INVALID_FRAME",
            message=f"Invalid frame: {reason}",
            details={"reason": reason, "frame_preview": frame_preview[:200] if frame_preview else ""},
        )


class IdempotencyError(ProtocolError):
    """Idempotency key error (duplicate or missing)."""
    
    def __init__(self, key: Optional[str], reason: str):
        super().__init__(
            code="IDEMPOTENCY_ERROR",
            message=reason,
            details={"idempotency_key": key},
        )


def _new_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now_ms() -> int:
    """Current timestamp in milliseconds."""
    return int(time.time() * 1000)


@dataclass
class ConnectRequest:
    """
    Connect handshake request from client.
    
    Sent as the first message after WebSocket connection established.
    """
    protocol_version: str
    role: Role
    requested_scopes: List[Scope] = field(default_factory=list)
    client_id: str = field(default_factory=lambda: _new_id("client"))
    client_info: Dict[str, Any] = field(default_factory=dict)
    auth_token: Optional[str] = None
    
    def validate(self) -> None:
        """Validate connect request fields."""
        if not self.protocol_version:
            raise InvalidFrameError("protocol_version is required")
        
        if not isinstance(self.role, Role):
            try:
                self.role = Role(self.role)
            except ValueError:
                raise RoleNotAllowedError(str(self.role))
        
        # Validate requested scopes are valid enums
        validated_scopes = []
        for scope in self.requested_scopes:
            if not isinstance(scope, Scope):
                try:
                    validated_scopes.append(Scope(scope))
                except ValueError:
                    raise InvalidFrameError(f"Invalid scope: {scope}")
            else:
                validated_scopes.append(scope)
        self.requested_scopes = validated_scopes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": MessageType.CONNECT.value,
            "protocol_version": self.protocol_version,
            "role": self.role.value if isinstance(self.role, Role) else self.role,
            "requested_scopes": [s.value if isinstance(s, Scope) else s for s in self.requested_scopes],
            "client_id": self.client_id,
            "client_info": self.client_info,
            "auth_token": self.auth_token,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectRequest":
        role_val = data.get("role", "operator")
        try:
            role = Role(role_val)
        except ValueError:
            role = role_val  # Will be caught by validate()
        
        scopes_val = data.get("requested_scopes", [])
        scopes = []
        for s in scopes_val:
            try:
                scopes.append(Scope(s))
            except ValueError:
                scopes.append(s)  # Will be caught by validate()
        
        return cls(
            protocol_version=str(data.get("protocol_version", "")),
            role=role,
            requested_scopes=scopes,
            client_id=str(data.get("client_id") or _new_id("client")),
            client_info=dict(data.get("client_info") or {}),
            auth_token=data.get("auth_token"),
        )


@dataclass
class ConnectResponse:
    """
    Connect handshake response from server.
    
    Indicates successful connection and granted scopes.
    """
    success: bool
    session_id: str = field(default_factory=lambda: _new_id("session"))
    protocol_version: str = PROTOCOL_VERSION
    granted_scopes: List[Scope] = field(default_factory=list)
    server_info: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ProtocolError] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": MessageType.CONNECTED.value,
            "success": self.success,
            "session_id": self.session_id,
            "protocol_version": self.protocol_version,
            "granted_scopes": [s.value if isinstance(s, Scope) else s for s in self.granted_scopes],
            "server_info": self.server_info,
        }
        if self.error:
            result["error"] = self.error.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectResponse":
        scopes = []
        for s in data.get("granted_scopes", []):
            try:
                scopes.append(Scope(s))
            except ValueError:
                pass  # Ignore invalid scopes in response
        
        return cls(
            success=bool(data.get("success", False)),
            session_id=str(data.get("session_id", "")),
            protocol_version=str(data.get("protocol_version", PROTOCOL_VERSION)),
            granted_scopes=scopes,
            server_info=dict(data.get("server_info") or {}),
        )


@dataclass
class ProtocolMessage:
    """
    Generic protocol message envelope.
    
    All messages after handshake use this format.
    """
    message_id: str = field(default_factory=lambda: _new_id("msg"))
    message_type: MessageType = MessageType.REQUEST
    operation: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = field(default_factory=_now_ms)
    request_id: Optional[str] = None  # For correlating responses
    idempotency_key: Optional[str] = None  # For side-effect dedup
    session_id: Optional[str] = None
    
    def validate(self) -> None:
        """Validate message fields."""
        if not self.message_id:
            raise InvalidFrameError("message_id is required")
        
        if not isinstance(self.message_type, MessageType):
            try:
                self.message_type = MessageType(self.message_type)
            except ValueError:
                raise InvalidFrameError(f"Invalid message_type: {self.message_type}")
        
        # Requests require operation
        if self.message_type == MessageType.REQUEST and not self.operation:
            raise InvalidFrameError("operation is required for request messages")
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "message_id": self.message_id,
            "type": self.message_type.value if isinstance(self.message_type, MessageType) else self.message_type,
            "operation": self.operation,
            "payload": self.payload,
            "timestamp_ms": self.timestamp_ms,
        }
        if self.request_id:
            result["request_id"] = self.request_id
        if self.idempotency_key:
            result["idempotency_key"] = self.idempotency_key
        if self.session_id:
            result["session_id"] = self.session_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolMessage":
        msg_type = data.get("type", "request")
        try:
            msg_type = MessageType(msg_type)
        except ValueError:
            msg_type = msg_type  # Will be caught by validate()
        
        return cls(
            message_id=str(data.get("message_id") or _new_id("msg")),
            message_type=msg_type,
            operation=str(data.get("operation", "")),
            payload=dict(data.get("payload") or data.get("data") or {}),
            timestamp_ms=int(data.get("timestamp_ms", _now_ms())),
            request_id=data.get("request_id"),
            idempotency_key=data.get("idempotency_key"),
            session_id=data.get("session_id"),
        )


def check_version_compatible(client_version: str) -> bool:
    """
    Check if client protocol version is compatible with server.
    
    Currently requires exact major version match.
    """
    try:
        parts = client_version.split(".")
        client_major = int(parts[0])
        return client_major == PROTOCOL_VERSION_MAJOR
    except (ValueError, IndexError):
        return False


def get_granted_scopes(role: Role, requested_scopes: List[Scope]) -> List[Scope]:
    """
    Determine which scopes to grant based on role and request.
    
    Returns intersection of role-allowed scopes and requested scopes.
    If no scopes requested, returns all role-allowed scopes.
    """
    allowed = ROLE_SCOPES.get(role, set())
    
    if not requested_scopes:
        return list(allowed)
    
    return [s for s in requested_scopes if s in allowed]


def scope_for_operation(operation: str) -> Optional[Scope]:
    """Get the required scope for an operation."""
    return SCOPE_OPERATIONS.get(operation)


def can_perform_operation(granted_scopes: List[Scope], operation: str) -> bool:
    """Check if granted scopes allow an operation."""
    required = scope_for_operation(operation)
    if required is None:
        # Unknown operations require ADMIN scope
        return Scope.ADMIN in granted_scopes
    return required in granted_scopes
