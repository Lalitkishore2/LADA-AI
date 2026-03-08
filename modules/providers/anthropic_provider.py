"""
Anthropic Provider Adapter

Handles the Anthropic Messages API format used by Claude models.
Protocol differs from OpenAI:
- /v1/messages endpoint instead of /v1/chat/completions
- x-api-key header instead of Authorization Bearer
- system prompt as top-level param, not in messages array
- Different streaming format (event: content_block_delta)
"""

import json
import logging
import requests
from typing import Optional, Dict, Any, List, Generator

from modules.providers.base_provider import (
    BaseProvider, ProviderConfig, ProviderResponse, StreamChunk, ProviderStatus
)

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """
    Provider adapter for Anthropic's Claude API.

    Supports:
    - Claude Opus 4, Sonnet 4, Haiku 4
    - Extended thinking (reasoning mode)
    - Image inputs (base64 in content blocks)
    """

    API_VERSION = "2023-06-01"

    def _get_headers(self) -> Dict[str, str]:
        return {
            'x-api-key': self.config.api_key,
            'anthropic-version': self.API_VERSION,
            'Content-Type': 'application/json',
        }

    def _convert_messages(self, messages: List[Dict[str, str]]):
        """
        Anthropic requires system prompt separate from messages.
        Extract system and convert to Anthropic format.
        """
        system_parts = []
        api_messages = []

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'system':
                system_parts.append(content)
            else:
                # Anthropic only allows 'user' and 'assistant' roles
                api_role = 'user' if role == 'user' else 'assistant'
                api_messages.append({
                    'role': api_role,
                    'content': content,
                })

        # Merge consecutive same-role messages (Anthropic requirement)
        merged = []
        for msg in api_messages:
            if merged and merged[-1]['role'] == msg['role']:
                merged[-1]['content'] += '\n' + msg['content']
            else:
                merged.append(msg)

        # Ensure first message is from user
        if merged and merged[0]['role'] != 'user':
            merged.insert(0, {'role': 'user', 'content': '(continuing conversation)'})

        system = '\n\n'.join(system_parts) if system_parts else None
        return system, merged

    def complete(self, messages: List[Dict[str, str]], model: str,
                 temperature: float = 0.7, max_tokens: int = 4096,
                 **kwargs) -> ProviderResponse:
        """Send a non-streaming completion request"""
        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        system, api_messages = self._convert_messages(messages)

        payload = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }

        if system:
            payload["system"] = system

        # temperature 0 means "not set" for some Anthropic modes
        if temperature > 0:
            payload["temperature"] = temperature

        try:
            resp = requests.post(
                url, json=payload, headers=self._get_headers(),
                timeout=self.config.timeout
            )

            if resp.status_code == 401:
                self.status = ProviderStatus.AUTH_FAILED
                self.last_error = "Invalid API key"
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error="Authentication failed")

            if resp.status_code == 429:
                self.status = ProviderStatus.RATE_LIMITED
                self.last_error = "Rate limited"
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error="Rate limited")

            if resp.status_code != 200:
                error_msg = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                self.last_error = error_msg
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error=error_msg)

            data = resp.json()

            # Extract text from content blocks
            content_blocks = data.get('content', [])
            text_parts = []
            for block in content_blocks:
                if block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))

            content = '\n'.join(text_parts).strip()

            usage = data.get('usage', {})
            return ProviderResponse(
                content=content,
                model=data.get('model', model),
                provider=self.provider_id,
                input_tokens=usage.get('input_tokens', 0),
                output_tokens=usage.get('output_tokens', 0),
                total_tokens=usage.get('input_tokens', 0) + usage.get('output_tokens', 0),
                finish_reason=data.get('stop_reason', ''),
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
                        temperature: float = 0.7, max_tokens: int = 4096,
                        **kwargs) -> Generator[StreamChunk, None, None]:
        """Stream completion via Anthropic SSE format"""
        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        system, api_messages = self._convert_messages(messages)

        payload = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if system:
            payload["system"] = system
        if temperature > 0:
            payload["temperature"] = temperature

        try:
            with requests.post(
                url, json=payload, headers=self._get_headers(),
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

                    # Anthropic SSE: "event: <type>" followed by "data: {json}"
                    if line.startswith('data: '):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            event_type = data.get('type', '')

                            if event_type == 'content_block_delta':
                                delta = data.get('delta', {})
                                if delta.get('type') == 'text_delta':
                                    text = delta.get('text', '')
                                    if text:
                                        yield StreamChunk(
                                            text=text, done=False,
                                            source=self.provider_id,
                                        )

                            elif event_type == 'message_delta':
                                # Final message with usage
                                usage = data.get('usage', {})
                                yield StreamChunk(
                                    text="", done=True,
                                    source=self.provider_id,
                                    metadata={
                                        'finish_reason': data.get('delta', {}).get('stop_reason', ''),
                                        'output_tokens': usage.get('output_tokens', 0),
                                    }
                                )
                                return

                            elif event_type == 'message_stop':
                                yield StreamChunk(text="", done=True,
                                                  source=self.provider_id)
                                return

                            elif event_type == 'error':
                                error_data = data.get('error', {})
                                yield StreamChunk(
                                    text="", done=True,
                                    source=self.provider_id,
                                    metadata={'error': error_data.get('message', 'Unknown error')}
                                )
                                return

                        except json.JSONDecodeError:
                            continue

            yield StreamChunk(text="", done=True, source=self.provider_id)

        except requests.Timeout:
            yield StreamChunk(text="", done=True, source=self.provider_id,
                              metadata={'error': f'Timeout after {self.config.timeout}s'})
        except Exception as e:
            yield StreamChunk(text="", done=True, source=self.provider_id,
                              metadata={'error': str(e)})

    def check_health(self) -> ProviderStatus:
        """Check Anthropic API availability"""
        if not self.config.api_key:
            self.last_error = "No API key configured"
            return ProviderStatus.UNAVAILABLE

        # Anthropic doesn't have a /models endpoint, so do a minimal request
        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        payload = {
            "model": "claude-haiku-4-20250514",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }

        try:
            resp = requests.post(
                url, json=payload, headers=self._get_headers(), timeout=5
            )
            if resp.status_code == 200:
                self.last_error = ""
                return ProviderStatus.AVAILABLE
            elif resp.status_code == 401:
                self.last_error = "Invalid API key"
                return ProviderStatus.AUTH_FAILED
            elif resp.status_code == 429:
                # Rate limited but the key works
                self.last_error = "Rate limited"
                return ProviderStatus.AVAILABLE
            else:
                self.last_error = f"HTTP {resp.status_code}"
                return ProviderStatus.UNAVAILABLE
        except Exception as e:
            self.last_error = str(e)
            return ProviderStatus.UNAVAILABLE
