"""Live smoke test for LADA browser compatibility endpoints.

This test is intentionally env-gated and runs only when a real API server and
browser gateway are available.
"""

import os
import socket
from urllib.parse import urlparse

import pytest

requests = pytest.importorskip("requests")

pytestmark = [pytest.mark.integration]


def _enabled() -> bool:
    return os.getenv("LADA_RUN_LIVE_BROWSER_SMOKE", os.getenv("LADA_RUN_LIVE_OPENCLAW_SMOKE", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _gateway_reachable(gateway_url: str) -> bool:
    parsed = urlparse(gateway_url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "wss":
        port = 443
    else:
        port = 80

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


@pytest.mark.skipif(
    not _enabled(),
    reason="Set LADA_RUN_LIVE_BROWSER_SMOKE=1 to run live browser smoke tests",
)
def test_live_lada_browser_smoke_matrix():
    base_url = os.getenv("LADA_LIVE_API_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    gateway_url = os.getenv("LADA_BROWSER_GATEWAY_URL", "ws://127.0.0.1:18789")
    bearer = os.getenv("LADA_LIVE_API_BEARER_TOKEN", "").strip()

    if not _gateway_reachable(gateway_url):
        pytest.skip(f"Browser gateway not reachable at {gateway_url}")

    headers = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    session = requests.Session()

    def call(method: str, path: str, payload=None):
        url = f"{base_url}{path}"
        resp = session.request(method=method, url=url, json=payload, headers=headers, timeout=20)
        assert resp.status_code < 500, f"{method} {path} failed with {resp.status_code}: {resp.text}"
        return resp

    status = call("GET", "/lada/browser/status").json()
    assert status.get("success") is True

    connect = call("POST", "/lada/browser/connect").json()
    assert connect.get("success") is True

    navigate = call("POST", "/lada/browser/navigate", {"url": "https://example.com"}).json()
    assert navigate.get("success") is True

    action = call("POST", "/lada/browser/action", {"action": "scroll", "direction": "down", "amount": 200}).json()
    assert action.get("success") is True

    snapshot = call("GET", "/lada/browser/snapshot").json()
    assert snapshot.get("success") is True

    disconnect = call("POST", "/lada/browser/disconnect").json()
    assert disconnect.get("success") is True
