"""Tests for tool contract versioning and compatibility checks."""

import pytest

import modules.tool_registry as tr
from modules.tool_registry import ToolCategory, ToolDefinition, ToolRegistry


def test_tool_registry_exposes_contract_metadata_in_stats_and_schema():
    tr._registry = None
    registry = tr.get_tool_registry()

    stats = registry.get_stats()
    info = registry.get_contract_info()
    schema = registry.to_ai_schema()

    assert stats["contract_major"] == info["major"]
    assert stats["contract_version"] == info["version"]
    assert info["tool_count"] >= 1

    first_fn = schema[0]["function"]
    assert first_fn["x_contract_version"] == info["version"]
    assert isinstance(first_fn["x_required_contract_major"], int)


def test_tool_registry_rejects_incompatible_tool_contract_major():
    registry = ToolRegistry(contract_version="1.2")

    incompatible_tool = ToolDefinition(
        name="future_tool",
        description="Requires next contract major",
        category=ToolCategory.SYSTEM,
        required_contract_major=2,
    )

    with pytest.raises(ValueError, match="Tool contract mismatch"):
        registry.register(incompatible_tool)


def test_wire_tool_handlers_skips_when_contract_major_mismatch(monkeypatch):
    import modules.tool_handlers as th

    registry = ToolRegistry(contract_version="2.0")
    compatible_tool = ToolDefinition(
        name="set_volume",
        description="Contract-compatible tool",
        category=ToolCategory.SYSTEM,
        required_contract_major=2,
    )
    registry.register(compatible_tool)

    monkeypatch.setattr(th, "HANDLER_CONTRACT_VERSION", "1.0")

    wired = th.wire_tool_handlers(registry)
    assert wired == 0
    assert registry.get("set_volume").handler is None
