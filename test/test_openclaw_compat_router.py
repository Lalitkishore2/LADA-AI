"""Tests for OpenClaw compatibility API router."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.openclaw_compat import create_openclaw_compat_router


class _FakeJarvis:
    def process(self, command):
        return True, f"handled:{command}"


class _FakeBrowser:
    def navigate(self, url):
        return {"success": True, "url": url, "title": "Example"}

    def click(self, selector, by="css"):
        return {"success": True, "selector": selector, "by": by}

    def type_text(self, selector, text, by="css"):
        return {"success": True, "selector": selector, "text": text, "by": by}

    def scroll(self, direction="down", amount=500):
        return {"success": True, "direction": direction, "amount": amount}

    def execute_js(self, _script, selector):
        return f"text:{selector}"

    def get_page_content(self):
        return {"success": True, "text": "page text"}


class _FakeState:
    def __init__(self):
        self._valid_token = "good-token"
        self.jarvis = _FakeJarvis()
        self.voice_processor = None
        self.lada_browser_adapter = None

    def load_components(self):
        return None

    def validate_session_token(self, token):
        return token == self._valid_token


def _build_client(monkeypatch, *, openclaw_mode="true", rpm="30"):
    monkeypatch.setenv("LADA_OPENCLAW_MODE", openclaw_mode)
    monkeypatch.setenv("LADA_OPENCLAW_COMPAT_RPM", rpm)

    import modules.stealth_browser as stealth_mod

    monkeypatch.setattr(stealth_mod, "get_stealth_browser", lambda: _FakeBrowser())

    app = FastAPI()
    app.include_router(create_openclaw_compat_router(_FakeState()))
    return TestClient(app)


def test_openclaw_status_requires_auth_and_returns_event(monkeypatch):
    client = _build_client(monkeypatch)

    unauthorized = client.get("/openclaw/compat/status")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/openclaw/compat/status",
        headers={"Authorization": "Bearer good-token", "X-Request-ID": "oc-status-1"},
    )
    assert authorized.status_code == 200
    payload = authorized.json()
    assert payload["type"] == "openclaw.event"
    assert payload["event_type"] == "openclaw.system.status"
    assert payload["request_id"] == "oc-status-1"
    assert payload["payload"]["ws_compat_enabled"] is True


def test_openclaw_status_reflects_ws_compat_flag(monkeypatch):
    monkeypatch.setenv("LADA_OPENCLAW_WS_COMPAT_ENABLED", "false")
    client = _build_client(monkeypatch)

    response = client.get(
        "/openclaw/compat/status",
        headers={"Authorization": "Bearer good-token", "X-Request-ID": "oc-status-flag-1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["payload"]["ws_compat_enabled"] is False


def test_openclaw_command_executes_and_wraps_response(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.post(
        "/openclaw/compat/command",
        json={"command": "open calculator", "request_id": "oc-cmd-1"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "openclaw.event"
    assert payload["event_type"] == "openclaw.command.result"
    assert payload["request_id"] == "oc-cmd-1"
    assert payload["payload"]["success"] is True
    assert payload["payload"]["response"] == "handled:open calculator"


def test_openclaw_browser_action_navigate(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.post(
        "/openclaw/compat/browser-action",
        json={"action": "navigate", "url": "example.com", "request_id": "oc-nav-1"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "openclaw.browser.result"
    assert payload["request_id"] == "oc-nav-1"
    assert payload["payload"]["success"] is True
    assert payload["payload"]["mode"] == "stealth_browser"


def test_openclaw_router_respects_feature_flag(monkeypatch):
    client = _build_client(monkeypatch, openclaw_mode="false")

    response = client.get(
        "/openclaw/compat/status",
        headers={"Authorization": "Bearer good-token"},
    )
    assert response.status_code == 404


def test_openclaw_router_rate_limit(monkeypatch):
    client = _build_client(monkeypatch, rpm="1")

    first = client.get(
        "/openclaw/compat/status",
        headers={"Authorization": "Bearer good-token"},
    )
    second = client.get(
        "/openclaw/compat/status",
        headers={"Authorization": "Bearer good-token"},
    )

    assert first.status_code == 200
    assert second.status_code == 429
