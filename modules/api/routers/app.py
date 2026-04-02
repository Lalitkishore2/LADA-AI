"""
LADA API — Dashboard and LADA App routes (/dashboard, /app, /sessions/*, /cost, /providers)
"""

import os
import json
import asyncio
import hashlib
import ipaddress
import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Body, Query, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from modules.api.deps import REQUEST_ID_HEADER, ensure_request_id, set_request_id_header
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)


def create_app_router(state):
    """Create dashboard + LADA web app + sessions/cost/providers router."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="http")

    r = APIRouter(tags=["app"], dependencies=[Depends(_trace_request)])
    base_dir = Path(__file__).parent.parent.parent.parent  # JarvisAI/
    dashboard_dir = base_dir / "web"
    sessions_dir = base_dir / "data" / "sessions"
    remote_rate_windows: Dict[str, Dict[str, float]] = {}
    remote_idempotency_cache: Dict[str, Dict[str, Any]] = {}

    def _bool_env(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _rollout_stage() -> str:
        stage = os.getenv("LADA_ROLLOUT_STAGE", "local").strip().lower()
        valid = {"disabled", "local", "internal", "canary", "public"}
        return stage if stage in valid else "local"

    def _find_tailscale_binary() -> str:
        for candidate in [
            os.path.join(os.environ.get("ProgramFiles", ""), "Tailscale", "tailscale.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Tailscale", "tailscale.exe"),
        ]:
            if candidate and os.path.isfile(candidate):
                return candidate
        return shutil.which("tailscale") or ""

    def _tailscale_rollout_status(deep_check: bool) -> dict:
        enabled = _bool_env("LADA_TAILSCALE_FUNNEL", False)
        tailscale_cmd = _find_tailscale_binary() if enabled else ""
        status = {
            "enabled": enabled,
            "binary_found": bool(tailscale_cmd),
            "deep_checked": False,
            "status": "disabled",
            "connected": False,
            "dns_name": "",
            "public_url": "",
        }

        if not enabled:
            return status

        if not tailscale_cmd:
            status["status"] = "not_installed"
            return status

        if not deep_check:
            status["status"] = "ready_for_check"
            return status

        status["deep_checked"] = True
        try:
            result = subprocess.run(
                [tailscale_cmd, "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                status["status"] = "not_connected"
                return status

            payload = json.loads(result.stdout or "{}")
            dns_name = str(payload.get("Self", {}).get("DNSName", "")).rstrip(".")
            connected = bool(payload.get("Self"))

            status["connected"] = connected
            status["dns_name"] = dns_name
            if dns_name:
                status["public_url"] = f"https://{dns_name}/app"
            status["status"] = "connected" if connected else "not_connected"
            return status
        except Exception:
            status["status"] = "error"
            return status

    def _int_env(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def _remote_control_enabled() -> bool:
        return _bool_env("LADA_REMOTE_CONTROL_ENABLED", False)

    def _remote_download_enabled() -> bool:
        return _bool_env("LADA_REMOTE_DOWNLOAD_ENABLED", False)

    def _dangerous_remote_enabled() -> bool:
        return _bool_env("LADA_REMOTE_ALLOW_DANGEROUS", False)

    def _remote_command_rpm() -> int:
        return max(0, _int_env("LADA_REMOTE_COMMAND_RPM", 30))

    def _remote_files_rpm() -> int:
        return max(0, _int_env("LADA_REMOTE_FILES_RPM", 60))

    def _remote_download_rpm() -> int:
        return max(0, _int_env("LADA_REMOTE_DOWNLOAD_RPM", 30))

    def _remote_idempotency_ttl_seconds() -> int:
        return max(30, _int_env("LADA_REMOTE_IDEMPOTENCY_TTL_SEC", 180))

    def _normalize_idempotency_key(raw_key: str) -> str:
        token = (raw_key or "").strip()
        if not token:
            return ""

        sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", ":", "|"} else "-" for ch in token)
        sanitized = sanitized[:128].strip("-_.:|")
        return sanitized

    def _cleanup_remote_idempotency_cache(now_ts: float) -> None:
        ttl = _remote_idempotency_ttl_seconds()
        stale_keys = [
            key
            for key, entry in remote_idempotency_cache.items()
            if now_ts - float(entry.get("created_at", 0)) >= ttl
        ]
        for key in stale_keys:
            remote_idempotency_cache.pop(key, None)

    def _remote_command_allowlist() -> list[str]:
        raw = os.getenv("LADA_REMOTE_ALLOWED_COMMANDS", "").strip()
        if not raw:
            return []

        for sep in ["\n", ","]:
            raw = raw.replace(sep, ";")

        values = []
        for item in raw.split(";"):
            token = item.strip().lower()
            if token:
                values.append(token)
        return values

    def _is_allowed_remote_command(command: str) -> bool:
        allowlist = _remote_command_allowlist()
        if not allowlist:
            return True

        normalized = " ".join(command.lower().split())
        for allowed in allowlist:
            if normalized == allowed or normalized.startswith(allowed + " "):
                return True
        return False

    def _max_download_bytes() -> int:
        try:
            mb = float(os.getenv("LADA_REMOTE_MAX_DOWNLOAD_MB", "50"))
            if mb <= 0:
                mb = 1
        except ValueError:
            mb = 50
        return int(mb * 1024 * 1024)

    def _default_remote_roots() -> list[Path]:
        home = Path.home()
        candidates = [
            home / "Desktop",
            home / "Documents",
            home / "Downloads",
            home / "Pictures",
            home / "Videos",
            home / "Music",
            home,
        ]
        return [p for p in candidates if p.exists()]

    def _allowed_remote_roots() -> list[Path]:
        raw = os.getenv("LADA_REMOTE_ALLOWED_ROOTS", "").strip()
        roots: list[Path] = []

        if raw:
            for sep in ["\n", ","]:
                raw = raw.replace(sep, ";")
            for item in raw.split(";"):
                token = item.strip().strip('"')
                if not token:
                    continue
                try:
                    path_obj = Path(token).resolve(strict=False)
                    if path_obj.exists():
                        roots.append(path_obj)
                except Exception:
                    continue

        if not roots:
            roots = _default_remote_roots()

        deduped: list[Path] = []
        seen = set()
        for root in roots:
            key = str(root).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root)
        return deduped

    def _is_within(child: Path, root: Path) -> bool:
        try:
            child.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve_remote_path(raw_path: str, *, require_exists: bool) -> Path:
        value = (raw_path or "").strip().strip('"')
        if not value:
            raise HTTPException(status_code=400, detail="Path is required")
        candidate = Path(value)
        if not candidate.is_absolute():
            raise HTTPException(status_code=400, detail="Path must be absolute")
        try:
            return candidate.resolve(strict=require_exists)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Path not found")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path")

    def _ensure_allowed_path(path_obj: Path) -> None:
        roots = _allowed_remote_roots()
        if not roots:
            raise HTTPException(status_code=503, detail="No allowed remote roots configured")
        if not any(_is_within(path_obj, root) for root in roots):
            raise HTTPException(status_code=403, detail="Path is outside allowed remote roots")

    def _validate_remote_path(raw_path: str, *, directory: bool = False, file: bool = False) -> Path:
        path_obj = _resolve_remote_path(raw_path, require_exists=True)
        _ensure_allowed_path(path_obj)
        if directory and not path_obj.is_dir():
            raise HTTPException(status_code=400, detail="Path must be a directory")
        if file and not path_obj.is_file():
            raise HTTPException(status_code=400, detail="Path must be a file")
        return path_obj

    def _build_remote_breadcrumbs(path_obj: Path, roots: list[Path]) -> list[Dict[str, str | bool]]:
        if not roots:
            return [{"name": path_obj.name or str(path_obj), "path": str(path_obj), "is_root": False}]

        matched_root = None
        for root in sorted(roots, key=lambda p: len(str(p)), reverse=True):
            if _is_within(path_obj, root):
                matched_root = root
                break

        if matched_root is None:
            return [{"name": path_obj.name or str(path_obj), "path": str(path_obj), "is_root": False}]

        breadcrumbs: list[Dict[str, str | bool]] = [
            {
                "name": matched_root.name or str(matched_root),
                "path": str(matched_root),
                "is_root": True,
            }
        ]

        current = matched_root
        for part in path_obj.relative_to(matched_root).parts:
            current = current / part
            breadcrumbs.append({"name": part, "path": str(current), "is_root": False})

        return breadcrumbs

    def _check_remote_rate_limit(request: Request, action: str, rpm: int) -> None:
        if rpm <= 0:
            return

        identity = _token_fingerprint(request) or _client_ip(request) or "unknown"
        key = f"{action}:{identity}"
        now = time.time()

        if len(remote_rate_windows) > 2000:
            stale_keys = [k for k, v in remote_rate_windows.items() if now - v.get("window_start", now) >= 180]
            for stale_key in stale_keys:
                remote_rate_windows.pop(stale_key, None)

        window = remote_rate_windows.get(key)
        if not window or now - window.get("window_start", 0) >= 60:
            remote_rate_windows[key] = {"window_start": now, "count": 1}
            return

        window["count"] = window.get("count", 0) + 1
        if window["count"] > rpm:
            retry_after = max(1, int(60 - (now - window.get("window_start", now))))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Remote {action} rate limit exceeded ({rpm}/min). "
                    f"Retry in {retry_after}s."
                ),
            )

    def _client_ip(request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "").strip()
        real_ip = request.headers.get("x-real-ip", "").strip()
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"

    def _client_scope(ip_text: str) -> str:
        token = (ip_text or "").strip().lower()
        if token in {"localhost", "testclient"}:
            return "loopback"

        try:
            ip_obj = ipaddress.ip_address(token)
        except ValueError:
            return "unknown"

        if ip_obj.is_loopback:
            return "loopback"
        if ip_obj.is_private:
            return "private"
        return "public"

    def _enforce_rollout_remote_access(request: Request, feature: str) -> None:
        stage = _rollout_stage()
        if stage == "disabled":
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Remote {feature} is disabled by rollout stage policy "
                    f"(LADA_ROLLOUT_STAGE=disabled)."
                ),
            )

        scope = _client_scope(_client_ip(request))

        if stage == "local" and scope != "loopback":
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Remote {feature} is restricted to local machine access "
                    f"while LADA_ROLLOUT_STAGE=local."
                ),
            )

        if stage == "internal" and scope not in {"loopback", "private"}:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Remote {feature} is restricted to private/LAN access "
                    f"while LADA_ROLLOUT_STAGE=internal."
                ),
            )

    def _token_fingerprint(request: Request) -> str:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else request.query_params.get("token", "")
        if not token:
            return ""
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return digest[:16]

    def _audit_remote_event(event_type: str, success: bool, request: Request, details: Dict) -> None:
        try:
            from modules.remote_audit import log_remote_event

            request_id = ensure_request_id(request, prefix="http")
            payload = {
                "request_id": request_id,
                "client_ip": _client_ip(request),
                "token_fp": _token_fingerprint(request),
                **(details or {}),
            }
            log_remote_event(event_type=event_type, success=success, details=payload)
        except Exception as exc:
            logger.warning(f"[Remote] Audit log failed: {exc}")

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
            error_info = safe_error_response(e, operation="cost_summary")
            logger.warning(f"[APIServer] cost_summary error: {type(e).__name__}")
            return {
                "error": error_info["error"],
                "total_requests": 0,
                "total_tokens": 0,
                "total_cost_usd": 0,
            }

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

    # ── Rollout ──────────────────────────────────────────────

    @r.get("/rollout/status")
    async def rollout_status(request: Request, deep_check: bool = Query(False)):
        request_id = ensure_request_id(request, prefix="http")
        stage = _rollout_stage()
        remote = {
            "control_enabled": _remote_control_enabled(),
            "downloads_enabled": _remote_download_enabled(),
            "dangerous_enabled": _dangerous_remote_enabled(),
            "allowlist_enforced": bool(_remote_command_allowlist()),
        }
        funnel = _tailscale_rollout_status(deep_check=deep_check)

        blockers = []
        if stage in {"canary", "public"} and not (remote["control_enabled"] or remote["downloads_enabled"]):
            blockers.append("Enable remote control or remote downloads before canary/public rollout.")
        if stage == "public" and not funnel["enabled"]:
            blockers.append("Set LADA_TAILSCALE_FUNNEL=true before public rollout.")
        if stage in {"canary", "public"} and funnel["enabled"] and not funnel["binary_found"]:
            blockers.append("Install tailscale to use LADA_TAILSCALE_FUNNEL in canary/public rollout.")

        return {
            "request_id": request_id,
            "env_name": os.getenv("ENV_NAME", "production"),
            "rollout_stage": stage,
            "remote": remote,
            "funnel": funnel,
            "readiness": {
                "ready": len(blockers) == 0,
                "blockers": blockers,
            },
        }

    # ── Remote Control + File Access ────────────────────────

    @r.get("/remote/status")
    async def remote_status(request: Request):
        request_id = ensure_request_id(request, prefix="http")
        max_bytes = _max_download_bytes()
        allowlist = _remote_command_allowlist()
        return {
            "request_id": request_id,
            "enabled": _remote_control_enabled(),
            "downloads_enabled": _remote_download_enabled(),
            "dangerous_enabled": _dangerous_remote_enabled(),
            "command_policy": "allowlist" if allowlist else "blocklist",
            "allowed_command_prefixes": allowlist,
            "command_rpm": _remote_command_rpm(),
            "files_rpm": _remote_files_rpm(),
            "download_rpm": _remote_download_rpm(),
            "allowed_roots": [str(p) for p in _allowed_remote_roots()],
            "max_download_mb": round(max_bytes / (1024 * 1024), 2),
        }

    @r.post("/remote/command")
    async def remote_command(request: Request, body: dict = Body(default={})):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            _audit_remote_event("remote.command", False, request, {"reason": "remote_control_disabled"})
            raise HTTPException(
                status_code=403,
                detail="Remote control is disabled. Set LADA_REMOTE_CONTROL_ENABLED=true to enable it.",
            )

        command = str(body.get("command", "")).strip()
        if not command:
            _audit_remote_event("remote.command", False, request, {"reason": "missing_command"})
            raise HTTPException(status_code=400, detail="Command is required")
        if len(command) > 500:
            _audit_remote_event("remote.command", False, request, {"reason": "command_too_long"})
            raise HTTPException(status_code=400, detail="Command is too long")

        idempotency_key = _normalize_idempotency_key(request.headers.get("idempotency-key", ""))
        idempotency_scope = _token_fingerprint(request) or _client_ip(request) or "unknown"
        idempotency_cache_key = ""
        if idempotency_key:
            now_ts = time.time()
            _cleanup_remote_idempotency_cache(now_ts)
            idempotency_cache_key = f"{idempotency_scope}|{idempotency_key}"
            cached_entry = remote_idempotency_cache.get(idempotency_cache_key)
            if cached_entry:
                cached_command = str(cached_entry.get("command", ""))
                if cached_command != command:
                    _audit_remote_event(
                        "remote.command",
                        False,
                        request,
                        {
                            "reason": "idempotency_conflict",
                            "command": command,
                            "idempotency_key": idempotency_key,
                        },
                    )
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency key reuse with a different command is not allowed.",
                    )

                replay_payload = dict(cached_entry.get("response") or {})
                replay_payload["request_id"] = request_id
                replay_payload["idempotency"] = {
                    "key": idempotency_key,
                    "replayed": True,
                }
                _audit_remote_event(
                    "remote.command",
                    True,
                    request,
                    {
                        "command": command,
                        "engine": replay_payload.get("engine", "unknown"),
                        "handled": bool(replay_payload.get("handled", False)),
                        "idempotency_replay": True,
                    },
                )
                return replay_payload

        try:
            _check_remote_rate_limit(request, "command", _remote_command_rpm())
        except HTTPException as exc:
            if exc.status_code == 429:
                _audit_remote_event(
                    "remote.command",
                    False,
                    request,
                    {
                        "reason": "rate_limited",
                        "command": command,
                        "limit_rpm": _remote_command_rpm(),
                    },
                )
            raise

        if not _is_allowed_remote_command(command):
            _audit_remote_event(
                "remote.command",
                False,
                request,
                {
                    "reason": "not_in_allowlist",
                    "command": command,
                    "allowed_prefixes": _remote_command_allowlist(),
                },
            )
            raise HTTPException(
                status_code=403,
                detail="Command is not allowed by remote command policy (allowlist).",
            )

        if not _dangerous_remote_enabled():
            lowered = command.lower()
            blocked_prefixes = (
                "shutdown",
                "restart",
                "format ",
                "delete ",
                "remove ",
                "wipe ",
                "power off",
            )
            if any(lowered.startswith(prefix) for prefix in blocked_prefixes):
                _audit_remote_event(
                    "remote.command",
                    False,
                    request,
                    {
                        "reason": "dangerous_blocked",
                        "command": command,
                    },
                )
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Dangerous remote commands are blocked. "
                        "Set LADA_REMOTE_ALLOW_DANGEROUS=true only if you fully trust this deployment."
                    ),
                )

        state.load_components()
        if not state.jarvis and not state.ai_router:
            _audit_remote_event("remote.command", False, request, {"reason": "no_processor", "command": command})
            raise HTTPException(status_code=503, detail="No command processor available")

        loop = asyncio.get_event_loop()

        def _execute() -> Dict[str, str]:
            if state.jarvis:
                handled, response = state.jarvis.process(command)
                if handled:
                    return {
                        "engine": "jarvis",
                        "handled": "true",
                        "response": response or "Command executed.",
                    }
            if state.ai_router:
                ai_response = state.ai_router.query(command)
                return {
                    "engine": "ai_router",
                    "handled": "false",
                    "response": ai_response or "No response.",
                }
            raise RuntimeError("No processor available")

        try:
            result = await loop.run_in_executor(None, _execute)
            _audit_remote_event(
                "remote.command",
                True,
                request,
                {
                    "command": command,
                    "engine": result.get("engine", "unknown"),
                    "handled": result.get("handled", "false") == "true",
                },
            )
            response_payload = {
                "success": True,
                "command": command,
                "engine": result.get("engine", "unknown"),
                "handled": result.get("handled", "false") == "true",
                "response": result.get("response", ""),
                "timestamp": datetime.now().isoformat(),
                "request_id": request_id,
            }
            if idempotency_key:
                response_payload["idempotency"] = {
                    "key": idempotency_key,
                    "replayed": False,
                }
                if idempotency_cache_key:
                    remote_idempotency_cache[idempotency_cache_key] = {
                        "created_at": time.time(),
                        "command": command,
                        "response": dict(response_payload),
                    }

            return response_payload
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[Remote] Command failed: {e}")
            _audit_remote_event(
                "remote.command",
                False,
                request,
                {
                    "reason": "execution_failed",
                    "command": command,
                    "error": str(e),
                },
            )
            raise HTTPException(status_code=500, detail="Remote command execution failed")

    @r.get("/remote/files")
    async def remote_list_files(
        request: Request,
        path: str = Query(...),
        show_hidden: bool = Query(False),
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=200),
    ):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "files")
        if not _remote_download_enabled():
            _audit_remote_event("remote.files", False, request, {"reason": "remote_download_disabled", "path": path})
            raise HTTPException(
                status_code=403,
                detail="Remote file access is disabled. Set LADA_REMOTE_DOWNLOAD_ENABLED=true to enable it.",
            )

        try:
            _check_remote_rate_limit(request, "files", _remote_files_rpm())
        except HTTPException as exc:
            if exc.status_code == 429:
                _audit_remote_event(
                    "remote.files",
                    False,
                    request,
                    {
                        "reason": "rate_limited",
                        "path": path,
                        "limit_rpm": _remote_files_rpm(),
                    },
                )
            raise

        folder = _validate_remote_path(path, directory=True)
        roots = _allowed_remote_roots()

        entries = []
        try:
            children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            raise HTTPException(status_code=500, detail="Could not list directory")

        for child in children:
            if not show_hidden and child.name.startswith('.'):
                continue

            # Skip symlink entries that resolve outside of allowed roots.
            effective = child
            if child.is_symlink():
                try:
                    effective = child.resolve(strict=True)
                except Exception:
                    continue
                if not any(_is_within(effective, root) for root in roots):
                    continue

            try:
                st = effective.stat()
            except Exception:
                continue

            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": effective.is_dir(),
                "is_symlink": child.is_symlink(),
                "size": None if effective.is_dir() else st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            })

        total_entries = len(entries)
        total_pages = max(1, (total_entries + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        start_index = (current_page - 1) * page_size
        end_index = start_index + page_size
        page_entries = entries[start_index:end_index]

        has_next = end_index < total_entries
        has_prev = current_page > 1
        truncated = has_next

        parent = folder.parent
        parent_allowed = any(_is_within(parent, root) for root in roots)
        breadcrumbs = _build_remote_breadcrumbs(folder, roots)

        response_payload = {
            "success": True,
            "request_id": request_id,
            "path": str(folder),
            "parent": str(parent) if parent_allowed and parent != folder else None,
            "entries": page_entries,
            "truncated": truncated,
            "breadcrumbs": breadcrumbs,
            "pagination": {
                "page": current_page,
                "page_size": page_size,
                "total_entries": total_entries,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
            },
        }
        _audit_remote_event(
            "remote.files",
            True,
            request,
            {
                "path": str(folder),
                "entry_count": len(response_payload["entries"]),
                "truncated": truncated,
                "page": current_page,
                "page_size": page_size,
                "total_entries": total_entries,
            },
        )
        return response_payload

    @r.get("/remote/download")
    async def remote_download(request: Request, path: str = Query(...)):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "download")
        if not _remote_download_enabled():
            _audit_remote_event("remote.download", False, request, {"reason": "remote_download_disabled", "path": path})
            raise HTTPException(
                status_code=403,
                detail="Remote file access is disabled. Set LADA_REMOTE_DOWNLOAD_ENABLED=true to enable it.",
            )

        try:
            _check_remote_rate_limit(request, "download", _remote_download_rpm())
        except HTTPException as exc:
            if exc.status_code == 429:
                _audit_remote_event(
                    "remote.download",
                    False,
                    request,
                    {
                        "reason": "rate_limited",
                        "path": path,
                        "limit_rpm": _remote_download_rpm(),
                    },
                )
            raise

        file_path = _validate_remote_path(path, file=True)

        try:
            file_size = file_path.stat().st_size
        except Exception:
            raise HTTPException(status_code=500, detail="Could not read file metadata")

        max_bytes = _max_download_bytes()
        if file_size > max_bytes:
            _audit_remote_event(
                "remote.download",
                False,
                request,
                {
                    "reason": "file_too_large",
                    "path": str(file_path),
                    "size": file_size,
                    "max": max_bytes,
                },
            )
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File exceeds max remote download size ({round(max_bytes / (1024 * 1024), 2)} MB)."
                ),
            )

        _audit_remote_event(
            "remote.download",
            True,
            request,
            {
                "path": str(file_path),
                "size": file_size,
            },
        )

        response = FileResponse(path=str(file_path), filename=file_path.name, media_type="application/octet-stream")
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    return r
