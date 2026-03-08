"""
LADA v8.0 - API Server & WebSocket Gateway
FastAPI REST endpoints + WebSocket real-time messaging for external access.

Features:
- REST API (12+ endpoints) for chat, agents, conversations, voice
- WebSocket gateway for real-time bidirectional messaging
- SSE streaming for chat responses
- Static file serving for web dashboard
"""

import os
import sys
import json
import logging
import asyncio
import uuid
import time
import secrets
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import FastAPI
try:
    from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks, Header, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
    import uvicorn
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False
    logger.warning("[APIServer] FastAPI not installed. Run: pip install fastapi uvicorn")


# ============================================================
# PYDANTIC MODELS
# ============================================================

if FASTAPI_OK:
    class ChatRequest(BaseModel):
        """Chat request model."""
        message: str = Field(..., description="User message")
        conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
        stream: bool = Field(False, description="Enable streaming response")
        model: Optional[str] = Field(None, description="AI model to use")
        use_web_search: bool = Field(False, description="Enable web search")

    class ChatResponse(BaseModel):
        """Chat response model."""
        success: bool
        response: str
        conversation_id: str
        model: str
        sources: List[Dict] = []
        timestamp: str

    class AgentRequest(BaseModel):
        """Agent request model."""
        agent: str = Field(..., description="Agent type: flight, hotel, restaurant, email, calendar")
        action: str = Field(..., description="Action to perform")
        params: Dict = Field(default_factory=dict, description="Action parameters")

    class AgentResponse(BaseModel):
        """Agent response model."""
        success: bool
        agent: str
        action: str
        result: Dict
        timestamp: str

    class ConversationInfo(BaseModel):
        """Conversation info model."""
        id: str
        title: str
        message_count: int
        created_at: str
        updated_at: str

    class HealthResponse(BaseModel):
        """Health check response."""
        status: str
        version: str
        uptime: float
        agents: List[str]
        models: List[str]

    # OpenAI-compatible models (for /v1 API consumers)
    class OpenAIChatMessage(BaseModel):
        """OpenAI-compatible chat message."""
        role: str
        content: str

    class OpenAIChatRequest(BaseModel):
        """OpenAI-compatible chat completions request."""
        model: str = Field("auto", description="Model ID or 'auto' for LADA tier routing")
        messages: List[OpenAIChatMessage] = Field(default_factory=list)
        stream: bool = Field(False)
        temperature: Optional[float] = Field(0.7)
        max_tokens: Optional[int] = Field(2048)


# ============================================================
# API SERVER CLASS
# ============================================================

class LADAAPIServer:
    """
    FastAPI-based REST API server + WebSocket gateway for LADA.

    REST Endpoints:
    - POST /chat - Send chat message
    - POST /chat/stream - Stream chat response
    - POST /agent - Execute agent action
    - POST /api/voice/direct - Direct voice command (Alexa/Google)
    - GET /conversations - List conversations
    - GET /conversations/{id} - Get conversation
    - DELETE /conversations/{id} - Delete conversation
    - GET /health - Health check

    WebSocket:
    - /ws - Real-time bidirectional messaging gateway

    Web Dashboard:
    - /dashboard - Web-based chat interface
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        self.host = host
        self.port = port
        self.start_time = datetime.now()

        # Session auth
        self._auth_password = os.getenv("LADA_WEB_PASSWORD", "lada1434")
        self._session_tokens: Dict[str, float] = {}  # token -> expiry timestamp
        self._session_ttl = int(os.getenv("LADA_SESSION_TTL", "86400"))  # 24h default

        # Initialize components (lazy load)
        self.ai_router = None
        self.chat_manager = None
        self.jarvis = None
        self.voice_processor = None
        self.agents = {}

        # WebSocket connection management
        self._ws_connections: Dict[str, WebSocket] = {}  # session_id -> websocket
        self._ws_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session data
        
        if not FASTAPI_OK:
            logger.error("[APIServer] FastAPI not available")
            return
        
        # Create FastAPI app
        self.app = FastAPI(
            title="LADA API",
            description="LADA v7.0 REST API - Your AI Assistant",
            version="7.0.0",
            docs_url="/docs",
            redoc_url="/redoc"
        )
        
        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add session auth middleware
        @self.app.middleware("http")
        async def auth_middleware(request, call_next):
            """Require valid session token on all routes except public ones."""
            path = request.url.path

            # Public routes (no auth needed)
            public_paths = [
                "/auth/login", "/health", "/docs", "/redoc", "/openapi.json",
                "/app", "/dashboard",
            ]
            # Serve the HTML page without auth (login screen is inside it)
            if any(path == p or path.startswith(p + "/") for p in public_paths):
                return await call_next(request)
            # Static files
            if path.startswith("/static"):
                return await call_next(request)
            # Root endpoint
            if path == "/":
                return await call_next(request)
            # /v1/* endpoints use their own LADA_API_KEY auth
            if path.startswith("/v1/"):
                return await call_next(request)

            # Extract session token from header or query param
            auth_header = request.headers.get("authorization", "")
            token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
            if not token:
                token = request.query_params.get("token", "")

            if not self._validate_session_token(token):
                from starlette.responses import JSONResponse as SJR
                return SJR(status_code=401, content={"detail": "Authentication required"})

            return await call_next(request)

        # Register auth routes first
        self._register_auth_routes()

        # Register routes
        self._register_routes()
        self._register_marketplace_routes()
        self._register_websocket_gateway()
        self._register_dashboard()
        self._register_openai_compat_routes()
        self._register_lada_app_routes()
        self._register_orchestration_routes()
    
    # ── Session Auth Helpers ──────────────────────────────────

    def _create_session_token(self) -> str:
        """Create a new session token with TTL."""
        token = secrets.token_hex(32)
        self._session_tokens[token] = time.time() + self._session_ttl
        # Prune expired tokens
        now = time.time()
        self._session_tokens = {t: exp for t, exp in self._session_tokens.items() if exp > now}
        return token

    def _validate_session_token(self, token: str) -> bool:
        """Check if a session token is valid and not expired."""
        if not token:
            return False
        expiry = self._session_tokens.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._session_tokens[token]
            return False
        return True

    def _register_auth_routes(self):
        """Register authentication endpoints."""

        @self.app.post("/auth/login")
        async def auth_login(body: dict = Body(default={})):
            """Validate password and return a session token."""
            password = body.get("password", "")
            if password == self._auth_password:
                token = self._create_session_token()
                return {"success": True, "token": token, "expires_in": self._session_ttl}
            raise HTTPException(status_code=401, detail="Invalid password")

        @self.app.get("/auth/check")
        async def auth_check(authorization: Optional[str] = Header(None)):
            """Check if current session token is still valid."""
            token = ""
            if authorization and authorization.startswith("Bearer "):
                token = authorization[7:]
            if self._validate_session_token(token):
                return {"valid": True}
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        @self.app.post("/auth/logout")
        async def auth_logout(authorization: Optional[str] = Header(None)):
            """Invalidate a session token."""
            token = ""
            if authorization and authorization.startswith("Bearer "):
                token = authorization[7:]
            self._session_tokens.pop(token, None)
            return {"success": True}

    def _load_components(self):
        """Lazy load LADA components."""
        if self.ai_router is None:
            try:
                from lada_ai_router import HybridAIRouter
                self.ai_router = HybridAIRouter()
            except Exception as e:
                logger.error(f"[APIServer] Failed to load AIRouter: {e}")
        
        if self.chat_manager is None:
            try:
                from modules.chat_manager import ChatManager
                self.chat_manager = ChatManager()
            except Exception as e:
                logger.error(f"[APIServer] Failed to load ChatManager: {e}")

        if self.jarvis is None:
            try:
                from lada_jarvis_core import JarvisCommandProcessor
                self.jarvis = JarvisCommandProcessor()
                logger.info("[APIServer] Loaded JarvisCommandProcessor")
            except Exception as e:
                logger.error(f"[APIServer] Failed to load Jarvis: {e}")

        if self.voice_processor is None:
            try:
                from modules.voice_nlu import VoiceCommandProcessor
                self.voice_processor = VoiceCommandProcessor()
                logger.info("[APIServer] Loaded VoiceCommandProcessor")
            except Exception as e:
                logger.error(f"[APIServer] Failed to load VoiceCommandProcessor: {e}")
        
        if not self.agents:
            self._load_agents()
    
    def _load_agents(self):
        """Load available agents."""
        agent_map = {
            'flight': ('modules.agents.flight_agent', 'FlightAgent'),
            'hotel': ('modules.agents.hotel_agent', 'HotelAgent'),
            'restaurant': ('modules.agents.restaurant_agent', 'RestaurantAgent'),
            'email': ('modules.agents.email_agent', 'EmailAgent'),
            'calendar': ('modules.agents.calendar_agent', 'CalendarAgent'),
            'product': ('modules.agents.product_agent', 'ProductAgent'),
        }
        
        for agent_name, (module_path, class_name) in agent_map.items():
            try:
                module = __import__(module_path, fromlist=[class_name])
                agent_class = getattr(module, class_name)
                self.agents[agent_name] = agent_class()
                logger.info(f"[APIServer] Loaded agent: {agent_name}")
            except Exception as e:
                logger.warning(f"[APIServer] Failed to load {agent_name}: {e}")
    
    def _register_routes(self):
        """Register API routes."""
        
        @self.app.get("/", response_class=JSONResponse)
        async def root():
            """API root endpoint."""
            return {
                "name": "LADA API",
                "version": "7.0.0",
                "status": "running",
                "docs": "/docs"
            }
        
        @self.app.get("/health", response_model=HealthResponse)
        async def health():
            """Health check endpoint."""
            self._load_components()
            
            uptime = (datetime.now() - self.start_time).total_seconds()
            
            return HealthResponse(
                status="healthy",
                version="7.0.0",
                uptime=uptime,
                agents=list(self.agents.keys()),
                models=["ollama", "gemini", "groq"]
            )
        
        @self.app.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """Send a chat message."""
            self._load_components()
            
            if not self.ai_router:
                raise HTTPException(status_code=500, detail="AI Router not available")
            
            try:
                # Get or create conversation
                if request.conversation_id and self.chat_manager:
                    conversation = self.chat_manager.load_conversation(request.conversation_id)
                else:
                    conversation = None
                
                # Build context from conversation history
                context = ""
                if conversation and conversation.messages:
                    recent = conversation.messages[-6:]  # Last 6 messages
                    context = "\n".join([
                        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
                        for m in recent
                    ])
                
                # Query AI
                response = self.ai_router.query(
                    request.message,
                    context=context,
                    use_web_search=request.use_web_search
                )
                
                # Save to conversation
                conv_id = request.conversation_id or datetime.now().strftime("%Y%m%d_%H%M%S")
                if self.chat_manager:
                    self.chat_manager.add_message(conv_id, "user", request.message)
                    self.chat_manager.add_message(conv_id, "assistant", response)
                
                return ChatResponse(
                    success=True,
                    response=response,
                    conversation_id=conv_id,
                    model=self.ai_router.current_model or "unknown",
                    sources=[],
                    timestamp=datetime.now().isoformat()
                )
                
            except Exception as e:
                logger.error(f"[APIServer] Chat error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/chat/stream")
        async def chat_stream(request: ChatRequest):
            """Stream a chat response."""
            self._load_components()
            
            if not self.ai_router:
                raise HTTPException(status_code=500, detail="AI Router not available")
            
            async def generate():
                try:
                    # Check if streaming is available
                    if hasattr(self.ai_router, 'stream_query'):
                        for chunk in self.ai_router.stream_query(request.message):
                            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                    else:
                        # Fallback to regular query
                        response = self.ai_router.query(request.message)
                        yield f"data: {json.dumps({'chunk': response})}\n\n"
                    
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream"
            )
        
        @self.app.post("/agent", response_model=AgentResponse)
        async def execute_agent(request: AgentRequest):
            """Execute an agent action."""
            self._load_components()
            
            agent_name = request.agent.lower()
            
            if agent_name not in self.agents:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_name}' not found. Available: {list(self.agents.keys())}"
                )
            
            agent = self.agents[agent_name]
            action = request.action.lower()
            
            try:
                # Map actions to methods
                if hasattr(agent, action):
                    method = getattr(agent, action)
                    result = method(**request.params)
                elif hasattr(agent, 'process'):
                    # Use generic process method
                    query = request.params.get('query', request.action)
                    result = agent.process(query)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Action '{action}' not supported by {agent_name}"
                    )
                
                return AgentResponse(
                    success=True,
                    agent=agent_name,
                    action=action,
                    result=result,
                    timestamp=datetime.now().isoformat()
                )
                
            except Exception as e:
                logger.error(f"[APIServer] Agent error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/agents")
        async def list_agents():
            """List available agents and their actions."""
            self._load_components()
            
            agents_info = {}
            for name, agent in self.agents.items():
                # Get public methods
                methods = [
                    m for m in dir(agent)
                    if not m.startswith('_') and callable(getattr(agent, m))
                ]
                agents_info[name] = {
                    'class': agent.__class__.__name__,
                    'actions': methods[:10]  # Limit to 10
                }
            
            return {
                'count': len(self.agents),
                'agents': agents_info
            }

        @self.app.get("/models")
        async def list_models():
            """List models for UI dropdown (includes offline entries for visibility)."""
            self._load_components()

            models = []
            if self.ai_router and hasattr(self.ai_router, 'get_all_available_models'):
                try:
                    models = self.ai_router.get_all_available_models() or []
                except Exception as e:
                    logger.warning(f"[APIServer] get_all_available_models failed: {e}")

            # Fallback to provider-manager list if registry list was unavailable
            if (not models) and self.ai_router and hasattr(self.ai_router, 'get_provider_dropdown_items'):
                try:
                    models = self.ai_router.get_provider_dropdown_items() or []
                except Exception as e:
                    logger.warning(f"[APIServer] get_provider_dropdown_items failed: {e}")

            return {
                'count': len(models),
                'models': models,
            }
        
        @self.app.get("/conversations")
        async def list_conversations():
            """List all conversations."""
            self._load_components()
            
            if not self.chat_manager:
                return {'count': 0, 'conversations': []}
            
            conversations = self.chat_manager.list_conversations()
            
            return {
                'count': len(conversations),
                'conversations': [
                    {
                        'id': c.get('id'),
                        'title': c.get('title', 'Untitled'),
                        'message_count': c.get('message_count', 0),
                        'created_at': c.get('created_at', ''),
                        'updated_at': c.get('updated_at', '')
                    }
                    for c in conversations
                ]
            }
        
        @self.app.get("/conversations/{conversation_id}")
        async def get_conversation(conversation_id: str):
            """Get a specific conversation."""
            self._load_components()
            
            if not self.chat_manager:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            conversation = self.chat_manager.load_conversation(conversation_id)
            
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            return {
                'id': conversation.id,
                'title': conversation.title,
                'messages': [
                    {
                        'role': m.role,
                        'content': m.content,
                        'timestamp': m.timestamp
                    }
                    for m in conversation.messages
                ],
                'created_at': conversation.created_at,
                'updated_at': conversation.updated_at
            }
        
        @self.app.delete("/conversations/{conversation_id}")
        async def delete_conversation(conversation_id: str):
            """Delete a conversation."""
            self._load_components()
            
            if not self.chat_manager:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            success = self.chat_manager.delete_conversation(conversation_id)
            
            if not success:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            return {'success': True, 'message': f'Conversation {conversation_id} deleted'}
        
        @self.app.post("/export/{conversation_id}")
        async def export_conversation(
            conversation_id: str,
            format: str = Query("markdown", description="Export format: markdown, json, pdf, docx")
        ):
            """Export a conversation."""
            self._load_components()
            
            if not self.chat_manager:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            conversation = self.chat_manager.load_conversation(conversation_id)
            
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            try:
                from modules.export_manager import ExportManager
                exporter = ExportManager()
                
                export_path = exporter.export_conversation(conversation, format)
                
                return {
                    'success': True,
                    'format': format,
                    'path': str(export_path)
                }
                
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/voice/listen")
        async def voice_listen():
            """Listen for voice input."""
            try:
                from modules.advanced_voice import listen_for_command
                
                text = listen_for_command(timeout=10)
                
                if text:
                    return {'success': True, 'text': text}
                else:
                    return {'success': False, 'text': '', 'error': 'No speech detected'}
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/voice/direct")
        async def voice_direct(
            request: Dict = Body(...),
            authorization: Optional[str] = Header(None)
        ):
            """
            Direct voice command endpoint for Alexa/Google Home.
            Expects: {"command": "...", "source": "alexa"}
            """
            # Simple API Key check FIRST (before loading components)
            expected_key = os.getenv("LADA_API_KEY", "lada-secret-key-12345")
            if not authorization or f"Bearer {expected_key}" != authorization:
                logger.warning(f"[APIServer] Unauthorized access attempt from {request.get('source', 'unknown')}")
                raise HTTPException(status_code=401, detail="Unauthorized")
            
            command = request.get("command")
            if not command:
                raise HTTPException(status_code=400, detail="Missing command")
            
            source = request.get("source", "unknown")
            full_ai_mode = request.get("full_ai", False)  # Request full AI processing
            logger.info(f"[APIServer] Received direct command from {source}: {command} (full_ai={full_ai_mode})")
            
            # For Alexa/Echo, we need to respond quickly (< 8 seconds)
            use_fast_mode = source in ["alexa", "google_home", "echo_dot"]
            
            try:
                import threading
                import concurrent.futures
                
                # ============ FULL AI MODE (for complex commands) ============
                # When full_ai=True, use Jarvis with timeout for intelligent processing
                if full_ai_mode or source == "echo_dot":
                    # Load components first
                    self._load_components()
                    
                    # Try to get response within timeout
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        # Try VoiceProcessor first for quick pattern-matched commands
                        if self.voice_processor:
                            try:
                                future = executor.submit(self.voice_processor.process, command)
                                handled, vp_response = future.result(timeout=3)
                                if handled and vp_response:
                                    if len(vp_response) > 250:
                                        vp_response = vp_response[:250] + "..."
                                    logger.info(f"[APIServer] VoiceProcessor response: {vp_response}")
                                    return {
                                        "success": True,
                                        "voice_response": vp_response,
                                        "timestamp": datetime.now().isoformat()
                                    }
                            except concurrent.futures.TimeoutError:
                                logger.info("[APIServer] VoiceProcessor timed out, trying Jarvis...")
                        
                        # Use full Jarvis AI for complex commands
                        if self.jarvis:
                            try:
                                future = executor.submit(self.jarvis.process, command)
                                success, jarvis_response = future.result(timeout=5)
                                
                                if jarvis_response:
                                    if len(jarvis_response) > 250:
                                        jarvis_response = jarvis_response[:250] + "..."
                                    logger.info(f"[APIServer] Jarvis response: {jarvis_response}")
                                    return {
                                        "success": success,
                                        "voice_response": jarvis_response,
                                        "timestamp": datetime.now().isoformat()
                                    }
                            except concurrent.futures.TimeoutError:
                                # Jarvis is taking too long but command is executing
                                logger.info("[APIServer] Jarvis timeout - executing in background")
                                
                                # Continue execution in background
                                def background_execute():
                                    try:
                                        self.jarvis.process(command)
                                    except Exception as e:
                                        logger.error(f"Background error: {e}")
                                
                                threading.Thread(target=background_execute, daemon=True).start()
                                
                                return {
                                    "success": True,
                                    "voice_response": "Working on it! Your command is being executed.",
                                    "timestamp": datetime.now().isoformat()
                                }
                        
                        # Fallback to AI Router for general queries
                        if self.ai_router:
                            try:
                                future = executor.submit(self.ai_router.query, command)
                                ai_response = future.result(timeout=4)
                                if ai_response:
                                    if len(ai_response) > 250:
                                        ai_response = ai_response[:250] + "..."
                                    return {
                                        "success": True,
                                        "voice_response": ai_response,
                                        "timestamp": datetime.now().isoformat()
                                    }
                            except concurrent.futures.TimeoutError:
                                pass
                    
                    # If nothing worked, return generic acknowledgment
                    return {
                        "success": True,
                        "voice_response": "Command received. Working on it.",
                        "timestamp": datetime.now().isoformat()
                    }
                
                # ============ FAST MODE (legacy Alexa path) ============
                if use_fast_mode:
                    cmd_lower = command.lower()
                    
                    # Check if this is a QUERY (needs immediate answer) vs ACTION (can ack + background)
                    query_patterns = ['what', 'when', 'where', 'who', 'how', 'why', 'is it', 'are there', 
                                      'time', 'date', 'battery', 'weather', 'status', 'tell me']
                    is_query = any(cmd_lower.startswith(p) or p in cmd_lower for p in query_patterns)
                    
                    # For queries, try to get immediate answer from VoiceProcessor
                    if is_query:
                        # Load VoiceProcessor if needed (fast)
                        if self.voice_processor is None:
                            try:
                                from modules.voice_nlu import VoiceCommandProcessor
                                self.voice_processor = VoiceCommandProcessor()
                            except Exception as e:
                                logger.error(f"[APIServer] Failed to load VoiceCommandProcessor: {e}")
                        
                        if self.voice_processor:
                            handled, vp_response = self.voice_processor.process(command)
                            if handled and vp_response:
                                if len(vp_response) > 300:
                                    vp_response = vp_response[:300] + "..."
                                return {
                                    "success": True,
                                    "voice_response": vp_response,
                                    "timestamp": datetime.now().isoformat()
                                }
                    
                    # For actions, acknowledge immediately and execute in background
                    action_acks = {
                        'open': f"Opening that for you.",
                        'close': f"Closing that.",
                        'create': f"Creating that now.",
                        'make': f"Making that for you.",
                        'set': f"Setting that up.",
                        'play': f"Playing now.",
                        'stop': f"Stopping.",
                        'pause': f"Pausing.",
                        'search': f"Searching for that.",
                        'find': f"Finding that.",
                        'show': f"Showing that.",
                        'take': f"Taking that.",
                        'send': f"Sending that.",
                        'type': f"Typing that.",
                        'click': f"Clicking.",
                        'go': f"Going there.",
                        'navigate': f"Navigating.",
                        'run': f"Running that.",
                        'start': f"Starting.",
                        'launch': f"Launching.",
                        'minimize': f"Minimizing.",
                        'maximize': f"Maximizing.",
                        'switch': f"Switching.",
                        'mute': f"Muting.",
                        'unmute': f"Unmuting.",
                        'volume': f"Adjusting volume.",
                        'brightness': f"Adjusting brightness.",
                        'screenshot': f"Taking a screenshot.",
                        'lock': f"Locking the screen.",
                        'shutdown': f"Initiating shutdown.",
                        'restart': f"Restarting.",
                        'sleep': f"Going to sleep mode.",
                    }
                    
                    # Find matching acknowledgment
                    ack_response = "Got it! Working on that."
                    for verb, ack in action_acks.items():
                        if cmd_lower.startswith(verb) or f" {verb} " in f" {cmd_lower} ":
                            ack_response = ack
                            break
                    
                    # Execute command in background thread (lazy load components there)
                    def execute_command():
                        try:
                            # Lazy load components in background
                            self._load_components()
                            
                            # Try VoiceProcessor first (fast pattern matching)
                            if self.voice_processor:
                                handled, _ = self.voice_processor.process(command)
                                if handled:
                                    logger.info(f"[APIServer] VoiceProcessor handled: {command}")
                                    return
                            
                            # Fall back to full Jarvis
                            if self.jarvis:
                                self.jarvis.process(command)
                                logger.info(f"[APIServer] Jarvis processed: {command}")
                        except Exception as e:
                            logger.error(f"[APIServer] Background execution error: {e}")
                    
                    # Start background execution
                    threading.Thread(target=execute_command, daemon=True).start()
                    
                    # Return immediate acknowledgment
                    return {
                        "success": True,
                        "voice_response": ack_response,
                        "timestamp": datetime.now().isoformat()
                    }
                
                # Non-Alexa mode: load components and wait for full response
                self._load_components()
                
                # Try VoiceProcessor first for quick commands
                if self.voice_processor:
                    handled, vp_response = self.voice_processor.process(command)
                    if handled and vp_response:
                        if len(vp_response) > 400:
                            vp_response = vp_response[:400] + "..."
                        return {
                            "success": True,
                            "voice_response": vp_response,
                            "timestamp": datetime.now().isoformat()
                        }

                # Process with Jarvis for complex commands
                if self.jarvis:
                    success, response = self.jarvis.process(command)
                    if len(response) > 400:
                        response = response[:400] + "..."
                    return {
                        "success": success,
                        "voice_response": response,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    # Fallback to AI Router if Jarvis is not available
                    response = self.ai_router.query(command)
                    return {
                        "success": True,
                        "voice_response": response,
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.error(f"[APIServer] Error processing direct command: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    # ============================================================
    # PLUGIN MARKETPLACE API
    # ============================================================

    def _register_marketplace_routes(self):
        """Register plugin marketplace API endpoints."""

        @self.app.get("/marketplace", response_class=JSONResponse)
        async def marketplace_list(
            category: Optional[str] = Query(None, description="Filter by category"),
            search: Optional[str] = Query(None, description="Search plugins"),
        ):
            """List available plugins in the marketplace."""
            try:
                from modules.plugin_marketplace import get_marketplace
                marketplace = get_marketplace()
                plugins = marketplace.list_available(category=category, search=search)
                return {
                    "success": True,
                    "plugins": plugins,
                    "stats": marketplace.get_stats(),
                }
            except Exception as e:
                logger.error(f"[APIServer] Marketplace list error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/marketplace/install", response_class=JSONResponse)
        async def marketplace_install(body: Dict = Body(...)):
            """Install a plugin from the marketplace."""
            name = body.get("name", "")
            if not name:
                raise HTTPException(status_code=400, detail="Plugin name required")
            try:
                from modules.plugin_marketplace import get_marketplace
                marketplace = get_marketplace()
                result = marketplace.install(name)
                return result
            except Exception as e:
                logger.error(f"[APIServer] Marketplace install error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/marketplace/{name}", response_class=JSONResponse)
        async def marketplace_uninstall(name: str):
            """Uninstall a plugin."""
            try:
                from modules.plugin_marketplace import get_marketplace
                marketplace = get_marketplace()
                result = marketplace.uninstall(name)
                return result
            except Exception as e:
                logger.error(f"[APIServer] Marketplace uninstall error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/marketplace/categories", response_class=JSONResponse)
        async def marketplace_categories():
            """Get available plugin categories."""
            try:
                from modules.plugin_marketplace import get_marketplace
                marketplace = get_marketplace()
                return {"categories": marketplace.get_categories()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/marketplace/updates", response_class=JSONResponse)
        async def marketplace_updates():
            """Check for plugin updates."""
            try:
                from modules.plugin_marketplace import get_marketplace
                marketplace = get_marketplace()
                updates = marketplace.check_updates()
                return {"updates": updates, "count": len(updates)}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/plugins", response_class=JSONResponse)
        async def list_plugins():
            """List installed plugins with status."""
            try:
                from modules.plugin_system import get_plugin_registry
                registry = get_plugin_registry()
                return {"plugins": registry.get_plugin_list()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    # ============================================================
    # WEBSOCKET GATEWAY (OpenClaw-style real-time messaging)
    # ============================================================

    def _register_websocket_gateway(self):
        """Register WebSocket gateway endpoint for real-time bidirectional messaging."""

        @self.app.websocket("/ws")
        async def websocket_gateway(websocket: WebSocket):
            """
            WebSocket gateway - real-time messaging with LADA.

            Protocol (JSON):
              Client -> Server:
                {"type": "chat", "id": "msg-1", "data": {"message": "Hello"}}
                {"type": "chat", "id": "msg-2", "data": {"message": "...", "stream": true}}
                {"type": "agent", "id": "msg-3", "data": {"agent": "...", "action": "...", "params": {}}}
                {"type": "system", "id": "msg-4", "data": {"action": "status"}}
                {"type": "ping"}

              Server -> Client:
                {"type": "chat.response", "id": "msg-1", "data": {"content": "...", "model": "..."}}
                {"type": "chat.chunk", "id": "msg-2", "data": {"chunk": "..."}}
                {"type": "chat.done", "id": "msg-2", "data": {"model": "...", "sources": []}}
                {"type": "agent.response", "id": "msg-3", "data": {"result": {}}}
                {"type": "system.status", "data": {...}}
                {"type": "pong"}
                {"type": "error", "id": "...", "data": {"message": "..."}}
            """
            # Validate session token from query parameter
            token = websocket.query_params.get("token", "")
            if not self._validate_session_token(token):
                await websocket.close(code=4001, reason="Authentication required")
                return

            await websocket.accept()
            session_id = str(uuid.uuid4())[:8]
            self._ws_connections[session_id] = websocket
            self._ws_sessions[session_id] = {
                'connected_at': time.time(),
                'messages_sent': 0,
                'messages_received': 0,
            }
            logger.info(f"[WS] Client connected: {session_id}")

            try:
                # Send welcome
                await websocket.send_json({
                    "type": "system.connected",
                    "data": {
                        "session_id": session_id,
                        "version": "8.0.0",
                        "capabilities": ["chat", "stream", "agent", "system"],
                    }
                })

                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": "Invalid JSON"}
                        })
                        continue

                    msg_type = msg.get("type", "")
                    msg_id = msg.get("id", "")
                    msg_data = msg.get("data", {})
                    self._ws_sessions[session_id]['messages_received'] += 1

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                    elif msg_type == "chat":
                        # Run chat handler as concurrent task so the receive loop
                        # continues processing pings during AI response generation
                        asyncio.create_task(self._ws_handle_chat(websocket, session_id, msg_id, msg_data))

                    elif msg_type == "agent":
                        await self._ws_handle_agent(websocket, msg_id, msg_data)

                    elif msg_type == "system":
                        await self._ws_handle_system(websocket, msg_id, msg_data)

                    elif msg_type == "plan":
                        await self._ws_handle_plan(websocket, msg_id, msg_data)

                    elif msg_type == "workflow":
                        await self._ws_handle_workflow(websocket, msg_id, msg_data)

                    elif msg_type == "task":
                        await self._ws_handle_task(websocket, msg_id, msg_data)

                    else:
                        await websocket.send_json({
                            "type": "error",
                            "id": msg_id,
                            "data": {"message": f"Unknown message type: {msg_type}"}
                        })

            except WebSocketDisconnect:
                logger.info(f"[WS] Client disconnected: {session_id}")
            except Exception as e:
                logger.error(f"[WS] Error for {session_id}: {e}")
            finally:
                self._ws_connections.pop(session_id, None)
                self._ws_sessions.pop(session_id, None)

    async def _ws_handle_chat(self, ws: 'WebSocket', session_id: str, msg_id: str, data: dict):
        """Handle chat messages over WebSocket with real-time streaming via asyncio.Queue bridge."""
        self._load_components()
        message = data.get("message", "")
        stream = data.get("stream", True)
        model = data.get("model")

        if not message:
            await ws.send_json({
                "type": "error", "id": msg_id,
                "data": {"message": "Empty message"}
            })
            return

        if not self.ai_router:
            await ws.send_json({
                "type": "error", "id": msg_id,
                "data": {"message": "AI router not available"}
            })
            return

        try:
            if stream and hasattr(self.ai_router, 'stream_query'):
                # Streaming response via asyncio.Queue bridge
                # Instead of list() which blocks until ALL chunks arrive,
                # we push chunks to a queue as they come and read them async.
                await ws.send_json({
                    "type": "chat.start", "id": msg_id,
                    "data": {"status": "streaming"}
                })

                full_response = ""
                sources = []
                q = asyncio.Queue()
                error_sent = False

                loop = asyncio.get_event_loop()

                def _stream_worker():
                    """Runs in thread pool, pushes chunks to async queue (thread-safe)."""
                    try:
                        for chunk_data in self.ai_router.stream_query(message):
                            asyncio.run_coroutine_threadsafe(q.put(chunk_data), loop)
                    except Exception as e:
                        asyncio.run_coroutine_threadsafe(q.put(e), loop)
                    finally:
                        asyncio.run_coroutine_threadsafe(q.put(None), loop)  # sentinel

                loop.run_in_executor(None, _stream_worker)

                # Read chunks from queue as they arrive (real-time)
                while True:
                    try:
                        chunk_data = await asyncio.wait_for(q.get(), timeout=120)
                    except asyncio.TimeoutError:
                        await ws.send_json({
                            "type": "chat.error", "id": msg_id,
                            "data": {"message": "Response timed out"}
                        })
                        error_sent = True
                        break

                    if chunk_data is None:
                        break  # stream finished

                    if isinstance(chunk_data, Exception):
                        await ws.send_json({
                            "type": "chat.error", "id": msg_id,
                            "data": {"message": str(chunk_data)}
                        })
                        error_sent = True
                        break

                    if isinstance(chunk_data, dict):
                        if 'sources' in chunk_data:
                            sources = chunk_data['sources']
                            await ws.send_json({
                                "type": "chat.sources", "id": msg_id,
                                "data": {"sources": sources}
                            })
                        elif chunk_data.get('chunk'):
                            full_response += chunk_data['chunk']
                            await ws.send_json({
                                "type": "chat.chunk", "id": msg_id,
                                "data": {"chunk": chunk_data['chunk']}
                            })
                        if chunk_data.get('done'):
                            break

                if not error_sent:
                    await ws.send_json({
                        "type": "chat.done", "id": msg_id,
                        "data": {
                            "content": full_response,
                            "model": getattr(self.ai_router, 'current_backend_name', 'unknown'),
                            "sources": sources,
                        }
                    })
            else:
                # Non-streaming response
                def _query_sync():
                    return self.ai_router.query(message)

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, _query_sync)

                await ws.send_json({
                    "type": "chat.response", "id": msg_id,
                    "data": {
                        "content": response,
                        "model": getattr(self.ai_router, 'current_backend_name', 'unknown'),
                    }
                })

            self._ws_sessions[session_id]['messages_sent'] += 1

        except Exception as e:
            logger.error(f"[WS] Chat handler error for {session_id}: {e}")
            try:
                await ws.send_json({
                    "type": "chat.error", "id": msg_id,
                    "data": {"message": f"Internal error: {str(e)}"}
                })
            except Exception:
                pass  # WS might already be closed

    async def _ws_handle_agent(self, ws: 'WebSocket', msg_id: str, data: dict):
        """Handle agent actions over WebSocket."""
        self._load_components()
        agent_name = data.get("agent", "").lower()
        action = data.get("action", "").lower()
        params = data.get("params", {})

        if agent_name not in self.agents:
            await ws.send_json({
                "type": "error", "id": msg_id,
                "data": {"message": f"Agent '{agent_name}' not found"}
            })
            return

        agent = self.agents[agent_name]
        try:
            if hasattr(agent, action):
                method = getattr(agent, action)
                result = method(**params)
            elif hasattr(agent, 'process'):
                result = agent.process(params.get('query', action))
            else:
                await ws.send_json({
                    "type": "error", "id": msg_id,
                    "data": {"message": f"Action '{action}' not supported"}
                })
                return

            await ws.send_json({
                "type": "agent.response", "id": msg_id,
                "data": {"agent": agent_name, "action": action, "result": result}
            })
        except Exception as e:
            await ws.send_json({
                "type": "error", "id": msg_id,
                "data": {"message": str(e)}
            })

    async def _ws_handle_system(self, ws: 'WebSocket', msg_id: str, data: dict):
        """Handle system commands over WebSocket."""
        action = data.get("action", "")

        if action == "status":
            self._load_components()
            status = {}
            if self.ai_router:
                status['backends'] = self.ai_router.get_status()
                if hasattr(self.ai_router, 'get_provider_status'):
                    status['providers'] = self.ai_router.get_provider_status()
                if hasattr(self.ai_router, 'get_cost_summary'):
                    status['cost'] = self.ai_router.get_cost_summary()
            status['uptime'] = (datetime.now() - self.start_time).total_seconds()
            status['ws_connections'] = len(self._ws_connections)
            await ws.send_json({
                "type": "system.status", "id": msg_id,
                "data": status
            })

        elif action == "models":
            self._load_components()
            models = []
            if self.ai_router and hasattr(self.ai_router, 'get_all_available_models'):
                try:
                    models = self.ai_router.get_all_available_models() or []
                except Exception as e:
                    logger.warning(f"[WS] get_all_available_models failed: {e}")
            if (not models) and self.ai_router and hasattr(self.ai_router, 'get_provider_dropdown_items'):
                try:
                    models = self.ai_router.get_provider_dropdown_items() or []
                except Exception as e:
                    logger.warning(f"[WS] get_provider_dropdown_items failed: {e}")
            await ws.send_json({
                "type": "system.models", "id": msg_id,
                "data": {"models": models}
            })

        elif action == "clear_history":
            if self.ai_router:
                self.ai_router.clear_history()
            await ws.send_json({
                "type": "system.ack", "id": msg_id,
                "data": {"action": "clear_history", "success": True}
            })

        else:
            await ws.send_json({
                "type": "error", "id": msg_id,
                "data": {"message": f"Unknown system action: {action}"}
            })

    async def _ws_handle_plan(self, ws: 'WebSocket', msg_id: str, data: dict):
        """Handle plan operations over WebSocket."""
        self._load_components()
        action = data.get("action", "")
        planner = getattr(self.jarvis, 'advanced_planner', None) if self.jarvis else None
        if not planner:
            await ws.send_json({"type": "error", "id": msg_id, "data": {"message": "Planner not available"}})
            return

        if action == "create":
            task = data.get("task", "")
            context = data.get("context", "")
            try:
                loop = asyncio.get_event_loop()
                plan = await loop.run_in_executor(None, lambda: planner.create_plan(task, context))
                await ws.send_json({"type": "plan.created", "id": msg_id, "data": plan.to_dict()})
            except Exception as e:
                await ws.send_json({"type": "error", "id": msg_id, "data": {"message": str(e)}})

        elif action == "execute":
            plan_id = data.get("plan_id", "")
            plan = planner.get_plan(plan_id)
            if not plan:
                await ws.send_json({"type": "error", "id": msg_id, "data": {"message": "Plan not found"}})
                return
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: planner.execute_plan(plan))
            await ws.send_json({"type": "plan.done", "id": msg_id, "data": result.to_dict()})

        elif action == "list":
            count = data.get("count", 10)
            plans = planner.get_recent_plans(count)
            await ws.send_json({
                "type": "plan.list", "id": msg_id,
                "data": {"plans": [p.to_dict() for p in plans]}
            })

        elif action == "cancel":
            planner.cancel()
            await ws.send_json({"type": "plan.cancelled", "id": msg_id, "data": {"success": True}})

        else:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": f"Unknown plan action: {action}"}})

    async def _ws_handle_workflow(self, ws: 'WebSocket', msg_id: str, data: dict):
        """Handle workflow operations over WebSocket."""
        self._load_components()
        action = data.get("action", "")
        wf = getattr(self.jarvis, 'workflow_engine', None) if self.jarvis else None
        if not wf:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Workflow engine not available"}})
            return

        if action == "list":
            workflows = wf.list_workflows()
            await ws.send_json({"type": "workflow.list", "id": msg_id,
                                "data": {"workflows": workflows}})

        elif action == "create":
            name = data.get("name", "")
            steps = data.get("steps", [])
            success = wf.register_workflow(name, steps)
            await ws.send_json({"type": "workflow.created", "id": msg_id,
                                "data": {"success": success, "name": name}})

        elif action == "execute":
            name = data.get("name", "")
            context = data.get("context", {})
            try:
                result = await wf.execute_workflow(name, context)
                await ws.send_json({
                    "type": "workflow.done", "id": msg_id,
                    "data": {
                        "success": result.success,
                        "workflow_name": result.workflow_name,
                        "steps_completed": result.steps_completed,
                        "total_steps": result.total_steps,
                        "duration_seconds": result.duration_seconds,
                        "error": result.error,
                    }
                })
            except Exception as e:
                await ws.send_json({"type": "error", "id": msg_id,
                                    "data": {"message": str(e)}})

        else:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": f"Unknown workflow action: {action}"}})

    async def _ws_handle_task(self, ws: 'WebSocket', msg_id: str, data: dict):
        """Handle task operations over WebSocket."""
        self._load_components()
        action = data.get("action", "")
        tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
        if not tc:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": "Task automation not available"}})
            return

        if action == "list":
            active = tc.get_active_tasks()
            await ws.send_json({"type": "task.list", "id": msg_id, "data": active})

        elif action == "create":
            command = data.get("command", "")
            task_def = tc.parse_complex_command(command)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: tc.execute_task(task_def))
            await ws.send_json({"type": "task.created", "id": msg_id, "data": result})

        elif action == "status":
            exec_id = data.get("execution_id", "")
            status = tc.get_task_status(exec_id)
            await ws.send_json({"type": "task.status", "id": msg_id, "data": status})

        elif action == "pause":
            exec_id = data.get("execution_id", "")
            result = tc.pause_task(exec_id)
            await ws.send_json({"type": "task.paused", "id": msg_id, "data": result})

        elif action == "resume":
            exec_id = data.get("execution_id", "")
            result = tc.resume_task(exec_id)
            await ws.send_json({"type": "task.resumed", "id": msg_id, "data": result})

        elif action == "cancel":
            exec_id = data.get("execution_id", "")
            result = tc.cancel_task(exec_id)
            await ws.send_json({"type": "task.cancelled", "id": msg_id, "data": result})

        else:
            await ws.send_json({"type": "error", "id": msg_id,
                                "data": {"message": f"Unknown task action: {action}"}})

    async def _ws_broadcast(self, message: dict, exclude: str = None):
        """Broadcast a message to all connected WebSocket clients."""
        dead = []
        for sid, ws in self._ws_connections.items():
            if sid == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(sid)
        for sid in dead:
            self._ws_connections.pop(sid, None)
            self._ws_sessions.pop(sid, None)

    # ============================================================
    # WEB DASHBOARD
    # ============================================================

    def _register_dashboard(self):
        """Register the web dashboard route."""
        dashboard_dir = Path(__file__).parent.parent / "web"

        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard():
            """Serve the web dashboard."""
            index_file = dashboard_dir / "index.html"
            if index_file.exists():
                return HTMLResponse(content=index_file.read_text(encoding='utf-8'))
            # Fallback minimal page
            return HTMLResponse(content="<h1>LADA Dashboard</h1><p>web/index.html not found</p>")

        # Serve static files if directory exists
        if dashboard_dir.exists():
            try:
                self.app.mount("/static", StaticFiles(directory=str(dashboard_dir)), name="static")
            except Exception as e:
                logger.warning(f"[APIServer] Could not mount static files: {e}")

    def _register_lada_app_routes(self):
        """Register LADA web app route + sessions/cost/providers endpoints."""
        from fastapi.responses import FileResponse, RedirectResponse
        app_dir = Path(__file__).parent.parent / "web"
        sessions_dir = Path(__file__).parent.parent / "data" / "sessions"

        @self.app.get("/app", response_class=HTMLResponse)
        async def serve_app():
            """Serve the LADA web app."""
            app_file = app_dir / "lada_app.html"
            if app_file.exists():
                return HTMLResponse(content=app_file.read_text(encoding='utf-8'))
            return HTMLResponse(content="<h1>LADA App</h1><p>web/lada_app.html not found. Run setup.</p>")

        # ── Sessions ──────────────────────────────────────────────

        @self.app.get("/sessions")
        async def list_sessions():
            """List all named sessions."""
            sessions_dir.mkdir(parents=True, exist_ok=True)
            sessions = sorted(p.stem for p in sessions_dir.glob("*.json"))
            return {"sessions": sessions}

        @self.app.post("/sessions/new")
        async def new_session(body: dict = Body(default={})):
            """Create or switch to a named session."""
            name = (body.get("name") or "").strip()
            if not name:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Session name required")
            sessions_dir.mkdir(parents=True, exist_ok=True)
            session_path = sessions_dir / f"{name}.json"
            existing = session_path.exists()
            if not existing:
                session_path.write_text(
                    json.dumps({"session_name": name, "updated_at": datetime.now().isoformat(), "messages": []},
                               indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )
            return {"session_name": name, "created": not existing}

        @self.app.post("/sessions/switch")
        async def switch_session(body: dict = Body(default={})):
            """Switch to a named session and return its history."""
            name = (body.get("name") or "").strip()
            if not name:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Session name required")
            session_path = sessions_dir / f"{name}.json"
            if session_path.exists():
                data = json.loads(session_path.read_text(encoding='utf-8'))
                return {"session_name": name, "messages": data.get("messages", [])}
            return {"session_name": name, "messages": []}

        @self.app.delete("/sessions/{name}")
        async def delete_session(name: str):
            """Delete a named session."""
            session_path = sessions_dir / f"{name}.json"
            if session_path.exists():
                session_path.unlink()
                return {"deleted": True, "session_name": name}
            return {"deleted": False, "session_name": name}

        @self.app.post("/sessions/save")
        async def save_session(body: dict = Body(default={})):
            """Save/update a named session with new messages."""
            name = (body.get("name") or "").strip()
            messages = body.get("messages", [])
            if not name:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Session name required")
            sessions_dir.mkdir(parents=True, exist_ok=True)
            session_path = sessions_dir / f"{name}.json"
            session_data = {
                "session_name": name,
                "updated_at": datetime.now().isoformat(),
                "messages": messages,
            }
            session_path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False), encoding='utf-8')
            return {"saved": True, "session_name": name, "message_count": len(messages)}

        # ── Cost ──────────────────────────────────────────────────

        @self.app.get("/cost/summary")
        async def cost_summary():
            """Return token usage and cost summary."""
            self._load_components()
            try:
                from modules.token_counter import CostTracker
                ct = CostTracker(persist_path="data/cost_history.json")
                return ct.get_summary()
            except Exception as e:
                return {"error": str(e), "total_requests": 0, "total_tokens": 0, "total_cost_usd": 0}

        # ── Providers ─────────────────────────────────────────────

        @self.app.get("/providers/status")
        async def providers_status():
            """Return provider health status."""
            self._load_components()
            result = []
            pm = getattr(self.ai_router, 'provider_manager', None) if self.ai_router else None
            if pm:
                try:
                    for name, pinfo in pm.providers.items():
                        result.append({
                            "name": name,
                            "type": getattr(pinfo, 'type', str(pinfo)),
                            "healthy": True,
                            "models": getattr(pinfo, 'model_count', 0),
                        })
                except Exception:
                    pass
            # Fallback: report env-key based status
            if not result:
                provider_keys = {
                    "Groq": "GROQ_API_KEY",
                    "Gemini": "GEMINI_API_KEY",
                    "OpenAI": "OPENAI_API_KEY",
                    "Anthropic": "ANTHROPIC_API_KEY",
                    "Mistral": "MISTRAL_API_KEY",
                    "xAI": "XAI_API_KEY",
                    "DeepSeek": "DEEPSEEK_API_KEY",
                    "Together": "TOGETHER_API_KEY",
                    "Fireworks": "FIREWORKS_API_KEY",
                    "Cerebras": "CEREBRAS_API_KEY",
                    "Ollama": "LOCAL_OLLAMA_URL",
                }
                for pname, env_key in provider_keys.items():
                    has_key = bool(os.getenv(env_key))
                    result.append({"name": pname, "healthy": has_key, "models": 0})
            return {"providers": result}

    # ============================================================
    # ORCHESTRATION API (Plans, Workflows, Tasks, Skills)
    # ============================================================

    def _register_orchestration_routes(self):
        """Register plan/workflow/task/skill management endpoints."""

        # ── Plans ──────────────────────────────────────────────

        @self.app.post("/plans")
        async def create_plan(body: dict = Body(default={})):
            """Create an execution plan from a task description."""
            self._load_components()
            task = body.get("task", "").strip()
            context = body.get("context", "")
            if not task:
                raise HTTPException(status_code=400, detail="Task description required")
            planner = getattr(self.jarvis, 'advanced_planner', None) if self.jarvis else None
            if not planner:
                raise HTTPException(status_code=503, detail="Planner not available")
            try:
                loop = asyncio.get_event_loop()
                plan = await loop.run_in_executor(None, lambda: planner.create_plan(task, context))
                return {"success": True, "plan": plan.to_dict()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/plans")
        async def list_plans(count: int = Query(10)):
            """List recent plans."""
            self._load_components()
            planner = getattr(self.jarvis, 'advanced_planner', None) if self.jarvis else None
            if not planner:
                return {"plans": [], "count": 0}
            plans = planner.get_recent_plans(count)
            return {"plans": [p.to_dict() for p in plans], "count": len(plans)}

        @self.app.get("/plans/{plan_id}")
        async def get_plan(plan_id: str):
            """Get plan details with step status."""
            self._load_components()
            planner = getattr(self.jarvis, 'advanced_planner', None) if self.jarvis else None
            if not planner:
                raise HTTPException(status_code=503, detail="Planner not available")
            plan = planner.get_plan(plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")
            return {"success": True, "plan": plan.to_dict()}

        @self.app.post("/plans/{plan_id}/execute")
        async def execute_plan(plan_id: str, background_tasks: BackgroundTasks):
            """Execute a plan asynchronously."""
            self._load_components()
            planner = getattr(self.jarvis, 'advanced_planner', None) if self.jarvis else None
            if not planner:
                raise HTTPException(status_code=503, detail="Planner not available")
            plan = planner.get_plan(plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")

            def run_plan():
                try:
                    planner.execute_plan(plan)
                except Exception as e:
                    logger.error(f"[APIServer] Plan execution error: {e}")

            background_tasks.add_task(run_plan)
            return {"success": True, "plan_id": plan_id, "status": "executing"}

        @self.app.delete("/plans/{plan_id}")
        async def cancel_plan(plan_id: str):
            """Cancel an active plan."""
            self._load_components()
            planner = getattr(self.jarvis, 'advanced_planner', None) if self.jarvis else None
            if not planner:
                raise HTTPException(status_code=503, detail="Planner not available")
            planner.cancel()
            return {"success": True, "plan_id": plan_id, "status": "cancelled"}

        # ── Workflows ─────────────────────────────────────────

        @self.app.get("/workflows")
        async def list_workflows():
            """List registered workflows."""
            self._load_components()
            wf = getattr(self.jarvis, 'workflow_engine', None) if self.jarvis else None
            if not wf:
                return {"workflows": [], "count": 0}
            workflows = wf.list_workflows()
            return {"workflows": workflows, "count": len(workflows)}

        @self.app.post("/workflows")
        async def create_workflow(body: dict = Body(default={})):
            """Register a new workflow from step definitions."""
            self._load_components()
            name = body.get("name", "").strip()
            steps = body.get("steps", [])
            if not name or not steps:
                raise HTTPException(status_code=400, detail="Workflow name and steps required")
            wf = getattr(self.jarvis, 'workflow_engine', None) if self.jarvis else None
            if not wf:
                raise HTTPException(status_code=503, detail="Workflow engine not available")
            success = wf.register_workflow(name, steps)
            return {"success": success, "name": name, "steps": len(steps)}

        @self.app.post("/workflows/{name}/execute")
        async def execute_workflow(name: str, body: dict = Body(default={})):
            """Execute a named workflow."""
            self._load_components()
            wf = getattr(self.jarvis, 'workflow_engine', None) if self.jarvis else None
            if not wf:
                raise HTTPException(status_code=503, detail="Workflow engine not available")
            context = body.get("context", {})
            try:
                result = await wf.execute_workflow(name, context)
                return {
                    "success": result.success,
                    "workflow_name": result.workflow_name,
                    "steps_completed": result.steps_completed,
                    "total_steps": result.total_steps,
                    "duration_seconds": result.duration_seconds,
                    "results": result.results,
                    "error": result.error,
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/workflows/history")
        async def workflow_history(limit: int = Query(10)):
            """Get workflow execution history."""
            self._load_components()
            wf = getattr(self.jarvis, 'workflow_engine', None) if self.jarvis else None
            if not wf:
                return {"history": [], "count": 0}
            history = wf.get_workflow_history(limit)
            return {
                "history": [
                    {"success": r.success, "workflow_name": r.workflow_name,
                     "steps_completed": r.steps_completed, "total_steps": r.total_steps,
                     "duration_seconds": r.duration_seconds, "error": r.error}
                    for r in history
                ],
                "count": len(history),
            }

        # ── Tasks ─────────────────────────────────────────────

        @self.app.get("/tasks")
        async def list_tasks():
            """List active and completed tasks."""
            self._load_components()
            tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
            if not tc:
                return {"active": [], "completed": [], "active_count": 0, "completed_count": 0}
            active = tc.get_active_tasks()
            completed = tc.get_completed_tasks(20)
            return {
                "active": active.get("active_tasks", []),
                "completed": completed.get("completed_tasks", []),
                "active_count": active.get("count", 0),
                "completed_count": completed.get("count", 0),
            }

        @self.app.post("/tasks")
        async def create_task(body: dict = Body(default={})):
            """Create and execute a task from a command string or definition."""
            self._load_components()
            tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
            if not tc:
                raise HTTPException(status_code=503, detail="Task automation not available")
            command = body.get("command", "").strip()
            if command:
                task_def = tc.parse_complex_command(command)
                result = tc.execute_task(task_def)
                return result
            template = body.get("template", "").strip()
            if template:
                return tc.execute_template(template)
            raise HTTPException(status_code=400, detail="Provide 'command' or 'template'")

        @self.app.get("/tasks/{execution_id}")
        async def get_task_status(execution_id: str):
            """Get task execution status."""
            self._load_components()
            tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
            if not tc:
                raise HTTPException(status_code=503, detail="Task automation not available")
            return tc.get_task_status(execution_id)

        @self.app.post("/tasks/{execution_id}/pause")
        async def pause_task(execution_id: str):
            """Pause a running task."""
            self._load_components()
            tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
            if not tc:
                raise HTTPException(status_code=503, detail="Task automation not available")
            return tc.pause_task(execution_id)

        @self.app.post("/tasks/{execution_id}/resume")
        async def resume_task(execution_id: str):
            """Resume a paused task."""
            self._load_components()
            tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
            if not tc:
                raise HTTPException(status_code=503, detail="Task automation not available")
            return tc.resume_task(execution_id)

        @self.app.post("/tasks/{execution_id}/cancel")
        async def cancel_task(execution_id: str):
            """Cancel a task."""
            self._load_components()
            tc = getattr(self.jarvis, 'tasks', None) if self.jarvis else None
            if not tc:
                raise HTTPException(status_code=503, detail="Task automation not available")
            return tc.cancel_task(execution_id)

        # ── Skills ────────────────────────────────────────────

        @self.app.post("/skills/generate")
        async def generate_skill(body: dict = Body(default={})):
            """AI-generate a new skill/plugin from description."""
            self._load_components()
            description = body.get("description", "").strip()
            name = body.get("name")
            if not description:
                raise HTTPException(status_code=400, detail="Skill description required")
            sg = getattr(self.jarvis, 'skill_generator', None) if self.jarvis else None
            if not sg:
                raise HTTPException(status_code=503, detail="Skill generator not available")
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: sg.generate(description, name))
                if result.get("success"):
                    return result
                raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/skills")
        async def list_skills():
            """List generated skills."""
            self._load_components()
            sg = getattr(self.jarvis, 'skill_generator', None) if self.jarvis else None
            if not sg:
                return {"skills": [], "count": 0}
            skills = sg.list_generated()
            return {"skills": skills, "count": len(skills)}

        @self.app.delete("/skills/{name}")
        async def delete_skill(name: str):
            """Delete a generated skill."""
            self._load_components()
            sg = getattr(self.jarvis, 'skill_generator', None) if self.jarvis else None
            if not sg:
                raise HTTPException(status_code=503, detail="Skill generator not available")
            if sg.delete_skill(name):
                return {"success": True, "name": name}
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # ============================================================
    # OPENAI-COMPATIBLE API (/v1 endpoints)
    # ============================================================

    def _verify_api_key(self, authorization: Optional[str]):
        """Verify Bearer token for OpenAI-compatible endpoints."""
        expected = os.getenv("LADA_API_KEY", "")
        if not expected:
            return  # No key configured = no auth required (local dev)
        if not authorization or authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="Invalid API key")

    def _register_openai_compat_routes(self):
        """Register OpenAI-compatible API endpoints."""

        @self.app.get("/v1/models")
        async def openai_list_models(authorization: Optional[str] = Header(None)):
            """List available models in OpenAI format."""
            self._verify_api_key(authorization)
            self._load_components()

            created = int(self.start_time.timestamp())
            models_list = [{
                "id": "auto",
                "object": "model",
                "created": created,
                "owned_by": "lada",
            }]

            pm = getattr(self.ai_router, 'provider_manager', None) if self.ai_router else None

            if pm and getattr(pm, 'model_registry', None):
                for entry in pm.model_registry.list_available_models():
                    # Skip local Ollama models (accessible directly via Ollama)
                    if entry.provider == "ollama-local":
                        continue
                    models_list.append({
                        "id": entry.id,
                        "object": "model",
                        "created": created,
                        "owned_by": entry.provider,
                    })
            elif self.ai_router and hasattr(self.ai_router, 'get_provider_dropdown_items'):
                for item in self.ai_router.get_provider_dropdown_items():
                    if item.get('value') == 'auto':
                        continue
                    models_list.append({
                        "id": item['value'],
                        "object": "model",
                        "created": created,
                        "owned_by": item.get('provider', 'lada'),
                    })

            return {"object": "list", "data": models_list}

        @self.app.post("/v1/chat/completions")
        async def openai_chat_completions(
            request: OpenAIChatRequest,
            authorization: Optional[str] = Header(None)
        ):
            """OpenAI-compatible chat completions (streaming + non-streaming)."""
            self._verify_api_key(authorization)
            self._load_components()

            if not self.ai_router:
                raise HTTPException(status_code=503, detail="AI Router not available")

            model_id = request.model if request.model != "auto" else None
            messages = [{"role": m.role, "content": m.content} for m in request.messages]
            temperature = request.temperature or 0.7
            max_tokens = request.max_tokens or 2048

            # Extract last user message for LADA complexity analysis
            last_user_msg = ""
            for m in reversed(messages):
                if m["role"] == "user":
                    last_user_msg = m["content"]
                    break

            if request.stream:
                return StreamingResponse(
                    self._openai_stream_generator(
                        messages, model_id, last_user_msg, temperature, max_tokens
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    }
                )
            else:
                return await self._openai_complete(
                    messages, model_id, last_user_msg, temperature, max_tokens
                )

    async def _openai_complete(self, messages, model_id, last_user_msg, temperature, max_tokens):
        """Non-streaming OpenAI-format chat completion."""
        pm = getattr(self.ai_router, 'provider_manager', None)
        sys_prompt = getattr(self.ai_router, 'system_prompt', '')

        # Inject LADA system prompt if no system message in request
        if sys_prompt and not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": sys_prompt})

        used_model = "auto"
        response = None

        if pm and model_id:
            # Path 1: Specific model via ProviderManager
            provider = pm.get_provider_for_model(model_id)
            if not provider:
                raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

            if pm._rate_limiter:
                allowed, reason = pm._rate_limiter.check(provider.provider_id)
                if not allowed:
                    raise HTTPException(status_code=429, detail=f"Rate limited: {reason}")

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: provider.complete_with_retry(messages, model_id, temperature, max_tokens)
            )

            if pm._rate_limiter:
                if response.success:
                    pm._rate_limiter.record_success(provider.provider_id)
                else:
                    pm._rate_limiter.record_failure(provider.provider_id)

            if not response.success:
                raise HTTPException(status_code=502, detail=response.error or "Provider error")
            used_model = model_id

        elif pm:
            # Path 2: Auto routing via ProviderManager
            selection = pm.get_best_model(last_user_msg)
            if not selection:
                raise HTTPException(status_code=503, detail="No models available")

            auto_model = selection['model_id']
            provider = pm.get_provider(selection['provider_id'])

            if pm._rate_limiter:
                allowed, reason = pm._rate_limiter.check(provider.provider_id)
                if not allowed:
                    raise HTTPException(status_code=429, detail=f"Rate limited: {reason}")

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: provider.complete_with_retry(messages, auto_model, temperature, max_tokens)
            )

            if pm._rate_limiter:
                if response.success:
                    pm._rate_limiter.record_success(provider.provider_id)
                else:
                    pm._rate_limiter.record_failure(provider.provider_id)

            if not response.success:
                raise HTTPException(status_code=502, detail=response.error or "Provider error")
            used_model = auto_model

        else:
            # Path 3: Legacy fallback via HybridAIRouter
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, lambda: self.ai_router.query(last_user_msg))
            from modules.providers.base_provider import ProviderResponse
            response = ProviderResponse(content=text or "", provider="legacy")
            used_model = getattr(self.ai_router, 'current_backend_name', 'auto')

        completion_id = f"chatcmpl-lada-{uuid.uuid4().hex[:12]}"
        return JSONResponse({
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": used_model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response.content,
                },
                "finish_reason": getattr(response, 'finish_reason', 'stop') or "stop",
            }],
            "usage": {
                "prompt_tokens": getattr(response, 'input_tokens', 0),
                "completion_tokens": getattr(response, 'output_tokens', 0),
                "total_tokens": getattr(response, 'total_tokens', 0),
            },
        })

    async def _openai_stream_generator(self, messages, model_id, last_user_msg, temperature, max_tokens):
        """Streaming SSE generator in OpenAI chat.completion.chunk format."""
        pm = getattr(self.ai_router, 'provider_manager', None)
        sys_prompt = getattr(self.ai_router, 'system_prompt', '')

        # Inject LADA system prompt if no system message in request
        if sys_prompt and not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": sys_prompt})

        completion_id = f"chatcmpl-lada-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        used_model = "auto"
        provider = None

        if pm and model_id:
            provider = pm.get_provider_for_model(model_id)
            used_model = model_id
        elif pm:
            selection = pm.get_best_model(last_user_msg)
            if selection:
                provider = pm.get_provider(selection['provider_id'])
                used_model = selection['model_id']

        if provider:
            # Stream via provider adapter using asyncio.Queue for true token-by-token
            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def _stream_in_thread():
                try:
                    for chunk in provider.stream_complete(messages, used_model, temperature, max_tokens):
                        asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop)
                except Exception as e:
                    logger.error(f"[OpenAI-compat] Stream error: {e}")
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

            loop.run_in_executor(None, _stream_in_thread)

            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                if chunk.text:
                    data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": used_model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": chunk.text},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                if chunk.done:
                    break
        else:
            # Legacy fallback: collect then yield
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                None, lambda: list(self.ai_router.stream_query(last_user_msg))
            )
            for chunk_data in chunks:
                text = chunk_data.get('chunk', '')
                if text:
                    data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": used_model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                if chunk_data.get('done'):
                    break

        # Final chunk with finish_reason
        final = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": used_model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        }
        yield f"data: {json.dumps(final)}\n\n"
        yield "data: [DONE]\n\n"

    def run(self):
        """Run the API server."""
        if not FASTAPI_OK:
            print("❌ FastAPI not installed. Run: pip install fastapi uvicorn")
            return
        
        print(f"🚀 LADA API Server starting on http://{self.host}:{self.port}")
        print(f"📚 API docs available at http://{self.host}:{self.port}/docs")
        
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
    
    async def run_async(self):
        """Run the API server asynchronously."""
        if not FASTAPI_OK:
            return
        
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
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
    
    # Ensure we're in the JarvisAI directory for proper module imports
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    os.chdir(parent_dir)
    sys.path.insert(0, parent_dir)
    
    parser = argparse.ArgumentParser(description="LADA API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    args = parser.parse_args()
    
    print("=" * 50)
    print("   LADA v7.0 API Server")
    print("=" * 50)
    
    if not FASTAPI_OK:
        print("\n❌ FastAPI not installed!")
        print("   Run: pip install fastapi uvicorn")
        sys.exit(1)
    
    run_server(host=args.host, port=args.port)
