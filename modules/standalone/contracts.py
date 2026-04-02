"""Typed command and event envelopes for standalone services."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

VALID_TARGETS = {
    "system",
    "ai",
    "browser",
    "comet",
    "voice",
    "plugin",
    "specialist",
    "orchestrator",
}

VALID_PERMISSION_LEVELS = {"safe", "moderate", "dangerous", "critical"}

VALID_STATUSES = {
    "accepted",
    "running",
    "completed",
    "failed",
    "rejected",
}

VALID_EVENT_TYPES = {
    "command.accepted",
    "command.started",
    "command.progress",
    "command.completed",
    "command.failed",
    "command.rejected",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class RetryPolicy:
    """Retry behavior attached to command envelopes."""

    max_attempts: int = 1
    initial_backoff_ms: int = 500
    max_backoff_ms: int = 5000

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("retry.max_attempts must be >= 1")
        if self.initial_backoff_ms < 0:
            raise ValueError("retry.initial_backoff_ms must be >= 0")
        if self.max_backoff_ms < self.initial_backoff_ms:
            raise ValueError("retry.max_backoff_ms must be >= retry.initial_backoff_ms")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "initial_backoff_ms": self.initial_backoff_ms,
            "max_backoff_ms": self.max_backoff_ms,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RetryPolicy":
        data = data or {}
        return cls(
            max_attempts=int(data.get("max_attempts", 1)),
            initial_backoff_ms=int(data.get("initial_backoff_ms", 500)),
            max_backoff_ms=int(data.get("max_backoff_ms", 5000)),
        )


@dataclass
class SafetyMetadata:
    """Safety and permission metadata attached to commands."""

    permission_level: str = "safe"
    requires_confirmation: bool = False
    dry_run: bool = False
    reason: str = ""

    def validate(self) -> None:
        if self.permission_level not in VALID_PERMISSION_LEVELS:
            allowed = ", ".join(sorted(VALID_PERMISSION_LEVELS))
            raise ValueError(f"safety.permission_level must be one of: {allowed}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "permission_level": self.permission_level,
            "requires_confirmation": self.requires_confirmation,
            "dry_run": self.dry_run,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SafetyMetadata":
        data = data or {}
        return cls(
            permission_level=str(data.get("permission_level", "safe")),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            dry_run=bool(data.get("dry_run", False)),
            reason=str(data.get("reason", "")),
        )


@dataclass
class CommandEnvelope:
    """Canonical command envelope sent through the command bus."""

    command_id: str = field(default_factory=lambda: _new_id("cmd"))
    correlation_id: str = field(default_factory=lambda: _new_id("corr"))
    source: str = "unknown"
    target: str = "system"
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at_ms: int = field(default_factory=_now_ms)
    timeout_ms: int = 60000
    idempotency_key: Optional[str] = None
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    safety: SafetyMetadata = field(default_factory=SafetyMetadata)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.command_id:
            raise ValueError("command_id is required")
        if not self.correlation_id:
            raise ValueError("correlation_id is required")
        if not self.source:
            raise ValueError("source is required")
        if self.target not in VALID_TARGETS:
            allowed = ", ".join(sorted(VALID_TARGETS))
            raise ValueError(f"target must be one of: {allowed}")
        if not self.action and not self.payload:
            raise ValueError("action or payload must be provided")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be > 0")

        self.retry.validate()
        self.safety.validate()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "source": self.source,
            "target": self.target,
            "action": self.action,
            "payload": self.payload,
            "created_at_ms": self.created_at_ms,
            "timeout_ms": self.timeout_ms,
            "idempotency_key": self.idempotency_key,
            "retry": self.retry.to_dict(),
            "safety": self.safety.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandEnvelope":
        envelope = cls(
            command_id=str(data.get("command_id") or _new_id("cmd")),
            correlation_id=str(data.get("correlation_id") or _new_id("corr")),
            source=str(data.get("source", "unknown")),
            target=str(data.get("target", "system")),
            action=str(data.get("action", "")).strip(),
            payload=dict(data.get("payload") or {}),
            created_at_ms=int(data.get("created_at_ms", _now_ms())),
            timeout_ms=int(data.get("timeout_ms", 60000)),
            idempotency_key=(
                str(data.get("idempotency_key"))
                if data.get("idempotency_key") is not None
                else None
            ),
            retry=RetryPolicy.from_dict(data.get("retry")),
            safety=SafetyMetadata.from_dict(data.get("safety")),
            metadata=dict(data.get("metadata") or {}),
        )
        envelope.validate()
        return envelope


@dataclass
class CommandResult:
    """Unified result object returned by command handlers."""

    success: bool
    message: str
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "output": self.output,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandResult":
        return cls(
            success=bool(data.get("success", False)),
            message=str(data.get("message", "")),
            output=dict(data.get("output") or {}),
            error=str(data.get("error")) if data.get("error") else None,
        )


@dataclass
class EventEnvelope:
    """Canonical event envelope emitted by orchestrator and daemons."""

    event_id: str = field(default_factory=lambda: _new_id("evt"))
    command_id: str = ""
    correlation_id: str = ""
    event_type: str = "command.accepted"
    source: str = "orchestrator"
    status: str = "accepted"
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = field(default_factory=_now_ms)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if not self.command_id:
            raise ValueError("command_id is required")
        if not self.correlation_id:
            raise ValueError("correlation_id is required")
        if self.event_type not in VALID_EVENT_TYPES:
            allowed = ", ".join(sorted(VALID_EVENT_TYPES))
            raise ValueError(f"event_type must be one of: {allowed}")
        if self.status not in VALID_STATUSES:
            allowed = ", ".join(sorted(VALID_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type,
            "source": self.source,
            "status": self.status,
            "payload": self.payload,
            "timestamp_ms": self.timestamp_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventEnvelope":
        event = cls(
            event_id=str(data.get("event_id") or _new_id("evt")),
            command_id=str(data.get("command_id", "")),
            correlation_id=str(data.get("correlation_id", "")),
            event_type=str(data.get("event_type", "command.accepted")),
            source=str(data.get("source", "orchestrator")),
            status=str(data.get("status", "accepted")),
            payload=dict(data.get("payload") or {}),
            timestamp_ms=int(data.get("timestamp_ms", _now_ms())),
            metadata=dict(data.get("metadata") or {}),
        )
        event.validate()
        return event


def make_event(
    command: CommandEnvelope,
    event_type: str,
    status: str,
    payload: Optional[Dict[str, Any]] = None,
    source: str = "orchestrator",
    metadata: Optional[Dict[str, Any]] = None,
) -> EventEnvelope:
    """Create a validated event for a command lifecycle update."""

    event = EventEnvelope(
        command_id=command.command_id,
        correlation_id=command.correlation_id,
        event_type=event_type,
        source=source,
        status=status,
        payload=payload or {},
        metadata=metadata or {},
    )
    event.validate()
    return event
