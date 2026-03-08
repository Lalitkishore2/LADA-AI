"""Tests for modules/task_planner.py"""
import json
from unittest.mock import MagicMock

import pytest


class TestTaskPlanner:
    """Tests for TaskPlanner class"""

    def test_init(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        assert planner.ai_router == mock_router
        assert planner.current_plan == []
        assert planner.execution_log == []

    def test_plan_task_success(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.return_value = json.dumps([
            {"number": 1, "action": "navigate", "target": "https://google.com", "description": "Open Google", "value": "", "wait_after": 2000},
            {"number": 2, "action": "fill", "target": "input", "description": "Fill search", "value": "test", "wait_after": 1000},
        ])

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Search for test on Google")

        assert len(steps) == 2
        assert steps[0]["action"] == "navigate"
        assert steps[1]["action"] == "fill"

    def test_plan_task_invalid_json(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.return_value = "This is not valid JSON at all"

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Do something")

        # Should return fallback plan
        assert isinstance(steps, list)

    def test_plan_task_exception(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        mock_router.query.side_effect = Exception("API Error")

        planner = TaskPlanner(mock_router)
        steps = planner.plan_task("Do something")

        # Should return fallback plan
        assert isinstance(steps, list)

    def test_validate_step_valid(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        step = {
            "number": 1,
            "action": "navigate",
            "target": "https://example.com",
            "description": "Go to example",
        }

        assert planner._validate_step(step) is True

    def test_validate_step_missing_fields(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        step = {"number": 1, "action": "navigate"}  # Missing target and description

        assert planner._validate_step(step) is False

    def test_get_fallback_plan(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)

        plan = planner._get_fallback_plan("Search for flights")

        assert isinstance(plan, list)
        assert len(plan) > 0
        assert plan[0].get("action") is not None

    def test_current_plan_access(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [{"number": 1, "action": "navigate", "target": "url", "description": "test"}]

        assert planner.current_plan == [{"number": 1, "action": "navigate", "target": "url", "description": "test"}]

    def test_clear_plan(self):
        from modules.task_planner import TaskPlanner

        mock_router = MagicMock()
        planner = TaskPlanner(mock_router)
        planner.current_plan = [{"step": 1}]
        planner.execution_log = [{"log": 1}]

        planner.clear_plan()

        assert planner.current_plan == []
        assert planner.execution_log == []
