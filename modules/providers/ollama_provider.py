"""
Ollama Provider Adapter

Handles both local Ollama and Ollama Cloud APIs.
Uses the Ollama REST API format:
- /api/generate (prompt-based, legacy)
- /api/chat (messages-based, preferred)

Works with:
- Local Ollama (localhost:11434)
- Ollama Cloud (ollama.com with API key)
- Any Ollama-compatible endpoint
"""

import json
import logging
import requests
from typing import Optional, Dict, Any, List, Generator

from modules.providers.base_provider import (
    BaseProvider, ProviderConfig, ProviderResponse, StreamChunk, ProviderStatus
)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    """
    Provider adapter for Ollama API (local and cloud).

    Supports:
    - /api/chat (messages format, preferred)
    - /api/generate (prompt format, fallback)
    - Streaming via NDJSON (newline-delimited JSON)
    - Bearer token auth (for cloud)
    - No auth (for local)
    """

    def _get_headers(self) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.config.api_key:
            headers['Authorization'] = f'Bearer {self.config.api_key}'
        return headers

    def complete(self, messages: List[Dict[str, str]], model: str,
                 temperature: float = 0.7, max_tokens: int = 2048,
                 **kwargs) -> ProviderResponse:
        """Send a non-streaming chat request to Ollama"""
        url = f"{self.config.base_url.rstrip('/')}/api/chat"

        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            role = msg.get('role', 'user')
            ollama_messages.append({
                'role': role,
                'content': msg.get('content', ''),
            })

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

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

            if resp.status_code != 200:
                error_msg = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                self.last_error = error_msg
                return ProviderResponse(content="", provider=self.provider_id,
                                        model=model, error=error_msg)

            data = resp.json()
            message = data.get('message', {})
            content = message.get('content', '').strip()

            # Ollama provides token counts in response
            prompt_eval_count = data.get('prompt_eval_count', 0)
            eval_count = data.get('eval_count', 0)

            return ProviderResponse(
                content=content,
                model=data.get('model', model),
                provider=self.provider_id,
                input_tokens=prompt_eval_count,
                output_tokens=eval_count,
                total_tokens=prompt_eval_count + eval_count,
                finish_reason='stop' if data.get('done') else '',
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
        """Stream completion from Ollama via NDJSON"""
        url = f"{self.config.base_url.rstrip('/')}/api/chat"

        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                'role': msg.get('role', 'user'),
                'content': msg.get('content', ''),
            })

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

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

                for line in resp.iter_lines():
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        message = data.get('message', {})
                        content = message.get('content', '')
                        done = data.get('done', False)

                        if content:
                            yield StreamChunk(
                                text=content,
                                done=False,
                                source=self.provider_id,
                            )

                        if done:
                            yield StreamChunk(
                                text="", done=True,
                                source=self.provider_id,
                                metadata={
                                    'input_tokens': data.get('prompt_eval_count', 0),
                                    'output_tokens': data.get('eval_count', 0),
                                }
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

    def complete_generate(self, prompt: str, model: str,
                          temperature: float = 0.7, max_tokens: int = 2048,
                          **kwargs) -> ProviderResponse:
        """
        Legacy /api/generate endpoint (prompt-based, not messages-based).
        Used as fallback for older Ollama versions.
        """
        url = f"{self.config.base_url.rstrip('/')}/api/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        try:
            resp = requests.post(
                url, json=payload, headers=self._get_headers(),
                timeout=self.config.timeout
            )

            if resp.status_code == 200:
                data = resp.json()
                return ProviderResponse(
                    content=data.get('response', '').strip(),
                    model=data.get('model', model),
                    provider=self.provider_id,
                    input_tokens=data.get('prompt_eval_count', 0),
                    output_tokens=data.get('eval_count', 0),
                )
            else:
                return ProviderResponse(
                    content="", provider=self.provider_id, model=model,
                    error=f"HTTP {resp.status_code}"
                )
        except Exception as e:
            return ProviderResponse(
                content="", provider=self.provider_id, model=model,
                error=str(e)
            )

    def check_health(self) -> ProviderStatus:
        """Check Ollama availability by listing tags"""
        url = f"{self.config.base_url.rstrip('/')}/api/tags"

        try:
            resp = requests.get(
                url, headers=self._get_headers(), timeout=3
            )
            if resp.status_code == 200:
                self.last_error = ""
                return ProviderStatus.AVAILABLE
            elif resp.status_code == 401:
                self.last_error = "Invalid API key"
                return ProviderStatus.AUTH_FAILED
            else:
                self.last_error = f"HTTP {resp.status_code}"
                return ProviderStatus.UNAVAILABLE
        except requests.Timeout:
            self.last_error = "Health check timeout"
            return ProviderStatus.UNAVAILABLE
        except Exception as e:
            self.last_error = str(e)
            return ProviderStatus.UNAVAILABLE
