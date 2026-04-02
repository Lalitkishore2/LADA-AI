"""Standalone orchestrator that routes bus commands to runtime handlers."""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from modules.standalone.command_bus import BaseCommandBus
from modules.standalone.contracts import (
    CommandEnvelope,
    CommandResult,
    EventEnvelope,
    make_event,
)

logger = logging.getLogger(__name__)

TargetHandler = Callable[[CommandEnvelope], CommandResult]


class StandaloneOrchestrator:
    """Routes command envelopes to handlers and emits lifecycle events."""

    def __init__(
        self,
        command_bus: BaseCommandBus,
        jarvis_getter: Optional[Callable[[], Any]] = None,
        ai_router_getter: Optional[Callable[[], Any]] = None,
        max_workers: int = 4,
    ):
        self.command_bus = command_bus
        self.jarvis_getter = jarvis_getter
        self.ai_router_getter = ai_router_getter
        self.max_workers = max(1, int(max_workers))

        self._handlers: Dict[str, TargetHandler] = {}
        self._waiters: Dict[str, "queue.Queue[EventEnvelope]"] = {}
        self._waiters_lock = threading.RLock()
        self._command_subscription: Optional[str] = None
        self._running = False

        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="orchestrator",
        )

        self.register_handler("system", self._handle_system_command)
        self.register_handler("ai", self._handle_ai_query)
        self.register_handler("orchestrator", self._handle_control)

    def start(self) -> None:
        if self._running:
            return

        self._command_subscription = self.command_bus.subscribe_commands(self._on_command)
        self._running = True
        logger.info("[Orchestrator] Started with handlers: %s", ", ".join(sorted(self._handlers)))

    def stop(self) -> None:
        if not self._running:
            return

        if self._command_subscription:
            self.command_bus.unsubscribe_commands(self._command_subscription)
            self._command_subscription = None

        self._running = False
        self._executor.shutdown(wait=False)
        logger.info("[Orchestrator] Stopped")

    def register_handler(self, target: str, handler: TargetHandler) -> None:
        self._handlers[target] = handler

    def submit(
        self,
        command: CommandEnvelope,
        wait_for_result: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> Optional[EventEnvelope]:
        """Submit command envelope to bus and optionally await final event."""

        command.validate()
        waiter: Optional["queue.Queue[EventEnvelope]"] = None

        if wait_for_result:
            waiter = queue.Queue(maxsize=1)
            with self._waiters_lock:
                self._waiters[command.command_id] = waiter

        self.command_bus.publish_command(command)

        if not wait_for_result or waiter is None:
            return None

        timeout_seconds = (timeout_ms or command.timeout_ms) / 1000.0

        try:
            return waiter.get(timeout=timeout_seconds)
        except queue.Empty:
            return make_event(
                command,
                event_type="command.failed",
                status="failed",
                payload={
                    "message": "Timed out waiting for command completion",
                    "error": "orchestrator_timeout",
                },
                source="orchestrator",
            )
        finally:
            with self._waiters_lock:
                self._waiters.pop(command.command_id, None)

    def get_status(self) -> Dict[str, Any]:
        with self._waiters_lock:
            waiter_count = len(self._waiters)
        return {
            "running": self._running,
            "handler_count": len(self._handlers),
            "handlers": sorted(self._handlers.keys()),
            "inflight_waiters": waiter_count,
            "max_workers": self.max_workers,
        }

    def _on_command(self, command: CommandEnvelope) -> None:
        if not self._running:
            return

        self._executor.submit(self._process_command, command)

    def _process_command(self, command: CommandEnvelope) -> None:
        self._publish_event(
            make_event(
                command,
                event_type="command.accepted",
                status="accepted",
                payload={"target": command.target, "action": command.action},
                source="orchestrator",
            )
        )

        self._publish_event(
            make_event(
                command,
                event_type="command.started",
                status="running",
                payload={"target": command.target, "action": command.action},
                source="orchestrator",
            )
        )

        handler = self._handlers.get(command.target)

        if handler is None:
            event = make_event(
                command,
                event_type="command.rejected",
                status="rejected",
                payload={
                    "message": f"No handler registered for target '{command.target}'",
                    "error": "missing_handler",
                },
                source="orchestrator",
            )
            self._publish_event(event)
            self._notify_waiter(event)
            return

        try:
            raw_result = handler(command)
            result = self._normalize_result(raw_result)

            if result.success:
                event = make_event(
                    command,
                    event_type="command.completed",
                    status="completed",
                    payload={
                        "message": result.message,
                        "output": result.output,
                    },
                    source="orchestrator",
                )
            else:
                event = make_event(
                    command,
                    event_type="command.failed",
                    status="failed",
                    payload={
                        "message": result.message,
                        "output": result.output,
                        "error": result.error or "handler_failed",
                    },
                    source="orchestrator",
                )

            self._publish_event(event)
            self._notify_waiter(event)
        except Exception as exc:
            event = make_event(
                command,
                event_type="command.failed",
                status="failed",
                payload={
                    "message": "Handler raised an exception",
                    "error": str(exc),
                },
                source="orchestrator",
            )
            self._publish_event(event)
            self._notify_waiter(event)
            logger.error("[Orchestrator] Command processing failed: %s", exc)

    def _publish_event(self, event: EventEnvelope) -> None:
        try:
            self.command_bus.publish_event(event)
        except Exception as exc:
            logger.error("[Orchestrator] Failed to publish event: %s", exc)

    def _notify_waiter(self, event: EventEnvelope) -> None:
        with self._waiters_lock:
            waiter = self._waiters.get(event.command_id)
        if waiter is None:
            return

        try:
            waiter.put_nowait(event)
        except queue.Full:
            pass

    def _normalize_result(self, raw_result: Any) -> CommandResult:
        if isinstance(raw_result, CommandResult):
            return raw_result

        if isinstance(raw_result, tuple) and len(raw_result) >= 2:
            return CommandResult(success=bool(raw_result[0]), message=str(raw_result[1]))

        if isinstance(raw_result, dict):
            return CommandResult.from_dict(raw_result)

        return CommandResult(
            success=False,
            message="Unsupported handler result",
            error=f"invalid_result_type:{type(raw_result).__name__}",
        )

    def _resolve_text(self, command: CommandEnvelope) -> str:
        payload = command.payload or {}
        text = (
            payload.get("command")
            or payload.get("text")
            or payload.get("prompt")
            or payload.get("message")
            or command.action
        )
        return str(text).strip() if text is not None else ""

    def _handle_system_command(self, command: CommandEnvelope) -> CommandResult:
        jarvis = self.jarvis_getter() if self.jarvis_getter else None
        if jarvis is None:
            return CommandResult(
                success=False,
                message="System command processor is unavailable",
                error="jarvis_unavailable",
            )

        command_text = self._resolve_text(command)
        if not command_text:
            return CommandResult(
                success=False,
                message="System command is empty",
                error="empty_command",
            )

        handled, response = jarvis.process(command_text)

        return CommandResult(
            success=bool(handled),
            message=response or "",
            output={"handled": bool(handled), "target": "system"},
            error=None if handled else "not_handled",
        )

    def _handle_ai_query(self, command: CommandEnvelope) -> CommandResult:
        ai_router = self.ai_router_getter() if self.ai_router_getter else None
        if ai_router is None:
            return CommandResult(
                success=False,
                message="AI router is unavailable",
                error="ai_unavailable",
            )

        prompt = self._resolve_text(command)
        if not prompt:
            return CommandResult(
                success=False,
                message="AI prompt is empty",
                error="empty_prompt",
            )

        payload = command.payload or {}
        model = payload.get("model")
        use_web_search = bool(payload.get("use_web_search", False))

        if model:
            response = ai_router.query(prompt, model=model, use_web_search=use_web_search)
        else:
            response = ai_router.query(prompt, use_web_search=use_web_search)

        return CommandResult(
            success=True,
            message=str(response),
            output={
                "target": "ai",
                "backend": getattr(ai_router, "current_backend_name", "unknown"),
            },
        )

    def _handle_control(self, command: CommandEnvelope) -> CommandResult:
        action = (command.action or "").strip().lower()

        if action in {"ping", "health"}:
            return CommandResult(success=True, message="ok", output=self.get_status())

        if action in {"status", "get_status"}:
            return CommandResult(success=True, message="status", output=self.get_status())

        if action in {"list_handlers", "handlers"}:
            return CommandResult(
                success=True,
                message="handlers",
                output={"handlers": sorted(self._handlers.keys())},
            )

        return CommandResult(
            success=False,
            message=f"Unsupported orchestrator action: {action}",
            error="unsupported_action",
        )


def create_orchestrator(
    command_bus: BaseCommandBus,
    jarvis_getter: Optional[Callable[[], Any]] = None,
    ai_router_getter: Optional[Callable[[], Any]] = None,
    max_workers: int = 4,
    autostart: bool = True,
) -> StandaloneOrchestrator:
    """Factory helper for orchestrator creation with optional auto-start."""

    orchestrator = StandaloneOrchestrator(
        command_bus=command_bus,
        jarvis_getter=jarvis_getter,
        ai_router_getter=ai_router_getter,
        max_workers=max_workers,
    )

    if autostart:
        orchestrator.start()

    return orchestrator
