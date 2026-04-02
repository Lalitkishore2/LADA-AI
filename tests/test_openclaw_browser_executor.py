"""Tests for OpenClaw compatibility aliases in BrowserExecutor."""

import sys
import types

from core.executors.browser_executor import BrowserExecutor


class _FakeCore:
    def __init__(self):
        self.comet_agent = None
        self.smart_browser = None
        self.browser_tabs = None
        self.youtube_summarizer = None
        self.page_summarizer = None
        self.multi_tab = None


class _FakeStealthBrowser:
    def navigate(self, url):
        return {"success": True, "url": url}


class _FakeAdapter:
    def status(self):
        return {
            "enabled": True,
            "state": "connected",
            "connected": True,
            "url": "ws://127.0.0.1:18789",
        }

    def click(self, selector):
        return bool(selector)


def _patch_no_adapter(monkeypatch):
    import integrations.openclaw_adapter as adapter_mod

    monkeypatch.setattr(adapter_mod, "get_openclaw_adapter", lambda force=False: None)


def test_openclaw_help_command_is_handled(monkeypatch):
    _patch_no_adapter(monkeypatch)

    executor = BrowserExecutor(_FakeCore())
    handled, response = executor.try_handle("openclaw help")

    assert handled is True
    assert "openclaw status" in response


def test_openclaw_navigate_falls_back_to_stealth(monkeypatch):
    _patch_no_adapter(monkeypatch)

    fake_module = types.SimpleNamespace(get_stealth_browser=lambda: _FakeStealthBrowser())
    monkeypatch.setitem(sys.modules, "modules.stealth_browser", fake_module)

    executor = BrowserExecutor(_FakeCore())
    handled, response = executor.try_handle("openclaw navigate example.com")

    assert handled is True
    assert "Stealth navigation successful" in response


def test_openclaw_click_uses_adapter_when_available(monkeypatch):
    import integrations.openclaw_adapter as adapter_mod

    monkeypatch.setattr(adapter_mod, "get_openclaw_adapter", lambda force=False: _FakeAdapter())

    executor = BrowserExecutor(_FakeCore())
    handled, response = executor.try_handle("openclaw click #login")

    assert handled is True
    assert "OpenClaw adapter clicked" in response
