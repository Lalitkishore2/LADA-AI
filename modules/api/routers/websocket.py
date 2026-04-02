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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# WebSocket security configuration
WS_MAX_MESSAGE_SIZE = int(os.getenv("LADA_WS_MAX_MESSAGE_SIZE", "65536"))  # 64KB default
WS_MAX_CONNECTIONS_PER_IP = int(os.getenv("LADA_WS_MAX_CONN_PER_IP", "5"))
WS_IDLE_TIMEOUT = int(os.getenv("LADA_WS_IDLE_TIMEOUT", "300"))  # 5 minutes
WS_MESSAGE_RATE_LIMIT = int(os.getenv("LADA_WS_MSG_RATE_LIMIT", "30"))  # messages per minute

# Track connections per IP
_connections_per_ip: dict = defaultdict(int)


def create_ws_router(state):
    """Create WebSocket gateway router."""
    r = APIRouter(tags=["websocket"])

    @r.websocket("/ws")
    async def websocket_gateway(websocket: WebSocket):
        """WebSocket gateway — real-time messaging with LADA."""
        # Get client IP (check X-Forwarded-For for proxied connections)
        client_ip = "unknown"
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
            'rate_limit_counter': 0,
            'rate_limit_window_start': time.time(),
        }
        logger.info(f"[WS] Client connected: {session_id} from {client_ip}")

        try:
            await websocket.send_json({
                "type": "system.connected",
                "data": {"session_id": session_id, "version": "8.0.0",
                         "capabilities": ["chat", "stream", "agent", "system"],
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
                        "data": {"message": f"Message too large. Max size: {WS_MAX_MESSAGE_SIZE} bytes"}
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
                        "data": {"message": "Rate limit exceeded. Slow down."}
                    })
                    logger.warning(f"[WS] Rate limit exceeded for {session_id}")
                    continue
                
                # Update last activity
                session['last_activity'] = now
                
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid JSON"}})
                    continue

                msg_type = msg.get("type", "")
                msg_id = msg.get("id", "")
                msg_data = msg.get("data", {})
                state.ws_sessions[session_id]['messages_received'] += 1

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "chat":
                    asyncio.create_task(_handle_chat(state, websocket, session_id, msg_id, msg_data))
                elif msg_type == "agent":
                    await _handle_agent(state, websocket, msg_id, msg_data)
                elif msg_type == "system":
                    await _handle_system(state, websocket, msg_id, msg_data)
                elif msg_type == "plan":
                    await _handle_plan(state, websocket, msg_id, msg_data)
                elif msg_type == "workflow":
                    await _handle_workflow(state, websocket, msg_id, msg_data)
                elif msg_type == "task":
                    await _handle_task(state, websocket, msg_id, msg_data)
                else:
                    await websocket.send_json({
                        "type": "error", "id": msg_id,
                        "data": {"message": f"Unknown message type: {msg_type}"},
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

    return r


async def _handle_chat(state, ws, session_id, msg_id, data):
    """Handle chat messages over WebSocket."""
    state.load_components()
    message = data.get("message", "")
    stream = data.get("stream", True)
    model = data.get("model")
    use_web_search = data.get("use_web_search", False)
    effective_model = model if model and model != 'auto' else None

    if not message:
        await ws.send_json({"type": "error", "id": msg_id, "data": {"message": "Empty message"}})
        return
    if not state.ai_router:
        await ws.send_json({"type": "error", "id": msg_id, "data": {"message": "AI router not available"}})
        return

    try:
        if stream and hasattr(state.ai_router, 'stream_query'):
            await ws.send_json({"type": "chat.start", "id": msg_id, "data": {"status": "streaming"}})
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
                    await ws.send_json({"type": "chat.error", "id": msg_id,
                                        "data": {"message": "Response timed out"}})
                    error_sent = True
                    break

                if chunk_data is None:
                    break
                if isinstance(chunk_data, Exception):
                    await ws.send_json({"type": "chat.error", "id": msg_id,
                                        "data": {"message": str(chunk_data)}})
                    error_sent = True
                    break

                if isinstance(chunk_data, dict):
                    if 'sources' in chunk_data:
                        sources = chunk_data['sources']
                        await ws.send_json({"type": "chat.sources", "id": msg_id,
                                            "data": {"sources": sources}})
                    elif chunk_data.get('chunk'):
                        full_response += chunk_data['chunk']
                        await ws.send_json({"type": "chat.chunk", "id": msg_id,
                                            "data": {"chunk": chunk_data['chunk']}})
                    if chunk_data.get('done'):
                        break

            if not error_sent:
                await ws.send_json({
                    "type": "chat.done", "id": msg_id,
                    "data": {
                        "content": full_response,
                        "model": getattr(state.ai_router, 'current_backend_name', 'unknown'),
                        "sources": sources,
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
                         "model": getattr(state.ai_router, 'current_backend_name', 'unknown')},
            })

        state.ws_sessions[session_id]['messages_sent'] += 1
    except Exception as e:
        logger.error(f"[WS] Chat handler error for {session_id}: {e}")
        try:
            await ws.send_json({"type": "chat.error", "id": msg_id,
                                "data": {"message": f"Internal error: {str(e)}"}})
        except Exception:
            pass


async def _handle_agent(state, ws, msg_id, data):
    state.load_components()
    agent_name = data.get("agent", "").lower()
    action = data.get("action", "").lower()
    params = data.get("params", {})
    if agent_name not in state.agents:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Agent '{agent_name}' not found"}})
        return
    agent = state.agents[agent_name]
    try:
        if hasattr(agent, action):
            result = getattr(agent, action)(**params)
        elif hasattr(agent, 'process'):
            result = agent.process(params.get('query', action))
        else:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": f"Action '{action}' not supported"}})
            return
        await ws.send_json({"type": "agent.response", "id": msg_id,
                            "data": {"agent": agent_name, "action": action, "result": result}})
    except Exception as e:
        await ws.send_json({"type": "error", "id": msg_id, "data": {"message": str(e)}})


async def _handle_system(state, ws, msg_id, data):
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
        await ws.send_json({"type": "system.status", "id": msg_id, "data": status})
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
        await ws.send_json({"type": "system.models", "id": msg_id, "data": {"models": models}})
    elif action == "clear_history":
        if state.ai_router:
            state.ai_router.clear_history()
        await ws.send_json({"type": "system.ack", "id": msg_id,
                            "data": {"action": "clear_history", "success": True}})
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown system action: {action}"}})


async def _handle_plan(state, ws, msg_id, data):
    state.load_components()
    action = data.get("action", "")
    planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
    if not planner:
        await ws.send_json({"type": "error", "id": msg_id, "data": {"message": "Planner not available"}})
        return
    if action == "create":
        try:
            loop = asyncio.get_event_loop()
            plan = await loop.run_in_executor(
                None, lambda: planner.create_plan(data.get("task", ""), data.get("context", "")))
            await ws.send_json({"type": "plan.created", "id": msg_id, "data": plan.to_dict()})
        except Exception as e:
            await ws.send_json({"type": "error", "id": msg_id, "data": {"message": str(e)}})
    elif action == "execute":
        plan = planner.get_plan(data.get("plan_id", ""))
        if not plan:
            await ws.send_json({"type": "error", "id": msg_id, "data": {"message": "Plan not found"}})
            return
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: planner.execute_plan(plan))
        await ws.send_json({"type": "plan.done", "id": msg_id, "data": result.to_dict()})
    elif action == "list":
        plans = planner.get_recent_plans(data.get("count", 10))
        await ws.send_json({"type": "plan.list", "id": msg_id,
                            "data": {"plans": [p.to_dict() for p in plans]}})
    elif action == "cancel":
        planner.cancel()
        await ws.send_json({"type": "plan.cancelled", "id": msg_id, "data": {"success": True}})
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown plan action: {action}"}})


async def _handle_workflow(state, ws, msg_id, data):
    state.load_components()
    action = data.get("action", "")
    wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
    if not wf:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": "Workflow engine not available"}})
        return
    if action == "list":
        workflows = wf.list_workflows()
        await ws.send_json({"type": "workflow.list", "id": msg_id,
                            "data": {"workflows": workflows}})
    elif action == "create":
        success = wf.register_workflow(data.get("name", ""), data.get("steps", []))
        await ws.send_json({"type": "workflow.created", "id": msg_id,
                            "data": {"success": success, "name": data.get("name", "")}})
    elif action == "execute":
        try:
            result = await wf.execute_workflow(data.get("name", ""), data.get("context", {}))
            await ws.send_json({"type": "workflow.done", "id": msg_id, "data": {
                "success": result.success, "workflow_name": result.workflow_name,
                "steps_completed": result.steps_completed, "total_steps": result.total_steps,
                "duration_seconds": result.duration_seconds, "error": result.error,
            }})
        except Exception as e:
            await ws.send_json({"type": "error", "id": msg_id, "data": {"message": str(e)}})
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown workflow action: {action}"}})


async def _handle_task(state, ws, msg_id, data):
    state.load_components()
    action = data.get("action", "")
    tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
    if not tc:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": "Task automation not available"}})
        return
    if action == "list":
        await ws.send_json({"type": "task.list", "id": msg_id, "data": tc.get_active_tasks()})
    elif action == "create":
        task_def = tc.parse_complex_command(data.get("command", ""))
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tc.execute_task(task_def))
        await ws.send_json({"type": "task.created", "id": msg_id, "data": result})
    elif action == "status":
        await ws.send_json({"type": "task.status", "id": msg_id,
                            "data": tc.get_task_status(data.get("execution_id", ""))})
    elif action == "pause":
        await ws.send_json({"type": "task.paused", "id": msg_id,
                            "data": tc.pause_task(data.get("execution_id", ""))})
    elif action == "resume":
        await ws.send_json({"type": "task.resumed", "id": msg_id,
                            "data": tc.resume_task(data.get("execution_id", ""))})
    elif action == "cancel":
        await ws.send_json({"type": "task.cancelled", "id": msg_id,
                            "data": tc.cancel_task(data.get("execution_id", ""))})
    else:
        await ws.send_json({"type": "error", "id": msg_id,
                            "data": {"message": f"Unknown task action: {action}"}})
