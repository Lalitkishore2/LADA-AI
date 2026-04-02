"""Resilience tests for half-open circuit breaker behavior."""

import time

from modules.rate_limiter import CircuitBreaker, ProviderRateLimiter


def test_circuit_breaker_half_open_allows_single_probe():
    breaker = CircuitBreaker(threshold=1, backoff_seconds=0.05)

    breaker.record_failure()
    assert breaker.is_open() is True

    time.sleep(0.06)

    # First call after backoff should be allowed as a probe.
    assert breaker.is_open() is False

    # Additional concurrent attempts are blocked until probe resolves.
    assert breaker.is_open() is True

    breaker.record_success()
    assert breaker.is_open() is False


def test_rate_limited_probe_releases_half_open_gate():
    limiter = ProviderRateLimiter()
    provider_id = "resilience-provider"

    # rpm=0 forces bucket denials; threshold=1 + backoff=0 puts breaker in HALF_OPEN immediately.
    limiter.register(provider_id, rpm=0, rpd=100, cb_threshold=1, cb_backoff=0.0)
    limiter.record_failure(provider_id)

    allowed1, reason1 = limiter.check(provider_id)
    assert allowed1 is False
    assert reason1 == "rate_limited"

    # If probe lock is released correctly, second check is also rate-limited (not circuit_open).
    allowed2, reason2 = limiter.check(provider_id)
    assert allowed2 is False
    assert reason2 == "rate_limited"
