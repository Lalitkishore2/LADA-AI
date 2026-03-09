"""
LADA API — Dashboard and LADA App routes (/dashboard, /app, /sessions/*, /cost, /providers)
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)


def create_app_router(state):
    """Create dashboard + LADA web app + sessions/cost/providers router."""
    r = APIRouter(tags=["app"])
    base_dir = Path(__file__).parent.parent.parent.parent  # JarvisAI/
    dashboard_dir = base_dir / "web"
    sessions_dir = base_dir / "data" / "sessions"

    # ── Dashboard ────────────────────────────────────────────

    @r.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        index_file = dashboard_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding='utf-8'))
        return HTMLResponse(content="<h1>LADA Dashboard</h1><p>web/index.html not found</p>")

    @r.get("/app", response_class=HTMLResponse)
    async def serve_app():
        app_file = dashboard_dir / "lada_app.html"
        if app_file.exists():
            return HTMLResponse(content=app_file.read_text(encoding='utf-8'))
        return HTMLResponse(content="<h1>LADA App</h1><p>web/lada_app.html not found.</p>")

    # ── Sessions ─────────────────────────────────────────────

    @r.get("/sessions")
    async def list_sessions():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        sessions = sorted(p.stem for p in sessions_dir.glob("*.json"))
        return {"sessions": sessions}

    @r.post("/sessions/new")
    async def new_session(body: dict = Body(default={})):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Session name required")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_path = sessions_dir / f"{name}.json"
        existing = session_path.exists()
        if not existing:
            session_path.write_text(
                json.dumps({"session_name": name, "updated_at": datetime.now().isoformat(), "messages": []},
                           indent=2, ensure_ascii=False),
                encoding='utf-8',
            )
        return {"session_name": name, "created": not existing}

    @r.post("/sessions/switch")
    async def switch_session(body: dict = Body(default={})):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Session name required")
        session_path = sessions_dir / f"{name}.json"
        if session_path.exists():
            data = json.loads(session_path.read_text(encoding='utf-8'))
            return {"session_name": name, "messages": data.get("messages", [])}
        return {"session_name": name, "messages": []}

    @r.delete("/sessions/{name}")
    async def delete_session(name: str):
        session_path = sessions_dir / f"{name}.json"
        if session_path.exists():
            session_path.unlink()
            return {"deleted": True, "session_name": name}
        return {"deleted": False, "session_name": name}

    @r.post("/sessions/save")
    async def save_session(body: dict = Body(default={})):
        name = (body.get("name") or "").strip()
        messages = body.get("messages", [])
        if not name:
            raise HTTPException(status_code=400, detail="Session name required")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_path = sessions_dir / f"{name}.json"
        session_data = {
            "session_name": name, "updated_at": datetime.now().isoformat(), "messages": messages,
        }
        session_path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False), encoding='utf-8')
        return {"saved": True, "session_name": name, "message_count": len(messages)}

    # ── Cost ─────────────────────────────────────────────────

    @r.get("/cost/summary")
    async def cost_summary():
        state.load_components()
        try:
            from modules.token_counter import CostTracker
            ct = CostTracker(persist_path="data/cost_history.json")
            return ct.get_summary()
        except Exception as e:
            return {"error": str(e), "total_requests": 0, "total_tokens": 0, "total_cost_usd": 0}

    # ── Providers ────────────────────────────────────────────

    @r.get("/providers/status")
    async def providers_status():
        state.load_components()
        result = []
        pm = getattr(state.ai_router, 'provider_manager', None) if state.ai_router else None
        if pm:
            try:
                for name, pinfo in pm.providers.items():
                    result.append({
                        "name": name,
                        "type": getattr(pinfo, 'type', str(pinfo)),
                        "healthy": True,
                        "models": getattr(pinfo, 'model_count', 0),
                    })
            except Exception:
                pass
        if not result:
            provider_keys = {
                "Groq": "GROQ_API_KEY", "Gemini": "GEMINI_API_KEY",
                "OpenAI": "OPENAI_API_KEY", "Anthropic": "ANTHROPIC_API_KEY",
                "Mistral": "MISTRAL_API_KEY", "xAI": "XAI_API_KEY",
                "DeepSeek": "DEEPSEEK_API_KEY", "Together": "TOGETHER_API_KEY",
                "Fireworks": "FIREWORKS_API_KEY", "Cerebras": "CEREBRAS_API_KEY",
                "Ollama": "LOCAL_OLLAMA_URL",
            }
            for pname, env_key in provider_keys.items():
                has_key = bool(os.getenv(env_key))
                result.append({"name": pname, "healthy": has_key, "models": 0})
        return {"providers": result}

    return r
