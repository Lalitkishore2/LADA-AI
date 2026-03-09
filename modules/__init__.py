"""
===============================
🤖 LADA v7.0 - Module Package
===============================

Core modules for LADA AI Assistant
Restructured with Comet-style agents
"""

# Core modules (with graceful fallback for dependencies)
try:
    from .nlu_engine import NLUEngine, SensitiveDataDetector
except ImportError:
    NLUEngine = None
    SensitiveDataDetector = None

try:
    from lada_memory import MemorySystem
except ImportError:
    MemorySystem = None

try:
    from .system_control import SystemController, PowerAction
except ImportError:
    SystemController = None
    PowerAction = None

try:
    from .safety_controller import SafetyController, ActionSeverity, PrivacyLevel
except ImportError:
    SafetyController = None
    ActionSeverity = None
    PrivacyLevel = None

try:
    from .health_monitor import HealthMonitor
except ImportError:
    HealthMonitor = None

try:
    from .advanced_features import ResponseCache, ConversationManager
except ImportError:
    ResponseCache = None
    ConversationManager = None

try:
    from .task_automation import TaskChoreographer, TaskStatus, TaskPriority
except ImportError:
    TaskChoreographer = None
    TaskStatus = None
    TaskPriority = None

try:
    from .file_operations import FileSystemController, FileOperation
except ImportError:
    FileSystemController = None
    FileOperation = None

try:
    from .browser_automation import CometBrowserAgent as BrowserControl
except ImportError:
    BrowserControl = None

# v7.0 New modules (with graceful fallback)
try:
    from .markdown_renderer import MarkdownRenderer
except ImportError:
    MarkdownRenderer = None

try:
    from .chat_manager import ChatManager, Message, Conversation
except ImportError:
    ChatManager = None
    Message = None
    Conversation = None

try:
    from .export_manager import ExportManager
except ImportError:
    ExportManager = None

try:
    from .agent_orchestrator import AgentOrchestrator, AgentType, AgentResult
except ImportError:
    AgentOrchestrator = None
    AgentType = None
    AgentResult = None

__all__ = [
    # Core modules
    'NLUEngine',
    'SensitiveDataDetector',
    'MemorySystem',
    'SystemController',
    'PowerAction',
    'SafetyController',
    'ActionSeverity',
    'PrivacyLevel',
    'HealthMonitor',
    'ResponseCache',
    'ConversationManager',
    'TaskChoreographer',
    'TaskStatus',
    'TaskPriority',
    'FileSystemController',
    'FileOperation',
    'BrowserControl',
    # v7.0 modules (may be None if deps missing)
    'MarkdownRenderer',
    'ChatManager',
    'Message',
    'Conversation',
    'ExportManager',
    'AgentOrchestrator',
    'AgentType',
    'AgentResult',
]

__version__ = '7.0.0'
__author__ = 'LADA Development Team'
