"""Stealth browser tool handler coverage."""

from modules.tool_registry import (
    ToolRegistry,
    create_agent_tools,
    create_lada_core_tools,
    create_messaging_tools,
    create_scheduling_tools,
    create_system_tools,
)
from modules.tool_handlers import wire_tool_handlers


class _FakeStealthBrowser:
    def navigate(self, url):
        return {"success": True, "url": url, "title": "Example"}

    def click(self, selector, by="css"):
        return {"success": True, "selector": selector, "by": by}

    def type_text(self, selector, text, by="css", clear_first=True):
        return {
            "success": True,
            "selector": selector,
            "text": text,
            "by": by,
            "clear_first": clear_first,
        }

    def scroll(self, direction="down", amount=300):
        return {"success": True, "direction": direction, "amount": amount}

    def execute_js(self, _script, selector):
        return f"selected:{selector}"

    def get_page_content(self):
        return {
            "success": True,
            "url": "https://example.com",
            "title": "Example",
            "text": "hello from stealth page",
        }


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry(contract_version="1.0")
    for tool in create_system_tools():
        registry.register(tool)
    for tool in create_agent_tools():
        registry.register(tool)
    for tool in create_scheduling_tools():
        registry.register(tool)
    for tool in create_messaging_tools():
        registry.register(tool)
    for tool in create_lada_core_tools():
        registry.register(tool)
    wire_tool_handlers(registry)
    return registry


def test_stealth_tools_are_wired():
    registry = _build_registry()
    assert registry.get("stealth_navigate").handler is not None
    assert registry.get("stealth_click").handler is not None
    assert registry.get("stealth_type").handler is not None
    assert registry.get("stealth_scroll").handler is not None
    assert registry.get("stealth_extract").handler is not None


def test_stealth_navigate_handler_success(monkeypatch):
    fake = _FakeStealthBrowser()
    monkeypatch.setattr("modules.tool_handlers._get_stealth_browser", lambda: fake)

    registry = _build_registry()
    result = registry.execute("stealth_navigate", {"url": "https://example.com"})

    assert result.success is True
    assert "Stealth navigation successful" in result.output


def test_stealth_navigate_handler_requires_url():
    registry = _build_registry()
    result = registry.execute("stealth_navigate", {"url": ""})
    assert result.success is False
    assert "URL is required" in (result.error or "")


def test_stealth_extract_handler_selector_and_page_paths(monkeypatch):
    fake = _FakeStealthBrowser()
    monkeypatch.setattr("modules.tool_handlers._get_stealth_browser", lambda: fake)

    registry = _build_registry()

    selected = registry.execute("stealth_extract", {"selector": "h1"})
    assert selected.success is True
    assert "selected:h1" in selected.output

    page = registry.execute("stealth_extract", {"selector": ""})
    assert page.success is True
    assert "hello from stealth page" in page.output
