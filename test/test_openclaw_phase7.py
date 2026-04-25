"""Phase 7 tests for OpenClaw WS compatibility flag gating."""

from modules.api.routers.websocket import _normalize_openclaw_message


def test_ws_openclaw_mapping_enabled_by_default(monkeypatch):
    monkeypatch.delenv("LADA_OPENCLAW_WS_COMPAT_ENABLED", raising=False)

    msg_type, msg_data = _normalize_openclaw_message(
        "openclaw.event",
        {
            "event_type": "chat.send",
            "payload": {"message": "hello"},
        },
    )

    assert msg_type == "chat"
    assert msg_data == {"message": "hello"}


def test_ws_openclaw_mapping_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LADA_OPENCLAW_WS_COMPAT_ENABLED", "false")

    payload = {
        "event_type": "chat.send",
        "payload": {"message": "hello"},
    }
    msg_type, msg_data = _normalize_openclaw_message("openclaw.event", payload)

    assert msg_type == "openclaw.event"
    assert msg_data == payload
