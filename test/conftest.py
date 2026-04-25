import pytest
import sys
from unittest.mock import MagicMock
import os
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock external dependencies before they are imported by modules
sys.modules['pygetwindow'] = MagicMock()
sys.modules['pyautogui'] = MagicMock()
sys.modules['pyautogui'].size.return_value = (1920, 1080)
sys.modules['pyautogui'].position.return_value = (100, 100)
sys.modules['selenium'] = MagicMock()
sys.modules['selenium.webdriver'] = MagicMock()
sys.modules['selenium.webdriver.common.by'] = MagicMock()
sys.modules['selenium.webdriver.common.keys'] = MagicMock()
sys.modules['selenium.webdriver.support.ui'] = MagicMock()
sys.modules['selenium.webdriver.support'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.credentials'] = MagicMock()
sys.modules['google_auth_oauthlib'] = MagicMock()
sys.modules['google_auth_oauthlib.flow'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['googleapiclient.errors'] = MagicMock()
sys.modules['psutil'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageGrab'] = MagicMock()
sys.modules['cv2'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()
sys.modules['soundfile'] = MagicMock()
sys.modules['speech_recognition'] = MagicMock()
sys.modules['pyttsx3'] = MagicMock()
sys.modules['spacy'] = MagicMock()
sys.modules['spacy.cli'] = MagicMock()
sys.modules['spacy.language'] = MagicMock()
sys.modules['thinc'] = MagicMock()
sys.modules['thinc.api'] = MagicMock()
sys.modules['en_core_web_sm'] = MagicMock()
sys.modules['pytesseract'] = MagicMock()
sys.modules['pandas'] = MagicMock()
sys.modules['pandas.compat'] = MagicMock()
sys.modules['pandas.util'] = MagicMock()
sys.modules['pandas._libs'] = MagicMock()

@pytest.fixture
def temp_test_dir():
    """Create a temporary directory for file testing"""
    test_dir = tempfile.mkdtemp()
    yield test_dir
    shutil.rmtree(test_dir)

@pytest.fixture
def mock_window():
    """Mock a window object"""
    mock = MagicMock()
    mock.title = "Test Window"
    mock._hWnd = 12345
    mock.left = 0
    mock.top = 0
    mock.width = 800
    mock.height = 600
    mock.isActive = True
    mock.isMinimized = False
    mock.isMaximized = False
    return mock

@pytest.fixture
def mock_browser_driver():
    """Mock Selenium WebDriver"""
    driver = MagicMock()
    driver.title = "Test Page"
    driver.current_url = "http://example.com"
    driver.page_source = "<html><body><h1>Test</h1></body></html>"
    return driver

@pytest.fixture
def mock_ai_router():
    """Mock AI router for testing (Legacy support)"""
    mock = MagicMock()
    mock.query.return_value = "Mock response"
    return mock
