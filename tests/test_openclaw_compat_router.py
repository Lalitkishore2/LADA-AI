"""Tests for OpenClaw compatibility API router."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.openclaw_compat import create_openclaw_compat_router


class _FakeAdapter:
    def __init__(self):
        self._connected = False

    def status(self):
        return {
            "enabled": True,
            "state": "connected" if self._connected else "idle",
            "connected": self._connected,
            "url": "ws://127.0.0.1:18789",
            "last_error": "",
        }

    def connect(self):
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def navigate(self, url):
        return bool(url)

    def click(self, selector):
        return bool(selector)

    def type_text(self, selector, text):
        return bool(selector)

    def scroll(self, direction="down", amount=500):
        return direction in {"up", "down"} and amount > 0

    def extract_text(self, selector=None):
        if selector:
            return f"selected:{selector}"
        return "page-text"

    def snapshot_summary(self):
        return {
            "url": "https://example.com",
            "title": "Example",
            "interactive_elements": 3,
            "text_chars": 120,
            "has_screenshot": False,
        }


class _FakeState:
    def __init__(self):
        self.openclaw_adapter = _FakeAdapter()

    def load_components(self):
        return None


def _build_client(state):
    app = FastAPI()
    app.include_router(create_openclaw_compat_router(state))
    return TestClient(app)


def test_openclaw_status_and_connect_flow():
    state = _FakeState()
    client = _build_client(state)

    status_resp = client.get("/openclaw/status", headers={"X-Request-ID": "openclaw-status-req-1"})
    assert status_resp.status_code == 200
    assert status_resp.headers["x-request-id"] == "openclaw-status-req-1"
    payload = status_resp.json()
    assert payload["success"] is True
    assert payload["adapter"]["enabled"] is True

    connect_resp = client.post("/openclaw/connect", headers={"X-Request-ID": "openclaw-connect-req-1"})
    assert connect_resp.status_code == 200
    assert connect_resp.headers["x-request-id"] == "openclaw-connect-req-1"
    assert connect_resp.json()["success"] is True


def test_openclaw_navigate_and_action_extract():
    state = _FakeState()
    client = _build_client(state)

    nav_resp = client.post("/openclaw/navigate", json={"url": "example.com"})
    assert nav_resp.status_code == 200
    nav_payload = nav_resp.json()
    assert nav_payload["success"] is True
    assert nav_payload["mode"] == "openclaw_adapter"

    extract_resp = client.post("/openclaw/action", json={"action": "extract", "selector": "#content"})
    assert extract_resp.status_code == 200
    extract_payload = extract_resp.json()
    assert extract_payload["success"] is True
    assert extract_payload["mode"] == "openclaw_adapter"
    assert "selected:#content" in extract_payload["content"]


def test_openclaw_snapshot_from_adapter():
    state = _FakeState()
    client = _build_client(state)

    snap_resp = client.get("/openclaw/snapshot")
    assert snap_resp.status_code == 200
    payload = snap_resp.json()
    assert payload["success"] is True
    assert payload["mode"] == "openclaw_adapter"
    assert payload["snapshot"]["title"] == "Example"
