"""Tests for modules/api_server.py"""
import sys
from unittest.mock import MagicMock

import pytest


class TestLADAAPIServer:
    """Tests for LADAAPIServer class"""

    def test_init_fastapi_available(self):
        # Since FastAPI is installed, just test direct instantiation
        from modules.api_server import LADAAPIServer, FASTAPI_OK
        if not FASTAPI_OK:
            pytest.skip("FastAPI not installed")

        server = LADAAPIServer()
        assert server.host == "0.0.0.0"
        assert server.port == 5000

    def test_init_no_fastapi(self, monkeypatch):
        monkeypatch.setattr("modules.api_server.FASTAPI_OK", False)

        from modules.api_server import LADAAPIServer

        server = LADAAPIServer()
        # Should not have app attribute or it should be None
        assert not hasattr(server, "app") or server.app is None

    def test_server_custom_host_port(self, monkeypatch):
        monkeypatch.setattr("modules.api_server.FASTAPI_OK", False)

        from modules.api_server import LADAAPIServer

        server = LADAAPIServer(host="0.0.0.0", port=9000)
        assert server.host == "0.0.0.0"
        assert server.port == 9000

    def test_server_has_start_time(self, monkeypatch):
        monkeypatch.setattr("modules.api_server.FASTAPI_OK", False)

        from modules.api_server import LADAAPIServer

        server = LADAAPIServer()
        # When FastAPI is not available, state is not created
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


class TestAPIModels:
    """Tests for Pydantic models when FastAPI available"""

    def test_models_defined_when_fastapi_ok(self, monkeypatch):
        # Just verify the module can be imported
        from modules import api_server

        # FASTAPI_OK determines if models are defined
        assert hasattr(api_server, "FASTAPI_OK")
