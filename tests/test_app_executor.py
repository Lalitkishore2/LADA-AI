"""Regression tests for core.executors.app_executor safety behavior."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.executors.app_executor import AppExecutor


class _FakePersonality:
    @staticmethod
    def get_acknowledgment():
        return "Done."

    @staticmethod
    def get_confirmation():
        return "Done."


class _FakeCore:
    def __init__(self):
        self.websites = {}
        self.apps = {}


def _patch_personality(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "lada_jarvis_core",
        SimpleNamespace(LadaPersonality=_FakePersonality),
    )


def test_app_executor_open_unknown_uses_argv(monkeypatch):
    _patch_personality(monkeypatch)
    core = _FakeCore()
    executor = AppExecutor(core)

    popen = MagicMock()
    monkeypatch.setattr("core.executors.app_executor.subprocess.Popen", popen)

    handled, _ = executor.try_handle("open calculator")

    assert handled is True
    assert popen.called
    args = popen.call_args[0][0]
    assert isinstance(args, list)


def test_app_executor_close_uses_taskkill_argv(monkeypatch):
    _patch_personality(monkeypatch)
    core = _FakeCore()
    executor = AppExecutor(core)

    run = MagicMock()
    monkeypatch.setattr("core.executors.app_executor.subprocess.run", run)

    handled, _ = executor.try_handle("close chrome")

    assert handled is True
    run.assert_called_once()
    cmd = run.call_args[0][0]
    assert isinstance(cmd, list)
    assert cmd[:2] == ["taskkill", "/im"]
