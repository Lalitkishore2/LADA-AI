"""
LADA API — Chat routes (/chat, /conversations, /models, /agents, /voice, /export)

Security: Uses error sanitization to prevent internal details from leaking.
"""

import os
import json
import asyncio
import logging
import threading
import inspect
import concurrent.futures
from typing import Optional, Dict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Body, Header, Request, Response, Depends
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

from modules.api.models import (
    ChatRequest, ChatResponse, AgentRequest, AgentResponse, HealthResponse
)
from modules.api.deps import REQUEST_ID_HEADER, ensure_request_id, set_request_id_header
from modules.error_sanitizer import safe_error_response, SafeErrorResponse, ErrorCategory

logger = logging.getLogger(__name__)


def _parse_bearer_token(authorization: Optional[str]) -> str:
    raw = (authorization or "").strip()
    if not raw:
        return ""

    parts = raw.split(None, 1)
    if len(parts) != 2:
        return ""

    scheme, token = parts
    if scheme.lower() != "bearer":
        return ""

    return token.strip()


def create_chat_router(state):
    """Create core chat/conversation/agent router."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="http")

    r = APIRouter(tags=["chat"], dependencies=[Depends(_trace_request)])

    def _chat_timeout_seconds() -> float:
        raw_value = os.getenv("LADA_API_CHAT_TIMEOUT_SEC", "90").strip()
        try:
            parsed = float(raw_value)
        except ValueError:
            parsed = 90.0
        return max(1.0, min(parsed, 600.0))

    async def _run_query_with_timeout(query_fn, timeout_message: str):
        loop = asyncio.get_event_loop()
        timeout_seconds = _chat_timeout_seconds()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, query_fn),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise SafeErrorResponse(
                timeout_message,
                status_code=504,
                category=ErrorCategory.TIMEOUT,
            ) from exc

    def _supports_router_options(callable_obj) -> bool:
        try:
            params = inspect.signature(callable_obj).parameters.values()
        except (TypeError, ValueError):
            return True

        has_var_keyword = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
        if has_var_keyword:
            return True

        names = {param.name for param in params}
        return "model" in names or "use_web_search" in names

    def _query_ai_router(message: str, effective_model: Optional[str], use_web_search: bool):
        query_fn = state.ai_router.query
        if _supports_router_options(query_fn):
            return query_fn(message, model=effective_model, use_web_search=use_web_search)
        return query_fn(message)

    def _stream_query_ai_router(message: str, effective_model: Optional[str], use_web_search: bool):
        stream_fn = state.ai_router.stream_query
        if _supports_router_options(stream_fn):
            return stream_fn(message, model=effective_model, use_web_search=use_web_search)
        return stream_fn(message)

    @r.get("/", response_class=JSONResponse)
    async def root():
        return {"name": "LADA API", "version": "7.0.0", "status": "running", "docs": "/docs"}

    @r.get("/health", response_model=HealthResponse)
    async def health():
        state.load_components()
        uptime = (datetime.now() - state.start_time).total_seconds()
        return HealthResponse(
            status="healthy", version="7.0.0", uptime=uptime,
            agents=list(state.agents.keys()), models=["ollama", "gemini", "groq"],
        )

    @r.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest, http_request: Request, response: Response):
        request_id = ensure_request_id(http_request, prefix="http")
        response.headers[REQUEST_ID_HEADER] = request_id
        state.load_components()
        if not state.ai_router:
            raise HTTPException(
                status_code=500,
                detail="AI Router not available",
                headers={REQUEST_ID_HEADER: request_id},
            )
        try:
            if request.conversation_id and state.chat_manager:
                conversation = state.chat_manager.load_conversation(request.conversation_id)
            else:
                conversation = None

            if state.jarvis:
                loop = asyncio.get_event_loop()
                handled, system_response = await loop.run_in_executor(
                    None, state.jarvis.process, request.message
                )
                if handled:
                    conv_id = request.conversation_id or datetime.now().strftime("%Y%m%d_%H%M%S")
                    if state.chat_manager:
                        state.chat_manager.add_message(conv_id, "user", request.message)
                        state.chat_manager.add_message(conv_id, "assistant", system_response or "Command executed.")
                    return ChatResponse(
                        success=True,
                        response=system_response or "Command executed.",
                        conversation_id=conv_id,
                        model="system-command",
                        sources=[],
                        timestamp=datetime.now().isoformat(),
                    )

            effective_model = request.model if request.model and request.model != 'auto' else None
            ai_response = await _run_query_with_timeout(
                lambda: _query_ai_router(request.message, effective_model, request.use_web_search),
                "Chat request timed out. Please try again.",
            )
            conv_id = request.conversation_id or datetime.now().strftime("%Y%m%d_%H%M%S")
            if state.chat_manager:
                state.chat_manager.add_message(conv_id, "user", request.message)
                state.chat_manager.add_message(conv_id, "assistant", ai_response)
            return ChatResponse(
                success=True, response=ai_response, conversation_id=conv_id,
                model=state.ai_router.current_model or "unknown", sources=[],
                timestamp=datetime.now().isoformat(),
            )
        except SafeErrorResponse as e:
            # Pre-sanitized error with specific status code
            raise HTTPException(
                status_code=e.status_code,
                detail=e.message,
                headers={REQUEST_ID_HEADER: request_id},
            )
        except Exception as e:
            # Sanitize error before exposing to client
            error_info = safe_error_response(e, operation="chat_query")
            logger.error(f"[APIServer] Chat error ({request_id}): {type(e).__name__}")  # Don't log full message
            raise HTTPException(
                status_code=error_info["status_code"],
                detail=error_info["error"],
                headers={REQUEST_ID_HEADER: request_id},
            )

    @r.post("/chat/stream")
    async def chat_stream(request: ChatRequest, http_request: Request):
        request_id = ensure_request_id(http_request, prefix="http")
        state.load_components()
        if not state.ai_router:
            raise HTTPException(
                status_code=500,
                detail="AI Router not available",
                headers={REQUEST_ID_HEADER: request_id},
            )

        async def generate():
            try:
                if state.jarvis:
                    loop = asyncio.get_event_loop()
                    handled, system_response = await loop.run_in_executor(
                        None, state.jarvis.process, request.message
                    )
                    if handled:
                        yield f"data: {json.dumps({'type': 'chat.chunk', 'data': {'chunk': system_response or 'Command executed.', 'request_id': request_id, 'is_system_command': True}})}\n\n"
                        yield f"data: {json.dumps({'type': 'chat.done', 'data': {'done': True, 'request_id': request_id, 'is_system_command': True}})}\n\n"
                        return

                last_metadata = {}
                effective_model = request.model if request.model and request.model != "auto" else None
                if hasattr(state.ai_router, 'stream_query'):
                    q = asyncio.Queue()
                    loop = asyncio.get_event_loop()

                    def _stream_worker():
                        try:
                            stream_iter = _stream_query_ai_router(
                                request.message,
                                effective_model,
                                request.use_web_search,
                            )
                            for chunk in stream_iter:
                                asyncio.run_coroutine_threadsafe(q.put(chunk), loop)
                        except Exception as stream_exc:
                            asyncio.run_coroutine_threadsafe(q.put(stream_exc), loop)
                        finally:
                            asyncio.run_coroutine_threadsafe(q.put(None), loop)

                    loop.run_in_executor(None, _stream_worker)

                    while True:
                        try:
                            item = await asyncio.wait_for(q.get(), timeout=_chat_timeout_seconds())
                        except asyncio.TimeoutError as exc:
                            raise SafeErrorResponse(
                                "Streaming request timed out. Please try again.",
                                status_code=504,
                                category=ErrorCategory.TIMEOUT,
                            ) from exc

                        if item is None:
                            break
                        if isinstance(item, Exception):
                            raise item

                        if isinstance(item, dict):
                            if item.get("sources"):
                                yield f"data: {json.dumps({'type': 'chat.sources', 'data': {'sources': item.get('sources', []), 'request_id': request_id}})}\n\n"
                                continue

                            metadata = item.get("metadata", {})
                            metadata = metadata if isinstance(metadata, dict) else {}
                            if metadata:
                                last_metadata = metadata

                            if item.get("chunk"):
                                payload = {
                                    "type": "chat.chunk",
                                    "data": {
                                        "chunk": item.get("chunk", ""),
                                        "request_id": request_id,
                                    },
                                }
                                if metadata:
                                    payload["data"]["metadata"] = metadata
                                yield f"data: {json.dumps(payload)}\n\n"

                            if item.get("done"):
                                done_payload = {
                                    "type": "chat.done",
                                    "data": {"done": True, "request_id": request_id},
                                }
                                if metadata:
                                    done_payload["data"]["metadata"] = metadata
                                yield f"data: {json.dumps(done_payload)}\n\n"
                                return
                        else:
                            payload = {
                                "type": "chat.chunk",
                                "data": {"chunk": item, "request_id": request_id},
                            }
                            yield f"data: {json.dumps(payload)}\n\n"
                else:
                    response = await _run_query_with_timeout(
                        lambda: _query_ai_router(request.message, effective_model, request.use_web_search),
                        "Streaming request timed out. Please try again.",
                    )
                    yield f"data: {json.dumps({'type': 'chat.chunk', 'data': {'chunk': response, 'request_id': request_id}})}\n\n"

                done_payload = {"type": "chat.done", "data": {"done": True, "request_id": request_id}}
                if last_metadata:
                    done_payload["data"]["metadata"] = last_metadata
                yield f"data: {json.dumps(done_payload)}\n\n"
            except SafeErrorResponse as e:
                yield f"data: {json.dumps({'type': 'chat.error', 'data': {'error': e.message, 'status_code': e.status_code, 'request_id': request_id}})}\n\n"
            except Exception as e:
                error_info = safe_error_response(e, operation="chat_stream")
                logger.error(f"[APIServer] Chat stream error ({request_id}): {type(e).__name__}")
                yield f"data: {json.dumps({'type': 'chat.error', 'data': {'error': error_info['error'], 'status_code': error_info['status_code'], 'request_id': request_id}})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={REQUEST_ID_HEADER: request_id},
        )

    @r.post("/agent", response_model=AgentResponse)
    async def execute_agent(request: AgentRequest, http_request: Request, response: Response):
        request_id = ensure_request_id(http_request, prefix="http")
        response.headers[REQUEST_ID_HEADER] = request_id
        state.load_components()
        agent_name = request.agent.lower()
        if agent_name not in state.agents:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_name}' not found. Available: {list(state.agents.keys())}",
                headers={REQUEST_ID_HEADER: request_id},
            )
        agent = state.agents[agent_name]
        action = request.action.lower()
        try:
            if hasattr(agent, action):
                result = getattr(agent, action)(**request.params)
            elif hasattr(agent, 'process'):
                result = agent.process(request.params.get('query', request.action))
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Action '{action}' not supported by {agent_name}",
                    headers={REQUEST_ID_HEADER: request_id},
                )
            return AgentResponse(
                success=True, agent=agent_name, action=action, result=result,
                timestamp=datetime.now().isoformat(),
            )
        except HTTPException as e:
            merged_headers = dict(e.headers or {})
            merged_headers.setdefault(REQUEST_ID_HEADER, request_id)
            raise HTTPException(
                status_code=e.status_code,
                detail=e.detail,
                headers=merged_headers,
            ) from e
        except Exception as e:
            error_info = safe_error_response(e, operation="agent_execute")
            logger.error(f"[APIServer] Agent error ({request_id}): {type(e).__name__}")
            raise HTTPException(
                status_code=error_info["status_code"],
                detail=error_info["error"],
                headers={REQUEST_ID_HEADER: request_id},
            )

    @r.get("/agents")
    async def list_agents():
        state.load_components()
        agents_info = {}
        for name, agent in state.agents.items():
            methods = [m for m in dir(agent) if not m.startswith('_') and callable(getattr(agent, m))]
            agents_info[name] = {'class': agent.__class__.__name__, 'actions': methods[:10]}
        return {'count': len(state.agents), 'agents': agents_info}

    @r.get("/models")
    async def list_models():
        state.load_components()
        models = []
        if state.ai_router and hasattr(state.ai_router, 'get_all_available_models'):
            try:
                models = state.ai_router.get_all_available_models() or []
            except Exception as e:
                logger.warning(f"[APIServer] get_all_available_models failed: {e}")
        if (not models) and state.ai_router and hasattr(state.ai_router, 'get_provider_dropdown_items'):
            try:
                models = state.ai_router.get_provider_dropdown_items() or []
            except Exception as e:
                logger.warning(f"[APIServer] get_provider_dropdown_items failed: {e}")
        return {'count': len(models), 'models': models}

    @r.get("/conversations")
    async def list_conversations():
        state.load_components()
        if not state.chat_manager:
            return {'count': 0, 'conversations': []}
        conversations = state.chat_manager.list_conversations()
        return {
            'count': len(conversations),
            'conversations': [
                {'id': c.get('id'), 'title': c.get('title', 'Untitled'),
                 'message_count': c.get('message_count', 0),
                 'created_at': c.get('created_at', ''), 'updated_at': c.get('updated_at', '')}
                for c in conversations
            ],
        }

    @r.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str):
        state.load_components()
        if not state.chat_manager:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation = state.chat_manager.load_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {
            'id': conversation.id, 'title': conversation.title,
            'messages': [{'role': m.role, 'content': m.content, 'timestamp': m.timestamp}
                         for m in conversation.messages],
            'created_at': conversation.created_at, 'updated_at': conversation.updated_at,
        }

    @r.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str):
        state.load_components()
        if not state.chat_manager:
            raise HTTPException(status_code=404, detail="Conversation not found")
        success = state.chat_manager.delete_conversation(conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {'success': True, 'message': f'Conversation {conversation_id} deleted'}

    @r.post("/export/{conversation_id}")
    async def export_conversation(
        conversation_id: str,
        format: str = Query("markdown", description="Export format: markdown, json, pdf, docx"),
    ):
        state.load_components()
        if not state.chat_manager:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conversation = state.chat_manager.load_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        try:
            from modules.export_manager import ExportManager
            exporter = ExportManager()
            export_path = exporter.export_conversation(conversation, format)
            return {'success': True, 'format': format, 'path': str(export_path)}
        except Exception as e:
            error_info = safe_error_response(e, operation="export_conversation")
            raise HTTPException(status_code=error_info["status_code"], detail=error_info["error"])

    @r.post("/voice/listen")
    async def voice_listen():
        try:
            from modules.advanced_voice import listen_for_command
            text = listen_for_command(timeout=10)
            if text:
                return {'success': True, 'text': text}
            return {'success': False, 'text': '', 'error': 'No speech detected'}
        except Exception as e:
            error_info = safe_error_response(e, operation="voice_listen")
            raise HTTPException(status_code=error_info["status_code"], detail=error_info["error"])

    @r.post("/api/voice/direct")
    async def voice_direct(request: Dict = Body(...), authorization: Optional[str] = Header(None)):
        """Direct voice command endpoint for Alexa/Google Home."""
        expected_key = os.getenv("LADA_API_KEY", "lada-secret-key-12345").strip()
        provided_key = _parse_bearer_token(authorization)
        if provided_key != expected_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

        command = request.get("command")
        if not command:
            raise HTTPException(status_code=400, detail="Missing command")

        source = request.get("source", "unknown")
        full_ai_mode = request.get("full_ai", False)
        logger.info(f"[APIServer] Direct command from {source}: {command} (full_ai={full_ai_mode})")
        use_fast_mode = source in ["alexa", "google_home", "echo_dot"]

        try:
            # FULL AI MODE
            if full_ai_mode or source == "echo_dot":
                state.load_components()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    if state.voice_processor:
                        try:
                            future = executor.submit(state.voice_processor.process, command)
                            handled, vp_response = future.result(timeout=3)
                            if handled and vp_response:
                                if len(vp_response) > 250:
                                    vp_response = vp_response[:250] + "..."
                                return {"success": True, "voice_response": vp_response,
                                        "timestamp": datetime.now().isoformat()}
                        except concurrent.futures.TimeoutError:
                            pass

                    if state.jarvis:
                        try:
                            future = executor.submit(state.jarvis.process, command)
                            success, jarvis_response = future.result(timeout=5)
                            if jarvis_response:
                                if len(jarvis_response) > 250:
                                    jarvis_response = jarvis_response[:250] + "..."
                                return {"success": success, "voice_response": jarvis_response,
                                        "timestamp": datetime.now().isoformat()}
                        except concurrent.futures.TimeoutError:
                            def background_execute():
                                try:
                                    state.jarvis.process(command)
                                except Exception as e:
                                    logger.error(f"Background error: {e}")
                            threading.Thread(target=background_execute, daemon=True).start()
                            return {"success": True,
                                    "voice_response": "Working on it! Your command is being executed.",
                                    "timestamp": datetime.now().isoformat()}

                    if state.ai_router:
                        try:
                            future = executor.submit(state.ai_router.query, command)
                            ai_response = future.result(timeout=4)
                            if ai_response:
                                if len(ai_response) > 250:
                                    ai_response = ai_response[:250] + "..."
                                return {"success": True, "voice_response": ai_response,
                                        "timestamp": datetime.now().isoformat()}
                        except concurrent.futures.TimeoutError:
                            pass

                return {"success": True, "voice_response": "Command received. Working on it.",
                        "timestamp": datetime.now().isoformat()}

            # FAST MODE (legacy Alexa path)
            if use_fast_mode:
                cmd_lower = command.lower()
                query_patterns = ['what', 'when', 'where', 'who', 'how', 'why', 'is it', 'are there',
                                  'time', 'date', 'battery', 'weather', 'status', 'tell me']
                is_query = any(cmd_lower.startswith(p) or p in cmd_lower for p in query_patterns)

                if is_query:
                    if state.voice_processor is None:
                        try:
                            from modules.voice_nlu import VoiceCommandProcessor
                            state.voice_processor = VoiceCommandProcessor()
                        except Exception:
                            pass
                    if state.voice_processor:
                        handled, vp_response = state.voice_processor.process(command)
                        if handled and vp_response:
                            if len(vp_response) > 300:
                                vp_response = vp_response[:300] + "..."
                            return {"success": True, "voice_response": vp_response,
                                    "timestamp": datetime.now().isoformat()}

                action_acks = {
                    'open': "Opening that for you.", 'close': "Closing that.",
                    'create': "Creating that now.", 'make': "Making that for you.",
                    'set': "Setting that up.", 'play': "Playing now.",
                    'stop': "Stopping.", 'pause': "Pausing.",
                    'search': "Searching for that.", 'find': "Finding that.",
                    'show': "Showing that.", 'take': "Taking that.",
                    'send': "Sending that.", 'type': "Typing that.",
                    'click': "Clicking.", 'go': "Going there.",
                    'navigate': "Navigating.", 'run': "Running that.",
                    'start': "Starting.", 'launch': "Launching.",
                    'minimize': "Minimizing.", 'maximize': "Maximizing.",
                    'switch': "Switching.", 'mute': "Muting.",
                    'unmute': "Unmuting.", 'volume': "Adjusting volume.",
                    'brightness': "Adjusting brightness.",
                    'screenshot': "Taking a screenshot.",
                    'lock': "Locking the screen.", 'shutdown': "Initiating shutdown.",
                    'restart': "Restarting.", 'sleep': "Going to sleep mode.",
                }
                ack_response = "Got it! Working on that."
                for verb, ack in action_acks.items():
                    if cmd_lower.startswith(verb) or f" {verb} " in f" {cmd_lower} ":
                        ack_response = ack
                        break

                def execute_command():
                    try:
                        state.load_components()
                        if state.voice_processor:
                            handled, _ = state.voice_processor.process(command)
                            if handled:
                                return
                        if state.jarvis:
                            state.jarvis.process(command)
                    except Exception as e:
                        logger.error(f"[APISServer] Background execution error: {e}")

                threading.Thread(target=execute_command, daemon=True).start()
                return {"success": True, "voice_response": ack_response,
                        "timestamp": datetime.now().isoformat()}

            # Non-Alexa mode
            state.load_components()
            if state.voice_processor:
                handled, vp_response = state.voice_processor.process(command)
                if handled and vp_response:
                    if len(vp_response) > 400:
                        vp_response = vp_response[:400] + "..."
                    return {"success": True, "voice_response": vp_response,
                            "timestamp": datetime.now().isoformat()}

            if state.jarvis:
                success, response = state.jarvis.process(command)
                if len(response) > 400:
                    response = response[:400] + "..."
                return {"success": success, "voice_response": response,
                        "timestamp": datetime.now().isoformat()}
            else:
                response = state.ai_router.query(command)
                return {"success": True, "voice_response": response,
                        "timestamp": datetime.now().isoformat()}
        except HTTPException:
            raise
        except Exception as e:
            error_info = safe_error_response(e, operation="voice_direct")
            logger.error(f"[APIServer] Error processing direct command: {type(e).__name__}")
            raise HTTPException(status_code=error_info["status_code"], detail=error_info["error"])

    @r.post("/files/search")
    async def search_files(
        request: Request,
        query: str = Body(..., embed=True),
        max_results: int = Body(10, embed=True),
        search_folder: str = Body(None, embed=True)
    ):
        """Search for files on the local system"""
        request_id = ensure_request_id(request, prefix="http")
        state.load_components()
        
        try:
            # Check if file operations are available
            try:
                from modules.file_operations import FileSystemController
                file_controller = FileSystemController()
            except ImportError:
                raise HTTPException(
                    status_code=501,
                    detail="File operations module not available"
                )
            
            # Search for files
            result = file_controller.search_files(
                name=query,
                search_folder=search_folder,
                recursive=True,
                max_results=max_results
            )
            
            if not result.get('success'):
                raise HTTPException(
                    status_code=500,
                    detail=result.get('error', 'File search failed')
                )
            
            files = result.get('files', [])
            
            return {
                'success': True,
                'query': query,
                'found': len(files),
                'files': files,
                'search_folder': result.get('search_folder'),
                'request_id': request_id
            }
            
        except HTTPException:
            raise
        except Exception as e:
            error_info = safe_error_response(e, operation="file_search")
            logger.error(f"[APIServer] File search error ({request_id}): {type(e).__name__}")
            raise HTTPException(
                status_code=error_info["status_code"],
                detail=error_info["error"],
                headers={REQUEST_ID_HEADER: request_id},
            )

    @r.get("/files/download")
    async def download_file(
        request: Request,
        path: str = Query(...)
    ):
        """Download a file from the local system"""
        request_id = ensure_request_id(request, prefix="http")
        
        try:
            # Validate and resolve path
            from pathlib import Path
            file_path = Path(path)
            if not file_path.is_absolute():
                # Use current directory or home directory as base
                try:
                    from modules.file_operations import FileSystemController
                    file_controller = FileSystemController()
                    file_path = Path(file_controller.current_directory) / path
                except:
                    file_path = Path.home() / path
            
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found")
            
            if not file_path.is_file():
                raise HTTPException(status_code=400, detail="Path is not a file")
            
            # Security check - prevent access to system files
            system_paths = [
                'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)',
                'C:\\ProgramData', 'C:\\System Volume Information'
            ]
            if any(str(file_path).startswith(sys_path) for sys_path in system_paths):
                raise HTTPException(status_code=403, detail="Access to system files denied")
            
            # Return file
            response = FileResponse(
                path=str(file_path),
                filename=file_path.name,
                media_type="application/octet-stream"
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            error_info = safe_error_response(e, operation="file_download")
            logger.error(f"[APIServer] File download error ({request_id}): {type(e).__name__}")
            raise HTTPException(
                status_code=error_info["status_code"],
                detail=error_info["error"],
                headers={REQUEST_ID_HEADER: request_id},
            )

    return r
