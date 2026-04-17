"""
LADA Gateway Protocol - Typed protocol contract.

This package provides:
- Protocol versioning and handshake
- Role-based connect with operator/node model
- Scoped permissions
- Frame validation
- Idempotency enforcement
"""

from modules.gateway_protocol.schema import (
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_MAJOR,
    PROTOCOL_VERSION_MINOR,
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
    ROLE_SCOPES,
    SCOPE_OPERATIONS,
    check_version_compatible,
    get_granted_scopes,
    scope_for_operation,
    can_perform_operation,
)

from modules.gateway_protocol.validator import (
    SessionState,
    IdempotencyCache,
    ValidationResult,
    ProtocolValidator,
    SIDE_EFFECT_OPERATIONS,
    get_validator,
    validate_handshake,
    validate_message,
)

__all__ = [
    # Schema constants
    "PROTOCOL_VERSION",
    "PROTOCOL_VERSION_MAJOR",
    "PROTOCOL_VERSION_MINOR",
    "ROLE_SCOPES",
    "SCOPE_OPERATIONS",
    "SIDE_EFFECT_OPERATIONS",
    # Enums
    "Role",
    "Scope",
    "MessageType",
    # Errors
    "ProtocolError",
    "VersionMismatchError",
    "RoleNotAllowedError",
    "ScopeNotAllowedError",
    "InvalidFrameError",
    "IdempotencyError",
    # Data classes
    "ConnectRequest",
    "ConnectResponse",
    "ProtocolMessage",
    "SessionState",
    "ValidationResult",
    # Classes
    "IdempotencyCache",
    "ProtocolValidator",
    # Functions
    "check_version_compatible",
    "get_granted_scopes",
    "scope_for_operation",
    "can_perform_operation",
    "get_validator",
    "validate_handshake",
    "validate_message",
]
