"""
LADA API — WebSocket gateway (/ws)

Security features:
- Message size limits (default 64KB)
- Connection rate limiting
- Max concurrent connections per IP
- Idle timeout
"""

import json
import time
import uuid
import asyncio
import logging
import os
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from modules.api.deps import normalize_request_id
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)

# WebSocket security configuration
WS_MAX_MESSAGE_SIZE = int(os.getenv("LADA_WS_MAX_MESSAGE_SIZE", "65536"))  # 64KB default
WS_MAX_CONNECTIONS_PER_IP = int(os.getenv("LADA_WS_MAX_CONN_PER_IP", "5"))
WS_IDLE_TIMEOUT = int(os.getenv("LADA_WS_IDLE_TIMEOUT", "300"))  # 5 minutes
WS_MESSAGE_RATE_LIMIT = int(os.getenv("LADA_WS_MSG_RATE_LIMIT", "30"))  # messages per minute

# Track connections per IP
_connections_per_ip: dict = defaultdict(int)


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
            
            token = websocket.query_params.get("token", "")
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
        }
        logger.info(f"[WS] Client connected: {session_id} from {client_ip} ({connect_request_id})")

        try:
            await websocket.send_json({
                "type": "system.connected",
                "data": {"session_id": session_id, "version": "8.0.0",
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
            state.ws_connections.pop(session_id, None)
            state.ws_sessions.pop(session_id, None)
            if hasattr(state, 'ws_orchestrator_subscribers'):
                state.ws_orchestrator_subscribers.discard(session_id)
                if hasattr(state, 'ws_orchestrator_subscription_filters'):
                    state.ws_orchestrator_subscription_filters.pop(session_id, None)
                _maybe_cleanup_orchestrator_event_bridge(state)

    return r


async def _handle_chat(state, ws, session_id, msg_id, data, request_id: str = ""):
    """Handle chat messages over WebSocket."""
    state.load_components()
    message = data.get("message", "")
    stream = data.get("stream", True)
    model = data.get("model")
    use_web_search = data.get("use_web_search", False)
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
                        full_response += chunk_data['chunk']
                        await ws.send_json(
                            {
                                "type": "chat.chunk",
                                "id": msg_id,
                                "data": {"chunk": chunk_data['chunk'], "request_id": request_id},
                            }
                        )
                    if chunk_data.get('done'):
                        break

            if not error_sent:
                await ws.send_json({
                    "type": "chat.done", "id": msg_id,
                    "data": {
                        "content": full_response,
                        "model": getattr(state.ai_router, 'current_backend_name', 'unknown'),
                        "sources": sources,
                        "request_id": request_id,
                    },
                })
        else:
            def _query_sync():
                return state.ai_router.query(message, model=effective_model, use_web_search=use_web_search)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _query_sync)
            await ws.send_json({
                "type": "chat.response", "id": msg_id,
                "data": {"content": response,
                         "model": getattr(state.ai_router, 'current_backend_name', 'unknown'),
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


async def _handle_workflow(state, ws, msg_id, data, request_id: str = ""):
    state.load_components()
    action = data.get("action", "")
    wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
    if not wf:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": "Workflow engine not available", "request_id": request_id}})
        return
    if action == "list":
        workflows = wf.list_workflows()
        await _send_ws_response(
            ws,
            "workflow.list",
            msg_id,
            {"workflows": workflows},
            request_id=request_id,
        )
    elif action == "create":
        success = wf.register_workflow(data.get("name", ""), data.get("steps", []))
        await _send_ws_response(
            ws,
            "workflow.created",
            msg_id,
            {"success": success, "name": data.get("name", "")},
            request_id=request_id,
        )
    elif action == "execute":
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
    tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
    if not tc:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": "Task automation not available", "request_id": request_id}})
        return
    if action == "list":
        await _send_ws_response(ws, "task.list", msg_id, tc.get_active_tasks(), request_id=request_id)
    elif action == "create":
        task_def = tc.parse_complex_command(data.get("command", ""))
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tc.execute_task(task_def))
        await _send_ws_response(ws, "task.created", msg_id, result, request_id=request_id)
    elif action == "status":
        await _send_ws_response(
            ws,
            "task.status",
            msg_id,
            tc.get_task_status(data.get("execution_id", "")),
            request_id=request_id,
        )
    elif action == "pause":
        await _send_ws_response(
            ws,
            "task.paused",
            msg_id,
            tc.pause_task(data.get("execution_id", "")),
            request_id=request_id,
        )
    elif action == "resume":
        await _send_ws_response(
            ws,
            "task.resumed",
            msg_id,
            tc.resume_task(data.get("execution_id", "")),
            request_id=request_id,
        )
    elif action == "cancel":
        await _send_ws_response(
            ws,
            "task.cancelled",
            msg_id,
            tc.cancel_task(data.get("execution_id", "")),
            request_id=request_id,
        )
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown task action: {action}", "request_id": request_id}})
