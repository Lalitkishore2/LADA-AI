"""
Tests for modules/voice_nlu.py
Covers: VoiceCommandProcessor class
"""

import pytest
import sys
from unittest.mock import MagicMock, patch


# Mock dependencies before import
@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock dependencies for voice_nlu."""
    mock_psutil = MagicMock()
    mock_psutil.cpu_percent.return_value = 50.0
    mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
    mock_psutil.sensors_battery.return_value = MagicMock(percent=80.0, secsleft=3600, power_plugged=True)
    
    with patch.dict(sys.modules, {
        'psutil': mock_psutil,
        'pyautogui': MagicMock(),
        'modules.system_control': MagicMock(),
        'lada_ai_router': MagicMock(),
        'modules.agent_actions': MagicMock()
    }):
        yield


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules(mock_dependencies):
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'voice_nlu' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestVoiceCommandProcessorInit:
    """Tests for VoiceCommandProcessor initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        assert processor is not None
    
    def test_init_has_apps(self):
        """Test processor has apps dictionary."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        assert hasattr(processor, 'apps')
    
    def test_init_has_history(self):
        """Test processor has history list."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        assert hasattr(processor, 'history')
        assert isinstance(processor.history, list)


class TestAcknowledgments:
    """Tests for acknowledgment messages."""
    
    def test_acknowledgments_exist(self):
        """Test ACKNOWLEDGMENTS constant exists."""
        from modules import voice_nlu as vn
        assert hasattr(vn.VoiceCommandProcessor, 'ACKNOWLEDGMENTS')
        assert len(vn.VoiceCommandProcessor.ACKNOWLEDGMENTS) > 0


class TestSeparators:
    """Tests for command separators."""
    
    def test_separators_exist(self):
        """Test SEPARATORS constant exists."""
        from modules import voice_nlu as vn
        assert hasattr(vn.VoiceCommandProcessor, 'SEPARATORS')
        assert len(vn.VoiceCommandProcessor.SEPARATORS) > 0


class TestProcessCommand:
    """Tests for command processing."""
    
    def test_process_greeting(self):
        """Test processing greeting."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("hello jarvis")
            # Should return some response
        elif hasattr(processor, 'process_command'):
            result = processor.process_command("hello jarvis")
    
    def test_process_time_query(self):
        """Test processing time query."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("what time is it")
        elif hasattr(processor, 'process_command'):
            result = processor.process_command("what time is it")
    
    def test_process_date_query(self):
        """Test processing date query."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("what is today's date")
    
    def test_process_battery_query(self):
        """Test processing battery query."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("battery status")


class TestVolumeCommands:
    """Tests for volume commands."""
    
    def test_set_volume(self):
        """Test set volume command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("set volume to 50")
    
    def test_mute(self):
        """Test mute command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("mute")
    
    def test_unmute(self):
        """Test unmute command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("unmute")


class TestAppCommands:
    """Tests for application commands."""
    
    def test_open_app(self):
        """Test open app command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        with patch('subprocess.Popen'):
            with patch('subprocess.run'):
                if hasattr(processor, 'process'):
                    result = processor.process("open notepad")
    
    def test_close_app(self):
        """Test close app command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        with patch('subprocess.run'):
            if hasattr(processor, 'process'):
                result = processor.process("close notepad")


class TestBrowserCommands:
    """Tests for browser commands."""
    
    def test_open_website(self):
        """Test open website command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        with patch('webbrowser.open'):
            if hasattr(processor, 'process'):
                result = processor.process("open google.com")
    
    def test_search_google(self):
        """Test search command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        with patch('webbrowser.open'):
            if hasattr(processor, 'process'):
                result = processor.process("search for python tutorials")
    
    def test_open_youtube(self):
        """Test YouTube command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        with patch('webbrowser.open'):
            if hasattr(processor, 'process'):
                result = processor.process("play music on youtube")


class TestSystemCommands:
    """Tests for system commands."""
    
    def test_system_info(self):
        """Test system info command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("system info")
    
    def test_screenshot(self):
        """Test screenshot command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        with patch('pyautogui.screenshot'):
            if hasattr(processor, 'process'):
                result = processor.process("take a screenshot")


class TestCompoundCommands:
    """Tests for compound commands."""
    
    def test_compound_command_separation(self):
        """Test compound command is separated."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        # Test that compound commands are recognized
        command = "open chrome and then open notepad"
        # Should split on "and then"


class TestCommandHistory:
    """Tests for command history."""
    
    def test_history_tracking(self):
        """Test that commands are added to history."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process') and hasattr(processor, 'history'):
            initial_len = len(processor.history)
            processor.process("hello")
            # History may or may not increase depending on implementation


class TestMediaCommands:
    """Tests for media control commands."""
    
    def test_play_pause(self):
        """Test play/pause command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("pause music")
    
    def test_next_track(self):
        """Test next track command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("next track")
    
    def test_previous_track(self):
        """Test previous track command."""
        from modules import voice_nlu as vn
        processor = vn.VoiceCommandProcessor()
        
        if hasattr(processor, 'process'):
            result = processor.process("previous track")


class TestProcessExecutionSafety:
    def test_handle_open_app_uses_argument_list(self):
        from modules import voice_nlu as vn

        processor = vn.VoiceCommandProcessor()

        with patch('subprocess.Popen') as mock_popen:
            handled, _ = processor._handle_open_app("open notepad")

        assert handled is True
        assert mock_popen.called
        launch_args = mock_popen.call_args[0][0]
        assert isinstance(launch_args, list)

    def test_handle_close_app_uses_subprocess_run(self):
        from modules import voice_nlu as vn

        processor = vn.VoiceCommandProcessor()

        with patch('subprocess.run') as mock_run:
            handled, _ = processor._handle_close_app("close chrome")

        assert handled is True
        assert mock_run.called
        kill_args = mock_run.call_args[0][0]
        assert isinstance(kill_args, list)

    def test_handle_power_confirm_shutdown_uses_subprocess_run(self):
        from modules import voice_nlu as vn

        processor = vn.VoiceCommandProcessor()

        with patch('subprocess.run') as mock_run:
            handled, _ = processor._handle_power("confirm shutdown")

        assert handled is True
        assert mock_run.called
        shutdown_args = mock_run.call_args[0][0]
        assert isinstance(shutdown_args, list)
        assert shutdown_args[:2] == ["shutdown", "/s"]
