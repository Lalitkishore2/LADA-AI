"""Tests for modules/routine_manager.py"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Mock schedule module
@pytest.fixture(autouse=True)
def mock_schedule():
    mock_sched = MagicMock()
    sys.modules["schedule"] = mock_sched
    yield mock_sched


class TestRoutine:
    """Tests for Routine dataclass"""

    def test_routine_creation(self, mock_schedule):
        from modules.routine_manager import Routine

        routine = Routine(
            name="morning_routine",
            workflow_name="morning_workflow",
            schedule_type="daily",
            schedule_time="08:00",
        )
        assert routine.name == "morning_routine"
        assert routine.workflow_name == "morning_workflow"
        assert routine.schedule_type == "daily"
        assert routine.schedule_time == "08:00"
        assert routine.enabled is True

    def test_routine_defaults(self, mock_schedule):
        from modules.routine_manager import Routine

        routine = Routine(
            name="test",
            workflow_name="test_workflow",
            schedule_type="trigger",
        )
        assert routine.days_of_week == []
        assert routine.trigger_event is None
        assert routine.context_conditions == {}
        assert routine.last_run is None
        assert routine.run_count == 0


class TestRoutineManager:
    """Tests for RoutineManager class"""

    def test_init(self, mock_schedule, tmp_path, monkeypatch):
        from modules.routine_manager import RoutineManager

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )

        manager = RoutineManager()
        assert manager.routines == {}
        assert manager.running is False

    def test_register_routine(self, mock_schedule, tmp_path, monkeypatch):
        from modules.routine_manager import RoutineManager, Routine

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )
        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._save_routine",
            lambda self, r: None,
        )

        manager = RoutineManager()
        manager.routine_dir = tmp_path

        routine = Routine(
            name="test_routine",
            workflow_name="test_workflow",
            schedule_type="trigger",
            trigger_event="system_startup",
        )

        result = manager.register_routine(routine)
        assert result is True
        assert "test_routine" in manager.routines

    def test_register_daily_routine(self, mock_schedule, tmp_path, monkeypatch):
        from modules.routine_manager import RoutineManager, Routine

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )
        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._save_routine",
            lambda self, r: None,
        )
        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._schedule_daily_routine",
            lambda self, r: None,
        )

        manager = RoutineManager()
        manager.routine_dir = tmp_path

        routine = Routine(
            name="daily_routine",
            workflow_name="daily_workflow",
            schedule_type="daily",
            schedule_time="09:00",
        )

        result = manager.register_routine(routine)
        assert result is True

    def test_trigger_handlers_registered(self, mock_schedule, monkeypatch):
        from modules.routine_manager import RoutineManager

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )

        manager = RoutineManager()
        assert "system_startup" in manager.trigger_handlers
        assert "user_login" in manager.trigger_handlers
        assert "idle_detected" in manager.trigger_handlers

    def test_routines_dict_access(self, mock_schedule, monkeypatch):
        from modules.routine_manager import RoutineManager, Routine

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )

        manager = RoutineManager()
        routine = Routine(
            name="test",
            workflow_name="wf",
            schedule_type="trigger",
        )
        manager.routines["test"] = routine

        # Access directly via dict
        assert "test" in manager.routines
        assert manager.routines["test"] == routine

    def test_routines_dict_missing(self, mock_schedule, monkeypatch):
        from modules.routine_manager import RoutineManager

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )

        manager = RoutineManager()
        assert "nonexistent" not in manager.routines

    def test_list_routines(self, mock_schedule, monkeypatch):
        from modules.routine_manager import RoutineManager, Routine

        monkeypatch.setattr(
            "modules.routine_manager.RoutineManager._load_routines",
            lambda self: None,
        )

        manager = RoutineManager()
        manager.routines["r1"] = Routine(name="r1", workflow_name="w1", schedule_type="daily")
        manager.routines["r2"] = Routine(name="r2", workflow_name="w2", schedule_type="trigger")

        result = manager.list_routines()
        assert len(result) == 2
