"""Tests for OpenAI-compatible /v1/models fallback behavior."""

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.openai_compat import create_openai_compat_router


class _Entry:
    def __init__(self, model_id: str, provider: str):
        self.id = model_id
        self.provider = provider


class _FakeModelRegistry:
    def __init__(self, entries):
        self._entries = entries

    def list_available_models(self):
        return list(self._entries)


class _FakeProviderManager:
    def __init__(self, model_registry):
        self.model_registry = model_registry


class _FailingProviderResponse:
    def __init__(self, error: str):
        self.success = False
        self.error = error


class _FailingProvider:
    provider_id = "test-provider"

    def __init__(self, error: str):
        self._error = error

    def complete_with_retry(self, messages, model_id, temperature, max_tokens):
        return _FailingProviderResponse(self._error)


class _FailingProviderManager:
    def __init__(self, error: str):
        self.model_registry = _FakeModelRegistry([])
        self._provider = _FailingProvider(error)
        self._rate_limiter = None

    def get_provider_for_model(self, model_id):
        return self._provider


class _MissingProviderManager:
    def __init__(self):
        self.model_registry = _FakeModelRegistry([])
        self._rate_limiter = None

    def get_provider_for_model(self, model_id):
        return None


class _FakeRouter:
    def __init__(self, entries, dropdown_items):
        self.provider_manager = _FakeProviderManager(_FakeModelRegistry(entries))
        self._dropdown_items = dropdown_items

    def get_provider_dropdown_items(self):
        return list(self._dropdown_items)


class _FakeState:
    def __init__(self, router):
        self.start_time = datetime.now()
        self.ai_router = router

    def load_components(self):
        return None


def _build_client(state):
    app = FastAPI()
    app.include_router(create_openai_compat_router(state))
    return TestClient(app)


def test_v1_models_uses_registry_and_excludes_ollama_local(monkeypatch):
    monkeypatch.setenv("LADA_API_KEY", "")

    entries = [
        _Entry("llama3.1:8b", "ollama-local"),
        _Entry("gpt-4o-mini", "openai"),
    ]
    router = _FakeRouter(entries=entries, dropdown_items=[])
    client = _build_client(_FakeState(router))

    resp = client.get("/v1/models", headers={"X-Request-ID": "openai-models-req-1"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "openai-models-req-1"
    data = resp.json()["data"]
    ids = {item["id"] for item in data}

    assert "auto" in ids
    assert "gpt-4o-mini" in ids
    assert "llama3.1:8b" not in ids


def test_v1_models_falls_back_to_dropdown_when_registry_empty(monkeypatch):
    monkeypatch.setenv("LADA_API_KEY", "")

    dropdown = [
        {"label": "Auto (Best Available)", "value": "auto", "provider": "lada", "available": True},
        {"label": "Gemini 2.5 (offline)", "value": "gemini-2.5", "provider": "google", "available": False},
        {"label": "GPT-4o mini", "value": "gpt-4o-mini", "provider": "openai", "available": True},
    ]
    router = _FakeRouter(entries=[], dropdown_items=dropdown)
    client = _build_client(_FakeState(router))

    resp = client.get("/v1/models", headers={"X-Request-ID": "openai-fallback-req-1"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "openai-fallback-req-1"
    data = resp.json()["data"]
    ids = {item["id"] for item in data}

    assert "auto" in ids
    assert "gpt-4o-mini" in ids
    assert "gemini-2.5" not in ids


def test_v1_chat_completions_sanitizes_provider_error(monkeypatch):
    monkeypatch.setenv("LADA_API_KEY", "")

    sensitive_key = "gsk_" + ("c" * 50)

    class _Router:
        def __init__(self):
            self.provider_manager = _FailingProviderManager(
                f"provider rejected request with key {sensitive_key}"
            )
            self.system_prompt = ""

    client = _build_client(_FakeState(_Router()))
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )

    assert response.status_code == 502
    detail = response.json().get("detail", "")
    assert sensitive_key not in detail


def test_v1_chat_completions_stream_invalid_model_returns_404(monkeypatch):
    monkeypatch.setenv("LADA_API_KEY", "")

    class _Router:
        def __init__(self):
            self.provider_manager = _MissingProviderManager()
            self.system_prompt = ""

    client = _build_client(_FakeState(_Router()))
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "missing-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 404
    assert "missing-model" in response.json().get("detail", "")
