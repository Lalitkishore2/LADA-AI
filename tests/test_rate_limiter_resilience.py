"""Resilience tests for half-open circuit breaker behavior."""

import time

from modules.rate_limiter import CircuitBreaker, ProviderRateLimiter


def test_circuit_breaker_half_open_allows_single_probe():
    breaker = CircuitBreaker(threshold=1, backoff_seconds=0.05)

    breaker.record_failure()
    assert breaker.is_open() is True

    time.sleep(0.08)

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


def test_half_open_probe_consumes_minute_token_after_success():
    limiter = ProviderRateLimiter()
    provider_id = "resilience-minute-window"

    limiter.register(provider_id, rpm=1, rpd=100, cb_threshold=1, cb_backoff=0.0)
    limiter.record_failure(provider_id)

    # Backoff is zero, so first check enters HALF_OPEN and allows one probe request.
    allowed_probe, reason_probe = limiter.check(provider_id)
    assert allowed_probe is True
    assert reason_probe == ""

    # Concurrent requests are blocked while probe is in progress.
    allowed_while_probe, reason_while_probe = limiter.check(provider_id)
    assert allowed_while_probe is False
    assert reason_while_probe == "circuit_open"

    # Probe succeeds and circuit closes, but consumed minute token still applies.
    limiter.record_success(provider_id)
    allowed_after_success, reason_after_success = limiter.check(provider_id)
    assert allowed_after_success is False
    assert reason_after_success == "rate_limited"


def test_half_open_probe_consumes_day_token_after_success():
    limiter = ProviderRateLimiter()
    provider_id = "resilience-day-window"

    limiter.register(provider_id, rpm=100, rpd=1, cb_threshold=1, cb_backoff=0.0)
    limiter.record_failure(provider_id)

    allowed_probe, reason_probe = limiter.check(provider_id)
    assert allowed_probe is True
    assert reason_probe == ""

    limiter.record_success(provider_id)
    allowed_after_success, reason_after_success = limiter.check(provider_id)
    assert allowed_after_success is False
    assert reason_after_success == "rate_limited"


def test_half_open_probe_failure_reopens_circuit(monkeypatch):
    limiter = ProviderRateLimiter()
    provider_id = "resilience-probe-failure"

    timeline = iter([100.0, 100.01, 100.08, 100.081, 100.09, 100.10])
    monkeypatch.setattr("modules.rate_limiter.time.monotonic", lambda: next(timeline))

    limiter.register(provider_id, rpm=10, rpd=100, cb_threshold=1, cb_backoff=0.05)
    limiter.record_failure(provider_id)

    # Circuit opens immediately after first failure.
    blocked_open, reason_open = limiter.check(provider_id)
    assert blocked_open is False
    assert reason_open == "circuit_open"

    # After backoff, one probe is allowed.
    allowed_probe, reason_probe = limiter.check(provider_id)
    assert allowed_probe is True
    assert reason_probe == ""

    # Probe failure should re-open the circuit and block immediately.
    limiter.record_failure(provider_id)
    blocked_again, reason_again = limiter.check(provider_id)
    assert blocked_again is False
    assert reason_again == "circuit_open"
