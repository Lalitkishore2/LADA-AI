"""Tests for marketplace router error sanitization."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.marketplace import create_marketplace_router


class _ExplodingMarketplace:
    def __init__(self, error_message: str):
        self._error_message = error_message

    def list_available(self, category=None, search=None):
        raise RuntimeError(self._error_message)

    def get_stats(self):
        return {}


class _HappyMarketplace:
    def list_available(self, category=None, search=None):
        _ = (category, search)
        return [{"name": "demo-plugin"}]

    def get_stats(self):
        return {"count": 1}


def test_marketplace_list_sanitizes_internal_errors(monkeypatch):
    sensitive_key = "sk-" + ("z" * 48)
    message = f"marketplace backend failed with token {sensitive_key}"

    monkeypatch.setattr(
        "modules.plugin_marketplace.get_marketplace",
        lambda: _ExplodingMarketplace(message),
    )

    app = FastAPI()
    app.include_router(create_marketplace_router(object()))
    client = TestClient(app)

    response = client.get("/marketplace")

    assert response.status_code == 500
    detail = response.json().get("detail", "")
    assert sensitive_key not in detail


def test_marketplace_list_propagates_request_id_header(monkeypatch):
    monkeypatch.setattr(
        "modules.plugin_marketplace.get_marketplace",
        lambda: _HappyMarketplace(),
    )

    app = FastAPI()
    app.include_router(create_marketplace_router(object()))
    client = TestClient(app)

    response = client.get("/marketplace", headers={"X-Request-ID": "marketplace-req-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "marketplace-req-1"
    assert response.json()["success"] is True
