"""
LADA API — Chat routes (/chat, /conversations, /models, /agents, /voice, /export)
"""

import os
import json
import logging
import threading
import concurrent.futures
from typing import Optional, Dict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Body, Header
from fastapi.responses import StreamingResponse, JSONResponse

from modules.api.models import (
    ChatRequest, ChatResponse, AgentRequest, AgentResponse, HealthResponse
)

logger = logging.getLogger(__name__)


def create_chat_router(state):
    """Create core chat/conversation/agent router."""
    r = APIRouter(tags=["chat"])

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
    async def chat(request: ChatRequest):
        state.load_components()
        if not state.ai_router:
            raise HTTPException(status_code=500, detail="AI Router not available")
        try:
            if request.conversation_id and state.chat_manager:
                conversation = state.chat_manager.load_conversation(request.conversation_id)
            else:
                conversation = None

            effective_model = request.model if request.model and request.model != 'auto' else None
            response = state.ai_router.query(
                request.message, model=effective_model, use_web_search=request.use_web_search,
            )
            conv_id = request.conversation_id or datetime.now().strftime("%Y%m%d_%H%M%S")
            if state.chat_manager:
                state.chat_manager.add_message(conv_id, "user", request.message)
                state.chat_manager.add_message(conv_id, "assistant", response)
            return ChatResponse(
                success=True, response=response, conversation_id=conv_id,
                model=state.ai_router.current_model or "unknown", sources=[],
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.error(f"[APIServer] Chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @r.post("/chat/stream")
    async def chat_stream(request: ChatRequest):
        state.load_components()
        if not state.ai_router:
            raise HTTPException(status_code=500, detail="AI Router not available")

        async def generate():
            try:
                if hasattr(state.ai_router, 'stream_query'):
                    for chunk in state.ai_router.stream_query(request.message):
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                else:
                    response = state.ai_router.query(request.message)
                    yield f"data: {json.dumps({'chunk': response})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @r.post("/agent", response_model=AgentResponse)
    async def execute_agent(request: AgentRequest):
        state.load_components()
        agent_name = request.agent.lower()
        if agent_name not in state.agents:
            raise HTTPException(status_code=404,
                detail=f"Agent '{agent_name}' not found. Available: {list(state.agents.keys())}")
        agent = state.agents[agent_name]
        action = request.action.lower()
        try:
            if hasattr(agent, action):
                result = getattr(agent, action)(**request.params)
            elif hasattr(agent, 'process'):
                result = agent.process(request.params.get('query', request.action))
            else:
                raise HTTPException(status_code=400,
                    detail=f"Action '{action}' not supported by {agent_name}")
            return AgentResponse(
                success=True, agent=agent_name, action=action, result=result,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.error(f"[APIServer] Agent error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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
            raise HTTPException(status_code=500, detail=str(e))

    @r.post("/voice/listen")
    async def voice_listen():
        try:
            from modules.advanced_voice import listen_for_command
            text = listen_for_command(timeout=10)
            if text:
                return {'success': True, 'text': text}
            return {'success': False, 'text': '', 'error': 'No speech detected'}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @r.post("/api/voice/direct")
    async def voice_direct(request: Dict = Body(...), authorization: Optional[str] = Header(None)):
        """Direct voice command endpoint for Alexa/Google Home."""
        expected_key = os.getenv("LADA_API_KEY", "lada-secret-key-12345")
        if not authorization or f"Bearer {expected_key}" != authorization:
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
                        logger.error(f"[APIServer] Background execution error: {e}")

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
        except Exception as e:
            logger.error(f"[APIServer] Error processing direct command: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return r
