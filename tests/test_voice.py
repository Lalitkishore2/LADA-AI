"""
LADA v9.0 - Voice System Tests
Tests for VoiceCommandProcessor
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock modules BEFORE importing VoiceCommandProcessor
# This ensures that when VoiceCommandProcessor imports them in __init__, it gets the mocks
mock_system_control = MagicMock()
sys.modules["modules.system_control"] = mock_system_control

mock_ai_router = MagicMock()
sys.modules["lada_ai_router"] = mock_ai_router

mock_agent_actions = MagicMock()
sys.modules["modules.agent_actions"] = mock_agent_actions

from modules.voice_nlu import VoiceCommandProcessor

class TestVoiceCommandProcessor:
    """Test VoiceCommandProcessor functionality"""
    
    @pytest.fixture
    def voice_processor(self):
        # Reset mocks
        mock_system_control.reset_mock()
        mock_ai_router.reset_mock()
        mock_agent_actions.reset_mock()
        
        # Create processor
        processor = VoiceCommandProcessor()
        return processor

    def test_initialization(self, voice_processor):
        """Test initialization of VoiceCommandProcessor"""
        assert voice_processor is not None
        assert voice_processor.system is not None
        assert voice_processor.ai_router is not None
        assert voice_processor.agent is not None
        assert hasattr(voice_processor, "apps")
        assert hasattr(voice_processor, "websites")

    def test_split_compound(self, voice_processor):
        """Test splitting compound commands"""
        command = "open chrome and then set volume to 50"
        parts = voice_processor._split_compound(command)
        assert len(parts) == 2
        assert "open chrome" in parts
        assert "set volume to 50" in parts

        command_single = "open chrome"
        parts_single = voice_processor._split_compound(command_single)
        assert len(parts_single) == 1
        assert parts_single[0] == "open chrome"

    def test_process_empty_command(self, voice_processor):
        """Test processing empty command"""
        handled, response = voice_processor.process("")
        assert not handled
        assert response == ""

    @patch.object(VoiceCommandProcessor, "_process_single")
    def test_process_compound_command(self, mock_process_single, voice_processor):
        """Test processing compound command calls _process_single multiple times"""
        mock_process_single.side_effect = [(True, "Opened Chrome"), (True, "Volume set")]
        
        command = "open chrome and then set volume to 50"
        handled, response = voice_processor.process(command)
        
        assert handled
        assert mock_process_single.call_count == 2
        assert "Opened Chrome" in response
        assert "Volume set" in response

    def test_analyze_with_ai_action(self, voice_processor):
        """Test AI analysis returning an action"""
        # Setup the mock for the router instance
        # voice_processor.ai_router is an instance of the mock class
        voice_processor.ai_router.query.return_value = "ACTION: set_volume | 50"
        
        handled, response = voice_processor._analyze_with_ai("set volume to 50")
        
        assert handled
        assert "Volume set to 50%" in response
        voice_processor.system.set_volume.assert_called_with(50)

    def test_analyze_with_ai_answer(self, voice_processor):
        """Test AI analysis returning an answer"""
        voice_processor.ai_router.query.return_value = "ACTION: answer | The sky is blue"
        
        handled, response = voice_processor._analyze_with_ai("what color is the sky")
        
        assert handled
        assert "The sky is blue" in response

    def test_analyze_with_ai_open_app(self, voice_processor):
        """Test AI analysis opening an app"""
        voice_processor.ai_router.query.return_value = "ACTION: open_app | notepad"
        
        with patch("subprocess.Popen") as mock_popen:
            handled, response = voice_processor._analyze_with_ai("open notepad")
            
            assert handled
            assert "Opening notepad" in response
            mock_popen.assert_called()

    def test_analyze_with_ai_failure(self, voice_processor):
        """Test AI analysis failure handling"""
        voice_processor.ai_router.query.return_value = None
        
        handled, response = voice_processor._analyze_with_ai("unknown command")
        
        assert not handled
        assert response == ""

    def test_process_fallback_to_ai(self, voice_processor):
        """Test fallback to AI when pattern matching fails"""
        # Mock _process_single to return False
        with patch.object(VoiceCommandProcessor, "_process_single", return_value=(False, "")):
            # Mock AI response
            voice_processor.ai_router.query.return_value = "ACTION: answer | I can help with that"
            
            handled, response = voice_processor.process("complex command")
            
            assert handled
            assert "I can help with that" in response
