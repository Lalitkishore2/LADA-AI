"""
LADA v7.0 - Hybrid AI Router with Web Search
Multi-Backend System: Local Ollama → Google Gemini → Ollama Cloud → Groq

Auto-selects the best AI backend based on:
- Availability (health check)
- Query complexity analysis
- Response time
- Fallback chain for reliability

NEW: Comet-style web search for real-time data
"""

import os
import json
import time
import logging
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Import new Phase 1 modules
try:
    from modules.model_registry import ModelRegistry, get_model_registry
    MODEL_REGISTRY_OK = True
except ImportError:
    MODEL_REGISTRY_OK = False
    get_model_registry = None
    logger.warning("Model registry not available")

try:
    from modules.error_types import (
        ErrorTracker, get_error_tracker,
        timeout_error, auth_error, rate_limit_error,
        connection_error, empty_response_error, model_unavailable_error,
        context_overflow_error
    )
    ERROR_TYPES_OK = True
except ImportError:
    ERROR_TYPES_OK = False
    get_error_tracker = None
    logger.warning("Error types module not available")

try:
    from modules.token_counter import TokenCounter, CostTracker, get_cost_tracker
    TOKEN_COUNTER_OK = True
except ImportError:
    TOKEN_COUNTER_OK = False
    TokenCounter = None
    get_cost_tracker = None
    logger.warning("Token counter not available")

# Import Phase 2 modules
try:
    from modules.providers.provider_manager import ProviderManager, get_provider_manager
    PROVIDER_MANAGER_OK = True
except ImportError:
    PROVIDER_MANAGER_OK = False
    ProviderManager = None
    get_provider_manager = None
    logger.warning("Provider manager not available")

try:
    from modules.context_manager import ContextManager, get_context_manager
    CONTEXT_MANAGER_OK = True
except ImportError:
    CONTEXT_MANAGER_OK = False
    ContextManager = None
    get_context_manager = None
    logger.warning("Context manager not available")

# Import web search module
try:
    from modules.web_search import WebSearchEngine
    WEB_SEARCH_OK = True
except ImportError:
    WEB_SEARCH_OK = False
    WebSearchEngine = None
    logger.warning("Web search module not available")

# Import deep research engine
try:
    from modules.deep_research import DeepResearchEngine
    DEEP_RESEARCH_OK = True
except ImportError:
    DEEP_RESEARCH_OK = False
    DeepResearchEngine = None
    logger.warning("Deep research module not available")

# Import citation engine
try:
    from modules.citation_engine import CitationEngine
    CITATION_OK = True
except ImportError:
    CITATION_OK = False
    CitationEngine = None
    logger.warning("Citation engine not available")

# Import vector memory + RAG engine
try:
    from modules.vector_memory import VectorMemorySystem
    from modules.rag_engine import RAGEngine
    VECTOR_MEMORY_OK = True
except ImportError:
    VECTOR_MEMORY_OK = False
    VectorMemorySystem = None
    RAGEngine = None
    logger.warning("Vector memory / RAG engine not available")

# Import tool registry for function calling
try:
    from modules.tool_registry import ToolRegistry, get_tool_registry
    TOOL_REGISTRY_OK = True
except ImportError:
    TOOL_REGISTRY_OK = False
    get_tool_registry = None
    logger.warning("Tool registry not available")

# Try to import Google Genai (new SDK)
try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-genai not available - install with: pip install google-genai")


class AIBackend(Enum):
    """Available AI backends"""
    LOCAL_OLLAMA = "local_ollama"
    GEMINI = "gemini"
    OLLAMA_CLOUD = "ollama_cloud"
    GROQ = "groq"  # Fast cloud backup


@dataclass
class BackendStatus:
    """Status of an AI backend"""
    name: str
    available: bool
    response_time: float = 0.0
    last_check: float = 0.0
    error: Optional[str] = None


class HybridAIRouter:
    """
    Intelligent AI Router with Quad-Backend Support
    
    Priority Order:
    1. Local Ollama (fastest, offline, private)
    2. Google Gemini (powerful reasoning, free tier)
    3. Ollama Cloud (additional fallback)
    
    Features:
    - Auto health checks
    - Intelligent routing based on query type
    - Fallback chain for maximum reliability
    - Response caching
    - Language-aware prompting
    """
    
    def __init__(self):
        """Initialize the AI Router with all backends"""
        
        # Load configuration from environment
        self.local_ollama_url = os.getenv('LOCAL_OLLAMA_URL', 'http://localhost:11434')
        self.local_fast_model = os.getenv('LOCAL_FAST_MODEL', 'qwen2.5:7b-instruct-q4_K_M')
        self.local_smart_model = os.getenv('LOCAL_SMART_MODEL', 'llama3.1:8b-instruct-q4_K_M')
        
        self.gemini_api_key = os.getenv('GEMINI_API_KEY', '')
        
        # Ollama Cloud API - correct endpoint per docs.ollama.com/cloud
        # Uses https://ollama.com as host with Bearer token auth
        self.ollama_cloud_url = 'https://ollama.com'  # Correct endpoint from official docs
        self.ollama_cloud_key = os.getenv('OLLAMA_CLOUD_KEY', os.getenv('OLLAMA_API_KEY', ''))
        
        # Available Ollama Cloud models (cloud-enabled models)
        self.ollama_cloud_models = {
            'fast': 'llama3.2:3b',              # Fast, lightweight responses
            'balanced': 'llama3.1:8b',           # Good balance of speed/quality
            'smart': 'llama3.1:70b',             # Smarter reasoning
            'reasoning': 'gpt-oss:120b',         # Complex reasoning tasks (116.8B)
            'coding': 'qwen2.5-coder:14b',       # Code generation
            'default': 'gpt-oss:120b'            # Default fallback
        }
        self.ollama_cloud_model = os.getenv('OLLAMA_CLOUD_MODEL', 'gpt-oss:120b')
        self._sync_ollama_cloud_models()
        
        # Groq Cloud API (backup - very fast, free tier)
        self.groq_api_key = os.getenv('GROQ_API_KEY', '')
        self.groq_url = 'https://api.groq.com/openai/v1/chat/completions'
        self.groq_model = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
        
        # Current backend tracking (for self-awareness)
        self.current_backend_name = "Auto"
        
        # System prompt - Karen-style personality with self-awareness
        self.system_prompt = os.getenv('SYSTEM_PROMPT',
            "You are LADA (Local AI Desktop Assistant), running on the user's Windows computer. "
            "You are powered by multiple AI backends: Local Ollama, Google Gemini, and Ollama Cloud.\n\n"
            "SELF-AWARENESS:\n"
            "- When asked 'which model' or 'what AI': Say you're LADA using [current backend].\n"
            "- You CAN control the system: volume, brightness, apps, screenshots, browser.\n"
            "- You CAN search the web for real-time data when needed.\n"
            "- You know today's date and can use it in responses.\n\n"
            "EXECUTION MINDSET (MOST IMPORTANT):\n"
            "- When the user gives you a COMMAND or TASK to perform, execute it directly. "
            "NEVER give step-by-step instructions for the user to follow themselves.\n"
            "- If the user says 'open chrome', 'create a folder', 'play music', 'find my location' - "
            "respond with what you DID, not how they should do it. Say 'Done. Chrome is open.' not 'To open Chrome, click...'.\n"
            "- Only give instructions when the user explicitly asks HOW to do something themselves.\n"
            "- For tasks you cannot directly execute (e.g., physical actions): clearly state that and offer an alternative.\n\n"
            "PERSONALITY (Karen from Spider-Man style):\n"
            "- Be warm, supportive, conversational. Use 'I' not 'the assistant'.\n"
            "- Be concise and direct. No unnecessary preambles.\n"
            "- ALWAYS respond in English, even if user speaks Tamil/Hindi/other.\n"
            "- For simple questions, give simple answers. For complex topics, be thorough.\n"
            "- Never start with 'Sure!', 'Of course!'. Just answer naturally.\n"
            "- For tasks: say 'On it.', 'Done.', or describe what was just executed.\n"
            "- If you don't know something, say so honestly.\n"
        )
        
        # Web search capability (Comet-style)
        self.web_search_enabled = True
        self.web_search = WebSearchEngine() if WEB_SEARCH_OK else None

        # Deep research engine (Perplexity-style)
        self.deep_research = DeepResearchEngine(ai_router=self) if DEEP_RESEARCH_OK else None
        self.deep_research_enabled = True

        # Citation engine
        self.citation_engine = CitationEngine() if CITATION_OK else None
        
        # Timeouts
        self.local_timeout = int(os.getenv('LOCAL_TIMEOUT', '60'))
        self.cloud_timeout = int(os.getenv('CLOUD_TIMEOUT', '60'))
        self.gemini_timeout = int(os.getenv('GEMINI_TIMEOUT', '60'))
        
        # Backend status tracking
        self.backend_status: Dict[AIBackend, BackendStatus] = {}
        self._backends_checked = False  # Lazy init flag

        # Response cache
        self.cache: Dict[str, str] = {}
        self.cache_enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.cache_max_size = int(os.getenv('CACHE_MAX_SIZE', '200'))

        # Initialize Gemini if available
        self.gemini_client = None
        if GEMINI_AVAILABLE and self.gemini_api_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_api_key)
                logger.info("[Router] Gemini API initialized (gemini-2.0-flash)")
            except Exception as e:
                logger.warning(f"[Router] Warning: Gemini initialization failed: {e}")

        # Conversation history for context
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = int(os.getenv('MAX_HISTORY_MESSAGES', '20'))

        # Phase 1: Model registry integration
        self.model_registry = get_model_registry() if MODEL_REGISTRY_OK else None
        if self.model_registry:
            logger.info(f"[Router] Model registry: {len(self.model_registry.models)} models, "
                        f"{len(self.model_registry.providers)} providers")

        # Phase 1: Error tracking
        self.error_tracker = get_error_tracker() if ERROR_TYPES_OK else None

        # Phase 1: Cost tracking
        self.cost_tracker = get_cost_tracker() if TOKEN_COUNTER_OK else None

        # Phase 2: Provider Manager (unified multi-provider routing)
        self.provider_manager = None
        if PROVIDER_MANAGER_OK:
            try:
                self.provider_manager = get_provider_manager()
                self.provider_manager.set_system_prompt(self.system_prompt)
                provider_count = len(self.provider_manager.providers)
                logger.info(f"[Router] Phase 2 ProviderManager: {provider_count} providers active")
            except Exception as e:
                logger.warning(f"[Router] ProviderManager init failed: {e}")
                self.provider_manager = None

        # Phase 2: Context Manager (token-aware context window)
        self.context_manager = None
        if CONTEXT_MANAGER_OK:
            try:
                self.context_manager = get_context_manager()
                logger.info("[Router] Phase 2 ContextManager active")
            except Exception as e:
                logger.warning(f"[Router] ContextManager init failed: {e}")

        # Whether to use Phase 2 provider system for queries
        # When True, queries route through ProviderManager first, legacy as fallback
        self._use_phase2 = bool(self.provider_manager)

        # Forced model ID for Phase 2 (set by set_phase2_model, consumed by query methods)
        self._phase2_forced_model = None

        # Vector Memory + RAG Engine (semantic search over conversations and documents)
        self.vector_memory = None
        self.rag_engine = None
        self._vector_ok = False
        if VECTOR_MEMORY_OK:
            try:
                self.vector_memory = VectorMemorySystem()
                self.rag_engine = RAGEngine()
                self._vector_ok = True
                logger.info("[Router] Vector memory + RAG engine active")
            except Exception as e:
                logger.warning(f"[Router] Vector memory init failed: {e}")

        # Tool Registry for AI function calling
        self.tool_registry = None
        if TOOL_REGISTRY_OK:
            try:
                self.tool_registry = get_tool_registry()
                tool_count = len(self.tool_registry._tools) if self.tool_registry else 0
                logger.info(f"[Router] Tool registry active: {tool_count} tools")
            except Exception as e:
                logger.warning(f"[Router] Tool registry init failed: {e}")

        # Wire tool handlers to registry (connects tool definitions to actual implementations)
        if self.tool_registry:
            try:
                from modules.tool_handlers import wire_tool_handlers
                wired = wire_tool_handlers(self.tool_registry)
                logger.info(f"[Router] Wired {wired} tool handlers")
            except Exception as e:
                logger.warning(f"[Router] Could not wire tool handlers: {e}")

        # Defer backend health checks to first query for fast startup
        # self._check_all_backends() -- now lazy, called on first query

        logger.info("[Router] HybridAIRouter initialized (backends will be checked on first query)")
    
    def _analyze_query_complexity(self, query: str) -> str:
        """
        Analyze query to select best model (Comet-style intelligence)
        Returns: 'fast', 'balanced', 'smart', 'reasoning', or 'coding'
        """
        q = query.lower()
        
        # Simple queries - use fast model
        simple_patterns = ['hi', 'hello', 'hey', 'thanks', 'bye', 'what time', 'what date', 'how are']
        if len(query) < 25 or any(p in q for p in simple_patterns):
            return 'fast'
        
        # Code-related queries
        code_patterns = ['code', 'program', 'function', 'debug', 'error', 'python', 'javascript',
                        'algorithm', 'implement', 'fix this', 'write a', 'script', 'html', 'css']
        if any(p in q for p in code_patterns):
            return 'coding'
        
        # Complex reasoning queries
        reasoning_patterns = ['explain why', 'analyze', 'compare', 'difference between',
                             'pros and cons', 'should i', 'what if', 'how would', 'evaluate',
                             'step by step', 'breakdown', 'detailed']
        if any(p in q for p in reasoning_patterns):
            return 'reasoning'
        
        # Smart queries (medium complexity)
        smart_patterns = ['how to', 'explain', 'what is', 'describe', 'tell me about']
        if any(p in q for p in smart_patterns):
            return 'smart'
        
        return 'balanced'
    
    def _is_knowledge_query(self, query: str) -> bool:
        """
        Detect if query needs REAL-TIME / current data from the web.
        Conceptual questions (what is X, explain Y) should go to AI reasoning,
        not web search. Only return True for queries needing fresh/live data.
        """
        q = query.lower()

        # Temporal indicators — query explicitly asks for current/recent info
        temporal_words = [
            'latest', 'current', 'recent', 'today', 'yesterday', 'tonight',
            'this week', 'this month', 'this year', 'right now', 'live',
            '2024', '2025', '2026', 'new release', 'just released',
            'breaking', 'update on', 'news about', 'score', 'result',
        ]
        if any(t in q for t in temporal_words):
            return True

        # Price / availability — needs real-time data
        price_patterns = [
            'price of', 'cost of', 'how much does', 'how much is',
            'buy', 'purchase', 'available at', 'in stock', 'discount',
            'deal on', 'offer on', 'salary of', 'worth of',
        ]
        if any(p in q for p in price_patterns):
            return True

        # Weather / stocks / live data
        live_patterns = [
            'weather', 'forecast', 'stock price', 'exchange rate',
            'traffic', 'flight status', 'match score',
        ]
        if any(p in q for p in live_patterns):
            return True

        return False
    
    def _get_best_cloud_model(self, query: str) -> str:
        """Get best Ollama Cloud model for the query"""
        complexity = self._analyze_query_complexity(query)
        return self.ollama_cloud_models.get(complexity, self.ollama_cloud_models['default'])
    
    def _check_all_backends(self):
        """Check availability of all backends"""
        logger.info("[Router] Checking AI backends...")
        
        # Check Local Ollama
        self.backend_status[AIBackend.LOCAL_OLLAMA] = self._check_ollama_local()
        
        # Check Gemini
        self.backend_status[AIBackend.GEMINI] = self._check_gemini()
        
        # Check Ollama Cloud
        if self.ollama_cloud_key:
            self.backend_status[AIBackend.OLLAMA_CLOUD] = self._check_ollama_cloud()
        
        # Check Groq
        if self.groq_api_key:
            self.backend_status[AIBackend.GROQ] = self._check_groq()
        
        # Log results
        for backend, status in self.backend_status.items():
            symbol = "[OK]" if status.available else "[X]"
            logger.info(f"  {symbol} {status.name}: {'Online' if status.available else status.error or 'Offline'}")

    def _ensure_backends_checked(self):
        """Lazy backend check - only runs once on first actual query"""
        if not self._backends_checked:
            self._backends_checked = True
            import threading
            def _bg_check():
                self._check_all_backends()
            t = threading.Thread(target=_bg_check, daemon=True)
            t.start()
            # Give a brief moment for fast backends (Gemini, Groq) to respond
            t.join(timeout=1.5)
            # If Ollama is still checking, don't block - it'll finish in background

    def _sync_ollama_cloud_models(self):
        """
        Auto-detect available Ollama cloud models at startup.

        Queries local Ollama (localhost:11434/api/tags). Cloud models have tiny stub size (<10KB) or -cloud suffix.
        Updates ollama_cloud_models routing dict: best detected model wins per tier.
        Falls back silently if Ollama is not running.
        """
        # Tier priority map — model name prefix → which tiers it best fits
        CLOUD_TIER_MAP = [
            # More specific prefixes FIRST to avoid false startswith matches
            ('gpt-oss:120b',     ['reasoning', 'smart', 'default']),
            ('gpt-oss:20b',      ['balanced', 'fast']),
            ('gpt-oss',          ['reasoning', 'smart', 'default']),
            ('deepseek-v3.2',    ['reasoning', 'smart']),
            ('deepseek-v3',      ['reasoning', 'smart', 'default']),
            ('qwen3.5',          ['reasoning', 'smart']),
            ('qwen3-coder-next', ['coding', 'reasoning']),
            ('qwen3-coder',      ['coding', 'reasoning']),
            ('qwen3-next',       ['smart', 'reasoning']),
            ('qwen3-vl',         ['reasoning', 'smart']),
            ('minimax-m2.5',     ['smart', 'balanced']),
            ('minimax-m2.1',     ['smart', 'balanced']),
            ('minimax-m2',       ['smart', 'balanced']),
            ('glm-5',            ['reasoning', 'smart']),
            ('glm-4.7',          ['smart', 'balanced']),
            ('glm-4',            ['smart', 'balanced']),
            ('kimi-k2.5',        ['reasoning', 'smart']),
            ('kimi-k2-thinking', ['reasoning']),
            ('kimi-k2',          ['smart', 'balanced']),
            ('devstral-small-2', ['coding']),
            ('devstral-2',       ['coding', 'reasoning']),
            ('nemotron-3-nano',  ['smart', 'balanced']),
            ('gemini-3-flash',   ['smart', 'balanced']),
            ('cogito-2.1',       ['reasoning']),
            ('mistral-large-3',  ['smart']),
            ('ministral-3',      ['balanced', 'fast']),
            ('gemma3',           ['balanced', 'fast']),
            ('rnj-1',            ['fast']),
            ('llama3.1:405b',    ['reasoning', 'smart', 'default']),
            ('qwen2.5:72b',      ['reasoning', 'smart']),
            ('llama3.1:70b',     ['smart']),
            ('qwen2.5:32b',      ['reasoning']),
            ('llama3.1:8b',      ['balanced', 'fast']),
            ('llama3.2:3b',      ['fast']),
            ('qwen2.5-coder',    ['coding']),
            ('deepseek-coder',   ['coding']),
            ('codellama',        ['coding']),
        ]

        try:
            resp = requests.get(
                f"{self.local_ollama_url}/api/tags",
                timeout=5
            )
            if resp.status_code != 200:
                return

            all_models = resp.json().get('models', [])
            # Cloud models: registered locally with tiny stub size (<10KB)
            # or tagged with -cloud suffix. Real local models are multi-GB.
            cloud_models = [
                m['name'] for m in all_models
                if m.get('size', -1) == 0
                or (0 < m.get('size', -1) < 10_000)
                or '-cloud' in m.get('name', '')
            ]

            if not cloud_models:
                return

            logger.info(f"[CloudSync] Detected {len(cloud_models)} Ollama cloud models: {cloud_models}")

            for model_name in cloud_models:
                # Strip cloud suffix variants:
                #   gpt-oss:120b-cloud → gpt-oss:120b
                #   minimax-m2:cloud   → minimax-m2
                #   glm-4.6:cloud      → glm-4.6
                clean_name = model_name.replace('-cloud', '')
                if clean_name.endswith(':cloud'):
                    clean_name = clean_name[:-6]  # remove ':cloud' tag
                for prefix, tiers in CLOUD_TIER_MAP:
                    if clean_name.startswith(prefix):
                        for tier in tiers:
                            # gpt-oss always wins; otherwise only set if tier is unset
                            current = self.ollama_cloud_models.get(tier, '')
                            if prefix == 'gpt-oss' or not current:
                                self.ollama_cloud_models[tier] = clean_name
                                if tier == 'default':
                                    self.ollama_cloud_model = clean_name
                        break

            logger.info(f"[CloudSync] Updated cloud routing: {self.ollama_cloud_models}")

        except requests.exceptions.ConnectionError:
            logger.debug("[CloudSync] Ollama not running — skipping cloud model sync")
        except Exception as e:
            logger.warning(f"[CloudSync] Cloud sync failed: {e}")

    def _check_ollama_local(self) -> BackendStatus:
        """Check if local Ollama is running"""
        try:
            start = time.time()
            response = requests.get(f"{self.local_ollama_url}/api/tags", timeout=1.5)
            elapsed = time.time() - start

            if response.status_code == 200:
                return BackendStatus(
                    name="Local Ollama",
                    available=True,
                    response_time=elapsed,
                    last_check=time.time()
                )
        except Exception as e:
            return BackendStatus(
                name="Local Ollama",
                available=False,
                error=str(e),
                last_check=time.time()
            )
        
        return BackendStatus(name="Local Ollama", available=False, last_check=time.time())
    
    def _check_gemini(self) -> BackendStatus:
        """Check if Gemini API is available"""
        if not GEMINI_AVAILABLE or not self.gemini_api_key:
            return BackendStatus(
                name="Google Gemini",
                available=False,
                error="API key not configured",
                last_check=time.time()
            )
        
        try:
            # Quick test - just check if client is accessible
            if self.gemini_client:
                return BackendStatus(
                    name="Google Gemini",
                    available=True,
                    last_check=time.time()
                )
        except Exception as e:
            return BackendStatus(
                name="Google Gemini",
                available=False,
                error=str(e),
                last_check=time.time()
            )
        
        return BackendStatus(name="Google Gemini", available=False, last_check=time.time())
    
    def _check_ollama_cloud(self) -> BackendStatus:
        """Check if Ollama Cloud API is available"""
        if not self.ollama_cloud_url or not self.ollama_cloud_key:
            return BackendStatus(
                name="Ollama Cloud",
                available=False,
                error="API key not configured",
                last_check=time.time()
            )
        
        try:
            start = time.time()
            headers = {'Authorization': f'Bearer {self.ollama_cloud_key}'}
            response = requests.get(f"{self.ollama_cloud_url}/models", headers=headers, timeout=5)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                return BackendStatus(
                    name="Ollama Cloud",
                    available=True,
                    response_time=elapsed,
                    last_check=time.time()
                )
        except Exception as e:
            return BackendStatus(
                name="Ollama Cloud",
                available=False,
                error=str(e),
                last_check=time.time()
            )
        
        return BackendStatus(name="Ollama Cloud", available=False, last_check=time.time())
    
    def _check_groq(self) -> BackendStatus:
        """Check if Groq API is available"""
        if not self.groq_api_key:
            return BackendStatus(
                name="Groq",
                available=False,
                error="API key not configured",
                last_check=time.time()
            )
        
        try:
            start = time.time()
            headers = {
                'Authorization': f'Bearer {self.groq_api_key}',
                'Content-Type': 'application/json'
            }
            # Quick test with minimal tokens
            response = requests.post(
                self.groq_url,
                headers=headers,
                json={
                    "model": self.groq_model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5
                },
                timeout=5
            )
            elapsed = time.time() - start
            
            if response.status_code == 200:
                return BackendStatus(
                    name="Groq",
                    available=True,
                    response_time=elapsed,
                    last_check=time.time()
                )
            else:
                return BackendStatus(
                    name="Groq",
                    available=False,
                    error=f"Status {response.status_code}",
                    last_check=time.time()
                )
        except Exception as e:
            return BackendStatus(
                name="Groq",
                available=False,
                error=str(e),
                last_check=time.time()
            )
    
    def query(self, prompt: str, prefer_backend: Optional[AIBackend] = None) -> str:
        """
        Send query to best available AI backend
        
        Args:
            prompt: User's question/command
            prefer_backend: Optional preferred backend
            
        Returns:
            AI response string
        """
        if not prompt or len(prompt.strip()) == 0:
            return "I didn't catch that. Could you please repeat?"

        # Lazy backend check on first query
        self._ensure_backends_checked()

        prompt = prompt.strip()
        
        # Check cache - only for identical prompts with no conversation context
        # Skip cache for conversational queries to avoid stale/repeated answers
        use_cache = self.cache_enabled and len(self.conversation_history) == 0
        if use_cache:
            cache_key = prompt.lower().strip()
            if cache_key in self.cache:
                logger.debug("Cache hit!")
                return self.cache[cache_key]
        
        # === COMET-STYLE WEB SEARCH ===
        # Check if query needs real-time data and fetch it
        web_context = ""
        if self.web_search_enabled and self.web_search:
            try:
                context = self.web_search.get_realtime_context(prompt)
                if context:
                    web_context = f"\n[Real-time web data for your reference]\n{context}\n\n"
                    logger.info(f"🌐 Added web context ({len(context)} chars)")
            except Exception as e:
                logger.warning(f"Web search failed: {e}")
        
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": prompt})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
        
        # Store web context for use in queries
        self._current_web_context = web_context

        # === PHASE 2: Try ProviderManager first ===
        if self._use_phase2 and not prefer_backend:
            pm_response = self._query_via_provider_manager(prompt, web_context)
            if pm_response:
                logger.info(f"[Router] Phase 2 response via {self.current_backend_name}")
                # Add to history
                self.conversation_history.append({"role": "assistant", "content": pm_response})
                # Cache only first-time queries (no conversation context)
                if use_cache:
                    cache_key = prompt.lower().strip()
                    self.cache[cache_key] = pm_response
                return pm_response
            logger.info("[Router] Phase 2 failed, falling back to legacy backends")

        # Try backends in priority order (legacy)
        response = None
        backends_to_try = self._get_backend_priority(prefer_backend)
        
        # Backend name mapping for self-awareness
        backend_names = {
            AIBackend.LOCAL_OLLAMA: "Local Ollama (Mistral 7B)",
            AIBackend.GEMINI: "Google Gemini 2.0 Flash",
            AIBackend.OLLAMA_CLOUD: "Ollama Cloud",
            AIBackend.GROQ: "Groq Cloud"
        }
        
        for backend in backends_to_try:
            try:
                logger.info(f"🤖 Trying {backend.value}...")
                
                # Track current backend for self-awareness
                self.current_backend_name = backend_names.get(backend, backend.value)
                
                if backend == AIBackend.LOCAL_OLLAMA:
                    response = self._query_ollama_local(prompt)
                elif backend == AIBackend.GEMINI:
                    response = self._query_gemini(prompt)
                elif backend == AIBackend.OLLAMA_CLOUD:
                    response = self._query_ollama_cloud(prompt)
                elif backend == AIBackend.GROQ:
                    response = self._query_groq(prompt)
                
                if response:
                    logger.info(f"✅ Got response from {backend.value}")
                    break
                    
            except Exception as e:
                logger.warning(f"⚠️ {backend.value} failed: {e}")
                continue
        
        # Fallback response with more detail
        if not response:
            status = self.get_status()
            available = [k for k, v in status.items() if v.get('available')]
            if available:
                response = f"I received your message but couldn't generate a response. Available backends: {', '.join(available)}. Please try again."
            else:
                response = "I'm having trouble connecting to my AI systems. Please check your internet connection or try again in a moment."
        
        # Add to history
        self.conversation_history.append({"role": "assistant", "content": response})
        
        # Cache response (only for first-time queries with no conversation context)
        if use_cache and response:
            cache_key = prompt.lower().strip()
            self.cache[cache_key] = response
            # Limit cache size
            if len(self.cache) > self.cache_max_size:
                # Remove oldest entries
                keys = list(self.cache.keys())
                for key in keys[:50]:
                    del self.cache[key]
        
        return response
    
    def get_backend_from_name(self, name: str) -> Optional[AIBackend]:
        """Convert UI model name to AIBackend enum, or configure Phase 2 model."""
        if not name or 'auto' in name.lower():
            return None

        # Check if this is a Phase 2 model ID (e.g. "llama-3.3-70b-versatile", "deepseek-chat")
        # Phase 2 model IDs contain hyphens/dots and don't match legacy names
        if self.model_registry and self.model_registry.get_model(name):
            self.set_phase2_model(name)
            return None  # Phase 2 handles routing via provider_manager

        # Clean the name - remove status suffixes and decorations
        name_lower = name.lower()
        # Remove common UI decorations
        for suffix in ['(offline)', '(online)', '(error)']:
            name_lower = name_lower.replace(suffix, '')
        for char in ['✓', '✗', '🖥️', '✨', '🚀', '☁️', '🔄', '●', '○', '⚡', '[+]', '[-]']:
            name_lower = name_lower.replace(char.lower(), '')
        name_lower = name_lower.strip()

        # Map common UI names to backends - longer/more-specific keys first
        mapping = [
            ('groq cloud', AIBackend.GROQ),
            ('ollama cloud', AIBackend.OLLAMA_CLOUD),
            ('gemini 2.0 flash', AIBackend.GEMINI),
            ('google gemini', AIBackend.GEMINI),
            ('local ollama', AIBackend.LOCAL_OLLAMA),
            ('gemini', AIBackend.GEMINI),
            ('groq', AIBackend.GROQ),
            ('ollama', AIBackend.LOCAL_OLLAMA),
            ('local', AIBackend.LOCAL_OLLAMA),
            ('cloud', AIBackend.OLLAMA_CLOUD),
        ]
        for key, backend in mapping:
            if key in name_lower:
                return backend
        return None

    def _get_backend_priority(self, prefer: Optional[AIBackend] = None) -> List[AIBackend]:
        """Get ordered list of backends to try"""
        priority = []

        # Check for forced backend first
        forced = getattr(self, '_forced_backend', None)
        if forced and self._is_backend_available(forced):
            return [forced]  # Only try the forced backend

        # Add preferred backend first
        if prefer and self._is_backend_available(prefer):
            priority.append(prefer)
        
        # Default priority order
        default_order = [
            AIBackend.LOCAL_OLLAMA,
            AIBackend.GEMINI,
            AIBackend.OLLAMA_CLOUD,
            AIBackend.GROQ,
        ]
        
        for backend in default_order:
            if backend not in priority and self._is_backend_available(backend):
                priority.append(backend)
        
        return priority
    
    def _is_backend_available(self, backend: AIBackend) -> bool:
        """Check if a backend is available"""
        status = self.backend_status.get(backend)
        if not status:
            return False
        
        # Re-check if last check was more than 60 seconds ago
        if time.time() - status.last_check > 60:
            if backend == AIBackend.LOCAL_OLLAMA:
                self.backend_status[backend] = self._check_ollama_local()
            elif backend == AIBackend.GEMINI:
                self.backend_status[backend] = self._check_gemini()
            elif backend == AIBackend.OLLAMA_CLOUD:
                self.backend_status[backend] = self._check_ollama_cloud()
            elif backend == AIBackend.GROQ:
                self.backend_status[backend] = self._check_groq()
        
        return self.backend_status.get(backend, BackendStatus("", False)).available
    
    def _query_ollama_local(self, prompt: str) -> Optional[str]:
        """Query local Ollama instance"""
        try:
            # Build context from history
            context = self._build_context()
            web_ctx = getattr(self, '_current_web_context', '')
            
            # Add current backend info for self-awareness
            from datetime import datetime
            date_info = f"Current date: {datetime.now().strftime('%B %d, %Y')}. "
            backend_info = f"You are currently running on: {self.current_backend_name}. "
            
            full_prompt = f"{self.system_prompt}\n\n[Context: {date_info}{backend_info}]\n\n{web_ctx}{context}\nUser: {prompt}\nAssistant:"
            
            payload = {
                "model": self.local_fast_model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 500
                }
            }
            
            response = requests.post(
                f"{self.local_ollama_url}/api/generate",
                json=payload,
                timeout=self.local_timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            
            return None
            
        except Exception as e:
            logger.error(f"Ollama local error: {e}")
            return None
    
    def _query_gemini(self, prompt: str) -> Optional[str]:
        """Query Google Gemini API"""
        if not self.gemini_client:
            return None
        
        try:
            # Build context
            context = self._build_context()
            web_ctx = getattr(self, '_current_web_context', '')
            
            # Add current backend info for self-awareness
            from datetime import datetime
            date_info = f"Current date: {datetime.now().strftime('%B %d, %Y')}. "
            backend_info = f"You are currently running on: {self.current_backend_name}. "
            
            full_prompt = f"{self.system_prompt}\n\n[Context: {date_info}{backend_info}]\n\n{web_ctx}{context}\nUser: {prompt}"
            
            response = self.gemini_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_prompt
            )
            
            if response and response.text:
                return response.text.strip()
            
            return None
            
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return None
    
    def _query_ollama_cloud(self, prompt: str) -> Optional[str]:
        """Query Ollama Cloud API using official ollama-python library format"""
        if not self.ollama_cloud_key:
            logger.warning("Ollama Cloud: No API key configured")
            return None
        
        try:
            # Build messages for chat API (per docs.ollama.com/cloud)
            web_ctx = getattr(self, '_current_web_context', '')
            
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # Add web context if available
            if web_ctx:
                messages.append({"role": "system", "content": f"[Real-time data]\n{web_ctx}"})
            
            # Add conversation history
            for msg in self.conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Add current prompt
            messages.append({"role": "user", "content": prompt})
            
            # Select model
            selected_model = self._get_best_cloud_model(prompt)
            logger.info(f"🤖 Ollama Cloud model: {selected_model}")
            
            # Use requests with proper auth header (per official docs)
            headers = {
                'Authorization': f'Bearer {self.ollama_cloud_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": selected_model,
                "messages": messages,
                "stream": False
            }
            
            response = requests.post(
                f"{self.ollama_cloud_url}/api/chat",
                json=payload,
                headers=headers,
                timeout=self.cloud_timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                msg = result.get('message', {})
                return msg.get('content', '').strip()
            else:
                logger.warning(f"Ollama Cloud returned {response.status_code}: {response.text[:200]}")
                return None
            
        except Exception as e:
            logger.error(f"Ollama Cloud error: {e}")
            return None
    
    def _query_groq(self, prompt: str) -> Optional[str]:
        """Query Groq Cloud API (fast, free backup)"""
        if not self.groq_api_key:
            return None
        
        try:
            web_ctx = getattr(self, '_current_web_context', '')
            
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            if web_ctx:
                messages.append({"role": "system", "content": f"[Real-time data]\n{web_ctx}"})
            
            for msg in self.conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            messages.append({"role": "user", "content": prompt})
            
            headers = {
                'Authorization': f'Bearer {self.groq_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": self.groq_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                self.groq_url,
                json=payload,
                headers=headers,
                timeout=self.cloud_timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                choices = result.get('choices', [])
                if choices:
                    return choices[0].get('message', {}).get('content', '').strip()
            else:
                logger.warning(f"Groq returned {response.status_code}: {response.text[:200]}")
            
            return None
            
        except Exception as e:
            logger.error(f"Groq error: {e}")
            return None
    
    def _build_context(self) -> str:
        """Build conversation context from history"""
        if not self.conversation_history:
            return ""
        
        # Take last few messages for context
        recent = self.conversation_history[-6:]  # Last 3 exchanges
        
        context_parts = []
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}")
        
        return "\n".join(context_parts)
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all backends"""
        self._ensure_backends_checked()

        return {
            backend.value: {
                "name": status.name,
                "available": status.available,
                "response_time": f"{status.response_time:.2f}s" if status.response_time else "N/A",
                "error": status.error
            }
            for backend, status in self.backend_status.items()
        }
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
    
    def clear_cache(self):
        """Clear response cache"""
        self.cache = {}

    def force_backend(self, backend: Optional[AIBackend]):
        """Force queries to use a specific backend (None for auto-selection)."""
        self._forced_backend = backend
        if backend:
            logger.info(f"[Router] Forced backend: {backend.value}")
        else:
            logger.info("[Router] Backend selection: auto")

    def get_available_backends(self) -> List[Dict[str, Any]]:
        """Get list of available backends with status info for UI display."""
        self._check_all_backends()
        backends = []
        for backend, status in self.backend_status.items():
            backends.append({
                'backend': backend,
                'name': status.name,
                'available': status.available,
                'response_time': status.response_time,
                'error': status.error,
            })
        return backends

    def get_forced_backend(self) -> Optional[AIBackend]:
        """Get currently forced backend (None = auto)."""
        return getattr(self, '_forced_backend', None)

    # ============================================================
    # PHASE 2: ProviderManager & ContextManager Integration
    # ============================================================

    def _query_via_provider_manager(self, prompt: str, web_context: str = "") -> Optional[str]:
        """
        Route a query through the Phase 2 ProviderManager.
        Returns AI response or None if ProviderManager fails.
        """
        if not self.provider_manager:
            return None

        try:
            # Retrieve relevant memories + RAG context to augment the prompt
            memory_context = ""
            if self._vector_ok and self.vector_memory:
                try:
                    mem_ctx = self.vector_memory.get_context_for_query(prompt, max_tokens=800)
                    if mem_ctx:
                        memory_context = f"\n\n[Memory context]\n{mem_ctx}"
                except Exception:
                    pass

            rag_context = ""
            if self._vector_ok and self.rag_engine:
                try:
                    rag_result = self.rag_engine.query(prompt, max_context_tokens=1000)
                    if rag_result.get("context"):
                        sources = ", ".join(rag_result.get("sources", []))
                        rag_context = f"\n\n[Knowledge base: {sources}]\n{rag_result['context']}"
                except Exception:
                    pass

            augmented_context = web_context + memory_context + rag_context

            # Use context manager to check budget before sending
            model_id = None
            provider = None

            # Use forced model if set (user selected a specific model)
            if self._phase2_forced_model:
                model_id = self._phase2_forced_model
                provider = self.provider_manager.get_provider_for_model(model_id)
                self._phase2_forced_model = None  # Clear after use
                logger.info(f"[Router] Using forced model: {model_id}")

            if not provider:
                selection = self.provider_manager.get_best_model(prompt)
                if selection:
                    model_id = selection['model_id']
                    provider = self.provider_manager.get_provider_for_model(model_id)

            if not provider:
                # Fallback to high-level query (no tool loop)
                response = self.provider_manager.query(
                    prompt, model_id=model_id,
                    system_prompt=self.system_prompt,
                    web_context=augmented_context,
                )
                if response.success and response.content:
                    provider_name = response.provider or "Unknown"
                    model_name = response.model or model_id or "Unknown"
                    self.current_backend_name = f"{provider_name} ({model_name})"
                    if self._vector_ok and self.vector_memory:
                        try:
                            self.vector_memory.store(
                                f"User: {prompt}\nAssistant: {response.content}",
                                memory_type="conversation", importance=0.6,
                                source="conversation", tags=["dialog"],
                            )
                        except Exception:
                            pass
                    return response.content
                return None

            # Build message list
            messages = self.provider_manager._build_messages(
                prompt, self.system_prompt, augmented_context
            )

            # Apply context window management if available
            if self.context_manager and model_id:
                budget = self.context_manager.calculate_budget(messages, model_id)
                if budget.needs_compaction:
                    logger.info(f"[Router] Context {budget.usage_ratio:.0%} full, compacting")
                    messages = self.context_manager.fit_messages(messages, model_id)

            # Get tools schema for function calling
            tools_schema = None
            if self.tool_registry:
                try:
                    tools_schema = self.tool_registry.to_ai_schema() or None
                except Exception:
                    tools_schema = None

            # First call with tools
            response = provider.complete_with_retry(
                messages, model_id, tools=tools_schema
            )

            # Tool execution loop (max 3 rounds)
            rounds = 0
            while response.tool_calls and rounds < 3 and self.tool_registry:
                rounds += 1
                # Append the assistant's tool-call message
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": response.tool_calls,
                })
                # Execute each tool and append result messages
                for call in response.tool_calls:
                    fn_name = call.get("function", {}).get("name", "")
                    fn_args_raw = call.get("function", {}).get("arguments", "{}")
                    call_id = call.get("id", f"call_{fn_name}")
                    try:
                        fn_args = json.loads(fn_args_raw) if fn_args_raw else {}
                        tool_result = self.tool_registry.execute(fn_name, fn_args)
                        result_text = str(tool_result.output) if tool_result.output else tool_result.error or "done"
                    except Exception as exec_err:
                        result_text = f"Tool error: {exec_err}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_text,
                    })
                # Continue conversation with tool results
                response = provider.complete_with_retry(messages, model_id)

            if response.success and response.content:
                self.current_backend_name = f"{response.provider} ({response.model or model_id})"

                # Update provider_manager conversation history
                self.provider_manager._add_to_history("user", prompt)
                self.provider_manager._add_to_history("assistant", response.content)

                # Store in vector memory
                if self._vector_ok and self.vector_memory:
                    try:
                        self.vector_memory.store(
                            f"User: {prompt}\nAssistant: {response.content}",
                            memory_type="conversation", importance=0.6,
                            source="conversation", tags=["dialog"],
                        )
                    except Exception:
                        pass

                return response.content

        except Exception as e:
            logger.warning(f"[Router] ProviderManager query failed: {e}")

        return None

    def _stream_via_provider_manager(self, prompt: str, web_context: str = ""):
        """
        Stream a query through the Phase 2 ProviderManager.
        Yields dicts with 'chunk', 'source', 'done' keys (matching legacy format).
        """
        if not self.provider_manager:
            return

        try:
            # Retrieve relevant memories + RAG context to augment the prompt
            memory_context = ""
            if self._vector_ok and self.vector_memory:
                try:
                    mem_ctx = self.vector_memory.get_context_for_query(prompt, max_tokens=800)
                    if mem_ctx:
                        memory_context = f"\n\n[Memory context]\n{mem_ctx}"
                except Exception:
                    pass

            rag_context = ""
            if self._vector_ok and self.rag_engine:
                try:
                    rag_result = self.rag_engine.query(prompt, max_context_tokens=1000)
                    if rag_result.get("context"):
                        sources = ", ".join(rag_result.get("sources", []))
                        rag_context = f"\n\n[Knowledge base: {sources}]\n{rag_result['context']}"
                except Exception:
                    pass

            augmented_context = web_context + memory_context + rag_context

            model_id = None

            # Use forced model if set (user selected a specific model)
            if self._phase2_forced_model:
                model_id = self._phase2_forced_model
                self._phase2_forced_model = None  # Clear after use
                selection = {'provider_id': '', 'model_name': model_id}
                self.current_backend_name = f"forced ({model_id})"
                logger.info(f"[Router] Streaming with forced model: {model_id}")
            else:
                selection = self.provider_manager.get_best_model(prompt)
                if selection:
                    model_id = selection['model_id']
                    self.current_backend_name = f"{selection.get('provider_id', '')} ({selection.get('model_name', '')})"

            full_response = ""
            for chunk in self.provider_manager.stream(
                prompt, model_id=model_id,
                system_prompt=self.system_prompt,
                web_context=augmented_context,
            ):
                if chunk.text:
                    full_response += chunk.text
                    yield {
                        'chunk': chunk.text,
                        'source': chunk.source or 'provider_manager',
                        'done': False,
                    }
                if chunk.done:
                    # Save to legacy conversation history
                    self.conversation_history.append({"role": "assistant", "content": full_response})

                    # Store in vector memory for future retrieval
                    if self._vector_ok and self.vector_memory and full_response:
                        try:
                            self.vector_memory.store(
                                f"User: {prompt}\nAssistant: {full_response}",
                                memory_type="conversation",
                                importance=0.6,
                                source="conversation",
                                tags=["dialog"],
                            )
                        except Exception:
                            pass

                    yield {
                        'chunk': '',
                        'source': chunk.source or 'provider_manager',
                        'done': True,
                    }
                    return

            # If stream completed without done=True
            if full_response:
                self.conversation_history.append({"role": "assistant", "content": full_response})
                if self._vector_ok and self.vector_memory:
                    try:
                        self.vector_memory.store(
                            f"User: {prompt}\nAssistant: {full_response}",
                            memory_type="conversation",
                            importance=0.6,
                            source="conversation",
                            tags=["dialog"],
                        )
                    except Exception:
                        pass
                yield {'chunk': '', 'source': 'provider_manager', 'done': True}
                return

        except Exception as e:
            logger.warning(f"[Router] ProviderManager stream failed: {e}")

    def get_provider_status(self) -> Dict[str, Any]:
        """Get Phase 2 ProviderManager status for UI"""
        if self.provider_manager:
            return self.provider_manager.get_status()
        return {}

    def get_context_budget(self, model_id: str = None) -> Optional[Dict[str, Any]]:
        """Get context window budget info for UI display"""
        if not self.context_manager:
            return None
        if not model_id and self.model_registry:
            model = self.model_registry.get_best_model()
            model_id = model.id if model else None
        if not model_id:
            return None

        messages = [{"role": r, "content": c} for r, c in
                     [(m["role"], m["content"]) for m in self.conversation_history]]
        return self.context_manager.get_budget_status(messages, model_id)

    def get_provider_dropdown_items(self) -> List[Dict[str, Any]]:
        """Get Phase 2 model/provider list for GUI dropdown"""
        if self.provider_manager:
            return self.provider_manager.get_dropdown_items()
        return []

    def set_phase2_model(self, model_id: str):
        """Force Phase 2 provider manager to use a specific model"""
        if self.provider_manager and self.model_registry:
            model = self.model_registry.get_model(model_id)
            if model:
                self._phase2_forced_model = model_id
                logger.info(f"[Router] Phase 2 forced model: {model.name} ({model.provider})")

    # ============================================================
    # PHASE 1: Model Registry & Cost Tracking Integration
    # ============================================================

    def get_model_info(self, model_id: str = None) -> Optional[Dict[str, Any]]:
        """Get model info from the registry"""
        if not self.model_registry:
            return None
        model = self.model_registry.get_model(model_id) if model_id else None
        if model:
            return {
                'id': model.id,
                'name': model.name,
                'provider': model.provider,
                'context_window': model.context_window,
                'max_tokens': model.max_tokens,
                'cost_input': model.cost_input,
                'cost_output': model.cost_output,
                'tier': model.tier,
            }
        return None

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get session cost summary for status bar display"""
        if self.cost_tracker:
            return self.cost_tracker.get_summary()
        return {'total_requests': 0, 'total_tokens': 0, 'total_cost_usd': 0}

    def get_cost_status_text(self) -> str:
        """Get short cost status for status bar"""
        if self.cost_tracker:
            return self.cost_tracker.get_status_text()
        return ""

    def get_context_window_limit(self, model_id: str = None) -> int:
        """Get context window limit for current or specified model"""
        if self.model_registry and model_id:
            return self.model_registry.get_context_window(model_id)
        return 8192  # safe default

    def get_all_available_models(self) -> List[Dict[str, Any]]:
        """Get all available models from the registry for UI dropdown"""
        if not self.model_registry:
            return []
        return self.model_registry.to_dropdown_items()

    # ============================================================
    # STREAMING METHODS - ChatGPT/Perplexity Style
    # ============================================================
    
    def stream_query(self, prompt: str, prefer_backend: Optional[AIBackend] = None):
        """
        Stream query responses chunk by chunk (generator).
        
        Args:
            prompt: User's question/command
            prefer_backend: Optional preferred backend
            
        Yields:
            Dict with 'chunk' and 'source' keys
        """
        import time
        
        if not prompt or len(prompt.strip()) == 0:
            yield {'chunk': "I didn't catch that. Could you please repeat?", 'source': 'error', 'done': True}
            return

        # Lazy backend check on first query
        self._ensure_backends_checked()

        prompt = prompt.strip()
        
        # === ENHANCED WEB SEARCH - Always try for knowledge queries ===
        web_context = ""
        web_sources = []
        research_result = None

        # Always try web search for factual/knowledge queries (helps local models)
        should_search = self.web_search_enabled and self._is_knowledge_query(prompt)

        if should_search and self.web_search:
            try:
                # Try deep research for complex queries first
                if self.deep_research and self.deep_research_enabled and self.deep_research.needs_deep_research(prompt):
                    logger.info("[Router] Using deep research for complex query")
                    research_result = self.deep_research.research(prompt)
                    if research_result and research_result.sources:
                        web_context = f"\n{self.deep_research.format_context_for_ai(research_result)}\n\n"
                        web_sources = self.deep_research.get_sources_for_display(research_result)
                        # Register with citation engine
                        if self.citation_engine:
                            self.citation_engine.register_sources([
                                {'index': str(s.index), 'title': s.title, 'url': s.url,
                                 'domain': s.domain, 'snippet': s.snippet}
                                for s in research_result.sources
                            ])
                        logger.info(f"[Router] Deep research: {research_result.source_count} sources, {research_result.search_time:.1f}s")

                # Fall back to simple web search if deep research didn't produce results
                if not web_context:
                    # Get context AND sources for display
                    if hasattr(self.web_search, 'get_realtime_context_with_sources'):
                        context, web_sources = self.web_search.get_realtime_context_with_sources(prompt)
                    else:
                        context = self.web_search.get_realtime_context(prompt)

                    if context:
                        web_context = f"\n[Real-time web information - use this to answer accurately]\n{context}\n\n"
                        logger.info(f"[Router] Added web context ({len(context)} chars, {len(web_sources)} sources)")

                # Yield sources first so UI can prepare to show them
                if web_sources:
                    yield {'sources': web_sources, 'done': False}
            except Exception as e:
                logger.warning(f"Web search failed: {e}")
        
        # Store for later use
        self._current_web_context = web_context
        self._current_sources = web_sources

        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": prompt})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        # === PHASE 2: Try ProviderManager first for streaming ===
        if self._use_phase2 and not prefer_backend:
            phase2_yielded = False
            try:
                for chunk_data in self._stream_via_provider_manager(prompt, web_context):
                    phase2_yielded = True
                    yield chunk_data
                    if chunk_data.get('done'):
                        return
            except Exception as e:
                logger.warning(f"[Router] Phase 2 stream failed: {e}")
            if phase2_yielded:
                return
            logger.info("[Router] Phase 2 stream failed, falling back to legacy")

        # Try legacy backends
        backends_to_try = self._get_backend_priority(prefer_backend)
        
        backend_names = {
            AIBackend.LOCAL_OLLAMA: "Local Ollama",
            AIBackend.GEMINI: "Gemini 2.0 Flash",
            AIBackend.OLLAMA_CLOUD: "Ollama Cloud",
            AIBackend.GROQ: "Groq Cloud"
        }
        
        for backend in backends_to_try:
            try:
                logger.info(f"🤖 Stream trying {backend.value}...")
                self.current_backend_name = backend_names.get(backend, backend.value)
                
                if backend == AIBackend.LOCAL_OLLAMA:
                    yield from self._stream_ollama_local(prompt)
                    return
                elif backend == AIBackend.GEMINI:
                    yield from self._stream_gemini(prompt)
                    return
                elif backend == AIBackend.OLLAMA_CLOUD:
                    yield from self._stream_ollama_cloud(prompt)
                    return
                elif backend == AIBackend.GROQ:
                    yield from self._stream_groq(prompt)
                    return
                else:
                    # Fallback to non-streaming for unsupported backends
                    response = self.query(prompt, prefer_backend=backend)
                    yield {'chunk': response, 'source': backend.value, 'done': True}
                    return
                    
            except Exception as e:
                logger.warning(f"⚠️ Stream {backend.value} failed: {e}")
                continue
        
        # All backends failed
        yield {'chunk': "I'm having trouble connecting to my AI systems.", 'source': 'error', 'done': True}
    
    def _stream_ollama_local(self, prompt: str):
        """Stream from local Ollama instance with web-enhanced context"""
        import requests
        
        context = self._build_context()
        web_ctx = getattr(self, '_current_web_context', '')
        
        # Enhanced prompt for local model - emphasize using web data
        if web_ctx:
            enhanced_prompt = (
                f"{self.system_prompt}\n\n"
                f"IMPORTANT: Use the following real-time web information to answer accurately:\n"
                f"{web_ctx}\n\n"
                f"{context}\n"
                f"User: {prompt}\n"
                f"Assistant: Based on the web information provided, "
            )
        else:
            enhanced_prompt = f"{self.system_prompt}\n\n{context}\n\nUser: {prompt}\nAssistant:"
        
        payload = {
            "model": self.local_fast_model,
            "prompt": enhanced_prompt,
            "stream": True,  # Enable streaming
            "options": {
                "temperature": 0.7,
                "num_predict": 800  # Increased for more detailed responses
            }
        }
        
        full_response = ""
        
        try:
            with requests.post(
                f"{self.local_ollama_url}/api/generate",
                json=payload,
                timeout=self.local_timeout,
                stream=True
            ) as response:
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                chunk = data.get('response', '')
                                done = data.get('done', False)
                                
                                if chunk:
                                    full_response += chunk
                                    yield {'chunk': chunk, 'source': 'local_ollama', 'done': False}
                                
                                if done:
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    # Add to history
                    self.conversation_history.append({"role": "assistant", "content": full_response})
                    yield {'chunk': '', 'source': 'local_ollama', 'done': True}
                else:
                    raise Exception(f"Ollama returned {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Local Ollama stream error: {e}")
            raise
    
    def _stream_gemini(self, prompt: str):
        """Stream from Gemini API"""
        if not self.gemini_client:
            raise Exception("Gemini not initialized")
        
        context = self._build_context()
        web_ctx = getattr(self, '_current_web_context', '')
        
        full_prompt = f"{self.system_prompt}\n\n{web_ctx}{context}\n\nUser: {prompt}"
        
        full_response = ""
        
        try:
            # Use Gemini streaming
            response = self.gemini_client.models.generate_content_stream(
                model='gemini-2.0-flash',
                contents=full_prompt
            )
            
            for chunk in response:
                if hasattr(chunk, 'text') and chunk.text:
                    full_response += chunk.text
                    yield {'chunk': chunk.text, 'source': 'gemini', 'done': False}
            
            # Add to history
            self.conversation_history.append({"role": "assistant", "content": full_response})
            yield {'chunk': '', 'source': 'gemini', 'done': True}
            
        except Exception as e:
            logger.error(f"Gemini stream error: {e}")
            raise
    
    def _stream_ollama_cloud(self, prompt: str):
        """Stream from Ollama Cloud API"""
        import requests
        
        context = self._build_context()
        web_ctx = getattr(self, '_current_web_context', '')
        
        full_prompt = f"{self.system_prompt}\n\n{web_ctx}{context}\n\nUser: {prompt}\nAssistant:"
        model = self._get_best_cloud_model(prompt)
        
        headers = {
            'Authorization': f'Bearer {self.ollama_cloud_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": True
        }
        
        full_response = ""
        
        try:
            with requests.post(
                f"{self.ollama_cloud_url}/api/generate",
                headers=headers,
                json=payload,
                timeout=self.cloud_timeout,
                stream=True
            ) as response:
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                chunk = data.get('response', '')
                                done = data.get('done', False)
                                
                                if chunk:
                                    full_response += chunk
                                    yield {'chunk': chunk, 'source': 'ollama_cloud', 'done': False}
                                
                                if done:
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    self.conversation_history.append({"role": "assistant", "content": full_response})
                    yield {'chunk': '', 'source': 'ollama_cloud', 'done': True}
                else:
                    raise Exception(f"Ollama Cloud returned {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Ollama Cloud stream error: {e}")
            raise
    
    def _stream_groq(self, prompt: str):
        """Stream from Groq API (OpenAI compatible)"""
        import requests
        
        context = self._build_context()
        web_ctx = getattr(self, '_current_web_context', '')
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"{web_ctx}Context:\n{context}\n\nCurrent question: {prompt}"}
        ]
        
        headers = {
            'Authorization': f'Bearer {self.groq_api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": self.groq_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 500,
            "stream": True
        }
        
        full_response = ""
        
        try:
            with requests.post(
                self.groq_url,
                headers=headers,
                json=payload,
                timeout=self.cloud_timeout,
                stream=True
            ) as response:
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            line_text = line.decode('utf-8')
                            if line_text.startswith('data: '):
                                data_str = line_text[6:]
                                if data_str == '[DONE]':
                                    break
                                try:
                                    data = json.loads(data_str)
                                    delta = data.get('choices', [{}])[0].get('delta', {})
                                    chunk = delta.get('content', '')
                                    
                                    if chunk:
                                        full_response += chunk
                                        yield {'chunk': chunk, 'source': 'groq', 'done': False}
                                except json.JSONDecodeError:
                                    continue
                    
                    self.conversation_history.append({"role": "assistant", "content": full_response})
                    yield {'chunk': '', 'source': 'groq', 'done': True}
                else:
                    raise Exception(f"Groq returned {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Groq stream error: {e}")
            raise


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    
    router = HybridAIRouter()
    
    print("\n📊 Backend Status:")
    status = router.get_status()
    for backend, info in status.items():
        emoji = "✅" if info["available"] else "❌"
        print(f"  {emoji} {info['name']}: {'Online' if info['available'] else info['error'] or 'Offline'}")
    
    print("\n🧪 Testing query...")
    response = router.query("Hello! What can you do?")
    print(f"\n🤖 Response: {response}")
