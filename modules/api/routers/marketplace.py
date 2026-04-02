"""
LADA API — Marketplace routes (/marketplace/*, /plugins)
"""

import logging
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Query, Body, Request, Response, Depends
from fastapi.responses import JSONResponse
from modules.api.deps import set_request_id_header
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)


def create_marketplace_router(state):
    """Create marketplace/plugin router."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="marketplace")

    r = APIRouter(tags=["marketplace"], dependencies=[Depends(_trace_request)])

    def _raise_sanitized_error(exc: Exception, operation: str) -> None:
        error_info = safe_error_response(exc, operation=operation)
        logger.error(f"[APIServer] {operation} error: {type(exc).__name__}")
        raise HTTPException(status_code=error_info["status_code"], detail=error_info["error"])

    @r.get("/marketplace", response_class=JSONResponse)
    async def marketplace_list(
        category: Optional[str] = Query(None, description="Filter by category"),
        search: Optional[str] = Query(None, description="Search plugins"),
    ):
        try:
            from modules.plugin_marketplace import get_marketplace
            marketplace = get_marketplace()
            plugins = marketplace.list_available(category=category, search=search)
            return {"success": True, "plugins": plugins, "stats": marketplace.get_stats()}
        except Exception as e:
            _raise_sanitized_error(e, "marketplace_list")

    @r.post("/marketplace/install", response_class=JSONResponse)
    async def marketplace_install(body: Dict = Body(...)):
        name = body.get("name", "")
        if not name:
            raise HTTPException(status_code=400, detail="Plugin name required")
        try:
            from modules.plugin_marketplace import get_marketplace
            marketplace = get_marketplace()
            return marketplace.install(name)
        except Exception as e:
            _raise_sanitized_error(e, "marketplace_install")

    @r.delete("/marketplace/{name}", response_class=JSONResponse)
    async def marketplace_uninstall(name: str):
        try:
            from modules.plugin_marketplace import get_marketplace
            marketplace = get_marketplace()
            return marketplace.uninstall(name)
        except Exception as e:
            _raise_sanitized_error(e, "marketplace_uninstall")

    @r.get("/marketplace/categories", response_class=JSONResponse)
    async def marketplace_categories():
        try:
            from modules.plugin_marketplace import get_marketplace
            marketplace = get_marketplace()
            return {"categories": marketplace.get_categories()}
        except Exception as e:
            _raise_sanitized_error(e, "marketplace_categories")

    @r.get("/marketplace/updates", response_class=JSONResponse)
    async def marketplace_updates():
        try:
            from modules.plugin_marketplace import get_marketplace
            marketplace = get_marketplace()
            updates = marketplace.check_updates()
            return {"updates": updates, "count": len(updates)}
        except Exception as e:
            _raise_sanitized_error(e, "marketplace_updates")

    @r.get("/plugins", response_class=JSONResponse)
    async def list_plugins():
        try:
            from modules.plugin_system import get_plugin_registry
            registry = get_plugin_registry()
            return {"plugins": registry.get_plugin_list()}
        except Exception as e:
            _raise_sanitized_error(e, "list_plugins")

    return r
