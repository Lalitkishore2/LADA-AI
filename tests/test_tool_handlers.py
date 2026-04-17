"""Tests for new tool handler wiring and task/todo behavior."""

from modules.tool_registry import ToolRegistry, create_lada_core_tools
from modules.tool_handlers import wire_tool_handlers


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry(contract_version="1.0")
    for tool in create_lada_core_tools():
        registry.register(tool)
    return registry


def test_wire_tool_handlers_wires_task_and_todo_write():
    registry = _build_registry()
    wired = wire_tool_handlers(registry)
    assert wired > 0
    assert registry.get("task").handler is not None
    assert registry.get("todo_write").handler is not None


def test_todo_write_add_list_complete_roundtrip():
    registry = _build_registry()
    wire_tool_handlers(registry)

    added = registry.execute(
        "todo_write",
        {"action": "add", "id": "t-1", "title": "Implement test", "description": "desc"},
    )
    assert added.success is True

    listed = registry.execute("todo_write", {"action": "list"})
    assert listed.success is True
    assert "t-1" in listed.output

    completed = registry.execute("todo_write", {"action": "complete", "id": "t-1"})
    assert completed.success is True

    listed_after = registry.execute("todo_write", {"action": "list"})
    assert "[done] t-1" in listed_after.output


def test_task_handler_rejects_missing_prompt():
    registry = _build_registry()
    wire_tool_handlers(registry)

    result = registry.execute("task", {"prompt": ""})
    assert result.success is False
    assert "required" in (result.error or "").lower()
