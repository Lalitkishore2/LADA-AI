"""Audit logging helpers for remote web control and file access."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

_LOCK = threading.Lock()


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _audit_log_path() -> Path:
    default_path = Path("data") / "audit" / "remote_actions.jsonl"
    configured = os.getenv("LADA_REMOTE_AUDIT_LOG", "").strip()
    if not configured:
        return default_path
    return Path(configured)


def _sanitize_value(value: Any, max_len: int = 512) -> Any:
    if isinstance(value, str):
        cleaned = value.replace("\r", " ").replace("\n", " ").strip()
        if len(cleaned) > max_len:
            return cleaned[:max_len] + "..."
        return cleaned
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v, max_len=max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v, max_len=max_len) for v in value]
    return value


def log_remote_event(event_type: str, success: bool, details: Dict[str, Any]) -> None:
    """Append one JSONL audit event for remote operations.

    Logging is best-effort and must never break request handling.
    """
    if not _bool_env("LADA_REMOTE_AUDIT_ENABLED", True):
        return

    payload = {
        "timestamp": datetime.now().isoformat(),
        "event": str(event_type),
        "success": bool(success),
        "details": _sanitize_value(details or {}),
    }

    path = _audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(payload, ensure_ascii=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
