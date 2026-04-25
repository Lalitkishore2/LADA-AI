"""
LADA v7.0 - JARVIS-like Command Processor Core
Complete system control with natural language understanding

Features:
- Karen-style voice personality (warm, friendly, supportive)
- Full system control (apps, browser, files, settings)
- Natural language command processing with NLU Engine
- Proactive assistance (battery warnings, time greetings)
- English + Thanglish (Tamil-English) support
- Privacy mode with sensitive data protection
- Memory system for learning user patterns
- Safety controller with undo and confirmations
"""

import os
import re
import subprocess
import webbrowser
import psutil
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import logging

logger = logging.getLogger(__name__)

# ── Service Registry (replaces 52 try/except import blocks) ──
from core.services import build_default_registry
from core.personality import LadaPersonality

_svc = build_default_registry()
_svc.probe_all()

# Backward-compatible _OK flags used by system status v11 and __init__
SYSTEM_OK = _svc.ok('system')
BROWSER_OK = _svc.ok('browser')
FILE_OK = _svc.ok('files')
NLU_OK = _svc.ok('nlu')
SAFETY_OK = _svc.ok('safety')
MEMORY_OK = _svc.ok('memory')
TASK_OK = _svc.ok('task_automation')
AGENT_OK = _svc.ok('agent_actions')
VISION_OK = _svc.ok('screen_vision')
WORKFLOW_OK = _svc.ok('workflow')
ROUTINE_OK = _svc.ok('routine')
ADVANCED_SYSTEM_OK = _svc.ok('advanced_system')
WINDOW_MANAGER_OK = _svc.ok('window_manager')
GUI_AUTOMATOR_OK = _svc.ok('gui_automator')
BROWSER_TAB_OK = _svc.ok('browser_tabs')
MULTI_TAB_OK = _svc.ok('multi_tab')
GMAIL_OK = _svc.ok('gmail')
CALENDAR_OK = _svc.ok('calendar')
TASK_ORCHESTRATOR_OK = _svc.ok('task_orchestrator')
SCREENSHOT_ANALYZER_OK = _svc.ok('screenshot_analyzer')
PATTERN_LEARNER_OK = _svc.ok('pattern_learner')
PROACTIVE_AGENT_OK = _svc.ok('proactive_agent')
FLIGHT_AGENT_OK = _svc.ok('flight_agent')
HOTEL_AGENT_OK = _svc.ok('hotel_agent')
PRODUCT_AGENT_OK = _svc.ok('product_agent')
RESTAURANT_AGENT_OK = _svc.ok('restaurant_agent')
EMAIL_AGENT_OK = _svc.ok('email_agent')
CALENDAR_AGENT_OK = _svc.ok('calendar_agent')
PRODUCTIVITY_OK = _svc.ok('productivity')
COMET_AGENT_OK = _svc.ok('comet')
PAGE_SUMMARIZER_OK = _svc.ok('page_summarizer')
YOUTUBE_SUMMARIZER_OK = _svc.ok('youtube_summarizer')
VECTOR_MEMORY_OK = _svc.ok('vector_memory')
RAG_ENGINE_OK = _svc.ok('rag_engine')
MCP_CLIENT_OK = _svc.ok('mcp_client')
AGENT_COLLAB_OK = _svc.ok('agent_collab')
REALTIME_VOICE_OK = _svc.ok('realtime_voice')
COMPUTER_USE_OK = _svc.ok('computer_use')
DYNAMIC_PROMPTS_OK = _svc.ok('dynamic_prompts')
TOKEN_OPTIMIZER_OK = _svc.ok('token_optimizer')
WEBHOOK_OK = _svc.ok('webhook')
SELF_MOD_OK = _svc.ok('self_modifier')
DESKTOP_CTRL_OK = _svc.ok('desktop_ctrl')
HEARTBEAT_OK = _svc.ok('heartbeat')
CONTEXT_COMPACT_OK = _svc.ok('context_compact')
MODEL_FAILOVER_OK = _svc.ok('model_failover')
PIPELINE_OK = _svc.ok('pipelines')
EVENT_HOOKS_OK = _svc.ok('event_hooks')
SPOTIFY_OK = _svc.ok('spotify')
SMART_HOME_OK = _svc.ok('smart_home')
ADVANCED_PLANNER_OK = _svc.ok('advanced_planner')
SKILL_GEN_OK = _svc.ok('skill_generator')
IMAGE_GEN_OK = _svc.ok('image_gen')
VIDEO_GEN_OK = _svc.ok('video_gen')
CODE_SANDBOX_OK = _svc.ok('code_sandbox')
DOC_READER_OK = _svc.ok('document_reader')
# Backward-compatible class/function references used by __init__
SystemController = _svc.get('system', 'SystemController')
CometBrowserAgent = _svc.get('browser', 'CometBrowserAgent')
FileSystemController = _svc.get('files', 'FileSystemController')
NLUEngine = _svc.get('nlu', 'NLUEngine')
SafetyController = _svc.get('safety', 'SafetyController')
PrivacyLevel = _svc.get('safety', 'PrivacyLevel')
ActionSeverity = _svc.get('safety', 'ActionSeverity')
MemorySystem = _svc.get('memory', 'MemorySystem')
TaskChoreographer = _svc.get('task_automation', 'TaskChoreographer')
AgentActions = _svc.get('agent_actions', 'AgentActions')
ScreenVision = _svc.get('screen_vision', 'ScreenVision')
create_workflow_engine = _svc.get('workflow', 'create_workflow_engine')
create_routine_manager = _svc.get('routine', 'create_routine_manager')
create_advanced_system_controller = _svc.get('advanced_system', 'create_advanced_system_controller')
create_window_manager = _svc.get('window_manager', 'create_window_manager')
create_gui_automator = _svc.get('gui_automator', 'create_gui_automator')
create_browser_tab_controller = _svc.get('browser_tabs', 'create_browser_tab_controller')
create_multi_tab_orchestrator = _svc.get('multi_tab', 'create_multi_tab_orchestrator')
create_gmail_controller = _svc.get('gmail', 'create_gmail_controller')
create_calendar_controller = _svc.get('calendar', 'create_calendar_controller')
get_task_orchestrator = _svc.get('task_orchestrator', 'get_task_orchestrator')
get_screenshot_analyzer = _svc.get('screenshot_analyzer', 'get_screenshot_analyzer')
get_pattern_learner = _svc.get('pattern_learner', 'get_pattern_learner')
get_proactive_agent = _svc.get('proactive_agent', 'get_proactive_agent')
FlightAgent = _svc.get('flight_agent', 'FlightAgent')
HotelAgent = _svc.get('hotel_agent', 'HotelAgent')
ProductAgent = _svc.get('product_agent', 'ProductAgent')
RestaurantAgent = _svc.get('restaurant_agent', 'RestaurantAgent')
EmailAgent = _svc.get('email_agent', 'EmailAgent')
CalendarAgent = _svc.get('calendar_agent', 'CalendarAgent')
ProductivityManager = _svc.get('productivity', 'ProductivityManager')
create_comet_agent = _svc.get('comet', 'create_comet_agent')
QuickActions = _svc.get('comet', 'QuickActions')
get_page_summarizer = _svc.get('page_summarizer', 'get_page_summarizer')
get_youtube_summarizer = _svc.get('youtube_summarizer', 'get_youtube_summarizer')
get_vector_memory = _svc.get('vector_memory', 'get_vector_memory')
get_rag_engine = _svc.get('rag_engine', 'get_rag_engine')
get_mcp_client = _svc.get('mcp_client', 'get_mcp_client')
get_collaboration_hub = _svc.get('agent_collab', 'get_collaboration_hub')
get_realtime_voice = _svc.get('realtime_voice', 'get_realtime_voice')
VoiceConfig = _svc.get('realtime_voice', 'VoiceConfig')
get_computer_use_agent = _svc.get('computer_use', 'get_computer_use_agent')
get_prompt_builder = _svc.get('dynamic_prompts', 'get_prompt_builder')
get_token_optimizer = _svc.get('token_optimizer', 'get_token_optimizer')
get_webhook_manager = _svc.get('webhook', 'get_webhook_manager')
get_self_mod_engine = _svc.get('self_modifier', 'get_self_mod_engine')
get_file_finder = _svc.get('desktop_ctrl', 'get_file_finder')
get_window_controller = _svc.get('desktop_ctrl', 'get_window_controller')
get_smart_browser = _svc.get('desktop_ctrl', 'get_smart_browser')
get_desktop_controller = _svc.get('desktop_ctrl', 'get_desktop_controller')
get_heartbeat_system = _svc.get('heartbeat', 'get_heartbeat_system')
DailyMemoryLog = _svc.get('heartbeat', 'DailyMemoryLog')
ContextCompactor = _svc.get('context_compact', 'ContextCompactor')
ModelFailoverChain = _svc.get('model_failover', 'ModelFailoverChain')
PipelineRunner = _svc.get('pipelines', 'PipelineRunner')
get_runner = _svc.get('pipelines', 'get_runner')
get_hook_manager = _svc.get('event_hooks', 'get_hook_manager')
emit_event = _svc.get('event_hooks', 'emit_event')
emit_command_event = _svc.get('event_hooks', 'emit_command_event')
SpotifyController = _svc.get('spotify', 'SpotifyController')
SmartHomeHub = _svc.get('smart_home', 'SmartHomeHub')
AdvancedPlanner = _svc.get('advanced_planner', 'AdvancedPlanner')
SkillGenerator = _svc.get('skill_generator', 'SkillGenerator')
get_image_generator = _svc.get('image_gen', 'get_image_generator')
get_video_generator = _svc.get('video_gen', 'get_video_generator')
CodeSandbox = _svc.get('code_sandbox', 'CodeSandbox')
DocumentReader = _svc.get('document_reader', 'DocumentReader')
DeepResearchEngine = _svc.get('deep_research', 'DeepResearchEngine')
FocusModeManager = _svc.get('focus_modes', 'FocusModeManager')
ExportManager = _svc.get('export', 'ExportManager')


class JarvisCommandProcessor:
    """
    Complete JARVIS-like command processor
    Handles all types of commands with natural language
    Integrates NLU, Safety, Memory, and all system modules
    """
    
    def __init__(self, ai_router=None, orchestrator=None):
        """Initialize all subsystems. ai_router: optional shared HybridAIRouter instance"""
        self.orchestrator = orchestrator
        # System control
        self.system = SystemController() if SYSTEM_OK else None
        
        # Browser control
        self.browser = CometBrowserAgent() if BROWSER_OK else None
        
        # File operations
        self.files = FileSystemController() if FILE_OK else None
        
        # NLU Engine for intent classification
        self.nlu = NLUEngine() if NLU_OK else None
        
        # Safety controller for confirmations and privacy
        self.safety = SafetyController() if SAFETY_OK else None
        
        # Memory system for learning
        self.memory = MemorySystem() if MEMORY_OK else None
        
        # Task automation
        self.tasks = TaskChoreographer() if TASK_OK else None
        
        # Agent actions (Comet-style full control)
        self.agent = AgentActions() if AGENT_OK else None
        
        # Screen vision (OCR and analysis)
        self.vision = ScreenVision() if VISION_OK else None
        
        # Workflow engine for multi-step automation
        self.workflow_engine = create_workflow_engine(self) if WORKFLOW_OK else None
        
        # Routine manager for scheduled tasks
        self.routine_manager = None
        if ROUTINE_OK and self.workflow_engine:
            self.routine_manager = create_routine_manager(self.workflow_engine, self)
            self.routine_manager.start_scheduler()
            logger.info("[LADA Core] Routine scheduler started")
        
        # ============ v9.0 JARVIS Modules ============
        # Advanced system control (file CRUD, search, organize)
        self.advanced_system = create_advanced_system_controller() if ADVANCED_SYSTEM_OK else None
        if self.advanced_system:
            logger.info("[LADA Core] Advanced System Control loaded")
        
        # Window manager (window control, app launching)
        self.window_manager = create_window_manager() if WINDOW_MANAGER_OK else None
        if self.window_manager:
            logger.info("[LADA Core] Window Manager loaded")
        
        # GUI automator (click, type, find elements, OCR)
        self.gui_automator = create_gui_automator() if GUI_AUTOMATOR_OK else None
        if self.gui_automator:
            logger.info("[LADA Core] GUI Automator loaded")
        
        # ============ v9.0 Week 2 Modules ============
        # Browser tab controller (open/close/switch tabs)
        self.browser_tabs = create_browser_tab_controller() if BROWSER_TAB_OK else None
        if self.browser_tabs:
            logger.info("[LADA Core] Browser Tab Controller loaded")
        
        # Multi-tab orchestrator (workspaces, sessions)
        self.multi_tab = create_multi_tab_orchestrator() if MULTI_TAB_OK else None
        if self.multi_tab:
            logger.info("[LADA Core] Multi-Tab Orchestrator loaded")
        
        # Gmail controller (email automation)
        self.gmail = create_gmail_controller() if GMAIL_OK else None
        if self.gmail and self.gmail.is_authenticated():
            logger.info("[LADA Core] Gmail Controller loaded")
        
        # Calendar controller (event management)
        self.calendar = create_calendar_controller() if CALENDAR_OK else None
        if self.calendar and self.calendar.is_authenticated():
            logger.info("[LADA Core] Calendar Controller loaded")
        
        # ============ v9.0 Week 3 Modules ============
        # Task Orchestrator (parallel execution, dependencies)
        self.task_orchestrator = get_task_orchestrator() if TASK_ORCHESTRATOR_OK else None
        if self.task_orchestrator:
            logger.info("[LADA Core] Task Orchestrator loaded")
        
        # Screenshot Analyzer (OCR, element detection)
        # Note: ai_router is optional, pass None if not available
        self.screenshot_analyzer = get_screenshot_analyzer(None) if SCREENSHOT_ANALYZER_OK else None
        if self.screenshot_analyzer:
            logger.info("[LADA Core] Screenshot Analyzer loaded")
        
        # Pattern Learner (user behavior, habits)
        self.pattern_learner = get_pattern_learner() if PATTERN_LEARNER_OK else None
        if self.pattern_learner:
            logger.info("[LADA Core] Pattern Learner loaded")
        
        # Proactive Agent (anticipate needs, suggestions)
        self.proactive_agent = get_proactive_agent(self, self.pattern_learner) if PROACTIVE_AGENT_OK else None
        if self.proactive_agent:
            logger.info("[LADA Core] Proactive Agent loaded")
        
        # ============ Smart Agents ============
        # Reuse shared AI router if provided, otherwise create one lazily
        self._ai_router = ai_router
        if not self._ai_router:
            try:
                from lada_ai_router import HybridAIRouter
                self._ai_router = HybridAIRouter()
            except Exception as e:
                pass
        
        # Flight agent for automated flight search (requires ai_router)
        self.flight_agent = FlightAgent(self._ai_router) if FLIGHT_AGENT_OK and self._ai_router else None
        if self.flight_agent:
            logger.info("[LADA Core] Flight Agent loaded")
        
        # Hotel agent for hotel search (no required args)
        self.hotel_agent = HotelAgent() if HOTEL_AGENT_OK else None
        if self.hotel_agent:
            logger.info("[LADA Core] Hotel Agent loaded")
        
        # Product agent for shopping (requires ai_router)
        self.product_agent = ProductAgent(self._ai_router) if PRODUCT_AGENT_OK and self._ai_router else None
        if self.product_agent:
            logger.info("[LADA Core] Product Agent loaded")
        
        # Restaurant agent for food/dining (no required args)
        self.restaurant_agent = RestaurantAgent() if RESTAURANT_AGENT_OK else None
        if self.restaurant_agent:
            logger.info("[LADA Core] Restaurant Agent loaded")
        
        # Email agent for email automation (credentials path)
        self.email_agent = EmailAgent() if EMAIL_AGENT_OK else None
        if self.email_agent:
            logger.info("[LADA Core] Email Agent loaded")
        
        # Calendar agent for scheduling (credentials path)
        self.calendar_agent = CalendarAgent() if CALENDAR_AGENT_OK else None
        if self.calendar_agent:
            logger.info("[LADA Core] Calendar Agent loaded")
        
        # ============ v9.0 Ultimate Features ============
        # Productivity Manager (alarms, reminders, timers, focus mode, backup)
        self.productivity = ProductivityManager() if PRODUCTIVITY_OK else None
        if self.productivity:
            self.productivity.start_all_monitoring()
            logger.info("[LADA Core] Productivity Manager loaded (alarms, reminders, timers, focus mode)")
        
        # Comet Agent (autonomous See → Think → Act control)
        self.comet_agent = create_comet_agent(self._ai_router) if COMET_AGENT_OK else None
        if self.comet_agent:
            self.quick_actions = QuickActions(self.comet_agent)
            # Log comet sub-component status for diagnostics
            try:
                from modules import comet_agent as _ca
                caps = []
                if getattr(_ca, 'BROWSER_OK', False): caps.append('browser')
                if getattr(_ca, 'GUI_OK', False): caps.append('gui')
                if getattr(_ca, 'SCREEN_VISION_OK', False): caps.append('vision')
                if getattr(_ca, 'SCREENSHOT_OK', False): caps.append('screenshot')
                if getattr(_ca, 'PYAUTOGUI_OK', False): caps.append('pyautogui')
                logger.info(f"[LADA Core] Comet Autonomous Agent loaded (capabilities: {', '.join(caps) or 'none'})")
            except Exception:
                logger.info("[LADA Core] Comet Autonomous Agent loaded")
        else:
            self.quick_actions = None

        # Comet-style browser intelligence
        self.page_summarizer = get_page_summarizer(self._ai_router) if PAGE_SUMMARIZER_OK else None
        if self.page_summarizer:
            logger.info("[LADA Core] Page Summarizer loaded")

        self.youtube_summarizer = get_youtube_summarizer(self._ai_router) if YOUTUBE_SUMMARIZER_OK else None
        if self.youtube_summarizer:
            logger.info("[LADA Core] YouTube Summarizer loaded")

        # ============ v11.0 - Gap Analysis Modules ============
        # Vector Memory (ChromaDB semantic search)
        self.vector_memory = get_vector_memory() if VECTOR_MEMORY_OK else None
        if self.vector_memory:
            logger.info("[LADA Core] Vector Memory System loaded")

        # RAG Engine (document retrieval augmented generation)
        self.rag_engine = get_rag_engine() if RAG_ENGINE_OK else None
        if self.rag_engine:
            logger.info("[LADA Core] RAG Engine loaded")

        # MCP Client (Model Context Protocol)
        self.mcp_client = get_mcp_client() if MCP_CLIENT_OK else None
        if self.mcp_client:
            mcp_status = self.mcp_client.initialize()
            logger.info(f"[LADA Core] MCP Client loaded: {mcp_status.get('total_tools', 0)} tools")

        # Multi-Agent Collaboration Hub
        self.collab_hub = get_collaboration_hub() if AGENT_COLLAB_OK else None
        if self.collab_hub:
            # Register existing agents with the collaboration hub
            if self.flight_agent:
                self.collab_hub.register_agent("flight_agent", ["flights", "travel", "booking"])
            if self.hotel_agent:
                self.collab_hub.register_agent("hotel_agent", ["hotels", "accommodation", "booking"])
            if self.product_agent:
                self.collab_hub.register_agent("product_agent", ["shopping", "products", "price"])
            if self.restaurant_agent:
                self.collab_hub.register_agent("restaurant_agent", ["restaurants", "food", "dining"])
            if self.email_agent:
                self.collab_hub.register_agent("email_agent", ["email", "gmail", "messages"])
            if self.calendar_agent:
                self.collab_hub.register_agent("calendar_agent", ["calendar", "schedule", "events"])
            if self.comet_agent:
                self.collab_hub.register_agent("comet_agent", ["browser", "web", "automation"])
            self.collab_hub.register_agent("orchestrator", ["planning", "delegation", "coordination"])
            logger.info(f"[LADA Core] Agent Collaboration Hub loaded: {len(self.collab_hub.list_agents())} agents")

        # Real-Time Voice Engine (LiveKit + Barge-In)
        self.realtime_voice = get_realtime_voice() if REALTIME_VOICE_OK else None
        if self.realtime_voice:
            logger.info(f"[LADA Core] Real-Time Voice loaded (engine: {self.realtime_voice.engine_type})")

        # LLM-Driven Computer Use Agent
        self.computer_use = get_computer_use_agent(self._ai_router) if COMPUTER_USE_OK else None
        if self.computer_use:
            logger.info("[LADA Core] Computer Use Agent loaded")

        # Dynamic Runtime Prompts
        self.prompt_builder = get_prompt_builder() if DYNAMIC_PROMPTS_OK else None
        if self.prompt_builder:
            logger.info("[LADA Core] Dynamic Prompt Builder loaded")

        # Token Optimizer
        self.token_optimizer = get_token_optimizer() if TOKEN_OPTIMIZER_OK else None
        if self.token_optimizer:
            logger.info("[LADA Core] Token Optimizer loaded")

        # Webhook Manager
        self.webhook_manager = get_webhook_manager() if WEBHOOK_OK else None
        if self.webhook_manager:
            # Auto-start webhook server if enabled
            if os.getenv('ENABLE_WEBHOOKS', 'false').lower() == 'true':
                self.webhook_manager.start_server()
            logger.info("[LADA Core] Webhook Manager loaded")

        # Self-Modifying Code Engine
        self.self_modifier = get_self_mod_engine() if SELF_MOD_OK else None
        if self.self_modifier:
            logger.info("[LADA Core] Self-Modifying Engine loaded")

        # ============ v12.0 - Desktop Control Suite ============
        self.file_finder = get_file_finder() if DESKTOP_CTRL_OK else None
        self.win_ctrl = get_window_controller() if DESKTOP_CTRL_OK else None
        self.smart_browser = get_smart_browser() if DESKTOP_CTRL_OK else None
        self.desktop_ctrl = get_desktop_controller() if DESKTOP_CTRL_OK else None
        if DESKTOP_CTRL_OK:
            logger.info("[LADA Core] Desktop Control Suite loaded (file finder, window ctrl, smart browser)")

        # ============ v11.0 - OpenClaw-Inspired Modules ============

        # Heartbeat System - proactive periodic check-ins
        self.heartbeat = get_heartbeat_system() if HEARTBEAT_OK else None
        if self.heartbeat:
            if self._ai_router:
                self.heartbeat.set_ai_router(self._ai_router)
            logger.info("[LADA Core] Heartbeat System loaded")

        # Daily Memory Log
        self.daily_memory = DailyMemoryLog() if HEARTBEAT_OK and DailyMemoryLog else None
        if self.daily_memory:
            logger.info("[LADA Core] Daily Memory Log loaded")

        # Context Compaction
        self.context_compactor = ContextCompactor() if CONTEXT_COMPACT_OK else None
        if self.context_compactor:
            logger.info("[LADA Core] Context Compaction loaded")

        # Model Failover Chain
        self.failover_chain = ModelFailoverChain() if MODEL_FAILOVER_OK else None
        if self.failover_chain:
            logger.info("[LADA Core] Model Failover Chain loaded")

        # Workflow Pipeline Runner
        self.pipeline_runner = get_runner() if PIPELINE_OK else None
        if self.pipeline_runner:
            logger.info("[LADA Core] Workflow Pipeline Runner loaded")

        # Event Hooks
        self.hook_manager = get_hook_manager() if EVENT_HOOKS_OK else None
        if self.hook_manager:
            logger.info("[LADA Core] Event Hooks loaded")

        # Spotify Controller
        self.spotify = SpotifyController() if SPOTIFY_OK else None
        if self.spotify:
            logger.info("[LADA Core] Spotify Controller loaded")

        # Smart Home Hub
        self.smart_home = SmartHomeHub() if SMART_HOME_OK else None
        if self.smart_home:
            logger.info("[LADA Core] Smart Home Hub loaded")

        # ============ Orchestration: AdvancedPlanner + SkillGenerator ============
        # Advanced Planner (AI-powered multi-step task decomposition)
        self.advanced_planner = None
        if ADVANCED_PLANNER_OK:
            try:
                self.advanced_planner = AdvancedPlanner(
                    ai_router=self._ai_router,
                    executor=self._execute_plan_step,
                )
                logger.info("[LADA Core] Advanced Planner loaded")
            except Exception as e:
                logger.error(f"[LADA Core] Advanced Planner init failed: {e}")

        # Skill Generator (AI-powered plugin creation from natural language)
        self.skill_generator = None
        if SKILL_GEN_OK:
            try:
                self.skill_generator = SkillGenerator(ai_router=self._ai_router)
                logger.info("[LADA Core] Skill Generator loaded")
            except Exception as e:
                logger.error(f"[LADA Core] Skill Generator init failed: {e}")

        # ============ Gap-closing: previously dormant modules ============
        # Image Generation (Stability AI + Gemini Imagen)
        self.image_gen = None
        if IMAGE_GEN_OK and get_image_generator:
            try:
                self.image_gen = get_image_generator()
                if self.image_gen and self.image_gen.is_available():
                    logger.info("[LADA Core] Image Generation loaded")
                else:
                    logger.info("[LADA Core] Image Generation loaded (no API keys configured)")
            except Exception as e:
                logger.error(f"[LADA Core] Image Generation init failed: {e}")

        # Video Generation (Google Veo + Stability AI)
        self.video_gen = None
        if VIDEO_GEN_OK and get_video_generator:
            try:
                self.video_gen = get_video_generator()
                if self.video_gen and self.video_gen.is_available():
                    logger.info("[LADA Core] Video Generation loaded")
                else:
                    logger.info("[LADA Core] Video Generation loaded (no API keys configured)")
            except Exception as e:
                logger.error(f"[LADA Core] Video Generation init failed: {e}")

        # Code Sandbox (RestrictedPython + subprocess isolation)
        self.code_sandbox = None
        if CODE_SANDBOX_OK and CodeSandbox:
            try:
                self.code_sandbox = CodeSandbox(timeout=30)
                logger.info("[LADA Core] Code Sandbox loaded")
            except Exception as e:
                logger.error(f"[LADA Core] Code Sandbox init failed: {e}")

        # Document Reader (PDF, DOCX, TXT)
        self.document_reader = None
        if DOC_READER_OK and DocumentReader:
            try:
                self.document_reader = DocumentReader(ai_router=self._ai_router)
                logger.info("[LADA Core] Document Reader loaded")
            except Exception as e:
                logger.error(f"[LADA Core] Document Reader init failed: {e}")

        # Window management (pygetwindow) - legacy, replaced by window_manager
        try:
            import pygetwindow as gw
            self.window_mgr = gw
            logger.info("[LADA Core] Window management available")
        except ImportError:
            self.window_mgr = None
            logger.warning("[LADA Core] pygetwindow not available")
        
        # Command history for context
        self.command_history: List[str] = []
        self.last_action = None
        self.pending_confirmation = None  # For dangerous commands
        self._last_activity_ts = time.time()
        self._created_at_ts = self._last_activity_ts
        self._session_count = 0
        self._kairos_thread: Optional[threading.Thread] = None
        self._kairos_stop = threading.Event()
        self._kairos_interval_seconds = int(os.getenv("LADA_KAIROS_INTERVAL_SECONDS", "600"))
        self._kairos_idle_seconds = int(os.getenv("LADA_KAIROS_IDLE_SECONDS", str(24 * 60 * 60)))
        self._kairos_min_sessions = int(os.getenv("LADA_KAIROS_MIN_SESSIONS", "5"))
        
        # Privacy mode
        self.privacy_mode = False
        
        # App paths database
        self.apps = {
            # Browsers
            'chrome': ['C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
                      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'],
            'firefox': ['C:\\Program Files\\Mozilla Firefox\\firefox.exe',
                       'C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe'],
            'edge': ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
                    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'],
            
            # Productivity
            'notepad': ['notepad.exe'],
            'calculator': ['calc.exe'],
            'paint': ['mspaint.exe'],
            'explorer': ['explorer.exe'],
            'cmd': ['cmd.exe'],
            'powershell': ['powershell.exe'],
            'terminal': ['wt.exe'],  # Windows Terminal
            
            # Development
            'vscode': ['C:\\Users\\{user}\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
                      'C:\\Program Files\\Microsoft VS Code\\Code.exe'],
            'code': ['C:\\Users\\{user}\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe'],
            
            # Media
            'vlc': ['C:\\Program Files\\VideoLAN\\VLC\\vlc.exe',
                   'C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe'],
            'spotify': ['C:\\Users\\{user}\\AppData\\Roaming\\Spotify\\Spotify.exe'],
            
            # Communication
            'discord': ['C:\\Users\\{user}\\AppData\\Local\\Discord\\Update.exe --processStart Discord.exe'],
            'teams': ['C:\\Users\\{user}\\AppData\\Local\\Microsoft\\Teams\\Update.exe --processStart Teams.exe'],
            'zoom': ['C:\\Users\\{user}\\AppData\\Roaming\\Zoom\\bin\\Zoom.exe'],
            'whatsapp': ['C:\\Users\\{user}\\AppData\\Local\\WhatsApp\\WhatsApp.exe'],
            
            # Office
            'word': ['C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE',
                    'C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\WINWORD.EXE'],
            'excel': ['C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE',
                     'C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\EXCEL.EXE'],
            'powerpoint': ['C:\\Program Files\\Microsoft Office\\root\\Office16\\POWERPNT.EXE'],
            
            # Utilities
            'settings': ['ms-settings:'],
            'control': ['control.exe'],
            'task manager': ['taskmgr.exe'],
            'snipping tool': ['snippingtool.exe'],
        }
        
        # Common websites
        self.websites = {
            'google': 'https://www.google.com',
            'youtube': 'https://www.youtube.com',
            'gmail': 'https://mail.google.com',
            'github': 'https://github.com',
            'stackoverflow': 'https://stackoverflow.com',
            'twitter': 'https://twitter.com',
            'x': 'https://x.com',
            'facebook': 'https://facebook.com',
            'instagram': 'https://instagram.com',
            'linkedin': 'https://linkedin.com',
            'reddit': 'https://reddit.com',
            'amazon': 'https://amazon.com',
            'netflix': 'https://netflix.com',
            'chatgpt': 'https://chat.openai.com',
            'gemini': 'https://gemini.google.com',
            'claude': 'https://claude.ai',
        }

        # Plugin command fallback (SKILL.md + plugin.json handlers)
        self._plugin_commands_enabled = (
            os.getenv("LADA_SKILL_MD_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self._plugin_handlers_ready = False
        self.plugin_registry = None
        if self._plugin_commands_enabled:
            try:
                from modules.plugin_system import get_plugin_registry

                self.plugin_registry = get_plugin_registry()
            except Exception as e:
                logger.warning(f"[LADA Core] Plugin registry unavailable: {e}")
        
        # ── Executors (decomposed command handlers) ──────────
        from core.executors.app_executor import AppExecutor
        from core.executors.system_executor import SystemExecutor
        from core.executors.web_media_executor import WebMediaExecutor
        from core.executors.workflow_executor import WorkflowExecutor
        from core.executors.productivity_executor import ProductivityExecutor
        from core.executors.browser_executor import BrowserExecutor
        from core.executors.desktop_executor import DesktopExecutor
        from core.executors.agent_executor import AgentExecutor
        self.executors = [
            WorkflowExecutor(self),
            ProductivityExecutor(self),
            BrowserExecutor(self),
            DesktopExecutor(self),
            SystemExecutor(self),
            AppExecutor(self),
            WebMediaExecutor(self),
            AgentExecutor(self),
        ]

        logger.info(f"[LADA Core] System: {SYSTEM_OK}, Browser: {BROWSER_OK}, Files: {FILE_OK}, NLU: {NLU_OK}, Safety: {SAFETY_OK}, Memory: {MEMORY_OK}, Workflow: {WORKFLOW_OK}, Routine: {ROUTINE_OK}")
        self._start_kairos_loop()
    
    # ============ Privacy & Safety Methods ============
    
    def set_privacy_mode(self, enabled: bool) -> str:
        """Toggle privacy mode on/off"""
        self.privacy_mode = enabled
        if self.safety and PrivacyLevel:
            mode = PrivacyLevel.PRIVATE if enabled else PrivacyLevel.PUBLIC
            self.safety.set_privacy_mode(mode)
        status = "enabled" if enabled else "disabled"
        return f"Privacy mode {status}. {'Commands will not be logged.' if enabled else 'Normal logging resumed.'}"
    
    def get_privacy_status(self) -> Dict[str, Any]:
        """Get current privacy and safety status"""
        return {
            'privacy_mode': self.privacy_mode,
            'safety_available': SAFETY_OK,
            'memory_available': MEMORY_OK,
            'nlu_available': NLU_OK,
        }
    
    def request_confirmation(self, action: str, details: str) -> Tuple[bool, str]:
        """Store a pending confirmation for dangerous action"""
        self.pending_confirmation = {
            'action': action,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        return True, f"⚠️ This will {action}. {details}\n\nSay 'yes' or 'confirm' to proceed, or 'no' to cancel."
    
    def handle_confirmation(self, response: str) -> Tuple[bool, str]:
        """Handle yes/no response to pending confirmation"""
        if not self.pending_confirmation:
            return False, ""
        
        response = response.lower().strip()
        if response in ['yes', 'confirm', 'do it', 'proceed', 'okay', 'ok']:
            action = self.pending_confirmation['action']
            self.pending_confirmation = None
            return True, f"confirmed:{action}"  # Special return to trigger action
        elif response in ['no', 'cancel', 'stop', 'abort', 'never mind']:
            self.pending_confirmation = None
            return True, "Cancelled. No changes made."
        
        return False, ""
    
    def remember_command(self, command: str, response: str):
        """Learn from successful command execution"""
        if self.memory and not self.privacy_mode:
            self.memory.remember('command', command)
            # Learn response if it was helpful
            if len(response) > 10:
                self.memory.learn_response(command, response)
        
        # Keep local history for context
        self.command_history.append(command)
        if len(self.command_history) > 20:
            self.command_history = self.command_history[-20:]
        
        # Record for pattern learning (v9.0)
        if self.pattern_learner and not self.privacy_mode:
            self.pattern_learner.record_command(command, success=True)
    
    def get_learned_response(self, query: str) -> Optional[str]:
        """Check if we have a learned response for this query"""
        if self.memory:
            return self.memory.get_learned(query)
        return None
    
    # ============ File Operations ============
    
    def search_files(self, query: str, location: str = None) -> Tuple[bool, str]:
        """Search for files by name"""
        if not self.files:
            return True, "File search is not available."
        
        search_path = location or str(Path.home())
        try:
            results = self.files.search_files(
                name=query,
                search_folder=search_path,
                recursive=True
            )
            if results.get('files'):
                files = results['files'][:10]
                file_list = '\n'.join([f"  • {f.get('name', 'Unknown')} ({f.get('path', '')})" for f in files])
                return True, f"Found {len(files)} files:\n{file_list}"
            return True, f"No files found matching '{query}'."
        except Exception as e:
            return True, f"Search error: {e}"
    
    def create_file(self, filename: str, content: str = "") -> Tuple[bool, str]:
        """Create a new file"""
        if not self.files:
            return True, "File operations not available."
        
        # Default to Desktop
        desktop = Path.home() / 'Desktop' / filename
        try:
            result = self.files.create_file(str(desktop), content)
            if result.get('success'):
                return True, f"Created {filename} on your Desktop."
            return True, f"Could not create file: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Error creating file: {e}"
    
    def delete_file(self, filepath: str, permanent: bool = False) -> Tuple[bool, str]:
        """Delete a file (with safety check)"""
        if not self.files:
            return True, "File operations not available."
        
        # Safety check for dangerous paths
        dangerous_paths = ['windows', 'system32', 'program files', 'appdata']
        if any(dp in filepath.lower() for dp in dangerous_paths):
            return self.request_confirmation(
                'delete a system-related file',
                f"File: {filepath}\n\nThis could affect system stability."
            )
        
        try:
            result = self.files.delete_file(filepath, permanent=permanent)
            if result.get('success'):
                return True, f"Deleted {Path(filepath).name}."
            return True, f"Could not delete: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Error: {e}"
    
    # ============ NLU Processing ============
    
    def _confirm_dangerous_action(self, title: str, message: str) -> bool:
        """
        Callback for permission system to request user confirmation.
        Returns True if user confirms, False otherwise.
        """
        # If we have a GUI, use it
        if hasattr(self, 'gui') and self.gui:
            try:
                return self.gui.confirm_dialog(title, message)
            except Exception as e:
                pass
        
        # For voice/CLI mode, we set pending_confirmation and wait
        # The user must say "confirm" or "yes" to proceed
        self.pending_confirmation = {
            'title': title,
            'message': message,
            'timestamp': datetime.datetime.now().isoformat()
        }
        logger.info(f"[LADA] Confirmation requested: {title}")
        
        # For now, default to allowing (user can configure stricter mode)
        # In strict mode, this would return False and require explicit confirmation
        return True
    
    def _execute_comet_task(self, task: str) -> Tuple[bool, str]:
        """Actually execute a task through CometAgent's See-Think-Act loop."""
        if not self.comet_agent:
            return False, "Autonomous agent not available."

        logger.info(f"[LADA Core] CometAgent executing: {task}")
        try:
            result = self.comet_agent.execute_task_sync(task, max_steps=30)
            if result.success:
                return True, f"Task completed: {result.message}"
            else:
                return True, f"Task did not fully complete: {result.message}"
        except Exception as e:
            logger.error(f"[LADA Core] CometAgent error: {e}")
            return True, f"Autonomous task failed: {str(e)}"

    def _is_autonomous_task(self, cmd: str) -> bool:
        """Detect if a command requires multi-step autonomous execution.

        Returns True for commands that need the See-Think-Act agent
        rather than simple one-shot system commands.
        """
        # Multi-step indicators (contains sequencing words)
        has_sequence = any(x in cmd for x in [
            ' and then ', ' then ', ' after that ', ' next ',
            ', and ', ' followed by ',
        ])

        # "go to X and Y" is also multi-step (even without "then")
        if 'go to ' in cmd and ' and ' in cmd:
            has_sequence = True
        if 'navigate to ' in cmd and ' and ' in cmd:
            has_sequence = True

        # Action verbs that ALWAYS need the agent (inherently complex)
        always_autonomous = [
            'fill in', 'fill out', 'fill the form',
            'log in', 'login', 'sign in', 'sign up',
            'add to cart', 'checkout', 'buy ', 'purchase',
            'download from', 'upload to',
            'book a ', 'order from', 'order a ',
            'compose email', 'write email', 'send email to',
            'post on', 'tweet', 'share on',
        ]
        if any(x in cmd for x in always_autonomous):
            return True

        # Action verbs that need website/multi-step context
        action_verbs = [
            'go to ', 'navigate to ', 'open website ',
        ]
        has_complex_action = any(x in cmd for x in action_verbs)

        # Multi-step: action verb + website/URL mention
        has_website = any(x in cmd for x in [
            '.com', '.org', '.net', '.io', '.ai',
            'amazon', 'google', 'youtube', 'gmail', 'twitter',
            'facebook', 'instagram', 'linkedin', 'github',
            'flipkart', 'swiggy', 'zomato', 'uber',
        ])

        # Combined: click/type + website = autonomous
        has_gui_action = any(x in cmd for x in [
            'click ', 'click on ', 'type in ', 'type into ',
            'scroll to ', 'drag ', 'select ',
        ])

        # "search for X on google/in browser" = needs agent
        if 'search' in cmd and any(x in cmd for x in ['on google', 'in browser', 'on the browser', 'in chrome', 'on youtube']):
            return True

        # Sequenced commands always need agent
        if has_sequence and (has_website or has_gui_action or has_complex_action):
            return True

        # Complex actions with website targets need agent
        if has_complex_action and has_website:
            return True

        # GUI actions on websites need agent
        if has_gui_action and has_website:
            return True

        return False

    # ── Orchestration bridge methods ──

    def _execute_plan_step(self, action_type: str, target: str, value: str, parameters: dict = None) -> str:
        """Execute a single plan step via existing JARVIS capabilities.

        Called by AdvancedPlanner.execute_plan() for each step.
        Maps planner action types to the command processor's subsystems.
        """
        parameters = parameters or {}
        try:
            if action_type == 'ai_query':
                if self._ai_router:
                    return str(self._ai_router.query(target or value))
                return "AI router unavailable"
            elif action_type == 'search':
                if hasattr(self, 'web_search') and self.web_search:
                    return str(self.web_search.search(target or value))
                return "Web search unavailable"
            elif action_type == 'navigate':
                if self.browser:
                    webbrowser.open(target)
                    return f"Opened {target}"
                return "Browser unavailable"
            elif action_type == 'system':
                if self.system:
                    handled, resp = self.process(value or target)
                    return resp
                return "System control unavailable"
            elif action_type in ('click', 'type', 'screenshot'):
                if self.comet_agent:
                    return str(self.comet_agent.execute_action(action_type, target, value))
                return "Comet agent unavailable"
            else:
                # Fallback: try processing as a regular command
                handled, resp = self.process(value or target or action_type)
                if handled:
                    return resp
                return f"Completed: {action_type} on {target}"
        except Exception as e:
            return f"Error executing {action_type}: {e}"

    def _is_complex_command(self, text: str) -> bool:
        """Detect multi-step commands that benefit from planning."""
        indicators = [
            ' and then ', ' after that ', ' followed by ',
            ' step by step', ' first ', ' next ',
            'plan ', 'workflow ', 'automate ',
            'create a project', 'set up ', 'build a ',
        ]
        return any(ind in text.lower() for ind in indicators)

    def process_with_nlu(self, command: str) -> Dict[str, Any]:
        """Process command through NLU engine for intent classification"""
        if not self.nlu:
            return {'intent': 'unknown', 'confidence': 0, 'entities': {}}
        
        try:
            result = self.nlu.process(command, {'history': self.command_history})
            return result
        except Exception as e:
            logger.warning(f"NLU processing error: {e}")
            return {'intent': 'unknown', 'confidence': 0, 'entities': {}}
    
    def process(self, command: str) -> Tuple[bool, str]:
        """
        Process a command and return (handled, response)
        
        Args:
            command: User's natural language command
            
        Returns:
            (handled: bool, response: str)
            - handled: True if command was executed locally
            - response: Result message to display/speak
        """
        if not command:
            return False, ""

        raw_command = command.strip()
        if not raw_command:
            return False, ""

        self._record_activity()

        cmd = raw_command.lower()
        
        # === CHECK FOR PENDING CONFIRMATION ===
        if self.pending_confirmation:
            handled, response = self.handle_confirmation(cmd)
            if handled:
                if response.startswith('confirmed:'):
                    # Execute the confirmed action
                    action = response.replace('confirmed:', '')
                    return self._execute_confirmed_action(action)
                return True, response
        
        # === PRIVACY MODE COMMANDS ===
        if any(x in cmd for x in ['enable privacy', 'privacy mode on', 'turn on privacy', 'private mode']):
            return True, self.set_privacy_mode(True)
        
        if any(x in cmd for x in ['disable privacy', 'privacy mode off', 'turn off privacy', 'public mode']):
            return True, self.set_privacy_mode(False)
        
        if any(x in cmd for x in ['privacy status', 'am i in privacy']):
            status = "enabled" if self.privacy_mode else "disabled"
            return True, f"Privacy mode is currently {status}."

        # === EXECUTOR DISPATCH (handles all domain commands) ===
        for executor in self.executors:
            handled, response = executor.try_handle(cmd)
            if handled:
                return True, response

        # --- Small inline handlers (too small for executors) ---

        # === UNDO COMMAND ===
        if cmd in ['undo', 'undo that', 'undo last action', 'revert']:
            return self._handle_undo()

        # === FILE SEARCH ===
        if any(x in cmd for x in ['find file', 'search file', 'look for file', 'find files', 'search for file']):
            match = re.search(r'(?:find|search|look for)\s+(?:files?\s+)?(?:named?\s+)?(.+)', cmd)
            if match:
                query = match.group(1).strip()
                return self.search_files(query)
            return True, "What file would you like me to search for?"

        # === CREATE FILE ===
        if any(x in cmd for x in ['create file', 'make file', 'new file', 'create a file']):
            match = re.search(r'(?:named?|called?)\s+([^\s]+)', cmd)
            if match:
                filename = match.group(1)
                return self.create_file(filename)
            return True, "What would you like to name the file?"

        # === DELETE FILE (with confirmation) ===
        if any(x in cmd for x in ['delete file', 'remove file', 'delete the file']):
            match = re.search(r'(?:delete|remove)\s+(?:the\s+)?file\s+(.+)', cmd)
            if match:
                filepath = match.group(1).strip()
                return self.request_confirmation(
                    f"delete the file '{filepath}'",
                    "This action cannot be undone if deleted permanently."
                )
            return True, "Which file would you like to delete?"

        # === NAVIGATE DIRECTORIES ===
        if any(x in cmd for x in ['go to ', 'open folder', 'navigate to', 'show me ']):
            return self._handle_navigation(cmd)

        # === TIME & DATE ===
        if any(x in cmd for x in ['what time', 'current time', 'tell me the time', 'what is the time']):
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            return True, f"It's {time_str}."

        if any(x in cmd for x in ['what date', "today's date", 'what is the date', 'what day']):
            now = datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            return True, f"Today is {date_str}."

        # === GREETINGS ===
        if any(x in cmd for x in ['hello', 'hi lada', 'hey lada', 'good morning', 'good evening', 'good night']):
            return True, LadaPersonality.get_time_greeting()

        if cmd in ['thanks', 'thank you', 'thanks lada']:
            return True, "You're welcome! I'm here if you need anything else."

        # === FILE OPERATIONS (secondary handler) ===
        if self.files:
            if any(x in cmd for x in ['create file', 'make file', 'new file']):
                return self._handle_file_create(cmd)

            if any(x in cmd for x in ['delete file', 'remove file']):
                return self._handle_file_delete(cmd)

        # === SYSTEM STATUS (v11.0 enhanced) ===
        if any(x in cmd for x in ['system status v11', 'v11 status', 'full system status', 'all modules status']):
            status_lines = ["LADA v11.0 System Status:"]
            modules = [
                ("Vector Memory", VECTOR_MEMORY_OK, self.vector_memory),
                ("RAG Engine", RAG_ENGINE_OK, self.rag_engine),
                ("MCP Client", MCP_CLIENT_OK, self.mcp_client),
                ("Agent Collaboration", AGENT_COLLAB_OK, self.collab_hub),
                ("Real-Time Voice", REALTIME_VOICE_OK, self.realtime_voice),
                ("Computer Use Agent", COMPUTER_USE_OK, self.computer_use),
                ("Dynamic Prompts", DYNAMIC_PROMPTS_OK, self.prompt_builder),
                ("Token Optimizer", TOKEN_OPTIMIZER_OK, self.token_optimizer),
                ("Webhook Manager", WEBHOOK_OK, self.webhook_manager),
                ("Self-Modifier", SELF_MOD_OK, self.self_modifier),
                ("Page Summarizer", PAGE_SUMMARIZER_OK, self.page_summarizer),
                ("YouTube Summarizer", YOUTUBE_SUMMARIZER_OK, self.youtube_summarizer),
                ("Comet Agent", COMET_AGENT_OK, self.comet_agent),
            ]
            for name, importable, instance in modules:
                icon = "[OK]" if instance else ("[--]" if importable else "[XX]")
                status_lines.append(f"  {icon} {name}")
            return True, '\n'.join(status_lines)

        # === PLUGIN SKILL FALLBACK ===
        plugin_response = self._try_plugin_execution(raw_command)
        if plugin_response:
            return True, plugin_response

        # Not a system command - let AI handle it
        return False, ""

    def _try_plugin_execution(self, query: str) -> Optional[str]:
        """Try plugin handlers after built-ins to preserve local command precedence."""
        if not getattr(self, "_plugin_commands_enabled", True):
            return None

        registry = getattr(self, "plugin_registry", None)
        if registry is None:
            return None

        if not getattr(self, "_plugin_handlers_ready", False):
            try:
                registry.load_all()
                registry.start_watcher()
                self._plugin_handlers_ready = True
            except Exception as e:
                logger.warning(f"[LADA Core] Plugin registry init failed: {e}")
                return None

        try:
            return registry.execute_handler(query)
        except Exception as e:
            logger.warning(f"[LADA Core] Plugin execution error: {e}")
            return None

    def _record_activity(self):
        self._last_activity_ts = time.time()
        self._session_count += 1

    def _start_kairos_loop(self):
        if self._kairos_thread and self._kairos_thread.is_alive():
            return

        def _worker():
            while not self._kairos_stop.wait(self._kairos_interval_seconds):
                try:
                    idle_for = time.time() - self._last_activity_ts
                    if idle_for < self._kairos_idle_seconds:
                        continue
                    if self._session_count < self._kairos_min_sessions:
                        continue
                    self._run_kairos_consolidation()
                except Exception as e:
                    logger.warning(f"[KAIROS] Background loop error: {e}")

        self._kairos_thread = threading.Thread(
            target=_worker,
            name="lada-kairos",
            daemon=True,
        )
        self._kairos_thread.start()
        logger.info("[KAIROS] Auto-dream loop started")

    def _run_kairos_consolidation(self):
        """
        KAIROS-safe consolidation:
        Orient -> Gather -> Consolidate -> Prune.
        """
        if not self.memory:
            return
        try:
            from lada_memory import get_markdown_memory
            md_mem = get_markdown_memory()
            recent_logs = md_mem.get_recent_logs(days=3)
            if not recent_logs:
                return

            gathered = {}
            gathered["Projects"] = "Recent activity consolidated from daily logs."
            gathered["Preferences"] = "Session patterns observed; preferences retained."
            gathered["Key Facts"] = "Important recent notes were preserved during idle consolidation."
            md_mem.consolidate_to_memory(gathered)

            md_mem.append_to_daily_log(
                "KAIROS consolidation completed (Orient→Gather→Consolidate→Prune).",
                category="kairos",
            )
            logger.info("[KAIROS] Consolidation completed")
        except Exception as e:
            logger.warning(f"[KAIROS] Consolidation failed: {e}")
    def _handle_typing(self, cmd: str) -> Tuple[bool, str]:
        """Handle typing commands - type text for the user"""
        # Extract what to type
        for pattern in ['type ', 'type this ', 'write this ', 'enter this ']:
            if pattern in cmd:
                text = cmd.split(pattern, 1)[-1].strip()
                break
        else:
            return True, "What would you like me to type?"
        
        if not text:
            return True, "What would you like me to type?"
        
        if self.system:
            result = self.system.type_text(text)
            if result.get('success'):
                return True, f"{LadaPersonality.get_acknowledgment()} I've typed that for you."
            return True, f"I couldn't type the text. {result.get('error', '')}"
        
        # Fallback without system controller
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.02)
            return True, f"{LadaPersonality.get_acknowledgment()} I've typed that for you."
        except ImportError:
            return True, "Typing requires pyautogui. Install with: pip install pyautogui"
        except Exception as e:
            return True, f"I couldn't type the text: {e}"
    
    def _handle_key_press(self, cmd: str) -> Tuple[bool, str]:
        """Handle key press commands"""
        key_map = {
            'enter': 'enter',
            'escape': 'escape',
            'esc': 'escape',
            'tab': 'tab',
            'backspace': 'backspace',
            'delete': 'delete',
            'space': 'space',
            'up': 'up',
            'down': 'down',
            'left': 'left',
            'right': 'right',
        }
        
        # Find the key to press
        for key_name, key_code in key_map.items():
            if key_name in cmd.lower():
                if self.system:
                    result = self.system.press_key(key_code)
                    if result.get('success'):
                        return True, f"{LadaPersonality.get_acknowledgment()}"
                    return True, f"Couldn't press {key_name}. {result.get('error', '')}"
                else:
                    try:
                        import pyautogui
                        pyautogui.press(key_code)
                        return True, f"{LadaPersonality.get_acknowledgment()}"
                    except ImportError:
                        return True, "Key press requires pyautogui. Install with: pip install pyautogui"
        
        return False, ""
    
    def get_proactive_alerts(self) -> Optional[str]:
        """Check for conditions that need proactive alerts"""
        alerts = []
        
        # Battery low warning
        try:
            battery = psutil.sensors_battery()
            if battery and not battery.power_plugged and battery.percent < 20:
                alerts.append(f"Heads up - battery is at {battery.percent}%. You might want to plug in soon.")
        except Exception as e:
            pass
        
        # High CPU warning
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            if cpu > 90:
                alerts.append(f"Your CPU is running quite hot at {cpu}%. Some processes might be using a lot of resources.")
        except Exception as e:
            pass
        
        # High memory warning
        try:
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                alerts.append(f"Memory usage is high at {mem.percent}%. Consider closing some applications.")
        except Exception as e:
            pass
        
        return " ".join(alerts) if alerts else None
    
    # ============ Helper Methods for Integrated Commands ============
    
    def _execute_confirmed_action(self, action: str) -> Tuple[bool, str]:
        """Execute an action that was confirmed by the user"""
        action = action.lower()
        
        if 'delete' in action:
            # Extract filepath from action description
            match = re.search(r"file\s+'([^']+)'", action)
            if match:
                filepath = match.group(1)
                return self.delete_file(filepath, permanent=True)
        
        if 'shutdown' in action or 'restart' in action:
            if 'shutdown' in action:
                subprocess.run(['shutdown', '/s', '/t', '60'], check=False)
                return True, "Computer will shut down in 60 seconds. Say 'cancel shutdown' to abort."
            elif 'restart' in action:
                subprocess.run(['shutdown', '/r', '/t', '60'], check=False)
                return True, "Computer will restart in 60 seconds. Say 'cancel shutdown' to abort."
        
        if 'empty recycle' in action or 'empty trash' in action:
            try:
                subprocess.run([
                    'powershell', '-Command',
                    'Clear-RecycleBin -Force -ErrorAction SilentlyContinue'
                ], capture_output=True)
                return True, "Recycle bin emptied."
            except Exception as e:
                return True, f"Could not empty recycle bin: {e}"

        if 'log' in action and ('off' in action or 'out' in action):
            if self.system:
                result = self.system.power_action('logoff')
                return True, "Logging off..." if result.get('success') else f"Could not log off: {result.get('error', '')}"
            subprocess.run(['shutdown', '/l', '/t', '1'], check=False)
            return True, "Logging off..."

        return True, f"Action '{action}' confirmed but execution not implemented."
    
    def _handle_undo(self) -> Tuple[bool, str]:
        """Handle undo request using safety controller's undo stack"""
        if not self.safety:
            return True, "Undo is not available."
        
        try:
            result = self.safety.undo_last()
            if result and result.get('success'):
                return True, f"Undone: {result.get('action', 'last action')}"
            return True, "Nothing to undo, or undo not possible for the last action."
        except Exception as e:
            return True, f"Could not undo: {e}"
    
    def _handle_navigation(self, cmd: str) -> Tuple[bool, str]:
        """Handle folder navigation commands"""
        # Common locations
        locations = {
            'desktop': str(Path.home() / 'Desktop'),
            'documents': str(Path.home() / 'Documents'),
            'downloads': str(Path.home() / 'Downloads'),
            'pictures': str(Path.home() / 'Pictures'),
            'music': str(Path.home() / 'Music'),
            'videos': str(Path.home() / 'Videos'),
            'home': str(Path.home()),
            'drive c': 'C:\\',
            'drive d': 'D:\\',
        }
        
        for name, path in locations.items():
            if name in cmd:
                if os.path.exists(path):
                    os.startfile(path)
                    return True, f"Opening {name.title()}..."
                return True, f"{name.title()} folder not found."
        
        # Try to find a path in the command
        match = re.search(r'(?:go to|open|navigate to|show)\s+(.+)', cmd)
        if match:
            target = match.group(1).strip()
            if os.path.exists(target):
                os.startfile(target)
                return True, f"Opening {target}..."
            return True, f"Could not find '{target}'."
        
        return False, ""
    
    # ============ Window Management (Phase 3) ============
    
    def _handle_window_command(self, cmd: str) -> Tuple[bool, str]:
        """Handle window management commands using pygetwindow"""
        if not self.window_mgr:
            return True, "Window management requires pygetwindow. Install with: pip install pygetwindow"
        
        try:
            cmd_lower = cmd.lower()
            
            # List all windows
            if any(x in cmd_lower for x in ['list windows', 'show windows', 'all windows', 'open windows']):
                windows = self.window_mgr.getAllTitles()
                # Filter empty titles
                windows = [w for w in windows if w.strip()][:10]
                if windows:
                    response = "**Open Windows:**\n"
                    for i, w in enumerate(windows, 1):
                        response += f"{i}. {w[:50]}\n"
                    return True, response
                return True, "No windows found."
            
            # Minimize all windows
            if any(x in cmd_lower for x in ['minimize all', 'show desktop', 'hide all windows']):
                for win in self.window_mgr.getAllWindows():
                    try:
                        win.minimize()
                    except Exception as e:
                        pass
                return True, "Minimized all windows."
            
            # Focus/activate a window
            if any(x in cmd_lower for x in ['focus ', 'switch to ', 'activate ', 'go to window']):
                for pattern in ['focus ', 'switch to ', 'activate ', 'go to window ']:
                    if pattern in cmd_lower:
                        target = cmd_lower.split(pattern, 1)[-1].strip()
                        break
                
                for win in self.window_mgr.getAllWindows():
                    if target.lower() in win.title.lower():
                        try:
                            win.activate()
                            return True, f"Switched to {win.title[:50]}."
                        except Exception as e:
                            return True, f"Found '{target}' but couldn't activate it."
                return True, f"No window matching '{target}' found."
            
            # Minimize specific window
            if 'minimize ' in cmd_lower:
                target = cmd_lower.split('minimize ', 1)[-1].strip()
                if target in ['this', 'current', 'active']:
                    active = self.window_mgr.getActiveWindow()
                    if active:
                        active.minimize()
                        return True, f"Minimized {active.title[:50]}."
                else:
                    for win in self.window_mgr.getAllWindows():
                        if target in win.title.lower():
                            win.minimize()
                            return True, f"Minimized {win.title[:50]}."
                return True, f"Window '{target}' not found."
            
            # Maximize window
            if 'maximize ' in cmd_lower:
                target = cmd_lower.split('maximize ', 1)[-1].strip()
                if target in ['this', 'current', 'active']:
                    active = self.window_mgr.getActiveWindow()
                    if active:
                        active.maximize()
                        return True, f"Maximized {active.title[:50]}."
                else:
                    for win in self.window_mgr.getAllWindows():
                        if target in win.title.lower():
                            win.maximize()
                            return True, f"Maximized {win.title[:50]}."
                return True, f"Window '{target}' not found."
            
            # Close specific window
            if 'close window ' in cmd_lower:
                target = cmd_lower.split('close window ', 1)[-1].strip()
                for win in self.window_mgr.getAllWindows():
                    if target in win.title.lower():
                        win.close()
                        return True, f"Closed {win.title[:50]}."
                return True, f"Window '{target}' not found."
            
            # Move window (left/right half)
            if any(x in cmd_lower for x in ['snap left', 'move left', 'window left']):
                import pyautogui
                pyautogui.hotkey('win', 'left')
                return True, "Snapped window to left."
            
            if any(x in cmd_lower for x in ['snap right', 'move right', 'window right']):
                import pyautogui
                pyautogui.hotkey('win', 'right')
                return True, "Snapped window to right."
            
        except Exception as e:
            return True, f"Window control error: {e}"
        
        return False, ""
    
    def get_routine_suggestion(self) -> Optional[str]:
        """Get a routine suggestion based on current time and learned patterns"""
        if not self.memory:
            return None
        
        current_hour = datetime.now().hour
        time_of_day = 'morning' if 5 <= current_hour < 12 else 'afternoon' if 12 <= current_hour < 17 else 'evening' if 17 <= current_hour < 21 else 'night'
        
        routine = self.memory.get_routine(time_of_day)
        if routine:
            return f"Would you like me to run your {time_of_day} routine? It includes: {', '.join(routine['actions'][:3])}"
        return None
    
    def run_multi_step_task(self, steps: List[str], on_progress=None) -> Tuple[bool, str]:
        """Run a multi-step task with progress updates"""
        results = []
        for i, step in enumerate(steps):
            if on_progress:
                on_progress(i + 1, len(steps), step)
            handled, response = self.process(step)
            results.append(f"Step {i+1}: {response}")
            time.sleep(0.5)  # Small delay between steps
        
        return True, "Completed all steps:\n" + "\n".join(results)


# Test the command processor
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    processor = JarvisCommandProcessor()
    
    # Test commands
    test_commands = [
        "what time is it",
        "what is the date",
        "set volume to 50",
        "open chrome",
        "search for python tutorials",
        "youtube play music",
        "battery status",
        "cpu usage",
        "take a screenshot",
    ]
    
    print("=" * 50)
    print("LADA JARVIS Core - Command Test")
    print("=" * 50)
    
    for cmd in test_commands:
        handled, response = processor.process(cmd)
        status = "✓" if handled else "→ AI"
        print(f"\n[{status}] '{cmd}'")
        print(f"    {response}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
