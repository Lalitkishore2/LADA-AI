"""
LADA API — WebSocket gateway (/ws)

Security features:
- Message size limits (default 64KB)
- Connection rate limiting
- Max concurrent connections per IP
- Idle timeout
- Protocol v1.0 handshake with role/scope negotiation
- Idempotency enforcement for side-effect operations
"""

import json
import time
import uuid
import asyncio
import logging
import os
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from urllib.parse import urlparse

from modules.api.deps import normalize_request_id
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)

# WebSocket security configuration
WS_MAX_MESSAGE_SIZE = int(os.getenv("LADA_WS_MAX_MESSAGE_SIZE", "65536"))  # 64KB default
WS_MAX_CONNECTIONS_PER_IP = int(os.getenv("LADA_WS_MAX_CONN_PER_IP", "5"))
WS_IDLE_TIMEOUT = int(os.getenv("LADA_WS_IDLE_TIMEOUT", "300"))  # 5 minutes
WS_MESSAGE_RATE_LIMIT = int(os.getenv("LADA_WS_MSG_RATE_LIMIT", "30"))  # messages per minute

# Protocol v1.0 feature flags
WS_PROTOCOL_ENABLED = os.getenv("LADA_WS_PROTOCOL_ENABLED", "1").lower() in ("1", "true", "yes")
WS_PROTOCOL_HANDSHAKE_TIMEOUT = int(os.getenv("LADA_WS_HANDSHAKE_TIMEOUT", "10"))  # seconds
WS_REQUIRE_IDEMPOTENCY = os.getenv("LADA_WS_REQUIRE_IDEMPOTENCY", "0").lower() in ("1", "true", "yes")

# Track connections per IP
_connections_per_ip: dict = defaultdict(int)

# Protocol validator singleton (lazy loaded)
_protocol_validator: Optional[Any] = None


def _extract_ws_auth_token(websocket: WebSocket) -> str:
    """Extract session token from Authorization header or query string."""
    auth_header = (websocket.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()
        if bearer_token:
            return bearer_token
    return (websocket.query_params.get("token", "") or "").strip()


def _get_protocol_validator():
    """Lazy-load protocol validator to avoid circular imports."""
    global _protocol_validator
    if _protocol_validator is None and WS_PROTOCOL_ENABLED:
        try:
            from modules.gateway_protocol.validator import ProtocolValidator
            _protocol_validator = ProtocolValidator(
                require_idempotency=WS_REQUIRE_IDEMPOTENCY,
                max_frame_size=WS_MAX_MESSAGE_SIZE,
            )
            logger.info("[WS] Protocol v1.0 validator initialized")
        except ImportError as e:
            logger.warning(f"[WS] Protocol validator not available: {e}")
    return _protocol_validator


def _sanitize_ws_error_message(exception: Exception, operation: str) -> str:
    """Return a client-safe WebSocket error message."""
    error_info = safe_error_response(exception, operation=operation)
    return error_info.get("error") or "An internal error occurred. Please try again later."


async def _send_ws_response(ws, msg_type: str, msg_id: str, data: Any, request_id: str = ""):
    """Send a websocket response while ensuring request_id is present."""
    resolved_request_id = normalize_request_id(request_id, prefix="ws")
    payload = {"type": msg_type, "id": msg_id, "data": data}
    if isinstance(data, dict):
        data.setdefault("request_id", resolved_request_id)
    else:
        payload["request_id"] = resolved_request_id
    await ws.send_json(payload)


def _safe_agent_url(url: str) -> str:
    candidate = str(url or "").strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        return ""
    lowered = candidate.lower()
    blocked_prefixes = ("chrome://", "devtools://", "about:", "file://", "javascript:", "data:")
    if lowered.startswith(blocked_prefixes):
        return ""
    return candidate


async def _handle_agent_rpc(state, ws, msg_id: str, data: Dict[str, Any], request_id: str = ""):
    """Handle high-frequency browser automation RPC over /agent WebSocket."""
    action = str(data.get("action", "")).strip().lower()
    if not action:
        await _send_ws_response(
            ws, "agent.rpc.error", msg_id,
            {"message": "action is required"},
            request_id=request_id,
        )
        return

    adapter = None
    try:
        state.load_components()
        adapter = getattr(state, "lada_browser_adapter", None)
        if adapter is None:
            try:
                from integrations.lada_browser_adapter import get_lada_browser_adapter
                adapter = get_lada_browser_adapter()
                state.lada_browser_adapter = adapter
            except Exception:
                adapter = None
    except Exception:
        adapter = None

    try:
        from modules.stealth_browser import get_stealth_browser
        browser = get_stealth_browser()
    except Exception as e:
        await _send_ws_response(
            ws, "agent.rpc.error", msg_id,
            {"message": f"Browser automation unavailable: {e}"},
            request_id=request_id,
        )
        return

    if action == "navigate":
        url = _safe_agent_url(data.get("url", ""))
        if not url:
            await _send_ws_response(
                ws, "agent.rpc.error", msg_id,
                {"message": "Blocked or invalid URL"},
                request_id=request_id,
            )
            return

        if adapter and getattr(adapter, "navigate", None):
            ok = bool(adapter.navigate(url))
            if ok:
                await _send_ws_response(
                    ws, "agent.rpc.done", msg_id,
                    {"success": True, "action": action, "mode": "lada_browser_adapter", "url": url},
                    request_id=request_id,
                )
                return

        result = browser.navigate(url)
        await _send_ws_response(
            ws, "agent.rpc.done", msg_id,
            {"success": bool(result.get("success")), "action": action, "mode": "stealth_browser", "result": result},
            request_id=request_id,
        )
        return

    if action == "click":
        selector = str(data.get("selector", "")).strip()
        by = str(data.get("by", "css") or "css").strip()
        if not selector:
            await _send_ws_response(ws, "agent.rpc.error", msg_id, {"message": "selector is required"}, request_id=request_id)
            return

        if adapter and getattr(adapter, "click", None):
            ok = bool(adapter.click(selector))
            if ok:
                await _send_ws_response(
                    ws, "agent.rpc.done", msg_id,
                    {"success": True, "action": action, "mode": "lada_browser_adapter", "selector": selector},
                    request_id=request_id,
                )
                return

        result = browser.click(selector=selector, by=by)
        await _send_ws_response(
            ws, "agent.rpc.done", msg_id,
            {"success": bool(result.get("success")), "action": action, "mode": "stealth_browser", "result": result},
            request_id=request_id,
        )
        return

    if action == "type":
        selector = str(data.get("selector", "")).strip()
        text = str(data.get("text", ""))
        by = str(data.get("by", "css") or "css").strip()
        if not selector:
            await _send_ws_response(ws, "agent.rpc.error", msg_id, {"message": "selector is required"}, request_id=request_id)
            return

        if adapter and getattr(adapter, "type_text", None):
            ok = bool(adapter.type_text(selector, text))
            if ok:
                await _send_ws_response(
                    ws, "agent.rpc.done", msg_id,
                    {"success": True, "action": action, "mode": "lada_browser_adapter", "selector": selector},
                    request_id=request_id,
                )
                return

        result = browser.type_text(selector=selector, text=text, by=by)
        await _send_ws_response(
            ws, "agent.rpc.done", msg_id,
            {"success": bool(result.get("success")), "action": action, "mode": "stealth_browser", "result": result},
            request_id=request_id,
        )
        return

    if action == "scroll":
        direction = str(data.get("direction", "down")).strip().lower() or "down"
        amount = int(data.get("amount", 500))
        if adapter and getattr(adapter, "scroll", None):
            ok = bool(adapter.scroll(direction=direction, amount=amount))
            if ok:
                await _send_ws_response(
                    ws, "agent.rpc.done", msg_id,
                    {"success": True, "action": action, "mode": "lada_browser_adapter", "direction": direction, "amount": amount},
                    request_id=request_id,
                )
                return

        result = browser.scroll(direction=direction, amount=amount)
        await _send_ws_response(
            ws, "agent.rpc.done", msg_id,
            {"success": bool(result.get("success")), "action": action, "mode": "stealth_browser", "result": result},
            request_id=request_id,
        )
        return

    await _send_ws_response(
        ws, "agent.rpc.error", msg_id,
        {"message": f"Unsupported action: {action}"},
        request_id=request_id,
    )


def _event_to_dict(event) -> dict:
    """Convert event payload to a serializable dictionary."""
    if hasattr(event, "to_dict"):
        try:
            return event.to_dict()
        except Exception:
            pass
    if isinstance(event, dict):
        return event
    return {"raw": str(event)}


def _normalize_filter_values(raw_value: Any) -> Set[str]:
    """Normalize scalar/list filter values into a case-insensitive set."""
    if raw_value is None:
        return set()

    if isinstance(raw_value, (list, tuple, set)):
        items = raw_value
    else:
        items = [raw_value]

    normalized: Set[str] = set()
    for item in items:
        text = str(item).strip().lower()
        if text:
            normalized.add(text)

    return normalized


def _normalize_orchestrator_filters(raw_filters: Any) -> Dict[str, Set[str]]:
    """Normalize client filter payload for orchestrator event subscriptions."""
    normalized: Dict[str, Set[str]] = {
        "event_types": set(),
        "targets": set(),
        "correlation_ids": set(),
        "command_ids": set(),
        "statuses": set(),
    }

    if not isinstance(raw_filters, dict):
        return normalized

    normalized["event_types"] = _normalize_filter_values(
        raw_filters.get("event_types", raw_filters.get("event_type"))
    )
    normalized["targets"] = _normalize_filter_values(
        raw_filters.get("targets", raw_filters.get("target"))
    )
    normalized["correlation_ids"] = _normalize_filter_values(
        raw_filters.get("correlation_ids", raw_filters.get("correlation_id"))
    )
    normalized["command_ids"] = _normalize_filter_values(
        raw_filters.get("command_ids", raw_filters.get("command_id"))
    )
    normalized["statuses"] = _normalize_filter_values(
        raw_filters.get("statuses", raw_filters.get("status"))
    )

    return normalized


def _serialize_orchestrator_filters(filters: Dict[str, Set[str]]) -> Dict[str, list]:
    """Serialize normalized filter sets into JSON-friendly lists."""
    if not filters:
        return {}

    result: Dict[str, list] = {}
    for key, values in filters.items():
        if values:
            result[key] = sorted(values)
    return result


def _extract_event_target(event_payload: dict) -> str:
    """Extract target from the best available field in an orchestrator event."""
    payload = event_payload.get("payload") if isinstance(event_payload, dict) else {}
    payload = payload if isinstance(payload, dict) else {}

    metadata = event_payload.get("metadata") if isinstance(event_payload, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}

    output = payload.get("output") if isinstance(payload, dict) else {}
    output = output if isinstance(output, dict) else {}

    candidates = [
        event_payload.get("target"),
        payload.get("target"),
        metadata.get("target"),
        output.get("target"),
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip().lower()
        if text:
            return text

    return ""


def _event_matches_orchestrator_filters(event_payload: dict, filters: Dict[str, Set[str]]) -> bool:
    """Return True if event payload matches subscription filter criteria."""
    if not filters:
        return True

    event_type = str(event_payload.get("event_type", "")).strip().lower()
    status = str(event_payload.get("status", "")).strip().lower()
    correlation_id = str(event_payload.get("correlation_id", "")).strip().lower()
    command_id = str(event_payload.get("command_id", "")).strip().lower()
    target = _extract_event_target(event_payload)

    if filters.get("event_types") and event_type not in filters["event_types"]:
        return False
    if filters.get("targets") and target not in filters["targets"]:
        return False
    if filters.get("correlation_ids") and correlation_id not in filters["correlation_ids"]:
        return False
    if filters.get("command_ids") and command_id not in filters["command_ids"]:
        return False
    if filters.get("statuses") and status not in filters["statuses"]:
        return False

    return True


async def _broadcast_orchestrator_event(state, event_payload: dict):
    """Broadcast standalone orchestrator lifecycle events to subscribed sessions."""
    subscribers = list(getattr(state, "ws_orchestrator_subscribers", set()))
    if not subscribers:
        return

    filter_map = getattr(state, "ws_orchestrator_subscription_filters", {})

    stale_sessions = []
    event_request_id = normalize_request_id(
        event_payload.get("request_id") or event_payload.get("correlation_id"),
        prefix="ws-event",
    )
    message = {
        "type": "orchestrator.event",
        "data": {"event": event_payload, "request_id": event_request_id},
    }

    for session_id in subscribers:
        ws = state.ws_connections.get(session_id)
        if ws is None:
            stale_sessions.append(session_id)
            continue

        session_filters = filter_map.get(session_id, {})
        if not _event_matches_orchestrator_filters(event_payload, session_filters):
            continue

        try:
            await ws.send_json(message)
            if session_id in state.ws_sessions:
                state.ws_sessions[session_id]['messages_sent'] += 1
        except Exception:
            stale_sessions.append(session_id)

    for session_id in stale_sessions:
        state.ws_orchestrator_subscribers.discard(session_id)
        if hasattr(state, 'ws_orchestrator_subscription_filters'):
            state.ws_orchestrator_subscription_filters.pop(session_id, None)

    _maybe_cleanup_orchestrator_event_bridge(state)


def _ensure_orchestrator_event_bridge(state, loop) -> tuple:
    """Ensure one bus subscription exists that fans events out to WS subscribers."""
    bus = getattr(state, "command_bus", None)
    if bus is None:
        return False, "Standalone command bus is unavailable"

    existing_token = getattr(state, "ws_orchestrator_bus_subscription_token", None)
    if existing_token:
        state.ws_orchestrator_event_loop = loop
        return True, ""

    if getattr(state, "ws_orchestrator_event_callback", None) is None:
        def _on_event(event):
            ws_loop = getattr(state, "ws_orchestrator_event_loop", None)
            if ws_loop is None or ws_loop.is_closed():
                return

            payload = _event_to_dict(event)
            try:
                asyncio.run_coroutine_threadsafe(
                    _broadcast_orchestrator_event(state, payload),
                    ws_loop,
                )
            except Exception as exc:
                logger.warning(f"[WS] Failed to schedule orchestrator event broadcast: {exc}")

        state.ws_orchestrator_event_callback = _on_event

    try:
        token = bus.subscribe_events(state.ws_orchestrator_event_callback)
        state.ws_orchestrator_bus_subscription_token = token
        state.ws_orchestrator_event_loop = loop
        logger.info("[WS] Standalone orchestrator event bridge subscribed")
        return True, ""
    except Exception as exc:
        logger.error(f"[WS] Failed to subscribe orchestrator event bridge: {exc}")
        return False, str(exc)


def _maybe_cleanup_orchestrator_event_bridge(state):
    """Tear down bus subscription when there are no WS event subscribers."""
    subscribers = getattr(state, "ws_orchestrator_subscribers", set())
    token = getattr(state, "ws_orchestrator_bus_subscription_token", None)

    if subscribers or not token:
        return

    bus = getattr(state, "command_bus", None)
    if bus is not None:
        try:
            bus.unsubscribe_events(token)
            logger.info("[WS] Standalone orchestrator event bridge unsubscribed")
        except Exception as exc:
            logger.warning(f"[WS] Failed to unsubscribe orchestrator event bridge: {exc}")

    state.ws_orchestrator_bus_subscription_token = None
    if hasattr(state, "ws_orchestrator_subscription_filters"):
        state.ws_orchestrator_subscription_filters.clear()


# ============================================================================
# Approval Event Broadcasting
# ============================================================================

async def _broadcast_approval_event(state, event_type: str, event_payload: dict):
    """
    Broadcast approval events to subscribed WebSocket sessions.
    
    Event types:
    - approval.requested: New approval request created
    - approval.approved: Request was approved
    - approval.denied: Request was denied
    - approval.cancelled: Request was cancelled
    - approval.expired: Request expired
    """
    subscribers = list(getattr(state, "ws_approval_subscribers", set()))
    if not subscribers:
        return
    
    stale_sessions = []
    event_request_id = normalize_request_id(
        event_payload.get("request_id") or event_payload.get("id"),
        prefix="ws-approval",
    )
    message = {
        "type": event_type,
        "data": {
            "event": event_payload,
            "request_id": event_request_id,
            "timestamp": datetime.now().isoformat(),
        },
    }
    
    for session_id in subscribers:
        ws = state.ws_connections.get(session_id)
        if ws is None:
            stale_sessions.append(session_id)
            continue
        
        # Check agent_id filter if set
        session_filter = getattr(state, "ws_approval_subscription_filters", {}).get(session_id, {})
        filter_agent_id = session_filter.get("agent_id")
        event_agent_id = event_payload.get("agent_id")
        
        if filter_agent_id and event_agent_id and filter_agent_id != event_agent_id:
            continue
        
        try:
            await ws.send_json(message)
            if session_id in state.ws_sessions:
                state.ws_sessions[session_id]['messages_sent'] += 1
        except Exception:
            stale_sessions.append(session_id)
    
    for session_id in stale_sessions:
        state.ws_approval_subscribers.discard(session_id)
        if hasattr(state, "ws_approval_subscription_filters"):
            state.ws_approval_subscription_filters.pop(session_id, None)


def broadcast_approval_event_sync(state, event_type: str, event_payload: dict):
    """
    Synchronous wrapper to broadcast approval events from non-async context.
    
    Call this from approval queue callbacks.
    """
    loop = getattr(state, "ws_approval_event_loop", None)
    if loop is None or loop.is_closed():
        return
    
    try:
        asyncio.run_coroutine_threadsafe(
            _broadcast_approval_event(state, event_type, event_payload),
            loop,
        )
    except Exception as exc:
        logger.warning(f"[WS] Failed to schedule approval event broadcast: {exc}")


async def _process_legacy_message(state, websocket, session_id: str, raw: str, request_id: str):
    """
    Process a message received during handshake that wasn't a protocol connect.
    Used for backward compatibility with legacy clients.
    """
    session = state.ws_sessions.get(session_id)
    if not session:
        return
    
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "Invalid JSON", "request_id": request_id},
        })
        return
    
    msg_type = msg.get("type", "")
    msg_id = msg.get("id", "")
    msg_data = msg.get("data", {})
    if not isinstance(msg_data, dict):
        msg_data = {}
    msg_request_id = normalize_request_id(
        msg.get("request_id") or msg.get("correlation_id") or request_id,
        prefix="ws",
    )
    session['messages_received'] = session.get('messages_received', 0) + 1
    
    # Delegate to appropriate handler (simplified for common cases)
    if msg_type == "ping":
        await websocket.send_json({"type": "pong", "data": {"request_id": msg_request_id}})
    elif msg_type == "chat":
        # Will be handled in main loop
        pass
    # Other types will be processed in main message loop


def create_ws_router(state):
    """Create WebSocket gateway router."""
    r = APIRouter(tags=["websocket"])

    @r.websocket("/ws")
    async def websocket_gateway(websocket: WebSocket):
        """WebSocket gateway — real-time messaging with LADA."""
        # Get client IP (check X-Forwarded-For for proxied connections)
        client_ip = "unknown"
        connect_request_id = normalize_request_id(websocket.headers.get("x-request-id"), prefix="ws")
        forwarded_for = websocket.headers.get("x-forwarded-for", "")
        real_ip = websocket.headers.get("x-real-ip", "")
        
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs; first is the client
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip.strip()
        elif websocket.client:
            client_ip = websocket.client.host
        
        # Atomic connection reservation (prevent TOCTOU race condition)
        reserved = False
        try:
            if _connections_per_ip[client_ip] >= WS_MAX_CONNECTIONS_PER_IP:
                await websocket.close(code=4029, reason="Too many connections from this IP")
                logger.warning(f"[WS] Rejected connection from {client_ip}: too many connections")
                return
            
            # Reserve connection slot before authentication
            _connections_per_ip[client_ip] += 1
            reserved = True
            
            token = _extract_ws_auth_token(websocket)
            if not state.validate_session_token(token):
                await websocket.close(code=4001, reason="Authentication required")
                return

            await websocket.accept()
        except Exception:
            # Release reservation if connection setup fails
            if reserved:
                _connections_per_ip[client_ip] = max(0, _connections_per_ip[client_ip] - 1)
            raise
        
        session_id = str(uuid.uuid4())[:8]
        state.ws_connections[session_id] = websocket
        state.ws_sessions[session_id] = {
            'connected_at': time.time(), 
            'messages_sent': 0, 
            'messages_received': 0,
            'last_activity': time.time(),
            'client_ip': client_ip,
            'request_id': connect_request_id,
            'rate_limit_counter': 0,
            'rate_limit_window_start': time.time(),
            'orchestrator_events': False,
            'orchestrator_event_filters': {},
            'protocol_session': None,  # Protocol v1.0 session state
            'granted_scopes': [],  # Protocol v1.0 scopes
        }
        logger.info(f"[WS] Client connected: {session_id} from {client_ip} ({connect_request_id})")

        # Protocol v1.0 handshake (optional, backward compatible)
        protocol_session = None
        validator = _get_protocol_validator()
        
        if validator and WS_PROTOCOL_ENABLED:
            try:
                # Wait for connect message with timeout
                raw_handshake = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_PROTOCOL_HANDSHAKE_TIMEOUT
                )
                
                handshake_data = json.loads(raw_handshake)
                msg_type = handshake_data.get("type", "")
                
                # Check if client is using protocol v1.0
                if msg_type == "connect" or "protocol_version" in handshake_data:
                    response, protocol_session = validator.validate_connect(handshake_data)
                    
                    if not response.success:
                        await websocket.send_json(response.to_dict())
                        await websocket.close(code=4003, reason=response.error.message if response.error else "Handshake failed")
                        logger.warning(f"[WS] Protocol handshake failed for {session_id}: {response.error}")
                        return
                    
                    # Store protocol session state
                    state.ws_sessions[session_id]['protocol_session'] = protocol_session
                    state.ws_sessions[session_id]['granted_scopes'] = [s.value for s in response.granted_scopes]
                    
                    # Send protocol connected response
                    await websocket.send_json(response.to_dict())
                    logger.info(f"[WS] Protocol v1.0 handshake complete for {session_id}")
                else:
                    # Legacy client - process message after sending legacy connected
                    await websocket.send_json({
                        "type": "system.connected",
                        "data": {"session_id": session_id, "version": "9.0.0",
                                 "request_id": connect_request_id,
                                 "protocol_version": "1.0",
                                 "capabilities": [
                                     "chat",
                                     "stream",
                                     "agent",
                                     "system",
                                     "orchestrator.dispatch",
                                     "orchestrator.events",
                                 ],
                                 "limits": {
                                     "max_message_size": WS_MAX_MESSAGE_SIZE,
                                     "rate_limit": WS_MESSAGE_RATE_LIMIT,
                                     "idle_timeout": WS_IDLE_TIMEOUT,
                                 }},
                    })
                    # Process the first message that wasn't a handshake
                    await _process_legacy_message(state, websocket, session_id, raw_handshake, connect_request_id)
                    
            except asyncio.TimeoutError:
                # No handshake message received - legacy client, send connected
                await websocket.send_json({
                    "type": "system.connected",
                    "data": {"session_id": session_id, "version": "9.0.0",
                             "request_id": connect_request_id,
                             "protocol_version": "1.0",
                             "capabilities": [
                                 "chat",
                                 "stream",
                                 "agent",
                                 "system",
                                 "orchestrator.dispatch",
                                 "orchestrator.events",
                             ],
                             "limits": {
                                 "max_message_size": WS_MAX_MESSAGE_SIZE,
                                 "rate_limit": WS_MESSAGE_RATE_LIMIT,
                                 "idle_timeout": WS_IDLE_TIMEOUT,
                             }},
                })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Invalid JSON in handshake", "request_id": connect_request_id},
                })
                await websocket.close(code=4003, reason="Invalid handshake")
                return
        else:
            # Protocol disabled - send legacy connected message immediately
            await websocket.send_json({
                "type": "system.connected",
                "data": {"session_id": session_id, "version": "9.0.0",
                         "request_id": connect_request_id,
                         "capabilities": [
                             "chat",
                             "stream",
                             "agent",
                             "system",
                             "orchestrator.dispatch",
                             "orchestrator.events",
                         ],
                         "limits": {
                             "max_message_size": WS_MAX_MESSAGE_SIZE,
                             "rate_limit": WS_MESSAGE_RATE_LIMIT,
                             "idle_timeout": WS_IDLE_TIMEOUT,
                         }},
            })

        try:

            while True:
                # Get live session object (not stale copy)
                session = state.ws_sessions.get(session_id)
                if not session:
                    # Session was removed externally
                    await websocket.close(code=4000, reason="Session expired")
                    break
                
                # Check idle timeout
                if time.time() - session.get('last_activity', 0) > WS_IDLE_TIMEOUT:
                    await websocket.close(code=4000, reason="Idle timeout")
                    logger.info(f"[WS] Session {session_id} closed due to idle timeout")
                    break
                
                # Receive with timeout for idle check
                try:
                    raw = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=60  # Check idle every minute
                    )
                except asyncio.TimeoutError:
                    continue  # Loop back to check idle timeout
                
                # Check message size
                if len(raw) > WS_MAX_MESSAGE_SIZE:
                    await websocket.send_json({
                        "type": "error", 
                        "data": {
                            "message": f"Message too large. Max size: {WS_MAX_MESSAGE_SIZE} bytes",
                            "request_id": session.get("request_id", ""),
                        },
                    })
                    logger.warning(f"[WS] Message from {session_id} rejected: too large ({len(raw)} bytes)")
                    continue
                
                # Check rate limit (read from live session)
                now = time.time()
                if now - session.get('rate_limit_window_start', 0) >= 60:
                    # Reset rate limit window
                    session['rate_limit_counter'] = 0
                    session['rate_limit_window_start'] = now
                
                session['rate_limit_counter'] = session.get('rate_limit_counter', 0) + 1
                if session['rate_limit_counter'] > WS_MESSAGE_RATE_LIMIT:
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": "Rate limit exceeded. Slow down.",
                            "request_id": session.get("request_id", ""),
                        },
                    })
                    logger.warning(f"[WS] Rate limit exceeded for {session_id}")
                    continue
                
                # Update last activity
                session['last_activity'] = now
                
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "message": "Invalid JSON",
                                "request_id": session.get("request_id", ""),
                            },
                        }
                    )
                    continue

                msg_type = msg.get("type", "")
                msg_id = msg.get("id", "")
                msg_data = msg.get("data", {})
                if not isinstance(msg_data, dict):
                    msg_data = {}
                msg_request_id = normalize_request_id(
                    msg.get("request_id") or msg.get("correlation_id") or session.get("request_id"),
                    prefix="ws",
                )
                state.ws_sessions[session_id]['messages_received'] += 1
                
                # Protocol v1.0 validation (if enabled and session has protocol state)
                protocol_session = session.get('protocol_session')
                idempotency_key = msg.get("idempotency_key")
                
                if protocol_session and validator:
                    from modules.gateway_protocol.schema import MessageType
                    from modules.gateway_protocol.validator import ValidationResult
                    
                    # Map legacy message types to protocol operations
                    operation = f"{msg_type}.send" if msg_type in ("chat", "agent") else msg_type
                    
                    # Build protocol message for validation
                    protocol_msg = {
                        "message_id": msg_id or None,
                        "type": "request",
                        "operation": operation,
                        "payload": msg_data,
                        "idempotency_key": idempotency_key,
                    }
                    
                    result = validator.validate_frame(protocol_msg, protocol_session)
                    
                    if not result.valid:
                        await websocket.send_json({
                            "type": "error",
                            "id": msg_id,
                            "data": {
                                "message": result.error.message if result.error else "Validation failed",
                                "code": result.error.code if result.error else "VALIDATION_ERROR",
                                "request_id": msg_request_id,
                            },
                        })
                        logger.warning(f"[WS] Protocol validation failed for {session_id}: {result.error}")
                        continue
                    
                    if result.is_duplicate:
                        # Return cached response for duplicate idempotency key
                        if result.cached_response:
                            await websocket.send_json(result.cached_response)
                        else:
                            await websocket.send_json({
                                "type": "response",
                                "id": msg_id,
                                "data": {
                                    "message": "Duplicate request",
                                    "idempotency_key": idempotency_key,
                                    "request_id": msg_request_id,
                                },
                            })
                        continue

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "data": {"request_id": msg_request_id}})
                elif msg_type == "chat":
                    asyncio.create_task(
                        _handle_chat(
                            state,
                            websocket,
                            session_id,
                            msg_id,
                            msg_data,
                            request_id=msg_request_id,
                        )
                    )
                elif msg_type == "agent":
                    await _handle_agent(
                        state,
                        websocket,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                elif msg_type == "system":
                    await _handle_system(
                        state,
                        websocket,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                elif msg_type == "orchestrator":
                    await _handle_orchestrator(
                        state,
                        websocket,
                        session_id,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                elif msg_type == "plan":
                    await _handle_plan(
                        state,
                        websocket,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                elif msg_type == "workflow":
                    await _handle_workflow(
                        state,
                        websocket,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                elif msg_type == "task":
                    await _handle_task(
                        state,
                        websocket,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                elif msg_type == "approval":
                    await _handle_approval(
                        state,
                        websocket,
                        session_id,
                        msg_id,
                        msg_data,
                        request_id=msg_request_id,
                    )
                else:
                    await websocket.send_json({
                        "type": "error", "id": msg_id,
                        "data": {
                            "message": f"Unknown message type: {msg_type}",
                            "request_id": msg_request_id,
                        },
                    })

        except WebSocketDisconnect:
            logger.info(f"[WS] Client disconnected: {session_id}")
        except Exception as e:
            logger.error(f"[WS] Error for {session_id}: {e}")
        finally:
            # Cleanup connection tracking
            _connections_per_ip[client_ip] = max(0, _connections_per_ip[client_ip] - 1)
            
            # Cleanup protocol session if present
            session_data = state.ws_sessions.get(session_id, {})
            protocol_session = session_data.get('protocol_session')
            if protocol_session and validator:
                validator.remove_session(protocol_session.session_id)
            
            state.ws_connections.pop(session_id, None)
            state.ws_sessions.pop(session_id, None)
            if hasattr(state, 'ws_orchestrator_subscribers'):
                state.ws_orchestrator_subscribers.discard(session_id)
                if hasattr(state, 'ws_orchestrator_subscription_filters'):
                    state.ws_orchestrator_subscription_filters.pop(session_id, None)
                _maybe_cleanup_orchestrator_event_bridge(state)
            if hasattr(state, 'ws_approval_subscribers'):
                state.ws_approval_subscribers.discard(session_id)
                if hasattr(state, 'ws_approval_subscription_filters'):
                    state.ws_approval_subscription_filters.pop(session_id, None)

    @r.websocket("/agent")
    async def websocket_agent_rpc(websocket: WebSocket):
        """Dedicated WS channel for high-frequency browser automation RPC."""
        client_ip = websocket.client.host if websocket.client else "unknown"

        if _connections_per_ip[client_ip] >= WS_MAX_CONNECTIONS_PER_IP:
            await websocket.close(code=4029, reason="Too many connections from this IP")
            return

        _connections_per_ip[client_ip] += 1
        token = _extract_ws_auth_token(websocket)
        if not state.validate_session_token(token):
            _connections_per_ip[client_ip] = max(0, _connections_per_ip[client_ip] - 1)
            await websocket.close(code=4001, reason="Authentication required")
            return

        await websocket.accept()
        session_id = f"agent_{uuid.uuid4().hex[:8]}"
        connect_request_id = normalize_request_id(websocket.headers.get("x-request-id"), prefix="ws-agent")
        try:
            await websocket.send_json(
                {
                    "type": "agent.connected",
                    "data": {
                        "session_id": session_id,
                        "request_id": connect_request_id,
                        "capabilities": ["navigate", "click", "type", "scroll"],
                    },
                }
            )

            while True:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=WS_IDLE_TIMEOUT)
                if len(raw) > WS_MAX_MESSAGE_SIZE:
                    await websocket.send_json(
                        {
                            "type": "agent.rpc.error",
                            "data": {"message": f"Message too large. Max size: {WS_MAX_MESSAGE_SIZE} bytes"},
                        }
                    )
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "agent.rpc.error", "data": {"message": "Invalid JSON"}})
                    continue

                msg_id = str(msg.get("id", "")).strip()
                msg_data = msg.get("data", {}) if isinstance(msg.get("data"), dict) else {}
                msg_request_id = normalize_request_id(
                    msg.get("request_id") or connect_request_id,
                    prefix="ws-agent",
                )
                await _handle_agent_rpc(state, websocket, msg_id, msg_data, request_id=msg_request_id)

        except WebSocketDisconnect:
            logger.info(f"[WS-agent] Client disconnected: {session_id}")
        except asyncio.TimeoutError:
            await websocket.close(code=4000, reason="Idle timeout")
        except Exception as e:
            logger.error(f"[WS-agent] Error for {session_id}: {e}")
        finally:
            _connections_per_ip[client_ip] = max(0, _connections_per_ip[client_ip] - 1)

    # =========================================================================
    # ACP WebSocket Endpoint (IDE Integration)
    # =========================================================================
    
    @r.websocket("/acp")
    async def acp_websocket_endpoint(websocket: WebSocket):
        """
        ACP (Agent Communication Protocol) WebSocket endpoint.
        
        Used for IDE integration (VS Code, JetBrains, etc.).
        Supports JSON-RPC 2.0 style communication.
        """
        client_ip = websocket.client.host if websocket.client else "unknown"
        
        # Check connection limit
        if _connections_per_ip[client_ip] >= WS_MAX_CONNECTIONS_PER_IP:
            await websocket.close(code=1013, reason="Too many connections")
            return
        
        await websocket.accept()
        _connections_per_ip[client_ip] += 1
        
        acp_session_id = f"acp_{uuid.uuid4().hex[:8]}"
        logger.info(f"[ACP] Client connected: {acp_session_id} from {client_ip}")
        
        # Lazy import ACP bridge
        try:
            from modules.acp_bridge import get_acp_server
            acp_server = get_acp_server()
        except ImportError as e:
            logger.error(f"[ACP] Bridge not available: {e}")
            await websocket.send_json({
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": "ACP bridge not available"},
                "id": None,
            })
            await websocket.close(code=1011)
            _connections_per_ip[client_ip] = max(0, _connections_per_ip[client_ip] - 1)
            return
        
        # Create ACP session
        acp_session = acp_server.create_session(
            session_id=acp_session_id,
            metadata={"ip": client_ip, "transport": "websocket"},
        )
        
        try:
            while True:
                # Receive message
                try:
                    raw_message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=WS_IDLE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.info(f"[ACP] Session {acp_session_id} timed out")
                    break
                
                # Size check
                if len(raw_message) > WS_MAX_MESSAGE_SIZE:
                    await websocket.send_json({
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Message too large"},
                        "id": None,
                    })
                    continue
                
                # Parse JSON-RPC request
                try:
                    request = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None,
                    })
                    continue
                
                # Handle request through ACP server
                response = await acp_server.handle_request(
                    session_id=acp_session_id,
                    request=request,
                )
                
                # Convert ACPResponse to dict for JSON serialization
                if hasattr(response, 'to_dict'):
                    response = response.to_dict()
                
                await websocket.send_json(response)
        
        except WebSocketDisconnect:
            logger.info(f"[ACP] Client disconnected: {acp_session_id}")
        except Exception as e:
            logger.error(f"[ACP] Error for {acp_session_id}: {e}")
        finally:
            _connections_per_ip[client_ip] = max(0, _connections_per_ip[client_ip] - 1)
            acp_server.close_session(acp_session_id)

    return r


def _next_ws_conversation_id() -> str:
    """Generate a conversation id when persistence is unavailable."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _persist_ws_chat_turn(
    state,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    *,
    model_used: Optional[str] = None,
    sources: Optional[list] = None,
) -> str:
    """Persist a chat turn and return the resolved conversation id."""
    resolved_id = str(conversation_id or "").strip()
    chat_manager = getattr(state, "chat_manager", None)
    if chat_manager is None:
        return resolved_id or _next_ws_conversation_id()

    user_conv = chat_manager.add_message(resolved_id, "user", user_message)
    resolved_id = str(getattr(user_conv, "id", "") or resolved_id).strip()
    if not resolved_id:
        resolved_id = _next_ws_conversation_id()

    chat_manager.add_message(
        resolved_id,
        "assistant",
        assistant_message,
        model_used=model_used,
        sources=sources or [],
    )
    return resolved_id


async def _handle_chat(state, ws, session_id, msg_id, data, request_id: str = ""):
    """Handle chat messages over WebSocket.
    
    Flow:
    1. Check for system commands first (jarvis.process)
    2. If not a system command, route to AI for response
    """
    state.load_components()
    message = data.get("message", "")
    stream = data.get("stream", True)
    model = data.get("model")
    use_web_search = data.get("use_web_search", False)
    conversation_id = str(data.get("conversation_id") or "").strip()
    effective_model = model if model and model != 'auto' else None

    if not message:
        await ws.send_json(
            {
                "type": "error",
                "id": msg_id,
                "data": {"message": "Empty message", "request_id": request_id},
            }
        )
        return
    
    # ── Check for system commands first ──────────────────────────────────
    if state.jarvis:
        try:
            loop = asyncio.get_event_loop()
            handled, response = await loop.run_in_executor(
                None, state.jarvis.process, message
            )
            if handled:
                assistant_text = response or "Command executed."
                conversation_id = _persist_ws_chat_turn(
                    state,
                    conversation_id,
                    message,
                    assistant_text,
                    model_used="system-command",
                )
                # System command was handled - send response and done
                await ws.send_json({
                    "type": "chat.response",
                    "id": msg_id,
                    "data": {
                        "response": assistant_text,
                        "content": assistant_text,
                        "sources": [],
                        "model": "system-command",
                        "is_system_command": True,
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                    },
                })
                return
        except Exception as e:
            logger.warning(f"[WS] Jarvis command check failed: {e}")
            # Fall through to AI query on error
    
    # ── Not a system command - route to AI ───────────────────────────────
    if not state.ai_router:
        await ws.send_json(
            {
                "type": "error",
                "id": msg_id,
                "data": {"message": "AI router not available", "request_id": request_id},
            }
        )
        return

    try:
        if stream and hasattr(state.ai_router, 'stream_query'):
            await ws.send_json(
                {
                    "type": "chat.start",
                    "id": msg_id,
                    "data": {"status": "streaming", "request_id": request_id},
                }
            )
            full_response = ""
            sources = []
            last_stream_metadata = {}
            q = asyncio.Queue()
            error_sent = False
            loop = asyncio.get_event_loop()

            def _stream_worker():
                try:
                    for chunk_data in state.ai_router.stream_query(
                            message, model=effective_model, use_web_search=use_web_search):
                        asyncio.run_coroutine_threadsafe(q.put(chunk_data), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(q.put(e), loop)
                finally:
                    asyncio.run_coroutine_threadsafe(q.put(None), loop)

            loop.run_in_executor(None, _stream_worker)

            while True:
                try:
                    chunk_data = await asyncio.wait_for(q.get(), timeout=120)
                except asyncio.TimeoutError:
                    await ws.send_json(
                        {
                            "type": "chat.error",
                            "id": msg_id,
                            "data": {"message": "Response timed out", "request_id": request_id},
                        }
                    )
                    error_sent = True
                    break

                if chunk_data is None:
                    break
                if isinstance(chunk_data, Exception):
                    safe_message = _sanitize_ws_error_message(chunk_data, "ws_chat_stream")
                    await ws.send_json(
                        {
                            "type": "chat.error",
                            "id": msg_id,
                            "data": {"message": safe_message, "request_id": request_id},
                        }
                    )
                    error_sent = True
                    break

                if isinstance(chunk_data, dict):
                    if 'sources' in chunk_data:
                        sources = chunk_data['sources']
                        await ws.send_json(
                            {
                                "type": "chat.sources",
                                "id": msg_id,
                                "data": {"sources": sources, "request_id": request_id},
                            }
                        )
                    elif chunk_data.get('chunk'):
                        chunk_metadata = chunk_data.get('metadata', {})
                        chunk_metadata = chunk_metadata if isinstance(chunk_metadata, dict) else {}
                        if chunk_metadata:
                            last_stream_metadata = chunk_metadata

                        full_response += chunk_data['chunk']
                        payload = {"chunk": chunk_data['chunk'], "request_id": request_id}
                        if chunk_metadata:
                            payload["metadata"] = chunk_metadata

                        await ws.send_json(
                            {
                                "type": "chat.chunk",
                                "id": msg_id,
                                "data": payload,
                            }
                        )

                    if chunk_data.get('done'):
                        done_metadata = chunk_data.get('metadata', {})
                        done_metadata = done_metadata if isinstance(done_metadata, dict) else {}
                        if done_metadata:
                            last_stream_metadata = done_metadata
                        break
                else:
                    text_chunk = str(chunk_data)
                    if text_chunk:
                        full_response += text_chunk
                        await ws.send_json(
                            {
                                "type": "chat.chunk",
                                "id": msg_id,
                                "data": {"chunk": text_chunk, "request_id": request_id},
                            }
                        )

            if not error_sent:
                final_content = full_response
                if (not final_content or not str(final_content).strip()) and last_stream_metadata:
                    metadata_error = str(last_stream_metadata.get("error", "")).strip()
                    if metadata_error:
                        final_content = metadata_error
                if not final_content or not str(final_content).strip():
                    final_content = "No response generated."

                backend_name = getattr(state.ai_router, 'current_backend_name', 'unknown')
                conversation_id = _persist_ws_chat_turn(
                    state,
                    conversation_id,
                    message,
                    final_content,
                    model_used=backend_name,
                    sources=sources,
                )
                done_payload = {
                    "content": final_content,
                    "model": backend_name,
                    "sources": sources,
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                }
                if last_stream_metadata:
                    done_payload["metadata"] = last_stream_metadata

                await ws.send_json({
                    "type": "chat.done", "id": msg_id,
                    "data": done_payload,
                })
        else:
            def _query_sync():
                return state.ai_router.query(message, model=effective_model, use_web_search=use_web_search)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _query_sync)
            backend_name = getattr(state.ai_router, 'current_backend_name', 'unknown')
            conversation_id = _persist_ws_chat_turn(
                state,
                conversation_id,
                message,
                response,
                model_used=backend_name,
            )
            await ws.send_json({
                "type": "chat.response", "id": msg_id,
                "data": {"content": response,
                         "model": backend_name,
                         "conversation_id": conversation_id,
                         "request_id": request_id},
            })

        state.ws_sessions[session_id]['messages_sent'] += 1
    except Exception as e:
        logger.error(f"[WS] Chat handler error for {session_id}: {type(e).__name__}")
        try:
            safe_message = _sanitize_ws_error_message(e, "ws_chat_handler")
            await ws.send_json(
                {
                    "type": "chat.error",
                    "id": msg_id,
                    "data": {"message": safe_message, "request_id": request_id},
                }
            )
        except Exception:
            pass


async def _handle_agent(state, ws, msg_id, data, request_id: str = ""):
    state.load_components()
    agent_name = data.get("agent", "").lower()
    action = data.get("action", "").lower()
    params = data.get("params", {})
    if agent_name not in state.agents:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Agent '{agent_name}' not found", "request_id": request_id}})
        return
    agent = state.agents[agent_name]
    try:
        if hasattr(agent, action):
            result = getattr(agent, action)(**params)
        elif hasattr(agent, 'process'):
            result = agent.process(params.get('query', action))
        else:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": f"Action '{action}' not supported", "request_id": request_id}})
            return
        await ws.send_json({"type": "agent.response", "id": msg_id,
                            "data": {"agent": agent_name, "action": action, "result": result, "request_id": request_id}})
    except Exception as e:
        safe_message = _sanitize_ws_error_message(e, "ws_agent")
        await ws.send_json({
            "type": "error",
            "id": msg_id,
            "data": {"message": safe_message, "request_id": request_id},
        })


async def _handle_system(state, ws, msg_id, data, request_id: str = ""):
    action = data.get("action", "")
    if action == "status":
        state.load_components()
        status = {}
        if state.ai_router:
            status['backends'] = state.ai_router.get_status()
            if hasattr(state.ai_router, 'get_provider_status'):
                status['providers'] = state.ai_router.get_provider_status()
            if hasattr(state.ai_router, 'get_cost_summary'):
                status['cost'] = state.ai_router.get_cost_summary()
        status['uptime'] = (datetime.now() - state.start_time).total_seconds()
        status['ws_connections'] = len(state.ws_connections)
        await _send_ws_response(ws, "system.status", msg_id, status, request_id=request_id)
    elif action == "models":
        state.load_components()
        models = []
        if state.ai_router and hasattr(state.ai_router, 'get_all_available_models'):
            try:
                models = state.ai_router.get_all_available_models() or []
            except Exception:
                pass
        if (not models) and state.ai_router and hasattr(state.ai_router, 'get_provider_dropdown_items'):
            try:
                models = state.ai_router.get_provider_dropdown_items() or []
            except Exception:
                pass
        await _send_ws_response(
            ws,
            "system.models",
            msg_id,
            {"models": models},
            request_id=request_id,
        )
    elif action == "clear_history":
        if state.ai_router:
            state.ai_router.clear_history()
        await _send_ws_response(
            ws,
            "system.ack",
            msg_id,
            {"action": "clear_history", "success": True},
            request_id=request_id,
        )
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown system action: {action}", "request_id": request_id}})


async def _handle_orchestrator(state, ws, session_id, msg_id, data, request_id: str = ""):
    """Handle standalone orchestrator dispatch and event subscription over WebSocket."""
    state.load_components()

    orchestrator = getattr(state, 'orchestrator', None)
    if not orchestrator:
        await ws.send_json({
            "type": "error",
            "id": msg_id,
            "data": {
                "message": (
                    "Standalone orchestrator is not enabled. "
                    "Set LADA_STANDALONE_ORCHESTRATOR=true to enable it."
                ),
                "request_id": request_id,
            },
        })
        return

    control_action = str(data.get("orchestrator_action", "")).strip().lower()
    if not control_action:
        candidate = str(data.get("action", "")).strip().lower()
        if candidate in {"subscribe", "unsubscribe", "status"} and not data.get("envelope"):
            control_action = candidate

    if not hasattr(state, "ws_orchestrator_subscription_filters"):
        state.ws_orchestrator_subscription_filters = {}

    if control_action == "subscribe":
        ok, err = _ensure_orchestrator_event_bridge(state, asyncio.get_running_loop())
        if not ok:
            safe_message = _sanitize_ws_error_message(RuntimeError(err), "ws_orchestrator_subscribe")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
            return

        requested_filters = _normalize_orchestrator_filters(
            data.get("filters", data.get("filter", {}))
        )

        state.ws_orchestrator_subscribers.add(session_id)
        state.ws_orchestrator_subscription_filters[session_id] = requested_filters
        if session_id in state.ws_sessions:
            state.ws_sessions[session_id]['orchestrator_events'] = True
            state.ws_sessions[session_id]['orchestrator_event_filters'] = _serialize_orchestrator_filters(
                requested_filters
            )

        await ws.send_json({
            "type": "orchestrator.subscribed",
            "id": msg_id,
            "data": {
                "subscribed": True,
                "subscriber_count": len(state.ws_orchestrator_subscribers),
                "filters": _serialize_orchestrator_filters(requested_filters),
                "request_id": request_id,
            },
        })
        return

    if control_action == "unsubscribe":
        state.ws_orchestrator_subscribers.discard(session_id)
        state.ws_orchestrator_subscription_filters.pop(session_id, None)
        if session_id in state.ws_sessions:
            state.ws_sessions[session_id]['orchestrator_events'] = False
            state.ws_sessions[session_id]['orchestrator_event_filters'] = {}
        _maybe_cleanup_orchestrator_event_bridge(state)

        await ws.send_json({
            "type": "orchestrator.unsubscribed",
            "id": msg_id,
            "data": {
                "subscribed": False,
                "subscriber_count": len(state.ws_orchestrator_subscribers),
                "filters": {},
                "request_id": request_id,
            },
        })
        return

    if control_action == "status":
        subscribed = session_id in state.ws_orchestrator_subscribers
        filters = state.ws_orchestrator_subscription_filters.get(session_id, {})
        await ws.send_json({
            "type": "orchestrator.status",
            "id": msg_id,
            "data": {
                "subscribed": subscribed,
                "subscriber_count": len(state.ws_orchestrator_subscribers),
                "stream_active": bool(getattr(state, 'ws_orchestrator_bus_subscription_token', None)),
                "filters": _serialize_orchestrator_filters(filters),
                "request_id": request_id,
            },
        })
        return

    from modules.standalone.contracts import CommandEnvelope

    wait_for_result = bool(data.get("wait", True))
    timeout_ms = int(data.get("timeout_ms", 60000))

    envelope_data = data.get("envelope")
    if isinstance(envelope_data, dict):
        raw_envelope = dict(envelope_data)
    else:
        raw_envelope = {
            "source": data.get("source", "ws"),
            "target": data.get("target", "system"),
            "action": data.get("action", ""),
            "payload": data.get("payload", {}),
            "timeout_ms": timeout_ms,
            "metadata": data.get("metadata", {}),
            "idempotency_key": data.get("idempotency_key"),
        }

    if "source" not in raw_envelope:
        raw_envelope["source"] = "ws"
    if "timeout_ms" not in raw_envelope:
        raw_envelope["timeout_ms"] = timeout_ms

    try:
        envelope = CommandEnvelope.from_dict(raw_envelope)
    except Exception:
        await ws.send_json({
            "type": "error",
            "id": msg_id,
            "data": {"message": "Invalid command envelope", "request_id": request_id},
        })
        return

    try:
        event = orchestrator.submit(
            envelope,
            wait_for_result=wait_for_result,
            timeout_ms=timeout_ms,
        )
    except Exception as e:
        safe_message = _sanitize_ws_error_message(e, "ws_orchestrator_dispatch")
        await ws.send_json({
            "type": "error",
            "id": msg_id,
            "data": {"message": safe_message, "request_id": request_id},
        })
        return

    response = {
        "type": "orchestrator.response",
        "id": msg_id,
        "data": {
            "accepted": True,
            "status": "accepted",
            "command": envelope.to_dict(),
            "request_id": request_id,
        },
    }

    if event is not None:
        response["data"]["status"] = event.status
        response["data"]["event_type"] = event.event_type
        response["data"]["result_event"] = event.to_dict()

    await ws.send_json(response)


async def _handle_plan(state, ws, msg_id, data, request_id: str = ""):
    state.load_components()
    action = data.get("action", "")
    planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
    if not planner:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": "Planner not available", "request_id": request_id}})
        return
    if action == "create":
        try:
            loop = asyncio.get_event_loop()
            plan = await loop.run_in_executor(
                None, lambda: planner.create_plan(data.get("task", ""), data.get("context", "")))
            await _send_ws_response(ws, "plan.created", msg_id, plan.to_dict(), request_id=request_id)
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_plan_create")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
    elif action == "execute":
        plan = planner.get_plan(data.get("plan_id", ""))
        if not plan:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Plan not found", "request_id": request_id}})
            return
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: planner.execute_plan(plan))
        await _send_ws_response(ws, "plan.done", msg_id, result.to_dict(), request_id=request_id)
    elif action == "list":
        plans = planner.get_recent_plans(data.get("count", 10))
        await _send_ws_response(
            ws,
            "plan.list",
            msg_id,
            {"plans": [p.to_dict() for p in plans]},
            request_id=request_id,
        )
    elif action == "cancel":
        planner.cancel()
        await _send_ws_response(
            ws,
            "plan.cancelled",
            msg_id,
            {"success": True},
            request_id=request_id,
        )
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown plan action: {action}", "request_id": request_id}})


def _ws_task_progress_percent(value: Any) -> str:
    try:
        progress = float(value)
    except (TypeError, ValueError):
        progress = 0.0
    if progress <= 1.0:
        progress *= 100.0
    progress = max(0.0, min(progress, 100.0))
    return f"{int(progress)}%"


def _ws_task_payload_from_registry(task_data: Dict[str, Any]) -> Dict[str, Any]:
    steps = task_data.get("steps", [])
    total_steps = len(steps) if isinstance(steps, list) and steps else 1
    current_index = task_data.get("current_step_index", 0)
    try:
        current_step = int(current_index)
    except (TypeError, ValueError):
        current_step = 0
    current_step = max(0, min(current_step, total_steps))
    return {
        "execution_id": task_data.get("id", ""),
        "task_name": task_data.get("name", ""),
        "status": task_data.get("status", "pending"),
        "progress": _ws_task_progress_percent(task_data.get("progress", 0.0)),
        "current_step": f"{current_step}/{total_steps}",
        "started_at": task_data.get("started_at"),
        "completed_at": task_data.get("completed_at"),
        "error": task_data.get("error"),
        "result": task_data.get("result"),
    }


async def _handle_workflow(state, ws, msg_id, data, request_id: str = ""):
    state.load_components()
    action = data.get("action", "")

    if action == "list":
        try:
            from modules.tasks import get_flow_registry

            flow_registry = get_flow_registry()
            flows = flow_registry.list_flows()
            if flows:
                workflows = []
                for flow in flows:
                    flow_data = flow.to_dict()
                    flow_task = flow_registry.get_task(flow.id)
                    actions = []
                    if flow_task and getattr(flow_task, "steps", None):
                        actions = [str(step.action) for step in flow_task.steps if getattr(step, "action", None)]
                    workflows.append(
                        {
                            "name": flow_data.get("name") or flow_data.get("id", ""),
                            "steps": int(flow_data.get("total_steps", 0) or 0),
                            "actions": actions,
                            "status": flow_data.get("status", "pending"),
                            "flow_id": flow_data.get("id"),
                            "source": "registry",
                        }
                    )
                await _send_ws_response(
                    ws,
                    "workflow.list",
                    msg_id,
                    {"workflows": workflows},
                    request_id=request_id,
                )
                return
        except Exception as e:
            logger.warning(f"[WS] workflow list registry fallback: {type(e).__name__}")

        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Workflow engine not available", "request_id": request_id}})
            return

        workflows = wf.list_workflows()
        await _send_ws_response(
            ws,
            "workflow.list",
            msg_id,
            {"workflows": workflows},
            request_id=request_id,
        )
    elif action == "create":
        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Workflow engine not available", "request_id": request_id}})
            return
        success = wf.register_workflow(data.get("name", ""), data.get("steps", []))
        await _send_ws_response(
            ws,
            "workflow.created",
            msg_id,
            {"success": success, "name": data.get("name", "")},
            request_id=request_id,
        )
    elif action == "execute":
        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Workflow engine not available", "request_id": request_id}})
            return
        try:
            result = await wf.execute_workflow(data.get("name", ""), data.get("context", {}))
            await _send_ws_response(
                ws,
                "workflow.done",
                msg_id,
                {
                    "success": result.success,
                    "workflow_name": result.workflow_name,
                    "steps_completed": result.steps_completed,
                    "total_steps": result.total_steps,
                    "duration_seconds": result.duration_seconds,
                    "error": result.error,
                },
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_workflow_execute")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown workflow action: {action}", "request_id": request_id}})


async def _handle_task(state, ws, msg_id, data, request_id: str = ""):
    state.load_components()
    action = data.get("action", "")
    if action == "list":
        try:
            from modules.tasks import get_registry

            registry_tasks = get_registry().list_tasks(active_only=True)
            if registry_tasks:
                payload = {
                    "success": True,
                    "active_tasks": [_ws_task_payload_from_registry(task.to_dict()) for task in registry_tasks],
                }
                payload["count"] = len(payload["active_tasks"])
                await _send_ws_response(ws, "task.list", msg_id, payload, request_id=request_id)
                return
        except Exception as e:
            logger.warning(f"[WS] task list registry fallback: {type(e).__name__}")

        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Task automation not available", "request_id": request_id}})
            return
        await _send_ws_response(ws, "task.list", msg_id, tc.get_active_tasks(), request_id=request_id)
    elif action == "create":
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Task automation not available", "request_id": request_id}})
            return
        task_def = tc.parse_complex_command(data.get("command", ""))
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tc.execute_task(task_def))
        await _send_ws_response(ws, "task.created", msg_id, result, request_id=request_id)
    elif action == "status":
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            await _send_ws_response(
                ws,
                "task.status",
                msg_id,
                tc.get_task_status(data.get("execution_id", "")),
                request_id=request_id,
            )
            return
        try:
            from modules.tasks import get_registry

            execution_id = data.get("execution_id", "")
            task = get_registry().get(execution_id)
            if not task:
                await ws.send_json({"type": "error", "id": msg_id,
                                    "data": {"message": f"Task '{execution_id}' not found", "request_id": request_id}})
                return
            await _send_ws_response(
                ws,
                "task.status",
                msg_id,
                _ws_task_payload_from_registry(task.to_dict()),
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_task_status")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
    elif action == "pause":
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            await _send_ws_response(
                ws,
                "task.paused",
                msg_id,
                tc.pause_task(data.get("execution_id", "")),
                request_id=request_id,
            )
            return
        try:
            from modules.tasks import get_registry

            execution_id = data.get("execution_id", "")
            token = get_registry().pause(execution_id)
            if not token:
                await ws.send_json({"type": "error", "id": msg_id,
                                    "data": {"message": "Cannot pause task", "request_id": request_id}})
                return
            await _send_ws_response(
                ws,
                "task.paused",
                msg_id,
                {"success": True, "execution_id": execution_id, "status": "paused", "resume_token": token},
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_task_pause")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
    elif action == "resume":
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            await _send_ws_response(
                ws,
                "task.resumed",
                msg_id,
                tc.resume_task(data.get("execution_id", "")),
                request_id=request_id,
            )
            return
        try:
            from modules.tasks import get_registry

            execution_id = data.get("execution_id", "")
            registry = get_registry()
            resumed = registry.resume(execution_id)
            if not resumed:
                existing = registry.get(execution_id)
                if existing and existing.resume_token:
                    resumed = registry.resume(existing.resume_token)
            if not resumed:
                await ws.send_json({"type": "error", "id": msg_id,
                                    "data": {"message": "Task or resume token not found", "request_id": request_id}})
                return
            await _send_ws_response(
                ws,
                "task.resumed",
                msg_id,
                {"success": True, "execution_id": resumed.id, "status": resumed.status.value},
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_task_resume")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
    elif action == "cancel":
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            await _send_ws_response(
                ws,
                "task.cancelled",
                msg_id,
                tc.cancel_task(data.get("execution_id", "")),
                request_id=request_id,
            )
            return
        try:
            from modules.tasks import get_registry

            execution_id = data.get("execution_id", "")
            reason = data.get("reason")
            if not get_registry().cancel(execution_id, reason):
                await ws.send_json({"type": "error", "id": msg_id,
                                    "data": {"message": "Cannot cancel task", "request_id": request_id}})
                return
            await _send_ws_response(
                ws,
                "task.cancelled",
                msg_id,
                {"success": True, "execution_id": execution_id, "status": "cancelled"},
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_task_cancel")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown task action: {action}", "request_id": request_id}})


async def _handle_approval(state, ws, session_id, msg_id, data, request_id: str = ""):
    """
    Handle approval-related WebSocket messages.
    
    Actions:
    - subscribe: Subscribe to approval events
    - unsubscribe: Unsubscribe from approval events
    - list: List pending approval requests
    - approve: Approve a request by token
    - deny: Deny a request by token
    - cancel: Cancel a request by token
    - check: Check if action requires approval
    """
    action = data.get("action", "")
    
    # Initialize approval subscribers set if needed
    if not hasattr(state, 'ws_approval_subscribers'):
        state.ws_approval_subscribers = set()
    if not hasattr(state, 'ws_approval_subscription_filters'):
        state.ws_approval_subscription_filters = {}
    if not hasattr(state, 'ws_approval_event_loop'):
        state.ws_approval_event_loop = asyncio.get_event_loop()
    
    if action == "subscribe":
        # Subscribe to approval events
        state.ws_approval_subscribers.add(session_id)
        
        # Store filters if provided
        filters = data.get("filters", {})
        if filters:
            state.ws_approval_subscription_filters[session_id] = filters
        
        await _send_ws_response(
            ws,
            "approval.subscribed",
            msg_id,
            {
                "session_id": session_id,
                "filters": filters,
            },
            request_id=request_id,
        )
        return
    
    elif action == "unsubscribe":
        state.ws_approval_subscribers.discard(session_id)
        state.ws_approval_subscription_filters.pop(session_id, None)
        
        await _send_ws_response(
            ws,
            "approval.unsubscribed",
            msg_id,
            {"session_id": session_id},
            request_id=request_id,
        )
        return
    
    elif action == "list":
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            agent_id = data.get("agent_id")
            pending = queue.list_pending(agent_id=agent_id)
            
            await _send_ws_response(
                ws,
                "approval.list",
                msg_id,
                {
                    "pending": [r.to_dict() for r in pending],
                    "count": len(pending),
                },
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_approval_list")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
        return
    
    elif action == "approve":
        try:
            from modules.approval import get_approval_queue
            
            token = data.get("token", "")
            if not token:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": "token is required", "request_id": request_id},
                })
                return
            
            queue = get_approval_queue()
            result = queue.approve(
                request_id_or_token=token,
                approver_id=data.get("approver_id", "ws_user"),
                reason=data.get("reason", ""),
                pin=data.get("pin"),
            )
            
            if not result:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": f"Request not found: {token}", "request_id": request_id},
                })
                return
            
            await _send_ws_response(
                ws,
                "approval.approved",
                msg_id,
                {
                    "token": token,
                    "status": result.status.value,
                    "request": result.to_dict(),
                },
                request_id=request_id,
            )
            
            # Broadcast to subscribers
            await _broadcast_approval_event(
                state,
                "approval.approved",
                result.to_dict(),
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_approval_approve")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
        return
    
    elif action == "deny":
        try:
            from modules.approval import get_approval_queue
            
            token = data.get("token", "")
            if not token:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": "token is required", "request_id": request_id},
                })
                return
            
            queue = get_approval_queue()
            result = queue.deny(
                request_id_or_token=token,
                approver_id=data.get("approver_id", "ws_user"),
                reason=data.get("reason", ""),
            )
            
            if not result:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": f"Request not found: {token}", "request_id": request_id},
                })
                return
            
            await _send_ws_response(
                ws,
                "approval.denied",
                msg_id,
                {
                    "token": token,
                    "status": result.status.value,
                    "request": result.to_dict(),
                },
                request_id=request_id,
            )
            
            # Broadcast to subscribers
            await _broadcast_approval_event(
                state,
                "approval.denied",
                result.to_dict(),
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_approval_deny")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
        return
    
    elif action == "cancel":
        try:
            from modules.approval import get_approval_queue
            
            token = data.get("token", "")
            if not token:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": "token is required", "request_id": request_id},
                })
                return
            
            queue = get_approval_queue()
            result = queue.cancel(token, reason=data.get("reason", ""))
            
            if not result:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": f"Request not found: {token}", "request_id": request_id},
                })
                return
            
            await _send_ws_response(
                ws,
                "approval.cancelled",
                msg_id,
                {
                    "token": token,
                    "status": result.status.value,
                },
                request_id=request_id,
            )
            
            # Broadcast to subscribers
            await _broadcast_approval_event(
                state,
                "approval.cancelled",
                result.to_dict(),
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_approval_cancel")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
        return
    
    elif action == "check":
        try:
            from modules.approval import get_hook_registry
            
            check_action = data.get("check_action", "")
            if not check_action:
                await ws.send_json({
                    "type": "error",
                    "id": msg_id,
                    "data": {"message": "check_action is required", "request_id": request_id},
                })
                return
            
            registry = get_hook_registry()
            result = registry.check_approval_required(
                action=check_action,
                command=data.get("command", ""),
                params=data.get("params", {}),
                agent_id=data.get("agent_id"),
                channel_type=data.get("channel_type"),
            )
            
            await _send_ws_response(
                ws,
                "approval.check",
                msg_id,
                result,
                request_id=request_id,
            )
        except Exception as e:
            safe_message = _sanitize_ws_error_message(e, "ws_approval_check")
            await ws.send_json({
                "type": "error",
                "id": msg_id,
                "data": {"message": safe_message, "request_id": request_id},
            })
        return
    
    else:
        await ws.send_json({
            "type": "error",
            "id": msg_id,
            "data": {"message": f"Unknown approval action: {action}", "request_id": request_id},
        })
