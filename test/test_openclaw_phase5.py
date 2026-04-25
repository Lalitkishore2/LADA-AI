"""Phase 5 tests for OpenClaw compatibility router wiring and WS mapping."""

from modules.api_server import FASTAPI_OK, LADAAPIServer
from modules.api.routers.websocket import _normalize_openclaw_message


def test_ws_openclaw_event_maps_to_internal_chat_type():
    msg_type, msg_data = _normalize_openclaw_message(
        "openclaw.event",
        {
            "event_type": "chat.send",
            "payload": {"message": "hello"},
        },
    )

    assert msg_type == "chat"
    assert msg_data == {"message": "hello"}


def test_ws_openclaw_unknown_event_falls_back_without_remap():
    original = {
        "event_type": "unknown.event",
        "payload": {"x": 1},
    }

    msg_type, msg_data = _normalize_openclaw_message("openclaw.event", original)

    assert msg_type == "openclaw.event"
    assert msg_data == original


def test_api_server_includes_openclaw_compat_router_when_fastapi_available():
    if not FASTAPI_OK:
        return

    server = LADAAPIServer(host="127.0.0.1", port=5001)

    route_paths = {route.path for route in server.app.routes}
    assert "/openclaw/compat/status" in route_paths
    assert "/openclaw/compat/command" in route_paths
    assert "/openclaw/compat/browser-action" in route_paths
