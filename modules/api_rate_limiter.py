"""
LADA API Rate Limiter — Per-endpoint and per-user rate limiting.

Provides fixed-window rate limiting for FastAPI endpoints with:
- Per-IP rate limiting for anonymous requests
- Per-user rate limiting for authenticated requests  
- Per-endpoint customizable limits
- In-memory storage (no external dependencies)
- Fixed-window counters with configurable window size

Usage:
    from modules.api_rate_limiter import RateLimiter, rate_limit
    
    limiter = RateLimiter()
    
    @app.get("/chat")
    @rate_limit(limiter, requests=60, window=60)  # 60 req/min
    async def chat(request: Request):
        ...
"""

import os
import time
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
from collections import defaultdict
from dataclasses import dataclass, field
import threading
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    # Default limits
    default_rpm: int = 60       # Requests per minute
    default_rpd: int = 10000    # Requests per day
    
    # Per-endpoint overrides (endpoint path -> limits)
    endpoint_limits: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # Burst allowance (1.5x normal rate for short bursts)
    burst_multiplier: float = 1.5
    
    # Sliding window size (seconds)
    window_size: int = 60
    
    # Cleanup interval (seconds)
    cleanup_interval: int = 300  # 5 minutes


@dataclass  
class RateLimitState:
    """Tracks rate limit state for a client"""
    requests: int = 0
    window_start: float = 0
    daily_requests: int = 0
    daily_reset: float = 0
    
    def reset_if_needed(self, window: int) -> None:
        """Reset counters if window expired"""
        now = time.time()
        if now - self.window_start >= window:
            self.requests = 0
            self.window_start = now
        
        # Daily reset
        if now - self.daily_reset >= 86400:
            self.daily_requests = 0
            self.daily_reset = now


class RateLimiter:
    """
    In-memory rate limiter with token bucket algorithm.
    
    Features:
    - Per-IP tracking for anonymous requests
    - Per-user tracking for authenticated requests
    - Sliding window counters
    - Thread-safe operations
    - Automatic cleanup of stale entries
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._states: Dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        
        # Load config from environment
        self._load_env_config()
        
        logger.info(f"[RateLimiter] Initialized (default: {self.config.default_rpm} RPM, {self.config.default_rpd} RPD)")
    
    def _load_env_config(self):
        """Load configuration from environment variables"""
        if rpm := os.getenv("LADA_API_RPM"):
            try:
                self.config.default_rpm = int(rpm)
            except ValueError:
                pass
        
        if rpd := os.getenv("LADA_API_RPD"):
            try:
                self.config.default_rpd = int(rpd)
            except ValueError:
                pass
    
    def _get_client_key(self, request: Any, user_id: Optional[str] = None) -> str:
        """Generate unique key for rate limiting"""
        if user_id:
            return f"user:{user_id}"
        
        # Get IP from request
        ip = "unknown"
        if hasattr(request, 'client') and request.client:
            ip = request.client.host
        elif hasattr(request, 'headers'):
            # Check X-Forwarded-For for proxied requests
            forwarded = request.headers.get('x-forwarded-for', '')
            if forwarded:
                ip = forwarded.split(',')[0].strip()
        
        return f"ip:{ip}"
    
    def _get_endpoint_limits(self, endpoint: str) -> tuple:
        """Get rate limits for an endpoint"""
        limits = self.config.endpoint_limits.get(endpoint, {})
        rpm = limits.get('rpm', self.config.default_rpm)
        rpd = limits.get('rpd', self.config.default_rpd)
        return rpm, rpd
    
    def check_rate_limit(
        self,
        request: Any,
        endpoint: str = "",
        user_id: Optional[str] = None,
        cost: int = 1,
        requests: Optional[int] = None,
        window: Optional[int] = None
    ) -> tuple:
        """
        Check if request should be rate limited.
        
        Args:
            request: FastAPI request object
            endpoint: Endpoint path (for per-endpoint limits)
            user_id: Authenticated user ID (optional)
            cost: Request cost (default 1, higher for expensive operations)
            requests: Override for max requests per window (optional)
            window: Override for window size in seconds (optional)
        
        Returns:
            (allowed: bool, retry_after: Optional[int], remaining: int)
        """
        client_key = self._get_client_key(request, user_id)
        endpoint_key = f"{client_key}:{endpoint}" if endpoint else client_key
        
        rpm, rpd = self._get_endpoint_limits(endpoint)
        
        # Apply per-decorator overrides if provided
        if requests is not None:
            rpm = requests
        actual_window = window if window is not None else self.config.window_size
        
        with self._lock:
            state = self._states[endpoint_key]
            state.reset_if_needed(actual_window)
            
            # Check minute limit
            if state.requests + cost > int(rpm * self.config.burst_multiplier):
                retry_after = int(actual_window - (time.time() - state.window_start))
                return False, max(1, retry_after), 0
            
            # Check daily limit
            if state.daily_requests + cost > rpd:
                retry_after = int(86400 - (time.time() - state.daily_reset))
                return False, max(1, retry_after), 0
            
            # Allow request
            state.requests += cost
            state.daily_requests += cost
            remaining = rpm - state.requests
            
            # Periodic cleanup
            self._maybe_cleanup()
            
            return True, None, max(0, remaining)
    
    def _maybe_cleanup(self):
        """Periodically clean up stale entries"""
        now = time.time()
        if now - self._last_cleanup < self.config.cleanup_interval:
            return
        
        self._last_cleanup = now
        cutoff = now - 86400  # Remove entries older than 1 day
        
        stale_keys = [
            k for k, v in self._states.items()
            if v.window_start < cutoff and v.daily_reset < cutoff
        ]
        for k in stale_keys:
            del self._states[k]
        
        if stale_keys:
            logger.debug(f"[RateLimiter] Cleaned up {len(stale_keys)} stale entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        with self._lock:
            return {
                'total_clients': len(self._states),
                'config': {
                    'default_rpm': self.config.default_rpm,
                    'default_rpd': self.config.default_rpd,
                    'burst_multiplier': self.config.burst_multiplier,
                },
            }
    
    def reset_client(self, client_key: str):
        """Reset rate limit state for a specific client"""
        with self._lock:
            if client_key in self._states:
                del self._states[client_key]


def rate_limit(
    limiter: RateLimiter,
    requests: int = 60,
    window: int = 60,
    cost: int = 1
):
    """
    Decorator for rate-limiting FastAPI endpoints.
    
    Args:
        limiter: RateLimiter instance
        requests: Max requests per window
        window: Window size in seconds
        cost: Cost per request (for weighted limiting)
    
    Example:
        @app.get("/expensive")
        @rate_limit(limiter, requests=10, window=60, cost=5)
        async def expensive_operation():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from starlette.requests import Request
            from starlette.responses import JSONResponse
            
            # Find request in args or kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get('request')
            
            if request:
                # Get user ID from auth token if available
                user_id = None
                auth_header = request.headers.get('authorization', '')
                if auth_header.startswith('Bearer '):
                    # Hash the token for privacy
                    token_hash = hashlib.sha256(auth_header[7:].encode()).hexdigest()[:16]
                    user_id = token_hash
                
                endpoint = request.url.path
                allowed, retry_after, remaining = limiter.check_rate_limit(
                    request, endpoint, user_id, cost, requests=requests, window=window
                )
                
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Rate limit exceeded",
                            "retry_after": retry_after,
                        },
                        headers={
                            "Retry-After": str(retry_after),
                            "X-RateLimit-Remaining": "0",
                        }
                    )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# FastAPI Middleware for Global Rate Limiting
# ============================================================

class RateLimitMiddleware:
    """
    ASGI middleware for global rate limiting.
    
    Usage:
        from modules.api_rate_limiter import RateLimitMiddleware, RateLimiter
        
        limiter = RateLimiter()
        app.add_middleware(RateLimitMiddleware, limiter=limiter)
    """
    
    def __init__(self, app, limiter: RateLimiter):
        self.app = app
        self.limiter = limiter
        
        # Endpoints exempt from rate limiting
        self.exempt_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        
        # Skip exempt paths
        if path in self.exempt_paths:
            await self.app(scope, receive, send)
            return
        
        # Create a mock request-like object for rate limiting
        class MockRequest:
            def __init__(self, scope):
                self.scope = scope
                # Normalize ASGI headers: list of (bytes, bytes) -> dict with lowercase str keys
                raw_headers = scope.get("headers", [])
                self.headers = {}
                for key, value in raw_headers:
                    if isinstance(key, bytes):
                        key = key.decode('latin-1').lower()
                    if isinstance(value, bytes):
                        value = value.decode('latin-1')
                    self.headers[key] = value
                # Safely extract client host
                client = scope.get("client")
                if client and isinstance(client, (list, tuple)) and len(client) > 0:
                    host = client[0]
                else:
                    host = "unknown"
                self.client = type('Client', (), {'host': host})()
        
        request = MockRequest(scope)
        
        # Check rate limit
        allowed, retry_after, remaining = self.limiter.check_rate_limit(request, path)
        
        if not allowed:
            # Return 429 response
            response_body = b'{"detail": "Rate limit exceeded", "retry_after": %d}' % retry_after
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"retry-after", str(retry_after).encode()],
                    [b"x-ratelimit-remaining", b"0"],
                ],
            })
            await send({
                "type": "http.response.body",
                "body": response_body,
            })
            return
        
        # Add rate limit headers to response
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append([b"x-ratelimit-remaining", str(remaining).encode()])
                message["headers"] = headers
            await send(message)
        
        await self.app(scope, receive, send_with_headers)


# ============================================================
# Singleton access
# ============================================================

_rate_limiter_instance: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def get_api_rate_limiter() -> RateLimiter:
    """Get or create the global API rate limiter instance"""
    global _rate_limiter_instance
    
    if _rate_limiter_instance is None:
        with _rate_limiter_lock:
            if _rate_limiter_instance is None:
                _rate_limiter_instance = RateLimiter()
    
    return _rate_limiter_instance
