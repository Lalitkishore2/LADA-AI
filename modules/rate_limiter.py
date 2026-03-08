"""
LADA Rate Limiter - Per-provider sliding window rate limiting with circuit breaker.

Used by ProviderManager to prevent hitting provider API rate limits and to
automatically disable providers that are repeatedly failing.
"""
import threading
import time
import logging
from collections import deque
from typing import Tuple, Dict, Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Sliding window rate limiter for a single provider.
    Tracks requests-per-minute and requests-per-day independently.
    Thread-safe.
    """

    def __init__(self, requests_per_minute: int = 60, requests_per_day: int = 10000):
        self.rpm = requests_per_minute
        self.rpd = requests_per_day
        self._minute_window: deque = deque()
        self._day_window: deque = deque()
        self._lock = threading.Lock()

    def acquire(self) -> Tuple[bool, float]:
        """
        Attempt to consume one token.
        Returns (allowed, retry_after_seconds).
        retry_after_seconds is 0.0 when allowed=True.
        """
        now = time.monotonic()
        with self._lock:
            # Evict expired entries
            while self._minute_window and now - self._minute_window[0] >= 60:
                self._minute_window.popleft()
            while self._day_window and now - self._day_window[0] >= 86400:
                self._day_window.popleft()

            # Check per-minute limit
            if len(self._minute_window) >= self.rpm:
                retry_after = 60.0 - (now - self._minute_window[0])
                return False, max(0.0, retry_after)

            # Check per-day limit
            if len(self._day_window) >= self.rpd:
                retry_after = 86400.0 - (now - self._day_window[0])
                return False, max(0.0, retry_after)

            # Consume token
            self._minute_window.append(now)
            self._day_window.append(now)
            return True, 0.0

    def reset(self):
        """Clear all windows (useful for testing)."""
        with self._lock:
            self._minute_window.clear()
            self._day_window.clear()

    def stats(self) -> Dict:
        """Return current usage counts and limits."""
        now = time.monotonic()
        with self._lock:
            # Count valid entries only
            minute_count = sum(1 for t in self._minute_window if now - t < 60)
            day_count = sum(1 for t in self._day_window if now - t < 86400)
        return {
            "requests_this_minute": minute_count,
            "rpm_limit": self.rpm,
            "requests_today": day_count,
            "rpd_limit": self.rpd,
            "minute_available": max(0, self.rpm - minute_count),
            "day_available": max(0, self.rpd - day_count),
        }


class CircuitBreaker:
    """
    Disables a provider temporarily after threshold consecutive failures.
    Auto-resets after backoff_seconds.

    State machine:
      CLOSED  (normal)      -> failures reach threshold -> OPEN
      OPEN    (disabled)    -> backoff expires           -> HALF_OPEN
      HALF_OPEN (one probe) -> next success              -> CLOSED
                            -> next failure              -> OPEN (reset timer)
    """

    def __init__(self, threshold: int = 5, backoff_seconds: float = 60.0):
        self.threshold = threshold
        self.backoff_seconds = backoff_seconds
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def record_success(self):
        """Reset failure count and close the circuit."""
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self):
        """Increment failure count; open circuit if threshold reached."""
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                self._opened_at = time.monotonic()
                logger.warning(
                    f"Circuit breaker opened after {self._failures} failures "
                    f"(backoff: {self.backoff_seconds}s)"
                )

    def is_open(self) -> bool:
        """
        Returns True if the provider should be skipped.
        Transparently transitions OPEN -> HALF_OPEN after backoff expires,
        allowing one probe request through.
        """
        with self._lock:
            if self._opened_at is None:
                return False  # CLOSED
            elapsed = time.monotonic() - self._opened_at
            if elapsed < self.backoff_seconds:
                return True   # OPEN — skip this provider
            # Backoff expired: transition to HALF_OPEN (let one probe through)
            return False

    @property
    def state(self) -> str:
        """Returns 'closed', 'open', or 'half_open'."""
        with self._lock:
            if self._opened_at is None:
                return "closed"
            elapsed = time.monotonic() - self._opened_at
            if elapsed < self.backoff_seconds:
                return "open"
            return "half_open"

    def stats(self) -> Dict:
        """Return circuit breaker state info."""
        with self._lock:
            state = self.state
            remaining = 0.0
            if self._opened_at is not None:
                remaining = max(0.0, self.backoff_seconds - (time.monotonic() - self._opened_at))
        return {
            "state": state,
            "failures": self._failures,
            "threshold": self.threshold,
            "backoff_seconds": self.backoff_seconds,
            "backoff_remaining": round(remaining, 1),
        }


class ProviderRateLimiter:
    """
    Registry of TokenBucket + CircuitBreaker per provider.
    Singleton. Used by ProviderManager during auto_configure() and before each request.
    """

    _instance: Optional['ProviderRateLimiter'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._registry_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'ProviderRateLimiter':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(
        self,
        provider_id: str,
        rpm: int = 60,
        rpd: int = 10000,
        cb_threshold: int = 5,
        cb_backoff: float = 60.0,
    ):
        """
        Register a provider with the given rate limits.
        Idempotent — calling again with the same provider_id re-registers
        (updates limits) without clearing existing window data.
        """
        with self._registry_lock:
            if provider_id not in self._buckets:
                self._buckets[provider_id] = TokenBucket(rpm, rpd)
            else:
                # Update limits without resetting counters
                self._buckets[provider_id].rpm = rpm
                self._buckets[provider_id].rpd = rpd

            if provider_id not in self._breakers:
                self._breakers[provider_id] = CircuitBreaker(cb_threshold, cb_backoff)
            else:
                self._breakers[provider_id].threshold = cb_threshold
                self._breakers[provider_id].backoff_seconds = cb_backoff

        logger.debug(f"Rate limiter registered: {provider_id} ({rpm} RPM, {rpd} RPD)")

    def check(self, provider_id: str) -> Tuple[bool, str]:
        """
        Check whether a request to provider_id is allowed.
        Auto-registers with defaults if provider is unknown.
        Returns (allowed, reason).
        reason is '' when allowed, 'circuit_open' or 'rate_limited' when denied.
        """
        with self._registry_lock:
            if provider_id not in self._buckets:
                # Auto-register with conservative defaults
                self._buckets[provider_id] = TokenBucket()
                self._breakers[provider_id] = CircuitBreaker()

        # Check circuit breaker first (cheaper)
        if self._breakers[provider_id].is_open():
            return False, "circuit_open"

        # Check rate bucket
        allowed, retry_after = self._buckets[provider_id].acquire()
        if not allowed:
            logger.debug(
                f"Rate limit hit for {provider_id} — retry after {retry_after:.1f}s"
            )
            return False, "rate_limited"

        return True, ""

    def record_success(self, provider_id: str):
        """Record a successful request for the given provider."""
        with self._registry_lock:
            if provider_id in self._breakers:
                self._breakers[provider_id].record_success()

    def record_failure(self, provider_id: str):
        """Record a failed request for the given provider."""
        with self._registry_lock:
            if provider_id in self._breakers:
                self._breakers[provider_id].record_failure()

    def get_stats(self) -> Dict:
        """Return rate limiter stats for all registered providers."""
        stats = {}
        with self._registry_lock:
            provider_ids = list(self._buckets.keys())
        for pid in provider_ids:
            stats[pid] = {
                "bucket": self._buckets[pid].stats(),
                "circuit": self._breakers[pid].stats(),
            }
        return stats

    def reset_provider(self, provider_id: str):
        """Reset rate limits and circuit breaker for a provider (testing/admin)."""
        with self._registry_lock:
            if provider_id in self._buckets:
                self._buckets[provider_id].reset()
            if provider_id in self._breakers:
                self._breakers[provider_id].record_success()


def get_rate_limiter() -> ProviderRateLimiter:
    """Get the global ProviderRateLimiter singleton."""
    return ProviderRateLimiter.get_instance()
