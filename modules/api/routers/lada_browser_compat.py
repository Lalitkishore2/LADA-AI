"""
LADA API - Browser compatibility routes (/lada/browser/*)

Provides a native compatibility surface for browser automation calls.
If adapter mode is disabled, endpoints fall back to stealth browser mode.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Body, Request, Response, Depends
from modules.api.deps import set_request_id_header

logger = logging.getLogger(__name__)


def create_lada_browser_compat_router(state):
    """Create LADA browser compatibility router."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="lada-browser")

    r = APIRouter(tags=["lada_browser_compat"], dependencies=[Depends(_trace_request)])

    def _get_adapter():
        state.load_components()
        adapter = getattr(state, "lada_browser_adapter", None)
        if adapter is not None:
            return adapter

        try:
            from integrations.lada_browser_adapter import get_lada_browser_adapter

            adapter = get_lada_browser_adapter()
            state.lada_browser_adapter = adapter
            return adapter
        except Exception as e:
            logger.warning(f"[LadaBrowserAPI] Adapter unavailable: {e}")
            return None

    def _get_stealth_browser():
        from modules.stealth_browser import get_stealth_browser

        return get_stealth_browser()

    def _normalize_url(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    @r.get("/lada/browser/status")
    async def browser_status():
        adapter = _get_adapter()
        adapter_status = adapter.status() if adapter else {
            "enabled": False,
            "state": "disabled",
            "connected": False,
            "last_error": "Adapter disabled or not initialized",
        }

        return {
            "success": True,
            "adapter": adapter_status,
            "fallback": "stealth_browser",
        }

    @r.post("/lada/browser/connect")
    async def browser_connect():
        adapter = _get_adapter()
        if not adapter:
            raise HTTPException(
                status_code=503,
                detail="Browser adapter is disabled. Set LADA_BROWSER_ADAPTER_ENABLED=true to enable it.",
            )

        ok = bool(adapter.connect())
        return {
            "success": ok,
            "message": "Connected" if ok else "Connection failed",
            "status": adapter.status(),
        }

    @r.post("/lada/browser/disconnect")
    async def browser_disconnect():
        adapter = _get_adapter()
        if not adapter:
            return {"success": True, "message": "Adapter not active"}

        adapter.disconnect()
        return {
            "success": True,
            "message": "Disconnected",
            "status": adapter.status(),
        }

    @r.post("/lada/browser/navigate")
    async def browser_navigate(body: dict = Body(default={})):
        url = _normalize_url(str(body.get("url", "")))
        if not url:
            raise HTTPException(status_code=400, detail="url is required")

        adapter = _get_adapter()
        if adapter:
            ok = bool(adapter.navigate(url))
            if ok:
                return {"success": True, "mode": "lada_browser_adapter", "url": url}

        try:
            browser = _get_stealth_browser()
            result = browser.navigate(url)
            if not result.get("success"):
                raise HTTPException(status_code=500, detail=result.get("error", "Navigation failed"))
            return {
                "success": True,
                "mode": "stealth_browser",
                "url": result.get("url", url),
                "title": result.get("title", ""),
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Navigation failed: {e}")

    @r.post("/lada/browser/action")
    async def browser_action(body: dict = Body(default={})):
        action = str(body.get("action", "")).strip().lower()
        selector = str(body.get("selector", "")).strip()
        text = str(body.get("text", ""))
        by = str(body.get("by", "css")).strip() or "css"
        direction = str(body.get("direction", "down")).strip().lower() or "down"
        amount = int(body.get("amount", 500))

        if not action:
            raise HTTPException(status_code=400, detail="action is required")

        adapter = _get_adapter()

        if action == "click":
            if not selector:
                raise HTTPException(status_code=400, detail="selector is required for click")

            if adapter:
                ok = bool(adapter.click(selector))
                if ok:
                    return {"success": True, "mode": "lada_browser_adapter", "action": action, "selector": selector}

            try:
                browser = _get_stealth_browser()
                result = browser.click(selector=selector, by=by)
                if not result.get("success"):
                    raise HTTPException(status_code=500, detail=result.get("error", "Click failed"))
                return {"success": True, "mode": "stealth_browser", "action": action, "selector": selector}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Click failed: {e}")

        if action == "type":
            if not selector:
                raise HTTPException(status_code=400, detail="selector is required for type")

            if adapter:
                ok = bool(adapter.type_text(selector, text))
                if ok:
                    return {"success": True, "mode": "lada_browser_adapter", "action": action, "selector": selector}

            try:
                browser = _get_stealth_browser()
                result = browser.type_text(selector=selector, text=text, by=by)
                if not result.get("success"):
                    raise HTTPException(status_code=500, detail=result.get("error", "Type failed"))
                return {"success": True, "mode": "stealth_browser", "action": action, "selector": selector}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Type failed: {e}")

        if action == "scroll":
            if direction not in {"up", "down"}:
                raise HTTPException(status_code=400, detail="direction must be 'up' or 'down'")

            if adapter:
                ok = bool(adapter.scroll(direction=direction, amount=amount))
                if ok:
                    return {"success": True, "mode": "lada_browser_adapter", "action": action, "direction": direction, "amount": amount}

            try:
                browser = _get_stealth_browser()
                result = browser.scroll(direction=direction, amount=amount)
                if not result.get("success"):
                    raise HTTPException(status_code=500, detail=result.get("error", "Scroll failed"))
                return {"success": True, "mode": "stealth_browser", "action": action, "direction": direction, "amount": amount}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Scroll failed: {e}")

        if action == "extract":
            content = ""
            mode = "lada_browser_adapter"
            if adapter:
                content = adapter.extract_text(selector=selector or None)

            if not content:
                mode = "stealth_browser"
                try:
                    browser = _get_stealth_browser()
                    if selector:
                        extracted = browser.execute_js(
                            "const el=document.querySelector(arguments[0]); return el ? el.innerText : '';",
                            selector,
                        )
                        content = str(extracted or "")
                    else:
                        result = browser.get_page_content()
                        content = str(result.get("text", "")) if result.get("success") else ""
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Extract failed: {e}")

            return {
                "success": bool(content),
                "mode": mode,
                "action": action,
                "selector": selector,
                "content": content,
            }

        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    @r.get("/lada/browser/snapshot")
    async def browser_snapshot(selector: Optional[str] = None):
        adapter = _get_adapter()
        if adapter:
            data = adapter.snapshot_summary()
            if data:
                return {"success": True, "mode": "lada_browser_adapter", "snapshot": data}

        try:
            browser = _get_stealth_browser()
            page = browser.get_page_content()
            shot = browser.screenshot()
            if not page.get("success"):
                raise HTTPException(status_code=500, detail=page.get("error", "Snapshot failed"))

            data = {
                "url": page.get("url", ""),
                "title": page.get("title", ""),
                "text_chars": len(str(page.get("text", ""))),
                "has_screenshot": bool(shot.get("success")),
                "screenshot_path": shot.get("path", ""),
                "selector": selector or "",
            }
            return {"success": True, "mode": "stealth_browser", "snapshot": data}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Snapshot failed: {e}")

    return r
