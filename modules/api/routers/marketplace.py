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
        name = str(body.get("name", "")).strip()
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

    # ─── Plugin Trust Endpoints ───────────────────────────────────────
    
    @r.get("/plugins/trust", response_class=JSONResponse)
    async def get_trust_registry():
        """Get all plugin trust entries."""
        try:
            from modules.plugins.trust import get_trust_registry
            registry = get_trust_registry()
            return {
                "success": True,
                "trust_entries": [e.to_dict() for e in registry.list_all()]
            }
        except Exception as e:
            _raise_sanitized_error(e, "get_trust_registry")

    @r.get("/plugins/trust/{plugin_id}", response_class=JSONResponse)
    async def get_plugin_trust(plugin_id: str):
        """Get trust info for a specific plugin."""
        try:
            from modules.plugins.trust import get_trust_registry
            registry = get_trust_registry()
            entry = registry.get(plugin_id)
            if not entry:
                raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found in trust registry")
            return {"success": True, "trust": entry.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_plugin_trust")

    @r.post("/plugins/trust/{plugin_id}", response_class=JSONResponse)
    async def update_plugin_trust(plugin_id: str, body: Dict = Body(...)):
        """Update trust level for a plugin."""
        try:
            from modules.plugins.trust import get_trust_registry, TrustLevel
            registry = get_trust_registry()
            
            trust_level = body.get("trust_level")
            if not trust_level:
                raise HTTPException(status_code=400, detail="trust_level required")
            
            try:
                level = TrustLevel(trust_level)
            except ValueError:
                valid = [t.value for t in TrustLevel]
                raise HTTPException(status_code=400, detail=f"Invalid trust_level. Valid: {valid}")
            
            entry = registry.get(plugin_id)
            if not entry:
                raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
            
            registry.set_trust_level(plugin_id, level)
            updated = registry.get(plugin_id)
            return {"success": True, "trust": updated.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "update_plugin_trust")

    # ─── Plugin Security Scan Endpoints ───────────────────────────────

    @r.post("/plugins/scan/{plugin_id}", response_class=JSONResponse)
    async def scan_plugin(plugin_id: str):
        """Run security scan on a plugin."""
        try:
            from modules.plugins.scanner import get_plugin_scanner
            from modules.plugin_system import get_plugin_registry
            
            # Get plugin path
            plugin_registry = get_plugin_registry()
            plugins = plugin_registry.get_plugin_list()
            plugin = next((p for p in plugins if p.get("id") == plugin_id), None)
            
            if not plugin:
                raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
            
            plugin_path = plugin.get("path", "")
            if not plugin_path:
                raise HTTPException(status_code=400, detail="Plugin path not available")
            
            scanner = get_plugin_scanner()
            result = scanner.scan(plugin_path)
            
            return {
                "success": True,
                "plugin_id": plugin_id,
                "scan_result": result.to_dict()
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "scan_plugin")

    @r.get("/plugins/scan/findings", response_class=JSONResponse)
    async def get_scan_findings():
        """Get recent scan findings across all plugins."""
        try:
            from modules.plugins.scanner import get_plugin_scanner
            scanner = get_plugin_scanner()
            
            # Get recent scans from history
            history = scanner.get_scan_history(limit=50)
            
            return {
                "success": True,
                "findings": history
            }
        except Exception as e:
            _raise_sanitized_error(e, "get_scan_findings")

    # ─── Plugin Policy Endpoints ──────────────────────────────────────

    @r.get("/plugins/policy", response_class=JSONResponse)
    async def get_plugin_policy():
        """Get current plugin policy configuration."""
        try:
            from modules.plugins.policy import get_policy_engine
            engine = get_policy_engine()
            return {
                "success": True,
                "policy": engine.get_policy_summary()
            }
        except Exception as e:
            _raise_sanitized_error(e, "get_plugin_policy")

    @r.post("/plugins/policy/check", response_class=JSONResponse)
    async def check_plugin_policy(body: Dict = Body(...)):
        """Check if a plugin action is allowed by policy."""
        try:
            from modules.plugins.policy import get_policy_engine
            engine = get_policy_engine()
            
            plugin_id = body.get("plugin_id")
            action = body.get("action")
            
            if not plugin_id or not action:
                raise HTTPException(status_code=400, detail="plugin_id and action required")
            
            result = engine.check_permission(plugin_id, action)
            return {
                "success": True,
                "plugin_id": plugin_id,
                "action": action,
                "allowed": result.allowed,
                "reason": result.reason
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "check_plugin_policy")

    @r.post("/plugins/policy/allow", response_class=JSONResponse)
    async def add_policy_allow(body: Dict = Body(...)):
        """Add plugin to allowlist."""
        try:
            from modules.plugins.policy import get_policy_engine
            engine = get_policy_engine()
            
            plugin_id = body.get("plugin_id")
            if not plugin_id:
                raise HTTPException(status_code=400, detail="plugin_id required")
            
            engine.add_to_allowlist(plugin_id)
            return {"success": True, "message": f"Plugin '{plugin_id}' added to allowlist"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "add_policy_allow")

    @r.post("/plugins/policy/deny", response_class=JSONResponse)
    async def add_policy_deny(body: Dict = Body(...)):
        """Add plugin to denylist."""
        try:
            from modules.plugins.policy import get_policy_engine
            engine = get_policy_engine()
            
            plugin_id = body.get("plugin_id")
            if not plugin_id:
                raise HTTPException(status_code=400, detail="plugin_id required")
            
            engine.add_to_denylist(plugin_id)
            return {"success": True, "message": f"Plugin '{plugin_id}' added to denylist"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "add_policy_deny")

    @r.delete("/plugins/policy/allow/{plugin_id}", response_class=JSONResponse)
    async def remove_policy_allow(plugin_id: str):
        """Remove plugin from allowlist."""
        try:
            from modules.plugins.policy import get_policy_engine
            engine = get_policy_engine()
            engine.remove_from_allowlist(plugin_id)
            return {"success": True, "message": f"Plugin '{plugin_id}' removed from allowlist"}
        except Exception as e:
            _raise_sanitized_error(e, "remove_policy_allow")

    @r.delete("/plugins/policy/deny/{plugin_id}", response_class=JSONResponse)
    async def remove_policy_deny(plugin_id: str):
        """Remove plugin from denylist."""
        try:
            from modules.plugins.policy import get_policy_engine
            engine = get_policy_engine()
            engine.remove_from_denylist(plugin_id)
            return {"success": True, "message": f"Plugin '{plugin_id}' removed from denylist"}
        except Exception as e:
            _raise_sanitized_error(e, "remove_policy_deny")

    return r
