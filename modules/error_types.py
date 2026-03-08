"""
LADA Error Classification System

Replaces silent 'except: continue' patterns with structured,
classified errors that provide:
- User-friendly error messages
- Technical details for logging
- Error categories for retry/recovery decisions
- Stack traces in debug mode

Every error in LADA should flow through this system.
"""

import logging
import traceback
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Classification of error types for routing recovery logic"""
    # Network / connectivity
    TIMEOUT = "timeout"
    CONNECTION_FAILED = "connection_failed"
    DNS_FAILURE = "dns_failure"

    # Authentication / authorization
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    KEY_INVALID = "key_invalid"

    # AI model issues
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTEXT_OVERFLOW = "context_overflow"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"
    CONTENT_FILTERED = "content_filtered"

    # System / resource
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    PROCESS_FAILED = "process_failed"

    # Tool / command
    TOOL_NOT_FOUND = "tool_not_found"
    INVALID_PARAMETERS = "invalid_parameters"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"

    # Module / plugin
    MODULE_UNAVAILABLE = "module_unavailable"
    PLUGIN_ERROR = "plugin_error"

    # General
    UNKNOWN = "unknown"
    INTERNAL = "internal"


class ErrorSeverity(Enum):
    """How severe is this error"""
    INFO = "info"           # Informational, not really an error
    WARNING = "warning"     # Something unexpected, but handled
    ERROR = "error"         # Operation failed, needs user attention
    CRITICAL = "critical"   # System-level failure


@dataclass
class LadaError:
    """
    Structured error with classification, user message, and technical details.
    """
    category: ErrorCategory
    severity: ErrorSeverity
    user_message: str          # Human-friendly message shown to user
    technical_message: str     # Detailed message for logs
    source: str = ""           # Which component raised this (e.g. "ai_router", "comet_agent")
    backend: str = ""          # Which AI backend (e.g. "gemini", "groq")
    recoverable: bool = True   # Can the system retry or recover?
    suggestion: str = ""       # Suggested action for the user
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    exception: Optional[Exception] = field(default=None, repr=False)
    context: Dict[str, Any] = field(default_factory=dict)

    def log(self):
        """Log this error at the appropriate level"""
        msg = f"[{self.source}] {self.category.value}: {self.technical_message}"
        if self.backend:
            msg = f"[{self.source}/{self.backend}] {self.category.value}: {self.technical_message}"

        if self.severity == ErrorSeverity.CRITICAL:
            logger.critical(msg, exc_info=self.exception)
        elif self.severity == ErrorSeverity.ERROR:
            logger.error(msg, exc_info=self.exception)
        elif self.severity == ErrorSeverity.WARNING:
            logger.warning(msg)
        else:
            logger.info(msg)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for audit logging"""
        d = {
            'category': self.category.value,
            'severity': self.severity.value,
            'user_message': self.user_message,
            'technical_message': self.technical_message,
            'source': self.source,
            'backend': self.backend,
            'recoverable': self.recoverable,
            'suggestion': self.suggestion,
            'timestamp': self.timestamp,
        }
        if self.exception:
            d['exception_type'] = type(self.exception).__name__
            d['exception_str'] = str(self.exception)
        if self.context:
            d['context'] = self.context
        return d


# ============================================================
# Factory functions for common error patterns
# ============================================================

def timeout_error(source: str, backend: str, timeout_seconds: float,
                  exception: Optional[Exception] = None) -> LadaError:
    """Create a timeout error"""
    return LadaError(
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.WARNING,
        user_message=f"{backend} is taking too long to respond. Trying next backend...",
        technical_message=f"Timeout after {timeout_seconds}s connecting to {backend}",
        source=source,
        backend=backend,
        recoverable=True,
        suggestion="Check your internet connection or try a different AI backend.",
        exception=exception,
        context={"timeout_seconds": timeout_seconds},
    )


def auth_error(source: str, backend: str,
               exception: Optional[Exception] = None) -> LadaError:
    """Create an authentication error"""
    return LadaError(
        category=ErrorCategory.AUTH_FAILED,
        severity=ErrorSeverity.ERROR,
        user_message=f"Authentication failed for {backend}. Check your API key.",
        technical_message=f"Auth failed for {backend}: {exception}",
        source=source,
        backend=backend,
        recoverable=False,
        suggestion=f"Go to Settings and verify your {backend} API key is correct.",
        exception=exception,
    )


def rate_limit_error(source: str, backend: str, retry_after: float = 0,
                     exception: Optional[Exception] = None) -> LadaError:
    """Create a rate limit error"""
    return LadaError(
        category=ErrorCategory.RATE_LIMITED,
        severity=ErrorSeverity.WARNING,
        user_message=f"{backend} rate limit reached. Switching to another backend...",
        technical_message=f"Rate limited by {backend}, retry after {retry_after}s",
        source=source,
        backend=backend,
        recoverable=True,
        suggestion="Wait a moment and try again, or switch to a different AI backend.",
        exception=exception,
        context={"retry_after": retry_after},
    )


def model_unavailable_error(source: str, backend: str, model: str,
                            exception: Optional[Exception] = None) -> LadaError:
    """Create a model unavailable error"""
    return LadaError(
        category=ErrorCategory.MODEL_UNAVAILABLE,
        severity=ErrorSeverity.WARNING,
        user_message=f"Model {model} is not available on {backend}. Trying alternatives...",
        technical_message=f"Model {model} unavailable on {backend}: {exception}",
        source=source,
        backend=backend,
        recoverable=True,
        exception=exception,
        context={"model": model},
    )


def context_overflow_error(source: str, backend: str, model: str,
                           token_count: int, limit: int) -> LadaError:
    """Create a context window overflow error"""
    return LadaError(
        category=ErrorCategory.CONTEXT_OVERFLOW,
        severity=ErrorSeverity.WARNING,
        user_message="The conversation is too long. Compacting context...",
        technical_message=f"Context overflow: {token_count} tokens > {limit} limit on {model}",
        source=source,
        backend=backend,
        recoverable=True,
        suggestion="Start a new conversation or let LADA auto-compact the context.",
        context={"token_count": token_count, "limit": limit, "model": model},
    )


def empty_response_error(source: str, backend: str) -> LadaError:
    """Create an empty response error"""
    return LadaError(
        category=ErrorCategory.EMPTY_RESPONSE,
        severity=ErrorSeverity.WARNING,
        user_message=f"{backend} returned an empty response. Trying next backend...",
        technical_message=f"Empty response from {backend}",
        source=source,
        backend=backend,
        recoverable=True,
    )


def connection_error(source: str, backend: str, url: str,
                     exception: Optional[Exception] = None) -> LadaError:
    """Create a connection failure error"""
    return LadaError(
        category=ErrorCategory.CONNECTION_FAILED,
        severity=ErrorSeverity.WARNING,
        user_message=f"Cannot connect to {backend}. Trying next backend...",
        technical_message=f"Connection failed to {url}: {exception}",
        source=source,
        backend=backend,
        recoverable=True,
        suggestion="Check your internet connection.",
        exception=exception,
        context={"url": url},
    )


def tool_error(source: str, tool_name: str, message: str,
               exception: Optional[Exception] = None) -> LadaError:
    """Create a tool execution error"""
    return LadaError(
        category=ErrorCategory.TOOL_EXECUTION_FAILED,
        severity=ErrorSeverity.ERROR,
        user_message=f"Failed to execute '{tool_name}': {message}",
        technical_message=f"Tool {tool_name} failed: {message}",
        source=source,
        recoverable=False,
        exception=exception,
        context={"tool_name": tool_name},
    )


def module_error(source: str, module_name: str,
                 exception: Optional[Exception] = None) -> LadaError:
    """Create a module unavailable error"""
    return LadaError(
        category=ErrorCategory.MODULE_UNAVAILABLE,
        severity=ErrorSeverity.INFO,
        user_message="",  # Module failures are silent (graceful degradation)
        technical_message=f"Module {module_name} unavailable: {exception}",
        source=source,
        recoverable=False,
        exception=exception,
        context={"module_name": module_name},
    )


# ============================================================
# Error tracking for session statistics
# ============================================================

class ErrorTracker:
    """
    Tracks errors during a session for reporting and pattern detection.
    """

    def __init__(self, max_history: int = 100):
        self.errors: list = []
        self.max_history = max_history
        self.counts: Dict[str, int] = {}  # category -> count

    def record(self, error: LadaError) -> None:
        """Record an error"""
        error.log()
        self.errors.append(error)
        key = error.category.value
        self.counts[key] = self.counts.get(key, 0) + 1

        # Trim old errors
        if len(self.errors) > self.max_history:
            self.errors = self.errors[-self.max_history:]

    def get_recent(self, count: int = 10) -> list:
        """Get recent errors"""
        return self.errors[-count:]

    def get_counts(self) -> Dict[str, int]:
        """Get error counts by category"""
        return dict(self.counts)

    def is_backend_failing(self, backend: str, threshold: int = 3) -> bool:
        """Check if a backend has failed repeatedly"""
        recent = [
            e for e in self.errors[-20:]
            if e.backend == backend and e.severity in (ErrorSeverity.ERROR, ErrorSeverity.CRITICAL)
        ]
        return len(recent) >= threshold

    def clear(self) -> None:
        """Clear all tracked errors"""
        self.errors.clear()
        self.counts.clear()


# Module-level singleton
_tracker: Optional[ErrorTracker] = None


def get_error_tracker() -> ErrorTracker:
    """Get the global error tracker"""
    global _tracker
    if _tracker is None:
        _tracker = ErrorTracker()
    return _tracker
