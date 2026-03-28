"""
Tests for Stealth Browser
"""

import pytest
from unittest.mock import MagicMock
import sys

# Mock heavy imports
sys.modules['undetected_chromedriver'] = MagicMock()
sys.modules['selenium'] = MagicMock()
sys.modules['selenium.webdriver'] = MagicMock()
sys.modules['selenium.webdriver.common'] = MagicMock()
sys.modules['selenium.webdriver.common.by'] = MagicMock()
sys.modules['selenium.webdriver.common.keys'] = MagicMock()
sys.modules['selenium.webdriver.support'] = MagicMock()
sys.modules['selenium.webdriver.support.ui'] = MagicMock()

from modules.stealth_browser import StealthBrowser, get_stealth_browser


class TestStealthBrowser:
    """Test stealth browser functionality"""
    
    def test_browser_class_exists(self):
        """Test browser class exists"""
        assert StealthBrowser is not None
    
    def test_browser_creation(self):
        """Test browser can be created"""
        browser = StealthBrowser()
        assert browser is not None
    
    def test_has_navigate_method(self):
        """Test browser has navigate method"""
        browser = StealthBrowser()
        assert hasattr(browser, 'navigate')


class TestGetStealthBrowser:
    """Test module-level factory"""
    
    def test_factory_returns_browser(self):
        """Test factory function returns browser instance"""
        browser = get_stealth_browser()
        assert browser is not None
