import pytest
from unittest.mock import MagicMock, patch
from modules.screenshot_analysis import ScreenshotAnalyzer, TextBlock, UIElement

class TestScreenshotAnalyzer:
    
    @pytest.fixture
    def analyzer(self):
        with patch('modules.screenshot_analysis.pyautogui'), \
             patch('modules.screenshot_analysis.pytesseract'), \
             patch('modules.screenshot_analysis.Image'):
            analyzer = ScreenshotAnalyzer()
            return analyzer

    def test_capture_screen(self, analyzer):
        """Test capturing screen"""
        with patch('modules.screenshot_analysis.PYAUTOGUI_OK', True):
            mock_img = MagicMock()
            mock_img.size = (1920, 1080)
            
            with patch('modules.screenshot_analysis.pyautogui.screenshot', return_value=mock_img):
                result = analyzer.capture_screen(save=False)
                
                assert result['success'] is True
                assert result['image'] == mock_img
                assert result['size'] == (1920, 1080)

    def test_extract_text(self, analyzer):
        """Test extracting text"""
        with patch('modules.screenshot_analysis.OCR_OK', True):
            mock_img = MagicMock()
            
            # Mock pytesseract output
            mock_data = {
                'text': ['Hello', 'World'],
                'conf': [90, 95],
                'left': [10, 60],
                'top': [10, 10],
                'width': [40, 40],
                'height': [20, 20],
                'line_num': [1, 1],
                'word_num': [1, 2]
            }
            
            with patch('modules.screenshot_analysis.pytesseract.image_to_data', return_value=mock_data):
                result = analyzer.extract_text(mock_img, detailed=True)
                
                assert result['success'] is True
                assert len(result['blocks']) == 2
                assert result['text'] == "Hello World"

    def test_find_text(self, analyzer):
        """Test finding text"""
        with patch('modules.screenshot_analysis.OCR_OK', True):
            # Mock extract_text result
            mock_blocks = [
                TextBlock("Hello", 10, 10, 40, 20, 0.9),
                TextBlock("World", 60, 10, 40, 20, 0.95)
            ]
            
            with patch.object(analyzer, 'extract_text') as mock_extract:
                mock_extract.return_value = {
                    'success': True,
                    'blocks': mock_blocks
                }
                
                result = analyzer.find_text("Hello")
                
                assert result['success'] is True
                assert result['found'] is True
                assert len(result['locations']) == 1
                assert result['locations'][0]['text'] == "Hello"

    def test_detect_ui_elements(self, analyzer):
        """Test detecting UI elements"""
        with patch('modules.screenshot_analysis.OCR_OK', True):
            # Mock extract_text result with button keyword
            mock_blocks = [
                TextBlock("Submit", 10, 10, 50, 30, 0.9),
                TextBlock("Cancel", 70, 10, 50, 30, 0.9)
            ]
            
            with patch.object(analyzer, 'extract_text') as mock_extract:
                mock_extract.return_value = {
                    'success': True,
                    'blocks': mock_blocks
                }
                
                result = analyzer.detect_ui_elements(element_types=['button'])
                
                assert result['success'] is True
                assert len(result['elements']) == 2
                assert result['elements'][0].type == 'button'

    def test_find_element(self, analyzer):
        """Test finding specific element"""
        with patch('modules.screenshot_analysis.OCR_OK', True):
            mock_elements = [
                UIElement('button', 'Submit', 10, 10, 50, 30),
                UIElement('link', 'More', 100, 10, 40, 20)
            ]
            
            with patch.object(analyzer, 'detect_ui_elements') as mock_detect:
                mock_detect.return_value = {
                    'success': True,
                    'elements': mock_elements
                }
                
                result = analyzer.find_element(text="Submit", element_type="button")
                
                assert result['success'] is True
                assert result['found'] is True
                assert result['element'].text == "Submit"

    def test_click_text(self, analyzer):
        """Test clicking text"""
        with patch('modules.screenshot_analysis.PYAUTOGUI_OK', True):
            with patch.object(analyzer, 'find_text') as mock_find:
                mock_find.return_value = {
                    'success': True,
                    'found': True,
                    'locations': [{'center': (50, 50)}]
                }
                
                with patch('modules.screenshot_analysis.pyautogui.click') as mock_click:
                    result = analyzer.click_text("Button")
                    
                    assert result['success'] is True
                    mock_click.assert_called_with(50, 50)
