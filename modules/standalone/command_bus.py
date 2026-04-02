"""Command bus implementations for standalone LADA services."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import Callable, Dict, List, Optional

from modules.standalone.contracts import CommandEnvelope, EventEnvelope

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore

    REDIS_OK = True
except Exception:
    REDIS_OK = False


CommandCallback = Callable[[CommandEnvelope], None]
EventCallback = Callable[[EventEnvelope], None]


class BaseCommandBus:
    """Abstract command bus interface."""

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def publish_command(self, command: CommandEnvelope) -> None:
        raise NotImplementedError

    def publish_event(self, event: EventEnvelope) -> None:
        raise NotImplementedError

    def subscribe_commands(self, callback: CommandCallback) -> str:
        raise NotImplementedError

    def unsubscribe_commands(self, token: str) -> None:
        raise NotImplementedError

    def subscribe_events(self, callback: EventCallback) -> str:
        raise NotImplementedError

    def unsubscribe_events(self, token: str) -> None:
        raise NotImplementedError


class InMemoryCommandBus(BaseCommandBus):
    """Threaded in-memory bus for local development and fallback mode."""

    def __init__(self, worker_count: int = 2):
        self.worker_count = max(1, int(worker_count))
        self._command_queue: "queue.Queue[Optional[CommandEnvelope]]" = queue.Queue()
        self._event_queue: "queue.Queue[Optional[EventEnvelope]]" = queue.Queue()
        self._command_subscribers: Dict[str, CommandCallback] = {}
        self._event_subscribers: Dict[str, EventCallback] = {}
        self._command_workers: List[threading.Thread] = []
        self._event_workers: List[threading.Thread] = []
        self._token_counter = 0
        self._running = False
        self._lock = threading.RLock()
        self._stats = {
            "commands_published": 0,
            "events_published": 0,
            "dispatch_errors": 0,
        }

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

            for i in range(self.worker_count):
                cmd_thread = threading.Thread(
                    target=self._command_worker,
                    name=f"bus-cmd-{i}",
                    daemon=True,
                )
                evt_thread = threading.Thread(
                    target=self._event_worker,
                    name=f"bus-evt-{i}",
                    daemon=True,
                )
                cmd_thread.start()
                evt_thread.start()
                self._command_workers.append(cmd_thread)
                self._event_workers.append(evt_thread)

            logger.info("[CommandBus] In-memory bus started (%d workers)", self.worker_count)

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

            for _ in self._command_workers:
                self._command_queue.put(None)
            for _ in self._event_workers:
                self._event_queue.put(None)

            for worker in self._command_workers + self._event_workers:
                worker.join(timeout=2)

            self._command_workers.clear()
            self._event_workers.clear()
            logger.info("[CommandBus] In-memory bus stopped")

    def publish_command(self, command: CommandEnvelope) -> None:
        command.validate()
        if not self._running:
            self.start()
        self._stats["commands_published"] += 1
        self._command_queue.put(command)

    def publish_event(self, event: EventEnvelope) -> None:
        event.validate()
        if not self._running:
            self.start()
        self._stats["events_published"] += 1
        self._event_queue.put(event)

    def subscribe_commands(self, callback: CommandCallback) -> str:
        token = self._next_token("cmd")
        with self._lock:
            self._command_subscribers[token] = callback
        return token

    def unsubscribe_commands(self, token: str) -> None:
        with self._lock:
            self._command_subscribers.pop(token, None)

    def subscribe_events(self, callback: EventCallback) -> str:
        token = self._next_token("evt")
        with self._lock:
            self._event_subscribers[token] = callback
        return token

    def unsubscribe_events(self, token: str) -> None:
        with self._lock:
            self._event_subscribers.pop(token, None)

    def get_stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def _next_token(self, prefix: str) -> str:
        with self._lock:
            self._token_counter += 1
            return f"{prefix}_{self._token_counter}"

    def _command_worker(self) -> None:
        while True:
            item = self._command_queue.get()
            if item is None:
                return
            subscribers = self._snapshot_command_subscribers()
            for callback in subscribers:
                self._safe_invoke(callback, item)

    def _event_worker(self) -> None:
        while True:
            item = self._event_queue.get()
            if item is None:
                return
            subscribers = self._snapshot_event_subscribers()
            for callback in subscribers:
                self._safe_invoke(callback, item)

    def _snapshot_command_subscribers(self) -> List[CommandCallback]:
        with self._lock:
            return list(self._command_subscribers.values())

    def _snapshot_event_subscribers(self) -> List[EventCallback]:
        with self._lock:
            return list(self._event_subscribers.values())

    def _safe_invoke(self, callback: Callable, item: object) -> None:
        try:
            callback(item)
        except Exception as exc:
            self._stats["dispatch_errors"] += 1
            logger.error("[CommandBus] Subscriber callback failed: %s", exc)


class RedisStreamsCommandBus(BaseCommandBus):
    """Redis Streams-backed bus used for process-to-process messaging."""

    def __init__(
        self,
        redis_url: str,
        command_stream: str = "lada:commands",
        event_stream: str = "lada:events",
        poll_block_ms: int = 1000,
    ):
        if not REDIS_OK:
            raise RuntimeError("redis package is not installed")

        self.redis_url = redis_url
        self.command_stream = command_stream
        self.event_stream = event_stream
        self.poll_block_ms = max(100, int(poll_block_ms))

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._command_subscribers: Dict[str, CommandCallback] = {}
        self._event_subscribers: Dict[str, EventCallback] = {}
        self._token_counter = 0
        self._lock = threading.RLock()
        self._running = False
        self._command_worker: Optional[threading.Thread] = None
        self._event_worker: Optional[threading.Thread] = None
        self._command_offset = "$"
        self._event_offset = "$"

    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            # Fail fast if Redis is unavailable.
            self._client.ping()

            self._running = True
            self._command_worker = threading.Thread(
                target=self._poll_commands,
                name="redis-cmd-poller",
                daemon=True,
            )
            self._event_worker = threading.Thread(
                target=self._poll_events,
                name="redis-evt-poller",
                daemon=True,
            )
            self._command_worker.start()
            self._event_worker.start()
            logger.info("[CommandBus] Redis Streams bus started (%s)", self.redis_url)

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._command_worker:
            self._command_worker.join(timeout=2)
        if self._event_worker:
            self._event_worker.join(timeout=2)

        logger.info("[CommandBus] Redis Streams bus stopped")

    def publish_command(self, command: CommandEnvelope) -> None:
        command.validate()
        payload = json.dumps(command.to_dict(), ensure_ascii=True)
        self._client.xadd(self.command_stream, {"payload": payload})

    def publish_event(self, event: EventEnvelope) -> None:
        event.validate()
        payload = json.dumps(event.to_dict(), ensure_ascii=True)
        self._client.xadd(self.event_stream, {"payload": payload})

    def subscribe_commands(self, callback: CommandCallback) -> str:
        token = self._next_token("cmd")
        with self._lock:
            self._command_subscribers[token] = callback
        return token

    def unsubscribe_commands(self, token: str) -> None:
        with self._lock:
            self._command_subscribers.pop(token, None)

    def subscribe_events(self, callback: EventCallback) -> str:
        token = self._next_token("evt")
        with self._lock:
            self._event_subscribers[token] = callback
        return token

    def unsubscribe_events(self, token: str) -> None:
        with self._lock:
            self._event_subscribers.pop(token, None)

    def _next_token(self, prefix: str) -> str:
        with self._lock:
            self._token_counter += 1
            return f"{prefix}_{self._token_counter}"

    def _poll_commands(self) -> None:
        while self._running:
            try:
                entries = self._client.xread(
                    {self.command_stream: self._command_offset},
                    count=20,
                    block=self.poll_block_ms,
                )
                self._dispatch_entries(entries, is_command=True)
            except Exception as exc:
                logger.error("[CommandBus] Redis command poll failed: %s", exc)

    def _poll_events(self) -> None:
        while self._running:
            try:
                entries = self._client.xread(
                    {self.event_stream: self._event_offset},
                    count=20,
                    block=self.poll_block_ms,
                )
                self._dispatch_entries(entries, is_command=False)
            except Exception as exc:
                logger.error("[CommandBus] Redis event poll failed: %s", exc)

    def _dispatch_entries(self, entries: list, is_command: bool) -> None:
        for _, messages in entries:
            for message_id, fields in messages:
                payload = fields.get("payload")
                if not payload:
                    continue

                try:
                    data = json.loads(payload)
                    if is_command:
                        envelope = CommandEnvelope.from_dict(data)
                        self._command_offset = message_id
                        callbacks = self._snapshot_commands()
                    else:
                        envelope = EventEnvelope.from_dict(data)
                        self._event_offset = message_id
                        callbacks = self._snapshot_events()

                    for callback in callbacks:
                        try:
                            callback(envelope)
                        except Exception as exc:
                            logger.error("[CommandBus] Redis subscriber callback failed: %s", exc)
                except Exception as exc:
                    logger.error("[CommandBus] Redis payload decode failed: %s", exc)

    def _snapshot_commands(self) -> List[CommandCallback]:
        with self._lock:
            return list(self._command_subscribers.values())

    def _snapshot_events(self) -> List[EventCallback]:
        with self._lock:
            return list(self._event_subscribers.values())


def create_command_bus(backend: Optional[str] = None) -> BaseCommandBus:
    """Create a command bus using env-configured backend with safe fallback."""

    selected = (backend or os.getenv("LADA_COMMAND_BUS", "memory")).strip().lower()

    if selected == "redis":
        redis_url = os.getenv("LADA_REDIS_URL", "redis://localhost:6379/0")
        command_stream = os.getenv("LADA_COMMAND_STREAM", "lada:commands")
        event_stream = os.getenv("LADA_EVENT_STREAM", "lada:events")
        poll_block_ms = int(os.getenv("LADA_REDIS_POLL_BLOCK_MS", "1000"))

        try:
            bus = RedisStreamsCommandBus(
                redis_url=redis_url,
                command_stream=command_stream,
                event_stream=event_stream,
                poll_block_ms=poll_block_ms,
            )
            bus.start()
            return bus
        except Exception as exc:
            logger.warning("[CommandBus] Redis backend unavailable, falling back to memory: %s", exc)

    bus = InMemoryCommandBus(worker_count=int(os.getenv("LADA_BUS_WORKERS", "2")))
    bus.start()
    return bus
