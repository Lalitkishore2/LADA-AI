"""Tests for modules/api_server.py"""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


class TestLADAAPIServer:
    """Tests for LADAAPIServer class"""

    def test_module_loads_dotenv_from_project_root(self, monkeypatch):
        calls = {}

        class _FakeDotenv:
            @staticmethod
            def load_dotenv(path=None):
                calls["path"] = path
                return True

        monkeypatch.setitem(sys.modules, "dotenv", _FakeDotenv)
        monkeypatch.delitem(sys.modules, "modules.api_server", raising=False)

        module = importlib.import_module("modules.api_server")

        assert "path" in calls
        assert Path(str(calls["path"])) == Path(module.__file__).resolve().parents[1] / ".env"

    def test_init_fastapi_available(self):
        # Since FastAPI is installed, just test direct instantiation
        from modules.api_server import LADAAPIServer, FASTAPI_OK
        if not FASTAPI_OK:
            pytest.skip("FastAPI not installed")

        server = LADAAPIServer()
        assert server.host == "0.0.0.0"
        assert server.port == 5000

    def test_init_no_fastapi(self, monkeypatch):
        # Evict cached module so the monkeypatched FASTAPI_OK is read fresh
        import sys, importlib
        monkeypatch.delitem(sys.modules, "modules.api_server", raising=False)

        import modules.api_server as _mod
        monkeypatch.setattr(_mod, "FASTAPI_OK", False)

        server = _mod.LADAAPIServer()
        # With FASTAPI_OK=False the constructor returns early; app must be None
        assert server.app is None

    def test_server_custom_host_port(self, monkeypatch):
        monkeypatch.setattr("modules.api_server.FASTAPI_OK", False)

        from modules.api_server import LADAAPIServer

        server = LADAAPIServer(host="0.0.0.0", port=9000)
        assert server.host == "0.0.0.0"
        assert server.port == 9000

    def test_server_has_start_time(self, monkeypatch):
        import sys
        monkeypatch.delitem(sys.modules, "modules.api_server", raising=False)

        import modules.api_server as _mod
        monkeypatch.setattr(_mod, "FASTAPI_OK", False)

        server = _mod.LADAAPIServer()
        # When FastAPI is not available, _state is not created so start_time is None
        assert server.start_time is None

    def test_server_components_lazy(self, monkeypatch):
        monkeypatch.setattr("modules.api_server.FASTAPI_OK", False)

        from modules.api_server import LADAAPIServer

        server = LADAAPIServer()
        # Components should be None (no state when FastAPI missing)
        assert server.ai_router is None
        assert server.chat_manager is None

    def test_load_components_method_exists(self, monkeypatch):
        monkeypatch.setattr("modules.api_server.FASTAPI_OK", False)

        from modules.api_server import LADAAPIServer

        server = LADAAPIServer()
        # Should have method to load components
        assert hasattr(server, "_load_components")

    def test_auth_middleware_accepts_lowercase_bearer_scheme(self):
        from modules.api_server import LADAAPIServer, FASTAPI_OK
        if not FASTAPI_OK:
            pytest.skip("FastAPI not installed")

        server = LADAAPIServer()
        observed = {}

        def _validate_session_token(token):
            observed["token"] = token
            return token == "token-lower-bearer"

        server._state.validate_session_token = _validate_session_token

        @server.app.get("/protected-probe")
        async def _protected_probe():
            return {"ok": True}

        client = TestClient(server.app)
        response = client.get(
            "/protected-probe",
            headers={"Authorization": "bearer token-lower-bearer"},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert observed["token"] == "token-lower-bearer"


class TestAPIModels:
    """Tests for Pydantic models when FastAPI available"""

    def test_models_defined_when_fastapi_ok(self, monkeypatch):
        # Just verify the module can be imported
        from modules import api_server

        # FASTAPI_OK determines if models are defined
        assert hasattr(api_server, "FASTAPI_OK")


class TestServerStateConfigParsing:
    def test_session_ttl_invalid_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("LADA_WEB_PASSWORD", "pw")
        monkeypatch.setenv("LADA_JWT_SECRET", "secret")
        monkeypatch.setenv("LADA_SESSION_TTL", "not-an-int")

        from modules.api.deps import ServerState

        state = ServerState()
        assert state._session_ttl == 86400

    def test_session_ttl_non_positive_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("LADA_WEB_PASSWORD", "pw")
        monkeypatch.setenv("LADA_JWT_SECRET", "secret")
        monkeypatch.setenv("LADA_SESSION_TTL", "0")

        from modules.api.deps import ServerState

        state = ServerState()
        assert state._session_ttl == 86400

    def test_load_agents_injects_ai_router_for_keyword_only_ctor(self, monkeypatch):
        monkeypatch.setenv("LADA_WEB_PASSWORD", "pw")
        monkeypatch.setenv("LADA_JWT_SECRET", "secret")

        from modules.api.deps import ServerState

        class _KeywordOnlyAgent:
            def __init__(self, *, ai_router):
                self.ai_router = ai_router

        class _ZeroArgAgent:
            def __init__(self):
                self.ready = True

        sentinel_router = object()
        state = ServerState()
        state.ai_router = sentinel_router

        real_import = __import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("modules.agents."):
                requested_name = fromlist[0] if fromlist else "Agent"
                module = SimpleNamespace()
                if name.endswith("flight_agent"):
                    setattr(module, requested_name, _KeywordOnlyAgent)
                else:
                    setattr(module, requested_name, _ZeroArgAgent)
                return module
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr("builtins.__import__", _fake_import)

        state._load_agents()

        assert "flight" in state.agents
        assert state.agents["flight"].ai_router is sentinel_router
