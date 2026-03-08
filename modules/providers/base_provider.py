"""
Base Provider - Abstract interface for all AI provider adapters.

Every AI backend (OpenAI, Anthropic, Google, Ollama, etc.) implements
this interface. The ProviderManager uses these adapters to route
queries across 22+ providers with unified streaming, error handling,
and cost tracking.

Design inspired by OpenClaw's multi-protocol provider system but
with added cost tracking, context window enforcement, and retry policies.
"""

import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Generator
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider health status"""
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"


@dataclass
class ProviderConfig:
    """
    Configuration for an AI provider.
    Loaded from models.json and .env.
    """
    provider_id: str           # e.g. "openai", "anthropic", "google"
    name: str                  # e.g. "OpenAI", "Anthropic"
    api_type: str              # e.g. "openai-completions", "anthropic-messages", "ollama"
    base_url: str              # e.g. "https://api.openai.com/v1"
    api_key: str = ""          # Auth key
    default_model: str = ""    # Default model to use
    timeout: float = 60.0      # Request timeout
    max_retries: int = 2       # Max retry attempts
    local: bool = False        # Is this a local provider
    priority: int = 99         # Lower = higher priority
    enabled: bool = True


@dataclass
class ProviderResponse:
    """
    Unified response from any AI provider.
    Normalizes response format across all APIs.
    """
    content: str                # Response text
    model: str = ""             # Model used
    provider: str = ""          # Provider ID
    input_tokens: int = 0       # Input token count (from API)
    output_tokens: int = 0      # Output token count (from API)
    total_tokens: int = 0       # Total tokens
    finish_reason: str = ""     # "stop", "length", "content_filter"
    latency_ms: float = 0       # Response time in milliseconds
    cached: bool = False        # Was this from cache
    error: str = ""             # Error message if failed
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # Function/tool calls from model

    @property
    def success(self) -> bool:
        return bool(self.content) and not self.error


@dataclass
class StreamChunk:
    """
    Single chunk from a streaming response.
    Yielded by stream_complete().
    """
    text: str = ""              # Chunk text
    done: bool = False          # Is this the final chunk
    source: str = ""            # Provider ID
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """
    Abstract base class for all AI provider adapters.

    Subclasses must implement:
    - complete() - single response
    - stream_complete() - streaming generator
    - check_health() - availability check

    The base class provides:
    - Retry logic with exponential backoff
    - Health status tracking
    - Response timing
    - Unified message formatting
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.status = ProviderStatus.UNKNOWN
        self.last_check: float = 0
        self.last_error: str = ""
        self.total_requests: int = 0
        self.total_errors: int = 0
        self.avg_latency_ms: float = 0
        self._health_check_interval = 60  # seconds

    @property
    def provider_id(self) -> str:
        return self.config.provider_id

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_available(self) -> bool:
        return self.status == ProviderStatus.AVAILABLE

    @property
    def needs_health_check(self) -> bool:
        return (time.time() - self.last_check) > self._health_check_interval

    # ============================================================
    # Abstract methods - must be implemented by subclass
    # ============================================================

    @abstractmethod
    def complete(self, messages: List[Dict[str, str]], model: str,
                 temperature: float = 0.7, max_tokens: int = 2048,
                 **kwargs) -> ProviderResponse:
        """
        Send a completion request and return the full response.

        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            model: Model ID to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        pass

    @abstractmethod
    def stream_complete(self, messages: List[Dict[str, str]], model: str,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        **kwargs) -> Generator[StreamChunk, None, None]:
        """
        Send a streaming completion request.
        Yields StreamChunk objects as response arrives.
        """
        pass

    @abstractmethod
    def check_health(self) -> ProviderStatus:
        """
        Check if the provider is available and responding.
        Should be fast (< 3s timeout).
        """
        pass

    # ============================================================
    # Shared methods
    # ============================================================

    def ensure_available(self) -> bool:
        """Check health if needed and return availability"""
        if self.needs_health_check:
            self.status = self.check_health()
            self.last_check = time.time()
        return self.is_available

    def complete_with_retry(self, messages: List[Dict[str, str]], model: str,
                            temperature: float = 0.7, max_tokens: int = 2048,
                            **kwargs) -> ProviderResponse:
        """
        Complete with automatic retry and exponential backoff.
        """
        last_error = ""
        for attempt in range(self.config.max_retries + 1):
            try:
                start = time.time()
                response = self.complete(messages, model, temperature, max_tokens, **kwargs)
                elapsed = (time.time() - start) * 1000

                self.total_requests += 1
                self._update_latency(elapsed)
                response.latency_ms = elapsed

                if response.success:
                    return response
                else:
                    last_error = response.error or "Empty response"

            except Exception as e:
                last_error = str(e)
                self.total_errors += 1
                logger.warning(f"[{self.name}] Attempt {attempt + 1} failed: {e}")

                if attempt < self.config.max_retries:
                    backoff = min(2 ** attempt, 8)
                    time.sleep(backoff)

        return ProviderResponse(
            content="",
            model=model,
            provider=self.provider_id,
            error=f"All {self.config.max_retries + 1} attempts failed: {last_error}",
        )

    def build_messages(self, prompt: str, system_prompt: str = "",
                       history: Optional[List[Dict[str, str]]] = None,
                       web_context: str = "") -> List[Dict[str, str]]:
        """
        Build standardized message list from components.
        This is the unified format across all providers.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if web_context:
            messages.append({
                "role": "system",
                "content": f"[Real-time web data]\n{web_context}"
            })

        if history:
            messages.extend(history[-6:])  # Last 3 exchanges

        messages.append({"role": "user", "content": prompt})
        return messages

    def _update_latency(self, new_ms: float):
        """Update running average latency"""
        if self.total_requests <= 1:
            self.avg_latency_ms = new_ms
        else:
            self.avg_latency_ms = (self.avg_latency_ms * 0.8) + (new_ms * 0.2)

    def get_status_dict(self) -> Dict[str, Any]:
        """Get provider status as dictionary"""
        return {
            'provider_id': self.provider_id,
            'name': self.name,
            'status': self.status.value,
            'available': self.is_available,
            'local': self.config.local,
            'priority': self.config.priority,
            'avg_latency_ms': round(self.avg_latency_ms, 1),
            'total_requests': self.total_requests,
            'total_errors': self.total_errors,
            'last_error': self.last_error,
        }
