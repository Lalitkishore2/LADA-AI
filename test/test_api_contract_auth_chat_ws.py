"""Contract tests for auth, chat, and websocket API routes."""

import time
from datetime import datetime
from types import SimpleNamespace

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
        self.last_stream_query = None

    def query(self, message, model=None, use_web_search=False):
        self.last_query = {
            "message": message,
            "model": model,
            "use_web_search": use_web_search,
        }
        return f"echo:{message}"

    def stream_query(self, message, model=None, use_web_search=False):
        self.last_stream_query = {
            "message": message,
            "model": model,
            "use_web_search": use_web_search,
        }
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

    def process(self, command: str):
        cmd = (command or "").lower().strip()
        if cmd.startswith("open ") or cmd.startswith("run "):
            return True, "Command executed."
        return False, ""


class _FakeChatManager:
    def __init__(self):
        self._counter = 0
        self.conversations = {}

    def _next_id(self) -> str:
        self._counter += 1
        return f"conv-{self._counter}"

    def add_message(self, conversation_id: str, role: str, content: str, **kwargs):
        conv_id = (conversation_id or "").strip() or self._next_id()
        conv = self.conversations.setdefault(conv_id, {"id": conv_id, "messages": []})
        conv["messages"].append(
            {
                "role": role,
                "content": content,
                "model_used": kwargs.get("model_used"),
                "sources": kwargs.get("sources", []),
            }
        )
        return SimpleNamespace(id=conv_id)


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


class _JwtStyleFakeState(_FakeState):
    def create_session_token(self):
        raw = super().create_session_token()
        return f"header.payload.{raw}"

    def validate_session_token(self, token):
        if isinstance(token, str) and token.count(".") == 2:
            base = token.split(".")[-1]
            return super().validate_session_token(base)
        return super().validate_session_token(token)

    def invalidate_token(self, token):
        if isinstance(token, str) and token.count(".") == 2:
            base = token.split(".")[-1]
            return super().invalidate_token(base)
        return super().invalidate_token(token)


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


def test_auth_accepts_lowercase_bearer_scheme():
    state = _FakeState()
    client = _build_client(create_auth_router(state))

    login = client.post(
        "/auth/login",
        json={"password": state._auth_password},
        headers={"X-Request-ID": "auth-login-lower-bearer-req-1"},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    check = client.get(
        "/auth/check",
        headers={
            "Authorization": f"bearer {token}",
            "X-Request-ID": "auth-check-lower-bearer-req-1",
        },
    )
    assert check.status_code == 200
    assert check.json() == {"valid": True}

    logout = client.post(
        "/auth/logout",
        headers={
            "Authorization": f"bearer {token}",
            "X-Request-ID": "auth-logout-lower-bearer-req-1",
        },
    )
    assert logout.status_code == 200

    after_logout = client.get(
        "/auth/check",
        headers={
            "Authorization": f"bearer {token}",
            "X-Request-ID": "auth-check-lower-bearer-after-logout-req-1",
        },
    )
    assert after_logout.status_code == 401


def test_voice_direct_accepts_lowercase_bearer_scheme(monkeypatch):
    monkeypatch.setenv("LADA_API_KEY", "voice-direct-key")

    state = _FakeState()
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/api/voice/direct",
        json={"command": "what time is it?", "source": "webhook"},
        headers={
            "Authorization": "bearer voice-direct-key",
            "X-Request-ID": "voice-direct-lower-bearer-req-1",
        },
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "voice-direct-lower-bearer-req-1"
    payload = response.json()
    assert payload["success"] is True
    assert payload["voice_response"] == "echo:what time is it?"


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


def test_chat_supports_legacy_query_signature_without_optional_kwargs():
    class _LegacyQueryAIRouter:
        def __init__(self):
            self.current_model = "legacy-model"
            self.current_backend_name = "legacy-backend"
            self.last_message = None

        def query(self, message):
            self.last_message = message
            return f"legacy:{message}"

        def get_status(self):
            return {"backend": "legacy"}

        def clear_history(self):
            return None

    state = _FakeState(ai_router=_LegacyQueryAIRouter())
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat",
        json={
            "message": "legacy hello",
            "model": "gpt-5",
            "use_web_search": True,
        },
        headers={"X-Request-ID": "chat-legacy-query-req-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["response"] == "legacy:legacy hello"
    assert payload["model"] == "legacy-model"
    assert state.ai_router.last_message == "legacy hello"


def test_chat_stream_supports_legacy_query_signature_without_optional_kwargs():
    class _LegacyQueryAIRouter:
        def __init__(self):
            self.current_model = "legacy-model"
            self.current_backend_name = "legacy-backend"
            self.last_message = None

        def query(self, message):
            self.last_message = message
            return f"legacy:{message}"

        def get_status(self):
            return {"backend": "legacy"}

        def clear_history(self):
            return None

    state = _FakeState(ai_router=_LegacyQueryAIRouter())
    client = _build_client(create_chat_router(state))
    request_id = "chat-stream-legacy-query-req-1"

    response = client.post(
        "/chat/stream",
        json={
            "message": "legacy stream",
            "model": "gpt-5",
            "use_web_search": True,
        },
        headers={"X-Request-ID": request_id},
    )

    assert response.status_code == 200
    body = response.text
    assert '"type": "chat.chunk"' in body
    assert '"chunk": "legacy:legacy stream"' in body
    assert f'"request_id": "{request_id}"' in body
    assert state.ai_router.last_message == "legacy stream"


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
    assert 'data: {"type": "chat.chunk", "data": {"chunk": "part-1", "request_id": "chat-stream-req-1"}}' in body
    assert 'data: {"type": "chat.chunk", "data": {"chunk": "part-2", "request_id": "chat-stream-req-1"}}' in body
    assert f'data: {{"type": "chat.done", "data": {{"done": true, "request_id": "{request_id}"}}}}' in body


def test_chat_stream_forwards_model_and_web_flag():
    state = _FakeState()
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat/stream",
        json={
            "message": "stream with model",
            "model": "gpt-4o-mini",
            "use_web_search": True,
        },
        headers={"X-Request-ID": "chat-stream-model-req-1"},
    )

    assert response.status_code == 200
    assert state.ai_router.last_stream_query == {
        "message": "stream with model",
        "model": "gpt-4o-mini",
        "use_web_search": True,
    }


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


def test_chat_stream_sse_passes_through_dict_chunk_metadata():
    class _MetadataStreamAIRouter(_FakeAIRouter):
        def stream_query(self, message):
            yield {"chunk": "part-1", "source": "provider", "done": False, "metadata": {"phase": "one"}}
            yield {
                "chunk": "",
                "source": "error",
                "done": True,
                "metadata": {
                    "error": "All providers unavailable or rate limited",
                    "providers_tried": ["provider"],
                },
            }

    state = _FakeState(ai_router=_MetadataStreamAIRouter())
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat/stream",
        json={"message": "stream please"},
        headers={"X-Request-ID": "chat-stream-meta-req-1"},
    )

    assert response.status_code == 200
    body = response.text
    assert '"type": "chat.chunk"' in body
    assert '"chunk": "part-1"' in body
    assert '"metadata": {"phase": "one"}' in body
    assert '"type": "chat.done"' in body
    assert '"providers_tried": ["provider"]' in body
    assert '"request_id": "chat-stream-meta-req-1"' in body


def test_chat_routes_system_command_to_jarvis():
    state = _FakeState()
    state.jarvis = _FakeJarvis()
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat",
        json={"message": "open calculator"},
        headers={"X-Request-ID": "chat-system-req-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["response"] == "Command executed."
    assert payload["model"] == "system-command"


def test_chat_stream_routes_system_command_to_jarvis():
    state = _FakeState()
    state.jarvis = _FakeJarvis()
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/chat/stream",
        json={"message": "open notepad"},
        headers={"X-Request-ID": "chat-stream-system-req-1"},
    )

    assert response.status_code == 200
    body = response.text
    assert '"is_system_command": true' in body
    assert '"type": "chat.done"' in body
    assert '"request_id": "chat-stream-system-req-1"' in body


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


def test_agent_process_allows_non_dict_result_payload():
    class _StringResultAgent:
        def process(self, _query: str):
            return "done"

    state = _FakeState()
    state.agents["demo"] = _StringResultAgent()
    client = _build_client(create_chat_router(state))

    response = client.post(
        "/agent",
        json={"agent": "demo", "action": "run", "params": {"query": "hello"}},
        headers={"X-Request-ID": "agent-string-result-req-1"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "agent-string-result-req-1"
    payload = response.json()
    assert payload["success"] is True
    assert payload["result"] == "done"


def test_websocket_rejects_invalid_token(monkeypatch):
    state = _FakeState()
    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws?token=invalid"):
            pass
    assert excinfo.value.code == 4001
    assert sum(ws_router._connections_per_ip.values()) == 0


def test_websocket_invalid_handshake_cleans_connection_tracking(monkeypatch):
    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    monkeypatch.setattr(ws_router, "WS_PROTOCOL_ENABLED", True)
    monkeypatch.setattr(ws_router, "WS_PROTOCOL_HANDSHAKE_TIMEOUT", 5)
    monkeypatch.setattr(ws_router, "_get_protocol_validator", lambda: object())
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(f"/ws?token={token}") as ws:
            ws.send_text("{not-json")
            error_frame = ws.receive_json()
            assert error_frame["type"] == "error"
            assert "Invalid JSON in handshake" in error_frame["data"]["message"]
            ws.receive_json()

    assert excinfo.value.code == 4003
    assert state.ws_connections == {}
    assert state.ws_sessions == {}
    assert sum(ws_router._connections_per_ip.values()) == 0


def test_websocket_protocol_reject_handshake_cleans_connection_tracking(monkeypatch):
    class _HandshakeError:
        message = "Protocol rejected"

    class _HandshakeRejectResponse:
        success = False
        error = _HandshakeError()

        def to_dict(self):
            return {
                "type": "error",
                "error": {"message": self.error.message},
            }

    class _RejectingValidator:
        def validate_connect(self, _payload):
            return _HandshakeRejectResponse(), None

        def remove_session(self, _session_id):
            return None

    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    monkeypatch.setattr(ws_router, "WS_PROTOCOL_ENABLED", True)
    monkeypatch.setattr(ws_router, "WS_PROTOCOL_HANDSHAKE_TIMEOUT", 5)
    monkeypatch.setattr(ws_router, "_get_protocol_validator", lambda: _RejectingValidator())
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_json({"type": "connect", "protocol_version": "1.0"})
        error_frame = ws.receive_json()
        assert error_frame["type"] == "error"
        assert error_frame["error"]["message"] == "Protocol rejected"

        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 4003

    assert state.ws_connections == {}
    assert state.ws_sessions == {}
    assert sum(ws_router._connections_per_ip.values()) == 0


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


def test_websocket_accepts_bearer_token_header(monkeypatch):
    state = _JwtStyleFakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "ws-auth-header-req-1"},
    ) as ws:
        connected = ws.receive_json()
        assert connected["type"] == "system.connected"
        assert connected["data"]["request_id"] == "ws-auth-header-req-1"


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


def test_websocket_chat_stream_propagates_metadata(monkeypatch):
    class _MetadataStreamAIRouter(_FakeAIRouter):
        def stream_query(self, message, model=None, use_web_search=False):
            yield {
                "chunk": "partial",
                "source": "provider",
                "done": False,
                "metadata": {"phase": "streaming"},
            }
            yield {
                "chunk": "",
                "source": "error",
                "done": True,
                "metadata": {
                    "error": "All providers unavailable or rate limited",
                    "providers_tried": ["provider"],
                },
            }

    state = _FakeState(ai_router=_MetadataStreamAIRouter())
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "chat",
                "id": "msg-meta-1",
                "request_id": "ws-chat-meta-req-1",
                "data": {"message": "trigger", "stream": True},
            }
        )

        chat_start = ws.receive_json()
        chat_chunk = ws.receive_json()
        chat_done = ws.receive_json()

    assert chat_start["type"] == "chat.start"
    assert chat_chunk["type"] == "chat.chunk"
    assert chat_chunk["data"]["chunk"] == "partial"
    assert chat_chunk["data"]["metadata"] == {"phase": "streaming"}
    assert chat_chunk["data"]["request_id"] == "ws-chat-meta-req-1"

    assert chat_done["type"] == "chat.done"
    assert chat_done["data"]["metadata"]["error"] == "All providers unavailable or rate limited"
    assert chat_done["data"]["metadata"]["providers_tried"] == ["provider"]
    assert chat_done["data"]["request_id"] == "ws-chat-meta-req-1"


def test_websocket_chat_stream_done_uses_metadata_error_when_content_empty(monkeypatch):
    class _DoneOnlyMetadataStreamAIRouter(_FakeAIRouter):
        def stream_query(self, message, model=None, use_web_search=False):
            yield {
                "chunk": "",
                "source": "error",
                "done": True,
                "metadata": {"error": "Local model is offline"},
            }

    state = _FakeState(ai_router=_DoneOnlyMetadataStreamAIRouter())
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected
        ws.send_json(
            {
                "type": "chat",
                "id": "msg-meta-2",
                "request_id": "ws-chat-meta-req-2",
                "data": {"message": "trigger", "stream": True},
            }
        )

        chat_start = ws.receive_json()
        chat_done = ws.receive_json()

    assert chat_start["type"] == "chat.start"
    assert chat_done["type"] == "chat.done"
    assert chat_done["data"]["content"] == "Local model is offline"
    assert chat_done["data"]["metadata"]["error"] == "Local model is offline"
    assert chat_done["data"]["request_id"] == "ws-chat-meta-req-2"


def test_websocket_chat_persists_history_with_conversation_id(monkeypatch):
    state = _FakeState()
    state.chat_manager = _FakeChatManager()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected
        ws.send_json(
            {
                "type": "chat",
                "id": "msg-conv-1",
                "request_id": "ws-chat-conv-req-1",
                "data": {"message": "remember this", "stream": True},
            }
        )

        chat_start = ws.receive_json()
        chunk_1 = ws.receive_json()
        chunk_2 = ws.receive_json()
        chat_done = ws.receive_json()

    assert chat_start["type"] == "chat.start"
    assert chunk_1["type"] == "chat.chunk"
    assert chunk_2["type"] == "chat.chunk"
    assert chat_done["type"] == "chat.done"
    assert chat_done["data"]["request_id"] == "ws-chat-conv-req-1"
    conversation_id = chat_done["data"]["conversation_id"]
    assert conversation_id

    stored_messages = state.chat_manager.conversations[conversation_id]["messages"]
    assert [entry["role"] for entry in stored_messages] == ["user", "assistant"]
    assert stored_messages[0]["content"] == "remember this"
    assert stored_messages[1]["content"] == "part-1part-2"


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


def test_websocket_workflow_and_task_list_use_registry_when_jarvis_missing(monkeypatch):
    class _FakeFlow:
        def __init__(self):
            self.id = "flow-reg-1"

        def to_dict(self):
            return {
                "id": "flow-reg-1",
                "name": "Registry Flow WS",
                "total_steps": 2,
                "status": "pending",
            }

    class _FakeFlowRegistry:
        def list_flows(self):
            return [_FakeFlow()]

        def get_task(self, flow_id):
            return SimpleNamespace(steps=[SimpleNamespace(action="open_url"), SimpleNamespace(action="extract_text")])

    class _FakeRegistryTask:
        def to_dict(self):
            return {
                "id": "task-reg-1",
                "name": "Registry Task WS",
                "status": "running",
                "progress": 0.5,
                "current_step_index": 1,
                "steps": [{"id": "step-1"}, {"id": "step-2"}],
                "started_at": "2026-04-19T12:00:00",
                "completed_at": None,
                "error": None,
                "result": None,
            }

    class _FakeRegistry:
        def list_tasks(self, active_only=False):
            if active_only:
                return [_FakeRegistryTask()]
            return []

    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr("modules.tasks.get_flow_registry", lambda: _FakeFlowRegistry())
    monkeypatch.setattr("modules.tasks.get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "workflow",
                "id": "wf-reg-1",
                "request_id": "ws-reg-workflow-req-1",
                "data": {"action": "list"},
            }
        )
        workflow_frame = ws.receive_json()
        assert workflow_frame["type"] == "workflow.list"
        assert workflow_frame["data"]["request_id"] == "ws-reg-workflow-req-1"
        assert workflow_frame["data"]["workflows"][0]["source"] == "registry"

        ws.send_json(
            {
                "type": "task",
                "id": "task-reg-1",
                "request_id": "ws-reg-task-req-1",
                "data": {"action": "list"},
            }
        )
        task_frame = ws.receive_json()
        assert task_frame["type"] == "task.list"
        assert task_frame["data"]["request_id"] == "ws-reg-task-req-1"
        assert task_frame["data"]["active_tasks"][0]["execution_id"] == "task-reg-1"


def test_websocket_task_lifecycle_routes_fallback_to_registry_when_jarvis_missing(monkeypatch):
    class _FakeRegistryTask:
        def __init__(self):
            self.id = "task-reg-lifecycle"
            self.resume_token = "resume-token-1"
            self.status = SimpleNamespace(value="paused")
            self._status = "paused"

        def to_dict(self):
            return {
                "id": self.id,
                "name": "Registry Lifecycle WS Task",
                "status": self._status,
                "progress": 0.2,
                "current_step_index": 1,
                "steps": [{"id": "step-1"}, {"id": "step-2"}],
                "started_at": "2026-04-19T12:30:00",
                "completed_at": None,
                "error": None,
                "result": None,
            }

    class _FakeRegistry:
        def __init__(self):
            self.task = _FakeRegistryTask()

        def get(self, task_id):
            if task_id == self.task.id:
                return self.task
            return None

        def pause(self, task_id):
            if task_id != self.task.id:
                return None
            self.task._status = "paused"
            self.task.status = SimpleNamespace(value="paused")
            self.task.resume_token = "resume-token-1"
            return "resume-token-1"

        def resume(self, token):
            if token == "resume-token-1":
                self.task._status = "running"
                self.task.status = SimpleNamespace(value="running")
                self.task.resume_token = None
                return self.task
            return None

        def cancel(self, task_id, reason=None):
            if task_id != self.task.id:
                return False
            self.task._status = "cancelled"
            self.task.status = SimpleNamespace(value="cancelled")
            return True

    fake_registry = _FakeRegistry()
    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr("modules.tasks.get_registry", lambda: fake_registry)
    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "task",
                "id": "task-status-1",
                "request_id": "ws-task-status-reg-1",
                "data": {"action": "status", "execution_id": "task-reg-lifecycle"},
            }
        )
        status_frame = ws.receive_json()
        assert status_frame["type"] == "task.status"
        assert status_frame["data"]["request_id"] == "ws-task-status-reg-1"
        assert status_frame["data"]["execution_id"] == "task-reg-lifecycle"

        ws.send_json(
            {
                "type": "task",
                "id": "task-pause-1",
                "request_id": "ws-task-pause-reg-1",
                "data": {"action": "pause", "execution_id": "task-reg-lifecycle"},
            }
        )
        pause_frame = ws.receive_json()
        assert pause_frame["type"] == "task.paused"
        assert pause_frame["data"]["request_id"] == "ws-task-pause-reg-1"
        assert pause_frame["data"]["resume_token"] == "resume-token-1"

        ws.send_json(
            {
                "type": "task",
                "id": "task-resume-1",
                "request_id": "ws-task-resume-reg-1",
                "data": {"action": "resume", "execution_id": "task-reg-lifecycle"},
            }
        )
        resume_frame = ws.receive_json()
        assert resume_frame["type"] == "task.resumed"
        assert resume_frame["data"]["request_id"] == "ws-task-resume-reg-1"
        assert resume_frame["data"]["status"] == "running"

        ws.send_json(
            {
                "type": "task",
                "id": "task-cancel-1",
                "request_id": "ws-task-cancel-reg-1",
                "data": {"action": "cancel", "execution_id": "task-reg-lifecycle"},
            }
        )
        cancel_frame = ws.receive_json()
        assert cancel_frame["type"] == "task.cancelled"
        assert cancel_frame["data"]["request_id"] == "ws-task-cancel-reg-1"
        assert cancel_frame["data"]["status"] == "cancelled"


def test_agent_websocket_rpc_navigate_blocks_internal_url(monkeypatch):
    class _FakeBrowser:
        def navigate(self, url):
            return {"success": True, "url": url, "title": "ok"}

        def click(self, selector, by="css"):
            return {"success": True}

        def type_text(self, selector, text, by="css"):
            return {"success": True}

        def scroll(self, direction="down", amount=500):
            return {"success": True}

    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    import modules.stealth_browser as stealth_browser_mod
    monkeypatch.setattr(stealth_browser_mod, "get_stealth_browser", lambda: _FakeBrowser())

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/agent?token={token}") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "agent.connected"

        ws.send_json(
            {
                "id": "agent-1",
                "request_id": "agent-rpc-req-1",
                "data": {"action": "navigate", "url": "chrome://settings"},
            }
        )
        blocked = ws.receive_json()
        assert blocked["type"] == "agent.rpc.error"
        assert "Blocked or invalid URL" in blocked["data"]["message"]
        assert blocked["data"]["request_id"] == "agent-rpc-req-1"


def test_agent_websocket_rpc_click_success(monkeypatch):
    class _FakeBrowser:
        def navigate(self, url):
            return {"success": True, "url": url}

        def click(self, selector, by="css"):
            return {"success": True, "selector": selector, "by": by}

        def type_text(self, selector, text, by="css"):
            return {"success": True}

        def scroll(self, direction="down", amount=500):
            return {"success": True}

    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    import modules.stealth_browser as stealth_browser_mod
    monkeypatch.setattr(stealth_browser_mod, "get_stealth_browser", lambda: _FakeBrowser())

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/agent?token={token}") as ws:
        ws.receive_json()  # agent.connected
        ws.send_json(
            {
                "id": "agent-2",
                "request_id": "agent-rpc-req-2",
                "data": {"action": "click", "selector": "#submit", "by": "css"},
            }
        )
        done = ws.receive_json()
        assert done["type"] == "agent.rpc.done"
        assert done["data"]["success"] is True
        assert done["data"]["action"] == "click"
        assert done["data"]["request_id"] == "agent-rpc-req-2"


def test_agent_websocket_accepts_bearer_token_header(monkeypatch):
    class _FakeBrowser:
        def navigate(self, url):
            return {"success": True, "url": url}

        def click(self, selector, by="css"):
            return {"success": True, "selector": selector, "by": by}

        def type_text(self, selector, text, by="css"):
            return {"success": True}

        def scroll(self, direction="down", amount=500):
            return {"success": True}

    state = _JwtStyleFakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    import modules.stealth_browser as stealth_browser_mod
    monkeypatch.setattr(stealth_browser_mod, "get_stealth_browser", lambda: _FakeBrowser())

    client = _build_client(create_ws_router(state))
    with client.websocket_connect("/agent", headers={"Authorization": f"Bearer {token}"}) as ws:
        connected = ws.receive_json()
        assert connected["type"] == "agent.connected"


def test_ws_openclaw_event_envelope_maps_to_internal_system(monkeypatch):
    class _FakeBrowser:
        def navigate(self, url):
            return {"success": True, "url": url}

        def click(self, selector, by="css"):
            return {"success": True, "selector": selector, "by": by}

        def type_text(self, selector, text, by="css"):
            return {"success": True, "selector": selector, "text": text, "by": by}

        def scroll(self, direction="down", amount=500):
            return {"success": True, "direction": direction, "amount": amount}

    state = _FakeState()
    token = state.create_session_token()

    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    import modules.stealth_browser as stealth_browser_mod
    monkeypatch.setattr(stealth_browser_mod, "get_stealth_browser", lambda: _FakeBrowser())

    client = _build_client(create_ws_router(state))
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.connected

        ws.send_json(
            {
                "type": "openclaw.event",
                "id": "oc-ws-1",
                "request_id": "oc-ws-req-1",
                "data": {
                    "event_type": "system.command",
                    "payload": {"action": "status"},
                },
            }
        )

        done = ws.receive_json()
        assert done["type"] == "system.status"
        assert done["data"]["request_id"] == "oc-ws-req-1"


def test_acp_websocket_session_setup_failure_cleans_connection_tracking(monkeypatch):
    class _BrokenACPServer:
        def create_session(self, **kwargs):
            raise RuntimeError("acp session boom")

        async def handle_request(self, session_id, request):
            return {"jsonrpc": "2.0", "result": {}, "id": None}

        def close_session(self, session_id):
            return True

    state = _FakeState()
    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()
    monkeypatch.setattr("modules.acp_bridge.get_acp_server", lambda: _BrokenACPServer())

    client = _build_client(create_ws_router(state))
    with client.websocket_connect("/acp") as ws:
        error_frame = ws.receive_json()
        assert error_frame["jsonrpc"] == "2.0"
        assert error_frame["error"]["message"] == "ACP session setup failed"

        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 1011

    assert sum(ws_router._connections_per_ip.values()) == 0


def test_acp_websocket_bridge_init_failure_cleans_connection_tracking(monkeypatch):
    state = _FakeState()
    monkeypatch.setattr(ws_router, "WS_MAX_CONNECTIONS_PER_IP", 5)
    ws_router._connections_per_ip.clear()

    def _raise_acp_init_error():
        raise RuntimeError("acp init boom")

    monkeypatch.setattr("modules.acp_bridge.get_acp_server", _raise_acp_init_error)

    client = _build_client(create_ws_router(state))
    with client.websocket_connect("/acp") as ws:
        error_frame = ws.receive_json()
        assert error_frame["jsonrpc"] == "2.0"
        assert error_frame["error"]["message"] == "ACP bridge not available"

        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 1011

    assert sum(ws_router._connections_per_ip.values()) == 0


def test_voice_direct_unauthorized_preserves_401():
    state = _FakeState()
    client = _build_client(create_chat_router(state))

    response = client.post("/api/voice/direct", json={"command": "hello"})

    assert response.status_code == 401
