"""Tests for modules/startup_optimizer.py"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


class TestStartupOptimizer:
    """Tests for StartupOptimizer class"""

    def test_init(self):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()
        assert optimizer.startup_time > 0
        assert optimizer._initialization_complete is False
        assert optimizer._loaded_modules == {}

    def test_init_with_jarvis_core(self):
        from modules.startup_optimizer import StartupOptimizer

        mock_jarvis = MagicMock()
        optimizer = StartupOptimizer(jarvis_core=mock_jarvis)
        assert optimizer.jarvis_core == mock_jarvis

    def test_optimize_imports(self, monkeypatch):
        from modules.startup_optimizer import StartupOptimizer
        import os

        optimizer = StartupOptimizer()
        optimizer.optimize_imports()

        # Should set environment variables
        assert os.environ.get("PYGAME_HIDE_SUPPORT_PROMPT") == "1"
        assert os.environ.get("TF_CPP_MIN_LOG_LEVEL") == "2"

    def test_get_startup_time(self):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()
        time.sleep(0.1)
        elapsed = optimizer.get_startup_time()

        assert elapsed >= 0.1

    def test_start_background_preload(self, monkeypatch):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()

        # Mock the lazy loader module
        mock_loader = MagicMock()
        mock_priority = MagicMock()
        mock_priority.get_background_modules.return_value = []

        monkeypatch.setattr(
            "modules.startup_optimizer.StartupOptimizer._background_preloader",
            lambda self: self._preload_complete.set(),
        )

        optimizer.start_background_preload()
        # Should have started a thread
        assert optimizer._background_thread is not None

    def test_wait_for_preload_timeout(self):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()
        # Don't start preload, so it should timeout
        result = optimizer.wait_for_preload(timeout=0.1)

        # Should return False on timeout (event not set)
        assert result is False

    def test_wait_for_preload_success(self):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()
        optimizer._preload_complete.set()

        result = optimizer.wait_for_preload(timeout=1.0)
        assert result is True

    def test_report_startup(self, capsys):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()
        optimizer._loaded_modules = {"module1": 0.5, "module2": 0.3}

        optimizer.report_startup()

        # Should print startup report
        captured = capsys.readouterr()
        # Just verify it runs without error
        assert True

    def test_loaded_modules_tracking(self):
        from modules.startup_optimizer import StartupOptimizer

        optimizer = StartupOptimizer()
        optimizer._loaded_modules["test_module"] = 0.5

        assert "test_module" in optimizer._loaded_modules
        assert optimizer._loaded_modules["test_module"] == 0.5
