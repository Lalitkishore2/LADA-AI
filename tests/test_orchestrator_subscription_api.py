"""Tests for orchestrator subscription observability endpoint."""

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
