"""
Tests for Alexa Integration
"""

import pytest
from unittest.mock import MagicMock
import sys

# Mock Flask before import
sys.modules['flask'] = MagicMock()
sys.modules['flask_ask_sdk'] = MagicMock()
sys.modules['ask_sdk_core'] = MagicMock()
sys.modules['ask_sdk_core.skill_builder'] = MagicMock()
sys.modules['ask_sdk_core.dispatch_components'] = MagicMock()
sys.modules['ask_sdk_core.utils'] = MagicMock()
sys.modules['ask_sdk_model'] = MagicMock()
sys.modules['ask_sdk_model.ui'] = MagicMock()

from integrations.alexa_server import AlexaSkillServer
from integrations.alexa_hybrid import AlexaHybridVoice, VoiceMode


class TestAlexaSkillServer:
    """Test Alexa skill server"""
    
    def test_server_class_exists(self):
        """Test server class exists"""
        assert AlexaSkillServer is not None
    
    def test_server_creation(self):
        """Test server can be created"""
        server = AlexaSkillServer()
        assert server is not None


class TestAlexaHybridVoice:
    """Test Alexa hybrid voice switching"""
    
    def test_hybrid_class_exists(self):
        """Test hybrid class exists"""
        assert AlexaHybridVoice is not None
    
    def test_voice_mode_enum(self):
        """Test VoiceMode enum values"""
        assert VoiceMode.AUTO.value == "auto"
        assert VoiceMode.ALEXA.value == "alexa"
        assert VoiceMode.LOCAL.value == "local"
    
    def test_hybrid_creation(self):
        """Test hybrid voice controller initializes"""
        hybrid = AlexaHybridVoice()
        assert hybrid is not None
