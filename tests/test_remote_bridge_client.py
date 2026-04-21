"""Tests for modules.remote_bridge_client."""

import pytest
from types import SimpleNamespace

from modules import remote_bridge_client as bridge


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class _InvalidJsonResponse(_FakeResponse):
    def json(self):
        raise ValueError("invalid json")


class _FakeSession:
    def __init__(self, *, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.post_calls = []
        self.get_calls = []
        self.closed = False

    def post(self, url, headers=None, json=None, timeout=None, verify=None):
        self.post_calls.append(
            {
                "url": url,
                "headers": dict(headers or {}),
                "json": json,
                "timeout": timeout,
                "verify": verify,
            }
        )
        if not self.post_responses:
            raise AssertionError(f"Unexpected POST call: {url}")
        return self.post_responses.pop(0)

    def get(self, url, headers=None, timeout=None, verify=None):
        self.get_calls.append(
            {
                "url": url,
                "headers": dict(headers or {}),
                "timeout": timeout,
                "verify": verify,
            }
        )
        if not self.get_responses:
            raise AssertionError(f"Unexpected GET call: {url}")
        return self.get_responses.pop(0)

    def close(self):
        self.closed = True


def _set_bridge_env(monkeypatch):
    monkeypatch.setenv("LADA_REMOTE_BRIDGE_SERVER_URL", "https://lada-ai.onrender.com")
    monkeypatch.setenv("LADA_REMOTE_BRIDGE_PASSWORD", "test-password")
    monkeypatch.setenv("LADA_REMOTE_BRIDGE_DEVICE_ID", "laptop-main")
    monkeypatch.setenv("LADA_REMOTE_BRIDGE_LABEL", "Main Laptop")


def test_bridge_client_requires_server_url(monkeypatch):
    monkeypatch.delenv("LADA_REMOTE_BRIDGE_SERVER_URL", raising=False)
    monkeypatch.setenv("LADA_REMOTE_BRIDGE_PASSWORD", "test-password")
    with pytest.raises(ValueError, match="LADA_REMOTE_BRIDGE_SERVER_URL"):
        bridge.RemoteBridgeClient()


def test_bridge_client_register_and_heartbeat(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[
            _FakeResponse(200, {"token": "tok-1"}),
            _FakeResponse(200, {"success": True}),
            _FakeResponse(200, {"success": True}),
        ]
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    client.register()
    client.heartbeat()

    assert fake_session.post_calls[0]["url"].endswith("/auth/login")
    assert fake_session.post_calls[1]["url"].endswith("/remote/device/register")
    assert fake_session.post_calls[1]["headers"]["Authorization"] == "Bearer tok-1"
    assert fake_session.post_calls[1]["json"]["device_id"] == "laptop-main"
    assert fake_session.post_calls[2]["url"].endswith("/remote/device/heartbeat")


def test_bridge_client_falls_back_to_api_prefix_on_404(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[
            _FakeResponse(404, {"detail": "Not Found"}, text='{"detail":"Not Found"}'),
            _FakeResponse(200, {"token": "tok-api"}),
            _FakeResponse(404, {"detail": "Not Found"}, text='{"detail":"Not Found"}'),
            _FakeResponse(200, {"success": True}),
        ]
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    client.register()

    assert fake_session.post_calls[0]["url"].endswith("/auth/login")
    assert fake_session.post_calls[1]["url"].endswith("/api/auth/login")
    assert fake_session.post_calls[2]["url"].endswith("/remote/device/register")
    assert fake_session.post_calls[3]["url"].endswith("/api/remote/device/register")


def test_bridge_client_missing_device_endpoints_reports_upgrade_hint(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[
            _FakeResponse(200, {"token": "tok-1"}),
            _FakeResponse(404, {"detail": "Not Found"}, text='{"detail":"Not Found"}'),
            _FakeResponse(404, {"detail": "Not Found"}, text='{"detail":"Not Found"}'),
        ]
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()

    with pytest.raises(RuntimeError, match="missing remote bridge device endpoints"):
        client.register()


def test_bridge_poll_once_without_command_stays_idle(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[_FakeResponse(200, {"token": "tok-1"})],
        get_responses=[_FakeResponse(200, {"success": True, "has_command": False})],
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    monkeypatch.setattr(
        client,
        "_execute_command",
        lambda _cmd: (_ for _ in ()).throw(AssertionError("_execute_command should not run")),
    )

    processed = client.poll_once()

    assert processed is False
    assert fake_session.get_calls[0]["url"].endswith("/remote/device/laptop-main/next-command")


def test_bridge_poll_once_executes_and_posts_result(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[
            _FakeResponse(200, {"token": "tok-1"}),
            _FakeResponse(200, {"success": True}),
        ],
        get_responses=[
            _FakeResponse(
                200,
                {
                    "success": True,
                    "has_command": True,
                    "command": {"command_id": "rcmd-1", "command": "open notepad"},
                },
            )
        ],
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    monkeypatch.setattr(
        client,
        "_execute_command",
        lambda command: {"success": True, "response": f"handled:{command}", "error": ""},
    )

    processed = client.poll_once()

    assert processed is True
    assert fake_session.post_calls[1]["url"].endswith("/remote/device/laptop-main/command-result")
    assert fake_session.post_calls[1]["json"]["command_id"] == "rcmd-1"
    assert fake_session.post_calls[1]["json"]["success"] is True
    assert fake_session.post_calls[1]["json"]["response"] == "handled:open notepad"


def test_bridge_poll_once_posts_failed_result_when_command_raises(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[
            _FakeResponse(200, {"token": "tok-1"}),
            _FakeResponse(200, {"success": True}),
        ],
        get_responses=[
            _FakeResponse(
                200,
                {
                    "success": True,
                    "has_command": True,
                    "command": {"command_id": "rcmd-err", "command": "open notepad"},
                },
            )
        ],
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()

    def _raise(_command):
        raise RuntimeError("jarvis boom")

    monkeypatch.setattr(client, "_execute_command", _raise)

    processed = client.poll_once()

    assert processed is True
    assert fake_session.post_calls[1]["url"].endswith("/remote/device/laptop-main/command-result")
    assert fake_session.post_calls[1]["json"]["command_id"] == "rcmd-err"
    assert fake_session.post_calls[1]["json"]["success"] is False
    assert "jarvis boom" in fake_session.post_calls[1]["json"]["error"]


def test_bridge_post_retries_after_unauthorized(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[
            _FakeResponse(200, {"token": "tok-1"}),
            _FakeResponse(401, {"detail": "unauthorized"}, text="unauthorized"),
            _FakeResponse(200, {"token": "tok-2"}),
            _FakeResponse(200, {"success": True}),
        ]
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    client.register()

    assert len(fake_session.post_calls) == 4
    assert fake_session.post_calls[0]["url"].endswith("/auth/login")
    assert fake_session.post_calls[1]["url"].endswith("/remote/device/register")
    assert fake_session.post_calls[2]["url"].endswith("/auth/login")
    assert fake_session.post_calls[3]["url"].endswith("/remote/device/register")
    assert client._token == "tok-2"


def test_run_remote_bridge_client_returns_config_error(monkeypatch):
    monkeypatch.delenv("LADA_REMOTE_BRIDGE_SERVER_URL", raising=False)
    monkeypatch.delenv("LADA_REMOTE_BRIDGE_PASSWORD", raising=False)

    assert bridge.run_remote_bridge_client() == 1


def test_bridge_run_forever_respects_stop_flag(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession()
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    monkeypatch.setattr(client, "register", lambda: None)
    monkeypatch.setattr(client, "poll_once", lambda: (_ for _ in ()).throw(AssertionError("poll_once should not run")))
    client.stop()

    client.run_forever()


def test_bridge_stop_closes_http_session(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession()
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()
    client.stop()

    assert client._stop_requested is True
    assert fake_session.closed is True


def test_bridge_login_invalid_json_raises_runtime_error(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(post_responses=[_InvalidJsonResponse(200, text="not-json")])
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()

    with pytest.raises(RuntimeError, match="Bridge auth returned invalid JSON"):
        client.register()


def test_bridge_poll_invalid_json_raises_runtime_error(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession(
        post_responses=[_FakeResponse(200, {"token": "tok-1"})],
        get_responses=[_InvalidJsonResponse(200, text="not-json")],
    )
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    client = bridge.RemoteBridgeClient()

    with pytest.raises(RuntimeError, match="returned invalid JSON"):
        client.poll_once()


def test_bridge_execute_command_uses_ai_agent_when_jarvis_unhandled(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession()
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    import modules.ai_command_agent as ai_agent_module

    class _FakeAIAgent:
        def __init__(self, provider_manager, tool_registry, config=None):
            self.provider_manager = provider_manager
            self.tool_registry = tool_registry
            self.config = config or {}

        def try_handle(self, command):
            assert "analyze" in command
            return SimpleNamespace(handled=True, response="Vision analyzed. Volume adjusted.")

    monkeypatch.setattr(ai_agent_module, "AICommandAgent", _FakeAIAgent)

    client = bridge.RemoteBridgeClient()
    client._jarvis = SimpleNamespace(process=lambda _command: (False, ""))
    client._ai_router = SimpleNamespace(
        provider_manager=object(),
        tool_registry=object(),
        query=lambda _command: "fallback",
    )

    result = client._execute_command("analyze the screen and control laptop volume")

    assert result["success"] is True
    assert result["response"] == "Vision analyzed. Volume adjusted."
    assert result["error"] == ""


def test_bridge_execute_command_falls_back_to_router_when_ai_agent_unhandled(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession()
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    import modules.ai_command_agent as ai_agent_module

    class _FakeAIAgent:
        def __init__(self, provider_manager, tool_registry, config=None):
            self.provider_manager = provider_manager
            self.tool_registry = tool_registry
            self.config = config or {}

        def try_handle(self, _command):
            return SimpleNamespace(handled=False, response="")

    monkeypatch.setattr(ai_agent_module, "AICommandAgent", _FakeAIAgent)

    client = bridge.RemoteBridgeClient()
    client._jarvis = SimpleNamespace(process=lambda _command: (False, ""))
    client._ai_router = SimpleNamespace(
        provider_manager=object(),
        tool_registry=object(),
        query=lambda _command: "Fallback router response",
    )

    result = client._execute_command("analyze this and reply")

    assert result["success"] is True
    assert result["response"] == "Fallback router response"
    assert result["error"] == ""


def test_bridge_execute_command_prefers_ai_agent_for_compound_command(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession()
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    import modules.ai_command_agent as ai_agent_module

    class _FakeAIAgent:
        def __init__(self, provider_manager, tool_registry, config=None):
            self.provider_manager = provider_manager
            self.tool_registry = tool_registry
            self.config = config or {}

        def try_handle(self, command):
            assert command == "analyze the screen and set volume to 35"
            return SimpleNamespace(handled=True, response="Screen analyzed and volume set to 35%.")

    monkeypatch.setattr(ai_agent_module, "AICommandAgent", _FakeAIAgent)

    client = bridge.RemoteBridgeClient()

    class _JarvisShouldNotRun:
        def process(self, _command):
            raise AssertionError("Jarvis should not run when AI agent handles a compound command")

    client._jarvis = _JarvisShouldNotRun()
    client._ai_router = SimpleNamespace(
        provider_manager=object(),
        tool_registry=object(),
        query=lambda _command: "fallback",
    )

    result = client._execute_command("analyze the screen and set volume to 35")

    assert result["success"] is True
    assert result["response"] == "Screen analyzed and volume set to 35%."
    assert result["error"] == ""


def test_bridge_execute_command_runs_each_compound_step_when_ai_agent_unhandled(monkeypatch):
    _set_bridge_env(monkeypatch)
    fake_session = _FakeSession()
    monkeypatch.setattr(bridge.requests, "Session", lambda: fake_session)

    import modules.ai_command_agent as ai_agent_module

    class _FakeAIAgent:
        def __init__(self, provider_manager, tool_registry, config=None):
            self.provider_manager = provider_manager
            self.tool_registry = tool_registry
            self.config = config or {}

        def try_handle(self, _command):
            return SimpleNamespace(handled=False, response="")

    monkeypatch.setattr(ai_agent_module, "AICommandAgent", _FakeAIAgent)

    client = bridge.RemoteBridgeClient()
    calls = []

    def _jarvis_process(command):
        calls.append(command)
        if command == "analyze the screen":
            return True, "Screen analysis complete."
        if command == "set volume to 35":
            return True, "Volume set to 35%."
        return False, ""

    client._jarvis = SimpleNamespace(process=_jarvis_process)
    client._ai_router = SimpleNamespace(
        provider_manager=object(),
        tool_registry=object(),
        query=lambda _command: "fallback",
    )

    result = client._execute_command("analyze the screen and set volume to 35")

    assert result["success"] is True
    assert result["response"] == "Screen analysis complete.\nVolume set to 35%."
    assert result["error"] == ""
    assert calls == ["analyze the screen", "set volume to 35"]
