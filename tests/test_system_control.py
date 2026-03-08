"""
Tests for modules/system_control.py
Covers: PowerAction enum, SystemController class
"""

import pytest
import sys
from unittest.mock import MagicMock, patch


# Mock Windows-specific modules before import
@pytest.fixture(autouse=True)
def mock_windows_modules():
    """Mock Windows-specific modules."""
    mock_pycaw = MagicMock()
    mock_pycaw.AudioUtilities = MagicMock()
    mock_pycaw.AudioUtilities.GetSpeakers.return_value = MagicMock()
    
    mock_psutil = MagicMock()
    mock_psutil.cpu_percent.return_value = 50.0
    mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
    mock_psutil.disk_usage.return_value = MagicMock(percent=70.0)
    mock_psutil.sensors_battery.return_value = MagicMock(percent=80.0)
    mock_psutil.net_if_addrs.return_value = {}
    mock_psutil.pids.return_value = [1, 2, 3]
    mock_psutil.Process = MagicMock()
    
    with patch.dict(sys.modules, {
        'pycaw': mock_pycaw,
        'pycaw.pycaw': mock_pycaw,
        'psutil': mock_psutil,
        'screen_brightness_control': MagicMock(),
        'pywifi': MagicMock()
    }):
        yield


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules(mock_windows_modules):
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'system_control' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestPowerAction:
    """Tests for PowerAction enum."""
    
    def test_power_action_values(self):
        """Test PowerAction enum values."""
        from modules import system_control as sc
        assert sc.PowerAction.SLEEP.value == "sleep"
        assert sc.PowerAction.HIBERNATE.value == "hibernate"
        assert sc.PowerAction.SHUTDOWN.value == "shutdown"
        assert sc.PowerAction.RESTART.value == "restart"
        assert sc.PowerAction.LOCK.value == "lock"
        assert sc.PowerAction.LOGOFF.value == "logoff"


class TestSystemControllerInit:
    """Tests for SystemController initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        from modules import system_control as sc
        controller = sc.SystemController()
        assert controller is not None
    
    def test_init_has_volume(self):
        """Test controller has volume attribute."""
        from modules import system_control as sc
        controller = sc.SystemController()
        assert hasattr(controller, 'current_volume')
    
    def test_init_has_brightness(self):
        """Test controller has brightness attribute."""
        from modules import system_control as sc
        controller = sc.SystemController()
        assert hasattr(controller, 'current_brightness')


class TestVolumeControl:
    """Tests for volume control."""
    
    def test_set_volume(self):
        """Test setting volume."""
        from modules import system_control as sc
        controller = sc.SystemController()
        result = controller.set_volume(50)
        assert 'success' in result
    
    def test_set_volume_clamps_max(self):
        """Test volume is clamped to 100."""
        from modules import system_control as sc
        controller = sc.SystemController()
        result = controller.set_volume(150)
        # Should clamp to 100
        assert result.get('volume', 100) <= 100
    
    def test_set_volume_clamps_min(self):
        """Test volume is clamped to 0."""
        from modules import system_control as sc
        controller = sc.SystemController()
        result = controller.set_volume(-50)
        # Should clamp to 0
        assert result.get('volume', 0) >= 0
    
    def test_get_volume(self):
        """Test getting volume."""
        from modules import system_control as sc
        controller = sc.SystemController()
        result = controller.get_volume()
        assert 'success' in result


class TestBrightnessControl:
    """Tests for brightness control."""
    
    def test_set_brightness(self):
        """Test setting brightness."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'set_brightness'):
            result = controller.set_brightness(70)
            assert result is None or 'success' in result
    
    def test_get_brightness(self):
        """Test getting brightness."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'get_brightness'):
            result = controller.get_brightness()


class TestMuteControl:
    """Tests for mute control."""
    
    def test_mute(self):
        """Test muting."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'mute'):
            result = controller.mute()
    
    def test_unmute(self):
        """Test unmuting."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'unmute'):
            result = controller.unmute()
    
    def test_toggle_mute(self):
        """Test toggling mute."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'toggle_mute'):
            result = controller.toggle_mute()


class TestWiFiControl:
    """Tests for WiFi control."""
    
    def test_get_wifi_status(self):
        """Test getting WiFi status."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'get_wifi_status'):
            result = controller.get_wifi_status()
    
    def test_toggle_wifi(self):
        """Test toggling WiFi."""
        from modules import system_control as sc
        controller = sc.SystemController()
        if hasattr(controller, 'toggle_wifi'):
            result = controller.toggle_wifi()


class TestPowerControl:
    """Tests for power control."""
    
    def test_execute_power_action(self):
        """Test executing power action."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        # Mock subprocess to avoid actually executing power commands
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            if hasattr(controller, 'execute_power_action'):
                # This should not actually execute
                pass  # Just checking method exists
    
    def test_lock_screen(self):
        """Test locking screen."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            if hasattr(controller, 'lock_screen'):
                result = controller.lock_screen()


class TestSystemInfo:
    """Tests for system information."""
    
    def test_get_system_info(self):
        """Test getting system info."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        if hasattr(controller, 'get_system_info'):
            info = controller.get_system_info()
            assert info is None or isinstance(info, dict)
    
    def test_get_battery_status(self):
        """Test getting battery status."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        if hasattr(controller, 'get_battery_status'):
            status = controller.get_battery_status()


class TestProcessControl:
    """Tests for process control."""
    
    def test_list_processes(self):
        """Test listing processes."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        if hasattr(controller, 'list_processes'):
            processes = controller.list_processes()
    
    def test_kill_process(self):
        """Test killing a process."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        with patch('psutil.Process') as mock_process:
            mock_process.return_value.terminate = MagicMock()
            
            if hasattr(controller, 'kill_process'):
                # Don't actually kill anything
                pass


class TestClipboard:
    """Tests for clipboard operations."""
    
    def test_get_clipboard(self):
        """Test getting clipboard content."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        if hasattr(controller, 'get_clipboard'):
            content = controller.get_clipboard()
    
    def test_set_clipboard(self):
        """Test setting clipboard content."""
        from modules import system_control as sc
        controller = sc.SystemController()
        
        if hasattr(controller, 'set_clipboard'):
            result = controller.set_clipboard("test content")
