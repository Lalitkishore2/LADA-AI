"""Tests for Windows capture guard wrapper."""

from modules.windows_capture_guard import apply_foreground_capture_guard


def test_capture_guard_non_windows_returns_clean_failure(monkeypatch):
    monkeypatch.setattr("modules.windows_capture_guard._is_windows", lambda: False)
    result = apply_foreground_capture_guard()
    assert result.success is False
    assert "Windows-only" in result.message
