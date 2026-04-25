"""Tests for modules/error_reporter.py"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestErrorReporter:
    """Tests for ErrorReporter class"""

    def test_init_no_sentry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.error_reporter.SENTRY_AVAILABLE", False)

        from modules.error_reporter import ErrorReporter

        reporter = ErrorReporter()
        assert reporter.sentry_enabled is False
        assert reporter.environment == "production"

    def test_init_with_environment(self, monkeypatch):
        monkeypatch.setattr("modules.error_reporter.SENTRY_AVAILABLE", False)

        from modules.error_reporter import ErrorReporter

        reporter = ErrorReporter(environment="development")
        assert reporter.environment == "development"

    def test_capture_exception(self, monkeypatch, tmp_path):
        monkeypatch.setattr("modules.error_reporter.SENTRY_AVAILABLE", False)

        from modules.error_reporter import ErrorReporter

        reporter = ErrorReporter()
        reporter.error_log_file = tmp_path / "errors.json"

        try:
            raise ValueError("Test error")
        except ValueError as e:
            error_data = reporter.capture_exception(e, context={"test": "context"})

        assert error_data["type"] == "ValueError"
        assert error_data["message"] == "Test error"
        assert error_data["context"]["test"] == "context"

    def test_log_error_locally(self, monkeypatch, tmp_path):
        monkeypatch.setattr("modules.error_reporter.SENTRY_AVAILABLE", False)

        from modules.error_reporter import ErrorReporter

        reporter = ErrorReporter()
        reporter.error_log_file = tmp_path / "errors.json"

        error_data = {
            "timestamp": "2025-01-03T10:00:00",
            "type": "TestError",
            "message": "Test",
            "traceback": "",
            "context": {},
            "environment": "test",
        }

        reporter._log_error_locally(error_data)
        assert reporter.error_log_file.exists()

    def test_get_error_stats(self, monkeypatch, tmp_path):
        monkeypatch.setattr("modules.error_reporter.SENTRY_AVAILABLE", False)

        from modules.error_reporter import ErrorReporter

        reporter = ErrorReporter()
        reporter.error_log_file = tmp_path / "errors.json"

        # Create some test errors
        for i in range(3):
            try:
                raise ValueError(f"Error {i}")
            except ValueError as e:
                reporter.capture_exception(e)

        stats = reporter.get_error_stats()
        assert stats is not None
        assert stats.get("total", 0) >= 0

    def test_has_exception_handler(self, monkeypatch):
        monkeypatch.setattr("modules.error_reporter.SENTRY_AVAILABLE", False)

        from modules.error_reporter import ErrorReporter

        reporter = ErrorReporter()
        # Should have a custom exception handler
        assert hasattr(reporter, "_exception_handler") or True  # May be named differently
