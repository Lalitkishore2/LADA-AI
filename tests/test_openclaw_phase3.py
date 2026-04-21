"""Phase 3 tests for Comet routing, specialist polling, planner selection, and telemetry."""

import sys
from types import SimpleNamespace

from modules.ai_command_agent import AICommandAgent
from modules.voice_nlu import VoiceCommandProcessor


class _DummyProviderManager:
    def get_best_model(self, _text, tier=None):
        return {"model_id": "gpt-test", "provider_id": "openai", "tier": tier}

    def get_provider_for_model(self, _model_id):
        return SimpleNamespace()


class _DummyToolRegistry:
    def __init__(self):
        self._tools = []

    def to_ai_schema(self):
        return []


def test_voice_autonomous_uses_comet_module_path(monkeypatch):
    calls = {}

    class _FakeComet:
        def execute_task_sync(self, task):
            calls["task"] = task
            return SimpleNamespace(success=True, message="comet completed")

        def cleanup(self):
            calls["cleanup"] = True

    fake_module = SimpleNamespace(create_comet_agent=lambda ai_router=None: _FakeComet())
    monkeypatch.setitem(sys.modules, "modules.comet_agent", fake_module)

    processor = VoiceCommandProcessor.__new__(VoiceCommandProcessor)
    processor.ai_router = None

    handled, response = VoiceCommandProcessor._execute_autonomous(
        processor,
        "open notes and then write a checklist",
    )

    assert handled is True
    assert response == "comet completed"
    assert calls["task"] == "open notes and then write a checklist"
    assert calls["cleanup"] is True


def test_specialist_delegation_waits_and_returns_result(monkeypatch):
    class _FakePool:
        def delegate_to_specialist(self, **kwargs):
            assert kwargs["required_capability"] == "flight_booking"
            return "task-123"

    class _FakeHub:
        def __init__(self):
            self.calls = 0

        def get_task_status(self, task_id):
            self.calls += 1
            if self.calls == 1:
                return {"task_id": task_id, "status": "delegated"}
            return {
                "task_id": task_id,
                "status": "completed",
                "result": {"data": "Found 3 good flights."},
            }

    monkeypatch.setattr("modules.ai_command_agent.SPECIALIST_POOL_OK", True)
    monkeypatch.setattr("modules.ai_command_agent.COLLAB_HUB_OK", True)
    monkeypatch.setattr("modules.ai_command_agent.get_specialist_pool", lambda: _FakePool())
    monkeypatch.setattr("modules.ai_command_agent.get_collaboration_hub", lambda: _FakeHub())

    agent = AICommandAgent(
        _DummyProviderManager(),
        _DummyToolRegistry(),
        config={
            "plugin_enabled": False,
            "comet_enabled": False,
            "specialist_wait_enabled": True,
            "specialist_wait_timeout_s": 1.0,
            "specialist_poll_interval_s": 0.0,
        },
    )

    result = agent.try_handle("book a flight to tokyo")

    assert result.handled is True
    assert result.executor_used == "specialist"
    assert result.final_status == "completed"
    assert "Found 3 good flights" in result.response
    assert result.intent_type == "command"


def test_planner_routes_to_plugin_handler(monkeypatch):
    class _FakePluginRegistry:
        def load_all(self):
            return {"demo": True}

        def start_watcher(self):
            return True

        def find_handler(self, query):
            if "workspace" in query.lower():
                return ("demo", "run", lambda _q: "ok")
            return None

        def execute_handler(self, query):
            return f"plugin handled: {query}"

    fake_registry = _FakePluginRegistry()
    monkeypatch.setattr("modules.ai_command_agent.PLUGIN_SYSTEM_OK", True)
    monkeypatch.setattr("modules.ai_command_agent.get_plugin_registry", lambda: fake_registry)

    agent = AICommandAgent(
        _DummyProviderManager(),
        _DummyToolRegistry(),
        config={"plugin_enabled": True, "comet_enabled": False},
    )

    result = agent.try_handle("launch workspace automation")

    assert result.handled is True
    assert result.executor_used == "plugin"
    assert result.final_status == "completed"
    assert "plugin handled" in result.response


def test_planner_routes_multi_step_to_comet(monkeypatch):
    class _FakeComet:
        def execute_task_sync(self, task, max_steps=20):
            assert "and then" in task
            return SimpleNamespace(success=True, message="comet multi-step done")

        def cleanup(self):
            return None

    monkeypatch.setattr("modules.ai_command_agent.COMET_OK", True)
    monkeypatch.setattr("modules.ai_command_agent.create_comet_agent", lambda: _FakeComet())

    agent = AICommandAgent(
        _DummyProviderManager(),
        _DummyToolRegistry(),
        config={"plugin_enabled": False, "comet_enabled": True},
    )

    result = agent.try_handle("open notepad and then create todo.txt")

    assert result.handled is True
    assert result.executor_used == "comet"
    assert result.final_status == "completed"
    assert result.response == "comet multi-step done"


def test_tool_loop_sets_unified_telemetry_fields():
    agent = AICommandAgent(
        _DummyProviderManager(),
        _DummyToolRegistry(),
        config={"plugin_enabled": False, "comet_enabled": False},
    )
    agent._execute = lambda _text, _tier: ("Done via tools", 2, "gpt-test")

    result = agent.try_handle("open calculator")

    assert result.handled is True
    assert result.executor_used == "tool_loop"
    assert result.tool_calls_made == 2
    assert result.tool_count == 2
    assert result.fallback_count == 0
    assert result.intent_type == "command"
    assert result.final_status == "completed"
