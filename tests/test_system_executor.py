"""Regression tests for core.executors.system_executor volume handling."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.executors.system_executor import SystemExecutor


class _FakePersonality:
    @staticmethod
    def get_acknowledgment():
        return "Done."


class _FakeCore:
    def __init__(self, system):
        self.system = system


def _patch_personality(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "lada_jarvis_core",
        SimpleNamespace(LadaPersonality=_FakePersonality),
    )


def test_system_executor_parses_set_laptop_volume_by_phrase(monkeypatch):
    _patch_personality(monkeypatch)

    system = MagicMock()
    system.set_volume.return_value = {"success": True, "volume": 70}

    executor = SystemExecutor(_FakeCore(system))
    handled, response = executor.try_handle("set the laptop volume by 70%")

    assert handled is True
    system.set_volume.assert_called_once_with(70)
    assert "70%" in response


def test_system_executor_unmute_not_treated_as_mute(monkeypatch):
    _patch_personality(monkeypatch)

    system = MagicMock()
    system.set_volume.return_value = {"success": True}

    executor = SystemExecutor(_FakeCore(system))
    handled, response = executor.try_handle("unmute")

    assert handled is True
    system.set_volume.assert_called_once_with(100)
    assert "maximum" in response.lower()


def test_system_executor_surfaces_volume_set_failure(monkeypatch):
    _patch_personality(monkeypatch)

    system = MagicMock()
    system.set_volume.return_value = {
        "success": False,
        "error": "pycaw not installed",
    }

    executor = SystemExecutor(_FakeCore(system))
    handled, response = executor.try_handle("set volume to 70")

    assert handled is True
    assert "couldn't change the volume" in response.lower()
    assert "pycaw not installed" in response


def test_system_executor_confirm_shutdown_reaches_execution(monkeypatch):
    _patch_personality(monkeypatch)

    system = MagicMock()
    executor = SystemExecutor(_FakeCore(system))

    run = MagicMock()
    monkeypatch.setattr("core.executors.system_executor.subprocess.run", run)

    handled, _ = executor.try_handle("confirm shutdown")

    assert handled is True
    run.assert_called_once()
    cmd = run.call_args[0][0]
    assert cmd[:2] == ["shutdown", "/s"]
