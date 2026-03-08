"""
Provider Manager - Central orchestrator for all AI providers.

Replaces the hardcoded backend system in lada_ai_router.py with a
config-driven, extensible provider registry that supports 22+ providers
through 4 unified protocol adapters.

Key improvements over the old system:
- Config-driven: add providers by editing models.json, not code
- Unified streaming: all providers stream through the same interface
- Cost tracking: per-request token counting and cost accumulation
- Context awareness: per-model context window enforcement
- Smart routing: complexity-based model selection
- Retry policies: exponential backoff with provider rotation
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any, List, Generator
from pathlib import Path

from modules.providers.base_provider import (
    BaseProvider, ProviderConfig, ProviderResponse, StreamChunk, ProviderStatus
)

logger = logging.getLogger(__name__)

# Import protocol adapters
try:
    from modules.providers.openai_provider import OpenAIProvider
except ImportError:
    OpenAIProvider = None

try:
    from modules.providers.anthropic_provider import AnthropicProvider
except ImportError:
    AnthropicProvider = None

try:
    from modules.providers.google_provider import GoogleProvider
except ImportError:
    GoogleProvider = None

try:
    from modules.providers.ollama_provider import OllamaProvider
except ImportError:
    OllamaProvider = None

# Import model registry
try:
    from modules.model_registry import get_model_registry
except ImportError:
    get_model_registry = None

# Import cost tracker
try:
    from modules.token_counter import get_cost_tracker
except ImportError:
    get_cost_tracker = None

# Import rate limiter
try:
    from modules.rate_limiter import get_rate_limiter
    RATE_LIMITER_OK = True
except ImportError:
    get_rate_limiter = None
    RATE_LIMITER_OK = False


# Map api_type strings to provider classes
PROTOCOL_MAP = {
    'openai-completions': OpenAIProvider,
    'anthropic-messages': AnthropicProvider,
    'google-generative-ai': GoogleProvider,
    'ollama': OllamaProvider,
}

# Map ENV variable names to their values
ENV_KEY_MAP = {
    'GEMINI_API_KEY': 'GEMINI_API_KEY',
    'GROQ_API_KEY': 'GROQ_API_KEY',
    'OPENAI_API_KEY': 'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY': 'ANTHROPIC_API_KEY',
    'MISTRAL_API_KEY': 'MISTRAL_API_KEY',
    'XAI_API_KEY': 'XAI_API_KEY',
    'OLLAMA_CLOUD_KEY': 'OLLAMA_CLOUD_KEY',
    'LOCAL_OLLAMA_URL': 'LOCAL_OLLAMA_URL',
}


class ProviderManager:
    """
    Central provider registry and routing engine.

    Manages all AI providers, their health status, and routes queries
    to the best available provider based on model selection, cost,
    and availability.

    Usage:
        manager = ProviderManager()
        manager.auto_configure()  # detect available providers from ENV

        # Query with auto-routing
        response = manager.query("What is quantum computing?")

        # Query specific model
        response = manager.query("explain relativity", model="gemini-2.0-flash")

        # Stream
        for chunk in manager.stream("tell me a story"):
            print(chunk.text, end="")
    """

    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.model_registry = get_model_registry() if get_model_registry else None
        self.cost_tracker = get_cost_tracker() if get_cost_tracker else None

        # Default routing preferences
        self.system_prompt = ""
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 20
        self._forced_provider: Optional[str] = None

        # Rate limiter singleton (per-provider request throttling + circuit breaker)
        self._rate_limiter = get_rate_limiter() if RATE_LIMITER_OK else None

        logger.info("[ProviderManager] Initialized")

    def auto_configure(self) -> int:
        """
        Auto-detect and configure providers from ENV variables and models.json.
        Returns the number of available providers.
        """
        configured = 0

        # Load provider definitions from model registry
        if self.model_registry:
            for pid, pinfo in self.model_registry.providers.items():
                api_type = pinfo.type
                provider_class = PROTOCOL_MAP.get(api_type)
                if not provider_class:
                    logger.debug(f"[ProviderManager] No adapter for api_type '{api_type}' (provider {pid})")
                    continue

                # Get API key from ENV
                config_keys = pinfo.config_keys
                api_key = ""
                base_url = ""

                for ck in config_keys:
                    val = os.getenv(ck, '')
                    if val:
                        if 'URL' in ck.upper():
                            base_url = val
                        else:
                            api_key = val

                # Get base URL from first model of this provider
                if not base_url:
                    for m in self.model_registry.models.values():
                        if m.provider == pid and m.base_url:
                            base_url = m.base_url
                            break

                if not base_url:
                    continue

                # For local providers, no key needed
                is_local = pinfo.local
                if not api_key and not is_local:
                    logger.debug(f"[ProviderManager] No API key for {pid}, skipping")
                    continue

                config = ProviderConfig(
                    provider_id=pid,
                    name=pinfo.name,
                    api_type=api_type,
                    base_url=base_url,
                    api_key=api_key,
                    timeout=float(os.getenv('AI_TIMEOUT', '60')),
                    max_retries=2,
                    local=is_local,
                    priority=pinfo.priority,
                    enabled=True,
                )

                provider = provider_class(config)
                self.providers[pid] = provider
                configured += 1
                logger.info(f"[ProviderManager] Configured: {config.name} ({api_type})")

                # Register with rate limiter
                if self._rate_limiter:
                    rpm = int(os.getenv(f"{pid.upper().replace('-', '_')}_RPM", "60"))
                    rpd = int(os.getenv(f"{pid.upper().replace('-', '_')}_RPD", "10000"))
                    self._rate_limiter.register(pid, rpm=rpm, rpd=rpd)

        # Always try to add local Ollama even without model registry
        if 'ollama-local' not in self.providers and OllamaProvider:
            local_url = os.getenv('LOCAL_OLLAMA_URL', 'http://localhost:11434')
            config = ProviderConfig(
                provider_id='ollama-local',
                name='Local Ollama',
                api_type='ollama',
                base_url=local_url,
                api_key='',
                timeout=60,
                local=True,
                priority=1,
            )
            self.providers['ollama-local'] = OllamaProvider(config)
            configured += 1

        logger.info(f"[ProviderManager] {configured} providers configured")
        return configured

    def get_provider(self, provider_id: str) -> Optional[BaseProvider]:
        """Get a specific provider by ID"""
        return self.providers.get(provider_id)

    def get_provider_for_model(self, model_id: str) -> Optional[BaseProvider]:
        """Find the provider that serves a specific model"""
        if self.model_registry:
            model = self.model_registry.get_model(model_id)
            if model:
                return self.providers.get(model.provider)
        return None

    def check_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Check health of all providers and return status"""
        results = {}
        for pid, provider in self.providers.items():
            provider.status = provider.check_health()
            provider.last_check = time.time()
            results[pid] = provider.get_status_dict()
        return results

    def get_available_providers(self) -> List[BaseProvider]:
        """Get list of available providers sorted by priority"""
        available = []
        for provider in self.providers.values():
            if provider.ensure_available():
                available.append(provider)
        return sorted(available, key=lambda p: p.config.priority)

    def get_best_model(self, query: str, tier: str = None) -> Optional[Dict[str, Any]]:
        """
        Select the best model for a query based on complexity and availability.
        Falls back through tiers: requested → lower tiers → any available.
        Returns dict with 'model_id', 'provider_id', 'model_name', 'tier'.
        """
        if not self.model_registry:
            return None

        # Determine query tier
        if not tier:
            tier = self._analyze_complexity(query)

        # Available provider IDs
        available_pids = {
            pid for pid, p in self.providers.items()
            if p.ensure_available()
        }

        if not available_pids:
            return None

        # Tier fallback chain: requested → progressively simpler tiers
        tier_fallback = {
            'reasoning': ['reasoning', 'smart', 'balanced', 'fast'],
            'coding': ['coding', 'smart', 'balanced', 'fast'],
            'smart': ['smart', 'balanced', 'fast'],
            'balanced': ['balanced', 'fast'],
            'fast': ['fast', 'balanced'],
        }

        tiers_to_try = tier_fallback.get(tier, [tier, 'balanced', 'fast'])

        for try_tier in tiers_to_try:
            candidates = self.model_registry.get_models_by_tier(try_tier)
            for model in candidates:
                if model.provider in available_pids:
                    return {
                        'model_id': model.id,
                        'provider_id': model.provider,
                        'model_name': model.name,
                        'tier': try_tier,
                    }

        # Last resort: any available model
        for provider in self.get_available_providers():
            models = self.model_registry.get_models_by_provider(provider.provider_id)
            if models:
                m = models[0]
                return {
                    'model_id': m.id,
                    'provider_id': provider.provider_id,
                    'model_name': m.name,
                    'tier': m.tier,
                }

        return None

    def query(self, prompt: str, model_id: str = None,
              system_prompt: str = None, web_context: str = "",
              temperature: float = 0.7, max_tokens: int = 2048,
              **kwargs) -> ProviderResponse:
        """
        Send a query to the best available provider.

        If model_id is specified, routes to that model's provider.
        Otherwise, auto-selects based on query complexity.
        """
        sys_prompt = system_prompt or self.system_prompt

        # Build messages
        messages = self._build_messages(prompt, sys_prompt, web_context)

        # Determine target model and provider
        if model_id:
            provider = self.get_provider_for_model(model_id)
            if not provider:
                # Try using model_id as provider_id
                provider = self.providers.get(model_id)
                if provider and self.model_registry:
                    models = self.model_registry.get_models_by_provider(provider.provider_id)
                    model_id = models[0].id if models else model_id
        else:
            selection = self.get_best_model(prompt)
            if selection:
                model_id = selection['model_id']
                provider = self.providers.get(selection['provider_id'])
            else:
                provider = None

        if not provider:
            return ProviderResponse(
                content="No AI providers are available. Check your configuration.",
                provider="none", error="No providers available"
            )

        # Query with retry
        if self._rate_limiter:
            allowed, reason = self._rate_limiter.check(provider.provider_id)
            if not allowed:
                # Try next available provider
                for fallback in self.get_available_providers():
                    if fallback.provider_id == provider.provider_id:
                        continue
                    fb_allowed, _ = self._rate_limiter.check(fallback.provider_id)
                    if fb_allowed:
                        provider = fallback
                        if self.model_registry:
                            fb_models = self.model_registry.get_models_by_provider(provider.provider_id)
                            model_id = fb_models[0].id if fb_models else model_id
                        break
                else:
                    return ProviderResponse(
                        content=f"Rate limited ({reason}). All providers at capacity.",
                        provider=provider.provider_id, error=reason
                    )

        response = provider.complete_with_retry(
            messages, model_id, temperature, max_tokens, **kwargs
        )

        # Record rate limiter outcome
        if self._rate_limiter:
            if response.success:
                self._rate_limiter.record_success(provider.provider_id)
            else:
                self._rate_limiter.record_failure(provider.provider_id)

        # Track cost
        if self.cost_tracker and response.success:
            model_info = self.model_registry.get_model(model_id) if self.model_registry else None
            cost_in = model_info.cost_input if model_info else 0
            cost_out = model_info.cost_output if model_info else 0
            self.cost_tracker.record(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model_id=model_id,
                provider=provider.provider_id,
                cost_input_per_m=cost_in,
                cost_output_per_m=cost_out,
            )

        # Update conversation history
        if response.success:
            self._add_to_history("user", prompt)
            self._add_to_history("assistant", response.content)

        return response

    def stream(self, prompt: str, model_id: str = None,
               system_prompt: str = None, web_context: str = "",
               temperature: float = 0.7, max_tokens: int = 2048,
               **kwargs) -> Generator[StreamChunk, None, None]:
        """
        Stream a query to the best available provider.
        Yields StreamChunk objects.
        """
        sys_prompt = system_prompt or self.system_prompt
        messages = self._build_messages(prompt, sys_prompt, web_context)

        # Determine target
        if model_id:
            provider = self.get_provider_for_model(model_id)
            if not provider:
                provider = self.providers.get(model_id)
                if provider and self.model_registry:
                    models = self.model_registry.get_models_by_provider(provider.provider_id)
                    model_id = models[0].id if models else model_id
        else:
            selection = self.get_best_model(prompt)
            if selection:
                model_id = selection['model_id']
                provider = self.providers.get(selection['provider_id'])
            else:
                provider = None

        if not provider:
            yield StreamChunk(
                text="No AI providers are available.",
                done=True, source="none",
                metadata={'error': 'No providers available'}
            )
            return

        # Stream with fallback to other providers on failure
        full_response = ""
        success = False
        providers_tried = []

        providers_to_try = [provider]
        # Add fallback providers
        for p in self.get_available_providers():
            if p.provider_id != provider.provider_id and p not in providers_to_try:
                providers_to_try.append(p)

        for p in providers_to_try:
            try:
                # Check rate limiter before attempting this provider
                if self._rate_limiter:
                    rl_allowed, rl_reason = self._rate_limiter.check(p.provider_id)
                    if not rl_allowed:
                        logger.debug(f"[ProviderManager] Rate limited {p.name}: {rl_reason}")
                        continue

                target_model = model_id
                # If switching providers, pick a model from the new provider
                if p.provider_id != (provider.provider_id if provider else None):
                    if self.model_registry:
                        tier = self._analyze_complexity(prompt)
                        alt_models = self.model_registry.get_models_by_provider(p.provider_id)
                        tier_match = [m for m in alt_models if m.tier == tier]
                        target_model = tier_match[0].id if tier_match else (alt_models[0].id if alt_models else target_model)

                providers_tried.append(p.provider_id)

                for chunk in p.stream_complete(messages, target_model, temperature, max_tokens, **kwargs):
                    if chunk.metadata.get('error') and not chunk.text:
                        # Provider failed, try next
                        logger.warning(f"[ProviderManager] Stream failed on {p.name}: {chunk.metadata['error']}")
                        break

                    if chunk.text:
                        full_response += chunk.text

                    yield chunk

                    if chunk.done:
                        success = True
                        break

                if success:
                    if self._rate_limiter:
                        self._rate_limiter.record_success(p.provider_id)
                    break

            except Exception as e:
                logger.warning(f"[ProviderManager] Stream error on {p.name}: {e}")
                if self._rate_limiter:
                    self._rate_limiter.record_failure(p.provider_id)
                continue

        if not success:
            yield StreamChunk(
                text="Failed to get response from any AI provider.",
                done=True, source="error"
            )

        # Track cost and history
        if success and full_response:
            self._add_to_history("user", prompt)
            self._add_to_history("assistant", full_response)

            if self.cost_tracker and self.model_registry:
                model_info = self.model_registry.get_model(model_id)
                if model_info:
                    self.cost_tracker.record_from_text(
                        input_text=prompt,
                        output_text=full_response,
                        model_id=model_id,
                        provider=provider.provider_id if provider else "",
                        cost_input_per_m=model_info.cost_input,
                        cost_output_per_m=model_info.cost_output,
                    )

    def force_provider(self, provider_id: Optional[str]):
        """Force all queries to a specific provider"""
        self._forced_provider = provider_id

    def set_system_prompt(self, prompt: str):
        """Set the system prompt for all queries"""
        self.system_prompt = prompt

    def _build_messages(self, prompt: str, system_prompt: str,
                        web_context: str = "") -> List[Dict[str, str]]:
        """Build unified message list"""
        messages = []

        if system_prompt:
            from datetime import datetime
            date_info = f"Current date: {datetime.now().strftime('%B %d, %Y')}."
            full_system = f"{system_prompt}\n\n[{date_info}]"
            messages.append({"role": "system", "content": full_system})

        if web_context:
            messages.append({
                "role": "system",
                "content": f"[Real-time web data]\n{web_context}"
            })

        # Add conversation history (last 6 messages)
        for msg in self.conversation_history[-6:]:
            messages.append(msg)

        messages.append({"role": "user", "content": prompt})
        return messages

    def _add_to_history(self, role: str, content: str):
        """Add message to conversation history"""
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

    def _analyze_complexity(self, query: str) -> str:
        """Analyze query complexity and return tier"""
        q = query.lower().strip()
        words = q.split()

        # Greetings and very short queries (under 4 words)
        greetings = {'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sup'}
        if len(words) <= 3 and (not words or words[0] in greetings or len(q) < 10):
            return 'fast'

        # Code patterns
        if any(p in q for p in ['code', 'program', 'function', 'debug', 'python',
                                 'javascript', 'algorithm', 'implement', 'script',
                                 'compile', 'syntax', 'variable', 'class ', 'def ',
                                 'refactor', 'unit test', 'api endpoint']):
            return 'coding'

        # Reasoning patterns
        if any(p in q for p in ['analyze', 'compare', 'evaluate', 'pros and cons',
                                 'differences between', 'trade-offs', 'implications',
                                 'critique', 'assess', 'weigh', 'argue', 'debate',
                                 'should i', 'which is better', 'advantages']):
            return 'reasoning'

        # Smart patterns
        if any(p in q for p in ['explain', 'how to', 'how does', 'what is',
                                 'describe', 'teach me', 'help me understand',
                                 'why does', 'what are', 'tell me about',
                                 'summarize', 'elaborate', 'in detail']):
            return 'smart'

        # Long queries default to balanced
        if len(words) > 8:
            return 'balanced'

        return 'fast'

    def get_status(self) -> Dict[str, Any]:
        """Get full status of all providers"""
        status = {
            'providers': {
                pid: p.get_status_dict()
                for pid, p in self.providers.items()
            },
            'total_providers': len(self.providers),
            'available': sum(1 for p in self.providers.values() if p.is_available),
            'forced_provider': self._forced_provider,
        }
        if self._rate_limiter:
            status['rate_limiter'] = self._rate_limiter.get_stats()
        return status

    def get_rate_limiter_stats(self) -> Dict[str, Any]:
        """Get rate limiter stats for all providers"""
        if self._rate_limiter:
            return self._rate_limiter.get_stats()
        return {}

    def get_dropdown_items(self) -> List[Dict[str, Any]]:
        """Get provider/model list for GUI dropdown"""
        items = [{'label': 'Auto (Best Available)', 'value': 'auto'}]

        for provider in sorted(self.providers.values(), key=lambda p: p.config.priority):
            available = provider.is_available
            if self.model_registry:
                models = self.model_registry.get_models_by_provider(provider.provider_id)
                for m in models:
                    suffix = "" if available else " (offline)"
                    items.append({
                        'label': f"{m.name}{suffix}",
                        'value': m.id,
                        'provider': provider.provider_id,
                        'available': available,
                    })
            else:
                suffix = "" if available else " (offline)"
                items.append({
                    'label': f"{provider.name}{suffix}",
                    'value': provider.provider_id,
                    'provider': provider.provider_id,
                    'available': available,
                })

        return items


# Module-level singleton
_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """Get or create the global ProviderManager"""
    global _manager
    if _manager is None:
        _manager = ProviderManager()
        _manager.auto_configure()
    return _manager
