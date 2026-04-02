"""Tests for standalone command contracts, bus, and orchestrator service."""

from modules.standalone.command_bus import InMemoryCommandBus
from modules.standalone.contracts import CommandEnvelope
from modules.standalone.orchestrator import create_orchestrator


class _FakeJarvis:
    def process(self, text):
        if "handled" in text:
            return True, "handled-system-command"
        return False, "not-handled"


class _FakeRouter:
    current_backend_name = "fake-backend"

    def query(self, prompt, **kwargs):
        return f"ai-response:{prompt}"


def test_command_envelope_validation_roundtrip():
    envelope = CommandEnvelope.from_dict(
        {
            "source": "test",
            "target": "system",
            "action": "volume up",
            "payload": {"command": "increase volume"},
        }
    )

    as_dict = envelope.to_dict()
    restored = CommandEnvelope.from_dict(as_dict)

    assert restored.source == "test"
    assert restored.target == "system"
    assert restored.payload["command"] == "increase volume"


def test_inmemory_bus_command_and_event_subscription():
    bus = InMemoryCommandBus(worker_count=1)
    bus.start()

    seen_commands = []
    seen_events = []

    command_token = bus.subscribe_commands(lambda cmd: seen_commands.append(cmd.command_id))
    event_token = bus.subscribe_events(lambda evt: seen_events.append(evt.event_type))

    envelope = CommandEnvelope.from_dict(
        {
            "source": "test",
            "target": "system",
            "action": "noop",
        }
    )
    bus.publish_command(envelope)

    # Publish one synthetic event to exercise event subscribers as well.
    from modules.standalone.contracts import make_event

    bus.publish_event(make_event(envelope, "command.accepted", "accepted"))

    import time

    deadline = time.time() + 1.5
    while time.time() < deadline and (not seen_commands or not seen_events):
        time.sleep(0.01)

    bus.unsubscribe_commands(command_token)
    bus.unsubscribe_events(event_token)
    bus.stop()

    assert seen_commands == [envelope.command_id]
    assert "command.accepted" in seen_events


def test_orchestrator_system_dispatch_returns_completion_event():
    bus = InMemoryCommandBus(worker_count=1)
    bus.start()

    jarvis = _FakeJarvis()
    orchestrator = create_orchestrator(
        command_bus=bus,
        jarvis_getter=lambda: jarvis,
        ai_router_getter=lambda: _FakeRouter(),
        autostart=True,
    )

    command = CommandEnvelope.from_dict(
        {
            "source": "test",
            "target": "system",
            "action": "run",
            "payload": {"command": "this should be handled"},
        }
    )

    event = orchestrator.submit(command, wait_for_result=True, timeout_ms=2000)

    orchestrator.stop()
    bus.stop()

    assert event is not None
    assert event.event_type == "command.completed"
    assert event.status == "completed"
    assert event.payload["message"] == "handled-system-command"


def test_orchestrator_ai_dispatch_uses_router():
    bus = InMemoryCommandBus(worker_count=1)
    bus.start()

    orchestrator = create_orchestrator(
        command_bus=bus,
        jarvis_getter=lambda: _FakeJarvis(),
        ai_router_getter=lambda: _FakeRouter(),
        autostart=True,
    )

    command = CommandEnvelope.from_dict(
        {
            "source": "test",
            "target": "ai",
            "action": "summarize",
            "payload": {"prompt": "hello"},
        }
    )

    event = orchestrator.submit(command, wait_for_result=True, timeout_ms=2000)

    orchestrator.stop()
    bus.stop()

    assert event is not None
    assert event.event_type == "command.completed"
    assert event.status == "completed"
    assert event.payload["message"] == "ai-response:hello"


def test_orchestrator_rejects_unknown_target():
    bus = InMemoryCommandBus(worker_count=1)
    bus.start()

    orchestrator = create_orchestrator(
        command_bus=bus,
        jarvis_getter=lambda: _FakeJarvis(),
        ai_router_getter=lambda: _FakeRouter(),
        autostart=True,
    )

    command = CommandEnvelope.from_dict(
        {
            "source": "test",
            "target": "plugin",
            "action": "do-work",
        }
    )

    event = orchestrator.submit(command, wait_for_result=True, timeout_ms=2000)

    orchestrator.stop()
    bus.stop()

    assert event is not None
    assert event.event_type == "command.rejected"
    assert event.status == "rejected"
