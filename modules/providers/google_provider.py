"""
Google Generative AI Provider Adapter

Handles Google's Gemini models via the google-genai SDK.
Protocol uses SDK methods rather than raw HTTP:
- genai.Client.models.generate_content() for non-streaming
- genai.Client.models.generate_content_stream() for streaming
"""

import logging
import time
from typing import Optional, Dict, Any, List, Generator

from modules.providers.base_provider import (
    BaseProvider, ProviderConfig, ProviderResponse, StreamChunk, ProviderStatus
)

logger = logging.getLogger(__name__)

# Try importing the Google GenAI SDK
try:
    import google.genai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None


class GoogleProvider(BaseProvider):
    """
    Provider adapter for Google Gemini models via google-genai SDK.

    Supports:
    - Gemini 2.0 Flash, 2.5 Flash, 2.5 Pro
    - Thinking (reasoning) mode
    - Multimodal input (text + image)
    - 1M+ context window
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize the Google GenAI client"""
        if not GENAI_AVAILABLE:
            logger.warning("[GoogleProvider] google-genai SDK not installed")
            return

        if not self.config.api_key:
            logger.warning("[GoogleProvider] No GEMINI_API_KEY configured")
            return

        try:
            self._client = genai.Client(api_key=self.config.api_key)
            logger.info("[GoogleProvider] Google GenAI client initialized")
        except Exception as e:
            logger.error(f"[GoogleProvider] Failed to init client: {e}")
            self._client = None

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """
        Convert messages to a single prompt string.
        Google's generate_content() takes a simple string or parts array.
        """
        parts = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'system':
                parts.append(content)
            elif role == 'user':
                parts.append(f"User: {content}")
            elif role == 'assistant':
                parts.append(f"Assistant: {content}")

        return '\n\n'.join(parts)

    def complete(self, messages: List[Dict[str, str]], model: str,
                 temperature: float = 0.7, max_tokens: int = 8192,
                 **kwargs) -> ProviderResponse:
        """Send a non-streaming request to Gemini"""
        if not self._client:
            return ProviderResponse(
                content="", provider=self.provider_id, model=model,
                error="Google GenAI client not initialized"
            )

        prompt = self._build_prompt(messages)

        try:
            config_params = {}
            if temperature > 0:
                config_params['temperature'] = temperature
            if max_tokens:
                config_params['max_output_tokens'] = max_tokens

            generate_config = None
            if config_params:
                generate_config = genai.types.GenerateContentConfig(**config_params)

            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=generate_config,
            )

            if response and response.text:
                # Extract usage metadata if available
                input_tokens = 0
                output_tokens = 0
                if hasattr(response, 'usage_metadata'):
                    um = response.usage_metadata
                    input_tokens = getattr(um, 'prompt_token_count', 0) or 0
                    output_tokens = getattr(um, 'candidates_token_count', 0) or 0

                return ProviderResponse(
                    content=response.text.strip(),
                    model=model,
                    provider=self.provider_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    finish_reason='stop',
                )
            else:
                return ProviderResponse(
                    content="", provider=self.provider_id, model=model,
                    error="Empty response from Gemini"
                )

        except Exception as e:
            error_str = str(e)
            self.last_error = error_str

            # Detect auth errors
            if '401' in error_str or 'API_KEY' in error_str.upper():
                self.status = ProviderStatus.AUTH_FAILED

            # Detect rate limiting
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                self.status = ProviderStatus.RATE_LIMITED

            return ProviderResponse(
                content="", provider=self.provider_id, model=model,
                error=error_str
            )

    def stream_complete(self, messages: List[Dict[str, str]], model: str,
                        temperature: float = 0.7, max_tokens: int = 8192,
                        **kwargs) -> Generator[StreamChunk, None, None]:
        """Stream completion from Gemini"""
        if not self._client:
            yield StreamChunk(text="", done=True, source=self.provider_id,
                              metadata={'error': 'Client not initialized'})
            return

        prompt = self._build_prompt(messages)

        try:
            config_params = {}
            if temperature > 0:
                config_params['temperature'] = temperature
            if max_tokens:
                config_params['max_output_tokens'] = max_tokens

            generate_config = None
            if config_params:
                generate_config = genai.types.GenerateContentConfig(**config_params)

            response_stream = self._client.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=generate_config,
            )

            for chunk in response_stream:
                if hasattr(chunk, 'text') and chunk.text:
                    yield StreamChunk(
                        text=chunk.text,
                        done=False,
                        source=self.provider_id,
                    )

            # Final chunk with usage if available
            yield StreamChunk(text="", done=True, source=self.provider_id)

        except Exception as e:
            self.last_error = str(e)
            yield StreamChunk(text="", done=True, source=self.provider_id,
                              metadata={'error': str(e)})

    def check_health(self) -> ProviderStatus:
        """Check Google Gemini availability"""
        if not GENAI_AVAILABLE:
            self.last_error = "google-genai SDK not installed"
            return ProviderStatus.UNAVAILABLE

        if not self._client:
            self._init_client()
            if not self._client:
                return ProviderStatus.UNAVAILABLE

        try:
            # Lightweight check: list models
            models = self._client.models.list()
            # If we can list models, the API key works
            self.last_error = ""
            return ProviderStatus.AVAILABLE
        except Exception as e:
            self.last_error = str(e)
            if '401' in str(e) or 'API_KEY' in str(e).upper():
                return ProviderStatus.AUTH_FAILED
            return ProviderStatus.UNAVAILABLE
