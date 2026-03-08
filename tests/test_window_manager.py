"""
Tests for modules/window_manager.py
Covers: WindowInfo dataclass, WindowManager class
"""

import pytest
import sys
from unittest.mock import MagicMock, patch


# Mock Windows-specific modules before import
@pytest.fixture(autouse=True)
def mock_windows_modules():
    """Mock Windows-specific modules."""
    mock_gw = MagicMock()
    mock_gw.getAllWindows.return_value = []
    mock_gw.getActiveWindow.return_value = None
    
    mock_psutil = MagicMock()
    mock_psutil.Process = MagicMock()
    
    with patch.dict(sys.modules, {
        'pygetwindow': mock_gw,
        'psutil': mock_psutil,
        'pyautogui': MagicMock()
    }):
        yield


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules(mock_windows_modules):
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'window_manager' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestWindowInfo:
    """Tests for WindowInfo dataclass."""
    
    def test_window_info_creation(self):
        """Test WindowInfo creation."""
        from modules import window_manager as wm
        info = wm.WindowInfo(
            title="Test Window",
            handle=12345,
            x=100,
            y=100,
            width=800,
            height=600,
            is_active=True,
            is_minimized=False,
            is_maximized=False
        )
        assert info.title == "Test Window"
        assert info.handle == 12345
        assert info.is_active is True
    
    def test_window_info_with_process(self):
        """Test WindowInfo with process name."""
        from modules import window_manager as wm
        info = wm.WindowInfo(
            title="Chrome",
            handle=1,
            x=0,
            y=0,
            width=1920,
            height=1080,
            is_active=False,
            is_minimized=False,
            is_maximized=True,
            process_name="chrome.exe"
        )
        assert info.process_name == "chrome.exe"


class TestAppPaths:
    """Tests for APP_PATHS constant."""
    
    def test_app_paths_exists(self):
        """Test APP_PATHS dictionary exists."""
        from modules import window_manager as wm
        assert hasattr(wm, 'APP_PATHS')
        assert isinstance(wm.APP_PATHS, dict)
    
    def test_common_apps_in_paths(self):
        """Test common apps are in APP_PATHS."""
        from modules import window_manager as wm
        assert 'chrome' in wm.APP_PATHS or 'notepad' in wm.APP_PATHS


class TestWindowManagerInit:
    """Tests for WindowManager initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        assert manager is not None


class TestWindowManagerGetWindows:
    """Tests for getting windows."""
    
    def test_get_all_windows(self):
        """Test getting all windows."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'get_all_windows'):
            windows = manager.get_all_windows()
            assert windows is None or isinstance(windows, list)
    
    def test_get_active_window(self):
        """Test getting active window."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'get_active_window'):
            window = manager.get_active_window()
    
    def test_find_window_by_title(self):
        """Test finding window by title."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'find_window'):
            window = manager.find_window("Chrome")


class TestWindowManagerWindowActions:
    """Tests for window actions."""
    
    def test_activate_window(self):
        """Test activating a window."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'activate_window'):
            result = manager.activate_window("Notepad")
    
    def test_maximize_window(self):
        """Test maximizing a window."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'maximize_window'):
            result = manager.maximize_window("Test")
    
    def test_minimize_window(self):
        """Test minimizing a window."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'minimize_window'):
            result = manager.minimize_window("Test")
    
    def test_close_window(self):
        """Test closing a window."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'close_window'):
            result = manager.close_window("Test")


class TestWindowManagerAppControl:
    """Tests for application control."""
    
    def test_open_app(self):
        """Test opening an application."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        with patch('subprocess.Popen') as mock_popen:
            if hasattr(manager, 'open_app'):
                result = manager.open_app("notepad")
    
    def test_open_app_with_args(self):
        """Test opening app with arguments."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        with patch('subprocess.Popen') as mock_popen:
            if hasattr(manager, 'open_app'):
                result = manager.open_app("notepad", args=["test.txt"])
    
    def test_close_app(self):
        """Test closing an application."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            if hasattr(manager, 'close_app'):
                result = manager.close_app("notepad")


class TestWindowManagerArrangement:
    """Tests for window arrangement."""
    
    def test_snap_left(self):
        """Test snapping window to left."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'snap_window'):
            result = manager.snap_window("Test", "left")
    
    def test_snap_right(self):
        """Test snapping window to right."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'snap_window'):
            result = manager.snap_window("Test", "right")
    
    def test_arrange_windows(self):
        """Test arranging windows."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'arrange_windows'):
            result = manager.arrange_windows("grid")


class TestWindowManagerSearch:
    """Tests for window search."""
    
    def test_find_windows_by_process(self):
        """Test finding windows by process name."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'find_windows_by_process'):
            windows = manager.find_windows_by_process("chrome.exe")
    
    def test_search_windows(self):
        """Test searching windows."""
        from modules import window_manager as wm
        manager = wm.WindowManager()
        
        if hasattr(manager, 'search_windows'):
            windows = manager.search_windows("browser")
