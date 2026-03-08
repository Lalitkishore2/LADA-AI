"""
OpenAI-Compatible Provider Adapter

Covers ALL providers that use the OpenAI chat completions API format:
- OpenAI (GPT-4o, GPT-4.1, o3-mini)
- Groq (Llama 3.3 70B, Mixtral)
- Mistral AI (Mistral Large, Codestral)
- xAI (Grok 2)
- Cerebras
- Together AI
- Fireworks AI
- Any OpenAI-compatible endpoint

This single adapter replaces what would be 8+ separate implementations.
"""

import json
import logging
import requests
from typing import Optional, Dict, Any, List, Generator

from modules.providers.base_provider import (
    BaseProvider, ProviderConfig, ProviderResponse, StreamChunk, ProviderStatus
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """
    Provider adapter for any OpenAI-compatible API.

    Handles:
    - /v1/chat/completions endpoint (standard)
    - Bearer token authentication
    - SSE streaming (data: {json})
    - Usage token reporting
    """

    def complete(self, messages: List[Dict[str, str]], model: str,
                 temperature: float = 0.7, max_tokens: int = 2048,
                 tools: Optional[List[Dict]] = None,
                 **kwargs) -> ProviderResponse:
        """Send a non-streaming completion request"""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        # Attach tools schema for function calling if provided
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Add any extra params (top_p, frequency_penalty, etc.)
        for k in ('top_p', 'frequency_penalty', 'presence_penalty', 'stop'):
            if k in kwargs:
                payload[k] = kwargs[k]

        headers = {
            'Content-Type': 'application/json',
        }
        if self.config.api_key:
            headers['Authorization'] = f'Bearer {self.config.api_key}'

        try:
            resp = requests.post(
                url, json=payload, headers=headers,
                timeout=self.config.timeout
            )

            if resp.status_code == 401:
                self.status = ProviderStatus.AUTH_FAILED
                self.last_error = "Invalid API key"
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error="Authentication failed")

            if resp.status_code == 429:
                self.status = ProviderStatus.RATE_LIMITED
                retry_after = resp.headers.get('retry-after', '60')
                self.last_error = f"Rate limited (retry after {retry_after}s)"
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error=self.last_error)

            if resp.status_code != 200:
                error_msg = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                self.last_error = error_msg
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error=error_msg)

            data = resp.json()
            choices = data.get('choices', [])
            if not choices:
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error="No choices in response")

            message = choices[0].get('message', {})
            content = message.get('content', '') or ''
            content = content.strip()
            finish_reason = choices[0].get('finish_reason', '')

            # Extract tool calls if the model chose to call functions
            raw_tool_calls = message.get('tool_calls', []) or []
            tool_calls = []
            for tc in raw_tool_calls:
                tool_calls.append({
                    'id': tc.get('id', ''),
                    'type': tc.get('type', 'function'),
                    'function': {
                        'name': tc.get('function', {}).get('name', ''),
                        'arguments': tc.get('function', {}).get('arguments', '{}'),
                    }
                })

            usage = data.get('usage', {})
            return ProviderResponse(
                content=content,
                model=data.get('model', model),
                provider=self.provider_id,
                input_tokens=usage.get('prompt_tokens', 0),
                output_tokens=usage.get('completion_tokens', 0),
                total_tokens=usage.get('total_tokens', 0),
                finish_reason=finish_reason,
                tool_calls=tool_calls,
            )

        except requests.Timeout:
            self.last_error = f"Timeout after {self.config.timeout}s"
            return ProviderResponse(content="", provider=self.provider_id,
                                    model=model, error=self.last_error)
        except requests.ConnectionError as e:
            self.status = ProviderStatus.UNAVAILABLE
            self.last_error = str(e)
            return ProviderResponse(content="", provider=self.provider_id,
                                    model=model, error=f"Connection failed: {e}")
        except Exception as e:
            self.last_error = str(e)
            return ProviderResponse(content="", provider=self.provider_id,
                                    model=model, error=str(e))

    def stream_complete(self, messages: List[Dict[str, str]], model: str,
                        temperature: float = 0.7, max_tokens: int = 2048,
                        **kwargs) -> Generator[StreamChunk, None, None]:
        """Send a streaming completion request via SSE"""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        for k in ('top_p', 'frequency_penalty', 'presence_penalty', 'stop'):
            if k in kwargs:
                payload[k] = kwargs[k]

        headers = {
            'Content-Type': 'application/json',
        }
        if self.config.api_key:
            headers['Authorization'] = f'Bearer {self.config.api_key}'

        try:
            with requests.post(
                url, json=payload, headers=headers,
                timeout=self.config.timeout, stream=True
            ) as resp:

                if resp.status_code != 200:
                    error = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                    yield StreamChunk(text="", done=True, source=self.provider_id,
                                      metadata={'error': error})
                    return

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    # SSE format: "data: {json}" or "data: [DONE]"
                    if line.startswith('data: '):
                        data_str = line[6:]

                        if data_str.strip() == '[DONE]':
                            yield StreamChunk(text="", done=True, source=self.provider_id)
                            return

                        try:
                            data = json.loads(data_str)
                            choices = data.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                content = delta.get('content', '')
                                finish = choices[0].get('finish_reason')

                                if content:
                                    yield StreamChunk(
                                        text=content,
                                        done=False,
                                        source=self.provider_id,
                                    )

                                if finish:
                                    # Extract usage from final chunk if available
                                    usage = data.get('usage', {})
                                    yield StreamChunk(
                                        text="", done=True,
                                        source=self.provider_id,
                                        metadata={
                                            'finish_reason': finish,
                                            'input_tokens': usage.get('prompt_tokens', 0),
                                            'output_tokens': usage.get('completion_tokens', 0),
                                        }
                                    )
                                    return

                        except json.JSONDecodeError:
                            continue

            # If we exit without [DONE], signal completion
            yield StreamChunk(text="", done=True, source=self.provider_id)

        except requests.Timeout:
            yield StreamChunk(text="", done=True, source=self.provider_id,
                              metadata={'error': f'Timeout after {self.config.timeout}s'})
        except Exception as e:
            yield StreamChunk(text="", done=True, source=self.provider_id,
                              metadata={'error': str(e)})

    def check_health(self) -> ProviderStatus:
        """Check if provider is reachable"""
        if not self.config.api_key and not self.config.local:
            self.last_error = "No API key configured"
            return ProviderStatus.UNAVAILABLE

        url = f"{self.config.base_url.rstrip('/')}/models"
        headers = {}
        if self.config.api_key:
            headers['Authorization'] = f'Bearer {self.config.api_key}'

        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                self.last_error = ""
                return ProviderStatus.AVAILABLE
            elif resp.status_code == 401:
                self.last_error = "Invalid API key"
                return ProviderStatus.AUTH_FAILED
            elif resp.status_code == 429:
                self.last_error = "Rate limited"
                return ProviderStatus.RATE_LIMITED
            else:
                self.last_error = f"HTTP {resp.status_code}"
                return ProviderStatus.UNAVAILABLE
        except requests.Timeout:
            self.last_error = "Health check timeout"
            return ProviderStatus.UNAVAILABLE
        except Exception as e:
            self.last_error = str(e)
            return ProviderStatus.UNAVAILABLE
