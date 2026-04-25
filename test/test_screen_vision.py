"""Tests for modules/screen_vision.py"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestScreenVision:
    """Tests for ScreenVision class"""

    def test_init(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", False)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        assert vision.screenshot_dir.exists()
        assert vision.last_screenshot is None

    def test_init_with_router(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", False)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)

        from modules.screen_vision import ScreenVision

        mock_router = MagicMock()
        vision = ScreenVision(ai_router=mock_router)
        assert vision.ai_router == mock_router

    def test_capture_screen_no_pyautogui(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", False)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        result = vision.capture_screen()

        assert result["success"] is False
        assert "not available" in result.get("error", "").lower()

    def test_capture_screen_with_pyautogui(self, monkeypatch, tmp_path):
        mock_pyautogui = MagicMock()
        mock_screenshot = MagicMock()
        mock_screenshot.size = (1920, 1080)
        mock_pyautogui.screenshot.return_value = mock_screenshot

        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", True)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)
        monkeypatch.setattr("modules.screen_vision.pyautogui", mock_pyautogui)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        vision.screenshot_dir = tmp_path

        result = vision.capture_screen()

        assert result["success"] is True
        assert "path" in result

    def test_capture_screen_with_region(self, monkeypatch, tmp_path):
        mock_pyautogui = MagicMock()
        mock_screenshot = MagicMock()
        mock_screenshot.size = (100, 100)
        mock_pyautogui.screenshot.return_value = mock_screenshot

        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", True)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)
        monkeypatch.setattr("modules.screen_vision.pyautogui", mock_pyautogui)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        vision.screenshot_dir = tmp_path

        result = vision.capture_screen(region=(0, 0, 100, 100))

        mock_pyautogui.screenshot.assert_called_once()
        assert result["success"] is True

    def test_extract_text_no_ocr(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", True)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        result = vision.extract_text(path="some_image.png")

        assert result.get("success") is False

    def test_extract_text_no_image(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", True)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", True)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        vision.last_screenshot = None

        result = vision.extract_text()

        # Should return error when no image available
        assert result.get("success") is False or "error" in result

    def test_analyze_screen_method_exists(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", True)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()
        assert hasattr(vision, "analyze_screen")

    def test_find_text_on_screen_no_ocr(self, monkeypatch):
        monkeypatch.setattr("modules.screen_vision.PYAUTOGUI_OK", True)
        monkeypatch.setattr("modules.screen_vision.PIL_OK", True)
        monkeypatch.setattr("modules.screen_vision.OCR_OK", False)

        from modules.screen_vision import ScreenVision

        vision = ScreenVision()

        if hasattr(vision, "find_text_on_screen"):
            result = vision.find_text_on_screen("test")
            assert result.get("success") is False
