"""
LADA AI Router — Unified Provider-Based Routing

Routes AI queries through ProviderManager with:
- Config-driven model selection from models.json
- Tier-based routing (fast/balanced/smart/reasoning/coding)
- Per-provider rate limiting + circuit breakers
- Comet-style web search for real-time data
- Vector memory + RAG augmentation
- AI tool calling (function calling)
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Phase 1 modules
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

# Phase 2 modules
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

# Web search module
try:
    from modules.web_search import WebSearchEngine
    WEB_SEARCH_OK = True
except ImportError:
    WEB_SEARCH_OK = False
    WebSearchEngine = None
    logger.warning("Web search module not available")

# Deep research engine
try:
    from modules.deep_research import DeepResearchEngine
    DEEP_RESEARCH_OK = True
except ImportError:
    DEEP_RESEARCH_OK = False
    DeepResearchEngine = None
    logger.warning("Deep research module not available")

# Citation engine
try:
    from modules.citation_engine import CitationEngine
    CITATION_OK = True
except ImportError:
    CITATION_OK = False
    CitationEngine = None
    logger.warning("Citation engine not available")

# Vector memory + RAG engine
try:
    from modules.vector_memory import VectorMemorySystem
    from modules.rag_engine import RAGEngine
    VECTOR_MEMORY_OK = True
except ImportError:
    VECTOR_MEMORY_OK = False
    VectorMemorySystem = None
    RAGEngine = None
    logger.warning("Vector memory / RAG engine not available")

# Tool registry for function calling
try:
    from modules.tool_registry import ToolRegistry, get_tool_registry
    TOOL_REGISTRY_OK = True
except ImportError:
    TOOL_REGISTRY_OK = False
    get_tool_registry = None
    logger.warning("Tool registry not available")


class HybridAIRouter:
    """
    AI Router — routes all queries through ProviderManager.

    Features:
    - Config-driven routing via models.json + ProviderManager
    - Tier-based model selection (fast/balanced/smart/reasoning/coding)
    - Web search augmentation for real-time queries
    - Vector memory + RAG context injection
    - AI tool calling loop (function calling)
    - Response caching for first-message queries
    """

    def __init__(self):
        """Initialize the AI Router"""

        # Current backend tracking (for self-awareness in responses)
        self.current_backend_name = "Auto"

        # System prompt
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

        # Web search capability
        self.web_search_enabled = True
        self.web_search = WebSearchEngine() if WEB_SEARCH_OK else None

        # Deep research engine
        self.deep_research = DeepResearchEngine(ai_router=self) if DEEP_RESEARCH_OK else None
        self.deep_research_enabled = True

        # Citation engine
        self.citation_engine = CitationEngine() if CITATION_OK else None

        # Response cache
        self.cache: Dict[str, str] = {}
        self.cache_enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.cache_max_size = int(os.getenv('CACHE_MAX_SIZE', '200'))

        # Model registry
        self.model_registry = get_model_registry() if MODEL_REGISTRY_OK else None
        if self.model_registry:
            logger.info(f"[Router] Model registry: {len(self.model_registry.models)} models, "
                        f"{len(self.model_registry.providers)} providers")

        # Error tracking
        self.error_tracker = get_error_tracker() if ERROR_TYPES_OK else None

        # Cost tracking
        self.cost_tracker = get_cost_tracker() if TOKEN_COUNTER_OK else None

        # Provider Manager (unified multi-provider routing)
        self.provider_manager = None
        if PROVIDER_MANAGER_OK:
            try:
                self.provider_manager = get_provider_manager()
                self.provider_manager.set_system_prompt(self.system_prompt)
                provider_count = len(self.provider_manager.providers)
                logger.info(f"[Router] ProviderManager: {provider_count} providers active")
            except Exception as e:
                logger.warning(f"[Router] ProviderManager init failed: {e}")
                self.provider_manager = None

        # Context Manager (token-aware context window)
        self.context_manager = None
        if CONTEXT_MANAGER_OK:
            try:
                self.context_manager = get_context_manager()
                logger.info("[Router] ContextManager active")
            except Exception as e:
                logger.warning(f"[Router] ContextManager init failed: {e}")

        # Forced model ID (set by set_phase2_model, consumed by query methods)
        self._phase2_forced_model = None

        # Vector Memory + RAG Engine
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

        # Wire tool handlers
        if self.tool_registry:
            try:
                from modules.tool_handlers import wire_tool_handlers
                wired = wire_tool_handlers(self.tool_registry)
                logger.info(f"[Router] Wired {wired} tool handlers")
            except Exception as e:
                logger.warning(f"[Router] Could not wire tool handlers: {e}")

        logger.info("[Router] HybridAIRouter initialized")

    # ============================================================
    # Web Search Helpers
    # ============================================================

    def _is_knowledge_query(self, query: str) -> bool:
        """
        Detect if query needs REAL-TIME / current data from the web.
        Conceptual questions (what is X, explain Y) should go to AI reasoning,
        not web search. Only return True for queries needing fresh/live data.
        """
        q = query.lower()

        temporal_words = [
            'latest', 'current', 'recent', 'today', 'yesterday', 'tonight',
            'this week', 'this month', 'this year', 'right now', 'live',
            '2024', '2025', '2026', 'new release', 'just released',
            'breaking', 'update on', 'news about', 'score', 'result',
        ]
        if any(t in q for t in temporal_words):
            return True

        price_patterns = [
            'price of', 'cost of', 'how much does', 'how much is',
            'buy', 'purchase', 'available at', 'in stock', 'discount',
            'deal on', 'offer on', 'salary of', 'worth of',
        ]
        if any(p in q for p in price_patterns):
            return True

        live_patterns = [
            'weather', 'forecast', 'stock price', 'exchange rate',
            'traffic', 'flight status', 'match score',
        ]
        if any(p in q for p in live_patterns):
            return True

        return False

    # ============================================================
    # Main Query Methods
    # ============================================================

    def query(self, prompt: str, prefer_backend=None,
              model: Optional[str] = None, use_web_search: Optional[bool] = None, **kwargs) -> str:
        """
        Send query to best available AI provider.

        Args:
            prompt: User's question/command
            prefer_backend: Ignored (kept for backward compatibility)
            model: Optional specific model ID to use
            use_web_search: Override web search toggle

        Returns:
            AI response string
        """
        if not prompt or len(prompt.strip()) == 0:
            return "I didn't catch that. Could you please repeat?"

        prompt = prompt.strip()

        # Check cache — only for first message (no conversation context)
        pm_history = self.provider_manager.conversation_history if self.provider_manager else []
        use_cache = self.cache_enabled and len(pm_history) == 0
        if use_cache:
            cache_key = prompt.lower().strip()
            if cache_key in self.cache:
                logger.debug("Cache hit!")
                return self.cache[cache_key]

        # Web search for real-time queries
        web_context = ""
        ws_enabled = use_web_search if use_web_search is not None else self.web_search_enabled
        if ws_enabled and self.web_search:
            try:
                context = self.web_search.get_realtime_context(prompt)
                if context:
                    web_context = f"\n[Real-time web data for your reference]\n{context}\n\n"
                    logger.info(f"[Router] Added web context ({len(context)} chars)")
            except Exception as e:
                logger.warning(f"Web search failed: {e}")

        # Add to conversation history
        if self.provider_manager:
            self.provider_manager._add_to_history("user", prompt)

        self._current_web_context = web_context

        # Route through ProviderManager
        response = self._query_via_provider_manager(prompt, web_context, forced_model=model)

        if response:
            logger.info(f"[Router] Response via {self.current_backend_name}")
            if self.provider_manager:
                self.provider_manager._add_to_history("assistant", response)
            if use_cache:
                cache_key = prompt.lower().strip()
                self.cache[cache_key] = response
            return response

        # All providers failed
        fallback = "I'm having trouble connecting to my AI systems. Please check your internet connection or try again in a moment."
        if self.provider_manager:
            self.provider_manager._add_to_history("assistant", fallback)

        # Cache the failure message to avoid repeated attempts
        if use_cache:
            cache_key = prompt.lower().strip()
            self.cache[cache_key] = fallback
            if len(self.cache) > self.cache_max_size:
                keys = list(self.cache.keys())
                for key in keys[:50]:
                    del self.cache[key]

        return fallback

    def stream_query(self, prompt: str, prefer_backend=None,
                     model: Optional[str] = None, use_web_search: Optional[bool] = None):
        """
        Stream query responses chunk by chunk (generator).

        Args:
            prompt: User's question/command
            prefer_backend: Ignored (kept for backward compatibility)
            model: Optional specific model ID to use
            use_web_search: Override web search toggle

        Yields:
            Dict with 'chunk', 'source', 'done' keys.
            May also yield {'sources': [...], 'done': False} for web search sources.
        """
        if not prompt or len(prompt.strip()) == 0:
            yield {'chunk': "I didn't catch that. Could you please repeat?", 'source': 'error', 'done': True}
            return

        prompt = prompt.strip()

        # Enhanced web search — deep research for complex queries
        web_context = ""
        web_sources = []

        ws_enabled = use_web_search if use_web_search is not None else self.web_search_enabled
        should_search = ws_enabled and self._is_knowledge_query(prompt)

        if should_search and self.web_search:
            try:
                # Try deep research for complex queries first
                if self.deep_research and self.deep_research_enabled and self.deep_research.needs_deep_research(prompt):
                    logger.info("[Router] Using deep research for complex query")
                    research_result = self.deep_research.research(prompt)
                    if research_result and research_result.sources:
                        web_context = f"\n{self.deep_research.format_context_for_ai(research_result)}\n\n"
                        web_sources = self.deep_research.get_sources_for_display(research_result)
                        if self.citation_engine:
                            self.citation_engine.register_sources([
                                {'index': str(s.index), 'title': s.title, 'url': s.url,
                                 'domain': s.domain, 'snippet': s.snippet}
                                for s in research_result.sources
                            ])
                        logger.info(f"[Router] Deep research: {research_result.source_count} sources, {research_result.search_time:.1f}s")

                # Fall back to simple web search
                if not web_context:
                    if hasattr(self.web_search, 'get_realtime_context_with_sources'):
                        context, web_sources = self.web_search.get_realtime_context_with_sources(prompt)
                    else:
                        context = self.web_search.get_realtime_context(prompt)

                    if context:
                        web_context = f"\n[Real-time web information - use this to answer accurately]\n{context}\n\n"
                        logger.info(f"[Router] Added web context ({len(context)} chars, {len(web_sources)} sources)")

                # Yield sources first so UI can render them
                if web_sources:
                    yield {'sources': web_sources, 'done': False}
            except Exception as e:
                logger.warning(f"Web search failed: {e}")

        self._current_web_context = web_context
        self._current_sources = web_sources

        # Add to conversation history
        if self.provider_manager:
            self.provider_manager._add_to_history("user", prompt)

        # Stream through ProviderManager
        phase2_yielded = False
        try:
            for chunk_data in self._stream_via_provider_manager(prompt, web_context, forced_model=model):
                phase2_yielded = True
                yield chunk_data
                if chunk_data.get('done'):
                    return
        except Exception as e:
            logger.warning(f"[Router] Provider stream failed: {e}")

        if phase2_yielded:
            return

        # All providers failed
        yield {'chunk': "I'm having trouble connecting to my AI systems.", 'source': 'error', 'done': True}

    # ============================================================
    # ProviderManager Integration
    # ============================================================

    def _query_via_provider_manager(self, prompt: str, web_context: str = "", forced_model: Optional[str] = None) -> Optional[str]:
        """
        Route a query through the ProviderManager.
        Returns AI response or None if all providers fail.
        """
        if not self.provider_manager:
            return None

        try:
            # Retrieve relevant memories + RAG context
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
            provider = None

            # Use forced model if set
            effective_forced = forced_model or self._phase2_forced_model
            if effective_forced:
                model_id = effective_forced
                provider = self.provider_manager.get_provider_for_model(model_id)
                if not forced_model:
                    self._phase2_forced_model = None
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
                    self._store_in_vector_memory(prompt, response.content)
                    return response.content
                return None

            # Build message list
            messages = self.provider_manager._build_messages(
                prompt, self.system_prompt, augmented_context
            )

            # Apply context window management
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
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": response.tool_calls,
                })
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
                response = provider.complete_with_retry(messages, model_id)

            if response.success and response.content:
                self.current_backend_name = f"{response.provider} ({response.model or model_id})"
                self._store_in_vector_memory(prompt, response.content)
                return response.content

        except Exception as e:
            logger.warning(f"[Router] ProviderManager query failed: {e}")

        return None

    def _stream_via_provider_manager(self, prompt: str, web_context: str = "", forced_model: Optional[str] = None):
        """
        Stream a query through the ProviderManager.
        Yields dicts with 'chunk', 'source', 'done' keys.
        """
        if not self.provider_manager:
            return

        try:
            # Retrieve relevant memories + RAG context
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

            # Use forced model if set
            effective_forced = forced_model or self._phase2_forced_model
            if effective_forced:
                model_id = effective_forced
                if not forced_model:
                    self._phase2_forced_model = None
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
                    if self.provider_manager and full_response:
                        self.provider_manager._add_to_history("assistant", full_response)
                    self._store_in_vector_memory(prompt, full_response)
                    yield {
                        'chunk': '',
                        'source': chunk.source or 'provider_manager',
                        'done': True,
                    }
                    return

            # Stream completed without done=True
            if full_response:
                if self.provider_manager:
                    self.provider_manager._add_to_history("assistant", full_response)
                self._store_in_vector_memory(prompt, full_response)
                yield {'chunk': '', 'source': 'provider_manager', 'done': True}
                return

        except Exception as e:
            logger.warning(f"[Router] ProviderManager stream failed: {e}")

    def _store_in_vector_memory(self, prompt: str, response: str):
        """Store conversation exchange in vector memory for future retrieval."""
        if self._vector_ok and self.vector_memory and response:
            try:
                self.vector_memory.store(
                    f"User: {prompt}\nAssistant: {response}",
                    memory_type="conversation", importance=0.6,
                    source="conversation", tags=["dialog"],
                )
            except Exception:
                pass

    # ============================================================
    # Model Selection & Status
    # ============================================================

    def get_backend_from_name(self, name: str):
        """
        Configure model selection from a UI model name/ID.

        For Phase 2 model IDs (e.g. "llama-3.3-70b-versatile"): sets as forced model.
        For "auto" or empty: clears forced model (auto-select).

        Returns None always (Phase 2 handles routing internally).
        Kept for backward compatibility with desktop app callers.
        """
        if not name or 'auto' in name.lower():
            self._phase2_forced_model = None
            return None

        # Check if this is a known model ID
        if self.model_registry and self.model_registry.get_model(name):
            self.set_phase2_model(name)
            return None

        # Try fuzzy match — the name might be a display name
        self._phase2_forced_model = None
        return None

    def set_phase2_model(self, model_id: str):
        """Force routing to use a specific model"""
        if self.provider_manager and self.model_registry:
            model = self.model_registry.get_model(model_id)
            if model:
                self._phase2_forced_model = model_id
                logger.info(f"[Router] Forced model: {model.name} ({model.provider})")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all providers. Returns flat dict keyed by provider ID,
        each with 'name', 'available', 'error' for backward compatibility."""
        if not self.provider_manager:
            return {}
        result = {}
        for pid, p in self.provider_manager.providers.items():
            status_dict = p.get_status_dict()
            result[pid] = {
                'name': status_dict.get('name', pid),
                'available': status_dict.get('available', False),
                'response_time': f"{status_dict.get('avg_latency_ms', 0):.0f}ms",
                'error': status_dict.get('last_error') or None,
            }
        return result

    def get_available_backends(self) -> List[Dict[str, Any]]:
        """Get list of available providers with status info for UI display."""
        if not self.provider_manager:
            return []
        providers = self.provider_manager.get_available_providers()
        return [
            {
                'name': p.config.name,
                'available': p.is_available,
                'error': p.last_error or None,
            }
            for p in providers
        ]

    def get_provider_status(self) -> Dict[str, Any]:
        """Get ProviderManager status for UI"""
        if self.provider_manager:
            return self.provider_manager.get_status()
        return {}

    def clear_history(self):
        """Clear conversation history"""
        if self.provider_manager:
            self.provider_manager.conversation_history = []

    def clear_cache(self):
        """Clear response cache"""
        self.cache = {}

    # Backward compatibility — these are no-ops now
    def force_backend(self, backend=None):
        """No-op. Use set_phase2_model() instead."""
        pass

    def get_forced_backend(self):
        """Returns None. Use _phase2_forced_model instead."""
        return None

    def _ensure_backends_checked(self):
        """No-op. ProviderManager does lazy health checks."""
        pass

    # ============================================================
    # Model Registry & Cost Tracking
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
        return 8192

    def get_all_available_models(self) -> List[Dict[str, Any]]:
        """Get all available models from the registry for UI dropdown"""
        if not self.model_registry:
            return []
        return self.model_registry.to_dropdown_items()

    def get_context_budget(self, model_id: str = None) -> Optional[Dict[str, Any]]:
        """Get context window budget info for UI display"""
        if not self.context_manager:
            return None
        if not model_id and self.model_registry:
            model = self.model_registry.get_best_model()
            model_id = model.id if model else None
        if not model_id:
            return None

        pm_history = self.provider_manager.conversation_history if self.provider_manager else []
        messages = [{"role": m["role"], "content": m["content"]} for m in pm_history]
        return self.context_manager.get_budget_status(messages, model_id)

    def get_provider_dropdown_items(self) -> List[Dict[str, Any]]:
        """Get model/provider list for GUI dropdown"""
        if self.provider_manager:
            return self.provider_manager.get_dropdown_items()
        return []

    @property
    def conversation_history(self) -> List[Dict[str, str]]:
        """Access conversation history from ProviderManager (single source of truth)."""
        if self.provider_manager:
            return self.provider_manager.conversation_history
        return []

    @conversation_history.setter
    def conversation_history(self, value: List[Dict[str, str]]):
        """Set conversation history on ProviderManager."""
        if self.provider_manager:
            self.provider_manager.conversation_history = value


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    router = HybridAIRouter()

    print("\n[Status]")
    status = router.get_status()
    for key, info in status.items():
        print(f"  {key}: {info}")

    print("\n[Test query]")
    response = router.query("Hello! What can you do?")
    print(f"\nResponse: {response}")
