"""LADA API - OpenClaw compatibility routes.

Optional compatibility surface for OpenClaw-style clients.
Protected by feature flag, auth checks, and per-IP rate limiting.
"""

from __future__ import annotations

import os
import time
import logging
from collections import defaultdict, deque
from typing import Deque, Dict, Any

from fastapi import APIRouter, HTTPException, Body, Request, Response, Depends

from modules.api.deps import set_request_id_header, normalize_request_id

logger = logging.getLogger(__name__)


def _flag_enabled(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _parse_bearer_token(authorization: str) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        return ""

    parts = raw.split(None, 1)
    if len(parts) != 2:
        return ""

    scheme, token = parts
    if scheme.lower() != "bearer":
        return ""

    return token.strip()


def _to_openclaw_event(frame_type: str, payload: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Wrap internal response payload into an OpenClaw-compatible event envelope."""
    event_type = {
        "command.result": "openclaw.command.result",
        "browser.result": "openclaw.browser.result",
        "system.status": "openclaw.system.status",
    }.get(frame_type, "openclaw.event")

    return {
        "type": "openclaw.event",
        "event_type": event_type,
        "timestamp": time.time(),
        "request_id": request_id,
        "payload": payload,
    }


def create_openclaw_compat_router(state):
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="openclaw")

    r = APIRouter(tags=["openclaw_compat"], dependencies=[Depends(_trace_request)])

    # In-memory per-IP sliding-window limiter for compatibility endpoints.
    per_ip_windows: Dict[str, Deque[float]] = defaultdict(deque)
    max_per_minute = max(1, int(str(os.getenv("LADA_OPENCLAW_COMPAT_RPM", "30")).strip() or "30"))

    def _require_feature_enabled():
        if not _flag_enabled("LADA_OPENCLAW_MODE", "false"):
            raise HTTPException(status_code=404, detail="OpenClaw compatibility mode is disabled")

    def _require_auth(request: Request):
        auth_header = request.headers.get("authorization", "")
        token = _parse_bearer_token(auth_header)
        if not token:
            token = str(request.query_params.get("token", "") or "").strip()
        if not state.validate_session_token(token):
            raise HTTPException(status_code=401, detail="Authentication required")

    def _enforce_rate_limit(request: Request):
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            client_ip = forwarded.split(",", 1)[0].strip()
        else:
            client_ip = (request.client.host if request.client else "unknown")

        now = time.time()
        window = per_ip_windows[client_ip]
        while window and (now - window[0]) >= 60.0:
            window.popleft()

        if len(window) >= max_per_minute:
            raise HTTPException(status_code=429, detail="Rate limit exceeded for OpenClaw compatibility endpoints")

        window.append(now)

    def _guard(request: Request):
        _require_feature_enabled()
        _require_auth(request)
        _enforce_rate_limit(request)

    def _execute_command(command: str) -> Dict[str, Any]:
        state.load_components()
        jarvis = getattr(state, "jarvis", None)
        if jarvis and hasattr(jarvis, "process"):
            handled, response = jarvis.process(command)
            return {
                "success": True,
                "handled": bool(handled),
                "response": str(response or ""),
            }

        processor = getattr(state, "voice_processor", None)
        if processor and hasattr(processor, "process"):
            output = processor.process(command)
            return {
                "success": True,
                "handled": True,
                "response": str(output or ""),
            }

        return {
            "success": False,
            "handled": False,
            "response": "No command processor available",
        }

    @r.get("/openclaw/compat/status")
    async def openclaw_status(request: Request):
        _guard(request)
        request_id = normalize_request_id(request.headers.get("x-request-id"), prefix="openclaw")
        state.load_components()

        payload = {
            "enabled": True,
            "mode": "openclaw_compat",
            "request_id": request_id,
            "ws_compat_enabled": _flag_enabled("LADA_OPENCLAW_WS_COMPAT_ENABLED", "true"),
            "ws_event_mapping": {
                "openclaw.chat": "chat",
                "openclaw.agent": "agent",
                "openclaw.system": "system",
                "openclaw.orchestrator": "orchestrator",
                "openclaw.plan": "plan",
                "openclaw.workflow": "workflow",
                "openclaw.task": "task",
                "openclaw.approval": "approval",
                "openclaw.event(chat.message)": "chat",
                "openclaw.event(agent.rpc)": "agent",
                "openclaw.event(orchestrator.dispatch)": "orchestrator",
            },
        }
        return _to_openclaw_event("system.status", payload, request_id)

    @r.post("/openclaw/compat/command")
    async def openclaw_command(request: Request, body: dict = Body(default={})): 
        _guard(request)
        request_id = normalize_request_id(
            body.get("request_id") or request.headers.get("x-request-id"),
            prefix="openclaw",
        )
        command = str(body.get("command", "")).strip()
        if not command:
            raise HTTPException(status_code=400, detail="command is required")

        result = _execute_command(command)
        return _to_openclaw_event("command.result", {"command": command, **result}, request_id)

    @r.post("/openclaw/compat/browser-action")
    async def openclaw_browser_action(request: Request, body: dict = Body(default={})):
        _guard(request)
        request_id = normalize_request_id(
            body.get("request_id") or request.headers.get("x-request-id"),
            prefix="openclaw",
        )

        action = str(body.get("action", "")).strip().lower()
        if not action:
            raise HTTPException(status_code=400, detail="action is required")

        state.load_components()
        adapter = getattr(state, "lada_browser_adapter", None)
        if adapter is None:
            try:
                from integrations.lada_browser_adapter import get_lada_browser_adapter

                adapter = get_lada_browser_adapter()
                state.lada_browser_adapter = adapter
            except Exception:
                adapter = None

        from modules.stealth_browser import get_stealth_browser

        browser = get_stealth_browser()
        mode = "stealth_browser"
        success = False
        result_payload: Dict[str, Any] = {}

        if action == "navigate":
            url = str(body.get("url", "")).strip()
            if not url:
                raise HTTPException(status_code=400, detail="url is required")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            if adapter and getattr(adapter, "navigate", None):
                success = bool(adapter.navigate(url))
                if success:
                    mode = "lada_browser_adapter"
                    result_payload = {"url": url}
            if not success:
                result = browser.navigate(url)
                success = bool(result.get("success"))
                result_payload = result

        elif action == "click":
            selector = str(body.get("selector", "")).strip()
            if not selector:
                raise HTTPException(status_code=400, detail="selector is required")

            if adapter and getattr(adapter, "click", None):
                success = bool(adapter.click(selector))
                if success:
                    mode = "lada_browser_adapter"
                    result_payload = {"selector": selector}
            if not success:
                result = browser.click(selector=selector)
                success = bool(result.get("success"))
                result_payload = result

        elif action == "type":
            selector = str(body.get("selector", "")).strip()
            text = str(body.get("text", ""))
            if not selector:
                raise HTTPException(status_code=400, detail="selector is required")

            if adapter and getattr(adapter, "type_text", None):
                success = bool(adapter.type_text(selector, text))
                if success:
                    mode = "lada_browser_adapter"
                    result_payload = {"selector": selector}
            if not success:
                result = browser.type_text(selector=selector, text=text)
                success = bool(result.get("success"))
                result_payload = result

        elif action == "scroll":
            direction = str(body.get("direction", "down")).strip().lower() or "down"
            try:
                amount = int(body.get("amount", 500))
            except Exception:
                raise HTTPException(status_code=400, detail="amount must be an integer")

            if adapter and getattr(adapter, "scroll", None):
                success = bool(adapter.scroll(direction=direction, amount=amount))
                if success:
                    mode = "lada_browser_adapter"
                    result_payload = {"direction": direction, "amount": amount}
            if not success:
                result = browser.scroll(direction=direction, amount=amount)
                success = bool(result.get("success"))
                result_payload = result

        elif action == "extract":
            selector = str(body.get("selector", "")).strip()
            content = ""

            if adapter and getattr(adapter, "extract_text", None):
                content = str(adapter.extract_text(selector=selector or None) or "")
                if content:
                    success = True
                    mode = "lada_browser_adapter"
                    result_payload = {"content": content}

            if not success:
                if selector:
                    extracted = browser.execute_js(
                        "const el=document.querySelector(arguments[0]); return el ? el.innerText : '';",
                        selector,
                    )
                    content = str(extracted or "")
                else:
                    page = browser.get_page_content()
                    content = str(page.get("text", "")) if page.get("success") else ""
                success = bool(content)
                result_payload = {"content": content}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

        payload = {
            "success": bool(success),
            "action": action,
            "mode": mode,
            "result": result_payload,
        }
        return _to_openclaw_event("browser.result", payload, request_id)

    return r
