"""Tests for modules/api_rate_limiter.py behavior and parsing edge cases."""

import hashlib
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from modules.api_rate_limiter import RateLimiter, rate_limit


class _CapturingLimiter:
    def __init__(self):
        self.calls = []

    def check_rate_limit(self, request, endpoint="", user_id=None, cost=1, requests=None, window=None):
        self.calls.append(
            {
                "endpoint": endpoint,
                "user_id": user_id,
                "cost": cost,
                "requests": requests,
                "window": window,
            }
        )
        return True, None, 99


def test_get_client_key_prefers_forwarded_for_over_proxy_client():
    limiter = RateLimiter()

    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1"},
        client=SimpleNamespace(host="10.0.0.1"),
    )

    key = limiter._get_client_key(request)

    assert key == "ip:203.0.113.5"


def test_rate_limit_decorator_accepts_lowercase_bearer_scheme():
    limiter = _CapturingLimiter()

    app = FastAPI()

    @app.get("/limited")
    @rate_limit(limiter, requests=10, window=60)
    async def limited(request: Request):
        _ = request
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/limited", headers={"Authorization": "bearer lower-token-value"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(limiter.calls) == 1

    expected_hash = hashlib.sha256("lower-token-value".encode()).hexdigest()[:16]
    assert limiter.calls[0]["user_id"] == expected_hash
