"""
LADA API — Dashboard and LADA App routes (/dashboard, /app, /sessions/*, /cost, /providers)
"""

import os
import json
import asyncio
import hashlib
import ipaddress
import re
import logging
import socket
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Body, Query, Request, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse

from modules.api.deps import REQUEST_ID_HEADER, ensure_request_id, set_request_id_header
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)


def _update_env_file(env_path: Path, updates: dict) -> None:
    """Update or add key=value entries in a .env file without disturbing other lines."""
    lines: list[str] = []
    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append any keys that weren't already in the file
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    try:
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as exc:
        logger.warning("[Env] Could not write .env file: %s", exc)


def create_app_router(state):
    """Create dashboard + LADA web app + sessions/cost/providers router."""
    async def _trace_request(request: Request, response: Response):

        set_request_id_header(request, response, prefix="http")

    r = APIRouter(tags=["app"], dependencies=[Depends(_trace_request)])
    base_dir = Path(__file__).parent.parent.parent.parent  # JarvisAI/
    dashboard_dir = base_dir / "web"
    sessions_dir = base_dir / "data" / "sessions"
    session_name_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    remote_rate_windows: Dict[str, Dict[str, float]] = {}
    remote_idempotency_cache: Dict[str, Dict[str, Any]] = {}
    remote_bridge_devices: Dict[str, Dict[str, Any]] = {}
    remote_bridge_queues: Dict[str, list[Dict[str, Any]]] = {}
    remote_bridge_results: Dict[str, Dict[str, Any]] = {}
    modern_ui_probe_cache: Dict[str, Any] = {
        "base_url": "",
        "checked_at": 0.0,
        "reachable": False,
    }

    def _bool_env(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _rollout_stage() -> str:
        stage = os.getenv("LADA_ROLLOUT_STAGE", "local").strip().lower()
        valid = {"disabled", "local", "internal", "canary", "public"}
        return stage if stage in valid else "local"

    def _web_ui_mode() -> str:
        """Select which UI /app should serve.

        Values:
          - legacy: always serve web/lada_app.html
          - modern: always redirect to modern frontend URL
          - auto: redirect only when modern frontend is reachable locally
        """
        mode = os.getenv("LADA_WEB_UI_MODE", "auto").strip().lower()
        valid = {"legacy", "auto", "modern"}
        return mode if mode in valid else "auto"

    def _provider_status_fallback() -> list[dict[str, Any]]:
        provider_keys = {
            "OpenAI": "OPENAI_API_KEY",
            "Anthropic": "ANTHROPIC_API_KEY",
            "Gemini": "GEMINI_API_KEY",
            "Groq": "GROQ_API_KEY",
            "Mistral": "MISTRAL_API_KEY",
            "xAI (Grok)": "XAI_API_KEY",
            "DeepSeek": "DEEPSEEK_API_KEY",
            "NVIDIA NIM": "NVIDIA_API_KEY",
            "Together AI": "TOGETHER_API_KEY",
            "Fireworks AI": "FIREWORKS_API_KEY",
            "Cerebras": "CEREBRAS_API_KEY",
            "Cohere": "COHERE_API_KEY",
            "Perplexity": "PERPLEXITY_API_KEY",
            "Replicate": "REPLICATE_API_TOKEN",
            "AWS Bedrock": "AWS_ACCESS_KEY_ID",
            "Azure OpenAI": "AZURE_OPENAI_API_KEY",
            "Hugging Face": "HF_API_TOKEN",
            "ElevenLabs": "ELEVENLABS_API_KEY",
            "Ollama (local)": "LOCAL_OLLAMA_URL",
            "LM Studio (local)": "LOCAL_LM_STUDIO_URL",
            "Jan (local)": "LOCAL_JAN_URL",
        }
        fallback = []
        for pname, env_key in provider_keys.items():
            fallback.append({"name": pname, "healthy": bool(os.getenv(env_key)), "models": 0, "env_key": env_key})
        return fallback

    def _modern_web_base_url() -> str:
        raw = os.getenv("LADA_MODERN_WEB_URL", "http://127.0.0.1:3000").strip()
        return raw.rstrip("/") if raw else "http://127.0.0.1:3000"

    def _modern_web_entry_path() -> str:
        path = os.getenv("LADA_MODERN_WEB_PATH", "/").strip() or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _probe_modern_web_reachable(base_url: str) -> bool:
        try:
            parsed = urlsplit(base_url)
            host = parsed.hostname
            if not host:
                return False
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            with socket.create_connection((host, port), timeout=0.45):
                return True
        except OSError:
            return False

    def _is_modern_web_reachable(base_url: str) -> bool:
        # Short cache avoids socket probe on every request.
        now = time.time()
        cache_ttl = 5.0
        if (
            modern_ui_probe_cache.get("base_url") == base_url
            and now - float(modern_ui_probe_cache.get("checked_at", 0.0)) < cache_ttl
        ):
            return bool(modern_ui_probe_cache.get("reachable", False))

        reachable = _probe_modern_web_reachable(base_url)
        modern_ui_probe_cache["base_url"] = base_url
        modern_ui_probe_cache["checked_at"] = now
        modern_ui_probe_cache["reachable"] = reachable
        return reachable

    def _build_modern_web_redirect_url(request: Request) -> str:
        base_url = _modern_web_base_url()
        base_parts = urlsplit(base_url)
        entry_path = _modern_web_entry_path()

        query_pairs = parse_qsl(base_parts.query, keep_blank_values=True)
        query_pairs.extend(parse_qsl(request.url.query, keep_blank_values=True))
        query = urlencode(query_pairs, doseq=True)

        return urlunsplit((
            base_parts.scheme or "http",
            base_parts.netloc,
            entry_path,
            query,
            "",
        ))

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

    def _remote_bridge_device_timeout_sec() -> int:
        return max(10, _int_env("LADA_REMOTE_BRIDGE_DEVICE_TIMEOUT_SEC", 60))

    def _remote_bridge_queue_max() -> int:
        return max(1, _int_env("LADA_REMOTE_BRIDGE_QUEUE_MAX", 200))

    def _remote_bridge_dispatch_timeout_sec() -> int:
        return max(1, _int_env("LADA_REMOTE_BRIDGE_DISPATCH_TIMEOUT_SEC", 30))

    def _remote_bridge_default_device_id() -> str:
        return str(os.getenv("LADA_REMOTE_BRIDGE_DEFAULT_DEVICE_ID", "") or "").strip()

    def _remote_bridge_auto_dispatch_enabled() -> bool:
        raw = os.getenv("LADA_REMOTE_BRIDGE_AUTO_DISPATCH")
        if raw is None or not str(raw).strip():
            return _rollout_stage() in {"canary", "public"}
        return _bool_env("LADA_REMOTE_BRIDGE_AUTO_DISPATCH", False)

    def _is_remote_bridge_device_online(device: Dict[str, Any], now_ts: float) -> bool:
        timeout = _remote_bridge_device_timeout_sec()
        last_seen = float(device.get("last_seen", 0.0))
        return last_seen > 0.0 and (now_ts - last_seen) <= timeout

    def _select_auto_bridge_device(now_ts: float) -> str:
        preferred = _remote_bridge_default_device_id()
        if preferred:
            preferred_device = remote_bridge_devices.get(preferred)
            if preferred_device and _is_remote_bridge_device_online(preferred_device, now_ts):
                return preferred

        online_ids = []
        for device_id in sorted(remote_bridge_devices.keys()):
            device = remote_bridge_devices.get(device_id, {})
            if _is_remote_bridge_device_online(device, now_ts):
                online_ids.append(device_id)

        return online_ids[0] if online_ids else ""

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

    def _prune_remote_bridge_state(now_ts: float) -> None:
        timeout = _remote_bridge_device_timeout_sec()
        stale_devices = []
        for device_id, device in remote_bridge_devices.items():
            if now_ts - float(device.get("last_seen", 0.0)) > (timeout * 10):
                stale_devices.append(device_id)

        for device_id in stale_devices:
            remote_bridge_devices.pop(device_id, None)
            remote_bridge_queues.pop(device_id, None)

        # Keep result cache bounded and fresh
        stale_result_keys = [
            key for key, value in remote_bridge_results.items()
            if now_ts - float(value.get("updated_at", 0.0)) > 3600
        ]
        for key in stale_result_keys:
            remote_bridge_results.pop(key, None)

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

    def _parse_bearer_token(authorization: str) -> str:
        raw = str(authorization or "").strip()
        if not raw:
            return ""

        parts = raw.split(None, 1)
        if len(parts) != 2:
            return ""

        scheme, token = parts
        if scheme.lower() != "bearer":
            return ""

        return token.strip()

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
        """Enforce rollout stage access control for remote features.

        canary/public stages allow all authenticated requests.
        local stage = loopback only.
        internal stage = loopback + private LAN.
        disabled = always blocked.
        """
        stage = _rollout_stage()
        if stage == "disabled":
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Remote {feature} is disabled by rollout stage policy "
                    f"(LADA_ROLLOUT_STAGE=disabled)."
                ),
            )

        # canary and public stages allow all authenticated clients (Render, etc.)
        if stage in {"canary", "public"}:
            return

        scope = _client_scope(_client_ip(request))

        if stage == "local" and scope != "loopback":
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Remote {feature} is restricted to local machine access "
                    f"while LADA_ROLLOUT_STAGE=local. Set LADA_ROLLOUT_STAGE=canary "
                    f"in Render env to allow remote file access."
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
        token = _parse_bearer_token(auth_header) or request.query_params.get("token", "")
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

    def _session_file(name: str) -> Path:
        token = (name or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail="Session name required")
        if token in {".", ".."} or not session_name_pattern.fullmatch(token):
            raise HTTPException(
                status_code=400,
                detail="Invalid session name. Use letters, numbers, dot, underscore, or dash.",
            )

        sessions_dir.mkdir(parents=True, exist_ok=True)
        base_path = sessions_dir.resolve()
        session_path = (base_path / f"{token}.json").resolve()
        try:
            session_path.relative_to(base_path)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session path")
        return session_path

    # ── Dashboard ────────────────────────────────────────────

    @r.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        index_file = dashboard_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding='utf-8'))
        return HTMLResponse(content="<h1>LADA Dashboard</h1><p>web/index.html not found</p>")

    @r.get("/app", response_class=HTMLResponse)
    async def serve_app(request: Request):
        mode = _web_ui_mode()
        if mode in {"auto", "modern"}:
            modern_base = _modern_web_base_url()
            modern_url = _build_modern_web_redirect_url(request)

            if mode == "modern":
                return RedirectResponse(url=modern_url, status_code=307)

            # Auto mode: only redirect for local machine requests and when frontend is reachable.
            if _client_scope(_client_ip(request)) == "loopback" and _is_modern_web_reachable(modern_base):
                return RedirectResponse(url=modern_url, status_code=307)

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
        session_path = _session_file(name)
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
        session_path = _session_file(name)
        if session_path.exists():
            try:
                data = json.loads(session_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Session data is corrupted")
            messages = data.get("messages", [])
            if not isinstance(messages, list):
                messages = []
            return {"session_name": name, "messages": messages}
        return {"session_name": name, "messages": []}

    @r.delete("/sessions/{name}")
    async def delete_session(name: str):
        session_path = _session_file(name)
        if session_path.exists():
            session_path.unlink()
            return {"deleted": True, "session_name": name}
        return {"deleted": False, "session_name": name}

    @r.post("/sessions/save")
    async def save_session(body: dict = Body(default={})):
        name = (body.get("name") or "").strip()
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="Messages must be a list")
        if any(not isinstance(item, dict) for item in messages):
            raise HTTPException(status_code=400, detail="Each message must be an object")
        session_path = _session_file(name)
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
        async def collect_status() -> list[dict[str, Any]]:
            def build_status() -> list[dict[str, Any]]:
                logger.info("[APIServer] Checking provider status")
                try:
                    state.load_components()
                except Exception as exc:
                    logger.warning("[APIServer] provider status load_components failed: %s", type(exc).__name__)
                    return []

                result: list[dict[str, Any]] = []
                pm = getattr(state.ai_router, "provider_manager", None) if state.ai_router else None
                if pm:
                    try:
                        for pid, pinfo in pm.providers.items():
                            logger.info("[APIServer] Checking provider: %s", pid)
                            # Get friendly name from provider config, fallback to pid
                            cfg = getattr(pinfo, "config", None)
                            friendly_name = getattr(cfg, "name", None) or pid
                            # Health check: local providers check connectivity, cloud check API key
                            is_local = getattr(cfg, "local", False) if cfg else False
                            api_key = getattr(cfg, "api_key", "") if cfg else ""
                            healthy = True  # already configured means key is set
                            result.append({
                                "name": friendly_name,
                                "id": pid,
                                "type": getattr(pinfo, "provider_type", str(type(pinfo).__name__)),
                                "healthy": healthy,
                                "local": is_local,
                                "models": getattr(pinfo, "model_count", 0),
                                "env_key": "" if is_local else "",
                            })
                    except Exception as exc:
                        logger.warning("[APIServer] provider manager scan failed: %s", type(exc).__name__)

                return result or _provider_status_fallback()

            try:
                return await asyncio.wait_for(asyncio.to_thread(build_status), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("[APIServer] provider status timed out after 5 seconds")
                return _provider_status_fallback()
            except Exception as exc:
                logger.warning("[APIServer] provider status failed: %s", type(exc).__name__)
                return _provider_status_fallback()

        return {"providers": await collect_status()}

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
        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        online_bridge_devices = [
            device_id
            for device_id, device in remote_bridge_devices.items()
            if _is_remote_bridge_device_online(device, now_ts)
        ]
        client_ip = _client_ip(request)
        can_toggle = (
            _rollout_stage() == "local"
            and _client_scope(client_ip) == "loopback"
        )
        return {
            "request_id": request_id,
            "enabled": _remote_control_enabled(),
            "downloads_enabled": _remote_download_enabled(),
            "dangerous_enabled": _dangerous_remote_enabled(),
            "can_toggle": can_toggle,
            "bridge_supported": True,
            "bridge_auto_dispatch": _remote_bridge_auto_dispatch_enabled(),
            "bridge_default_device_id": _remote_bridge_default_device_id(),
            "bridge_online_device_count": len(online_bridge_devices),
            "bridge_online_devices": sorted(online_bridge_devices),
            "command_policy": "allowlist" if allowlist else "blocklist",
            "allowed_command_prefixes": allowlist,
            "command_rpm": _remote_command_rpm(),
            "files_rpm": _remote_files_rpm(),
            "download_rpm": _remote_download_rpm(),
            "allowed_roots": [str(p) for p in _allowed_remote_roots()],
            "max_download_mb": round(max_bytes / (1024 * 1024), 2),
        }

    @r.post("/remote/toggle")
    async def remote_toggle(request: Request, body: dict = Body(default={})):
        """Toggle remote features on/off. Only allowed from loopback in local rollout stage."""
        request_id = ensure_request_id(request, prefix="http")
        client_ip = _client_ip(request)
        if _rollout_stage() != "local" or _client_scope(client_ip) != "loopback":
            raise HTTPException(
                status_code=403,
                detail="Remote feature toggle is only available when accessing locally (loopback, local rollout stage).",
            )

        enable = bool(body.get("enabled", False))
        new_val = "true" if enable else "false"

        # Apply in-process immediately
        os.environ["LADA_REMOTE_CONTROL_ENABLED"] = new_val
        os.environ["LADA_REMOTE_DOWNLOAD_ENABLED"] = new_val

        # Persist to .env file
        env_path = base_dir / ".env"
        _update_env_file(env_path, {
            "LADA_REMOTE_CONTROL_ENABLED": new_val,
            "LADA_REMOTE_DOWNLOAD_ENABLED": new_val,
        })

        logger.info("[Remote] Toggled remote features to %s by %s", new_val, client_ip)
        return {
            "request_id": request_id,
            "success": True,
            "enabled": enable,
            "downloads_enabled": enable,
        }

    # ── Plugin Key Manager ───────────────────────────────────

    # All integrations with their env var names and display metadata
    _PLUGIN_REGISTRY = [
        {"id": "openai",       "name": "OpenAI",          "env": "OPENAI_API_KEY",          "category": "ai",      "url": "https://platform.openai.com/api-keys"},
        {"id": "anthropic",    "name": "Anthropic",       "env": "ANTHROPIC_API_KEY",        "category": "ai",      "url": "https://console.anthropic.com/settings/keys"},
        {"id": "gemini",       "name": "Google Gemini",   "env": "GEMINI_API_KEY",           "category": "ai",      "url": "https://aistudio.google.com/app/apikey"},
        {"id": "groq",         "name": "Groq",            "env": "GROQ_API_KEY",             "category": "ai",      "url": "https://console.groq.com/keys"},
        {"id": "mistral",      "name": "Mistral AI",      "env": "MISTRAL_API_KEY",          "category": "ai",      "url": "https://console.mistral.ai/api-keys"},
        {"id": "xai",          "name": "xAI (Grok)",      "env": "XAI_API_KEY",             "category": "ai",      "url": "https://console.x.ai"},
        {"id": "deepseek",     "name": "DeepSeek",        "env": "DEEPSEEK_API_KEY",         "category": "ai",      "url": "https://platform.deepseek.com"},
        {"id": "nvidia",       "name": "NVIDIA NIM",      "env": "NVIDIA_API_KEY",           "category": "ai",      "url": "https://build.nvidia.com"},
        {"id": "together",     "name": "Together AI",     "env": "TOGETHER_API_KEY",         "category": "ai",      "url": "https://api.together.xyz/settings/api-keys"},
        {"id": "fireworks",    "name": "Fireworks AI",    "env": "FIREWORKS_API_KEY",        "category": "ai",      "url": "https://fireworks.ai/account/api-keys"},
        {"id": "cerebras",     "name": "Cerebras",        "env": "CEREBRAS_API_KEY",         "category": "ai",      "url": "https://cloud.cerebras.ai"},
        {"id": "cohere",       "name": "Cohere",          "env": "COHERE_API_KEY",           "category": "ai",      "url": "https://dashboard.cohere.com/api-keys"},
        {"id": "perplexity",   "name": "Perplexity",      "env": "PERPLEXITY_API_KEY",       "category": "ai",      "url": "https://www.perplexity.ai/settings/api"},
        {"id": "replicate",    "name": "Replicate",       "env": "REPLICATE_API_TOKEN",      "category": "ai",      "url": "https://replicate.com/account/api-tokens"},
        {"id": "aws_bedrock",  "name": "AWS Bedrock",     "env": "AWS_ACCESS_KEY_ID",        "category": "ai",      "url": "https://aws.amazon.com/bedrock"},
        {"id": "azure_openai", "name": "Azure OpenAI",   "env": "AZURE_OPENAI_API_KEY",     "category": "ai",      "url": "https://portal.azure.com"},
        {"id": "hf",           "name": "Hugging Face",    "env": "HF_API_TOKEN",             "category": "ai",      "url": "https://huggingface.co/settings/tokens"},
        {"id": "elevenlabs",   "name": "ElevenLabs",      "env": "ELEVENLABS_API_KEY",       "category": "voice",   "url": "https://elevenlabs.io/api"},
        {"id": "stripe",       "name": "Stripe",          "env": "STRIPE_SECRET_KEY",        "category": "payment", "url": "https://dashboard.stripe.com/apikeys"},
        {"id": "sendgrid",     "name": "SendGrid",        "env": "SENDGRID_API_KEY",         "category": "comms",   "url": "https://app.sendgrid.com/settings/api_keys"},
        {"id": "twilio",       "name": "Twilio",          "env": "TWILIO_AUTH_TOKEN",        "category": "comms",   "url": "https://console.twilio.com"},
        {"id": "notion",       "name": "Notion",          "env": "NOTION_API_KEY",           "category": "tools",   "url": "https://www.notion.so/my-integrations"},
        {"id": "github",       "name": "GitHub",          "env": "GITHUB_TOKEN",             "category": "dev",     "url": "https://github.com/settings/tokens"},
        {"id": "serper",       "name": "Serper (Search)", "env": "SERPER_API_KEY",           "category": "search",  "url": "https://serper.dev"},
        {"id": "tavily",       "name": "Tavily (Search)", "env": "TAVILY_API_KEY",           "category": "search",  "url": "https://tavily.com"},
        {"id": "ollama_url",   "name": "Ollama (Local)",  "env": "LOCAL_OLLAMA_URL",         "category": "local",   "url": "http://localhost:11434"},
        {"id": "lmstudio_url", "name": "LM Studio (Local)", "env": "LOCAL_LM_STUDIO_URL",   "category": "local",   "url": "http://localhost:1234"},
    ]

    def _mask_key(val: str) -> str:
        if not val:
            return ""
        if len(val) <= 8:
            return "****"
        return val[:4] + "****" + val[-4:]

    @r.get("/plugins/keys")
    async def get_plugin_keys():
        """Return all plugin key statuses (masked values)."""
        result = []
        for p in _PLUGIN_REGISTRY:
            raw = os.getenv(p["env"], "")
            result.append({
                "id": p["id"],
                "name": p["name"],
                "env": p["env"],
                "category": p["category"],
                "url": p["url"],
                "configured": bool(raw),
                "masked_value": _mask_key(raw),
            })
        return {"plugins": result}

    @r.post("/plugins/keys")
    async def set_plugin_key(body: dict = Body(default={})):
        """Set a plugin API key — writes to os.environ and .env file."""
        plugin_id = str(body.get("id", "")).strip()
        value = str(body.get("value", "")).strip()

        plugin = next((p for p in _PLUGIN_REGISTRY if p["id"] == plugin_id), None)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        env_key = plugin["env"]
        if value:
            os.environ[env_key] = value
        else:
            os.environ.pop(env_key, None)

        env_path = base_dir / ".env"
        _update_env_file(env_path, {env_key: value})

        return {
            "success": True,
            "id": plugin_id,
            "env": env_key,
            "configured": bool(value),
            "masked_value": _mask_key(value),
        }

    @r.delete("/plugins/keys/{plugin_id}")
    async def delete_plugin_key(plugin_id: str):
        """Remove a plugin API key from env and .env file."""
        plugin = next((p for p in _PLUGIN_REGISTRY if p["id"] == plugin_id), None)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        env_key = plugin["env"]
        os.environ.pop(env_key, None)

        # Remove from .env by setting empty value
        env_path = base_dir / ".env"
        _update_env_file(env_path, {env_key: ""})

        return {"success": True, "id": plugin_id, "configured": False}

    # ── Computer Control ─────────────────────────────────────

    @r.get("/computer/screenshot")
    async def computer_screenshot():
        """Take a screenshot of the current screen and return as base64 PNG."""
        try:
            import mss
            import mss.tools
            import base64
            import io
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # All monitors combined
                shot = sct.grab(monitor)
                # Convert to PNG bytes
                from PIL import Image
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode()
            return {"success": True, "image_b64": b64, "width": shot.width, "height": shot.height}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Screenshot failed: {e}")

    @r.post("/computer/action")
    async def computer_action(body: dict = Body(default={})):
        """Execute a computer control action (click, type, scroll, key, move)."""
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.05
        except ImportError:
            raise HTTPException(status_code=500, detail="pyautogui not installed. Run: pip install pyautogui")

        action = str(body.get("action", "")).strip().lower()
        result = {"success": True, "action": action}

        try:
            if action == "click":
                x, y = int(body.get("x", 0)), int(body.get("y", 0))
                button = str(body.get("button", "left"))
                pyautogui.click(x, y, button=button)
                result["coords"] = [x, y]
            elif action == "double_click":
                x, y = int(body.get("x", 0)), int(body.get("y", 0))
                pyautogui.doubleClick(x, y)
                result["coords"] = [x, y]
            elif action == "right_click":
                x, y = int(body.get("x", 0)), int(body.get("y", 0))
                pyautogui.rightClick(x, y)
                result["coords"] = [x, y]
            elif action == "move":
                x, y = int(body.get("x", 0)), int(body.get("y", 0))
                pyautogui.moveTo(x, y, duration=0.2)
                result["coords"] = [x, y]
            elif action == "type":
                text = str(body.get("text", ""))
                interval = float(body.get("interval", 0.02))
                pyautogui.typewrite(text, interval=interval)
                result["typed"] = len(text)
            elif action == "key":
                keys = body.get("keys", [])
                if isinstance(keys, str):
                    keys = [keys]
                pyautogui.hotkey(*keys)
                result["keys"] = keys
            elif action == "scroll":
                x, y = int(body.get("x", 0)), int(body.get("y", 0))
                amount = int(body.get("amount", 3))
                pyautogui.scroll(amount, x=x, y=y)
                result["coords"] = [x, y]
            elif action == "screenshot":
                # Return screenshot after action
                pass
            else:
                raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Action '{action}' failed: {e}")

        # Optionally take a screenshot after the action
        if body.get("screenshot_after", False):
            try:
                import mss, base64, io
                from PIL import Image
                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    shot = sct.grab(monitor)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG", optimize=True)
                    result["screenshot_b64"] = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass
        return result

    @r.get("/computer/windows")
    async def computer_windows():
        """Get a list of all open window titles."""
        try:
            from modules.computer_control import ComputerControl
            ctrl = ComputerControl()
            windows = ctrl.get_windows()
            return {"success": True, "windows": windows}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @r.post("/computer/focus")
    async def computer_focus(body: dict = Body(default={})):
        """Focus a window by title."""
        title = body.get("title", "")
        if not title:
            raise HTTPException(status_code=400, detail="Window title is required")
        try:
            from modules.computer_control import ComputerControl
            ctrl = ComputerControl()
            result = ctrl.focus_window(title)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=result.get("error"))
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Browser Control ──────────────────────────────────────

    @r.post("/browser/open")
    async def browser_open(body: dict = Body(default={})):
        url = body.get("url", "")
        profile = body.get("profile", "openclaw")
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        try:
            from modules.browser_control import BrowserControl
            browser = BrowserControl(profile=profile)
            res = browser.open(url)
            browser.close()
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @r.post("/browser/action")
    async def browser_action(body: dict = Body(default={})):
        action = body.get("action", "")
        profile = body.get("profile", "openclaw")
        try:
            from modules.browser_control import BrowserControl
            browser = BrowserControl(profile=profile)
            res = {"success": False, "error": "Unknown action"}
            
            if action == "click":
                selector = body.get("selector")
                if selector:
                    res = browser.click(selector)
                else:
                    x, y = int(body.get("x", 0)), int(body.get("y", 0))
                    res = browser.click_coords(x, y)
            elif action == "type":
                res = browser.type(body.get("selector", ""), body.get("text", ""))
            elif action == "press":
                res = browser.press(body.get("key", ""))
            elif action == "evaluate":
                res = browser.evaluate(body.get("js_code", ""))
                
            browser.close()
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @r.get("/browser/screenshot")
    async def browser_screenshot(profile: str = Query("openclaw")):
        try:
            from modules.browser_control import BrowserControl
            browser = BrowserControl(profile=profile)
            res = browser.screenshot()
            browser.close()
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @r.get("/browser/text")
    async def browser_text(profile: str = Query("openclaw")):
        try:
            from modules.browser_control import BrowserControl
            browser = BrowserControl(profile=profile)
            res = browser.get_page_text()
            browser.close()
            return res
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @r.post("/remote/device/register")
    async def remote_device_register(request: Request, body: dict = Body(default={})):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            raise HTTPException(status_code=403, detail="Remote control is disabled.")

        device_id = str(body.get("device_id", "")).strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")
        if len(device_id) > 128:
            raise HTTPException(status_code=400, detail="device_id is too long")

        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        remote_bridge_devices[device_id] = {
            "device_id": device_id,
            "label": str(body.get("label", "")).strip()[:128],
            "capabilities": body.get("capabilities", {}),
            "metadata": body.get("metadata", {}),
            "registered_at": remote_bridge_devices.get(device_id, {}).get("registered_at", now_ts),
            "last_seen": now_ts,
        }
        remote_bridge_queues.setdefault(device_id, [])
        return {
            "success": True,
            "request_id": request_id,
            "device_id": device_id,
            "registered": True,
        }

    @r.post("/remote/device/heartbeat")
    async def remote_device_heartbeat(request: Request, body: dict = Body(default={})):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            raise HTTPException(status_code=403, detail="Remote control is disabled.")

        device_id = str(body.get("device_id", "")).strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")

        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        device = remote_bridge_devices.get(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not registered")
        device["last_seen"] = now_ts
        return {"success": True, "request_id": request_id, "device_id": device_id}

    @r.get("/remote/devices")
    async def remote_devices(request: Request):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            raise HTTPException(status_code=403, detail="Remote control is disabled.")
        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        timeout = _remote_bridge_device_timeout_sec()

        devices = []
        for device_id, device in remote_bridge_devices.items():
            queue_len = len(remote_bridge_queues.get(device_id, []))
            last_seen = float(device.get("last_seen", 0.0))
            devices.append({
                "device_id": device_id,
                "label": device.get("label", ""),
                "online": (now_ts - last_seen) <= timeout,
                "last_seen": datetime.fromtimestamp(last_seen).isoformat() if last_seen else "",
                "queue_length": queue_len,
                "capabilities": device.get("capabilities", {}),
            })
        devices.sort(key=lambda item: item["device_id"])
        return {"success": True, "request_id": request_id, "devices": devices}

    @r.get("/remote/device/{device_id}/next-command")
    async def remote_device_next_command(device_id: str, request: Request):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            raise HTTPException(status_code=403, detail="Remote control is disabled.")

        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        device = remote_bridge_devices.get(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not registered")
        device["last_seen"] = now_ts

        dispatch_timeout = _remote_bridge_dispatch_timeout_sec()
        in_flight = [
            item
            for item in remote_bridge_results.values()
            if item.get("device_id") == device_id and item.get("status") == "dispatched"
        ]
        if in_flight:
            in_flight.sort(key=lambda item: float(item.get("dispatched_at", 0.0)))
            pending = in_flight[0]
            dispatched_at = float(pending.get("dispatched_at", 0.0))

            if dispatched_at and (now_ts - dispatched_at) < dispatch_timeout:
                return {"success": True, "request_id": request_id, "has_command": False}

            pending["dispatched_at"] = now_ts
            pending["updated_at"] = now_ts
            pending["redelivery_count"] = int(pending.get("redelivery_count", 0)) + 1
            return {
                "success": True,
                "request_id": request_id,
                "has_command": True,
                "command": {
                    "command_id": pending["command_id"],
                    "command": pending["command"],
                    "created_at": pending["created_at"],
                    "metadata": pending.get("metadata", {}),
                },
            }

        queue = remote_bridge_queues.setdefault(device_id, [])
        if not queue:
            return {"success": True, "request_id": request_id, "has_command": False}

        item = queue.pop(0)
        item["status"] = "dispatched"
        item["dispatched_at"] = now_ts
        item["redelivery_count"] = int(item.get("redelivery_count", 0))
        remote_bridge_results[item["command_id"]] = {
            **item,
            "updated_at": now_ts,
        }
        return {
            "success": True,
            "request_id": request_id,
            "has_command": True,
            "command": {
                "command_id": item["command_id"],
                "command": item["command"],
                "created_at": item["created_at"],
                "metadata": item.get("metadata", {}),
            },
        }

    @r.post("/remote/device/{device_id}/command-result")
    async def remote_device_command_result(device_id: str, request: Request, body: dict = Body(default={})):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            raise HTTPException(status_code=403, detail="Remote control is disabled.")

        command_id = str(body.get("command_id", "")).strip()
        if not command_id:
            raise HTTPException(status_code=400, detail="command_id is required")

        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        existing = remote_bridge_results.get(command_id)
        if not existing or existing.get("device_id") != device_id:
            raise HTTPException(status_code=404, detail="Command not found for device")

        result_payload = {
            "success": bool(body.get("success", False)),
            "response": str(body.get("response", "")),
            "error": str(body.get("error", "")),
            "completed_at": datetime.now().isoformat(),
        }
        existing["status"] = "completed" if result_payload["success"] else "failed"
        existing["result"] = result_payload
        existing["updated_at"] = now_ts

        device = remote_bridge_devices.get(device_id)
        if device:
            device["last_seen"] = now_ts

        return {"success": True, "request_id": request_id, "command_id": command_id}

    @r.get("/remote/device/{device_id}/command-result/{command_id}")
    async def remote_device_get_command_result(device_id: str, command_id: str, request: Request):
        request_id = ensure_request_id(request, prefix="http")
        _enforce_rollout_remote_access(request, "command")
        if not _remote_control_enabled():
            raise HTTPException(status_code=403, detail="Remote control is disabled.")
        item = remote_bridge_results.get(command_id)
        if not item or item.get("device_id") != device_id:
            raise HTTPException(status_code=404, detail="Command result not found")

        result = item.get("result")
        return {
            "success": True,
            "request_id": request_id,
            "command_id": command_id,
            "status": item.get("status", "unknown"),
            "result": result,
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
        target_device_id = str(body.get("device_id", "")).strip()
        auto_dispatched = False
        if not command:
            _audit_remote_event("remote.command", False, request, {"reason": "missing_command"})
            raise HTTPException(status_code=400, detail="Command is required")
        if len(command) > 500:
            _audit_remote_event("remote.command", False, request, {"reason": "command_too_long"})
            raise HTTPException(status_code=400, detail="Command is too long")

        now_ts = time.time()
        _prune_remote_bridge_state(now_ts)
        if not target_device_id and _remote_bridge_auto_dispatch_enabled():
            auto_target_device_id = _select_auto_bridge_device(now_ts)
            if auto_target_device_id:
                target_device_id = auto_target_device_id
                auto_dispatched = True

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
                cached_device = str(cached_entry.get("device_id", ""))
                current_device = target_device_id or ""
                if cached_command != command or cached_device != current_device:
                    _audit_remote_event(
                        "remote.command",
                        False,
                        request,
                        {
                            "reason": "idempotency_conflict",
                            "command": command,
                            "device_id": current_device,
                            "idempotency_key": idempotency_key,
                        },
                    )
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency key reuse with a different command/device is not allowed.",
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

        if target_device_id:
            now_ts = time.time()
            _prune_remote_bridge_state(now_ts)
            if target_device_id not in remote_bridge_devices:
                raise HTTPException(status_code=404, detail="Device not registered")
            queue = remote_bridge_queues.setdefault(target_device_id, [])
            if len(queue) >= _remote_bridge_queue_max():
                raise HTTPException(status_code=429, detail="Remote device queue is full")

            command_id = f"rcmd-{uuid.uuid4().hex[:16]}"
            created_at = datetime.now().isoformat()
            queue_item = {
                "command_id": command_id,
                "device_id": target_device_id,
                "command": command,
                "created_at": created_at,
                "status": "queued",
                "metadata": body.get("metadata", {}),
            }
            queue.append(queue_item)

            response_payload = {
                "success": True,
                "queued": True,
                "command_id": command_id,
                "device_id": target_device_id,
                "queue_length": len(queue),
                "engine": "remote_bridge_queue",
                "response": f"Queued for device {target_device_id}",
                "auto_dispatched": auto_dispatched,
                "timestamp": created_at,
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
                        "device_id": target_device_id,
                        "response": dict(response_payload),
                    }

            _audit_remote_event(
                "remote.command",
                True,
                request,
                {
                    "command": command,
                    "engine": "remote_bridge_queue",
                    "handled": False,
                    "device_id": target_device_id,
                    "queued": True,
                    "auto_dispatched": auto_dispatched,
                },
            )
            return response_payload

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
                "auto_dispatched": False,
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
                        "device_id": "",
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
