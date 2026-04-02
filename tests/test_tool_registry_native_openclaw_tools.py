"""Regression tests for native OpenClaw-like system tools in ToolRegistry."""

import modules.tool_registry as tr


def test_native_openclaw_like_tools_export_to_ai_schema():
    tr._registry = None
    registry = tr.get_tool_registry()

    schema = registry.to_ai_schema()
    by_name = {entry["function"]["name"]: entry["function"] for entry in schema}

    assert "take_camera_photo" in by_name
    assert "send_notification" in by_name
    assert "record_screen" in by_name

    notify_props = by_name["send_notification"]["parameters"]["properties"]
    notify_required = by_name["send_notification"]["parameters"]["required"]
    assert "title" in notify_props
    assert "message" in notify_props
    assert "title" in notify_required
    assert "message" in notify_required

    record_props = by_name["record_screen"]["parameters"]["properties"]
    assert "duration_seconds" in record_props
