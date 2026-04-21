"""
LADA Service Registry — Centralised lazy-loading and availability tracking
for all optional modules.

Replaces the 52 try/except import blocks at the top of lada_jarvis_core.py.
"""

import importlib
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class _ServiceEntry:
    __slots__ = (
        'module_path',
        'names',
        'factory',
        'required',
        'env_flag',
        'env_enabled_values',
        'available',
        'loaded',
        '_cached',
    )

    def __init__(self, module_path: str, names: List[str],
                 factory: Optional[str] = None, required: bool = False,
                 env_flag: Optional[str] = None,
                 env_enabled_values: Optional[List[str]] = None):
        self.module_path = module_path
        self.names = names            # class/function names to import
        self.factory = factory         # optional factory function name
        self.required = required
        self.env_flag = env_flag
        if env_enabled_values:
            self.env_enabled_values = {str(value).strip().lower() for value in env_enabled_values}
        else:
            self.env_enabled_values = {"1", "true", "yes", "on"}
        self.available = False         # True if import succeeded
        self.loaded = False
        self._cached: Dict[str, Any] = {}

    def _env_enabled(self) -> bool:
        if not self.env_flag:
            return True
        raw_value = str(os.getenv(self.env_flag, "")).strip().lower()
        return raw_value in self.env_enabled_values

    def probe(self) -> bool:
        """Try to import the module; set self.available accordingly."""
        if not self._env_enabled():
            for n in self.names:
                self._cached[n] = None
            self.available = False
            self.loaded = False
            return False

        try:
            mod = importlib.import_module(self.module_path)
            for n in self.names:
                self._cached[n] = getattr(mod, n, None)
            self.available = True
            self.loaded = True
        except ImportError:
            for n in self.names:
                self._cached[n] = None
            self.available = False
        return self.available

    def get(self, name: str) -> Any:
        """Return a previously imported name (class, factory, etc.)."""
        if not self.loaded:
            self.probe()
        return self._cached.get(name)


class ServiceRegistry:
    """
    Central registry for LADA's optional modules.

    Usage:
        svc = ServiceRegistry()
        svc.register('system', 'modules.system_control',
                      ['SystemController'])
        svc.probe_all()

        if svc.ok('system'):
            cls = svc.get('system', 'SystemController')
            instance = cls()
    """

    def __init__(self):
        self._entries: Dict[str, _ServiceEntry] = {}

    # ── Registration ────────────────────────────────────────

    def register(self, key: str, module_path: str, names: List[str],
                 factory: Optional[str] = None, required: bool = False,
                 env_flag: Optional[str] = None,
                 env_enabled_values: Optional[List[str]] = None):
        """Register a service (module) by key."""
        self._entries[key] = _ServiceEntry(
            module_path,
            names,
            factory,
            required,
            env_flag=env_flag,
            env_enabled_values=env_enabled_values,
        )

    # ── Bulk probe ──────────────────────────────────────────

    def probe_all(self) -> Dict[str, bool]:
        """Import-test every registered module.  Returns {key: available}."""
        result = {}
        for key, entry in self._entries.items():
            ok = entry.probe()
            result[key] = ok
            if not ok and entry.required:
                raise ImportError(
                    f"Required module '{entry.module_path}' could not be imported"
                )
            level = logging.DEBUG if ok else logging.WARNING
            logger.log(level, "[ServiceRegistry] %s (%s): %s",
                        key, entry.module_path, "OK" if ok else "not available")
        return result

    # ── Lookups ─────────────────────────────────────────────

    def ok(self, key: str) -> bool:
        """Return True if the module was successfully imported."""
        entry = self._entries.get(key)
        return entry.available if entry else False

    def get(self, key: str, name: Optional[str] = None) -> Any:
        """
        Retrieve an imported object by key.

        If *name* is given, return that specific attribute.
        Otherwise return the *first* registered name.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        if name:
            return entry.get(name)
        # Default: first registered name
        return entry.get(entry.names[0]) if entry.names else None

    def get_factory(self, key: str) -> Any:
        """Return the factory function for a service (or None)."""
        entry = self._entries.get(key)
        if entry and entry.factory:
            return entry.get(entry.factory)
        return None

    def keys(self) -> List[str]:
        return list(self._entries.keys())

    def available_keys(self) -> List[str]:
        return [k for k, e in self._entries.items() if e.available]


def build_default_registry() -> ServiceRegistry:
    """Create and return the default LADA service registry with all modules registered."""
    svc = ServiceRegistry()

    # Core modules
    svc.register('system', 'modules.system_control', ['SystemController'])
    svc.register('browser', 'modules.browser_automation', ['CometBrowserAgent'])
    svc.register('files', 'modules.file_operations', ['FileSystemController'])
    svc.register('nlu', 'modules.nlu_engine', ['NLUEngine'])
    svc.register('safety', 'modules.safety_controller',
                 ['SafetyController', 'PrivacyLevel', 'ActionSeverity'])
    svc.register('memory', 'lada_memory', ['MemorySystem'])

    # Task / agents
    svc.register('task_automation', 'modules.task_automation', ['TaskChoreographer'])
    svc.register('agent_actions', 'modules.agent_actions', ['AgentActions'])
    svc.register('screen_vision', 'modules.screen_vision', ['ScreenVision'])

    # Workflow / routine
    svc.register('workflow', 'modules.workflow_engine',
                 ['WorkflowEngine', 'create_workflow_engine'])
    svc.register('routine', 'modules.routine_manager',
                 ['RoutineManager', 'create_routine_manager'])

    # v9.0 JARVIS modules
    svc.register('advanced_system', 'modules.advanced_system_control',
                 ['AdvancedSystemController', 'create_advanced_system_controller'])
    svc.register('window_manager', 'modules.window_manager',
                 ['WindowManager', 'create_window_manager'])
    svc.register('gui_automator', 'modules.gui_automator',
                 ['GUIAutomator', 'create_gui_automator'])

    # v9.0 Week 2
    svc.register('browser_tabs', 'modules.browser_tab_controller',
                 ['BrowserTabController', 'create_browser_tab_controller'])
    svc.register('multi_tab', 'modules.multi_tab_orchestrator',
                 ['MultiTabOrchestrator', 'create_multi_tab_orchestrator'])
    svc.register('gmail', 'modules.gmail_controller',
                 ['GmailController', 'create_gmail_controller'])
    svc.register('calendar', 'modules.calendar_controller',
                 ['CalendarController', 'create_calendar_controller'])

    # v9.0 Week 3
    svc.register('task_orchestrator', 'modules.task_orchestrator',
                 ['TaskOrchestrator', 'get_task_orchestrator'])
    svc.register('screenshot_analyzer', 'modules.screenshot_analysis',
                 ['ScreenshotAnalyzer', 'get_screenshot_analyzer'])
    svc.register('pattern_learner', 'modules.pattern_learning',
                 ['PatternLearner', 'get_pattern_learner'])

    # Week 4
    svc.register('proactive_agent', 'modules.proactive_agent',
                 ['ProactiveAgent', 'get_proactive_agent'])

    # Smart agents
    svc.register('flight_agent', 'modules.agents.flight_agent', ['FlightAgent'])
    svc.register('hotel_agent', 'modules.agents.hotel_agent', ['HotelAgent'])
    svc.register('product_agent', 'modules.agents.product_agent', ['ProductAgent'])
    svc.register('restaurant_agent', 'modules.agents.restaurant_agent', ['RestaurantAgent'])
    svc.register('email_agent', 'modules.agents.email_agent', ['EmailAgent'])
    svc.register('calendar_agent', 'modules.agents.calendar_agent', ['CalendarAgent'])

    # v9.0 Ultimate
    svc.register('productivity', 'modules.productivity_tools',
                 ['ProductivityManager', 'AlarmManager', 'ReminderManager',
                  'TimerManager', 'FocusMode', 'InternetSpeedTest', 'BackupManager'])
    svc.register('comet', 'modules.comet_agent',
                 ['CometAgent', 'create_comet_agent', 'QuickActions'])

    # Browser intelligence
    svc.register('page_summarizer', 'modules.page_summarizer',
                 ['PageSummarizer', 'get_page_summarizer'])
    svc.register('youtube_summarizer', 'modules.youtube_summarizer',
                 ['YouTubeSummarizer', 'get_youtube_summarizer'])

    # v11.0 Gap Analysis
    svc.register('vector_memory', 'modules.vector_memory',
                 ['VectorMemorySystem', 'get_vector_memory'])
    svc.register('rag_engine', 'modules.rag_engine',
                 ['RAGEngine', 'get_rag_engine'])
    svc.register('mcp_client', 'modules.mcp_client',
                 ['MCPClient', 'get_mcp_client'])
    svc.register('agent_collab', 'modules.agent_collaboration',
                 ['AgentCollaborationHub', 'get_collaboration_hub'])
    svc.register('specialist_pool', 'modules.agents.specialist_pool',
                 ['SpecialistPool', 'get_specialist_pool', 'init_specialist_pool', 'SPECIALIST_CAPABILITIES'])
    svc.register('realtime_voice', 'modules.realtime_voice',
                 ['RealTimeVoiceEngine', 'get_realtime_voice', 'VoiceConfig'])
    svc.register('computer_use', 'modules.computer_use_agent',
                 ['ComputerUseAgent', 'get_computer_use_agent'])
    svc.register('dynamic_prompts', 'modules.dynamic_prompts',
                 ['DynamicPromptBuilder', 'get_prompt_builder'])
    svc.register('token_optimizer', 'modules.token_optimizer',
                 ['TokenOptimizer', 'get_token_optimizer'])
    svc.register('webhook', 'modules.webhook_manager',
                 ['WebhookManager', 'get_webhook_manager'])
    svc.register('self_modifier', 'modules.self_modifier',
                 ['SelfModifyingEngine', 'get_self_mod_engine'])

    # Desktop control
    svc.register('desktop_ctrl', 'modules.desktop_control',
                 ['SmartFileFinder', 'WindowController', 'SmartBrowser',
                  'DesktopController', 'get_file_finder', 'get_window_controller',
                  'get_smart_browser', 'get_desktop_controller'])

    # Browser-gateway inspired
    svc.register('heartbeat', 'modules.heartbeat_system',
                 ['HeartbeatSystem', 'DailyMemoryLog', 'get_heartbeat_system'])
    svc.register('context_compact', 'modules.context_compaction',
                 ['ContextCompactor', 'estimate_tokens', 'should_compact'])
    svc.register('model_failover', 'modules.model_failover',
                 ['ModelFailoverChain'])
    svc.register('pipelines', 'modules.workflow_pipelines',
                 ['PipelineRunner', 'PipelineBuilder', 'get_runner'])
    svc.register('event_hooks', 'modules.event_hooks',
                 ['HookManager', 'get_hook_manager',
                  'emit_event', 'emit_command_event',
                  'emit_agent_event', 'emit_voice_event', 'EventType'])

    # Spotify / Smart Home
    svc.register('spotify', 'modules.spotify_controller', ['SpotifyController'])
    svc.register('smart_home', 'modules.smart_home', ['SmartHomeHub'])
    svc.register('alexa_server', 'integrations.alexa_server', ['AlexaSkillServer'])
    svc.register(
        'openclaw_gateway',
        'integrations.openclaw_gateway',
        ['OpenClawGateway', 'OpenClawConfig', 'get_openclaw_gateway'],
        env_flag='LADA_OPENCLAW_MODE',
    )
    svc.register(
        'openclaw_skills',
        'integrations.openclaw_skills',
        ['SkillsManager', 'get_skills_manager', 'load_skills', 'match_skill'],
        env_flag='LADA_OPENCLAW_MODE',
    )
    svc.register('lada_browser_adapter', 'integrations.lada_browser_adapter',
                 ['LadaBrowserAdapter', 'get_lada_browser_adapter', 'lada_browser_adapter_enabled'])
    svc.register('stealth_browser', 'modules.stealth_browser',
                 ['StealthBrowser', 'StealthConfig', 'get_stealth_browser'])

    # Orchestration
    svc.register('advanced_planner', 'modules.advanced_planner', ['AdvancedPlanner'])
    svc.register('skill_generator', 'modules.skill_generator', ['SkillGenerator'])

    # Standalone runtime foundations
    svc.register('standalone_contracts', 'modules.standalone.contracts',
                 ['CommandEnvelope', 'EventEnvelope', 'CommandResult'])
    svc.register('standalone_bus', 'modules.standalone.command_bus',
                 ['InMemoryCommandBus', 'RedisStreamsCommandBus', 'create_command_bus'])
    svc.register('standalone_orchestrator', 'modules.standalone.orchestrator',
                 ['StandaloneOrchestrator', 'create_orchestrator'])

    # Gap-closing: wire existing dormant modules
    svc.register('image_gen', 'modules.image_generation',
                 ['ImageGenerator', 'get_image_generator'])
    svc.register('video_gen', 'modules.video_generation',
                 ['VideoGenerator', 'get_video_generator'])
    svc.register('code_sandbox', 'modules.code_sandbox',
                 ['CodeSandbox', 'ExecutionMode', 'ExecutionResult'])
    svc.register('document_reader', 'modules.document_reader',
                 ['DocumentReader'])
    svc.register('deep_research', 'modules.deep_research',
                 ['DeepResearchEngine'])
    svc.register('visual_grounding', 'modules.visual_grounding',
                 ['VisualGrounding'])
    svc.register('page_vision', 'modules.page_vision',
                 ['PageVision'])
    svc.register('sentiment', 'modules.sentiment_analysis',
                 ['SentimentAnalyzer'])
    svc.register('weather_briefing', 'modules.weather_briefing',
                 ['WeatherBriefing'])
    svc.register('focus_modes', 'modules.focus_modes',
                 ['FocusModeManager'])
    svc.register('citation', 'modules.citation_engine',
                 ['CitationEngine'])
    svc.register('export', 'modules.export_manager',
                 ['ExportManager'])
    svc.register('canvas', 'modules.canvas_widget',
                 ['AICanvas', 'CanvasState', 'ContentType', 'create_canvas'])

    return svc
