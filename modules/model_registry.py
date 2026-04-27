"""
LADA Model Registry - Config-driven AI model catalog

Loads model definitions from models.json. Provides model lookup by:
- Provider name
- Capability tier (fast/balanced/smart/reasoning/coding)
- Query complexity analysis
- Available providers (based on configured API keys)

Replaces hardcoded model names in lada_ai_router.py with a
queryable registry that supports 22+ providers and 700+ models.
"""

import os
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModelEntry:
    """Single AI model definition"""
    id: str
    name: str
    provider: str
    api: str
    base_url: str
    context_window: int
    max_tokens: int
    reasoning: bool
    input_types: List[str]
    cost_input: float  # per million tokens
    cost_output: float
    tier: str  # fast, balanced, smart, reasoning, coding
    local: bool = False
    description: str = ""
    tags: List[str] = field(default_factory=list)
    params: str = ""


@dataclass
class ProviderEntry:
    """AI provider definition"""
    name: str
    type: str  # API protocol: ollama, google-generative-ai, openai-completions, anthropic-messages
    config_keys: List[str]  # ENV keys required (e.g. GEMINI_API_KEY)
    local: bool
    priority: int


class ModelRegistry:
    """
    Config-driven model catalog.

    Loads models.json at startup. Provides:
    - Model lookup by provider, tier, or ID
    - Available provider detection (checks ENV keys)
    - Best model selection for a given query tier
    - Cost estimation for a model + token count
    - Context window limits per model
    """

    def __init__(self, catalog_path: str = None):
        self.catalog_path = Path(catalog_path or os.getenv(
            'MODEL_CATALOG_PATH',
            str(Path(__file__).parent.parent / 'models.json')
        ))
        self.models: Dict[str, ModelEntry] = {}
        self.providers: Dict[str, ProviderEntry] = {}
        self.tiers: Dict[str, str] = {}
        self._available_providers: Optional[Dict[str, bool]] = None

        self._load_catalog()
        logger.info(f"[ModelRegistry] Loaded {len(self.models)} models from {len(self.providers)} providers")

    def _load_catalog(self):
        """Load model catalog from JSON file"""
        if not self.catalog_path.exists():
            logger.warning(f"[ModelRegistry] Catalog not found: {self.catalog_path}")
            return

        try:
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[ModelRegistry] Failed to load catalog: {e}")
            return

        # Load models
        for m in data.get('models', []):
            cost = m.get('cost', {})
            base_url = m.get('baseUrl', '')

            # Resolve empty baseUrl from provider config keys (e.g., KAGGLE_URL)
            if not base_url:
                provider_id = m.get('provider', '')
                prov_data = data.get('providers', {}).get(provider_id, {})
                for key in prov_data.get('configKeys', []):
                    if 'URL' in key.upper():
                        base_url = os.getenv(key, '')
                        break

            entry = ModelEntry(
                id=m['id'],
                name=m['name'],
                provider=m['provider'],
                api=m['api'],
                base_url=base_url,
                context_window=m.get('contextWindow', 8192),
                max_tokens=m.get('maxTokens', 4096),
                reasoning=m.get('reasoning', False),
                input_types=m.get('input', ['text']),
                cost_input=cost.get('input', 0),
                cost_output=cost.get('output', 0),
                tier=m.get('tier', 'balanced'),
                local=m.get('local', False),
                description=m.get('description', ''),
                tags=m.get('tags', []),
                params=m.get('params', ''),
            )
            self.models[entry.id] = entry

        # Load providers
        for pid, p in data.get('providers', {}).items():
            self.providers[pid] = ProviderEntry(
                name=p['name'],
                type=p['type'],
                config_keys=p.get('configKeys', []),
                local=p.get('local', False),
                priority=p.get('priority', 99),
            )

        # Load tier descriptions
        self.tiers = data.get('tiers', {})

    def get_available_providers(self) -> Dict[str, bool]:
        """Check which providers have their API keys configured"""
        if self._available_providers is not None:
            return self._available_providers

        result = {}
        for pid, prov in self.providers.items():
            if prov.local:
                if pid == 'ollama-local':
                    local_url = os.getenv('LOCAL_OLLAMA_URL', 'http://localhost:11434').strip() or 'http://localhost:11434'
                    result[pid] = self._probe_ollama_local(local_url)
                else:
                    result[pid] = True
            else:
                # Check if all required config keys are set
                result[pid] = all(
                    os.getenv(key, '').strip() != ''
                    for key in prov.config_keys
                )
        self._available_providers = result
        return result

    def _probe_ollama_local(self, base_url: str) -> bool:
        """Check whether a local Ollama endpoint is reachable."""
        if not base_url:
            return False

        candidates = []
        normalized = base_url.rstrip('/')
        candidates.append(f"{normalized}/api/tags")
        candidates.append(normalized)

        for url in candidates:
            try:
                request = urllib.request.Request(url, method='GET')
                with urllib.request.urlopen(request, timeout=1.5) as response:
                    return 200 <= getattr(response, 'status', 200) < 500
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            except Exception:
                continue
        return False

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        """Get a model by its ID"""
        return self.models.get(model_id)

    def get_models_by_provider(self, provider: str) -> List[ModelEntry]:
        """Get all models for a provider"""
        return [m for m in self.models.values() if m.provider == provider]

    def get_models_by_tier(self, tier: str) -> List[ModelEntry]:
        """Get all models matching a capability tier"""
        return [m for m in self.models.values() if m.tier == tier]

    def get_best_model(self, tier: str = 'balanced', prefer_local: bool = True) -> Optional[ModelEntry]:
        """
        Get best available model for a tier.

        Priority:
        1. Local models (if prefer_local and available)
        2. Cloud models by provider priority
        """
        available = self.get_available_providers()
        candidates = [
            m for m in self.models.values()
            if m.tier == tier and available.get(m.provider, False)
        ]

        if not candidates:
            # Fallback: try any available model
            candidates = [
                m for m in self.models.values()
                if available.get(m.provider, False)
            ]

        if not candidates:
            return None

        # Sort: local first (if preferred), then by provider priority
        def sort_key(m: ModelEntry):
            prov = self.providers.get(m.provider)
            priority = prov.priority if prov else 99
            local_bonus = 0 if (prefer_local and m.local) else 100
            return (local_bonus, priority)

        candidates.sort(key=sort_key)
        return candidates[0]

    def get_context_window(self, model_id: str) -> int:
        """Get context window size for a model"""
        model = self.models.get(model_id)
        return model.context_window if model else 8192

    def estimate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in dollars for a query"""
        model = self.models.get(model_id)
        if not model:
            return 0.0
        input_cost = (input_tokens / 1_000_000) * model.cost_input
        output_cost = (output_tokens / 1_000_000) * model.cost_output
        return input_cost + output_cost

    def get_provider(self, provider_id: str) -> Optional[ProviderEntry]:
        """Get provider info"""
        return self.providers.get(provider_id)

    def list_available_models(self) -> List[ModelEntry]:
        """List all models from available providers"""
        available = self.get_available_providers()
        return [
            m for m in self.models.values()
            if available.get(m.provider, False)
        ]

    def to_dropdown_items(self) -> List[Dict[str, str]]:
        """Generate items for GUI model dropdown"""
        available = self.get_available_providers()
        items = []
        seen_providers = set()

        # Group by provider, sorted by priority
        sorted_providers = sorted(
            self.providers.items(),
            key=lambda x: x[1].priority
        )

        for pid, prov in sorted_providers:
            if pid in seen_providers:
                continue
            seen_providers.add(pid)

            models = self.get_models_by_provider(pid)
            is_available = available.get(pid, False)

            for m in models:
                suffix = '' if is_available else ' (offline)'
                items.append({
                    'id': m.id,
                    'name': f"{m.name}{suffix}",
                    'provider': pid,
                    'provider_name': prov.name,
                    'available': is_available,
                    'tier': m.tier,
                    'description': m.description,
                    'tags': m.tags,
                    'params': m.params,
                    'reasoning': m.reasoning,
                    'input_types': m.input_types,
                    'context_window': m.context_window,
                })

        return items


# Module-level singleton
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get or create the global model registry"""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
