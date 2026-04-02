"""Contract tests for auth, chat, and websocket API routes."""

import time
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from modules.api.routers.auth import create_auth_router
from modules.api.routers.chat import create_chat_router
from modules.api.routers.websocket import create_ws_router
from modules.api.routers import websocket as ws_router


class _FakeAIRouter:
    def __init__(self):
        self.current_model = "test-model"
        self.current_backend_name = "test-backend"
        self.last_query = None

    def query(self, message, model=None, use_web_search=False):
        self.last_query = {
            "message": message,
            "model": model,
            "use_web_search": use_web_search,
        }
        return f"echo:{message}"

    def stream_query(self, message):
        yield "part-1"
        yield "part-2"

    def get_status(self):
        return {"backend": "ok"}

    def clear_history(self):
        return None


class _FakePlan:
    def __init__(self, plan_id: str):
        self.plan_id = plan_id

    def to_dict(self):
        return {"plan_id": self.plan_id}


class _FakePlanResult:
    def to_dict(self):
        return {"success": True}


class _FakePlanner:
    def create_plan(self, task: str, context: str):
        return _FakePlan("plan-created")

    def get_plan(self, plan_id: str):
        if plan_id:
            return _FakePlan(plan_id)
        return None

    def execute_plan(self, plan):
        return _FakePlanResult()

    def get_recent_plans(self, count: int):
        return [_FakePlan("plan-1")]

    def cancel(self):
        return None


class _FakeWorkflowResult:
    def __init__(self):
        self.success = True
        self.workflow_name = "wf-sample"
        self.steps_completed = 1
        self.total_steps = 1
        self.duration_seconds = 0.1
        self.error = None


class _FakeWorkflowEngine:
    def list_workflows(self):
        return [{"name": "wf-sample"}]

    def register_workflow(self, name: str, steps):
        return True

    async def execute_workflow(self, name: str, context):
        return _FakeWorkflowResult()


class _FakeTaskController:
    def get_active_tasks(self):
        return {"tasks": [{"execution_id": "task-1"}]}

    def parse_complex_command(self, command: str):
        return {"command": command}

    def execute_task(self, task_def):
        return {"success": True, "execution_id": "task-created"}

    def get_task_status(self, execution_id: str):
        return {"execution_id": execution_id, "status": "running"}

    def pause_task(self, execution_id: str):
        return {"execution_id": execution_id, "success": True}

    def resume_task(self, execution_id: str):
        return {"execution_id": execution_id, "success": True}

    def cancel_task(self, execution_id: str):
        return {"execution_id": execution_id, "success": True}


class _FakeJarvis:
    def __init__(self):
        self.advanced_planner = _FakePlanner()
        self.workflow_engine = _FakeWorkflowEngine()
        self.tasks = _FakeTaskController()


class _FakeState:
    def __init__(self, ai_router=None):
        self._auth_password = "lada-test-password"
        self._session_ttl = 3600
        self._tokens = {}

        self.start_time = datetime.now()
        self.ai_router = ai_router or _FakeAIRouter()
        self.chat_manager = None
        self.jarvis = None
        self.voice_processor = None
        self.agents = {}

        self.ws_connections = {}
        self.ws_sessions = {}
        self.ws_orchestrator_subscribers = set()
        self.ws_orchestrator_subscription_filters = {}
        self.ws_orchestrator_bus_subscription_token = None
        self.ws_orchestrator_event_loop = None
        self.ws_orchestrator_event_callback = None

    def load_components(self):
        return None

    def create_session_token(self):
        token = f"tok-{len(self._tokens) + 1}"
        self._tokens[token] = time.time() + self._session_ttl
        return token

    def validate_session_token(self, token):
        expiry = self._tokens.get(token)
        return bool(expiry and expiry > time.time())

    def invalidate_token(self, token):
        self._tokens.pop(token, None)


def _build_client(*routers):
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return TestClient(app)


def test_auth_login_check_logout_contract():
    state = _FakeState()
    client = _build_client(create_auth_router(state))

    denied = client.post(
        "/auth/login",
        json={"password": "wrong"},
        headers={"X-Request-ID": "auth-denied-req-1"},
    )
    assert denied.status_code == 401

    login = client.post(
        "/auth/login",
        json={"password": state._auth_password},
        headers={"X-Request-ID": "auth-login-req-1"},
    )
    assert login.status_code == 200
    assert login.headers["x-request-id"] == "auth-login-req-1"
    payload = login.json()
    assert payload["success"] is True
    assert isinstance(payload["token"], str) and payload["token"]
    assert payload["expires_in"] == state._session_ttl

    token = payload["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Request-ID": "auth-check-req-1",
    }

    check = client.get("/auth/check", headers=headers)
    assert check.status_code == 200
    assert check.headers["x-request-id"] == "auth-check-req-1"
    assert check.json() == {"valid": True}

    logout = client.post(
        "/auth/logout",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-ID": "auth-logout-req-1",
        },
    )
    assert logout.status_code == 200
    assert logout.headers["x-request-id"] == "auth-logout-req-1"
    assert logout.json()["success"] is True

    after_logout = client.get("/auth/check", headers=headers)
    assert after_logout.status_code == 401


def test_chat_contract_auto_model_and_web_flag():
    state = _FakeState()
    client = _build_client(create_chat_router(state))
    request_id = "chat-contract-req-1"

    response = client.post(
        "/chat",
        json={
            "message": "hello",
            "model": "auto",
            "use_web_search": True,
        },
        headers={"X-Request-ID": request_id},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    payload = response.json()
    assert payload["success"] is True
    assert payload["response"] == "echo:hello"
    assert payload["model"] == "test-model"
    assert state.ai_router.last_query["model"] is None
    assert state.ai_router.last_query["use_web_search"] is True


def test_chat_health_propagates_request_id_header():
    state = _FakeState()
    client = _build_client(create_chat_router(state))

    response = client.get("/health", headers={"X-Request-ID": "chat-health-req-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "chat-health-req-1"
    assert response.json()["status"] == "healthy"


def test_chat_stream_sse_contract_contains_chunks_and_done():
    state = _FakeState()
    client = _build_client(create_chat_router(state))
    request_id = "chat-stream-req-1"

    response = client.post(
        "/chat/stream",
        json={"message": "stream please"},
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"] == request_id

    body = response.text
    assert 'data: {"chunk": "part-1"}' in body
    assert 'data: {"chunk": "part-2"}' in body
    assert f'data: {{"done": true, "request_id": "{request_id}"}}' in body


def test_chat_timeout_returns_504(monkeypatch):
    class _SlowAIRouter(_FakeAIRouter):
        def query(self, message, model=None, use_web_search=False):
            time.sleep(1.2)
            return "late-response"

    monkeypatch.setenv("LADA_API_CHAT_TIMEOUT_SEC", "1")

    state = _FakeState(ai_router=_SlowAIRouter())
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat",
        json={"message": "timeout please"},
        headers={"X-Request-ID": "chat-timeout-req-1"},
    )

    assert response.status_code == 504
    assert response.headers["x-request-id"] == "chat-timeout-req-1"
    assert response.json()["detail"] == "Chat request timed out. Please try again."


def test_chat_stream_sanitizes_error_payload():
    sensitive_key = "gsk_" + ("a" * 50)

    class _ExplodingStreamAIRouter(_FakeAIRouter):
        def stream_query(self, message):
            raise RuntimeError(f"provider failed with key {sensitive_key}")

    state = _FakeState(ai_router=_ExplodingStreamAIRouter())
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat/stream",
        json={"message": "trigger stream error"},
        headers={"X-Request-ID": "chat-stream-error-req-1"},
    )

    assert response.status_code == 200
    body = response.text
    assert sensitive_key not in body
    assert '"status_code": 500' in body
    assert '"request_id": "chat-stream-error-req-1"' in body


def test_agent_not_found_preserves_404_and_request_id_header():
    state = _FakeState()
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/agent",
        json={"agent": "missing", "action": "run", "params": {}},
        headers={"X-Request-ID": "agent-missing-req-1"},
    )

    assert response.status_code == 404
    assert response.headers["x-request-id"] == "agent-missing-req-1"
    assert "not found" in response.json()["detail"].lower()


def test_websocket_rejects_invalid_token(monkeypatch):
    state = _FakeState()
    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws?token=invalid"):
            pass
    assert excinfo.value.code == 4001


def test_websocket_ping_pong_and_size_limit(monkeypatch):
    state = _FakeState()
    token = state.create_session_token()
    ws_request_id = "ws-contract-req-1"

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    monkeypatch.setattr(ws_router, "WS_MAX_MESSAGE_SIZE", 24)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}", headers={"X-Request-ID": ws_request_id}) as ws:
        connected = ws.receive_json()
        assert connected["type"] == "system.connected"
        assert "session_id" in connected["data"]
        assert connected["data"]["request_id"] == ws_request_id

        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        assert pong["data"]["request_id"] == ws_request_id

        ws.send_text("x" * 50)
        oversized = ws.receive_json()
        assert oversized["type"] == "error"
        assert "Message too large" in oversized["data"]["message"]


def test_websocket_chat_error_sanitizes_sensitive_details(monkeypatch):
    sensitive_key = "gsk_" + ("b" * 50)

    class _ExplodingStreamAIRouter(_FakeAIRouter):
        def stream_query(self, message, model=None, use_web_search=False):
            raise RuntimeError(f"stream failed with key {sensitive_key}")

    state = _FakeState(ai_router=_ExplodingStreamAIRouter())
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "chat",
                "id": "msg-1",
                "request_id": "ws-chat-error-req-1",
                "data": {"message": "trigger", "stream": True},
            }
        )

        frames = []
        for _ in range(4):
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == "chat.error":
                break

    error_frame = next((f for f in frames if f.get("type") == "chat.error"), None)
    assert error_frame is not None
    assert sensitive_key not in error_frame["data"]["message"]
    assert error_frame["data"]["request_id"] == "ws-chat-error-req-1"


def test_websocket_system_frames_propagate_request_id(monkeypatch):
    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "system",
                "id": "sys-1",
                "request_id": "ws-system-req-1",
                "data": {"action": "status"},
            }
        )
        status_frame = ws.receive_json()
        assert status_frame["type"] == "system.status"
        assert status_frame["data"]["request_id"] == "ws-system-req-1"

        ws.send_json(
            {
                "type": "system",
                "id": "sys-2",
                "request_id": "ws-system-req-2",
                "data": {"action": "models"},
            }
        )
        models_frame = ws.receive_json()
        assert models_frame["type"] == "system.models"
        assert models_frame["data"]["request_id"] == "ws-system-req-2"


def test_websocket_plan_workflow_task_frames_propagate_request_id(monkeypatch):
    state = _FakeState()
    state.jarvis = _FakeJarvis()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "plan",
                "id": "plan-1",
                "request_id": "ws-plan-req-1",
                "data": {"action": "list", "count": 1},
            }
        )
        plan_frame = ws.receive_json()
        assert plan_frame["type"] == "plan.list"
        assert plan_frame["data"]["request_id"] == "ws-plan-req-1"

        ws.send_json(
            {
                "type": "workflow",
                "id": "wf-1",
                "request_id": "ws-workflow-req-1",
                "data": {"action": "list"},
            }
        )
        workflow_frame = ws.receive_json()
        assert workflow_frame["type"] == "workflow.list"
        assert workflow_frame["data"]["request_id"] == "ws-workflow-req-1"

        ws.send_json(
            {
                "type": "task",
                "id": "task-1",
                "request_id": "ws-task-req-1",
                "data": {"action": "list"},
            }
        )
        task_frame = ws.receive_json()
        assert task_frame["type"] == "task.list"
        assert task_frame["data"]["request_id"] == "ws-task-req-1"


def test_voice_direct_unauthorized_preserves_401():
    state = _FakeState()
    client = _build_client(create_chat_router(state))

    response = client.post("/api/voice/direct", json={"command": "hello"})

    assert response.status_code == 401