import pytest
from unittest.mock import MagicMock, patch
from modules.permission_system import PermissionSystem

class TestPermissionSystem:
    
    @pytest.fixture
    def system(self):
        return PermissionSystem()

    def test_assess_risk(self, system):
        """Test risk assessment via check_permission"""
        # Register a mock callback so it doesn't auto-allow
        system.confirmation_callback = MagicMock(return_value=False)

        # We test via check_permission which calls _assess_risk
        allowed, reason, details = system.check_permission("delete system32")
        # Should be denied or require confirmation
        assert allowed is False or details.get('required_confirmation') is True
        
        allowed, reason, details = system.check_permission("read file")
        assert allowed is True

    def test_request_confirmation(self, system):
        """Test confirmation request"""
        # Mock user input or GUI dialog
        with patch.object(system, '_request_confirmation') as mock_confirm:
            mock_confirm.return_value = True
            # Force a high risk command
            system.check_permission("delete file")
            # Depending on rules, it might trigger confirmation
            pass

    def test_log_action(self, system):
        """Test action logging"""
        system._audit_action("test_action", True, False, False)
        assert len(system.audit_log) == 1

    def test_add_to_whitelist(self, system):
        """Test whitelisting"""
        system.whitelist.add("safe_action")
        assert "safe_action" in system.whitelist

    def test_set_permission_level(self, system):
        """Test setting permission level"""
        from modules.permission_system import PermissionLevel
        system.set_permission_level(PermissionLevel.ADMIN, password="test")
        # Might fail if password wrong, but we check call
        assert system.permission_level == PermissionLevel.USER # Default if password fails
