"""
LADA API — OpenAI-compatible routes (/v1/models, /v1/chat/completions)
"""

import os
import json
import time
import uuid
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request, Response, Depends
from fastapi.responses import StreamingResponse, JSONResponse

from modules.api.deps import set_request_id_header
from modules.api.models import OpenAIChatRequest
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)


def _sanitize_provider_error_detail(raw_error: Optional[str]) -> str:
    """Return a client-safe provider error message."""
    if not raw_error:
        return "Unable to reach the upstream service. Please try again later."

    error_info = safe_error_response(RuntimeError(raw_error), operation="openai_provider")
    return error_info.get("error") or "Unable to reach the upstream service. Please try again later."


def create_openai_compat_router(state):
    """Create OpenAI-compatible /v1 router."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="openai")

    r = APIRouter(tags=["openai-compat"], dependencies=[Depends(_trace_request)])

    def _verify_api_key(authorization: Optional[str]):
        expected = os.getenv("LADA_API_KEY", "")
        if not expected:
            return
        if not authorization or authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="Invalid API key")

    @r.get("/v1/models")
    async def openai_list_models(authorization: Optional[str] = Header(None)):
        _verify_api_key(authorization)
        state.load_components()

        created = int(state.start_time.timestamp())
        models_list = [{"id": "auto", "object": "model", "created": created, "owned_by": "lada"}]
        seen_ids = {"auto"}

        discovered = []

        pm = getattr(state.ai_router, 'provider_manager', None) if state.ai_router else None
        if pm and getattr(pm, 'model_registry', None):
            try:
                for entry in pm.model_registry.list_available_models():
                    if entry.provider == "ollama-local":
                        continue
                    discovered.append({
                        "id": entry.id,
                        "provider": entry.provider,
                    })
            except Exception as e:
                logger.warning(f"[OpenAI-compat] model registry list failed: {e}")

        # Fallback path: use dropdown metadata when registry list is empty.
        if (not discovered) and state.ai_router and hasattr(state.ai_router, 'get_provider_dropdown_items'):
            try:
                for item in state.ai_router.get_provider_dropdown_items() or []:
                    mid = str(item.get('value', '')).strip()
                    if not mid or mid == 'auto':
                        continue

                    label = str(item.get('label', ''))
                    if '(offline)' in label.lower():
                        continue

                    discovered.append({
                        "id": mid,
                        "provider": item.get('provider', 'lada'),
                    })
            except Exception as e:
                logger.warning(f"[OpenAI-compat] provider dropdown fallback failed: {e}")

        for row in discovered:
            model_id = row.get('id')
            if not model_id or model_id in seen_ids:
                continue
            seen_ids.add(model_id)
            models_list.append({
                "id": model_id,
                "object": "model",
                "created": created,
                "owned_by": row.get('provider', 'lada'),
            })

        return {"object": "list", "data": models_list}

    @r.post("/v1/chat/completions")
    async def openai_chat_completions(
        request: OpenAIChatRequest, authorization: Optional[str] = Header(None),
    ):
        _verify_api_key(authorization)
        state.load_components()

        if not state.ai_router:
            raise HTTPException(status_code=503, detail="AI Router not available")

        model_id = request.model if request.model != "auto" else None
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        temperature = request.temperature or 0.7
        max_tokens = request.max_tokens or 2048

        last_user_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_user_msg = m["content"]
                break

        if request.stream:
            pm = getattr(state.ai_router, 'provider_manager', None)
            if pm and model_id and not pm.get_provider_for_model(model_id):
                raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
            return StreamingResponse(
                _stream_generator(state, messages, model_id, last_user_msg, temperature, max_tokens),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
            )
        else:
            return await _complete(state, messages, model_id, last_user_msg, temperature, max_tokens)

    return r


async def _complete(state, messages, model_id, last_user_msg, temperature, max_tokens):
    """Non-streaming OpenAI-format chat completion."""
    pm = getattr(state.ai_router, 'provider_manager', None)
    sys_prompt = getattr(state.ai_router, 'system_prompt', '')

    if sys_prompt and not any(m["role"] == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": sys_prompt})

    used_model = "auto"
    response = None

    if pm and model_id:
        provider = pm.get_provider_for_model(model_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
        if pm._rate_limiter:
            allowed, reason = pm._rate_limiter.check(provider.provider_id)
            if not allowed:
                raise HTTPException(status_code=429, detail=f"Rate limited: {reason}")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: provider.complete_with_retry(messages, model_id, temperature, max_tokens))
        if pm._rate_limiter:
            if response.success:
                pm._rate_limiter.record_success(provider.provider_id)
            else:
                pm._rate_limiter.record_failure(provider.provider_id)
        if not response.success:
            raise HTTPException(status_code=502, detail=_sanitize_provider_error_detail(response.error))
        used_model = model_id

    elif pm:
        selection = pm.get_best_model(last_user_msg)
        if not selection:
            raise HTTPException(status_code=503, detail="No models available")
        auto_model = selection['model_id']
        provider = pm.get_provider(selection['provider_id'])
        if pm._rate_limiter:
            allowed, reason = pm._rate_limiter.check(provider.provider_id)
            if not allowed:
                raise HTTPException(status_code=429, detail=f"Rate limited: {reason}")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: provider.complete_with_retry(messages, auto_model, temperature, max_tokens))
        if pm._rate_limiter:
            if response.success:
                pm._rate_limiter.record_success(provider.provider_id)
            else:
                pm._rate_limiter.record_failure(provider.provider_id)
        if not response.success:
            raise HTTPException(status_code=502, detail=_sanitize_provider_error_detail(response.error))
        used_model = auto_model

    else:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, lambda: state.ai_router.query(last_user_msg))
        from modules.providers.base_provider import ProviderResponse
        response = ProviderResponse(content=text or "", provider="legacy")
        used_model = getattr(state.ai_router, 'current_backend_name', 'auto')

    completion_id = f"chatcmpl-lada-{uuid.uuid4().hex[:12]}"
    return JSONResponse({
        "id": completion_id, "object": "chat.completion", "created": int(time.time()),
        "model": used_model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response.content},
            "finish_reason": getattr(response, 'finish_reason', 'stop') or "stop",
        }],
        "usage": {
            "prompt_tokens": getattr(response, 'input_tokens', 0),
            "completion_tokens": getattr(response, 'output_tokens', 0),
            "total_tokens": getattr(response, 'total_tokens', 0),
        },
    })


async def _stream_generator(state, messages, model_id, last_user_msg, temperature, max_tokens):
    """Streaming SSE generator in OpenAI chat.completion.chunk format."""
    pm = getattr(state.ai_router, 'provider_manager', None)
    sys_prompt = getattr(state.ai_router, 'system_prompt', '')

    if sys_prompt and not any(m["role"] == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": sys_prompt})

    completion_id = f"chatcmpl-lada-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    used_model = "auto"
    provider = None

    if pm and model_id:
        provider = pm.get_provider_for_model(model_id)
        used_model = model_id
    elif pm:
        selection = pm.get_best_model(last_user_msg)
        if selection:
            provider = pm.get_provider(selection['provider_id'])
            used_model = selection['model_id']

    if provider:
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _stream_in_thread():
            try:
                for chunk in provider.stream_complete(messages, used_model, temperature, max_tokens):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            except Exception as e:
                logger.error(f"[OpenAI-compat] Stream error: {e}")
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop.run_in_executor(None, _stream_in_thread)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            if chunk.text:
                data = {
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": used_model,
                    "choices": [{"index": 0, "delta": {"content": chunk.text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(data)}\n\n"
            if chunk.done:
                break
    else:
        loop = asyncio.get_event_loop()
        chunks = await loop.run_in_executor(
            None, lambda: list(state.ai_router.stream_query(last_user_msg)))
        for chunk_data in chunks:
            text = chunk_data.get('chunk', '')
            if text:
                data = {
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": used_model,
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(data)}\n\n"
            if chunk_data.get('done'):
                break

    final = {
        "id": completion_id, "object": "chat.completion.chunk", "created": created,
        "model": used_model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"
