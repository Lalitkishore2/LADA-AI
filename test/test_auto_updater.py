"""Tests for modules/auto_updater.py"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Mock requests module
@pytest.fixture(autouse=True)
def mock_requests():
    mock_req = MagicMock()
    sys.modules["requests"] = mock_req
    yield mock_req


class TestAutoUpdater:
    """Tests for AutoUpdater class"""

    def test_init_default(self):
        from modules.auto_updater import AutoUpdater

        updater = AutoUpdater()
        assert updater.current_version == "7.0.0"
        assert "lada-ai" in updater.repo

    def test_init_custom_repo(self):
        from modules.auto_updater import AutoUpdater

        updater = AutoUpdater(repo="myuser/myrepo")
        assert "myuser/myrepo" in updater.repo

    def test_init_custom_version(self):
        from modules.auto_updater import AutoUpdater

        updater = AutoUpdater(current_version="8.0.0")
        assert updater.current_version == "8.0.0"

    def test_api_url_constructed(self):
        from modules.auto_updater import AutoUpdater

        updater = AutoUpdater(repo="user/repo")
        assert "user/repo" in updater.api_url
        assert "releases/latest" in updater.api_url

    def test_check_for_updates_no_network(self, monkeypatch):
        from modules.auto_updater import AutoUpdater

        mock_requests = MagicMock()
        mock_requests.get.side_effect = Exception("Network error")
        monkeypatch.setattr("modules.auto_updater.requests", mock_requests)

        updater = AutoUpdater()
        result = updater.check_for_updates(force=True)

        # Should return None on error
        assert result is None

    def test_check_for_updates_success(self, monkeypatch, tmp_path):
        from modules.auto_updater import AutoUpdater

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v9.0.0",
            "name": "LADA v9.0.0",
            "body": "Release notes here",
            "published_at": "2025-01-03T10:00:00Z",
            "assets": [{"browser_download_url": "https://example.com/file.zip"}],
        }

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response
        monkeypatch.setattr("modules.auto_updater.requests", mock_requests)

        updater = AutoUpdater(current_version="7.0.0")
        updater.cache_file = tmp_path / "cache.json"

        result = updater.check_for_updates(force=True)

        # Should return update info if newer version
        assert result is None or result.get("available") is True

    def test_check_for_updates_no_update_needed(self, monkeypatch, tmp_path):
        from modules.auto_updater import AutoUpdater

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v7.0.0",  # Same version
            "name": "LADA v7.0.0",
            "body": "Release notes",
            "published_at": "2025-01-03T10:00:00Z",
            "assets": [],
        }

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response
        monkeypatch.setattr("modules.auto_updater.requests", mock_requests)

        updater = AutoUpdater(current_version="7.0.0")
        updater.cache_file = tmp_path / "cache.json"

        result = updater.check_for_updates(force=True)

        # Same version, no update needed
        assert result is None

    def test_is_newer_version(self):
        from modules.auto_updater import AutoUpdater

        updater = AutoUpdater(current_version="7.0.0")

        assert updater._is_newer_version("8.0.0") is True
        assert updater._is_newer_version("7.1.0") is True
        assert updater._is_newer_version("7.0.1") is True
        assert updater._is_newer_version("7.0.0") is False
        assert updater._is_newer_version("6.0.0") is False

    def test_download_update_no_info(self):
        from modules.auto_updater import AutoUpdater

        updater = AutoUpdater()

        # Test with valid but no download_url
        update_info = {"version": "8.0.0", "available": True}
        result = updater.download_update(update_info)
        # Should return None when no download_url
        assert result is None
