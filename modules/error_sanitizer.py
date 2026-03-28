"""
Error Sanitization Layer - Prevent internal error details from leaking to clients.

Provides:
- Safe error message generation for external responses
- Internal error logging with full details
- Error classification and appropriate HTTP status codes
- Sensitive data redaction (API keys, file paths, credentials)
- Security-focused error handling

Usage:
    from modules.error_sanitizer import sanitize_error, safe_error_response
    
    try:
        dangerous_operation()
    except Exception as e:
        # Log full error internally
        logger.error(f"Operation failed: {e}")
        # Return sanitized error to client
        return safe_error_response(e, operation="user_query")
"""

import os
import re
import logging
import traceback
from typing import Optional, Dict, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for classification"""
    LOW = "low"           # Minor issues, non-blocking
    MEDIUM = "medium"     # Significant issues, may impact functionality
    HIGH = "high"         # Critical issues, blocks key features
    CRITICAL = "critical" # System-wide failures, immediate action needed


class ErrorCategory(Enum):
    """Error categories for proper HTTP status code mapping"""
    VALIDATION = "validation"       # 400
    AUTHENTICATION = "auth"          # 401
    AUTHORIZATION = "authz"          # 403
    NOT_FOUND = "not_found"         # 404
    CONFLICT = "conflict"           # 409
    RATE_LIMIT = "rate_limit"       # 429
    SERVER_ERROR = "server"         # 500
    BAD_GATEWAY = "bad_gateway"     # 502
    UNAVAILABLE = "unavailable"     # 503
    TIMEOUT = "timeout"             # 504


# Patterns for sensitive data that should be redacted
SENSITIVE_PATTERNS = [
    # API Keys (various formats)
    (r'(sk-[a-zA-Z0-9]{48})', '[API_KEY_REDACTED]'),  # OpenAI
    (r'(xai-[a-zA-Z0-9]{48})', '[API_KEY_REDACTED]'),  # xAI
    (r'(gsk_[a-zA-Z0-9]{50})', '[API_KEY_REDACTED]'),  # Groq
    (r'([a-zA-Z0-9]{39})', '[API_KEY_REDACTED]'),  # Anthropic (39 chars)
    (r'(AIza[0-9A-Za-z-_]{35})', '[API_KEY_REDACTED]'),  # Google
    
    # Tokens
    (r'(Bearer\s+[a-zA-Z0-9_\-\.]+)', 'Bearer [TOKEN_REDACTED]'),
    (r'(token["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-\.]+)', r'\1[TOKEN_REDACTED]'),
    
    # File paths (Windows and Unix) - double backslashes for raw strings
    (r'C:\\\\Users\\\\[^\\\\]+', r'C:\\Users\\[USER]'),
    (r'/home/[^/]+', r'/home/[USER]'),
    (r'/Users/[^/]+', r'/Users/[USER]'),
    
    # IP addresses (internal)
    (r'192\.168\.\d{1,3}\.\d{1,3}', '[INTERNAL_IP]'),
    (r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[INTERNAL_IP]'),
    (r'172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}', '[INTERNAL_IP]'),
    
    # Passwords in URLs or config
    (r'(password["\']?\s*[:=]\s*["\']?)([^"\'}\s]+)', r'\1[PASSWORD_REDACTED]'),
    (r'://[^:]+:([^@]+)@', r'://[USER]:[PASSWORD_REDACTED]@'),
]


def redact_sensitive_data(text: str) -> str:
    """
    Redact sensitive data from error messages or logs.
    
    Args:
        text: Original text that may contain sensitive data
    
    Returns:
        Text with sensitive data replaced by placeholders
    """
    if not text:
        return text
    
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def categorize_error(exception: Exception) -> Tuple[ErrorCategory, int]:
    """
    Categorize an exception and determine appropriate HTTP status code.
    
    Args:
        exception: Exception instance
    
    Returns:
        Tuple of (ErrorCategory, HTTP status code)
    """
    error_type = type(exception).__name__
    error_msg = str(exception).lower()
    
    # Authentication errors
    if any(keyword in error_msg for keyword in ['unauthorized', 'authentication', 'login', 'token invalid']):
        return ErrorCategory.AUTHENTICATION, 401
    
    # Authorization errors
    if any(keyword in error_msg for keyword in ['forbidden', 'permission denied', 'access denied']):
        return ErrorCategory.AUTHORIZATION, 403
    
    # Not found errors
    if any(keyword in error_msg for keyword in ['not found', 'does not exist', 'no such']):
        return ErrorCategory.NOT_FOUND, 404
    
    # Validation errors
    if any(keyword in error_msg for keyword in ['invalid', 'validation', 'bad request', 'malformed']):
        return ErrorCategory.VALIDATION, 400
    
    # Conflict errors
    if any(keyword in error_msg for keyword in ['conflict', 'already exists', 'duplicate']):
        return ErrorCategory.CONFLICT, 409
    
    # Rate limit errors
    if any(keyword in error_msg for keyword in ['rate limit', 'too many requests', 'quota exceeded']):
        return ErrorCategory.RATE_LIMIT, 429
    
    # Timeout errors
    if any(keyword in error_msg for keyword in ['timeout', 'timed out', 'deadline exceeded']):
        return ErrorCategory.TIMEOUT, 504
    
    # Unavailable errors
    if any(keyword in error_msg for keyword in ['unavailable', 'service down', 'connection refused']):
        return ErrorCategory.UNAVAILABLE, 503
    
    # Default to server error
    return ErrorCategory.SERVER_ERROR, 500


def get_user_friendly_message(category: ErrorCategory) -> str:
    """
    Get a user-friendly error message for an error category.
    
    Args:
        category: ErrorCategory
    
    Returns:
        Human-readable error message
    """
    messages = {
        ErrorCategory.VALIDATION: "The request contains invalid data. Please check your input and try again.",
        ErrorCategory.AUTHENTICATION: "Authentication failed. Please check your credentials and try again.",
        ErrorCategory.AUTHORIZATION: "You don't have permission to perform this action.",
        ErrorCategory.NOT_FOUND: "The requested resource was not found.",
        ErrorCategory.CONFLICT: "This action conflicts with the current state. Please refresh and try again.",
        ErrorCategory.RATE_LIMIT: "Too many requests. Please slow down and try again later.",
        ErrorCategory.SERVER_ERROR: "An internal error occurred. Please try again later.",
        ErrorCategory.BAD_GATEWAY: "Unable to reach the upstream service. Please try again later.",
        ErrorCategory.UNAVAILABLE: "The service is temporarily unavailable. Please try again later.",
        ErrorCategory.TIMEOUT: "The request timed out. Please try again.",
    }
    return messages.get(category, "An unexpected error occurred.")


def sanitize_error(
    exception: Exception,
    operation: str = "operation",
    include_category: bool = True
) -> Dict[str, Any]:
    """
    Sanitize an exception for safe external exposure.
    
    Args:
        exception: Original exception
        operation: Human-readable operation name (e.g., "user_query", "file_upload")
        include_category: Whether to include error category in response
    
    Returns:
        Dict with sanitized error info safe for client consumption
    """
    # Categorize error
    category, status_code = categorize_error(exception)
    
    # Get user-friendly message
    user_message = get_user_friendly_message(category)
    
    # Log full error details internally (with stack trace)
    logger.error(
        f"[ErrorSanitizer] {operation} failed: {type(exception).__name__}: {exception}",
        exc_info=True
    )
    
    # Construct sanitized response
    result = {
        "success": False,
        "error": user_message,
        "status_code": status_code,
    }
    
    if include_category:
        result["error_category"] = category.value
    
    # In development mode, optionally include error type (not message)
    if os.getenv("LADA_DEBUG_MODE", "").lower() in ("1", "true", "yes"):
        result["debug_error_type"] = type(exception).__name__
    
    return result


def safe_error_response(
    exception: Exception,
    operation: str = "operation",
    include_trace: bool = False
) -> Dict[str, Any]:
    """
    Generate a safe error response for API endpoints.
    
    Similar to sanitize_error but with additional API-specific fields.
    
    Args:
        exception: Original exception
        operation: Operation name
        include_trace: Whether to include redacted trace (dev mode only)
    
    Returns:
        Dict safe for JSON serialization in API responses
    """
    result = sanitize_error(exception, operation=operation)
    
    # Add trace in dev mode
    if include_trace and os.getenv("LADA_DEBUG_MODE", "").lower() in ("1", "true", "yes"):
        trace = traceback.format_exc()
        result["trace"] = redact_sensitive_data(trace)
    
    return result


class SafeErrorResponse(Exception):
    """
    Exception that carries pre-sanitized error info.
    
    Use this when you want to raise an exception with specific HTTP status
    and user message.
    
    Example:
        raise SafeErrorResponse(
            "Invalid model ID",
            status_code=400,
            category=ErrorCategory.VALIDATION
        )
    """
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        category: Optional[ErrorCategory] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.category = category or ErrorCategory.SERVER_ERROR
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API response"""
        return {
            "success": False,
            "error": self.message,
            "status_code": self.status_code,
            "error_category": self.category.value
        }


def log_error_with_context(
    exception: Exception,
    context: Dict[str, Any],
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
) -> None:
    """
    Log an error with additional context for debugging.
    
    Context is logged separately to avoid leaking in error responses.
    
    Args:
        exception: The exception
        context: Dict with contextual info (user_id, request_id, model, etc.)
        severity: Error severity level
    """
    redacted_context = {k: redact_sensitive_data(str(v)) for k, v in context.items()}
    
    log_func = logger.error
    if severity == ErrorSeverity.CRITICAL:
        log_func = logger.critical
    elif severity == ErrorSeverity.LOW:
        log_func = logger.warning
    
    log_func(
        f"[ErrorContext] {type(exception).__name__}: {exception} | "
        f"Severity: {severity.value} | Context: {redacted_context}",
        exc_info=True
    )
