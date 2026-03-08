import pytest
from unittest.mock import MagicMock, patch
from modules.gui_automator import GUIAutomator

class TestGUIAutomator:
    
    @pytest.fixture
    def automator(self):
        with patch('modules.gui_automator.pyautogui') as mock_pyautogui:
            # Setup mock pyautogui
            mock_pyautogui.size.return_value = (1920, 1080)
            mock_pyautogui.position.return_value = (100, 200)
            
            automator = GUIAutomator()
            yield automator

    def test_click(self, automator):
        """Test clicking"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.click(100, 200, button='left', clicks=1)
            
            assert result['success'] is True
            assert result['position']['x'] == 100
            assert result['position']['y'] == 200
            assert result['button'] == 'left'

    def test_double_click(self, automator):
        """Test double clicking"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.double_click(100, 200)
            
            assert result['success'] is True
            assert result['clicks'] == 2

    def test_right_click(self, automator):
        """Test right clicking"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.right_click(100, 200)
            
            assert result['success'] is True
            assert result['button'] == 'right'

    def test_move_mouse(self, automator):
        """Test moving mouse"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.move_mouse(500, 500)
            
            assert result['success'] is True
            assert result['position']['x'] == 500
            assert result['position']['y'] == 500

    def test_get_mouse_position(self, automator):
        """Test getting mouse position"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.get_mouse_position()
            
            assert result['success'] is True
            assert result['x'] == 100
            assert result['y'] == 200

    def test_scroll(self, automator):
        """Test scrolling"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.scroll(direction='down', amount=3)
            
            assert result['success'] is True
            assert result['direction'] == 'down'
            assert result['amount'] == 3

    def test_drag(self, automator):
        """Test dragging"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.drag(0, 0, 100, 100)
            
            assert result['success'] is True
            assert result['from']['x'] == 0
            assert result['to']['x'] == 100

    def test_type_text(self, automator):
        """Test typing text"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.type_text("Hello World")
            
            assert result['success'] is True
            assert result['text'] == "Hello World"

    def test_press_key(self, automator):
        """Test pressing key"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.press_key('enter')
            
            assert result['success'] is True
            assert result['key'] == 'enter'

    def test_hotkey(self, automator):
        """Test hotkey"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            result = automator.hotkey('ctrl', 'c')
            
            assert result['success'] is True
            assert result['keys'] == ['ctrl', 'c']

    def test_screenshot(self, automator):
        """Test taking screenshot"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            # Mock screenshot object
            mock_img = MagicMock()
            mock_img.width = 1920
            mock_img.height = 1080
            
            with patch('modules.gui_automator.pyautogui.screenshot', return_value=mock_img):
                result = automator.screenshot()
                
                assert result['success'] is True
                assert result['size']['width'] == 1920
                assert result['size']['height'] == 1080
                assert 'base64' in result

    def test_find_image_on_screen(self, automator):
        """Test finding image"""
        with patch('modules.gui_automator.PYAUTOGUI_OK', True):
            # Mock locateOnScreen
            mock_loc = MagicMock()
            mock_loc.left = 10
            mock_loc.top = 10
            mock_loc.width = 50
            mock_loc.height = 50
            
            mock_center = MagicMock()
            mock_center.x = 35
            mock_center.y = 35
            
            with patch('modules.gui_automator.pyautogui.locateOnScreen', return_value=mock_loc), \
                 patch('modules.gui_automator.pyautogui.center', return_value=mock_center):
                
                result = automator.find_image_on_screen("test.png")
                
                assert result['success'] is True
                assert result['found'] is True
                assert result['position']['x'] == 35
