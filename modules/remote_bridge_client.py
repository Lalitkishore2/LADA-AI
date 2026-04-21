"""
Remote bridge client for executing Render-hosted remote commands on a local laptop.
"""

from __future__ import annotations

import os
import re
import time
import socket
import logging
from typing import Any, Dict

import requests


logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _normalize_prefix(raw: str) -> str:
    prefix = str(raw or "").strip()
    if not prefix:
        return ""
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    return prefix.rstrip("/")


class RemoteBridgeClient:
    def __init__(self) -> None:
        self.server_url = os.getenv("LADA_REMOTE_BRIDGE_SERVER_URL", "").strip().rstrip("/")
        self.password = os.getenv("LADA_REMOTE_BRIDGE_PASSWORD", "").strip()
        self.device_id = os.getenv("LADA_REMOTE_BRIDGE_DEVICE_ID", "").strip() or socket.gethostname()
        self.label = os.getenv("LADA_REMOTE_BRIDGE_LABEL", "").strip() or f"Laptop-{self.device_id}"
        legacy_poll_interval = _float_env("LADA_REMOTE_BRIDGE_POLL_INTERVAL_SEC", 8.0)
        self.idle_poll_interval = max(1.0, _float_env("LADA_REMOTE_BRIDGE_IDLE_POLL_INTERVAL_SEC", legacy_poll_interval))
        self.active_poll_interval = max(0.3, _float_env("LADA_REMOTE_BRIDGE_ACTIVE_POLL_INTERVAL_SEC", 1.0))
        if self.active_poll_interval > self.idle_poll_interval:
            self.active_poll_interval = self.idle_poll_interval
        self.active_window_sec = max(3.0, _float_env("LADA_REMOTE_BRIDGE_ACTIVE_WINDOW_SEC", 20.0))
        self.heartbeat_interval = max(5, _int_env("LADA_REMOTE_BRIDGE_HEARTBEAT_SEC", 20))
        self.reconnect_delay = max(1.0, _float_env("LADA_REMOTE_BRIDGE_RECONNECT_SEC", 3.0))
        self.login_timeout = max(3.0, _float_env("LADA_REMOTE_BRIDGE_LOGIN_TIMEOUT_SEC", 10.0))
        self.request_timeout = max(3.0, _float_env("LADA_REMOTE_BRIDGE_REQUEST_TIMEOUT_SEC", 12.0))
        self.verify_tls = _bool_env("LADA_REMOTE_BRIDGE_VERIFY_TLS", True)
        configured_prefix = _normalize_prefix(os.getenv("LADA_REMOTE_BRIDGE_API_PREFIX", ""))
        self._api_prefix_candidates: list[str] = []
        for candidate in [configured_prefix, "", "/api"]:
            normalized = _normalize_prefix(candidate)
            if normalized not in self._api_prefix_candidates:
                self._api_prefix_candidates.append(normalized)
        self._active_api_prefix: str | None = configured_prefix if configured_prefix else None

        if not self.server_url:
            raise ValueError("LADA_REMOTE_BRIDGE_SERVER_URL is required")
        if not self.password:
            raise ValueError("LADA_REMOTE_BRIDGE_PASSWORD is required")

        self._session = requests.Session()
        self._token: str = ""
        self._jarvis = None
        self._ai_router = None
        self._ai_agent = None
        self._stop_requested = False

    def _url(self, path: str, prefix: str | None = None) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        effective_prefix = _normalize_prefix(
            self._active_api_prefix if prefix is None else prefix
        )
        return f"{self.server_url}{effective_prefix}{normalized_path}"

    def _candidate_prefixes(self, preferred_prefix: str | None = None) -> list[str]:
        ordered: list[str] = []
        for candidate in (preferred_prefix, self._active_api_prefix, *self._api_prefix_candidates):
            normalized = _normalize_prefix(candidate or "")
            if normalized not in ordered:
                ordered.append(normalized)
        return ordered

    def _auth_headers(self, preferred_prefix: str | None = None) -> Dict[str, str]:
        if not self._token:
            self._login(preferred_prefix=preferred_prefix)
        return {"Authorization": f"Bearer {self._token}"}

    def _parse_json_object(self, response: requests.Response, *, context: str) -> Dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{context} returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"{context} returned an unexpected payload shape")
        return payload

    def _login(self, preferred_prefix: str | None = None) -> None:
        attempted_not_found: list[str] = []
        for prefix in self._candidate_prefixes(preferred_prefix):
            login_url = self._url("/auth/login", prefix)
            resp = self._session.post(
                login_url,
                json={"password": self.password},
                timeout=self.login_timeout,
                verify=self.verify_tls,
            )
            if resp.status_code == 404:
                attempted_not_found.append(login_url)
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"Bridge auth failed ({resp.status_code}): {resp.text[:200]}")

            payload = self._parse_json_object(resp, context="Bridge auth")
            token = str(payload.get("token", "")).strip()
            if not token:
                raise RuntimeError("Bridge auth succeeded but no token was returned")
            self._token = token
            self._active_api_prefix = prefix
            return

        if attempted_not_found:
            tried = ", ".join(attempted_not_found)
            raise RuntimeError(
                f"Bridge auth endpoint not found (404). Tried: {tried}. "
                "Set LADA_REMOTE_BRIDGE_API_PREFIX if your API is mounted under a path."
            )
        raise RuntimeError("Bridge auth failed: no reachable auth endpoint")

    def _request_json(self, method: str, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        attempted_not_found: list[str] = []
        method_upper = method.upper()
        request_fn = self._session.post if method_upper == "POST" else self._session.get

        for prefix in self._candidate_prefixes():
            headers = self._auth_headers(preferred_prefix=prefix)
            url = self._url(path, prefix)

            request_kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": self.request_timeout,
                "verify": self.verify_tls,
            }
            if method_upper == "POST":
                request_kwargs["json"] = payload or {}

            resp = request_fn(url, **request_kwargs)
            if resp.status_code == 401:
                self._token = ""
                headers = self._auth_headers(preferred_prefix=prefix)
                request_kwargs["headers"] = headers
                resp = request_fn(url, **request_kwargs)

            if resp.status_code == 404:
                attempted_not_found.append(url)
                continue

            if resp.status_code >= 400:
                raise RuntimeError(f"Bridge {method_upper} {path} failed ({resp.status_code}): {resp.text[:300]}")

            self._active_api_prefix = _normalize_prefix(prefix)
            return self._parse_json_object(resp, context=f"Bridge {method_upper} {path}")

        tried = ", ".join(attempted_not_found) if attempted_not_found else "none"
        extra_hint = ""
        if path.startswith("/remote/device/"):
            extra_hint = (
                " Server appears to be missing remote bridge device endpoints "
                "(/remote/device/*). Redeploy the latest LADA server build or set "
                "LADA_REMOTE_BRIDGE_SERVER_URL to a deployment that includes bridge routes."
            )
        raise RuntimeError(
            f"Bridge {method_upper} {path} failed (404): endpoint not found. Tried: {tried}.{extra_hint}"
        )

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_json("POST", path, payload)

    def _get(self, path: str) -> Dict[str, Any]:
        return self._request_json("GET", path)

    def register(self) -> None:
        self._post(
            "/remote/device/register",
            {
                "device_id": self.device_id,
                "label": self.label,
                "capabilities": {
                    "jarvis": True,
                    "shell": True,
                },
                "metadata": {
                    "hostname": socket.gethostname(),
                    "platform": os.name,
                },
            },
        )

    def heartbeat(self) -> None:
        self._post("/remote/device/heartbeat", {"device_id": self.device_id})

    def _ensure_processors(self) -> None:
        if self._jarvis is None:
            from lada_jarvis_core import JarvisCommandProcessor

            self._jarvis = JarvisCommandProcessor()
        if self._ai_router is None:
            from lada_ai_router import HybridAIRouter

            self._ai_router = HybridAIRouter()

    def _ensure_ai_agent(self):
        if self._ai_agent is not None:
            return self._ai_agent

        if not _bool_env("LADA_REMOTE_BRIDGE_AI_AGENT_ENABLED", True):
            return None

        self._ensure_processors()
        provider_manager = getattr(self._ai_router, "provider_manager", None)
        tool_registry = getattr(self._ai_router, "tool_registry", None)
        if not provider_manager or not tool_registry:
            return None

        try:
            from modules.ai_command_agent import AICommandAgent

            self._ai_agent = AICommandAgent(
                provider_manager=provider_manager,
                tool_registry=tool_registry,
                config={
                    "enabled": True,
                    "max_rounds": max(1, _int_env("LADA_REMOTE_BRIDGE_AI_AGENT_MAX_ROUNDS", 5)),
                },
            )
            logger.info("[Bridge] AI command agent enabled for bridge command execution")
        except Exception as exc:
            logger.warning("[Bridge] AI command agent unavailable: %s", exc)
            self._ai_agent = None

        return self._ai_agent

    @staticmethod
    def _format_ai_agent_response(agent_result: Any) -> str:
        response_text = str(getattr(agent_result, "response", "") or "").strip()
        if response_text:
            return response_text

        executor_used = str(getattr(agent_result, "executor_used", "") or "").strip()
        if executor_used:
            return f"Command executed via {executor_used}."
        return "Command executed."

    @staticmethod
    def _looks_action_clause(text: str) -> bool:
        clause = str(text or "").strip().lower()
        if not clause:
            return False

        starters = (
            "analyze",
            "analyse",
            "inspect",
            "scan",
            "describe",
            "show",
            "set",
            "change",
            "adjust",
            "increase",
            "decrease",
            "mute",
            "unmute",
            "open",
            "close",
            "launch",
            "start",
            "run",
            "click",
            "type",
            "scroll",
            "take",
            "capture",
            "find",
            "search",
            "control",
        )
        return clause.startswith(starters)

    def _split_compound_command(self, command: str) -> list[str]:
        text = str(command or "").strip()
        if not text:
            return []

        # Strong sequencing markers should always split.
        strong_parts = [
            part.strip()
            for part in re.split(r"\s+(?:and then|then|after that|followed by)\s+|\s*>>\s*|\s*&&\s*", text, flags=re.IGNORECASE)
            if part and part.strip()
        ]
        if len(strong_parts) >= 2:
            return strong_parts

        # Split on plain "and" only when each side looks action-oriented.
        and_parts = [part.strip() for part in re.split(r"\s+and\s+", text, flags=re.IGNORECASE) if part and part.strip()]
        if len(and_parts) >= 2:
            action_count = sum(1 for part in and_parts if self._looks_action_clause(part))
            if action_count >= 2:
                return and_parts

        return []

    def _execute_compound_steps(self, steps: list[str], ai_agent: Any) -> Dict[str, Any] | None:
        if len(steps) < 2:
            return None

        responses: list[str] = []
        for step in steps:
            handled, response = self._jarvis.process(step)
            if handled:
                text = str(response or "").strip()
                if text:
                    responses.append(text)
                continue

            if ai_agent:
                try:
                    agent_result = ai_agent.try_handle(step)
                    if getattr(agent_result, "handled", False):
                        responses.append(self._format_ai_agent_response(agent_result))
                        continue
                except Exception as exc:
                    logger.warning("[Bridge] AI command agent step execution failed: %s", exc)

            return None

        merged_response = "\n".join([r for r in responses if r]) or "Command executed."
        return {"success": True, "response": merged_response, "error": ""}

    def _execute_command(self, command: str) -> Dict[str, Any]:
        self._ensure_processors()
        ai_agent = self._ensure_ai_agent()
        steps = self._split_compound_command(command)

        # For compound requests, prefer AI-agent planning first, then deterministic step execution.
        if steps:
            if ai_agent:
                try:
                    agent_result = ai_agent.try_handle(command)
                    if getattr(agent_result, "handled", False):
                        return {
                            "success": True,
                            "response": self._format_ai_agent_response(agent_result),
                            "error": "",
                        }
                except Exception as exc:
                    logger.warning("[Bridge] AI command agent execution failed: %s", exc)

            compound_result = self._execute_compound_steps(steps, ai_agent)
            if compound_result:
                return compound_result

        handled, response = self._jarvis.process(command)
        if handled:
            return {"success": True, "response": str(response or "Command executed"), "error": ""}

        if ai_agent:
            try:
                agent_result = ai_agent.try_handle(command)
                if getattr(agent_result, "handled", False):
                    return {
                        "success": True,
                        "response": self._format_ai_agent_response(agent_result),
                        "error": "",
                    }
            except Exception as exc:
                logger.warning("[Bridge] AI command agent execution failed: %s", exc)

        fallback = self._ai_router.query(command)
        return {"success": True, "response": str(fallback or ""), "error": ""}

    def _normalize_command_result(self, result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "success": False,
                "response": "",
                "error": "Invalid command result payload",
            }

        return {
            "success": bool(result.get("success", False)),
            "response": str(result.get("response", "")),
            "error": str(result.get("error", ""))[:500],
        }

    def poll_once(self) -> bool:
        payload = self._get(f"/remote/device/{self.device_id}/next-command")
        has_command = bool(payload.get("has_command", False))
        if not has_command:
            return False

        command_payload = payload.get("command") or {}
        command_id = str(command_payload.get("command_id", "")).strip()
        command_text = str(command_payload.get("command", "")).strip()
        if not command_id or not command_text:
            raise RuntimeError("Bridge received invalid command payload")

        try:
            result = self._execute_command(command_text)
        except Exception as exc:
            logger.exception("[Bridge] Command execution failed for %s: %s", command_id, exc)
            result = {
                "success": False,
                "response": "",
                "error": str(exc),
            }

        normalized_result = self._normalize_command_result(result)
        self._post(
            f"/remote/device/{self.device_id}/command-result",
            {
                "command_id": command_id,
                "success": bool(normalized_result.get("success", False)),
                "response": str(normalized_result.get("response", "")),
                "error": str(normalized_result.get("error", "")),
            },
        )
        return True

    def run_forever(self) -> None:
        logger.info("[Bridge] Connecting to %s as device '%s'", self.server_url, self.device_id)
        is_registered = False
        next_heartbeat = 0.0
        last_command_at = 0.0
        while not self._stop_requested:
            try:
                if not is_registered:
                    self.register()
                    logger.info("[Bridge] Registered device '%s' (%s)", self.device_id, self.label)
                    is_registered = True
                    next_heartbeat = time.time() + self.heartbeat_interval
                    last_command_at = 0.0

                now = time.time()
                if now >= next_heartbeat:
                    self.heartbeat()
                    next_heartbeat = now + self.heartbeat_interval

                processed = self.poll_once()
                if processed:
                    last_command_at = now
                    continue

                recently_active = last_command_at > 0 and (now - last_command_at) <= self.active_window_sec
                self._sleep_with_stop(self.active_poll_interval if recently_active else self.idle_poll_interval)
            except requests.RequestException as exc:
                logger.warning("[Bridge] Network issue: %s", exc)
                self._token = ""
                is_registered = False
                self._sleep_with_stop(self.reconnect_delay)
            except RuntimeError as exc:
                message = str(exc)
                if "Bridge auth failed" in message or "auth endpoint not found" in message:
                    raise
                if "(404)" in message and "/remote/" in message:
                    raise
                logger.warning("[Bridge] Runtime issue: %s", message)
                self._token = ""
                is_registered = False
                self._sleep_with_stop(self.reconnect_delay)

    def stop(self) -> None:
        self._stop_requested = True
        try:
            self._session.close()
        except Exception:
            pass

    def _sleep_with_stop(self, duration: float) -> None:
        deadline = time.time() + max(0.0, duration)
        while not self._stop_requested and time.time() < deadline:
            remaining = deadline - time.time()
            time.sleep(min(0.25, max(0.0, remaining)))


def run_remote_bridge_client() -> int:
    try:
        client = RemoteBridgeClient()
    except ValueError as exc:
        print(f"[Bridge] Configuration error: {exc}")
        return 1

    print("=" * 50)
    print("   LADA Remote Bridge Client")
    print("=" * 50)
    print(f"Server:  {client.server_url}")
    print(f"Device:  {client.device_id}")
    print(f"Label:   {client.label}")
    print(f"Polling: idle={client.idle_poll_interval}s, active={client.active_poll_interval}s")
    print(f"Heartbeat: every {client.heartbeat_interval}s")
    print("Status:  Running (Ctrl+C to stop)")
    print("=" * 50)
    try:
        client.run_forever()
    except KeyboardInterrupt:
        print("\n[Bridge] Stopped.")
        return 0
    except requests.RequestException as exc:
        print(f"\n[Bridge] Network error: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"\n[Bridge] Runtime error: {exc}")
        return 1

    return 0
