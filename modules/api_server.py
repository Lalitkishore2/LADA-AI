"""
LADA v8.0 - API Server & WebSocket Gateway
FastAPI REST endpoints + WebSocket real-time messaging for external access.

This file is a thin assembler. All route logic lives in modules/api/routers/.
"""

import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import FastAPI
try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False
    logger.warning("[APIServer] FastAPI not installed. Run: pip install fastapi uvicorn")


# Re-export Pydantic models for backward compatibility
if FASTAPI_OK:
    from modules.api.models import (  # noqa: F401
        ChatRequest, ChatResponse, AgentRequest, AgentResponse,
        ConversationInfo, HealthResponse, OpenAIChatMessage, OpenAIChatRequest,
    )


# ============================================================
# API SERVER CLASS
# ============================================================

class LADAAPIServer:
    """
    FastAPI-based REST API server + WebSocket gateway for LADA.

    All route logic is delegated to modules/api/routers/.
    This class only handles app creation, middleware, and server lifecycle.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        self.host = host
        self.port = port
        self._state = None

        if not FASTAPI_OK:
            logger.error("[APIServer] FastAPI not available")
            return

        # Shared server state
        from modules.api.deps import ServerState, REQUEST_ID_HEADER, ensure_request_id
        self._state = ServerState()

        # Create FastAPI app
        self.app = FastAPI(
            title="LADA API",
            description="LADA v8.0 REST API - Your AI Assistant",
            version="8.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
        )

        # CORS middleware - Restrict to specific origins for security
        allowed_origins = os.getenv("LADA_CORS_ORIGINS", "")
        if allowed_origins:
            # Use specific origins from env var (comma-separated), filter empty strings
            origins_list = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]
            logger.info(f"[APIServer] CORS enabled for specific origins: {origins_list}")
        else:
            # Default: localhost/127.0.0.1 on common ports for development
            origins_list = [
                "http://localhost:3000",
                "http://localhost:5000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5000",
            ]
            logger.warning("[APIServer] CORS using default localhost origins. Set LADA_CORS_ORIGINS for production.")
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins_list,  # Specific origins only
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

        # Rate limiting middleware (applied before auth)
        try:
            from modules.api_rate_limiter import RateLimitMiddleware, get_api_rate_limiter
            rate_limiter = get_api_rate_limiter()
            self.app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
            logger.info("[APIServer] Rate limiting enabled")
        except ImportError:
            logger.warning("[APIServer] Rate limiting not available")

        # Session auth middleware
        @self.app.middleware("http")
        async def auth_middleware(request, call_next):
            request_id = ensure_request_id(request, prefix="http")

            def _with_request_id(response):
                response.headers[REQUEST_ID_HEADER] = request_id
                return response

            path = request.url.path
            public_paths = [
                "/auth/login", "/health", "/docs", "/redoc", "/openapi.json",
                "/app", "/dashboard",
            ]
            if any(path == p or path.startswith(p + "/") for p in public_paths):
                return _with_request_id(await call_next(request))
            if path.startswith("/static"):
                return _with_request_id(await call_next(request))
            if path == "/":
                return _with_request_id(await call_next(request))
            if path.startswith("/v1/"):
                return _with_request_id(await call_next(request))

            auth_header = request.headers.get("authorization", "")
            token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
            if not token:
                token = request.query_params.get("token", "")

            if not self._state.validate_session_token(token):
                from starlette.responses import JSONResponse as SJR
                return _with_request_id(SJR(status_code=401, content={"detail": "Authentication required"}))

            return _with_request_id(await call_next(request))

        # ── Register routers ─────────────────────────────────
        from modules.api.routers.auth import create_auth_router
        from modules.api.routers.chat import create_chat_router
        from modules.api.routers.marketplace import create_marketplace_router
        from modules.api.routers.app import create_app_router
        from modules.api.routers.orchestration import create_orchestration_router
        from modules.api.routers.openai_compat import create_openai_compat_router
        from modules.api.routers.lada_browser_compat import create_lada_browser_compat_router
        from modules.api.routers.websocket import create_ws_router

        self.app.include_router(create_auth_router(self._state))
        self.app.include_router(create_chat_router(self._state))
        self.app.include_router(create_marketplace_router(self._state))
        self.app.include_router(create_app_router(self._state))
        self.app.include_router(create_orchestration_router(self._state))
        self.app.include_router(create_openai_compat_router(self._state))
        self.app.include_router(create_lada_browser_compat_router(self._state))
        self.app.include_router(create_ws_router(self._state))

        # Mount static files
        dashboard_dir = Path(__file__).parent.parent / "web"
        if dashboard_dir.exists():
            try:
                self.app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="static")
            except Exception as e:
                logger.warning(f"[APIServer] Could not mount static files: {e}")

    # ── Backward-compatible properties ───────────────────────

    @property
    def ai_router(self):
        return self._state.ai_router if self._state else None

    @ai_router.setter
    def ai_router(self, value):
        if self._state:
            self._state.ai_router = value

    @property
    def chat_manager(self):
        return self._state.chat_manager if self._state else None

    @chat_manager.setter
    def chat_manager(self, value):
        if self._state:
            self._state.chat_manager = value

    @property
    def voice_processor(self):
        return self._state.voice_processor if self._state else None

    @voice_processor.setter
    def voice_processor(self, value):
        if self._state:
            self._state.voice_processor = value

    @property
    def jarvis(self):
        return self._state.jarvis if self._state else None

    @jarvis.setter
    def jarvis(self, value):
        if self._state:
            self._state.jarvis = value

    @property
    def agents(self):
        return self._state.agents if self._state else {}

    @property
    def start_time(self):
        return self._state.start_time if self._state else None

    def _load_components(self):
        """Backward-compat: delegate to ServerState."""
        if self._state:
            self._state.load_components()

    # ── Server lifecycle ─────────────────────────────────────

    def run(self):
        """Run the API server."""
        if not FASTAPI_OK:
            print("FastAPI not installed. Run: pip install fastapi uvicorn")
            return
        print(f"LADA API Server starting on http://{self.host}:{self.port}")
        print(f"API docs available at http://{self.host}:{self.port}/docs")
        uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")

    async def run_async(self):
        """Run the API server asynchronously."""
        if not FASTAPI_OK:
            return
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


# ============================================================
# STANDALONE FUNCTIONS
# ============================================================

def create_app() -> 'FastAPI':
    """Create and return the FastAPI app for external ASGI servers."""
    server = LADAAPIServer()
    return server.app


def run_server(host: str = "0.0.0.0", port: int = 5000):
    """Run the API server."""
    server = LADAAPIServer(host=host, port=port)
    server.run()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse

    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    os.chdir(parent_dir)
    sys.path.insert(0, parent_dir)

    parser = argparse.ArgumentParser(description="LADA API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    args = parser.parse_args()

    print("=" * 50)
    print("   LADA v8.0 API Server")
    print("=" * 50)

    if not FASTAPI_OK:
        print("\nFastAPI not installed!")
        print("   Run: pip install fastapi uvicorn")
        sys.exit(1)

    run_server(host=args.host, port=args.port)
