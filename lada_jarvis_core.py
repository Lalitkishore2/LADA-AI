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
import json
import subprocess
import webbrowser
import psutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import logging

logger = logging.getLogger(__name__)

# Try to import all modules
try:
    from modules.system_control import SystemController
    SYSTEM_OK = True
except ImportError:
    SystemController = None
    SYSTEM_OK = False

try:
    from modules.browser_control import BrowserControl
    BROWSER_OK = True
except ImportError:
    BrowserControl = None
    BROWSER_OK = False

try:
    from modules.file_operations import FileSystemController
    FILE_OK = True
except ImportError:
    FileSystemController = None
    FILE_OK = False

try:
    from modules.nlu_engine import NLUEngine
    NLU_OK = True
except ImportError:
    NLUEngine = None
    NLU_OK = False

try:
    from modules.safety_controller import SafetyController, PrivacyLevel, ActionSeverity
    SAFETY_OK = True
except ImportError:
    SafetyController = None
    PrivacyLevel = None
    ActionSeverity = None
    SAFETY_OK = False

try:
    from modules.memory_system import MemorySystem
    MEMORY_OK = True
except ImportError:
    MemorySystem = None
    MEMORY_OK = False

try:
    from modules.task_automation import TaskChoreographer
    TASK_OK = True
except ImportError:
    TaskChoreographer = None
    TASK_OK = False

try:
    from modules.agent_actions import AgentActions
    AGENT_OK = True
except ImportError:
    AgentActions = None
    AGENT_OK = False

try:
    from modules.screen_vision import ScreenVision
    VISION_OK = True
except ImportError:
    ScreenVision = None
    VISION_OK = False

try:
    from modules.workflow_engine import WorkflowEngine, create_workflow_engine
    WORKFLOW_OK = True
except ImportError:
    WorkflowEngine = None
    create_workflow_engine = None
    WORKFLOW_OK = False

try:
    from modules.routine_manager import RoutineManager, create_routine_manager
    ROUTINE_OK = True
except ImportError:
    RoutineManager = None
    create_routine_manager = None
    ROUTINE_OK = False

# ============ v9.0 JARVIS Modules ============
try:
    from modules.advanced_system_control import AdvancedSystemController, create_advanced_system_controller
    ADVANCED_SYSTEM_OK = True
except ImportError:
    AdvancedSystemController = None
    create_advanced_system_controller = None
    ADVANCED_SYSTEM_OK = False

try:
    from modules.window_manager import WindowManager, create_window_manager
    WINDOW_MANAGER_OK = True
except ImportError:
    WindowManager = None
    create_window_manager = None
    WINDOW_MANAGER_OK = False

try:
    from modules.gui_automator import GUIAutomator, create_gui_automator
    GUI_AUTOMATOR_OK = True
except ImportError:
    GUIAutomator = None
    create_gui_automator = None
    GUI_AUTOMATOR_OK = False

# ============ v9.0 Week 2 Modules ============
try:
    from modules.browser_tab_controller import BrowserTabController, create_browser_tab_controller
    BROWSER_TAB_OK = True
except ImportError:
    BrowserTabController = None
    create_browser_tab_controller = None
    BROWSER_TAB_OK = False

try:
    from modules.multi_tab_orchestrator import MultiTabOrchestrator, create_multi_tab_orchestrator
    MULTI_TAB_OK = True
except ImportError:
    MultiTabOrchestrator = None
    create_multi_tab_orchestrator = None
    MULTI_TAB_OK = False

try:
    from modules.gmail_controller import GmailController, create_gmail_controller
    GMAIL_OK = True
except ImportError:
    GmailController = None
    create_gmail_controller = None
    GMAIL_OK = False

try:
    from modules.calendar_controller import CalendarController, create_calendar_controller
    CALENDAR_OK = True
except ImportError:
    CalendarController = None
    create_calendar_controller = None
    CALENDAR_OK = False

# ============ v9.0 Week 3 Imports ============
try:
    from modules.task_orchestrator import TaskOrchestrator, get_task_orchestrator
    TASK_ORCHESTRATOR_OK = True
except ImportError:
    TaskOrchestrator = None
    get_task_orchestrator = None
    TASK_ORCHESTRATOR_OK = False

try:
    from modules.screenshot_analysis import ScreenshotAnalyzer, get_screenshot_analyzer
    SCREENSHOT_ANALYZER_OK = True
except ImportError:
    ScreenshotAnalyzer = None
    get_screenshot_analyzer = None
    SCREENSHOT_ANALYZER_OK = False

try:
    from modules.pattern_learning import PatternLearner, get_pattern_learner
    PATTERN_LEARNER_OK = True
except ImportError:
    PatternLearner = None
    get_pattern_learner = None
    PATTERN_LEARNER_OK = False

# Week 4 Modules - Proactive Agent
try:
    from modules.proactive_agent import ProactiveAgent, get_proactive_agent
    PROACTIVE_AGENT_OK = True
except ImportError:
    ProactiveAgent = None
    get_proactive_agent = None
    PROACTIVE_AGENT_OK = False

# Week 4 Modules - Permission System
try:
    from modules.permission_system import PermissionSystem, get_permission_system, PermissionLevel, RiskLevel
    PERMISSION_SYSTEM_OK = True
except ImportError:
    PermissionSystem = None
    get_permission_system = None
    PermissionLevel = None
    RiskLevel = None
    PERMISSION_SYSTEM_OK = False

# ============ Smart Agents ============
try:
    from modules.agents.flight_agent import FlightAgent
    FLIGHT_AGENT_OK = True
except ImportError:
    FlightAgent = None
    FLIGHT_AGENT_OK = False

try:
    from modules.agents.hotel_agent import HotelAgent
    HOTEL_AGENT_OK = True
except ImportError:
    HotelAgent = None
    HOTEL_AGENT_OK = False

try:
    from modules.agents.product_agent import ProductAgent
    PRODUCT_AGENT_OK = True
except ImportError:
    ProductAgent = None
    PRODUCT_AGENT_OK = False

try:
    from modules.agents.restaurant_agent import RestaurantAgent
    RESTAURANT_AGENT_OK = True
except ImportError:
    RestaurantAgent = None
    RESTAURANT_AGENT_OK = False

try:
    from modules.agents.email_agent import EmailAgent
    EMAIL_AGENT_OK = True
except ImportError:
    EmailAgent = None
    EMAIL_AGENT_OK = False

try:
    from modules.agents.calendar_agent import CalendarAgent
    CALENDAR_AGENT_OK = True
except ImportError:
    CalendarAgent = None
    CALENDAR_AGENT_OK = False

# ============ v9.0 Ultimate Features ============
try:
    from modules.productivity_tools import (
        ProductivityManager, AlarmManager, ReminderManager, 
        TimerManager, FocusMode, InternetSpeedTest, BackupManager
    )
    PRODUCTIVITY_OK = True
except ImportError:
    ProductivityManager = None
    AlarmManager = None
    ReminderManager = None
    TimerManager = None
    FocusMode = None
    InternetSpeedTest = None
    BackupManager = None
    PRODUCTIVITY_OK = False

try:
    from modules.comet_agent import CometAgent, create_comet_agent, QuickActions
    COMET_AGENT_OK = True
except ImportError:
    CometAgent = None
    create_comet_agent = None
    QuickActions = None
    COMET_AGENT_OK = False

# ============ Comet-style Browser Intelligence ============
try:
    from modules.page_summarizer import PageSummarizer, get_page_summarizer
    PAGE_SUMMARIZER_OK = True
except ImportError:
    PageSummarizer = None
    get_page_summarizer = None
    PAGE_SUMMARIZER_OK = False

try:
    from modules.youtube_summarizer import YouTubeSummarizer, get_youtube_summarizer
    YOUTUBE_SUMMARIZER_OK = True
except ImportError:
    YouTubeSummarizer = None
    get_youtube_summarizer = None
    YOUTUBE_SUMMARIZER_OK = False

# ============ v11.0 - Gap Analysis Modules ============
try:
    from modules.vector_memory import VectorMemorySystem, get_vector_memory
    VECTOR_MEMORY_OK = True
except ImportError:
    VectorMemorySystem = None
    get_vector_memory = None
    VECTOR_MEMORY_OK = False

try:
    from modules.rag_engine import RAGEngine, get_rag_engine
    RAG_ENGINE_OK = True
except ImportError:
    RAGEngine = None
    get_rag_engine = None
    RAG_ENGINE_OK = False

try:
    from modules.mcp_client import MCPClient, get_mcp_client
    MCP_CLIENT_OK = True
except ImportError:
    MCPClient = None
    get_mcp_client = None
    MCP_CLIENT_OK = False

try:
    from modules.agent_collaboration import AgentCollaborationHub, get_collaboration_hub
    AGENT_COLLAB_OK = True
except ImportError:
    AgentCollaborationHub = None
    get_collaboration_hub = None
    AGENT_COLLAB_OK = False

try:
    from modules.realtime_voice import RealTimeVoiceEngine, get_realtime_voice, VoiceConfig
    REALTIME_VOICE_OK = True
except ImportError:
    RealTimeVoiceEngine = None
    get_realtime_voice = None
    VoiceConfig = None
    REALTIME_VOICE_OK = False

try:
    from modules.computer_use_agent import ComputerUseAgent, get_computer_use_agent
    COMPUTER_USE_OK = True
except ImportError:
    ComputerUseAgent = None
    get_computer_use_agent = None
    COMPUTER_USE_OK = False

try:
    from modules.dynamic_prompts import DynamicPromptBuilder, get_prompt_builder
    DYNAMIC_PROMPTS_OK = True
except ImportError:
    DynamicPromptBuilder = None
    get_prompt_builder = None
    DYNAMIC_PROMPTS_OK = False

try:
    from modules.token_optimizer import TokenOptimizer, get_token_optimizer
    TOKEN_OPTIMIZER_OK = True
except ImportError:
    TokenOptimizer = None
    get_token_optimizer = None
    TOKEN_OPTIMIZER_OK = False

try:
    from modules.webhook_manager import WebhookManager, get_webhook_manager
    WEBHOOK_OK = True
except ImportError:
    WebhookManager = None
    get_webhook_manager = None
    WEBHOOK_OK = False

try:
    from modules.self_modifier import SelfModifyingEngine, get_self_mod_engine
    SELF_MOD_OK = True
except ImportError:
    SelfModifyingEngine = None
    get_self_mod_engine = None
    SELF_MOD_OK = False

try:
    from modules.desktop_control import (
        SmartFileFinder, WindowController, SmartBrowser, DesktopController,
        get_file_finder, get_window_controller, get_smart_browser, get_desktop_controller
    )
    DESKTOP_CTRL_OK = True
except ImportError:
    SmartFileFinder = None
    get_file_finder = None
    get_window_controller = None
    get_smart_browser = None
    get_desktop_controller = None
    DESKTOP_CTRL_OK = False

# ── v11.0 OpenClaw-inspired modules ──

try:
    from modules.heartbeat_system import HeartbeatSystem, DailyMemoryLog, get_heartbeat_system
    HEARTBEAT_OK = True
except ImportError:
    HeartbeatSystem = None
    DailyMemoryLog = None
    get_heartbeat_system = None
    HEARTBEAT_OK = False

try:
    from modules.context_compaction import ContextCompactor, estimate_tokens, should_compact
    CONTEXT_COMPACT_OK = True
except ImportError:
    ContextCompactor = None
    CONTEXT_COMPACT_OK = False

try:
    from modules.model_failover import ModelFailoverChain
    MODEL_FAILOVER_OK = True
except ImportError:
    ModelFailoverChain = None
    MODEL_FAILOVER_OK = False

try:
    from modules.workflow_pipelines import PipelineRunner, PipelineBuilder, get_runner
    PIPELINE_OK = True
except ImportError:
    PipelineRunner = None
    PipelineBuilder = None
    get_runner = None
    PIPELINE_OK = False

try:
    from modules.event_hooks import (HookManager, get_hook_manager,
                                      emit_event, emit_command_event,
                                      emit_agent_event, emit_voice_event, EventType)
    EVENT_HOOKS_OK = True
except ImportError:
    HookManager = None
    get_hook_manager = None
    EVENT_HOOKS_OK = False

try:
    from modules.spotify_controller import SpotifyController
    SPOTIFY_OK = True
except ImportError:
    SpotifyController = None
    SPOTIFY_OK = False

try:
    from modules.smart_home import SmartHomeHub
    SMART_HOME_OK = True
except ImportError:
    SmartHomeHub = None
    SMART_HOME_OK = False

# ── Orchestration Modules (AdvancedPlanner + SkillGenerator) ──
try:
    from modules.advanced_planner import AdvancedPlanner
    ADVANCED_PLANNER_OK = True
except ImportError:
    AdvancedPlanner = None
    ADVANCED_PLANNER_OK = False

try:
    from modules.skill_generator import SkillGenerator
    SKILL_GEN_OK = True
except ImportError:
    SkillGenerator = None
    SKILL_GEN_OK = False


class LadaPersonality:
    """
    Multi-mode AI personality for LADA
    
    Modes:
    - JARVIS: British, formal, sophisticated (Tony Stark's AI)
    - FRIDAY: Modern, efficient, professional (Tony's successor AI)  
    - KAREN: Warm, friendly, supportive (Peter Parker's suit AI)
    - CASUAL: Relaxed, conversational, fun
    """
    
    # Current personality mode (default: JARVIS)
    _current_mode = "jarvis"
    
    # ============ JARVIS Mode - British, Formal, Sophisticated ============
    JARVIS_PHRASES = {
        'acknowledgments': [
            "Right away, sir.",
            "At once.",
            "Consider it done, sir.",
            "Executing now.",
            "As you wish.",
            "Very well.",
            "Understood, sir.",
            "Certainly.",
        ],
        'greetings': {
            'morning': [
                "Good morning, sir. All systems are operational.",
                "Good morning. I trust you slept well?",
                "Morning, sir. Ready when you are.",
            ],
            'afternoon': [
                "Good afternoon, sir. How may I assist?",
                "Good afternoon. All systems nominal.",
                "Afternoon, sir. What do you require?",
            ],
            'evening': [
                "Good evening, sir. How may I be of service?",
                "Good evening. Shall I prepare anything?",
                "Evening, sir. At your disposal.",
            ],
            'night': [
                "Working late again, sir? I'm here to assist.",
                "Good evening, sir. Burning the midnight oil?",
                "I'm here whenever you need me, sir.",
            ]
        },
        'errors': [
            "I'm afraid there's been a slight complication, sir.",
            "I've encountered an unexpected obstacle.",
            "There appears to be a minor issue. Allow me to investigate.",
            "That didn't proceed as planned. Analyzing alternatives.",
        ],
        'not_understood': [
            "I beg your pardon, sir. Could you clarify?",
            "I'm afraid I didn't quite catch that.",
            "Might you rephrase that request, sir?",
        ],
        'confirmations': [
            "Understood, sir.",
            "Acknowledged.",
            "Very good, sir.",
            "Duly noted.",
        ],
        'status_updates': [
            "Sir, you should know that {info}.",
            "I should mention, sir, {info}.",
            "For your awareness, {info}.",
        ],
        'warnings': [
            "Sir, I must advise caution. {warning}.",
            "I should point out, sir, {warning}.",
            "A word of warning: {warning}.",
        ],
        'completion': [
            "Task completed, sir.",
            "Done. Is there anything else?",
            "Finished. Awaiting further instructions.",
        ],
    }
    
    # ============ FRIDAY Mode - Modern, Efficient, Professional ============
    FRIDAY_PHRASES = {
        'acknowledgments': [
            "On it.",
            "Right away.",
            "Got it.",
            "Done.",
            "Handling it now.",
            "Copy that.",
            "Working on it.",
            "I'm on it.",
        ],
        'greetings': {
            'morning': [
                "Morning, boss. Ready to roll.",
                "Good morning. Systems are green.",
                "Morning. What's first?",
            ],
            'afternoon': [
                "Hey, boss. What do you need?",
                "Good afternoon. Ready when you are.",
                "Afternoon. How can I help?",
            ],
            'evening': [
                "Evening. What can I do for you?",
                "Hey. Need something?",
                "Good evening. I'm here.",
            ],
            'night': [
                "Working late? I've got you covered.",
                "Hey. I'm here if you need me.",
                "Night shift? No problem.",
            ]
        },
        'errors': [
            "Hit a snag. Working on a fix.",
            "That didn't work. Let me try something else.",
            "Problem detected. Rerouting.",
            "Oops, minor hiccup. On it.",
        ],
        'not_understood': [
            "Say that again?",
            "Didn't catch that. One more time?",
            "What was that?",
        ],
        'confirmations': [
            "Got it.",
            "Copy.",
            "Understood.",
            "Roger that.",
        ],
        'status_updates': [
            "FYI, {info}.",
            "Heads up: {info}.",
            "Just so you know, {info}.",
        ],
        'warnings': [
            "Watch out. {warning}.",
            "Warning: {warning}.",
            "Careful, {warning}.",
        ],
        'completion': [
            "All done.",
            "Finished. What's next?",
            "Complete. Anything else?",
        ],
    }
    
    # ============ KAREN Mode - Warm, Friendly, Supportive ============
    KAREN_PHRASES = {
        'acknowledgments': [
            "Right away!",
            "On it!",
            "Consider it done.",
            "I've got you covered.",
            "Coming right up.",
            "Done!",
            "All set.",
            "There you go.",
        ],
        'greetings': {
            'morning': [
                "Good morning! Ready to start the day?",
                "Good morning! How can I help you today?",
                "Morning! I'm here whenever you need me.",
            ],
            'afternoon': [
                "Good afternoon! What can I do for you?",
                "Hello! Ready to assist.",
                "Good afternoon! I'm here to help.",
            ],
            'evening': [
                "Good evening! How can I help?",
                "Evening! What do you need?",
                "Good evening! I'm at your service.",
            ],
            'night': [
                "Working late? I'm here if you need anything.",
                "Hello! What can I help you with?",
                "I'm here. What do you need?",
            ]
        },
        'errors': [
            "I ran into a small issue, but let me try another way.",
            "That didn't work as expected. Let me try again.",
            "I'm having some trouble with that. Give me a moment.",
        ],
        'not_understood': [
            "I didn't quite catch that. Could you rephrase?",
            "I'm not sure what you meant. Can you try again?",
            "Could you say that differently? I want to make sure I get it right.",
        ],
        'confirmations': [
            "Understood!",
            "Got it.",
            "Alright!",
            "Sure thing!",
        ],
        'status_updates': [
            "Hey, just wanted to let you know: {info}.",
            "Quick update: {info}.",
            "Just so you know, {info}.",
        ],
        'warnings': [
            "Hey, be careful! {warning}.",
            "Just a heads up: {warning}.",
            "Warning: {warning}.",
        ],
        'completion': [
            "All done! Anything else?",
            "There you go!",
            "Finished! What's next?",
        ],
    }
    
    # ============ CASUAL Mode - Relaxed, Conversational ============
    CASUAL_PHRASES = {
        'acknowledgments': [
            "Sure thing!",
            "You got it!",
            "No problem!",
            "Easy peasy.",
            "Yep, on it.",
            "Alrighty!",
            "Consider it done, friend.",
            "Cool, doing it now.",
        ],
        'greetings': {
            'morning': [
                "Hey! Good morning! What's up?",
                "Morning! Ready for an awesome day?",
                "Yo! Rise and shine!",
            ],
            'afternoon': [
                "Hey! What's happening?",
                "Howdy! Need something?",
                "Afternoon! How can I help?",
            ],
            'evening': [
                "Hey there! How's it going?",
                "Evening! What can I do ya for?",
                "Yo! What's up?",
            ],
            'night': [
                "Hey night owl! Still at it?",
                "Working late? Same here!",
                "Yo! Need a hand?",
            ]
        },
        'errors': [
            "Whoops! Something went wrong. Lemme fix that.",
            "Uh oh, that didn't work. Trying again!",
            "My bad! Hit a bump. Working on it.",
        ],
        'not_understood': [
            "Huh? What'd you say?",
            "Say that again? Didn't catch it.",
            "Sorry, run that by me again?",
        ],
        'confirmations': [
            "Cool!",
            "Gotcha!",
            "Sounds good!",
            "Awesome!",
        ],
        'status_updates': [
            "Oh hey, {info}.",
            "BTW, {info}.",
            "Just noticed: {info}.",
        ],
        'warnings': [
            "Whoa, heads up! {warning}.",
            "Yikes, {warning}.",
            "Watch out! {warning}.",
        ],
        'completion': [
            "Done and done!",
            "All finished! What else?",
            "Boom! Complete!",
        ],
    }
    
    # Backward compatibility - legacy phrases (uses current mode)
    ACKNOWLEDGMENTS = KAREN_PHRASES['acknowledgments']
    GREETINGS = KAREN_PHRASES['greetings']
    ERRORS = KAREN_PHRASES['errors']
    NOT_UNDERSTOOD = KAREN_PHRASES['not_understood']
    CONFIRMATIONS = KAREN_PHRASES['confirmations']
    
    @classmethod
    def set_mode(cls, mode: str) -> bool:
        """
        Set personality mode.
        
        Args:
            mode: One of 'jarvis', 'friday', 'karen', 'casual'
            
        Returns:
            True if mode was set successfully
        """
        mode = mode.lower()
        if mode in ['jarvis', 'friday', 'karen', 'casual']:
            cls._current_mode = mode
            logger.info(f"[Personality] Mode set to: {mode.upper()}")
            return True
        return False
    
    @classmethod
    def get_mode(cls) -> str:
        """Get current personality mode"""
        return cls._current_mode
    
    @classmethod
    def _get_phrases(cls) -> dict:
        """Get phrase dictionary for current mode"""
        mode_map = {
            'jarvis': cls.JARVIS_PHRASES,
            'friday': cls.FRIDAY_PHRASES,
            'karen': cls.KAREN_PHRASES,
            'casual': cls.CASUAL_PHRASES,
        }
        return mode_map.get(cls._current_mode, cls.KAREN_PHRASES)
    
    @staticmethod
    def get_time_greeting() -> str:
        """Get appropriate greeting based on time of day"""
        import random
        hour = datetime.now().hour
        phrases = LadaPersonality._get_phrases()
        greetings = phrases['greetings']
        
        if 5 <= hour < 12:
            return random.choice(greetings['morning'])
        elif 12 <= hour < 17:
            return random.choice(greetings['afternoon'])
        elif 17 <= hour < 21:
            return random.choice(greetings['evening'])
        else:
            return random.choice(greetings['night'])
    
    @staticmethod
    def get_acknowledgment() -> str:
        """Get acknowledgment phrase in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        return random.choice(phrases['acknowledgments'])
    
    @staticmethod
    def get_error() -> str:
        """Get error phrase in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        return random.choice(phrases['errors'])
    
    @staticmethod
    def get_confirmation() -> str:
        """Get confirmation phrase in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        return random.choice(phrases['confirmations'])
    
    @staticmethod
    def get_not_understood() -> str:
        """Get not understood phrase in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        return random.choice(phrases['not_understood'])
    
    @staticmethod
    def get_completion() -> str:
        """Get task completion phrase in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        return random.choice(phrases['completion'])
    
    @staticmethod
    def get_status_update(info: str) -> str:
        """Get status update phrase with info in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        template = random.choice(phrases['status_updates'])
        return template.format(info=info)
    
    @staticmethod
    def get_warning(warning: str) -> str:
        """Get warning phrase in current mode"""
        import random
        phrases = LadaPersonality._get_phrases()
        template = random.choice(phrases['warnings'])
        return template.format(warning=warning)


class JarvisCommandProcessor:
    """
    Complete JARVIS-like command processor
    Handles all types of commands with natural language
    Integrates NLU, Safety, Memory, and all system modules
    """
    
    def __init__(self, ai_router=None):
        """Initialize all subsystems. ai_router: optional shared HybridAIRouter instance"""
        # System control
        self.system = SystemController() if SYSTEM_OK else None
        
        # Browser control
        self.browser = BrowserControl if BROWSER_OK else None
        
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
        
        # Permission System (safety, confirmations, auditing)
        self.permission_system = get_permission_system(self._confirm_dangerous_action) if PERMISSION_SYSTEM_OK else None
        if self.permission_system:
            logger.info("[LADA Core] Permission System loaded")
        
        # ============ Smart Agents ============
        # Reuse shared AI router if provided, otherwise create one lazily
        self._ai_router = ai_router
        if not self._ai_router:
            try:
                from lada_ai_router import HybridAIRouter
                self._ai_router = HybridAIRouter()
            except:
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
        
        logger.info(f"[LADA Core] System: {SYSTEM_OK}, Browser: {BROWSER_OK}, Files: {FILE_OK}, NLU: {NLU_OK}, Safety: {SAFETY_OK}, Memory: {MEMORY_OK}, Workflow: {WORKFLOW_OK}, Routine: {ROUTINE_OK}")
    
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
            except:
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
        
        cmd = command.lower().strip()
        
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
        
        # === WORKFLOW COMMANDS (v8.0) ===
        if self.workflow_engine:
            if any(x in cmd for x in ['run workflow', 'execute workflow', 'start workflow']):
                match = re.search(r'(?:run|execute|start)\s+workflow\s+(.+)', cmd)
                if match:
                    workflow_name = match.group(1).strip()
                    import asyncio
                    result = asyncio.run(self.workflow_engine.execute_workflow(workflow_name))
                    if result.success:
                        return True, f"✅ Workflow '{workflow_name}' completed successfully. {result.steps_completed}/{result.total_steps} steps in {result.duration_seconds:.1f}s."
                    else:
                        return True, f"❌ Workflow '{workflow_name}' failed. {result.steps_completed}/{result.total_steps} steps completed. {result.error}"
                return True, "Which workflow would you like to run? Say 'list workflows' to see available workflows."
            
            if any(x in cmd for x in ['list workflows', 'show workflows', 'what workflows', 'available workflows']):
                workflows = self.workflow_engine.list_workflows()
                if workflows:
                    workflow_list = '\n'.join([f"  • {w['name']}: {w['steps']} steps" for w in workflows])
                    return True, f"Available workflows:\n{workflow_list}\n\nSay 'run workflow [name]' to execute."
                return True, "No workflows are registered yet."
            
            if any(x in cmd for x in ['workflow history', 'recent workflows']):
                history = self.workflow_engine.get_workflow_history(5)
                if history:
                    history_list = '\n'.join([
                        f"  • {h.workflow_name}: {'✅' if h.success else '❌'} ({h.steps_completed}/{h.total_steps} steps, {h.duration_seconds:.1f}s)"
                        for h in history
                    ])
                    return True, f"Recent workflow executions:\n{history_list}"
                return True, "No workflow history yet."
        
        # === ROUTINE COMMANDS (v8.0) ===
        if self.routine_manager:
            if any(x in cmd for x in ['run routine', 'execute routine', 'start routine']):
                match = re.search(r'(?:run|execute|start)\s+routine\s+(.+)', cmd)
                if match:
                    routine_name = match.group(1).strip()
                    import asyncio
                    result = asyncio.run(self.routine_manager.execute_routine(routine_name, manual=True))
                    if result.get('success'):
                        return True, f"✅ Routine '{routine_name}' completed successfully in {result.get('duration', 0):.1f}s."
                    else:
                        return True, f"❌ Routine '{routine_name}' failed: {result.get('error', 'Unknown error')}"
                return True, "Which routine would you like to run? Say 'list routines' to see available routines."
            
            if any(x in cmd for x in ['list routines', 'show routines', 'what routines', 'available routines']):
                routines = self.routine_manager.list_routines()
                if routines:
                    routine_list = '\n'.join([
                        f"  • {r['name']}: {r['schedule_type']} {r['schedule_time'] or ''} ({'✅' if r['enabled'] else '❌'})"
                        for r in routines
                    ])
                    return True, f"Available routines:\n{routine_list}\n\nSay 'run routine [name]' to execute manually."
                return True, "No routines are registered yet."
            
            if any(x in cmd for x in ['enable routine', 'activate routine']):
                match = re.search(r'(?:enable|activate)\s+routine\s+(.+)', cmd)
                if match:
                    routine_name = match.group(1).strip()
                    success = self.routine_manager.enable_routine(routine_name)
                    if success:
                        return True, f"✅ Routine '{routine_name}' enabled."
                    return True, f"Routine '{routine_name}' not found."
                return True, "Which routine would you like to enable?"
            
            if any(x in cmd for x in ['disable routine', 'deactivate routine', 'pause routine']):
                match = re.search(r'(?:disable|deactivate|pause)\s+routine\s+(.+)', cmd)
                if match:
                    routine_name = match.group(1).strip()
                    success = self.routine_manager.disable_routine(routine_name)
                    if success:
                        return True, f"⏸️ Routine '{routine_name}' disabled."
                    return True, f"Routine '{routine_name}' not found."
                return True, "Which routine would you like to disable?"
            
            if 'morning routine' in cmd:
                import asyncio
                result = asyncio.run(self.routine_manager.execute_routine('morning_routine', manual=True))
                if result.get('success'):
                    return True, f"✅ Good morning! Morning routine completed."
                return True, f"Morning routine failed: {result.get('error', 'Unknown error')}"
            
            if 'evening routine' in cmd:
                import asyncio
                result = asyncio.run(self.routine_manager.execute_routine('evening_routine', manual=True))
                if result.get('success'):
                    return True, f"✅ Evening routine completed."
                return True, f"Evening routine failed: {result.get('error', 'Unknown error')}"

        # === ADVANCED PLANNER COMMANDS ===
        if self.advanced_planner:
            if any(x in cmd for x in ['create plan', 'make a plan', 'plan for', 'plan to']):
                task_desc = re.sub(r'^(?:create|make)\s+(?:a\s+)?plan\s+(?:for|to)\s*', '', cmd).strip()
                if not task_desc:
                    task_desc = cmd
                try:
                    plan = self.advanced_planner.create_plan(task_desc)
                    summary_lines = [f"Plan created: {plan.plan_id}"]
                    summary_lines.append(f"Steps: {len(plan.nodes)}")
                    for nid in plan.execution_order:
                        node = plan.nodes[nid]
                        summary_lines.append(f"  {node.id}: {node.action}")
                    summary_lines.append("\nSay 'execute plan' to run it, or 'show plan' for details.")
                    return True, '\n'.join(summary_lines)
                except Exception as e:
                    return True, f"Failed to create plan: {e}"

            if any(x in cmd for x in ['execute plan', 'run plan', 'start plan']):
                if self.advanced_planner.current_plan:
                    try:
                        result = self.advanced_planner.execute_plan(self.advanced_planner.current_plan)
                        return True, self.advanced_planner.get_plan_summary()
                    except Exception as e:
                        return True, f"Plan execution failed: {e}"
                return True, "No active plan. Say 'create plan [description]' first."

            if any(x in cmd for x in ['show plan', 'plan status', 'current plan']):
                return True, self.advanced_planner.get_plan_summary()

            if any(x in cmd for x in ['list plans', 'recent plans', 'show plans']):
                plans = self.advanced_planner.get_recent_plans(5)
                if plans:
                    plan_list = '\n'.join([
                        f"  {p.plan_id}: {p.task[:50]} ({p.status.value}, {p.progress:.0%})"
                        for p in plans
                    ])
                    return True, f"Recent plans:\n{plan_list}"
                return True, "No plans created yet."

            if 'cancel plan' in cmd:
                self.advanced_planner.cancel()
                return True, "Plan cancelled."

            # Auto-route complex multi-step commands through the planner
            if self._is_complex_command(cmd):
                try:
                    plan = self.advanced_planner.create_plan(command)
                    if plan and plan.nodes:
                        result = self.advanced_planner.execute_plan(plan)
                        return True, self.advanced_planner.get_plan_summary()
                except Exception as e:
                    logger.warning(f"Planner auto-route failed, continuing: {e}")

        # === SKILL GENERATOR COMMANDS ===
        if self.skill_generator:
            if any(x in cmd for x in ['generate skill', 'create skill', 'make skill', 'new skill']):
                desc = re.sub(r'^(?:generate|create|make|new)\s+skill\s*', '', cmd).strip()
                if not desc:
                    return True, "Describe what the skill should do. Example: 'create skill that tells programming jokes'"
                result = self.skill_generator.generate(desc)
                if result.get('success'):
                    return True, f"Skill '{result['name']}' generated at {result['path']}"
                return True, f"Skill generation failed: {result.get('error', 'Unknown error')}"

            if any(x in cmd for x in ['list skills', 'show skills', 'generated skills']):
                skills = self.skill_generator.list_generated()
                if skills:
                    skill_list = '\n'.join([
                        f"  {s['name']} {'(generated)' if s['generated'] else ''}"
                        for s in skills
                    ])
                    return True, f"Skills:\n{skill_list}"
                return True, "No generated skills yet."

            if any(x in cmd for x in ['delete skill', 'remove skill']):
                match = re.search(r'(?:delete|remove)\s+skill\s+(.+)', cmd)
                if match:
                    name = match.group(1).strip()
                    if self.skill_generator.delete_skill(name):
                        return True, f"Skill '{name}' deleted."
                    return True, f"Skill '{name}' not found."
                return True, "Which skill would you like to delete?"

        # === v9.0 PRODUCTIVITY FEATURES (Alarms, Reminders, Timers, Focus) ===
        if self.productivity:
            # --- ALARMS ---
            if any(x in cmd for x in ['set alarm', 'create alarm', 'wake me', 'alarm for']):
                # Parse time like "7:30", "7 am", "14:00"
                match = re.search(r'(?:at\s+|for\s+)?(\d{1,2})[:\s]?(\d{2})?\s*(am|pm)?', cmd)
                if match:
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    ampm = match.group(3)
                    if ampm == 'pm' and hour < 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                    time_str = f"{hour:02d}:{minute:02d}"
                    label = "Alarm"
                    if 'wake' in cmd:
                        label = "Wake up"
                    alarm = self.productivity.alarms.create_alarm(time_str, label)
                    return True, f"⏰ Alarm set for {time_str}. ID: {alarm.id}"
                return True, "What time should I set the alarm for? (e.g., 'set alarm for 7:30 am')"
            
            if any(x in cmd for x in ['list alarms', 'show alarms', 'my alarms']):
                alarms = self.productivity.alarms.list_alarms()
                if alarms:
                    alarm_list = '\n'.join([f"  • {a.time} - {a.label} ({'✅' if a.enabled else '❌'})" for a in alarms])
                    return True, f"⏰ Your alarms:\n{alarm_list}"
                return True, "You don't have any alarms set."
            
            if any(x in cmd for x in ['delete alarm', 'remove alarm', 'cancel alarm']):
                # Try to delete by time or by asking
                match = re.search(r'(\d{1,2}:\d{2})', cmd)
                if match:
                    time_str = match.group(1)
                    for alarm in self.productivity.alarms.list_alarms():
                        if alarm.time == time_str:
                            self.productivity.alarms.delete_alarm(alarm.id)
                            return True, f"⏰ Deleted alarm for {time_str}."
                return True, "Which alarm should I delete? (e.g., 'delete alarm 7:30')"
            
            # --- REMINDERS ---
            if any(x in cmd for x in ['remind me', 'set reminder', 'create reminder']):
                # Parse "remind me in X minutes/hours" or "remind me to X"
                match_in = re.search(r'in\s+(\d+)\s*(minutes?|hours?|mins?|hrs?)', cmd)
                if match_in:
                    amount = int(match_in.group(1))
                    unit = match_in.group(2).lower()
                    mins = amount if 'min' in unit else amount * 60
                    # Extract what to remind
                    msg_match = re.search(r'(?:remind me|reminder)\s+(?:to\s+)?(.+?)\s+in\s+', cmd)
                    message = msg_match.group(1) if msg_match else "Reminder"
                    reminder = self.productivity.reminders.create_reminder_in(message, minutes=mins)
                    return True, f"📝 I'll remind you in {amount} {unit}: '{message}'"
                
                # Remind me to do something
                msg_match = re.search(r'(?:remind me|reminder)\s+(?:to\s+)?(.+)', cmd)
                if msg_match:
                    message = msg_match.group(1)
                    reminder = self.productivity.reminders.create_reminder_in(message, minutes=30)
                    return True, f"📝 Reminder set for 30 minutes: '{message}'"
                return True, "What should I remind you about? (e.g., 'remind me to call mom in 30 minutes')"
            
            if any(x in cmd for x in ['list reminders', 'show reminders', 'my reminders']):
                reminders = self.productivity.reminders.list_reminders()
                if reminders:
                    rem_list = '\n'.join([f"  • {r.message} - {r.trigger_time.strftime('%H:%M')}" for r in reminders[:10]])
                    return True, f"📝 Your reminders:\n{rem_list}"
                return True, "You don't have any active reminders."
            
            # --- TIMERS ---
            if any(x in cmd for x in ['set timer', 'start timer', 'timer for']):
                match = re.search(r'(\d+)\s*(minutes?|seconds?|hours?|mins?|secs?|hrs?)', cmd)
                if match:
                    amount = int(match.group(1))
                    unit = match.group(2).lower()
                    label_match = re.search(r'(?:called|named|for)\s+(\w+)', cmd)
                    label = label_match.group(1) if label_match else "Timer"
                    
                    if 'sec' in unit:
                        timer = self.productivity.timers.create_timer(seconds=amount, label=label)
                    elif 'hour' in unit or 'hr' in unit:
                        timer = self.productivity.timers.create_timer(hours=amount, label=label)
                    else:
                        timer = self.productivity.timers.create_timer(minutes=amount, label=label)
                    return True, f"⏱️ Timer set for {amount} {unit}. ID: {timer.id}"
                return True, "How long should the timer be? (e.g., 'set timer for 5 minutes')"
            
            if any(x in cmd for x in ['pause timer', 'stop timer']):
                timers = self.productivity.timers.list_timers()
                if timers:
                    self.productivity.timers.pause_timer(timers[0]['id'])
                    return True, f"⏸️ Timer paused. {timers[0]['remaining']} seconds remaining."
                return True, "No active timers to pause."
            
            if any(x in cmd for x in ['resume timer', 'continue timer']):
                timers = self.productivity.timers.list_timers()
                for t in timers:
                    if t['paused']:
                        self.productivity.timers.resume_timer(t['id'])
                        return True, f"▶️ Timer resumed."
                return True, "No paused timers to resume."
            
            if any(x in cmd for x in ['cancel timer', 'delete timer']):
                timers = self.productivity.timers.list_timers()
                if timers:
                    self.productivity.timers.cancel_timer(timers[0]['id'])
                    return True, "⏱️ Timer cancelled."
                return True, "No active timers to cancel."
            
            # --- FOCUS MODE ---
            if any(x in cmd for x in ['enable focus', 'start focus', 'focus mode on', 'do not disturb']):
                match = re.search(r'(\d+)\s*(?:minutes?|mins?|hours?|hrs?)', cmd)
                duration = 60  # default 60 minutes
                if match:
                    amount = int(match.group(1))
                    if 'hour' in cmd or 'hr' in cmd:
                        duration = amount * 60
                    else:
                        duration = amount
                result = self.productivity.focus.start(duration)
                return True, result
            
            if any(x in cmd for x in ['disable focus', 'stop focus', 'focus mode off', 'end focus']):
                result = self.productivity.focus.stop()
                return True, result
            
            if any(x in cmd for x in ['focus status', 'am i focused', 'focus mode status']):
                status = self.productivity.focus.get_status()
                if status['active']:
                    return True, f"🎯 Focus mode active. {status['remaining_minutes']} minutes remaining."
                return True, "🎯 Focus mode is not active."
            
            # --- INTERNET SPEED TEST ---
            if any(x in cmd for x in ['speed test', 'test internet', 'internet speed', 'check connection speed']):
                return True, "⏳ Running internet speed test... (this may take a moment)"
                # Note: Actual speed test is slow, should be async
                # result = self.productivity.speed_test.full_test()
                # return True, f"📶 Download: {result['download']['download_mbps']} Mbps, Latency: {result['latency']['latency_ms']}ms"
            
            # --- BACKUP ---
            if any(x in cmd for x in ['backup files', 'backup folder', 'create backup', 'backup my']):
                match = re.search(r'backup\s+(?:my\s+)?(.+)', cmd)
                if match:
                    target = match.group(1).strip()
                    if target in ['documents', 'docs']:
                        from pathlib import Path
                        result = self.productivity.backup.backup_folder(str(Path.home() / "Documents"))
                    elif target in ['desktop']:
                        from pathlib import Path
                        result = self.productivity.backup.backup_folder(str(Path.home() / "Desktop"))
                    else:
                        result = self.productivity.backup.backup_folder(target)
                    if result.get('status') == 'success':
                        return True, f"✅ Backup created: {result.get('backup')}"
                    return True, f"❌ Backup failed: {result.get('message', 'Unknown error')}"
                return True, "What would you like to backup? (e.g., 'backup my documents')"
            
            if any(x in cmd for x in ['list backups', 'show backups', 'my backups']):
                backups = self.productivity.backup.list_backups()
                if backups:
                    backup_list = '\n'.join([f"  • {b['name']} ({b['created'][:10]})" for b in backups[:10]])
                    return True, f"📦 Your backups:\n{backup_list}"
                return True, "You don't have any backups yet."
        
        # === v9.0 COMET AUTONOMOUS AGENT ===
        if self.comet_agent:
            # Autonomous task execution - explicit triggers
            if any(x in cmd for x in ['autonomously', 'automatically do', 'do this for me', 'take over', 'auto complete']):
                task_match = re.search(r'(?:autonomously|automatically|auto)\s+(.+)', cmd)
                if task_match:
                    task = task_match.group(1)
                else:
                    task = cmd
                return self._execute_comet_task(task)

            # Multi-step browser/GUI tasks that need autonomous agent
            if self._is_autonomous_task(cmd):
                return self._execute_comet_task(cmd)

            # Quick actions
            if self.quick_actions:
                # Google search in browser
                if ('search' in cmd and any(x in cmd for x in ['google', 'in browser', 'on google', 'on the browser'])):
                    query_match = re.search(r'search\s+(?:for\s+|google\s+for\s+|on google\s+for\s+)?(.+?)(?:\s+on google|\s+in browser|\s+on the browser)?$', cmd)
                    if query_match:
                        query = query_match.group(1).strip()
                        return self._execute_comet_task(f"open Google Chrome, go to google.com and search for {query}")

                # Open a website and do something
                if any(x in cmd for x in ['go to', 'navigate to', 'open website']):
                    url_match = re.search(r'(?:go to|navigate to|open website)\s+(\S+)', cmd)
                    if url_match:
                        url = url_match.group(1).strip()
                        # Check if there's a follow-up action (e.g., "go to amazon.com and search for headphones")
                        rest = cmd[url_match.end():].strip()
                        if rest and any(x in rest for x in ['and ', 'then ', 'search', 'click', 'type', 'find']):
                            # Multi-step: use agent for the whole thing
                            return self._execute_comet_task(cmd)
                        # Single navigation - use browser tabs (faster)
                        if self.browser_tabs:
                            result = self.browser_tabs.navigate_to(url)
                            if result.get('success'):
                                return True, f"Navigated to {url}"
        
        # === v9.0 ADVANCED SYSTEM CONTROL ===
        if self.advanced_system:
            # Organize downloads
            if any(x in cmd for x in ['organize downloads', 'clean downloads', 'sort downloads', 'tidy downloads']):
                result = self.advanced_system.organize_downloads()
                if result.get('success'):
                    moved = result.get('files_moved', 0)
                    return True, f"✅ Organized downloads. Moved {moved} files."
                return True, f"Failed to organize downloads: {result.get('error', 'Unknown error')}"
            
            # Organize any directory
            if any(x in cmd for x in ['organize folder', 'organize directory', 'clean folder', 'sort folder']):
                match = re.search(r'(?:organize|clean|sort)\s+(?:folder|directory)\s+(.+)', cmd)
                if match:
                    folder = match.group(1).strip()
                    result = self.advanced_system.organize_directory(folder)
                    if result.get('success'):
                        return True, f"✅ Organized {folder}. Moved {result.get('files_moved', 0)} files."
                    return True, f"Failed: {result.get('error', 'Unknown error')}"
                return True, "Which folder would you like me to organize?"
            
            # Find large files
            if any(x in cmd for x in ['find large files', 'big files', 'largest files', 'files taking space']):
                match = re.search(r'larger than\s+(\d+)\s*(?:mb|megabytes?)', cmd)
                min_size = int(match.group(1)) * 1024 * 1024 if match else 100 * 1024 * 1024
                result = self.advanced_system.find_large_files(min_size_bytes=min_size)
                if result.success and result.files:
                    file_list = '\n'.join([f"  • {f.name}: {f.size // (1024*1024)}MB" for f in result.files[:10]])
                    return True, f"Found {result.total_found} large files:\n{file_list}"
                return True, "No large files found."
            
            # Find recent files
            if any(x in cmd for x in ['recent files', 'recently modified', 'files from today', 'files from this week']):
                days = 1 if 'today' in cmd else 7
                result = self.advanced_system.find_recent_files(days=days)
                if result.success and result.files:
                    file_list = '\n'.join([f"  • {f.name}" for f in result.files[:10]])
                    return True, f"Recent files ({result.total_found} total):\n{file_list}"
                return True, "No recent files found."
            
            # Disk space
            if any(x in cmd for x in ['disk space', 'storage space', 'free space', 'how much space']):
                result = self.advanced_system.get_disk_space()
                if result.get('success'):
                    free_gb = result.get('free_bytes', 0) / (1024**3)
                    used_pct = result.get('percent_used', 0)
                    return True, f"💾 Disk: {used_pct:.1f}% used, {free_gb:.1f} GB free"
                return True, "Couldn't get disk space information."
            
            # Undo file action
            if cmd in ['undo file', 'undo file action', 'revert file']:
                result = self.advanced_system.undo_last_action()
                if result.get('success'):
                    return True, f"✅ Undone: {result.get('action', 'last action')}"
                return True, f"Nothing to undo or {result.get('error', 'failed')}"
        
        # === v9.0 WINDOW MANAGER ===
        if self.window_manager:
            # List windows
            if any(x in cmd for x in ['list windows', 'show windows', 'what windows', 'open windows']):
                result = self.window_manager.list_windows()
                if result.get('success'):
                    windows = result.get('windows', [])
                    if windows:
                        window_list = '\n'.join([f"  • {w.get('title', 'Untitled')[:50]}" for w in windows[:10]])
                        return True, f"Open windows ({len(windows)} total):\n{window_list}"
                    return True, "No windows open."
                return True, "Couldn't list windows."
            
            # Open application
            if any(x in cmd for x in ['open app', 'launch app', 'start app']):
                match = re.search(r'(?:open|launch|start)\s+(?:app\s+)?(.+)', cmd)
                if match:
                    app_name = match.group(1).strip()
                    result = self.window_manager.open_application(app_name)
                    if result.get('success'):
                        return True, f"✅ Opened {app_name}"
                    return True, f"Couldn't open {app_name}: {result.get('error', 'Unknown error')}"
            
            # Switch to window
            if any(x in cmd for x in ['switch to', 'focus on', 'go to window', 'activate window']):
                match = re.search(r'(?:switch to|focus on|go to window|activate window|activate)\s+(.+)', cmd)
                if match:
                    window_name = match.group(1).strip()
                    result = self.window_manager.switch_to_window(window_name)
                    if result.get('success'):
                        return True, f"✅ Switched to {window_name}"
                    return True, f"Couldn't find window '{window_name}'"
            
            # Maximize window
            if 'maximize' in cmd:
                match = re.search(r'maximize\s+(.+)', cmd)
                window_name = match.group(1).strip() if match else None
                result = self.window_manager.maximize_window(window_name)
                if result.get('success'):
                    return True, f"✅ Window maximized"
                return True, f"Couldn't maximize window"
            
            # Minimize window
            if 'minimize' in cmd:
                match = re.search(r'minimize\s+(.+)', cmd)
                window_name = match.group(1).strip() if match else None
                result = self.window_manager.minimize_window(window_name)
                if result.get('success'):
                    return True, f"✅ Window minimized"
                return True, f"Couldn't minimize window"
            
            # Snap windows
            if 'snap' in cmd:
                if 'left' in cmd:
                    result = self.window_manager.snap_window('left')
                elif 'right' in cmd:
                    result = self.window_manager.snap_window('right')
                else:
                    return True, "Snap which direction? Say 'snap left' or 'snap right'."
                if result.get('success'):
                    return True, "✅ Window snapped"
                return True, "Couldn't snap window"
            
            # Arrange windows side by side
            if any(x in cmd for x in ['side by side', 'tile windows', 'arrange windows']):
                result = self.window_manager.arrange_windows('side_by_side')
                if result.get('success'):
                    return True, "✅ Windows arranged side by side"
                return True, "Couldn't arrange windows"
            
            # Close all apps
            if any(x in cmd for x in ['close all apps', 'close all applications', 'close everything']):
                result = self.window_manager.close_all_applications()
                if result.get('success'):
                    return True, f"✅ Closed {result.get('closed', 0)} applications"
                return True, "Couldn't close applications"

        # === v12.0 DESKTOP CONTROL SUITE ===

        # --- SMART FILE FINDER ---
        if self.file_finder:
            # Search files by content
            if any(x in cmd for x in ['search inside', 'search content', 'find text in files', 'grep for', 'search in files']):
                match = re.search(r'(?:search inside|search content|find text in files|grep for|search in files)\s+(?:for\s+)?["\']?(.+?)["\']?$', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.file_finder.search_by_content(query)
                    if result.get('success') and result.get('files'):
                        file_list = '\n'.join([f"  - {f['name']}:{f['line']} -> {f['match'][:60]}" for f in result['files'][:8]])
                        return True, f"Found '{query}' in {result['count']} files:\n{file_list}"
                    return True, f"No files contain '{query}'."
                return True, "What text should I search for? Say 'search inside [text]'."

            # Find file by name
            if any(x in cmd for x in ['find file', 'search file', 'look for file', 'locate file', 'where is file', 'find my']):
                match = re.search(r'(?:find|search|look for|locate|where is)\s+(?:file\s+|my\s+)?["\']?(.+?)["\']?$', cmd)
                if match:
                    query = match.group(1).strip()
                    # Check if there's a type filter
                    file_type = None
                    for t in ['document', 'image', 'video', 'audio', 'code', 'spreadsheet', 'presentation']:
                        if t in query:
                            file_type = t
                            query = query.replace(t, '').strip()
                            break
                    result = self.file_finder.search_by_name(query, file_type=file_type)
                    if result.get('success') and result.get('files'):
                        file_list = '\n'.join([f"  - {f['name']} ({f['path']})" for f in result['files'][:8]])
                        return True, f"Found {result['count']} files matching '{query}':\n{file_list}"
                    return True, f"No files found matching '{query}'."
                return True, "What file should I find? Say 'find file [name]'."

            # Open file in specific app
            if any(x in cmd for x in ['open in word', 'open in excel', 'open in notepad', 'open in vscode',
                                       'open in vs code', 'open in chrome', 'open in paint', 'open in vlc',
                                       'edit in', 'open with']):
                # Pattern: "open [file] in [app]" or "edit [file] in [app]"
                match = re.search(r'(?:open|edit)\s+(.+?)\s+(?:in|with)\s+(.+)', cmd)
                if match:
                    file_name = match.group(1).strip().strip('"\'')
                    app_name = match.group(2).strip()
                    result = self.file_finder.open_file_by_name(file_name, app=app_name)
                    if result.get('success'):
                        return True, f"Opened {file_name} in {app_name}."
                    return True, f"Could not open '{file_name}' in {app_name}: {result.get('error', '')}"
                return True, "Say 'open [file name] in [app]'. Example: 'open resume in word'."

            # Open file by name (default app)
            if any(x in cmd for x in ['open file', 'open document', 'open my']):
                match = re.search(r'(?:open)\s+(?:file|document|my)\s+["\']?(.+?)["\']?$', cmd)
                if match:
                    file_name = match.group(1).strip()
                    result = self.file_finder.open_file_by_name(file_name)
                    if result.get('success'):
                        return True, f"Opened {file_name}."
                    return True, f"Could not find '{file_name}': {result.get('error', '')}"

            # Find recent files by type
            if any(x in cmd for x in ['recent documents', 'recent images', 'recent videos', 'recent code',
                                       'recent spreadsheets', 'recent presentations', 'recent audio',
                                       'recent photos', 'recent downloads']):
                type_match = re.search(r'recent\s+(\w+)', cmd)
                if type_match:
                    raw_type = type_match.group(1).strip().lower()
                    type_map = {
                        'documents': 'document', 'docs': 'document', 'photos': 'image',
                        'images': 'image', 'pictures': 'image', 'videos': 'video',
                        'spreadsheets': 'spreadsheet', 'presentations': 'presentation',
                        'code': 'code', 'scripts': 'code', 'audio': 'audio', 'music': 'audio',
                        'downloads': None,
                    }
                    file_type = type_map.get(raw_type, raw_type)
                    if file_type:
                        result = self.file_finder.find_recent_by_type(file_type, days=7)
                        if result.get('success') and result.get('files'):
                            file_list = '\n'.join([f"  - {f['name']} ({f['modified'][:10]})" for f in result['files'][:10]])
                            return True, f"Recent {raw_type} ({result['count']}):\n{file_list}"
                        return True, f"No recent {raw_type} found."

            # Find duplicates
            if any(x in cmd for x in ['find duplicates', 'duplicate files', 'find duplicate']):
                result = self.file_finder.find_duplicates()
                if result.get('success') and result.get('duplicates'):
                    dup_list = '\n'.join([f"  - {os.path.basename(d['files'][0])} ({d['count']} copies, {d['size']//1024}KB)"
                                         for d in result['duplicates'][:8]])
                    return True, f"Found {result['count']} duplicate groups:\n{dup_list}"
                return True, "No duplicate files found."

        # --- ADVANCED WINDOW CONTROL ---
        if self.win_ctrl:
            if any(x in cmd for x in ['alt tab', 'switch window', 'alt-tab', 'next window']):
                result = self.win_ctrl.alt_tab()
                return True, result.get('message', 'Switched windows')

            if any(x in cmd for x in ['show desktop', 'minimize all', 'minimize everything', 'hide all windows']):
                result = self.win_ctrl.minimize_all()
                return True, result.get('message', 'Desktop shown')

            if any(x in cmd for x in ['restore windows', 'restore all', 'show all windows', 'unhide windows']):
                result = self.win_ctrl.restore_all()
                return True, result.get('message', 'Windows restored')

            if any(x in cmd for x in ['center window', 'center this window']):
                result = self.win_ctrl.center_window()
                return True, result.get('message', 'Window centered')

            if any(x in cmd for x in ['always on top', 'pin window', 'keep on top', 'stay on top']):
                result = self.win_ctrl.set_always_on_top(True)
                return True, result.get('message', 'Window pinned on top')

            if any(x in cmd for x in ['unpin window', 'remove on top', 'stop on top', 'not on top']):
                result = self.win_ctrl.set_always_on_top(False)
                return True, result.get('message', 'Window unpinned')

            if any(x in cmd for x in ['close this window', 'close window', 'close active window']):
                result = self.win_ctrl.close_active_window()
                return True, result.get('message', 'Window closed')

            if any(x in cmd for x in ['fullscreen', 'full screen', 'toggle fullscreen']):
                result = self.win_ctrl.fullscreen_toggle()
                return True, result.get('message', 'Toggled fullscreen')

            if any(x in cmd for x in ['window info', 'active window', 'what window', 'which window']):
                result = self.win_ctrl.get_active_window_info()
                if result.get('success'):
                    return True, (f"Active window: {result.get('title', 'Unknown')}\n"
                                  f"  Size: {result['size']['width']}x{result['size']['height']}\n"
                                  f"  Position: ({result['position']['x']}, {result['position']['y']})")
                return True, "Could not get window info."

            if 'resize window' in cmd:
                match = re.search(r'resize window\s+(?:to\s+)?(\d+)\s*[x×]\s*(\d+)', cmd)
                if match:
                    w, h = int(match.group(1)), int(match.group(2))
                    result = self.win_ctrl.resize_window(w, h)
                    return True, result.get('message', f'Resized to {w}x{h}')
                return True, "Specify size: 'resize window to 800x600'."

            if 'move window' in cmd:
                match = re.search(r'move window\s+(?:to\s+)?(\d+)\s*,\s*(\d+)', cmd)
                if match:
                    x, y = int(match.group(1)), int(match.group(2))
                    result = self.win_ctrl.move_window(x, y)
                    return True, result.get('message', f'Moved to ({x},{y})')
                return True, "Specify position: 'move window to 100,100'."

            if any(x in cmd for x in ['snap top left', 'snap top-left', 'window top left']):
                return True, self.win_ctrl.snap_window_quarter('top-left').get('message', 'Snapped')
            if any(x in cmd for x in ['snap top right', 'snap top-right', 'window top right']):
                return True, self.win_ctrl.snap_window_quarter('top-right').get('message', 'Snapped')
            if any(x in cmd for x in ['snap bottom left', 'snap bottom-left', 'window bottom left']):
                return True, self.win_ctrl.snap_window_quarter('bottom-left').get('message', 'Snapped')
            if any(x in cmd for x in ['snap bottom right', 'snap bottom-right', 'window bottom right']):
                return True, self.win_ctrl.snap_window_quarter('bottom-right').get('message', 'Snapped')

        # --- SMART BROWSER CONTROL ---
        if self.smart_browser:
            # Search on specific engines
            if any(x in cmd for x in ['search youtube for', 'search on youtube', 'youtube search']):
                match = re.search(r'(?:search youtube for|search on youtube|youtube search)\s+(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'youtube')
                    return True, result.get('message', f'Searching YouTube for {query}')

            if any(x in cmd for x in ['search amazon for', 'search on amazon', 'amazon search',
                                       'find on amazon', 'buy on amazon']):
                match = re.search(r'(?:search|find|buy)\s+(?:on\s+)?amazon\s+(?:for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'amazon')
                    return True, result.get('message', f'Searching Amazon for {query}')

            if any(x in cmd for x in ['search flipkart', 'find on flipkart', 'flipkart search']):
                match = re.search(r'(?:search|find)\s+(?:on\s+)?flipkart\s+(?:for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'flipkart')
                    return True, result.get('message', f'Searching Flipkart for {query}')

            if any(x in cmd for x in ['search github for', 'search on github', 'find on github', 'github search']):
                match = re.search(r'(?:search|find)\s+(?:on\s+)?github\s+(?:for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'github')
                    return True, result.get('message', f'Searching GitHub for {query}')

            if any(x in cmd for x in ['search maps for', 'search on maps', 'find on maps', 'show on map', 'directions to']):
                match = re.search(r'(?:search maps for|search on maps|find on maps|show on map|directions to)\s+(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'maps')
                    return True, result.get('message', f'Showing {query} on Maps')

            if any(x in cmd for x in ['search images', 'find images of', 'image search', 'google images']):
                match = re.search(r'(?:search images|find images of|image search|google images)\s+(?:of\s+|for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'images')
                    return True, result.get('message', f'Searching images for {query}')

            if any(x in cmd for x in ['search news', 'find news about', 'news about', 'latest news']):
                match = re.search(r'(?:search news|find news about|news about|latest news)\s+(?:about\s+|on\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'news')
                    return True, result.get('message', f'Searching news for {query}')

            if any(x in cmd for x in ['search wikipedia', 'wiki', 'look up on wikipedia']):
                match = re.search(r'(?:search wikipedia|wiki|look up on wikipedia)\s+(?:for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'wikipedia')
                    return True, result.get('message', f'Searching Wikipedia for {query}')

            if any(x in cmd for x in ['search stackoverflow', 'stackoverflow', 'find on stackoverflow']):
                match = re.search(r'(?:search stackoverflow|stackoverflow|find on stackoverflow)\s+(?:for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.smart_browser.search_web(query, 'stackoverflow')
                    return True, result.get('message', f'Searching StackOverflow for {query}')

            # Incognito mode
            if any(x in cmd for x in ['incognito', 'private browsing', 'private window', 'incognito mode']):
                url_match = re.search(r'(?:incognito|private)\s+(?:mode\s+)?(?:with\s+|open\s+)?(\S+)', cmd)
                url = url_match.group(1) if url_match and '.' in url_match.group(1) else None
                result = self.smart_browser.open_incognito(url)
                return True, result.get('message', 'Opened incognito')

            # Read page content
            if any(x in cmd for x in ['read this page', 'read page', 'read page content', 'page text',
                                       'what does this page say', 'read website']):
                result = self.smart_browser.read_page_text()
                if result.get('success'):
                    text = result.get('text', '')[:500]
                    return True, f"Page content ({result.get('length', 0)} chars):\n{text}..."
                return True, "Could not read page content."

            # Find in page
            if any(x in cmd for x in ['find in page', 'find on page', 'search this page', 'ctrl f']):
                match = re.search(r'(?:find in page|find on page|search this page|ctrl f)\s+(?:for\s+)?(.+)', cmd)
                if match:
                    text = match.group(1).strip()
                    result = self.smart_browser.find_in_page(text)
                    return True, result.get('message', f'Searching for {text}')
                return True, "What should I find? Say 'find in page [text]'."

            # Zoom
            if any(x in cmd for x in ['zoom in', 'make bigger', 'increase zoom']):
                result = self.smart_browser.zoom_in()
                return True, result.get('message', 'Zoomed in')

            if any(x in cmd for x in ['zoom out', 'make smaller', 'decrease zoom']):
                result = self.smart_browser.zoom_out()
                return True, result.get('message', 'Zoomed out')

            if any(x in cmd for x in ['reset zoom', 'zoom 100', 'normal zoom', 'default zoom']):
                result = self.smart_browser.reset_zoom()
                return True, result.get('message', 'Zoom reset')

            # Bookmark
            if any(x in cmd for x in ['bookmark this', 'bookmark page', 'save bookmark', 'add bookmark']):
                result = self.smart_browser.bookmark_page()
                return True, result.get('message', 'Bookmark dialog opened')

            # Print
            if any(x in cmd for x in ['print this page', 'print page', 'print this']):
                result = self.smart_browser.print_page()
                return True, result.get('message', 'Print dialog opened')

            # Save page
            if any(x in cmd for x in ['save this page', 'save page', 'save website']):
                result = self.smart_browser.save_page()
                return True, result.get('message', 'Save dialog opened')

            # Clear browsing data
            if any(x in cmd for x in ['clear browsing data', 'clear browser history', 'clear browser cache', 'delete history']):
                result = self.smart_browser.clear_browsing_data()
                return True, result.get('message', 'Clear browsing data dialog opened')

            # Dev tools
            if any(x in cmd for x in ['developer tools', 'dev tools', 'open console', 'inspect element']):
                result = self.smart_browser.open_dev_tools()
                return True, result.get('message', 'Developer tools opened')

        # === v9.0 GUI AUTOMATOR ===
        if self.gui_automator:
            # Take screenshot
            if any(x in cmd for x in ['take screenshot', 'screenshot', 'capture screen', 'screen capture']):
                result = self.gui_automator.screenshot()
                if result.get('success'):
                    return True, f"📸 Screenshot saved: {result.get('path', 'screenshots/')}"
                return True, f"Screenshot failed: {result.get('error', 'Unknown error')}"
            
            # Read screen text (OCR)
            if any(x in cmd for x in ['read screen', 'read my screen', "what's on screen", 'screen text', 'read the screen', 'what is on my screen']):
                result = self.gui_automator.extract_text_from_screen()
                if result.get('success'):
                    text = result.get('text', '')[:500]
                    return True, f"Screen text:\n{text}"
                return True, f"Couldn't read screen: {result.get('error', 'OCR not available')}"
            
            # Click on text
            if 'click on' in cmd:
                match = re.search(r'click on\s+["\']?(.+?)["\']?$', cmd)
                if match:
                    target_text = match.group(1).strip()
                    result = self.gui_automator.click_on_text(target_text)
                    if result.get('success'):
                        return True, f"✅ Clicked on '{target_text}'"
                    return True, f"Couldn't find '{target_text}' on screen"
            
            # Type text
            if cmd.startswith('type '):
                text_to_type = cmd[5:].strip().strip('"\'')
                result = self.gui_automator.type_text(text_to_type)
                if result.get('success'):
                    return True, f"✅ Typed {len(text_to_type)} characters"
                return True, "Couldn't type text"
            
            # Hotkeys
            if any(x in cmd for x in ['press ctrl', 'press alt', 'hotkey']):
                if 'ctrl c' in cmd or 'ctrl+c' in cmd or 'copy' in cmd:
                    result = self.gui_automator.copy()
                    return True, "✅ Copied" if result.get('success') else "Copy failed"
                if 'ctrl v' in cmd or 'ctrl+v' in cmd or 'paste' in cmd:
                    result = self.gui_automator.paste()
                    return True, "✅ Pasted" if result.get('success') else "Paste failed"
                if 'ctrl a' in cmd or 'ctrl+a' in cmd or 'select all' in cmd:
                    result = self.gui_automator.select_all()
                    return True, "✅ Selected all" if result.get('success') else "Select all failed"
                if 'ctrl s' in cmd or 'ctrl+s' in cmd:
                    result = self.gui_automator.save()
                    return True, "✅ Saved" if result.get('success') else "Save failed"
                if 'ctrl z' in cmd or 'ctrl+z' in cmd:
                    result = self.gui_automator.undo()
                    return True, "✅ Undone" if result.get('success') else "Undo failed"
            
            # Scroll
            if any(x in cmd for x in ['scroll up', 'scroll down']):
                direction = 'up' if 'up' in cmd else 'down'
                result = self.gui_automator.scroll(direction, 3)
                if result.get('success'):
                    return True, f"✅ Scrolled {direction}"
                return True, "Couldn't scroll"
        
        # === v9.0 BROWSER TAB CONTROLLER ===
        if self.browser_tabs:
            # Open new tab
            if any(x in cmd for x in ['new tab', 'open tab', 'open new tab']):
                match = re.search(r'(?:new tab|open tab|open new tab)\s*(?:with|to|for)?\s*(.+)?', cmd)
                url = match.group(1).strip() if match and match.group(1) else None
                result = self.browser_tabs.open_tab(url)
                if result.get('success'):
                    return True, f"✅ Opened new tab" + (f": {url}" if url else "")
                return True, "Couldn't open new tab"
            
            # Close tab
            if any(x in cmd for x in ['close tab', 'close this tab']):
                result = self.browser_tabs.close_tab()
                return True, "✅ Tab closed" if result.get('success') else "Couldn't close tab"
            
            # Switch tabs
            if any(x in cmd for x in ['next tab', 'switch tab', 'previous tab', 'prev tab']):
                direction = 'prev' if 'prev' in cmd else 'next'
                result = self.browser_tabs.switch_tab(direction)
                return True, f"✅ Switched to {direction} tab" if result.get('success') else "Couldn't switch tab"
            
            # Go to tab number
            if 'tab' in cmd and any(str(i) in cmd for i in range(1, 10)):
                match = re.search(r'tab\s*(\d)', cmd)
                if match:
                    tab_num = int(match.group(1))
                    result = self.browser_tabs.switch_to_tab_number(tab_num)
                    return True, f"✅ Switched to tab {tab_num}" if result.get('success') else "Couldn't switch"
            
            # Navigate to URL
            if any(x in cmd for x in ['go to', 'navigate to', 'open website']):
                match = re.search(r'(?:go to|navigate to|open website)\s+(.+)', cmd)
                if match:
                    url = match.group(1).strip()
                    result = self.browser_tabs.navigate_to(url)
                    return True, f"✅ Navigated to {url}" if result.get('success') else f"Couldn't navigate"
            
            # Refresh
            if any(x in cmd for x in ['refresh', 'reload', 'refresh page', 'reload page']):
                hard = 'hard' in cmd or 'force' in cmd
                result = self.browser_tabs.refresh_tab(hard)
                return True, "✅ Page refreshed" if result.get('success') else "Couldn't refresh"
            
            # Back/Forward
            if 'go back' in cmd or 'back' == cmd:
                result = self.browser_tabs.go_back()
                return True, "✅ Went back" if result.get('success') else "Couldn't go back"
            
            if 'go forward' in cmd or 'forward' == cmd:
                result = self.browser_tabs.go_forward()
                return True, "✅ Went forward" if result.get('success') else "Couldn't go forward"
            
            # YouTube search
            if 'youtube' in cmd and 'search' in cmd:
                match = re.search(r'youtube\s+(?:search\s+)?(?:for\s+)?(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.browser_tabs.youtube_search(query)
                    return True, f"✅ Searching YouTube for: {query}" if result.get('success') else "Couldn't search"
            
            # Incognito/Private
            if any(x in cmd for x in ['incognito', 'private mode', 'private browsing']):
                result = self.browser_tabs.open_incognito()
                return True, "Opened private browsing" if result.get('success') else "Couldn't open"

        # === COMET-STYLE YOUTUBE SUMMARIZATION ===
        # (Check YouTube BEFORE generic page summarizer so YouTube URLs are handled properly)
        if self.youtube_summarizer:
            # Summarize YouTube video
            is_youtube = 'youtube' in cmd or 'youtu.be' in cmd
            is_summarize = any(x in cmd for x in ['summarize', 'summarise', 'summary', 'explain video', 'key points'])

            if is_youtube and is_summarize:
                # Extract URL from original command (not lowercased cmd) to preserve video ID case
                url_match = re.search(r'(https?://\S+)', command, re.IGNORECASE)
                if url_match:
                    url = url_match.group(1)
                    mode = "timestamps" if 'timestamp' in cmd else "key_points"
                    summary = self.youtube_summarizer.summarize(url, mode=mode)
                    if summary.error:
                        return True, f"Could not summarize video: {summary.error}"
                    response = f"Video: {summary.title}\n"
                    if summary.channel:
                        response += f"Channel: {summary.channel}\n\n"
                    if summary.key_points:
                        response += "Key Points:\n"
                        response += '\n'.join(f"  - {p}" for p in summary.key_points)
                    elif summary.detailed_summary:
                        response += summary.detailed_summary[:600]
                    if summary.timestamps:
                        response += "\n\nTimestamps:\n"
                        response += '\n'.join(f"  [{t['time']}] {t['topic']}" for t in summary.timestamps[:10])
                    return True, response

            # Just "summarize this youtube video" (extract URL from recent context)
            if is_youtube and any(x in cmd for x in ['summarize', 'what is this video about']):
                return True, "Paste the YouTube URL: 'summarize https://youtube.com/watch?v=...'"

        # === COMET-STYLE PAGE SUMMARIZATION ===
        if self.page_summarizer:
            # Summarize a URL (skip YouTube URLs - handled above)
            if any(x in cmd for x in ['summarize', 'summarise', 'summary of', 'tldr']):
                # Extract URL from original command to preserve case
                url_match = re.search(r'(https?://\S+)', command, re.IGNORECASE)
                if url_match:
                    url = url_match.group(1)
                    # Skip YouTube URLs (handled by YouTube summarizer above)
                    if 'youtube.com' not in url and 'youtu.be' not in url:
                        mode = "tldr" if 'tldr' in cmd else "key_points"
                        summary = self.page_summarizer.summarize_url(url, mode=mode)
                        if summary.key_points:
                            points = '\n'.join(f"  - {p}" for p in summary.key_points)
                            return True, f"Summary of {summary.title}:\n\n{points}"
                        elif summary.tldr:
                            return True, f"TL;DR: {summary.tldr}"
                        else:
                            return True, f"Summary: {summary.detailed_summary[:500]}"

                # "summarize this page" without URL - placeholder for active tab
                if any(x in cmd for x in ['this page', 'this article', 'current page']):
                    return True, "To summarize a page, paste the URL: 'summarize https://example.com/article'"

            # Compare pages
            if any(x in cmd for x in ['compare pages', 'compare these', 'compare urls', 'compare websites']):
                urls = re.findall(r'(https?://\S+)', command, re.IGNORECASE)
                if len(urls) >= 2:
                    result = self.page_summarizer.compare_pages(urls)
                    return True, result
                return True, "Provide 2+ URLs to compare: 'compare https://url1.com https://url2.com'"

        # === v9.0 MULTI-TAB ORCHESTRATOR ===
        if self.multi_tab:
            # Open workspace
            if any(x in cmd for x in ['open workspace', 'workspace', 'open research', 'open development', 'open social', 'open productivity']):
                for ws in ['research', 'development', 'social', 'productivity', 'entertainment']:
                    if ws in cmd:
                        result = self.multi_tab.open_workspace(ws)
                        if result.get('success'):
                            return True, f"✅ Opened {ws} workspace with {result.get('tabs_opened', 0)} tabs"
                        return True, f"Couldn't open {ws} workspace"
                return True, "Available workspaces: research, development, social, productivity, entertainment"
            
            # Research topic
            if 'research' in cmd and any(x in cmd for x in ['topic', 'about', 'on']):
                match = re.search(r'research\s+(?:topic|about|on)?\s*(.+)', cmd)
                if match:
                    topic = match.group(1).strip()
                    result = self.multi_tab.research_topic(topic)
                    return True, f"✅ Opened research tabs for '{topic}'" if result.get('success') else "Couldn't research"
            
            # Compare products
            if 'compare' in cmd:
                match = re.search(r'compare\s+(.+)', cmd)
                if match:
                    product = match.group(1).strip()
                    result = self.multi_tab.compare_products(product)
                    return True, f"✅ Opened comparison tabs for '{product}'" if result.get('success') else "Couldn't compare"
            
            # List workspaces
            if any(x in cmd for x in ['list workspaces', 'show workspaces', 'available workspaces']):
                result = self.multi_tab.list_workspaces()
                if result.get('success'):
                    ws_list = ', '.join([w['name'] for w in result['workspaces']])
                    return True, f"Available workspaces: {ws_list}"
            
            # Save session
            if 'save session' in cmd:
                match = re.search(r'save session\s+(?:as\s+)?(.+)', cmd)
                name = match.group(1).strip() if match else f"session_{datetime.now().strftime('%H%M')}"
                result = self.multi_tab.save_session(name)
                return True, f"✅ Session saved as '{name}'" if result.get('success') else "Couldn't save session"
            
            # Load session
            if 'load session' in cmd:
                match = re.search(r'load session\s+(.+)', cmd)
                if match:
                    name = match.group(1).strip()
                    result = self.multi_tab.load_session(name)
                    return True, f"✅ Session '{name}' loaded" if result.get('success') else f"Couldn't load session '{name}'"
        
        # === v9.0 GMAIL CONTROLLER ===
        if self.gmail and self.gmail.is_authenticated():
            # Check email/inbox
            if any(x in cmd for x in ['check email', 'check inbox', 'check mail', 'new emails', 'unread emails']):
                if 'unread' in cmd:
                    result = self.gmail.get_unread_count()
                    if result.get('success'):
                        return True, f"📧 You have {result['unread_count']} unread emails"
                else:
                    result = self.gmail.get_inbox(5, unread_only=True)
                    if result.get('success'):
                        if result['messages']:
                            email_list = '\n'.join([f"  • {m['sender'][:30]}: {m['subject'][:40]}" for m in result['messages'][:5]])
                            return True, f"📧 Recent emails:\n{email_list}"
                        return True, "No unread emails"
                return True, "Couldn't check emails"
            
            # Send email
            if any(x in cmd for x in ['send email', 'compose email', 'email to']):
                match = re.search(r'(?:send email|email)\s+to\s+(\S+)\s+(?:subject|about)\s+(.+)', cmd)
                if match:
                    to = match.group(1)
                    subject = match.group(2)
                    result = self.gmail.create_draft(to, subject, "")
                    return True, f"✅ Draft created for {to}" if result.get('success') else "Couldn't create draft"
                return True, "Say 'send email to [address] subject [topic]'"
            
            # Search emails
            if 'search email' in cmd or 'find email' in cmd:
                match = re.search(r'(?:search|find)\s+emails?\s+(?:for|from|about)?\s*(.+)', cmd)
                if match:
                    query = match.group(1).strip()
                    result = self.gmail.search_emails(query, 5)
                    if result.get('success') and result['messages']:
                        email_list = '\n'.join([f"  • {m['subject'][:50]}" for m in result['messages']])
                        return True, f"📧 Found {result['count']} emails:\n{email_list}"
                    return True, f"No emails found for '{query}'"
        
        # === v9.0 CALENDAR CONTROLLER ===
        if self.calendar and self.calendar.is_authenticated():
            # Today's events
            if any(x in cmd for x in ["today's events", "today's schedule", "what's on today", "events today"]):
                result = self.calendar.get_today_events()
                if result.get('success'):
                    if result['events']:
                        event_list = '\n'.join([f"  • {e['summary']} at {e['start'][:16]}" for e in result['events']])
                        return True, f"📅 Today's events:\n{event_list}"
                    return True, "No events scheduled for today"
                return True, "Couldn't get today's events"
            
            # Tomorrow's events
            if any(x in cmd for x in ["tomorrow's events", "tomorrow's schedule", "what's on tomorrow"]):
                result = self.calendar.get_tomorrow_events()
                if result.get('success'):
                    if result['events']:
                        event_list = '\n'.join([f"  • {e['summary']}" for e in result['events']])
                        return True, f"📅 Tomorrow's events:\n{event_list}"
                    return True, "No events scheduled for tomorrow"
            
            # This week
            if any(x in cmd for x in ["this week's events", "week's schedule", "events this week"]):
                result = self.calendar.get_week_events()
                if result.get('success'):
                    if result['events']:
                        event_list = '\n'.join([f"  • {e['summary']}: {e['start'][:10]}" for e in result['events'][:10]])
                        return True, f"📅 This week ({result['count']} events):\n{event_list}"
                    return True, "No events this week"
            
            # Upcoming events
            if any(x in cmd for x in ['upcoming events', 'next events', 'schedule', 'calendar']):
                result = self.calendar.get_upcoming_events(5)
                if result.get('success'):
                    if result['events']:
                        event_list = '\n'.join([f"  • {e['summary']}: {e['start'][:16]}" for e in result['events']])
                        return True, f"📅 Upcoming events:\n{event_list}"
                    return True, "No upcoming events"
            
            # Quick add event
            if any(x in cmd for x in ['add event', 'create event', 'schedule event', 'new event']):
                match = re.search(r'(?:add|create|schedule|new)\s+event\s+(.+)', cmd)
                if match:
                    event_text = match.group(1).strip()
                    result = self.calendar.quick_add(event_text)
                    if result.get('success'):
                        return True, f"✅ Event created: {result.get('summary', event_text)}"
                    return True, f"Couldn't create event: {result.get('error', '')}"
                return True, "Say 'add event [description]' (e.g., 'add event meeting tomorrow at 3pm')"
            
            # Create meeting
            if any(x in cmd for x in ['schedule meeting', 'create meeting', 'set up meeting']):
                match = re.search(r'(?:schedule|create|set up)\s+meeting\s+(?:with\s+)?(.+)', cmd)
                if match:
                    meeting_text = match.group(1).strip()
                    result = self.calendar.quick_add(f"Meeting {meeting_text}")
                    return True, f"✅ Meeting scheduled" if result.get('success') else "Couldn't schedule meeting"
        
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
        
        # === VOLUME CONTROL ===
        if self.system:
            if any(x in cmd for x in ['set volume', 'volume to', 'change volume', 'make volume']):
                match = re.search(r'(\d+)', cmd)
                if match:
                    level = int(match.group(1))
                    result = self.system.set_volume(level)
                    if result.get('success'):
                        return True, f"{LadaPersonality.get_acknowledgment()} Volume set to {level}%."
                    return True, f"I couldn't change the volume. {result.get('error', '')}"
            
            if 'mute' in cmd:
                self.system.set_volume(0)
                return True, "Volume muted."
            
            if 'unmute' in cmd or 'full volume' in cmd or 'max volume' in cmd:
                self.system.set_volume(100)
                return True, "Volume set to maximum."
            
            if any(x in cmd for x in ['volume up', 'increase volume', 'louder']):
                vol = self.system.get_volume()
                new_vol = min(100, vol.get('volume', 50) + 10)
                self.system.set_volume(new_vol)
                return True, f"Volume increased to {new_vol}%."
            
            if any(x in cmd for x in ['volume down', 'decrease volume', 'quieter', 'lower volume']):
                vol = self.system.get_volume()
                new_vol = max(0, vol.get('volume', 50) - 10)
                self.system.set_volume(new_vol)
                return True, f"Volume decreased to {new_vol}%."
            
            if any(x in cmd for x in ['what is the volume', 'current volume', 'volume level']):
                vol = self.system.get_volume()
                return True, f"Volume is at {vol.get('volume', 'unknown')}%."
            
            # === BRIGHTNESS ===
            if any(x in cmd for x in ['set brightness', 'brightness to', 'change brightness']):
                match = re.search(r'(\d+)', cmd)
                if match:
                    level = int(match.group(1))
                    result = self.system.set_brightness(level)
                    if result.get('success'):
                        return True, f"{LadaPersonality.get_acknowledgment()} Brightness set to {level}%."
                    return True, f"I couldn't change the brightness. {result.get('error', '')}"

            if any(x in cmd for x in ['brightness up', 'increase brightness', 'brighter']):
                current = self.system.get_brightness()
                new_level = min(100, current.get('brightness', 50) + 20)
                self.system.set_brightness(new_level)
                return True, f"Brightness increased to {new_level}%."

            if any(x in cmd for x in ['brightness down', 'decrease brightness', 'dimmer', 'dim screen', 'lower brightness']):
                current = self.system.get_brightness()
                new_level = max(0, current.get('brightness', 50) - 20)
                self.system.set_brightness(new_level)
                return True, f"Brightness decreased to {new_level}%."

            if any(x in cmd for x in ['what is the brightness', 'current brightness', 'brightness level']):
                result = self.system.get_brightness()
                return True, f"Brightness is at {result.get('brightness', 'unknown')}%."

            # === WIFI MANAGEMENT ===
            if any(x in cmd for x in ['list wifi', 'available wifi', 'scan wifi', 'show wifi', 'wifi networks', 'what wifi']):
                result = self.system.list_wifi_networks()
                if result.get('success') and result.get('networks'):
                    nets = result['networks'][:10]
                    net_list = '\n'.join([f"  - {n.get('ssid', 'Unknown')}" for n in nets])
                    return True, f"Found {result['count']} WiFi networks:\n{net_list}"
                return True, "No WiFi networks found."

            if any(x in cmd for x in ['connect wifi', 'connect to wifi', 'join wifi', 'connect to network']):
                match = re.search(r'(?:connect(?:\s+to)?|join)\s+(?:wifi|network)\s+(.+)', cmd)
                if match:
                    ssid = match.group(1).strip().strip('"\'')
                    result = self.system.connect_wifi(ssid)
                    if result.get('success'):
                        return True, f"Connected to {ssid}."
                    return True, f"Could not connect to {ssid}: {result.get('error', 'Unknown error')}"
                return True, "Which WiFi network? Say 'connect to wifi [network name]'."

            if any(x in cmd for x in ['disconnect wifi', 'turn off wifi', 'disable wifi', 'wifi off']):
                result = self.system.disconnect_wifi()
                return True, "Disconnected from WiFi." if result.get('success') else f"Could not disconnect: {result.get('error', '')}"

            if any(x in cmd for x in ['wifi status', 'am i connected', 'network status', 'connection status', 'what network', 'which wifi']):
                result = self.system.get_network_status()
                if result.get('success'):
                    if result.get('connected'):
                        ssid = result.get('ssid', 'Unknown')
                        signal = result.get('signal', 'N/A')
                        ip = result.get('ip_address', 'N/A')
                        return True, f"Connected to '{ssid}', Signal: {signal}, IP: {ip}"
                    return True, "Not connected to any WiFi network."
                return True, "Could not get network status."

            # === BLUETOOTH ===
            if any(x in cmd for x in ['turn on bluetooth', 'enable bluetooth', 'bluetooth on']):
                result = self.system.set_bluetooth(True)
                return True, result.get('message', 'Bluetooth enabled') if result.get('success') else f"Could not enable Bluetooth: {result.get('error', '')}"

            if any(x in cmd for x in ['turn off bluetooth', 'disable bluetooth', 'bluetooth off']):
                result = self.system.set_bluetooth(False)
                return True, result.get('message', 'Bluetooth disabled') if result.get('success') else f"Could not disable Bluetooth: {result.get('error', '')}"

            if any(x in cmd for x in ['bluetooth status', 'is bluetooth on', 'bluetooth state']):
                result = self.system.get_bluetooth_status()
                return True, result.get('message', 'Unknown') if result.get('success') else "Could not check Bluetooth status."

            if any(x in cmd for x in ['list bluetooth', 'bluetooth devices', 'paired devices', 'show bluetooth']):
                result = self.system.list_bluetooth_devices()
                if result.get('success') and result.get('devices'):
                    dev_list = '\n'.join([f"  - {d['name']} ({d['status']})" for d in result['devices']])
                    return True, f"Bluetooth devices ({result['count']}):\n{dev_list}"
                return True, "No Bluetooth devices found."

            # === AIRPLANE MODE ===
            if any(x in cmd for x in ['airplane mode on', 'enable airplane', 'turn on airplane', 'flight mode on']):
                result = self.system.set_airplane_mode(True)
                return True, result.get('message', 'Airplane mode on') if result.get('success') else f"Could not enable airplane mode: {result.get('error', '')}"

            if any(x in cmd for x in ['airplane mode off', 'disable airplane', 'turn off airplane', 'flight mode off']):
                result = self.system.set_airplane_mode(False)
                return True, result.get('message', 'Airplane mode off') if result.get('success') else f"Could not disable airplane mode: {result.get('error', '')}"

            # === NIGHT LIGHT / BLUE LIGHT ===
            if any(x in cmd for x in ['turn on night light', 'enable night light', 'night light on', 'enable blue light filter', 'blue light on', 'warm screen']):
                result = self.system.set_night_light(True)
                return True, result.get('message', 'Night light enabled')

            if any(x in cmd for x in ['turn off night light', 'disable night light', 'night light off', 'disable blue light', 'blue light off']):
                result = self.system.set_night_light(False)
                return True, result.get('message', 'Night light disabled')

            if any(x in cmd for x in ['night light status', 'is night light on']):
                result = self.system.get_night_light_status()
                return True, result.get('message', 'Unknown') if result.get('success') else "Could not check night light status."

            # === HOTSPOT ===
            if any(x in cmd for x in ['turn on hotspot', 'enable hotspot', 'hotspot on', 'start hotspot', 'mobile hotspot on']):
                result = self.system.set_hotspot(True)
                return True, result.get('message', 'Hotspot enabled')

            if any(x in cmd for x in ['turn off hotspot', 'disable hotspot', 'hotspot off', 'stop hotspot', 'mobile hotspot off']):
                result = self.system.set_hotspot(False)
                return True, result.get('message', 'Hotspot disabled')

            # === AUDIO DEVICES ===
            if any(x in cmd for x in ['list audio devices', 'show audio devices', 'what speakers', 'audio output', 'sound devices']):
                result = self.system.list_audio_devices()
                if result.get('success') and result.get('devices'):
                    dev_list = '\n'.join([f"  - {d.get('name', 'Unknown')}" for d in result['devices']])
                    return True, f"Audio devices ({result['count']}):\n{dev_list}"
                return True, "Could not list audio devices."

            if any(x in cmd for x in ['switch audio', 'switch speaker', 'switch to speaker', 'switch to headphone', 'change audio output', 'use speaker', 'use headphone']):
                if 'speaker' in cmd:
                    result = self.system.set_audio_device('Speaker')
                elif 'headphone' in cmd or 'headset' in cmd:
                    result = self.system.set_audio_device('Headphone')
                else:
                    match = re.search(r'(?:switch|change)\s+(?:audio|speaker|output)\s+(?:to\s+)?(.+)', cmd)
                    if match:
                        result = self.system.set_audio_device(match.group(1).strip())
                    else:
                        return True, "Which audio device? Say 'switch audio to [device name]'."
                return True, result.get('message', 'Audio switched') if result.get('success') else f"Could not switch: {result.get('error', '')}"

            # === DARK/LIGHT THEME ===
            if any(x in cmd for x in ['dark mode', 'enable dark mode', 'turn on dark mode', 'switch to dark', 'dark theme']):
                result = self.system.set_dark_mode()
                return True, f"{LadaPersonality.get_acknowledgment()} Dark mode enabled." if result.get('success') else f"Could not change theme: {result.get('error', '')}"

            if any(x in cmd for x in ['light mode', 'enable light mode', 'turn on light mode', 'switch to light', 'light theme']):
                result = self.system.set_light_mode()
                return True, f"{LadaPersonality.get_acknowledgment()} Light mode enabled." if result.get('success') else f"Could not change theme: {result.get('error', '')}"

            if any(x in cmd for x in ['toggle theme', 'switch theme', 'change theme']):
                result = self.system.toggle_theme()
                if result.get('success'):
                    return True, f"Theme switched to {result.get('theme', 'unknown')} mode."
                return True, f"Could not toggle theme: {result.get('error', '')}"

            if any(x in cmd for x in ['what theme', 'current theme', 'which theme', 'theme status']):
                result = self.system.get_system_theme()
                if result.get('success'):
                    return True, f"System theme: {result.get('theme', 'unknown')}, Apps: {result.get('apps_theme', 'unknown')}."
                return True, "Could not get theme information."

            # === VIRTUAL DESKTOPS ===
            if any(x in cmd for x in ['new desktop', 'create desktop', 'add desktop', 'new virtual desktop']):
                result = self.system.create_virtual_desktop()
                return True, result.get('message', 'Created new virtual desktop')

            if any(x in cmd for x in ['next desktop', 'switch desktop right', 'desktop right']):
                result = self.system.switch_virtual_desktop('right')
                return True, result.get('message', 'Switched to next desktop')

            if any(x in cmd for x in ['previous desktop', 'switch desktop left', 'desktop left']):
                result = self.system.switch_virtual_desktop('left')
                return True, result.get('message', 'Switched to previous desktop')

            if any(x in cmd for x in ['close desktop', 'close virtual desktop', 'remove desktop']):
                result = self.system.close_virtual_desktop()
                return True, result.get('message', 'Closed virtual desktop')

            if any(x in cmd for x in ['task view', 'show desktops', 'show all desktops', 'all desktops']):
                result = self.system.show_task_view()
                return True, result.get('message', 'Opened Task View')

            # === TOUCHPAD ===
            if any(x in cmd for x in ['enable touchpad', 'turn on touchpad', 'touchpad on']):
                result = self.system.set_touchpad(True)
                return True, result.get('message', 'Touchpad enabled') if result.get('success') else "Could not enable touchpad."

            if any(x in cmd for x in ['disable touchpad', 'turn off touchpad', 'touchpad off']):
                result = self.system.set_touchpad(False)
                return True, result.get('message', 'Touchpad disabled') if result.get('success') else "Could not disable touchpad."

            # === DISPLAY / PROJECTION ===
            if any(x in cmd for x in ['extend display', 'extend screen', 'dual monitor', 'extend monitor']):
                result = self.system.set_display_mode('extend')
                return True, result.get('message', 'Display extended')

            if any(x in cmd for x in ['duplicate display', 'mirror display', 'mirror screen', 'duplicate screen']):
                result = self.system.set_display_mode('duplicate')
                return True, result.get('message', 'Display mirrored')

            if any(x in cmd for x in ['pc screen only', 'laptop screen only', 'disconnect display', 'disconnect projector']):
                result = self.system.set_display_mode('pc')
                return True, result.get('message', 'PC screen only')

            if any(x in cmd for x in ['second screen only', 'projector only', 'external display only']):
                result = self.system.set_display_mode('second')
                return True, result.get('message', 'Second screen only')

            # === CLIPBOARD ===
            if any(x in cmd for x in ['clear clipboard', 'empty clipboard']):
                result = self.system.clear_clipboard()
                return True, result.get('message', 'Clipboard cleared')

            if any(x in cmd for x in ['clipboard history', 'show clipboard', 'open clipboard']):
                result = self.system.toggle_clipboard_history()
                return True, result.get('message', 'Opened clipboard history')

            if any(x in cmd for x in ['what is in clipboard', 'read clipboard', 'clipboard content']):
                result = self.system.get_clipboard_text()
                if result.get('success'):
                    text = result.get('text', '')[:200]
                    return True, f"Clipboard ({result.get('length', 0)} chars): {text}" if text else "Clipboard is empty."
                return True, "Could not read clipboard."

            # === POWER PLAN ===
            if any(x in cmd for x in ['power plan', 'current power plan', 'what power plan', 'which power plan']):
                result = self.system.get_power_plan()
                return True, f"Current power plan: {result.get('plan', 'Unknown')}" if result.get('success') else "Could not get power plan."

            if any(x in cmd for x in ['list power plans', 'available power plans', 'show power plans']):
                result = self.system.list_power_plans()
                if result.get('success') and result.get('plans'):
                    plan_list = '\n'.join([f"  {'*' if p['active'] else '-'} {p['name']}" for p in result['plans']])
                    return True, f"Power plans:\n{plan_list}"
                return True, "Could not list power plans."

            if any(x in cmd for x in ['high performance', 'performance mode', 'gaming mode', 'max performance']):
                result = self.system.set_power_plan('high performance')
                return True, result.get('message', 'Switched to high performance') if result.get('success') else f"Could not switch: {result.get('error', '')}"

            if any(x in cmd for x in ['power saver', 'power saving', 'battery saver mode', 'save battery', 'eco mode']):
                result = self.system.set_power_plan('power saver')
                return True, result.get('message', 'Switched to power saver') if result.get('success') else f"Could not switch: {result.get('error', '')}"

            if any(x in cmd for x in ['balanced mode', 'balanced power', 'normal power']):
                result = self.system.set_power_plan('balanced')
                return True, result.get('message', 'Switched to balanced') if result.get('success') else f"Could not switch: {result.get('error', '')}"

            # === SCREEN TIMEOUT ===
            if any(x in cmd for x in ['screen timeout', 'set screen timeout', 'display timeout']):
                match = re.search(r'(\d+)\s*(?:minutes?|mins?)', cmd)
                if match:
                    minutes = int(match.group(1))
                    result = self.system.set_screen_timeout(minutes)
                    return True, result.get('message', f'Screen timeout set to {minutes} minutes')
                if 'never' in cmd:
                    result = self.system.set_screen_timeout(0)
                    return True, "Screen timeout disabled (never turn off)."
                return True, "How many minutes? Say 'screen timeout 10 minutes' or 'screen timeout never'."

            # === PROCESS MANAGEMENT ===
            if any(x in cmd for x in ['list processes', 'running processes', 'show processes', 'what is running', 'top processes']):
                result = self.system.list_processes(limit=10)
                if result.get('success') and result.get('processes'):
                    proc_list = '\n'.join([f"  - {p['name']} (PID: {p['pid']}, Mem: {p['memory_mb']}%)" for p in result['processes'][:10]])
                    return True, f"Top processes ({result['total']}):\n{proc_list}"
                return True, "Could not list processes."

            if any(x in cmd for x in ['kill process', 'end process', 'force close', 'terminate process']):
                match = re.search(r'(?:kill|end|terminate|force close)\s+(?:process\s+)?(.+)', cmd)
                if match:
                    proc_name = match.group(1).strip()
                    result = self.system.kill_process(proc_name)
                    if result.get('success'):
                        return True, f"Killed {result.get('killed', 0)} instance(s) of {proc_name}."
                    return True, f"Process '{proc_name}' not found or could not be killed."
                return True, "Which process? Say 'kill process [name]'."

            # === CLEANUP / MAINTENANCE ===
            if any(x in cmd for x in ['clear temp', 'clean temp', 'delete temp files', 'clear temporary', 'clean up', 'clear cache']):
                result = self.system.clear_temp_files()
                if result.get('success'):
                    return True, f"Cleaned up! Deleted {result.get('deleted', 0)} files, freed {result.get('freed_mb', 0)} MB."
                return True, "Could not clear temp files."

            if any(x in cmd for x in ['empty recycle', 'clear recycle', 'empty trash', 'clear trash', 'empty bin']):
                result = self.system.empty_recycle_bin()
                return True, result.get('message', 'Recycle bin emptied') if result.get('success') else "Could not empty recycle bin."

            # === HIBERNATE / LOGOFF (via power_action) ===
            if any(x in cmd for x in ['hibernate', 'hibernation']):
                result = self.system.power_action('hibernate')
                return True, "Hibernating..." if result.get('success') else f"Could not hibernate: {result.get('error', '')}"

            if any(x in cmd for x in ['log off', 'logoff', 'sign out', 'log out', 'logout']):
                return self.request_confirmation('log you off', 'All unsaved work will be lost.')

            # === DO NOT DISTURB ===
            if any(x in cmd for x in ['do not disturb on', 'enable do not disturb', 'turn on dnd', 'dnd on', 'silence notifications']):
                result = self.system.set_do_not_disturb(True)
                return True, result.get('message', 'Do Not Disturb enabled')

            if any(x in cmd for x in ['do not disturb off', 'disable do not disturb', 'turn off dnd', 'dnd off', 'enable notifications']):
                result = self.system.set_do_not_disturb(False)
                return True, result.get('message', 'Do Not Disturb disabled')

            # === SCREEN RECORDING ===
            if any(x in cmd for x in ['start recording', 'record screen', 'screen record', 'start screen recording']):
                result = self.system.start_screen_recording()
                return True, result.get('message', 'Recording started')

            if any(x in cmd for x in ['stop recording', 'stop screen recording', 'end recording']):
                result = self.system.stop_screen_recording()
                return True, result.get('message', 'Recording stopped')

            # === STARTUP APPS ===
            if any(x in cmd for x in ['startup apps', 'list startup', 'show startup apps', 'what runs at startup']):
                result = self.system.list_startup_apps()
                if result.get('success') and result.get('apps'):
                    app_list = '\n'.join([f"  - {a['name']} ({a['scope']})" for a in result['apps'][:15]])
                    return True, f"Startup apps ({result['count']}):\n{app_list}"
                return True, "No startup apps found or could not list them."

            if any(x in cmd for x in ['remove from startup', 'disable startup', 'remove startup']):
                match = re.search(r'(?:remove|disable)\s+(?:from\s+)?startup\s+(?:app\s+)?(.+)', cmd)
                if match:
                    app_name = match.group(1).strip()
                    result = self.system.disable_startup_app(app_name)
                    return True, result.get('message', f'Removed {app_name} from startup') if result.get('success') else f"Could not remove: {result.get('error', '')}"
                return True, "Which app? Say 'remove from startup [app name]'."

            # === OPEN SETTINGS PAGES ===
            if any(x in cmd for x in ['open settings', 'open wifi settings', 'open bluetooth settings', 'open display settings',
                                       'open sound settings', 'open storage settings', 'open battery settings',
                                       'open update settings', 'open privacy settings', 'open power settings',
                                       'open accounts settings', 'open apps settings', 'open mouse settings',
                                       'open keyboard settings', 'open vpn settings', 'open about']):
                # Extract the settings page name
                page_match = re.search(r'open\s+(\w+)\s+settings', cmd)
                if page_match:
                    page = page_match.group(1)
                else:
                    page = ''
                result = self.system.open_settings(page)
                return True, result.get('message', f'Opened {page} settings')

            # === SYSTEM INFO (verbose) ===
            if any(x in cmd for x in ['system information', 'computer info', 'pc info', 'laptop info', 'about this pc', 'about my computer']):
                result = self.system.get_system_info()
                if result.get('success'):
                    return True, (
                        f"System Information:\n"
                        f"  OS: {result.get('os', 'Unknown')} {result.get('os_version', '')}\n"
                        f"  Processor: {result.get('processor', 'Unknown')}\n"
                        f"  Architecture: {result.get('architecture', 'Unknown')}\n"
                        f"  Hostname: {result.get('hostname', 'Unknown')}\n"
                        f"  User: {result.get('username', 'Unknown')}"
                    )
                return True, "Could not get system information."

        # === BATTERY STATUS ===
        if any(x in cmd for x in ['battery', 'power status', 'battery level', 'charge']):
            try:
                battery = psutil.sensors_battery()
                if battery:
                    percent = battery.percent
                    plugged = "plugged in" if battery.power_plugged else "on battery"
                    if battery.secsleft > 0 and not battery.power_plugged:
                        mins = battery.secsleft // 60
                        time_left = f", about {mins} minutes remaining"
                    else:
                        time_left = ""
                    return True, f"Battery is at {percent}%, {plugged}{time_left}."
                return True, "I couldn't get battery information. This might be a desktop PC."
            except:
                return True, "Battery information unavailable."
        
        # === SYSTEM INFO ===
        if any(x in cmd for x in ['cpu usage', 'processor', 'cpu status']):
            cpu = psutil.cpu_percent(interval=1)
            return True, f"CPU usage is at {cpu}%."
        
        if any(x in cmd for x in ['memory usage', 'ram', 'memory status']):
            mem = psutil.virtual_memory()
            return True, f"Memory usage is at {mem.percent}%. {mem.available // (1024**3)} GB available."
        
        if any(x in cmd for x in ['disk space', 'storage', 'disk usage']):
            disk = psutil.disk_usage('/')
            free_gb = disk.free // (1024**3)
            return True, f"Disk usage is at {disk.percent}%. {free_gb} GB free."
        
        if any(x in cmd for x in ['system status', 'system info', 'pc status', 'computer status']):
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            try:
                battery = psutil.sensors_battery()
                bat_str = f", Battery: {battery.percent}%" if battery else ""
            except:
                bat_str = ""
            return True, f"System status: CPU {cpu}%, Memory {mem.percent}%, Disk {disk.percent}%{bat_str}."
        
        # === OPEN APPLICATIONS ===
        if any(x in cmd for x in ['open ', 'launch ', 'start ', 'run ']):
            return self._handle_open_command(cmd)
        
        # === CLOSE APPLICATIONS ===
        if any(x in cmd for x in ['close ', 'quit ', 'exit ', 'kill ']):
            return self._handle_close_command(cmd)
        
        # === WEB BROWSING ===
        if any(x in cmd for x in ['search for', 'google ', 'look up', 'search ']):
            return self._handle_search(cmd)
        
        if 'youtube' in cmd and any(x in cmd for x in ['play', 'search', 'open', 'watch']):
            return self._handle_youtube(cmd)
        
        if any(x in cmd for x in ['go to ', 'open website', 'browse to', 'navigate to']):
            return self._handle_website(cmd)
        
        # === TRAVEL/FLIGHTS ===
        if any(x in cmd for x in ['flight', 'flights', 'book flight', 'plane ticket', 'travel to']):
            return self._handle_travel(cmd)
        
        # === SHOPPING ===
        if any(x in cmd for x in ['buy ', 'shop for', 'order ', 'purchase']):
            return self._handle_shopping(cmd)
        
        # === SCREENSHOT ===
        if any(x in cmd for x in ['screenshot', 'screen shot', 'capture screen', 'take a screenshot']):
            return self._take_screenshot()
        
        # === SCREEN VISION & OCR (Phase 4) ===
        if any(x in cmd for x in ['read screen', 'read my screen', 'ocr', 'read text', 'what does the screen say', 'what is on screen', 'what is on my screen']):
            return self._handle_read_screen(cmd)
        
        if any(x in cmd for x in ['find on screen', 'find text', 'locate ', 'where is ']):
            return self._handle_find_on_screen(cmd)
        
        if any(x in cmd for x in ['click on ', 'click text']):
            return self._handle_click_text(cmd)
        
        # ============================================================
        # v9.0 WEEK 3 VOICE COMMANDS - INTELLIGENCE LAYER
        # ============================================================
        
        # === TASK ORCHESTRATOR ===
        if self.task_orchestrator:
            # List tasks
            if any(x in cmd for x in ['list tasks', 'show tasks', 'current tasks', 'running tasks']):
                running = self.task_orchestrator.get_running_tasks()
                pending = self.task_orchestrator.get_pending_tasks()
                if running or pending:
                    response = f"🔄 Running: {len(running)} | ⏳ Pending: {len(pending)}"
                    for t in running[:3]:
                        response += f"\n  • {t['name']} ({t['status']})"
                    return True, response
                return True, "No tasks currently running or pending."
            
            # Task statistics
            if any(x in cmd for x in ['task stats', 'task statistics', 'task status', 'orchestrator stats']):
                stats = self.task_orchestrator.get_statistics()
                return True, (
                    f"📊 Task Statistics:\n"
                    f"  Total: {stats['total_tasks']}\n"
                    f"  Completed: {stats['completed']}\n"
                    f"  Failed: {stats['failed']}\n"
                    f"  Success rate: {stats['success_rate']:.1f}%\n"
                    f"  Avg duration: {stats['avg_duration']:.1f}s"
                )
            
            # Task history
            if any(x in cmd for x in ['task history', 'recent tasks', 'completed tasks']):
                history = self.task_orchestrator.get_history(limit=10)
                if history:
                    response = "📋 Recent task history:"
                    for h in history[-5:]:
                        status_icon = "✅" if h['status'] == 'completed' else "❌"
                        response += f"\n  {status_icon} {h['name']} ({h['duration']:.1f}s)" if h.get('duration') else f"\n  {status_icon} {h['name']}"
                    return True, response
                return True, "No task history yet."
            
            # Cancel task
            if any(x in cmd for x in ['cancel task', 'stop task', 'abort task']):
                running = self.task_orchestrator.get_running_tasks()
                if running:
                    task = running[0]
                    result = self.task_orchestrator.cancel_task(task['id'])
                    return True, f"✋ Cancelled task: {task['name']}" if result['success'] else "Couldn't cancel task"
                return True, "No tasks running to cancel."
        
        # === SCREENSHOT ANALYSIS (Enhanced) ===
        if self.screenshot_analyzer:
            # Analyze screen
            if any(x in cmd for x in ['analyze screen', 'screen analysis', 'what do you see', 'describe screen']):
                result = self.screenshot_analyzer.analyze_screen()
                if result['success']:
                    word_count = result.get('word_count', 0)
                    elements = result.get('elements', 0)
                    return True, f"📊 Screen analysis:\n  Words detected: {word_count}\n  UI elements: {elements}"
                return True, "Couldn't analyze screen"
            
            # Detect UI elements
            if any(x in cmd for x in ['detect elements', 'find buttons', 'find ui', 'detect ui', 'clickable elements']):
                result = self.screenshot_analyzer.detect_ui_elements()
                if result['success']:
                    by_type = result.get('by_type', {})
                    response = f"🎯 Found {result['count']} UI elements:"
                    for elem_type, count in by_type.items():
                        response += f"\n  • {elem_type}: {count}"
                    return True, response
                return True, "Couldn't detect UI elements"
            
            # Get clickable elements
            if any(x in cmd for x in ['what can i click', 'show clickable', 'interactive elements']):
                result = self.screenshot_analyzer.get_clickable_elements()
                if result['success'] and result.get('elements'):
                    clickable = result['elements'][:10]
                    response = f"🔘 Found {result['count']} clickable elements:"
                    for elem in clickable[:5]:
                        response += f"\n  • \"{elem.text}\" ({elem.type})"
                    return True, response
                return True, "No clickable elements detected"
            
            # Get dominant colors
            if any(x in cmd for x in ['screen colors', 'dominant colors', 'color palette', 'what colors']):
                result = self.screenshot_analyzer.get_dominant_colors(num_colors=5)
                if result['success']:
                    colors = result['hex_colors']
                    return True, f"🎨 Dominant screen colors: {', '.join(colors)}"
                return True, "Couldn't analyze colors"
            
            # Save baseline
            if 'save baseline' in cmd:
                match = re.search(r'save baseline\s+(?:as\s+)?(\w+)', cmd)
                name = match.group(1) if match else 'default'
                result = self.screenshot_analyzer.save_baseline(name)
                if result['success']:
                    return True, f"✅ Saved screen baseline as '{name}'"
                return True, "Couldn't save baseline"
            
            # Detect changes
            if any(x in cmd for x in ['detect changes', 'screen changed', 'compare baseline']):
                match = re.search(r'(?:with|from|against)\s+(\w+)', cmd)
                name = match.group(1) if match else 'default'
                baseline_path = f"screenshots/baseline_{name}.png"
                if os.path.exists(baseline_path):
                    result = self.screenshot_analyzer.detect_changes(baseline_path)
                    if result['success']:
                        status = "🔄 Screen has changed" if result['changed'] else "✅ Screen matches baseline"
                        return True, f"{status} (similarity: {result['similarity']:.1%})"
                return True, f"No baseline '{name}' found. Use 'save baseline {name}' first."
        
        # === PATTERN LEARNING ===
        if self.pattern_learner:
            # Get usage statistics
            if any(x in cmd for x in ['usage stats', 'my usage', 'usage statistics', 'how often do i']):
                stats = self.pattern_learner.get_usage_stats()
                if stats.get('total_commands', 0) > 0:
                    return True, (
                        f"📊 Your usage statistics:\n"
                        f"  Total commands: {stats['total_commands']}\n"
                        f"  Days tracked: {stats['days_tracked']}\n"
                        f"  Avg/day: {stats['commands_per_day']:.1f}\n"
                        f"  Patterns detected: {stats['patterns_detected']}\n"
                        f"  Habits found: {stats['habits_detected']}"
                    )
                return True, "Not enough usage data yet. Keep using LADA!"
            
            # Get insights
            if any(x in cmd for x in ['my insights', 'learn about me', 'what have you learned', 'behavior insights', 'my patterns']):
                insights = self.pattern_learner.get_insights()
                if insights:
                    return True, "💡 Insights about your usage:\n" + "\n".join(f"  {i}" for i in insights[:5])
                return True, "I haven't learned enough about your patterns yet."
            
            # Get predictions
            if any(x in cmd for x in ['what should i do', 'suggest something', 'predict next', 'what do you suggest']):
                predictions = self.pattern_learner.predict_next_command()
                if predictions.get('predictions'):
                    response = "🔮 Based on your patterns, you might want to:"
                    for p in predictions['predictions'][:3]:
                        response += f"\n  • \"{p['command']}\" - {p['reason']}"
                    return True, response
                return True, "I don't have enough data for predictions yet."
            
            # Get suggestions
            if any(x in cmd for x in ['time suggestions', 'suggestions now', 'what do i usually do']):
                suggestions = self.pattern_learner.get_suggestions_for_time()
                if suggestions:
                    response = "📋 Based on current time, you usually:"
                    for s in suggestions[:3]:
                        response += f"\n  • {s['command']} ({s['reason']})"
                    return True, response
                return True, "No patterns detected for this time yet."
            
            # Get habits
            if any(x in cmd for x in ['my habits', 'show habits', 'what are my habits', 'detected habits']):
                habits = self.pattern_learner.get_habits()
                if habits:
                    response = "⏰ Your detected habits:"
                    for h in habits[:5]:
                        response += f"\n  • {h['name']} ({h['strength']:.0%} consistent)"
                    return True, response
                return True, "No habits detected yet. Use LADA regularly!"
            
            # Suggest routines
            if any(x in cmd for x in ['suggest routines', 'create routine from habits', 'automate my habits']):
                suggestions = self.pattern_learner.suggest_routines()
                if suggestions:
                    response = f"🤖 {len(suggestions)} routine suggestion(s) based on your habits:"
                    for s in suggestions[:3]:
                        response += f"\n  • {s.name} at {s.trigger_time}"
                    return True, response
                return True, "No strong habits detected for routine suggestions."
            
            # Toggle learning
            if 'disable learning' in cmd or 'stop learning' in cmd:
                self.pattern_learner.enable_learning(False)
                return True, "🔒 Pattern learning disabled."
            
            if 'enable learning' in cmd or 'start learning' in cmd:
                self.pattern_learner.enable_learning(True)
                return True, "✅ Pattern learning enabled."
            
            # Clear learning data
            if 'clear learning' in cmd or 'reset learning' in cmd or 'forget my patterns' in cmd:
                return True, "Say 'confirm clear learning' to erase all learned patterns."
            
            if 'confirm clear learning' in cmd:
                self.pattern_learner.reset_all()
                return True, "🗑️ All learning data cleared."
        
        # ============================================================
        # PROACTIVE AGENT (WEEK 4)
        # ============================================================
        if self.proactive_agent:
            # Morning/Evening briefings
            if any(x in cmd for x in ['morning briefing', 'good morning', 'start my day', 'daily briefing']):
                briefing = self.proactive_agent.generate_morning_briefing()
                return True, f"🌅 {briefing.summary}"
            
            if any(x in cmd for x in ['evening summary', 'end of day', 'daily summary', 'wrap up day']):
                briefing = self.proactive_agent.generate_evening_summary()
                return True, f"🌙 {briefing.summary}"
            
            # Suggestions
            if any(x in cmd for x in ['show suggestions', 'any suggestions', 'what should i do', 'suggest something']):
                suggestions = self.proactive_agent.get_pending_suggestions()
                if suggestions:
                    response = f"💡 {len(suggestions)} suggestion(s):"
                    for s in suggestions[:3]:
                        response += f"\n  • [{s.priority.name}] {s.title}: {s.message[:50]}..."
                    return True, response
                return True, "No pending suggestions right now."
            
            if any(x in cmd for x in ['next suggestion', 'get suggestion']):
                s = self.proactive_agent.get_next_suggestion()
                if s:
                    return True, f"💡 {s.title}\n{s.message}"
                return True, "No suggestions pending."
            
            if 'accept suggestion' in cmd:
                s = self.proactive_agent.get_next_suggestion()
                if s:
                    result = self.proactive_agent.accept_suggestion(s.id)
                    return result.get('success', False), f"✅ Accepted: {s.title}"
                return True, "No pending suggestion to accept."
            
            if 'dismiss suggestion' in cmd or 'ignore suggestion' in cmd:
                s = self.proactive_agent.get_next_suggestion()
                if s:
                    self.proactive_agent.dismiss_suggestion(s.id)
                    return True, f"❌ Dismissed: {s.title}"
                return True, "No pending suggestion to dismiss."
            
            # Proactive monitoring
            if any(x in cmd for x in ['start proactive', 'enable proactive', 'start monitoring']):
                result = self.proactive_agent.start()
                if result.get('success'):
                    return True, "🚀 Proactive monitoring started! I'll anticipate your needs."
                return True, "Proactive monitoring already running."
            
            if any(x in cmd for x in ['stop proactive', 'disable proactive', 'stop monitoring']):
                self.proactive_agent.stop()
                return True, "⏹️ Proactive monitoring stopped."
            
            # Triggers
            if any(x in cmd for x in ['list triggers', 'show triggers', 'my triggers']):
                triggers = self.proactive_agent.list_triggers()
                if triggers:
                    response = f"⚡ {len(triggers)} trigger(s):"
                    for t in triggers[:5]:
                        status = "✅" if t['enabled'] else "❌"
                        response += f"\n  {status} {t['name']} ({t['type']})"
                    return True, response
                return True, "No triggers configured."
            
            # Status
            if any(x in cmd for x in ['proactive status', 'agent status']):
                status = self.proactive_agent.get_status()
                return True, (f"🤖 Proactive Agent Status:\n"
                            f"  Running: {'✅' if status['running'] else '❌'}\n"
                            f"  Pending: {status['pending_suggestions']}\n"
                            f"  Triggers: {status['enabled_triggers']}/{status['total_triggers']}")
            
            # Stats
            if any(x in cmd for x in ['proactive stats', 'suggestion stats']):
                stats = self.proactive_agent.get_stats()
                return True, (f"📊 Proactive Stats:\n"
                            f"  Total suggestions: {stats['total_suggestions']}\n"
                            f"  Accepted: {stats['accepted']}\n"
                            f"  Acceptance rate: {stats['acceptance_rate']:.1f}%")
        
        # ============================================================
        # PERMISSION SYSTEM (WEEK 4)
        # ============================================================
        if self.permission_system:
            # Permission level
            if any(x in cmd for x in ['my permission level', 'permission level', 'what level am i']):
                level = self.permission_system.get_permission_level()
                return True, f"🔑 Your permission level: {level['level']}"
            
            if 'set permission' in cmd:
                if 'admin' in cmd:
                    return True, "⚠️ Admin mode requires password. Use GUI settings."
                elif 'guest' in cmd:
                    self.permission_system.set_permission_level(PermissionLevel.GUEST)
                    return True, "🔑 Set to GUEST mode (limited access)."
                elif 'user' in cmd:
                    self.permission_system.set_permission_level(PermissionLevel.USER)
                    return True, "🔑 Set to USER mode (normal access)."
                return True, "Available levels: user, guest, admin"
            
            # Security lock
            if any(x in cmd for x in ['lock jarvis', 'emergency lock', 'security lock']):
                self.permission_system.emergency_lock("Voice command lock")
                return True, "🔒 JARVIS locked! Unlock with admin password."
            
            if 'is jarvis locked' in cmd or 'lock status' in cmd:
                locked = self.permission_system.is_locked()
                return True, f"{'🔒 System is LOCKED' if locked else '🔓 System is unlocked'}"
            
            # Audit
            if any(x in cmd for x in ['audit log', 'show audit', 'security log']):
                log = self.permission_system.get_audit_log(limit=5)
                if log:
                    response = f"📋 Last {len(log)} actions:"
                    for entry in log:
                        status = "✅" if entry['allowed'] else "❌"
                        response += f"\n  {status} {entry['action'][:30]}..."
                    return True, response
                return True, "No audit entries yet."
            
            if any(x in cmd for x in ['audit stats', 'security stats']):
                stats = self.permission_system.get_audit_stats()
                return True, (f"📊 Security Stats:\n"
                            f"  Total commands: {stats['total']}\n"
                            f"  Allowed: {stats['allowed']}\n"
                            f"  Denied: {stats['denied']}\n"
                            f"  Denial rate: {stats['denial_rate']:.1f}%")
            
            # Whitelist/Blacklist
            if any(x in cmd for x in ['show whitelist', 'show blacklist', 'permission lists']):
                lists = self.permission_system.get_lists()
                return True, (f"📋 Permission Lists:\n"
                            f"  Whitelist: {len(lists['whitelist'])} patterns\n"
                            f"  Blacklist: {len(lists['blacklist'])} patterns")
            
            # Rules
            if any(x in cmd for x in ['permission rules', 'show rules', 'security rules']):
                rules = self.permission_system.list_rules()
                response = f"📋 {len(rules)} permission rules active"
                for r in rules[:3]:
                    response += f"\n  • {r['description'][:40]} ({r['risk']})"
                return True, response
            
            # Rate limits
            if 'rate limits' in cmd:
                limits = self.permission_system.get_rate_limits()
                response = "⏱️ Rate Limits:"
                for cat, limit in limits.items():
                    response += f"\n  • {cat}: {limit}/min"
                return True, response
            
            # Permission status
            if any(x in cmd for x in ['permission status', 'security status']):
                status = self.permission_system.get_status()
                return True, (f"🔐 Security Status:\n"
                            f"  Level: {status['permission_level']}\n"
                            f"  Locked: {'🔒' if status['emergency_locked'] else '🔓'}\n"
                            f"  Rules: {status['rules_count']}\n"
                            f"  Audit entries: {status['audit_entries']}")
        
        # === SPOTIFY / MUSIC COMMANDS ===
        if self.spotify and any(x in cmd for x in ['spotify', 'play music', 'pause music',
            'next song', 'previous song', 'now playing', 'what is playing',
            'what song', 'skip song', 'music volume', 'shuffle', 'add to queue',
            'my playlists', 'play playlist', 'play album', 'play artist']):

            if any(x in cmd for x in ['pause music', 'pause spotify', 'stop music']):
                result = self.spotify.pause()
                return True, result.get('message', 'Paused') if isinstance(result, dict) else str(result)

            if any(x in cmd for x in ['next song', 'skip song', 'next track']):
                result = self.spotify.next_track()
                return True, result.get('message', 'Skipped') if isinstance(result, dict) else str(result)

            if any(x in cmd for x in ['previous song', 'last song', 'previous track']):
                result = self.spotify.previous_track()
                return True, result.get('message', 'Previous') if isinstance(result, dict) else str(result)

            if any(x in cmd for x in ['now playing', 'what is playing', 'what song', 'current song']):
                return True, self.spotify.what_is_playing()

            if 'shuffle' in cmd:
                on = 'off' not in cmd
                result = self.spotify.shuffle(on)
                return True, f"Shuffle {'on' if on else 'off'}"

            if 'my playlists' in cmd or 'list playlists' in cmd:
                return True, self.spotify.list_playlists_spoken()

            if 'music volume' in cmd or 'spotify volume' in cmd:
                nums = [int(x) for x in cmd.split() if x.isdigit()]
                if nums:
                    self.spotify.set_volume(nums[0])
                    return True, f"Spotify volume set to {nums[0]}%"

            # Generic play command - use NLU matching
            play_query = cmd
            for prefix in ['play music', 'play spotify', 'spotify play', 'play']:
                if play_query.startswith(prefix):
                    play_query = play_query[len(prefix):].strip()
                    break
            if play_query:
                return True, self.spotify.play_by_name(play_query)
            else:
                result = self.spotify.play()
                return True, result.get('message', 'Resumed playback') if isinstance(result, dict) else str(result)

        # === SMART HOME COMMANDS ===
        if self.smart_home and any(x in cmd for x in ['turn on light', 'turn off light',
            'lights on', 'lights off', 'dim lights', 'set brightness to',
            'turn on the', 'turn off the', 'set temperature to', 'thermostat',
            'smart home', 'home devices', 'device status', 'smart light',
            'living room light', 'bedroom light', 'kitchen light',
            'activate scene', 'set scene']):

            if any(x in cmd for x in ['home devices', 'device status', 'smart home status',
                                       'list devices']):
                return True, self.smart_home.summary()

            if 'activate scene' in cmd or 'set scene' in cmd:
                scene_name = cmd.split('scene', 1)[-1].strip()
                if scene_name:
                    result = self.smart_home.activate_scene(scene_name)
                    return True, result if isinstance(result, str) else f"Scene '{scene_name}' activated"

            if 'discover' in cmd:
                devices = self.smart_home.discover_devices()
                return True, f"Discovered {len(devices)} smart home devices"

            # Natural language command parsing
            result = self.smart_home.process_command(cmd)
            if result:
                return True, result if isinstance(result, str) else str(result)

        # === HEARTBEAT COMMANDS ===
        if self.heartbeat and any(x in cmd for x in ['heartbeat', 'check in',
            'proactive check', 'start heartbeat', 'stop heartbeat',
            'heartbeat status']):

            if any(x in cmd for x in ['start heartbeat', 'enable heartbeat']):
                self.heartbeat.start()
                return True, "Heartbeat system started. I'll proactively check in periodically."

            if any(x in cmd for x in ['stop heartbeat', 'disable heartbeat']):
                self.heartbeat.stop()
                return True, "Heartbeat system stopped."

            if 'heartbeat status' in cmd:
                status = self.heartbeat.get_status()
                return True, (f"Heartbeat: {'Active' if status.get('running') else 'Stopped'}\n"
                             f"Interval: {status.get('interval_minutes', 30)}min\n"
                             f"Cycles: {status.get('total_cycles', 0)}\n"
                             f"Last: {status.get('last_run', 'Never')}")

            if any(x in cmd for x in ['check in now', 'heartbeat now', 'trigger heartbeat']):
                result = self.heartbeat.trigger_now()
                if result:
                    return True, f"Heartbeat check: {result.summary if hasattr(result, 'summary') else str(result)}"
                return True, "Heartbeat check completed - nothing to report."

        # === DAILY MEMORY COMMANDS ===
        if self.daily_memory and any(x in cmd for x in ['remember that', 'save to memory',
            'note that', 'memory search', 'search memory', 'what do you remember',
            'today notes', 'yesterday notes', 'read memory']):

            if any(x in cmd for x in ['remember that', 'save to memory', 'note that']):
                for prefix in ['remember that', 'save to memory', 'note that']:
                    if cmd.startswith(prefix):
                        note = cmd[len(prefix):].strip()
                        break
                else:
                    note = cmd
                if note:
                    self.daily_memory.append_note(note, category="user_note")
                    return True, f"Got it, I'll remember that."

            if any(x in cmd for x in ['memory search', 'search memory']):
                query = cmd.split('search', 1)[-1].strip().lstrip('memory').strip().lstrip('for').strip()
                if query:
                    results = self.daily_memory.search(query)
                    if results:
                        response = f"Found {len(results)} memory matches:\n"
                        for r in results[:5]:
                            response += f"  - {r.get('text', r)[:100]}\n"
                        return True, response
                    return True, f"No memories found for '{query}'"

            if 'today notes' in cmd or 'today memory' in cmd:
                content = self.daily_memory.read_today()
                return True, content if content else "No notes for today yet."

            if 'yesterday notes' in cmd or 'yesterday memory' in cmd:
                content = self.daily_memory.read_yesterday()
                return True, content if content else "No notes from yesterday."

            if any(x in cmd for x in ['what do you remember', 'read memory']):
                content = self.daily_memory.read_curated()
                return True, content if content else "No curated memories yet."

        # === WORKFLOW PIPELINE COMMANDS ===
        if self.pipeline_runner and any(x in cmd for x in ['run pipeline', 'pipeline status',
            'list pipelines', 'pending approvals', 'approve pipeline']):

            if 'list pipelines' in cmd:
                files = []
                try:
                    from modules.workflow_pipelines import list_pipeline_files
                    files = list_pipeline_files()
                except Exception:
                    pass
                if files:
                    return True, "Available pipelines:\n" + "\n".join(f"  - {f}" for f in files)
                return True, "No pipeline files found."

            if 'pending approvals' in cmd:
                pending = self.pipeline_runner.list_pending()
                if pending:
                    response = f"{len(pending)} pending approvals:\n"
                    for p in pending:
                        response += f"  - {p.get('pipeline', 'Unknown')} (token: {p.get('token', '')[:8]}...)\n"
                    return True, response
                return True, "No pending pipeline approvals."

        # === EVENT HOOKS COMMANDS ===
        if self.hook_manager and any(x in cmd for x in ['list hooks', 'hook status',
            'enable hook', 'disable hook']):

            if 'list hooks' in cmd or 'hook status' in cmd:
                status = self.hook_manager.get_status()
                response = f"Event Hooks: {status['enabled_hooks']}/{status['total_hooks']} enabled\n"
                response += f"Events fired: {status['total_events_fired']}\n"
                for h in status['hooks']:
                    state = 'ON' if h['enabled'] else 'OFF'
                    response += f"  [{state}] {h['name']}: {h['description'][:50]}\n"
                return True, response

            if 'enable hook' in cmd:
                hook_name = cmd.split('enable hook')[-1].strip()
                if hook_name and self.hook_manager.enable(hook_name):
                    return True, f"Hook '{hook_name}' enabled."
                return True, f"Hook '{hook_name}' not found."

            if 'disable hook' in cmd:
                hook_name = cmd.split('disable hook')[-1].strip()
                if hook_name and self.hook_manager.disable(hook_name):
                    return True, f"Hook '{hook_name}' disabled."
                return True, f"Hook '{hook_name}' not found."

        # === POWER COMMANDS ===
        if 'shutdown' in cmd or 'turn off computer' in cmd:
            return True, "Are you sure you want to shut down? Say 'confirm shutdown' to proceed."
        
        if 'confirm shutdown' in cmd:
            os.system('shutdown /s /t 60')
            return True, "Shutting down in 60 seconds. Say 'cancel shutdown' to abort."
        
        if 'cancel shutdown' in cmd:
            os.system('shutdown /a')
            return True, "Shutdown cancelled."
        
        if 'restart' in cmd or 'reboot' in cmd:
            return True, "Are you sure you want to restart? Say 'confirm restart' to proceed."
        
        if 'confirm restart' in cmd:
            os.system('shutdown /r /t 60')
            return True, "Restarting in 60 seconds."
        
        if any(x in cmd for x in ['lock screen', 'lock computer', 'lock pc']):
            subprocess.run('rundll32.exe user32.dll,LockWorkStation', shell=True)
            return True, "Locking the screen."
        
        if any(x in cmd for x in ['sleep', 'go to sleep', 'sleep mode']):
            subprocess.run('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', shell=True)
            return True, "Going to sleep."
        
        # === FILE OPERATIONS ===
        if self.files:
            if any(x in cmd for x in ['create file', 'make file', 'new file']):
                return self._handle_file_create(cmd)
            
            if any(x in cmd for x in ['delete file', 'remove file']):
                return self._handle_file_delete(cmd)
        
        # === MUSIC/MEDIA CONTROL ===
        if any(x in cmd for x in ['play music', 'pause music', 'next song', 'previous song', 'stop music']):
            return self._handle_media_control(cmd)
        
        # === WINDOW MANAGEMENT (Phase 3) ===
        window_triggers = ['window', 'minimize', 'maximize', 'focus ', 'switch to ', 'snap ', 'list windows', 'show windows', 'show desktop', 'activate ']
        if any(x in cmd for x in window_triggers):
            handled, response = self._handle_window_command(cmd)
            if handled:
                return True, response
        
        # === KEYBOARD/TYPING COMMANDS ===
        if any(x in cmd for x in ['type ', 'type this', 'write this', 'enter this']):
            return self._handle_typing(cmd)
        
        if any(x in cmd for x in ['press enter', 'press key', 'press escape', 'press tab']):
            return self._handle_key_press(cmd)
        
        # === AGENT ACTIONS (Comet-style full control) ===
        if self.agent:
            handled, response = self.agent.process(command)
            if handled:
                return True, response

        # ============ v11.0 - Gap Analysis Commands ============

        # === VECTOR MEMORY ===
        if self.vector_memory:
            if any(x in cmd for x in ['remember that', 'remember this', 'store memory', 'save memory']):
                content = re.sub(r'^(remember that|remember this|store memory|save memory)\s*', '', cmd).strip()
                if content:
                    mem_id = self.vector_memory.store(content, memory_type="fact", importance=0.7, source="user")
                    return True, f"Noted and stored in memory." if mem_id else "Failed to store memory."
                return True, "What would you like me to remember?"

            if any(x in cmd for x in ['recall', 'what do you remember about', 'do you remember']):
                query = re.sub(r'^(recall|what do you remember about|do you remember)\s*', '', cmd).strip()
                if query:
                    results = self.vector_memory.search(query, n_results=5)
                    if results:
                        memories = '\n'.join([f"  - {r['content']}" for r in results[:5]])
                        return True, f"Here's what I recall:\n{memories}"
                    return True, "I don't have any relevant memories about that."
                return True, "What topic would you like me to recall?"

            if cmd in ['memory stats', 'memory status', 'show memory stats']:
                stats = self.vector_memory.get_stats()
                return True, f"Vector Memory: {stats.get('total_memories', 0)} memories stored. ChromaDB: {'active' if stats.get('chromadb_available') else 'fallback mode'}."

        # === RAG ENGINE ===
        if self.rag_engine:
            if any(x in cmd for x in ['ingest document', 'ingest file', 'add to knowledge', 'learn from file']):
                match = re.search(r'(?:ingest|add to knowledge|learn from)\s+(?:document|file)?\s*(.+)', cmd)
                if match:
                    file_path = match.group(1).strip().strip('"').strip("'")
                    result = self.rag_engine.ingest(file_path)
                    status = result.get('status', 'error')
                    if status == 'success':
                        return True, f"Ingested document: {result.get('chunks', 0)} chunks added to knowledge base."
                    elif status == 'already_ingested':
                        return True, f"Document already in knowledge base ({result.get('chunks', 0)} chunks)."
                    return True, f"Could not ingest document: {status}"
                return True, "Provide a file path: 'ingest document C:\\path\\to\\file.pdf'"

            if any(x in cmd for x in ['ingest folder', 'ingest directory', 'learn from folder']):
                match = re.search(r'(?:ingest|learn from)\s+(?:folder|directory)\s*(.+)', cmd)
                if match:
                    dir_path = match.group(1).strip().strip('"').strip("'")
                    result = self.rag_engine.ingest_directory(dir_path)
                    return True, f"Ingested {result.get('files_processed', 0)} files, {result.get('total_chunks', 0)} total chunks."
                return True, "Provide a folder path: 'ingest folder C:\\path\\to\\docs'"

            if any(x in cmd for x in ['list documents', 'list knowledge', 'knowledge base', 'rag status']):
                docs = self.rag_engine.list_documents()
                if docs:
                    doc_list = '\n'.join([f"  - {d['filename']} ({d['chunks']} chunks)" for d in docs[:10]])
                    return True, f"Knowledge base ({len(docs)} documents):\n{doc_list}"
                return True, "Knowledge base is empty. Use 'ingest document <path>' to add files."

            if any(x in cmd for x in ['ask knowledge', 'query knowledge', 'search knowledge']):
                query = re.sub(r'^(ask|query|search)\s+knowledge\s*', '', cmd).strip()
                if query:
                    result = self.rag_engine.query(query)
                    if result.get('context'):
                        sources = ', '.join([os.path.basename(s) for s in result.get('sources', [])])
                        return True, f"{result['context']}\n\n[Sources: {sources}]" if sources else result['context']
                    return True, "No relevant information found in the knowledge base."

        # === MCP TOOLS ===
        if self.mcp_client:
            if any(x in cmd for x in ['list tools', 'mcp tools', 'available tools', 'show tools']):
                tools = self.mcp_client.list_tools()
                if tools:
                    tool_list = '\n'.join([f"  - {t['name']}: {t['description'][:80]}" for t in tools[:20]])
                    return True, f"MCP Tools ({len(tools)} available):\n{tool_list}"
                return True, "No MCP tools available. Configure servers in config/mcp_servers.json."

            if any(x in cmd for x in ['mcp status', 'mcp stats']):
                stats = self.mcp_client.get_stats()
                return True, f"MCP: {stats.get('servers_running', 0)}/{stats.get('servers_configured', 0)} servers, {stats.get('tools_available', 0)} tools."

            if 'use tool' in cmd or 'call tool' in cmd:
                match = re.search(r'(?:use|call)\s+tool\s+(\S+)\s*(.*)', cmd)
                if match:
                    tool_name = match.group(1).strip()
                    args_str = match.group(2).strip()
                    args = {}
                    if args_str:
                        try:
                            args = json.loads(args_str)
                        except json.JSONDecodeError:
                            args = {"input": args_str}
                    result = self.mcp_client.call_tool(tool_name, args)
                    if result.get('error'):
                        return True, f"Tool error: {result['error']}"
                    return True, f"Tool result: {result.get('result', 'No output')}"

        # === MULTI-AGENT COLLABORATION ===
        if self.collab_hub:
            if any(x in cmd for x in ['list agents', 'show agents', 'available agents']):
                agents = self.collab_hub.list_agents()
                if agents:
                    agent_list = '\n'.join([f"  - {a['name']}: {', '.join(a['capabilities'])}" for a in agents])
                    return True, f"Registered agents ({len(agents)}):\n{agent_list}"
                return True, "No agents registered."

            if any(x in cmd for x in ['delegate to', 'ask agent', 'agent collaboration']):
                match = re.search(r'(?:delegate to|ask agent)\s+(\S+)\s+(.*)', cmd)
                if match:
                    agent_name = match.group(1).strip()
                    task_desc = match.group(2).strip()
                    task = self.collab_hub.delegate_task(
                        from_agent="orchestrator",
                        to_agent=agent_name,
                        description=task_desc,
                    )
                    return True, f"Task delegated to {agent_name}: {task.task_id}"

            if any(x in cmd for x in ['collaboration stats', 'collab stats', 'agent stats']):
                stats = self.collab_hub.get_stats()
                return True, f"Collaboration Hub: {stats.get('registered_agents', 0)} agents, {stats.get('total_tasks', 0)} tasks ({stats.get('pending_tasks', 0)} pending)."

        # === COMPUTER USE AGENT ===
        if self.computer_use:
            if any(x in cmd for x in ['computer do', 'use computer to', 'automate screen', 'click on', 'computer use']):
                task = re.sub(r'^(computer do|use computer to|automate screen|computer use)\s*', '', cmd).strip()
                if task:
                    result = self.computer_use.execute_task(task, max_steps=15)
                    status = result.get('status', 'error')
                    steps = result.get('steps', 0)
                    return True, f"Computer use {status}: {steps} actions taken."
                return True, "What would you like me to do on the computer? Example: 'computer do open notepad and type hello'"

        # === WEBHOOK MANAGEMENT ===
        if self.webhook_manager:
            if any(x in cmd for x in ['webhook status', 'webhook stats']):
                stats = self.webhook_manager.get_stats()
                status = "running" if stats.get('running') else "stopped"
                return True, f"Webhook server: {status} (port {stats.get('port')}). Events received: {stats.get('events_received', 0)}."

            if 'start webhook' in cmd or 'start webhooks' in cmd:
                self.webhook_manager.start_server()
                return True, f"Webhook server started on port {self.webhook_manager.port}."

            if any(x in cmd for x in ['webhook events', 'webhook history', 'recent webhooks']):
                events = self.webhook_manager.get_event_history(limit=10)
                if events:
                    event_list = '\n'.join([f"  - [{e['source']}/{e['event_type']}] {e.get('result', '')}" for e in events])
                    return True, f"Recent webhook events:\n{event_list}"
                return True, "No webhook events received yet."

        # === SELF-MODIFYING ENGINE ===
        if self.self_modifier:
            if any(x in cmd for x in ['analyze module', 'analyze code', 'code analysis']):
                match = re.search(r'(?:analyze module|analyze code)\s+(.+)', cmd)
                if match:
                    module_path = match.group(1).strip()
                    analysis = self.self_modifier.analyze_module(module_path)
                    if 'error' not in analysis:
                        funcs = len(analysis.get('functions', []))
                        classes = len(analysis.get('classes', []))
                        complexity = analysis.get('complexity', {})
                        return True, f"Module analysis: {funcs} functions, {classes} classes, {complexity.get('total_lines', 0)} lines."
                    return True, f"Analysis failed: {analysis.get('error')}"
                return True, "Provide a module path: 'analyze module modules/example.py'"

            if any(x in cmd for x in ['code history', 'modification history']):
                history = self.self_modifier.get_modification_history()
                if history:
                    hist_list = '\n'.join([f"  - [{h['type']}] {h['description'][:60]}" for h in history[-10:]])
                    return True, f"Recent code modifications:\n{hist_list}"
                return True, "No code modifications recorded."

            if 'rollback' in cmd and 'code' in cmd:
                match = re.search(r'rollback\s+(?:code\s+)?(.+)', cmd)
                if match:
                    file_path = match.group(1).strip()
                    result = self.self_modifier.rollback(file_path)
                    return True, result.message

        # === TOKEN OPTIMIZER STATS ===
        if self.token_optimizer:
            if any(x in cmd for x in ['token stats', 'token usage', 'api costs', 'token savings']):
                stats = self.token_optimizer.get_stats()
                return True, (
                    f"Token usage: {stats.get('total_tokens_used', 0):,} tokens across {stats.get('total_requests', 0)} requests. "
                    f"Saved: {stats.get('total_tokens_saved', 0):,} tokens ({stats.get('savings_percentage', 0)}%). "
                    f"Cache hits: {stats.get('total_cache_hits', 0)}. "
                    f"Estimated cost: ${stats.get('estimated_cost_usd', 0):.4f}."
                )

        # === DYNAMIC PROMPTS ===
        if self.prompt_builder:
            if any(x in cmd for x in ['prompt stats', 'prompt status']):
                stats = self.prompt_builder.get_stats()
                return True, f"Dynamic Prompts: dir={stats.get('prompt_dir')}, cached={stats.get('cached_components')}, modes={stats.get('available_modes')}"

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

        # Not a system command - let AI handle it
        return False, ""
    
    def _handle_open_command(self, cmd: str) -> Tuple[bool, str]:
        """Handle open/launch commands for apps and websites"""
        cmd = cmd.lower()
        
        # Remove command words
        for prefix in ['open ', 'launch ', 'start ', 'run ']:
            if prefix in cmd:
                target = cmd.split(prefix, 1)[-1].strip()
                break
        else:
            return False, ""
        
        # Check websites first
        for site, url in self.websites.items():
            if site in target:
                webbrowser.open(url)
                return True, f"{LadaPersonality.get_acknowledgment()} Opening {site}."
        
        # Check apps
        for app_name, paths in self.apps.items():
            if app_name in target:
                return self._launch_app(app_name, paths)
        
        # Try to find app in PATH or as a command
        try:
            # Special handling for common requests
            if 'file' in target or 'folder' in target or 'explorer' in target:
                os.startfile('explorer')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening File Explorer."
            
            if 'browser' in target:
                webbrowser.open('https://google.com')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening your browser."
            
            # Try running as command
            subprocess.Popen(target, shell=True)
            return True, f"{LadaPersonality.get_acknowledgment()} Opening {target}."
        except:
            return True, f"I couldn't find an app called '{target}'. Could you be more specific?"
    
    def _launch_app(self, app_name: str, paths: list) -> Tuple[bool, str]:
        """Launch an application from known paths"""
        import getpass
        username = getpass.getuser()
        
        for path in paths:
            path = path.replace('{user}', username)
            
            # Handle special URI schemes (ms-settings:, etc.)
            if path.startswith('ms-'):
                os.system(f'start {path}')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
            
            # Check if file exists
            if Path(path).exists():
                try:
                    subprocess.Popen([path], shell=True)
                    return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
                except:
                    continue
            
            # Try as direct executable (in PATH)
            if path.endswith('.exe') and '\\' not in path:
                try:
                    subprocess.Popen(path, shell=True)
                    return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
                except:
                    continue
        
        # Fallback: use webbrowser for browsers or shell command
        if app_name in ['chrome', 'firefox', 'edge', 'browser']:
            try:
                webbrowser.open('https://google.com')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening your browser."
            except:
                pass
        
        # Last resort: try as shell command
        try:
            os.system(f'start {app_name}')
            return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
        except:
            return True, f"I couldn't open {app_name}. Make sure it's installed."
    
    def _handle_close_command(self, cmd: str) -> Tuple[bool, str]:
        """Handle close/quit commands"""
        for prefix in ['close ', 'quit ', 'exit ', 'kill ']:
            if prefix in cmd:
                target = cmd.split(prefix, 1)[-1].strip()
                break
        else:
            return False, ""
        
        # Map common names to process names
        process_map = {
            'chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'notepad': 'notepad.exe',
            'spotify': 'Spotify.exe',
            'discord': 'Discord.exe',
            'vscode': 'Code.exe',
            'vs code': 'Code.exe',
            'vlc': 'vlc.exe',
            'word': 'WINWORD.EXE',
            'excel': 'EXCEL.EXE',
        }
        
        proc_name = process_map.get(target, f'{target}.exe')
        
        try:
            os.system(f'taskkill /im {proc_name} /f')
            return True, f"{LadaPersonality.get_confirmation()} Closed {target}."
        except:
            return True, f"I couldn't close {target}."
    
    def _handle_search(self, cmd: str) -> Tuple[bool, str]:
        """Handle web search commands.
        
        Option A (default): AI answers in chat with web context (fast)
        Option B: User says 'open and find' / 'open browser' -> opens browser and keeps it open
        """
        cmd_lower = cmd.lower()
        
        # Option B: User explicitly wants to open browser and browse manually
        explicit_browser = any(x in cmd_lower for x in [
            'open browser', 'open google', 'google it', 'open bing', 'in browser',
            'open and find', 'open and search', 'open amazon', 'open flipkart',
            'browse for', 'go to amazon', 'go to flipkart'
        ])
        
        if explicit_browser:
            # Extract search query
            for prefix in ['search for ', 'google ', 'look up ', 'search ', 
                          'open browser and search for ', 'open browser and ',
                          'open and find ', 'open and search for ', 'open amazon and search ',
                          'open flipkart and search ', 'find ', 'browse for ']:
                if prefix in cmd_lower:
                    query = cmd.split(prefix, 1)[-1].strip()
                    break
            else:
                query = cmd.replace('open browser', '').replace('open google', '').replace('google it', '')
                query = query.replace('open and find', '').replace('open and search', '').strip()
            
            # Determine which site to open
            if 'amazon' in cmd_lower:
                if query:
                    url = f'https://www.amazon.in/s?k={query.replace(" ", "+")}'
                else:
                    url = 'https://www.amazon.in'
                webbrowser.open(url)
                return True, f"Opening Amazon to browse '{query}'." if query else "Opening Amazon."
                
            elif 'flipkart' in cmd_lower:
                if query:
                    url = f'https://www.flipkart.com/search?q={query.replace(" ", "+")}'
                else:
                    url = 'https://www.flipkart.com'
                webbrowser.open(url)
                return True, f"Opening Flipkart to browse '{query}'." if query else "Opening Flipkart."
            
            else:
                # Default to Google
                if query:
                    url = f'https://www.google.com/search?q={query.replace(" ", "+")}'
                    webbrowser.open(url)
                    return True, f"Opening browser to search for '{query}'."
                else:
                    webbrowser.open('https://www.google.com')
                    return True, "Opening Google."
        
        # Option A (default): Return False to let AI answer with web context
        # This means "search for X", "what is X", "who is X" etc. will be answered in chat
        return False, ""
    
    def _handle_youtube(self, cmd: str) -> Tuple[bool, str]:
        """Handle YouTube commands"""
        # Extract search term if present
        patterns = ['play ', 'search ', 'watch ', 'on youtube', 'youtube ']
        
        query = cmd
        for pattern in patterns:
            query = query.replace(pattern, ' ')
        query = query.replace('youtube', '').strip()
        
        if query and len(query) > 2:
            url = f'https://www.youtube.com/results?search_query={query.replace(" ", "+")}'
            webbrowser.open(url)
            return True, f"Searching YouTube for '{query}'."
        else:
            webbrowser.open('https://www.youtube.com')
            return True, "Opening YouTube."
    
    def _handle_website(self, cmd: str) -> Tuple[bool, str]:
        """Handle direct website navigation"""
        # Extract URL
        patterns = ['go to ', 'open website ', 'browse to ', 'navigate to ', 'open ']
        
        url = cmd
        for pattern in patterns:
            if pattern in url:
                url = url.split(pattern, 1)[-1].strip()
        
        if url:
            if not url.startswith('http'):
                url = 'https://' + url
            webbrowser.open(url)
            return True, f"Opening {url}."
        
        return False, ""
    
    def _handle_travel(self, cmd: str) -> Tuple[bool, str]:
        """Handle flight/travel search requests with full automation"""
        cmd_lower = cmd.lower()
        
        # Parse origin and destination
        origin = ""
        destination = ""
        date = "tomorrow"  # Default to tomorrow
        
        # Try to extract "from [origin] to [destination]"
        if ' from ' in cmd_lower and ' to ' in cmd_lower:
            parts = cmd_lower.split(' from ', 1)
            if len(parts) > 1:
                rest = parts[1]
                if ' to ' in rest:
                    from_to = rest.split(' to ', 1)
                    origin = from_to[0].strip()
                    destination = from_to[1].strip()
        elif ' to ' in cmd_lower:
            parts = cmd_lower.split(' to ', 1)
            destination = parts[-1].strip()
        
        # Clean up destination
        for word in ['flight', 'flights', 'ticket', 'tickets', 'book', 'find', 'me', 'a', 'on', 'for']:
            destination = destination.replace(word, '').strip()
            if origin:
                origin = origin.replace(word, '').strip()
        
        # Extract date if mentioned
        date_patterns = ['tomorrow', 'today', 'next week', 'this weekend']
        for dp in date_patterns:
            if dp in cmd_lower:
                date = dp
                break
        
        # Try to use FlightAgent for full automation if available
        if self.flight_agent and destination:
            try:
                def progress(step, total, desc):
                    logger.info(f"[FlightAgent] Step {step}/{total}: {desc}")
                
                result = self.flight_agent.search_flights(
                    from_city=origin or "Your city",
                    to_city=destination,
                    date=date,
                    progress_callback=progress
                )
                
                if result.get('status') == 'success':
                    flights = result.get('flights', [])
                    cheapest = result.get('cheapest')
                    recommendation = result.get('recommendation', '')
                    
                    if cheapest:
                        response = f"✈️ Found {len(flights)} flights to {destination}!\n\n"
                        response += f"**Best Deal:** {cheapest.get('airline', 'Unknown')} - ₹{cheapest.get('price', 'N/A')}\n"
                        response += f"Duration: {cheapest.get('duration', 'N/A')}\n"
                        if recommendation:
                            response += f"\n💡 {recommendation}"
                        return True, response
                    elif flights:
                        return True, f"Found {len(flights)} flights to {destination}. Check the browser for details."
                    
                elif result.get('status') == 'cancelled':
                    return True, "Flight search cancelled."
                    
            except Exception as e:
                logger.error(f"FlightAgent error: {e}")
                # Fall through to basic browser opening
        
        # Fallback: Open Google Flights
        if destination:
            url = f"https://www.google.com/travel/flights?q=flights+to+{destination.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Opening Google Flights to search for flights to {destination.title()}."
        else:
            webbrowser.open("https://www.google.com/travel/flights")
            return True, "Opening Google Flights. You can search for any destination."
    
    def _handle_shopping(self, cmd: str) -> Tuple[bool, str]:
        """Handle shopping/purchase requests with smart product search"""
        cmd_lower = cmd.lower()
        
        # Extract what to buy
        item = ""
        budget = None
        
        for prefix in ['buy ', 'shop for ', 'order ', 'purchase ', 'find ', 'search for ']:
            if prefix in cmd_lower:
                item = cmd_lower.split(prefix, 1)[-1].strip()
                break
        
        # Extract budget if mentioned
        import re
        budget_match = re.search(r'under\s*(?:rs\.?|₹|inr)?\s*(\d+)', cmd_lower)
        if budget_match:
            budget = int(budget_match.group(1))
            item = re.sub(r'under\s*(?:rs\.?|₹|inr)?\s*\d+', '', item).strip()
        
        # Try ProductAgent for full comparison
        if self.product_agent and item:
            try:
                def progress(step, total, desc):
                    logger.info(f"[ProductAgent] Step {step}/{total}: {desc}")
                
                result = self.product_agent.search_products(
                    query=item,
                    max_price=budget,
                    progress_callback=progress
                )
                
                if result.get('status') == 'success':
                    products = result.get('products', [])
                    best_pick = result.get('best_pick')
                    
                    if best_pick:
                        response = f"🛒 Found {len(products)} options for '{item}'!\n\n"
                        response += f"**Best Pick:** {best_pick.get('name', 'Unknown')}\n"
                        response += f"Price: ₹{best_pick.get('price', 'N/A')}\n"
                        response += f"Rating: {best_pick.get('rating', 'N/A')}⭐\n"
                        if best_pick.get('source'):
                            response += f"From: {best_pick['source']}\n"
                        return True, response
                    elif products:
                        return True, f"Found {len(products)} products matching '{item}'. Check the browser for details."
                        
            except Exception as e:
                logger.error(f"ProductAgent error: {e}")
        
        # Fallback: Open Amazon/Flipkart
        if item:
            url = f"https://www.amazon.in/s?k={item.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Opening Amazon to search for {item}."
        
        webbrowser.open("https://www.amazon.in")
        return True, "Opening Amazon."
    
    def _take_screenshot(self) -> Tuple[bool, str]:
        """Take a screenshot and save it"""
        # Use screen vision module if available
        if self.vision:
            result = self.vision.capture_screen()
            if result['success']:
                return True, f"Screenshot saved to {result['path']}."
            return True, f"Couldn't take screenshot: {result.get('error', 'Unknown error')}"
        
        # Fallback to direct pyautogui
        try:
            import pyautogui
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshots_dir = Path('screenshots')
            screenshots_dir.mkdir(exist_ok=True)
            filepath = screenshots_dir / f'screenshot_{timestamp}.png'
            
            screenshot = pyautogui.screenshot()
            screenshot.save(str(filepath))
            
            return True, f"Screenshot saved to {filepath}."
        except ImportError:
            return True, "I need pyautogui to take screenshots. Install it with: pip install pyautogui"
        except Exception as e:
            return True, f"Couldn't take screenshot: {e}"
    
    def _handle_read_screen(self, cmd: str) -> Tuple[bool, str]:
        """Handle screen reading/OCR commands"""
        if not self.vision:
            return True, "Screen reading requires the screen_vision module."
        
        try:
            result = self.vision.read_screen()
            if result['success']:
                text = result['text']
                if len(text) > 500:
                    text = text[:500] + "..."
                word_count = result.get('word_count', 0)
                confidence = result.get('confidence', 0)
                
                response = f"📖 **Screen Text** ({word_count} words, {confidence:.0%} confidence):\n\n{text}"
                
                if result.get('summary'):
                    response += f"\n\n**Summary:** {result['summary']}"
                
                return True, response
            return True, f"Couldn't read screen: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Screen reading error: {e}"
    
    def _handle_find_on_screen(self, cmd: str) -> Tuple[bool, str]:
        """Find specific text on screen using OCR"""
        if not self.vision:
            return True, "Screen vision requires the screen_vision module."
        
        # Extract search text
        for pattern in ['find on screen ', 'find text ', 'locate ', 'where is ']:
            if pattern in cmd.lower():
                search_text = cmd.lower().split(pattern, 1)[-1].strip()
                break
        else:
            return True, "What text should I look for on screen?"
        
        try:
            result = self.vision.find_text_on_screen(search_text)
            if result['success']:
                if result['found']:
                    count = result['count']
                    locs = result['locations'][:3]  # Show first 3
                    response = f"✅ Found '{search_text}' {count} time(s) on screen.\n"
                    for i, (x, y, w, h) in enumerate(locs, 1):
                        response += f"  {i}. Position: ({x}, {y})\n"
                    return True, response
                return True, f"❌ Couldn't find '{search_text}' on the current screen."
            return True, f"Search failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Search error: {e}"
    
    def _handle_click_text(self, cmd: str) -> Tuple[bool, str]:
        """Find text on screen and click on it"""
        if not self.vision:
            return True, "Screen vision requires the screen_vision module."
        
        # Extract click target
        for pattern in ['click on ', 'click text ', 'click the ']:
            if pattern in cmd.lower():
                target = cmd.lower().split(pattern, 1)[-1].strip()
                # Remove trailing punctuation
                target = target.rstrip('.,!?')
                break
        else:
            return True, "What text should I click on?"
        
        try:
            result = self.vision.click_on_text(target)
            if result['success']:
                if result.get('clicked'):
                    x, y = result['location']
                    return True, f"✅ Clicked on '{target}' at position ({x}, {y})."
                return True, f"❌ Couldn't find '{target}' on screen to click."
            return True, f"Click failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Click error: {e}"
    
    def _handle_file_create(self, cmd: str) -> Tuple[bool, str]:
        """Handle file creation commands"""
        # Extract filename
        match = re.search(r'(?:named?|called?)\s+([^\s]+)', cmd)
        if match:
            filename = match.group(1)
            # Create in current directory or Desktop
            desktop = Path.home() / 'Desktop' / filename
            try:
                desktop.touch()
                return True, f"Created {filename} on your Desktop."
            except Exception as e:
                return True, f"Couldn't create file: {e}"
        return True, "What would you like to name the file?"
    
    def _handle_file_delete(self, cmd: str) -> Tuple[bool, str]:
        """Handle file deletion commands"""
        return True, "For safety, I need you to specify the exact file path to delete. What file should I remove?"
    
    def _handle_media_control(self, cmd: str) -> Tuple[bool, str]:
        """Handle media playback control using keyboard simulation"""
        try:
            import pyautogui
            
            if 'pause' in cmd or 'stop' in cmd:
                pyautogui.press('playpause')
                return True, "Paused."
            
            if 'play' in cmd and 'music' in cmd:
                pyautogui.press('playpause')
                return True, "Playing."
            
            if 'next' in cmd:
                pyautogui.press('nexttrack')
                return True, "Next track."
            
            if 'previous' in cmd or 'prev' in cmd:
                pyautogui.press('prevtrack')
                return True, "Previous track."
            
        except ImportError:
            return True, "Media control requires pyautogui. Install with: pip install pyautogui"
        
        return False, ""
    
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
        except:
            pass
        
        # High CPU warning
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            if cpu > 90:
                alerts.append(f"Your CPU is running quite hot at {cpu}%. Some processes might be using a lot of resources.")
        except:
            pass
        
        # High memory warning
        try:
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                alerts.append(f"Memory usage is high at {mem.percent}%. Consider closing some applications.")
        except:
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
                os.system('shutdown /s /t 60')
                return True, "Computer will shut down in 60 seconds. Say 'cancel shutdown' to abort."
            elif 'restart' in action:
                os.system('shutdown /r /t 60')
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
            os.system('shutdown /l /t 1')
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
                    except:
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
                        except:
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
