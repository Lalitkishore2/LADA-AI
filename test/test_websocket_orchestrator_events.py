"""Tests for standalone orchestrator WebSocket event streaming semantics."""

import asyncio

from modules.api.routers.websocket import _handle_orchestrator
from modules.standalone.contracts import make_event


class _FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


class _FakeBus:
    def __init__(self):
        self.callback = None
        self.unsubscribed_tokens = []

    def subscribe_events(self, callback):
        self.callback = callback
        return "tok-1"

    def unsubscribe_events(self, token):
        self.unsubscribed_tokens.append(token)


class _FakeOrchestrator:
    def __init__(self):
        self.last_envelope = None

    def submit(self, envelope, wait_for_result=True, timeout_ms=60000):
        self.last_envelope = envelope
        return make_event(
            envelope,
            event_type="command.completed",
            status="completed",
            payload={"message": "ok"},
            source="orchestrator",
        )


class _FakeState:
    def __init__(self):
        self.orchestrator = _FakeOrchestrator()
        self.command_bus = _FakeBus()

        self.ws_connections = {}
        self.ws_sessions = {}

        self.ws_orchestrator_subscribers = set()
        self.ws_orchestrator_subscription_filters = {}
        self.ws_orchestrator_bus_subscription_token = None
        self.ws_orchestrator_event_loop = None
        self.ws_orchestrator_event_callback = None

    def load_components(self):
        return None


def test_orchestrator_ws_subscribe_and_receive_streamed_event():
    state = _FakeState()
    ws = _FakeWebSocket()
    session_id = "sess-1"

    state.ws_connections[session_id] = ws
    state.ws_sessions[session_id] = {
        "messages_sent": 0,
        "orchestrator_events": False,
    }

    async def _scenario():
        await _handle_orchestrator(
            state,
            ws,
            session_id,
            "msg-1",
            {"orchestrator_action": "subscribe"},
        )

        class _Event:
            def to_dict(self):
                return {
                    "event_type": "command.completed",
                    "status": "completed",
                    "payload": {"message": "done"},
                }

        state.ws_orchestrator_event_callback(_Event())
        await asyncio.sleep(0.05)

    asyncio.run(_scenario())

    message_types = [m.get("type") for m in ws.sent]
    assert "orchestrator.subscribed" in message_types
    assert "orchestrator.event" in message_types
    assert state.ws_sessions[session_id]["orchestrator_events"] is True
    assert state.ws_sessions[session_id]["messages_sent"] >= 1


def test_orchestrator_ws_unsubscribe_cleans_bus_bridge():
    state = _FakeState()
    ws = _FakeWebSocket()
    session_id = "sess-2"

    state.ws_connections[session_id] = ws
    state.ws_sessions[session_id] = {
        "messages_sent": 0,
        "orchestrator_events": False,
    }

    async def _scenario():
        await _handle_orchestrator(
            state,
            ws,
            session_id,
            "msg-1",
            {"orchestrator_action": "subscribe"},
        )
        await _handle_orchestrator(
            state,
            ws,
            session_id,
            "msg-2",
            {"orchestrator_action": "unsubscribe"},
        )

    asyncio.run(_scenario())

    assert session_id not in state.ws_orchestrator_subscribers
    assert state.ws_orchestrator_bus_subscription_token is None
    assert state.command_bus.unsubscribed_tokens == ["tok-1"]


def test_orchestrator_ws_dispatch_keeps_command_action_compatible():
    state = _FakeState()
    ws = _FakeWebSocket()
    session_id = "sess-3"

    state.ws_connections[session_id] = ws
    state.ws_sessions[session_id] = {
        "messages_sent": 0,
        "orchestrator_events": False,
    }

    async def _scenario():
        await _handle_orchestrator(
            state,
            ws,
            session_id,
            "msg-3",
            {
                "source": "ws",
                "target": "system",
                "action": "custom_action",
                "payload": {"command": "hello"},
                "wait": True,
            },
        )

    asyncio.run(_scenario())

    assert state.orchestrator.last_envelope is not None
    assert state.orchestrator.last_envelope.action == "custom_action"

    assert ws.sent
    last = ws.sent[-1]
    assert last["type"] == "orchestrator.response"
    assert last["data"]["status"] == "completed"


def test_orchestrator_ws_subscription_filters_limit_fanout():
    state = _FakeState()

    ws_filtered = _FakeWebSocket()
    session_filtered = "sess-filtered"
    state.ws_connections[session_filtered] = ws_filtered
    state.ws_sessions[session_filtered] = {
        "messages_sent": 0,
        "orchestrator_events": False,
        "orchestrator_event_filters": {},
    }

    ws_unfiltered = _FakeWebSocket()
    session_unfiltered = "sess-unfiltered"
    state.ws_connections[session_unfiltered] = ws_unfiltered
    state.ws_sessions[session_unfiltered] = {
        "messages_sent": 0,
        "orchestrator_events": False,
        "orchestrator_event_filters": {},
    }

    async def _scenario():
        await _handle_orchestrator(
            state,
            ws_filtered,
            session_filtered,
            "msg-1",
            {
                "orchestrator_action": "subscribe",
                "filters": {
                    "event_type": "command.completed",
                    "correlation_id": "corr-match",
                    "target": "system",
                },
            },
        )
        await _handle_orchestrator(
            state,
            ws_unfiltered,
            session_unfiltered,
            "msg-2",
            {"orchestrator_action": "subscribe"},
        )

        class _StartedWrongCorrelation:
            def to_dict(self):
                return {
                    "event_type": "command.started",
                    "status": "running",
                    "correlation_id": "corr-match",
                    "payload": {"target": "system"},
                }

        class _CompletedWrongTarget:
            def to_dict(self):
                return {
                    "event_type": "command.completed",
                    "status": "completed",
                    "correlation_id": "corr-match",
                    "payload": {"target": "ai"},
                }

        class _CompletedMatch:
            def to_dict(self):
                return {
                    "event_type": "command.completed",
                    "status": "completed",
                    "correlation_id": "corr-match",
                    "payload": {"target": "system"},
                }

        state.ws_orchestrator_event_callback(_StartedWrongCorrelation())
        state.ws_orchestrator_event_callback(_CompletedWrongTarget())
        state.ws_orchestrator_event_callback(_CompletedMatch())
        await asyncio.sleep(0.05)

    asyncio.run(_scenario())

    filtered_events = [m for m in ws_filtered.sent if m.get("type") == "orchestrator.event"]
    unfiltered_events = [m for m in ws_unfiltered.sent if m.get("type") == "orchestrator.event"]

    assert len(filtered_events) == 1
    assert filtered_events[0]["data"]["event"]["event_type"] == "command.completed"
    assert filtered_events[0]["data"]["event"]["payload"]["target"] == "system"

    assert len(unfiltered_events) == 3
