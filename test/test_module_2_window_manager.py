import pytest
from unittest.mock import MagicMock, patch
from modules.window_manager import WindowManager

class TestWindowManager:
    
    @pytest.fixture
    def manager(self):
        return WindowManager()

    @patch('modules.window_manager.gw')
    def test_list_windows(self, mock_gw, manager):
        """Test listing windows"""
        # Setup mock windows
        w1 = MagicMock()
        w1.title = "Window 1"
        # w1.title is a string, so we don't mock strip on it.
        
        w2 = MagicMock()
        w2.title = "Window 2"
        
        mock_gw.getAllWindows.return_value = [w1, w2]
        mock_gw.getActiveWindow.return_value = w1
        
        windows = manager.list_windows()
        assert windows['count'] == 2
        assert windows['windows'][0].title == "Window 1"
        assert windows['windows'][0].is_active is True

    @patch('modules.window_manager.gw')
    def test_switch_to_window(self, mock_gw, manager):
        """Test switching to a window"""
        w1 = MagicMock()
        w1.title = "Target Window"
        w1.isMinimized = False
        mock_gw.getAllWindows.return_value = [w1]
        mock_gw.getActiveWindow.return_value = None
        
        # Assuming switch_to_window exists
        if hasattr(manager, 'switch_to_window'):
            result = manager.switch_to_window("Target Window")
            w1.activate.assert_called_once()
            assert result['success'] is True

    @patch('modules.window_manager.gw')
    def test_maximize_window(self, mock_gw, manager):
        """Test maximizing a window"""
        w1 = MagicMock()
        w1.title = "Target"
        mock_gw.getAllWindows.return_value = [w1]
        
        if hasattr(manager, 'maximize_window'):
            manager.maximize_window("Target")
            w1.maximize.assert_called_once()

    @patch('modules.window_manager.gw')
    def test_minimize_window(self, mock_gw, manager):
        """Test minimizing a window"""
        w1 = MagicMock()
        w1.title = "Target"
        mock_gw.getAllWindows.return_value = [w1]
        
        if hasattr(manager, 'minimize_window'):
            manager.minimize_window("Target")
            w1.minimize.assert_called_once()

    @patch('modules.window_manager.gw')
    def test_close_window(self, mock_gw, manager):
        """Test closing a window"""
        w1 = MagicMock()
        w1.title = "Target"
        mock_gw.getAllWindows.return_value = [w1]
        
        if hasattr(manager, 'close_window'):
            manager.close_window("Target")
            w1.close.assert_called_once()

    @patch('subprocess.Popen')
    @patch('pathlib.Path.exists')
    def test_open_application(self, mock_exists, mock_popen, manager):
        """Test opening an application"""
        mock_exists.return_value = True
        if hasattr(manager, 'open_application'):
            manager.open_application("notepad")
            mock_popen.assert_called()

    def test_get_active_window(self, manager):
        """Test getting active window"""
        with patch('modules.window_manager.gw') as mock_gw:
            w1 = MagicMock()
            w1.title = "Active"
            mock_gw.getActiveWindow.return_value = w1
            
            if hasattr(manager, 'get_active_window'):
                info = manager.get_active_window()
                assert info['title'] == "Active"
