"""Rate limiter boundary and retry-after behavior tests."""

import uuid

from modules.rate_limiter import ProviderRateLimiter, TokenBucket


def test_token_bucket_minute_limit_returns_retry_after(monkeypatch):
    bucket = TokenBucket(requests_per_minute=2, requests_per_day=100)
    timeline = iter([100.0, 100.1, 129.5])
    monkeypatch.setattr("modules.rate_limiter.time.monotonic", lambda: next(timeline))

    allowed1, retry1 = bucket.acquire()
    allowed2, retry2 = bucket.acquire()
    allowed3, retry3 = bucket.acquire()

    assert allowed1 is True and retry1 == 0.0
    assert allowed2 is True and retry2 == 0.0
    assert allowed3 is False
    assert 30.4 < retry3 < 30.6


def test_token_bucket_day_limit_returns_retry_after(monkeypatch):
    bucket = TokenBucket(requests_per_minute=100, requests_per_day=2)
    timeline = iter([1000.0, 1000.1, 1000.2])
    monkeypatch.setattr("modules.rate_limiter.time.monotonic", lambda: next(timeline))

    allowed1, _ = bucket.acquire()
    allowed2, _ = bucket.acquire()
    allowed3, retry3 = bucket.acquire()

    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is False
    assert 86399.7 < retry3 < 86399.9


def test_register_updates_limits_without_resetting_window():
    limiter = ProviderRateLimiter()
    provider_id = f"reregister-{uuid.uuid4().hex}"

    limiter.register(provider_id, rpm=1, rpd=100)
    allowed1, reason1 = limiter.check(provider_id)
    allowed2, reason2 = limiter.check(provider_id)

    assert allowed1 is True
    assert reason1 == ""
    assert allowed2 is False
    assert reason2 == "rate_limited"

    # Re-register with a higher RPM should keep prior window data but update limits.
    limiter.register(provider_id, rpm=2, rpd=100)
    allowed3, reason3 = limiter.check(provider_id)

    assert allowed3 is True
    assert reason3 == ""


def test_unknown_provider_auto_registers_on_first_check():
    limiter = ProviderRateLimiter()
    provider_id = f"auto-{uuid.uuid4().hex}"

    allowed, reason = limiter.check(provider_id)
    stats = limiter.get_stats()

    assert allowed is True
    assert reason == ""
    assert provider_id in stats


def test_circuit_open_short_circuits_before_bucket_consumption():
    limiter = ProviderRateLimiter()
    provider_id = f"circuit-first-{uuid.uuid4().hex}"

    limiter.register(provider_id, rpm=1, rpd=100, cb_threshold=1, cb_backoff=60.0)
    limiter.record_failure(provider_id)  # Opens circuit immediately at threshold=1

    allowed, reason = limiter.check(provider_id)
    stats = limiter.get_stats()[provider_id]

    assert allowed is False
    assert reason == "circuit_open"
    assert stats["bucket"]["requests_this_minute"] == 0


def test_rate_limit_isolation_between_providers():
    limiter = ProviderRateLimiter()
    provider_one = f"iso-one-{uuid.uuid4().hex}"
    provider_two = f"iso-two-{uuid.uuid4().hex}"

    limiter.register(provider_one, rpm=1, rpd=100)
    limiter.register(provider_two, rpm=5, rpd=100)

    allowed_1a, reason_1a = limiter.check(provider_one)
    allowed_1b, reason_1b = limiter.check(provider_one)
    allowed_2a, reason_2a = limiter.check(provider_two)

    assert allowed_1a is True
    assert reason_1a == ""
    assert allowed_1b is False
    assert reason_1b == "rate_limited"
    assert allowed_2a is True
    assert reason_2a == ""
