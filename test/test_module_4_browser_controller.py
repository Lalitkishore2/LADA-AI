import pytest
from unittest.mock import MagicMock, patch
from modules.browser_tab_controller import BrowserTabController

class TestBrowserTabController:
    
    @pytest.fixture
    def controller(self):
        # Mock selenium and pyautogui
        with patch('modules.browser_tab_controller.webdriver') as mock_webdriver, \
             patch('modules.browser_tab_controller.pyautogui') as mock_pyautogui:
            
            controller = BrowserTabController()
            # Mock drivers dict
            controller.drivers = {'chrome': MagicMock()}
            controller.use_selenium = True
            return controller

    def test_open_tab(self, controller):
        """Test opening a new tab"""
        url = "http://example.com"
        result = controller.open_tab(url, browser='chrome')
        
        assert result['success'] is True
        assert result['url'] == "https://http://example.com" or result['url'] == "http://example.com"
        # Verify selenium execution
        controller.drivers['chrome'].execute_script.assert_called()

    def test_close_tab(self, controller):
        """Test closing a tab"""
        result = controller.close_tab(browser='chrome')
        
        assert result['success'] is True
        controller.drivers['chrome'].close.assert_called()

    def test_switch_tab(self, controller):
        """Test switching tabs"""
        # This uses pyautogui in the implementation
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.switch_tab(direction='next', count=1)
            assert result['success'] is True
            assert result['direction'] == 'next'

    def test_switch_to_tab_number(self, controller):
        """Test switching to specific tab number"""
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.switch_to_tab_number(1)
            assert result['success'] is True
            assert result['tab_number'] == 1

    def test_navigate_to(self, controller):
        """Test navigation"""
        url = "http://test.com"
        result = controller.navigate_to(url, browser='chrome')
        
        assert result['success'] is True
        controller.drivers['chrome'].get.assert_called()

    def test_refresh_tab(self, controller):
        """Test refreshing tab"""
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.refresh_tab(hard_refresh=False)
            assert result['success'] is True
            assert result['hard_refresh'] is False

    def test_go_back(self, controller):
        """Test going back"""
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.go_back()
            assert result['success'] is True

    def test_go_forward(self, controller):
        """Test going forward"""
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.go_forward()
            assert result['success'] is True

    def test_google_search(self, controller):
        """Test google search"""
        # Mock open_tab since google_search calls it
        controller.open_tab = MagicMock(return_value={'success': True})
        
        result = controller.google_search("test query")
        
        assert result['success'] is True
        controller.open_tab.assert_called()
        args, _ = controller.open_tab.call_args
        assert "google.com/search" in args[0]
        assert "test+query" in args[0] or "test%20query" in args[0]

    def test_scroll_page(self, controller):
        """Test scrolling"""
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.scroll_page(direction='down', amount='page')
            assert result['success'] is True
            assert result['direction'] == 'down'

    def test_zoom(self, controller):
        """Test zooming"""
        with patch('modules.browser_tab_controller.PYAUTOGUI_OK', True):
            result = controller.zoom(action='in')
            assert result['success'] is True
            assert result['action'] == 'in'
