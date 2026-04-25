"""Tests for modules/page_vision.py"""
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestPageVision:
    """Tests for PageVision class"""

    def test_init_no_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()
            assert vision.api_key is None
            assert vision.cache == {}

    def test_init_with_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test_key")

        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()
            assert vision.api_key == "test_key"

    def test_init_with_explicit_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision(api_key="explicit_key")
            assert vision.api_key == "explicit_key"

    def test_load_image_not_exists(self, monkeypatch):
        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()
            result = vision._load_image("/nonexistent/path/image.png")
            assert result is None

    def test_load_image_exists(self, tmp_path, monkeypatch):
        from modules.page_vision import PageVision

        # Create test image file
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"fake image content")

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()
            result = vision._load_image(str(test_file))
            assert result == b"fake image content"

    def test_analyze_page_layout_cache_hit(self, monkeypatch):
        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()
            cached_result = {"page_type": "cached", "elements": []}
            vision.cache["layout_test.png"] = cached_result

            result = vision.analyze_page_layout("test.png")
            assert result == cached_result

    def test_analyze_page_layout_no_model(self, monkeypatch):
        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()
            vision.model = None

            result = vision.analyze_page_layout("nonexistent.png")
            # Should return error or empty result
            assert "error" in result or result.get("elements") == [] or result.get("page_type") == "unknown"

    def test_cache_stores_results(self, monkeypatch):
        from modules.page_vision import PageVision

        with patch.object(PageVision, "_init_model", return_value=None):
            vision = PageVision()

            vision.cache["test_key"] = {"result": "value"}
            assert "test_key" in vision.cache
            assert vision.cache["test_key"]["result"] == "value"

    def test_model_initialization_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        from modules.page_vision import PageVision

        vision = PageVision()
        # Without API key, model should not be initialized
        assert vision.model is None
