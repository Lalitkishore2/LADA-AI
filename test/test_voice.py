"""
LADA v9.0 - Voice System Tests
Tests for VoiceCommandProcessor
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import importlib


@pytest.fixture
def voice_module():
    """Load voice_nlu with deterministic mocked dependencies."""
    mock_system_control = MagicMock()
    mock_ai_router = MagicMock()
    mock_agent_actions = MagicMock()

    # Ensure constructor calls return stable mock instances.
    mock_system_control.SystemController.return_value = MagicMock()
    mock_ai_router.HybridAIRouter.return_value = MagicMock()
    mock_agent_actions.AgentActions.return_value = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "modules.system_control": mock_system_control,
            "lada_ai_router": mock_ai_router,
            "modules.agent_actions": mock_agent_actions,
        },
        clear=False,
    ):
        sys.modules.pop("modules.voice_nlu", None)
        module = importlib.import_module("modules.voice_nlu")
        yield module

class TestVoiceCommandProcessor:
    """Test VoiceCommandProcessor functionality"""
    
    @pytest.fixture
    def voice_processor(self, voice_module):
        return voice_module.VoiceCommandProcessor()

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

    def test_process_compound_command(self, voice_module, voice_processor):
        """Test processing compound command calls _process_single multiple times"""
        with patch.object(voice_module.VoiceCommandProcessor, "_process_single") as mock_process_single:
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
        with patch.object(type(voice_processor), "_process_single", return_value=(False, "")):
            # Mock AI response
            voice_processor.ai_router.query.return_value = "ACTION: answer | I can help with that"
            
            handled, response = voice_processor.process("complex command")
            
            assert handled
            assert "I can help with that" in response

    def test_execute_ai_action_set_volume_without_system(self, voice_processor):
        """AI volume actions should return a clear handled response when system control is unavailable."""
        voice_processor.system = None

        handled, response = voice_processor._execute_ai_action("ACTION: set_volume | 50")

        assert handled
        assert "System control not available" in response

    def test_execute_ai_action_clamps_volume_and_brightness(self, voice_processor):
        """AI volume/brightness actions should clamp values to 0-100 before calling system control."""
        voice_processor.system = MagicMock()

        handled_volume, response_volume = voice_processor._execute_ai_action("ACTION: set_volume | 150")
        handled_brightness, response_brightness = voice_processor._execute_ai_action("ACTION: set_brightness | -10")

        assert handled_volume
        assert handled_brightness
        assert "Volume set to 100%" in response_volume
        assert "Brightness set to 0%" in response_brightness
        voice_processor.system.set_volume.assert_called_once_with(100)
        voice_processor.system.set_brightness.assert_called_once_with(0)

    def test_handle_volume_supports_laptop_volume_by_phrase(self, voice_processor):
        """Pattern handler should parse natural phrasing like 'set the laptop volume by 70%'."""
        voice_processor.system = MagicMock()
        voice_processor.system.set_volume.return_value = {"success": True, "volume": 70}

        handled, response = voice_processor._handle_volume("set the laptop volume by 70%")

        assert handled
        voice_processor.system.set_volume.assert_called_once_with(70)
        assert "70%" in response

    def test_handle_volume_unmute_does_not_hit_mute_branch(self, voice_processor):
        """'unmute' should set max volume instead of being treated as 'mute'."""
        voice_processor.system = MagicMock()
        voice_processor.system.set_volume.return_value = {"success": True}

        handled, response = voice_processor._handle_volume("unmute")

        assert handled
        voice_processor.system.set_volume.assert_called_once_with(100)
        assert "maximum" in response.lower()

    def test_execute_ai_action_set_volume_surfaces_system_failure(self, voice_processor):
        """AI action path should report system control failures rather than false success."""
        voice_processor.system = MagicMock()
        voice_processor.system.set_volume.return_value = {
            "success": False,
            "error": "pycaw not installed",
        }

        handled, response = voice_processor._execute_ai_action("ACTION: set_volume | 70")

        assert handled
        assert "couldn't set the volume" in response.lower()
        assert "pycaw not installed" in response
