"""Tests for orchestrator subscription observability endpoint."""

from types import SimpleNamespace
from typing import Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.orchestration import create_orchestration_router


class _FakeState:
    def __init__(self):
        self._standalone_orchestrator_enabled = True
        self.orchestrator = object()

        self.ws_orchestrator_subscribers = set()
        self.ws_orchestrator_subscription_filters = {}
        self.ws_orchestrator_bus_subscription_token = None

        self.ws_sessions = {}
        self.ws_connections = {}

    def load_components(self):
        return None


def _build_client(state: _FakeState) -> TestClient:
    app = FastAPI()
    app.include_router(create_orchestration_router(state))
    return TestClient(app)


def test_orchestrator_subscriptions_endpoint_returns_session_details():
    state = _FakeState()
    state.ws_orchestrator_subscribers = {"sess-a", "sess-b"}
    state.ws_orchestrator_subscription_filters = {
        "sess-a": {
            "event_types": {"command.completed", "command.failed"},
            "targets": {"system"},
            "correlation_ids": {"corr-1"},
        },
    }
    state.ws_orchestrator_bus_subscription_token = "tok-1"
    state.ws_connections = {"sess-a": object()}
    state.ws_sessions = {
        "sess-a": {
            "orchestrator_events": True,
            "messages_sent": 5,
            "messages_received": 3,
            "last_activity": 1234.5,
        },
        "sess-b": {
            "orchestrator_events": False,
            "messages_sent": 0,
            "messages_received": 1,
            "last_activity": 999.1,
        },
    }

    client = _build_client(state)
    response = client.get(
        "/orchestrator/subscriptions",
        headers={"X-Request-ID": "orchestrator-subs-req-1"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "orchestrator-subs-req-1"
    payload = response.json()

    assert payload["enabled"] is True
    assert payload["orchestrator_available"] is True
    assert payload["stream_active"] is True
    assert payload["subscriber_count"] == 2
    assert "sessions" in payload
    assert len(payload["sessions"]) == 2

    sessions_by_id = {entry["session_id"]: entry for entry in payload["sessions"]}

    assert sessions_by_id["sess-a"]["connected"] is True
    assert sessions_by_id["sess-a"]["orchestrator_events"] is True
    assert sessions_by_id["sess-a"]["messages_sent"] == 5
    assert sessions_by_id["sess-a"]["messages_received"] == 3
    assert sessions_by_id["sess-a"]["filters"]["targets"] == ["system"]
    assert sessions_by_id["sess-a"]["filters"]["correlation_ids"] == ["corr-1"]
    assert sessions_by_id["sess-a"]["filters"]["event_types"] == [
        "command.completed",
        "command.failed",
    ]

    assert sessions_by_id["sess-b"]["connected"] is False
    assert sessions_by_id["sess-b"]["filters"] == {}


def test_orchestrator_subscriptions_endpoint_can_skip_session_dump():
    state = _FakeState()
    state._standalone_orchestrator_enabled = False
    state.orchestrator = None
    state.ws_orchestrator_subscribers = {"sess-a"}

    client = _build_client(state)
    response = client.get(
        "/orchestrator/subscriptions",
        params={"include_sessions": "false"},
        headers={"X-Request-ID": "orchestrator-skip-req-1"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "orchestrator-skip-req-1"
    payload = response.json()

    assert payload["enabled"] is False
    assert payload["orchestrator_available"] is False
    assert payload["stream_active"] is False
    assert payload["subscriber_count"] == 1
    assert "sessions" not in payload


def test_create_plan_sanitizes_internal_error():
    sensitive_key = "sk-" + ("x" * 48)

    class _FailingPlanner:
        def create_plan(self, task, context):
            raise RuntimeError(f"planner failed with token {sensitive_key}")

    class _Jarvis:
        def __init__(self):
            self.advanced_planner = _FailingPlanner()

    state = _FakeState()
    state.jarvis = _Jarvis()

    client = _build_client(state)
    response = client.post("/plans", json={"task": "test task"})

    assert response.status_code == 500
    detail = response.json().get("detail", "")
    assert sensitive_key not in detail


def test_legacy_list_routes_use_registry_payloads_when_available(monkeypatch):
    class _FakeRegistryTask:
        def __init__(self, task_id: str, name: str, status: str, progress: float = 0.0):
            self._data = {
                "id": task_id,
                "name": name,
                "status": status,
                "progress": progress,
                "current_step_index": 1,
                "steps": [{"id": "step-1"}, {"id": "step-2"}],
                "started_at": "2026-04-19T10:00:00",
                "completed_at": None,
                "error": None,
            }

        def to_dict(self):
            return dict(self._data)

    class _FakeRegistry:
        def list_tasks(self, active_only=False):
            if active_only:
                return [_FakeRegistryTask("task-reg-1", "Registry Active Task", "running", 0.5)]
            return []

        def get_history(self, limit=20):
            return [
                {
                    "id": "task-reg-2",
                    "name": "Registry Completed Task",
                    "status": "completed",
                    "started_at": "2026-04-19T09:00:00",
                    "completed_at": "2026-04-19T09:01:00",
                    "error": None,
                }
            ]

    class _FakeFlow:
        def __init__(self):
            self.id = "flow-reg-1"

        def to_dict(self):
            return {
                "id": "flow-reg-1",
                "name": "Registry Flow",
                "total_steps": 2,
                "status": "pending",
            }

    class _FakeFlowRegistry:
        def list_flows(self):
            return [_FakeFlow()]

        def get_task(self, flow_id):
            return SimpleNamespace(steps=[SimpleNamespace(action="open_url"), SimpleNamespace(action="extract_text")])

    monkeypatch.setattr("modules.tasks.get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr("modules.tasks.get_flow_registry", lambda: _FakeFlowRegistry())

    state = _FakeState()
    state.jarvis = None
    client = _build_client(state)

    tasks_response = client.get("/tasks")
    assert tasks_response.status_code == 200
    tasks_payload = tasks_response.json()
    assert tasks_payload["active_count"] == 1
    assert tasks_payload["completed_count"] == 1
    assert tasks_payload["active"][0]["execution_id"] == "task-reg-1"
    assert tasks_payload["completed"][0]["execution_id"] == "task-reg-2"

    workflows_response = client.get("/workflows")
    assert workflows_response.status_code == 200
    workflows_payload = workflows_response.json()
    assert workflows_payload["count"] == 1
    assert workflows_payload["workflows"][0]["name"] == "Registry Flow"
    assert workflows_payload["workflows"][0]["source"] == "registry"


def test_legacy_task_lifecycle_routes_fallback_to_registry(monkeypatch):
    class _FakeRegistryTask:
        def __init__(self, task_id: str, status: str = "paused", resume_token: Optional[str] = "resume-1"):
            self.id = task_id
            self.status = SimpleNamespace(value=status)
            self.resume_token = resume_token
            self._status = status

        def to_dict(self):
            return {
                "id": self.id,
                "name": "Registry Lifecycle Task",
                "status": self._status,
                "progress": 0.25,
                "current_step_index": 1,
                "steps": [{"id": "step-1"}, {"id": "step-2"}],
                "started_at": "2026-04-19T11:00:00",
                "completed_at": None,
                "error": None,
                "result": None,
            }

    class _FakeRegistry:
        def __init__(self):
            self._task = _FakeRegistryTask("task-reg-lifecycle")

        def get(self, task_id):
            if task_id == "task-reg-lifecycle":
                return self._task
            return None

        def pause(self, task_id):
            if task_id != "task-reg-lifecycle":
                return None
            self._task._status = "paused"
            self._task.status = SimpleNamespace(value="paused")
            self._task.resume_token = "resume-1"
            return "resume-1"

        def resume(self, token):
            if token == "resume-1":
                self._task._status = "running"
                self._task.status = SimpleNamespace(value="running")
                self._task.resume_token = None
                return self._task
            return None

        def cancel(self, task_id, reason=None):
            if task_id != "task-reg-lifecycle":
                return False
            self._task._status = "cancelled"
            self._task.status = SimpleNamespace(value="cancelled")
            return True

    fake_registry = _FakeRegistry()
    monkeypatch.setattr("modules.tasks.get_registry", lambda: fake_registry)

    state = _FakeState()
    state.jarvis = None
    client = _build_client(state)

    status_response = client.get("/tasks/task-reg-lifecycle")
    assert status_response.status_code == 200
    assert status_response.json()["execution_id"] == "task-reg-lifecycle"

    pause_response = client.post("/tasks/task-reg-lifecycle/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["resume_token"] == "resume-1"

    resume_response = client.post("/tasks/task-reg-lifecycle/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "running"

    cancel_response = client.post("/tasks/task-reg-lifecycle/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
