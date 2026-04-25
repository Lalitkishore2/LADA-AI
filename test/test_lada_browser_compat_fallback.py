"""Fallback tests for LADA browser compatibility router when adapter is unavailable."""

import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.lada_browser_compat import create_lada_browser_compat_router


class _FakeStealthBrowser:
    def navigate(self, url):
        return {"success": True, "url": url, "title": "Example Domain"}

    def click(self, selector, by="css"):
        return {"success": True, "selector": selector, "by": by}

    def type_text(self, selector, text, by="css"):
        return {"success": True, "selector": selector, "text": text, "by": by}

    def scroll(self, direction="down", amount=500):
        return {"success": True, "direction": direction, "amount": amount}

    def execute_js(self, script, selector):
        _ = script
        return f"selected:{selector}"

    def get_page_content(self):
        return {
            "success": True,
            "url": "https://example.com",
            "title": "Example",
            "text": "Fallback content from stealth browser.",
        }

    def screenshot(self):
        return {"success": True, "path": "screenshots/fallback.png"}


class _FakeState:
    def __init__(self):
        self.lada_browser_adapter = None

    def load_components(self):
        return None


def _build_client(monkeypatch):
    fake_browser = _FakeStealthBrowser()
    fake_module = types.SimpleNamespace(get_stealth_browser=lambda: fake_browser)
    monkeypatch.setitem(sys.modules, "modules.stealth_browser", fake_module)

    import integrations.lada_browser_adapter as adapter_mod

    monkeypatch.setattr(adapter_mod, "get_lada_browser_adapter", lambda force=False: None)

    app = FastAPI()
    app.include_router(create_lada_browser_compat_router(_FakeState()))
    return TestClient(app)


def test_lada_browser_falls_back_to_stealth_for_navigation_and_actions(monkeypatch):
    client = _build_client(monkeypatch)

    status_resp = client.get("/lada/browser/status", headers={"X-Request-ID": "lada-browser-fallback-req-1"})
    assert status_resp.status_code == 200
    assert status_resp.headers["x-request-id"] == "lada-browser-fallback-req-1"
    assert status_resp.json()["adapter"]["enabled"] is False

    nav_resp = client.post("/lada/browser/navigate", json={"url": "example.com"})
    assert nav_resp.status_code == 200
    nav_payload = nav_resp.json()
    assert nav_payload["success"] is True
    assert nav_payload["mode"] == "stealth_browser"

    click_resp = client.post("/lada/browser/action", json={"action": "click", "selector": "#login"})
    assert click_resp.status_code == 200
    click_payload = click_resp.json()
    assert click_payload["success"] is True
    assert click_payload["mode"] == "stealth_browser"

    extract_resp = client.post("/lada/browser/action", json={"action": "extract", "selector": "h1"})
    assert extract_resp.status_code == 200
    extract_payload = extract_resp.json()
    assert extract_payload["success"] is True
    assert extract_payload["mode"] == "stealth_browser"
    assert "selected:h1" in extract_payload["content"]


def test_lada_browser_snapshot_uses_stealth_when_adapter_unavailable(monkeypatch):
    client = _build_client(monkeypatch)

    snap_resp = client.get("/lada/browser/snapshot")
    assert snap_resp.status_code == 200
    payload = snap_resp.json()
    assert payload["success"] is True
    assert payload["mode"] == "stealth_browser"
    assert payload["snapshot"]["title"] == "Example"
    assert payload["snapshot"]["has_screenshot"] is True
