"""
Tests for MoltBot Robot Controller
"""

import pytest
from unittest.mock import MagicMock
import sys

# Mock serial before import
sys.modules['serial'] = MagicMock()
sys.modules['serial.tools'] = MagicMock()
sys.modules['serial.tools.list_ports'] = MagicMock()

from integrations.moltbot_controller import MoltBotController, MoltBotStatus, get_moltbot_controller


class TestMoltBotController:
    """Test MoltBot robot controller"""
    
    def test_controller_class_exists(self):
        """Test controller class exists"""
        assert MoltBotController is not None
    
    def test_controller_creation(self):
        """Test controller can be created"""
        controller = MoltBotController()
        assert controller is not None
    
    def test_has_connect_method(self):
        """Test controller has connect method"""
        controller = MoltBotController()
        assert hasattr(controller, 'connect')


class TestMoltBotStatus:
    """Test MoltBot status dataclass"""
    
    def test_status_class_exists(self):
        """Test status class exists"""
        assert MoltBotStatus is not None


class TestGetMoltBotController:
    """Test module-level factory"""
    
    def test_factory_returns_controller(self):
        """Test factory function returns controller"""
        controller = get_moltbot_controller()
        assert controller is not None
