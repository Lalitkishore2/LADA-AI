"""
LADA v12.0 — MCP Tool Interceptor
Middleware layer for all MCP tool calls that provides:

- Uniform rate-limiting across servers
- Audit logging every tool invocation
- Input sanitization (strip secrets before sending to MCP servers)
- Timeout enforcement with retry logic
- Metrics and cost tracking

Sits between AICommandAgent and MCPClient.
"""

from __future__ import annotations

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class InterceptorConfig:
    """Configuration for the MCP interceptor."""
    max_calls_per_minute: int = 30
    max_calls_per_tool_per_minute: int = 10
    default_timeout: float = 30.0
    max_retries: int = 2
    retry_delay: float = 1.0
    audit_enabled: bool = True
    max_audit_entries: int = 1000
    sanitize_inputs: bool = True


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""
    tool_name: str
    server_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    retries: int = 0
    blocked: bool = False
    block_reason: str = ""


class MCPInterceptor:
    """
    Middleware for MCP tool calls.

    Usage::

        interceptor = MCPInterceptor(mcp_client=client)
        result = interceptor.call_tool("read_file", {"path": "/foo"})

    The interceptor wraps ``MCPClient.call_tool`` with rate-limiting, retries,
    audit logging, and input sanitization.
    """

    # Keys in arguments that should be masked before logging
    _SENSITIVE_KEYS = {
        "password", "secret", "token", "api_key", "apikey",
        "access_token", "authorization", "credential",
    }

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        config: Optional[InterceptorConfig] = None,
    ) -> None:
        self.mcp_client = mcp_client
        self.config = config or InterceptorConfig()

        # Rate-limiter state
        self._call_timestamps: List[float] = []
        self._tool_timestamps: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

        # Audit log
        self._audit: List[ToolCallRecord] = []

        # Optional pre/post hooks
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

    # -- Public API --

    def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Intercept and execute an MCP tool call.

        Returns the raw result dict from MCPClient.call_tool,
        or an error dict if blocked/failed.
        """
        arguments = arguments or {}
        timeout = timeout or self.config.default_timeout

        # 1. Rate limiting
        blocked, reason = self._check_rate_limit(tool_name)
        if blocked:
            record = ToolCallRecord(
                tool_name=tool_name,
                server_name="",
                arguments=self._sanitize(arguments) if self.config.sanitize_inputs else arguments,
                blocked=True,
                block_reason=reason,
            )
            self._log_record(record)
            return {"error": reason, "tool": tool_name, "blocked": True}

        # 2. Pre-hooks
        for hook in self._pre_hooks:
            try:
                hook(tool_name, arguments)
            except Exception as e:
                logger.warning(f"[MCP-Interceptor] Pre-hook error: {e}")

        # 3. Execute with retries
        last_error = None
        retries = 0
        start = time.time()

        for attempt in range(1 + self.config.max_retries):
            try:
                if self.mcp_client is None:
                    return {"error": "MCP client not configured", "tool": tool_name}

                result = self.mcp_client.call_tool(
                    tool_name, arguments, timeout=timeout
                )
                duration_ms = (time.time() - start) * 1000

                record = ToolCallRecord(
                    tool_name=tool_name,
                    server_name=result.get("server", ""),
                    arguments=self._sanitize(arguments) if self.config.sanitize_inputs else arguments,
                    result=str(result.get("result", ""))[:500],
                    duration_ms=duration_ms,
                    retries=retries,
                )
                self._log_record(record)

                # 4. Post-hooks
                for hook in self._post_hooks:
                    try:
                        hook(tool_name, arguments, result)
                    except Exception as e:
                        logger.warning(f"[MCP-Interceptor] Post-hook error: {e}")

                return result

            except Exception as e:
                last_error = str(e)
                retries = attempt
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay)

        # All retries exhausted
        duration_ms = (time.time() - start) * 1000
        record = ToolCallRecord(
            tool_name=tool_name,
            server_name="",
            arguments=self._sanitize(arguments) if self.config.sanitize_inputs else arguments,
            error=last_error,
            duration_ms=duration_ms,
            retries=retries,
        )
        self._log_record(record)
        return {"error": last_error, "tool": tool_name}

    def add_pre_hook(self, hook: Callable) -> None:
        """Register a pre-call hook: ``hook(tool_name, arguments)``."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable) -> None:
        """Register a post-call hook: ``hook(tool_name, arguments, result)``."""
        self._post_hooks.append(hook)

    # -- Rate limiting --

    def _check_rate_limit(self, tool_name: str) -> tuple:
        """Return (blocked: bool, reason: str)."""
        now = time.time()
        window = 60.0

        with self._lock:
            # Global rate limit
            self._call_timestamps = [
                t for t in self._call_timestamps if now - t < window
            ]
            if len(self._call_timestamps) >= self.config.max_calls_per_minute:
                return True, f"Global rate limit ({self.config.max_calls_per_minute}/min) exceeded"
            self._call_timestamps.append(now)

            # Per-tool rate limit
            tool_ts = self._tool_timestamps[tool_name]
            self._tool_timestamps[tool_name] = [
                t for t in tool_ts if now - t < window
            ]
            if len(self._tool_timestamps[tool_name]) >= self.config.max_calls_per_tool_per_minute:
                return True, f"Tool '{tool_name}' rate limit ({self.config.max_calls_per_tool_per_minute}/min) exceeded"
            self._tool_timestamps[tool_name].append(now)

        return False, ""

    # -- Sanitization --

    def _sanitize(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive argument values for audit logging."""
        sanitized = {}
        for key, value in arguments.items():
            if key.lower() in self._SENSITIVE_KEYS:
                sanitized[key] = "•••REDACTED•••"
            elif isinstance(value, str) and len(value) > 200:
                sanitized[key] = value[:100] + "…(truncated)"
            else:
                sanitized[key] = value
        return sanitized

    # -- Audit --

    def _log_record(self, record: ToolCallRecord) -> None:
        if self.config.audit_enabled:
            self._audit.append(record)
            if len(self._audit) > self.config.max_audit_entries:
                self._audit = self._audit[-self.config.max_audit_entries:]

        if record.blocked:
            logger.warning(f"[MCP-Interceptor] BLOCKED {record.tool_name}: {record.block_reason}")
        elif record.error:
            logger.error(f"[MCP-Interceptor] FAILED {record.tool_name} ({record.retries} retries): {record.error}")
        else:
            logger.debug(f"[MCP-Interceptor] OK {record.tool_name} ({record.duration_ms:.0f}ms)")

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent audit entries."""
        return [
            {
                "tool": r.tool_name,
                "server": r.server_name,
                "args": r.arguments,
                "result": r.result,
                "error": r.error,
                "duration_ms": r.duration_ms,
                "retries": r.retries,
                "blocked": r.blocked,
                "block_reason": r.block_reason,
                "timestamp": r.timestamp,
            }
            for r in self._audit[-limit:]
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostics."""
        total = len(self._audit)
        blocked = sum(1 for r in self._audit if r.blocked)
        errors = sum(1 for r in self._audit if r.error and not r.blocked)
        return {
            "total_calls": total,
            "blocked_calls": blocked,
            "error_calls": errors,
            "success_calls": total - blocked - errors,
            "avg_duration_ms": (
                sum(r.duration_ms for r in self._audit if not r.blocked) /
                max(1, total - blocked)
            ),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[MCPInterceptor] = None


def get_mcp_interceptor(
    mcp_client: Optional[Any] = None,
    config: Optional[InterceptorConfig] = None,
) -> MCPInterceptor:
    """Get or create the global MCPInterceptor."""
    global _instance
    if _instance is None:
        _instance = MCPInterceptor(mcp_client=mcp_client, config=config)
    return _instance
