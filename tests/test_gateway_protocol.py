"""
Tests for LADA Gateway Protocol v1.0

Tests cover:
- Protocol schema validation
- Connect handshake (version, role, scopes)
- Frame validation
- Idempotency enforcement
- Error handling
"""

import pytest
import json
from unittest.mock import MagicMock

from modules.gateway_protocol.schema import (
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_MAJOR,
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
)


class TestProtocolSchema:
    """Tests for protocol schema definitions."""
    
    def test_protocol_version_format(self):
        """Protocol version should be in major.minor format."""
        assert "." in PROTOCOL_VERSION
        parts = PROTOCOL_VERSION.split(".")
        assert len(parts) == 2
        assert int(parts[0]) == PROTOCOL_VERSION_MAJOR
    
    def test_role_enum_values(self):
        """Role enum should have operator and node."""
        assert Role.OPERATOR.value == "operator"
        assert Role.NODE.value == "node"
    
    def test_scope_enum_values(self):
        """Scope enum should have expected values."""
        assert Scope.CHAT.value == "chat"
        assert Scope.APPROVE.value == "approve"
        assert Scope.ADMIN.value == "admin"
    
    def test_operator_has_more_scopes_than_node(self):
        """Operator role should have more scopes than node role."""
        operator_scopes = ROLE_SCOPES[Role.OPERATOR]
        node_scopes = ROLE_SCOPES[Role.NODE]
        assert len(operator_scopes) > len(node_scopes)
        assert Scope.APPROVE in operator_scopes
        assert Scope.APPROVE not in node_scopes
    
    def test_version_compatibility_exact_match(self):
        """Exact version match should be compatible."""
        assert check_version_compatible(PROTOCOL_VERSION)
    
    def test_version_compatibility_same_major(self):
        """Same major version should be compatible."""
        assert check_version_compatible(f"{PROTOCOL_VERSION_MAJOR}.99")
    
    def test_version_compatibility_different_major(self):
        """Different major version should be incompatible."""
        assert not check_version_compatible(f"{PROTOCOL_VERSION_MAJOR + 1}.0")
    
    def test_version_compatibility_invalid_format(self):
        """Invalid version format should be incompatible."""
        assert not check_version_compatible("invalid")
        assert not check_version_compatible("")


class TestConnectRequest:
    """Tests for connect request parsing and validation."""
    
    def test_from_dict_valid_operator(self):
        """Valid operator connect request should parse correctly."""
        data = {
            "type": "connect",
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
            "requested_scopes": ["chat", "approve"],
            "client_id": "test_client",
        }
        request = ConnectRequest.from_dict(data)
        request.validate()
        
        assert request.protocol_version == PROTOCOL_VERSION
        assert request.role == Role.OPERATOR
        assert Scope.CHAT in request.requested_scopes
        assert Scope.APPROVE in request.requested_scopes
    
    def test_from_dict_valid_node(self):
        """Valid node connect request should parse correctly."""
        data = {
            "protocol_version": PROTOCOL_VERSION,
            "role": "node",
            "client_info": {"name": "test_node"},
        }
        request = ConnectRequest.from_dict(data)
        request.validate()
        
        assert request.role == Role.NODE
        assert request.client_info["name"] == "test_node"
    
    def test_invalid_role_raises_error(self):
        """Invalid role should raise RoleNotAllowedError."""
        data = {
            "protocol_version": PROTOCOL_VERSION,
            "role": "invalid_role",
        }
        request = ConnectRequest.from_dict(data)
        with pytest.raises(RoleNotAllowedError):
            request.validate()
    
    def test_invalid_scope_raises_error(self):
        """Invalid scope should raise InvalidFrameError."""
        data = {
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
            "requested_scopes": ["invalid_scope"],
        }
        request = ConnectRequest.from_dict(data)
        with pytest.raises(InvalidFrameError):
            request.validate()
    
    def test_missing_version_raises_error(self):
        """Missing protocol_version should raise InvalidFrameError."""
        data = {
            "role": "operator",
        }
        request = ConnectRequest.from_dict(data)
        with pytest.raises(InvalidFrameError):
            request.validate()
    
    def test_to_dict_round_trip(self):
        """to_dict and from_dict should be reversible."""
        original = ConnectRequest(
            protocol_version=PROTOCOL_VERSION,
            role=Role.OPERATOR,
            requested_scopes=[Scope.CHAT, Scope.SYSTEM],
            client_id="test_123",
        )
        data = original.to_dict()
        restored = ConnectRequest.from_dict(data)
        
        assert restored.protocol_version == original.protocol_version
        assert restored.role == original.role
        assert restored.client_id == original.client_id


class TestConnectResponse:
    """Tests for connect response creation."""
    
    def test_success_response(self):
        """Success response should have correct structure."""
        response = ConnectResponse(
            success=True,
            session_id="session_123",
            granted_scopes=[Scope.CHAT, Scope.SYSTEM],
        )
        data = response.to_dict()
        
        assert data["type"] == "connected"
        assert data["success"] is True
        assert data["session_id"] == "session_123"
        assert "chat" in data["granted_scopes"]
    
    def test_error_response(self):
        """Error response should include error details."""
        error = VersionMismatchError("0.9", PROTOCOL_VERSION)
        response = ConnectResponse(
            success=False,
            error=error,
        )
        data = response.to_dict()
        
        assert data["success"] is False
        assert "error" in data
        assert data["error"]["code"] == "VERSION_MISMATCH"


class TestProtocolMessage:
    """Tests for protocol message parsing and validation."""
    
    def test_request_message_valid(self):
        """Valid request message should parse correctly."""
        data = {
            "type": "request",
            "operation": "chat.send",
            "payload": {"message": "hello"},
        }
        msg = ProtocolMessage.from_dict(data)
        msg.validate()
        
        assert msg.message_type == MessageType.REQUEST
        assert msg.operation == "chat.send"
    
    def test_request_without_operation_raises_error(self):
        """Request message without operation should fail validation."""
        data = {
            "type": "request",
            "payload": {},
        }
        msg = ProtocolMessage.from_dict(data)
        with pytest.raises(InvalidFrameError):
            msg.validate()
    
    def test_event_message_valid(self):
        """Event message without operation should be valid."""
        data = {
            "type": "event",
            "payload": {"status": "completed"},
        }
        msg = ProtocolMessage.from_dict(data)
        msg.validate()  # Should not raise
    
    def test_idempotency_key_preserved(self):
        """Idempotency key should be preserved in parsing."""
        data = {
            "type": "request",
            "operation": "tasks.create",
            "idempotency_key": "unique_key_123",
        }
        msg = ProtocolMessage.from_dict(data)
        
        assert msg.idempotency_key == "unique_key_123"


class TestScopeChecks:
    """Tests for scope and authorization checks."""
    
    def test_get_granted_scopes_operator(self):
        """Operator should get all requested scopes they're allowed."""
        granted = get_granted_scopes(Role.OPERATOR, [Scope.CHAT, Scope.APPROVE])
        assert Scope.CHAT in granted
        assert Scope.APPROVE in granted
    
    def test_get_granted_scopes_node_limited(self):
        """Node should not get scopes they're not allowed."""
        granted = get_granted_scopes(Role.NODE, [Scope.CHAT, Scope.APPROVE])
        assert Scope.CHAT in granted
        assert Scope.APPROVE not in granted
    
    def test_get_granted_scopes_empty_request(self):
        """Empty request should grant all role-allowed scopes."""
        granted = get_granted_scopes(Role.OPERATOR, [])
        assert len(granted) == len(ROLE_SCOPES[Role.OPERATOR])
    
    def test_scope_for_operation(self):
        """Operations should map to correct scopes."""
        assert scope_for_operation("chat.send") == Scope.CHAT
        assert scope_for_operation("approvals.decide") == Scope.APPROVE
        assert scope_for_operation("unknown") is None
    
    def test_can_perform_operation(self):
        """Operation authorization should check scopes correctly."""
        scopes = [Scope.CHAT, Scope.SYSTEM]
        assert can_perform_operation(scopes, "chat.send")
        assert can_perform_operation(scopes, "system.command")
        assert not can_perform_operation(scopes, "approvals.decide")


class TestIdempotencyCache:
    """Tests for idempotency key caching."""
    
    def test_new_key_not_duplicate(self):
        """New key should not be detected as duplicate."""
        cache = IdempotencyCache()
        is_dup, cached = cache.check_and_set("key_1")
        
        assert not is_dup
        assert cached is None
    
    def test_same_key_is_duplicate(self):
        """Same key should be detected as duplicate."""
        cache = IdempotencyCache()
        cache.check_and_set("key_1", {"response": "first"})
        is_dup, cached = cache.check_and_set("key_1")
        
        assert is_dup
        assert cached == {"response": "first"}
    
    def test_different_keys_not_duplicate(self):
        """Different keys should not conflict."""
        cache = IdempotencyCache()
        cache.check_and_set("key_1")
        is_dup, _ = cache.check_and_set("key_2")
        
        assert not is_dup
    
    def test_max_size_eviction(self):
        """Cache should evict oldest entries when over max size."""
        cache = IdempotencyCache(max_size=3)
        cache.check_and_set("key_1")
        cache.check_and_set("key_2")
        cache.check_and_set("key_3")
        cache.check_and_set("key_4")  # Should evict key_1
        
        assert len(cache) == 3
        # key_1 should be evicted
        is_dup, _ = cache.check_and_set("key_1")
        assert not is_dup


class TestProtocolValidator:
    """Tests for the protocol validator."""
    
    def test_validate_connect_success(self):
        """Valid connect request should succeed."""
        validator = ProtocolValidator()
        data = {
            "type": "connect",
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
        }
        response, session = validator.validate_connect(data)
        
        assert response.success
        assert session is not None
        assert session.role == Role.OPERATOR
    
    def test_validate_connect_version_mismatch(self):
        """Connect with wrong version should fail."""
        validator = ProtocolValidator()
        data = {
            "type": "connect",
            "protocol_version": "99.0",
            "role": "operator",
        }
        response, session = validator.validate_connect(data)
        
        assert not response.success
        assert session is None
        assert response.error.code == "VERSION_MISMATCH"
    
    def test_validate_frame_authorized(self):
        """Authorized operation should pass validation."""
        validator = ProtocolValidator(require_idempotency=False)
        _, session = validator.validate_connect({
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
        })
        
        result = validator.validate_frame({
            "type": "request",
            "operation": "chat.send",
            "payload": {},
        }, session)
        
        assert result.valid
    
    def test_validate_frame_unauthorized(self):
        """Unauthorized operation should fail validation."""
        validator = ProtocolValidator(require_idempotency=False)
        _, session = validator.validate_connect({
            "protocol_version": PROTOCOL_VERSION,
            "role": "node",  # Node can't approve
        })
        
        result = validator.validate_frame({
            "type": "request",
            "operation": "approvals.decide",
            "payload": {},
        }, session)
        
        assert not result.valid
        assert result.error.code == "SCOPE_NOT_ALLOWED"
    
    def test_validate_frame_missing_idempotency(self):
        """Side-effect operation without idempotency key should fail when required."""
        validator = ProtocolValidator(require_idempotency=True)
        _, session = validator.validate_connect({
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
        })
        
        result = validator.validate_frame({
            "type": "request",
            "operation": "tasks.create",  # Side-effect operation
            "payload": {},
        }, session)
        
        assert not result.valid
        assert result.error.code == "IDEMPOTENCY_ERROR"
    
    def test_validate_frame_with_idempotency(self):
        """Side-effect operation with idempotency key should pass."""
        validator = ProtocolValidator(require_idempotency=True)
        _, session = validator.validate_connect({
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
        })
        
        result = validator.validate_frame({
            "type": "request",
            "operation": "tasks.create",
            "payload": {},
            "idempotency_key": "unique_123",
        }, session)
        
        assert result.valid
        assert not result.is_duplicate
    
    def test_validate_frame_duplicate_idempotency(self):
        """Duplicate idempotency key should be detected."""
        validator = ProtocolValidator(require_idempotency=True)
        _, session = validator.validate_connect({
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
        })
        
        # First request
        result1 = validator.validate_frame({
            "type": "request",
            "operation": "tasks.create",
            "payload": {},
            "idempotency_key": "dup_key",
        }, session)
        
        # Second request with same key
        result2 = validator.validate_frame({
            "type": "request",
            "operation": "tasks.create",
            "payload": {},
            "idempotency_key": "dup_key",
        }, session)
        
        assert result1.valid and not result1.is_duplicate
        assert result2.valid and result2.is_duplicate
    
    def test_session_lifecycle(self):
        """Sessions should be tracked and removable."""
        validator = ProtocolValidator()
        
        _, session = validator.validate_connect({
            "protocol_version": PROTOCOL_VERSION,
            "role": "operator",
        })
        
        assert validator.session_count() == 1
        assert validator.get_session(session.session_id) is not None
        
        validator.remove_session(session.session_id)
        
        assert validator.session_count() == 0
        assert validator.get_session(session.session_id) is None


class TestProtocolErrors:
    """Tests for protocol error handling."""
    
    def test_version_mismatch_error_details(self):
        """VersionMismatchError should include version details."""
        error = VersionMismatchError("0.9", "1.0")
        data = error.to_dict()
        
        assert data["code"] == "VERSION_MISMATCH"
        assert "0.9" in data["message"]
        assert data["details"]["client_version"] == "0.9"
        assert data["details"]["server_version"] == "1.0"
    
    def test_role_not_allowed_error(self):
        """RoleNotAllowedError should list allowed roles."""
        error = RoleNotAllowedError("admin")
        data = error.to_dict()
        
        assert data["code"] == "ROLE_NOT_ALLOWED"
        assert "operator" in data["details"]["allowed_roles"]
        assert "node" in data["details"]["allowed_roles"]
    
    def test_scope_not_allowed_error(self):
        """ScopeNotAllowedError should include operation context."""
        error = ScopeNotAllowedError("approve", "node", "approvals.decide")
        data = error.to_dict()
        
        assert data["code"] == "SCOPE_NOT_ALLOWED"
        assert data["details"]["scope"] == "approve"
        assert data["details"]["role"] == "node"
        assert data["details"]["operation"] == "approvals.decide"
    
    def test_idempotency_error(self):
        """IdempotencyError should include key info."""
        error = IdempotencyError("key_123", "Duplicate request")
        data = error.to_dict()
        
        assert data["code"] == "IDEMPOTENCY_ERROR"
        assert data["details"]["idempotency_key"] == "key_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
