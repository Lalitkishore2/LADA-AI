"""
LADA Model Failover System (OpenClaw-inspired)
===============================================
Enhances the existing HybridAIRouter with intelligent failover, auth profile
rotation, cooldown tracking, and auto-recovery.

Features:
- Ordered fallback chain across multiple model providers
- Auth profile rotation: try multiple API keys per provider before switching
- Per-model/profile cooldown tracking persisted to config/auth-profiles.json
- Failure classification: auth failures, rate limits, timeouts
- Usage statistics per provider (last used, cooldown_until, request count)
- Configurable billingBackoffHours for failed profiles
- Health check mechanism for each model endpoint
- Auto-recovery: background thread periodically re-checks cooled-down models

Usage:
    from modules.model_failover import ModelFailoverChain

    chain = ModelFailoverChain()
    result = chain.query("What is the capital of France?")
    if result.success:
        print(result.response)
    else:
        print(f"All models failed: {result.error}")
"""

import os
import json
import time
import logging
import threading
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_AUTH_PROFILES_FILE = "auth-profiles.json"
_DEFAULT_BILLING_BACKOFF_HOURS = 1.0
_DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 60
_DEFAULT_TIMEOUT_BACKOFF_SECONDS = 120
_HEALTH_CHECK_INTERVAL_SECONDS = 300  # 5 minutes
_AUTO_RECOVERY_INTERVAL_SECONDS = 180  # 3 minutes


class FailureType(Enum):
    """Classification of failures that trigger failover behaviour."""
    AUTH_FAILURE = "auth_failure"          # 401, 403, invalid key
    RATE_LIMIT = "rate_limit"             # 429, quota exceeded
    TIMEOUT = "timeout"                   # Request timed out
    SERVER_ERROR = "server_error"         # 500, 502, 503, 504
    CONNECTION_ERROR = "connection_error"  # DNS, refused, reset
    INVALID_RESPONSE = "invalid_response"  # Malformed / empty body
    UNKNOWN = "unknown"


class Provider(Enum):
    """Built-in provider identifiers."""
    OLLAMA = "ollama"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENAI = "openai"



# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class UsageStats:
    """Per-profile usage counters and timestamps."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_used: Optional[str] = None          # ISO timestamp
    last_failure: Optional[str] = None       # ISO timestamp
    last_failure_type: Optional[str] = None
    last_success: Optional[str] = None       # ISO timestamp
    avg_latency_ms: float = 0.0
    _latency_samples: List[float] = field(default_factory=list, repr=False)

    def record_success(self, latency_ms: float) -> None:
        """Record a successful request."""
        now = datetime.utcnow().isoformat() + "Z"
        self.total_requests += 1
        self.successful_requests += 1
        self.last_used = now
        self.last_success = now
        self._latency_samples.append(latency_ms)
        # Rolling window of last 50 samples
        if len(self._latency_samples) > 50:
            self._latency_samples = self._latency_samples[-50:]
        self.avg_latency_ms = sum(self._latency_samples) / len(self._latency_samples)

    def record_failure(self, failure_type: FailureType) -> None:
        """Record a failed request."""
        now = datetime.utcnow().isoformat() + "Z"
        self.total_requests += 1
        self.failed_requests += 1
        self.last_used = now
        self.last_failure = now
        self.last_failure_type = failure_type.value

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dict (excludes internal latency buffer)."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "last_used": self.last_used,
            "last_failure": self.last_failure,
            "last_failure_type": self.last_failure_type,
            "last_success": self.last_success,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageStats":
        """Reconstruct from persisted dict."""
        stats = cls()
        stats.total_requests = data.get("total_requests", 0)
        stats.successful_requests = data.get("successful_requests", 0)
        stats.failed_requests = data.get("failed_requests", 0)
        stats.last_used = data.get("last_used")
        stats.last_failure = data.get("last_failure")
        stats.last_failure_type = data.get("last_failure_type")
        stats.last_success = data.get("last_success")
        stats.avg_latency_ms = data.get("avg_latency_ms", 0.0)
        return stats


@dataclass
class AuthProfile:
    """
    A single authentication profile for a provider endpoint.

    Multiple AuthProfiles can exist for the same provider (e.g. two Gemini
    API keys tied to different billing accounts).
    """
    name: str                               # Human-readable label, e.g. "gemini-personal"
    provider: str                           # Provider identifier (Provider enum value)
    api_key: str = ""                       # API key / token
    base_url: str = ""                      # Endpoint base URL
    model: str = ""                         # Model name to use
    is_healthy: bool = True                 # Current health state
    cooldown_until: Optional[str] = None    # ISO timestamp; None = not cooled down
    usage_stats: UsageStats = field(default_factory=UsageStats)
    extra: Dict[str, Any] = field(default_factory=dict)  # Provider-specific options

    # ---- helpers ----------------------------------------------------------

    def is_on_cooldown(self) -> bool:
        """Return True if this profile is currently cooling down."""
        if self.cooldown_until is None:
            return False
        try:
            until = datetime.fromisoformat(self.cooldown_until.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=until.tzinfo)
            return now < until
        except (ValueError, TypeError):
            return False

    def set_cooldown(self, seconds: float) -> None:
        """Put this profile on cooldown for *seconds* seconds."""
        until = datetime.utcnow() + timedelta(seconds=seconds)
        self.cooldown_until = until.isoformat() + "Z"
        self.is_healthy = False

    def clear_cooldown(self) -> None:
        """Remove cooldown and mark healthy."""
        self.cooldown_until = None
        self.is_healthy = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
            "is_healthy": self.is_healthy,
            "cooldown_until": self.cooldown_until,
            "usage_stats": self.usage_stats.to_dict(),
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthProfile":
        stats_data = data.get("usage_stats", {})
        return cls(
            name=data.get("name", ""),
            provider=data.get("provider", ""),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            is_healthy=data.get("is_healthy", True),
            cooldown_until=data.get("cooldown_until"),
            usage_stats=UsageStats.from_dict(stats_data) if stats_data else UsageStats(),
            extra=data.get("extra", {}),
        )


@dataclass
class FailoverResult:
    """Outcome of a failover-aware query."""
    model_used: str                         # Model identifier that produced the response
    profile_used: str                       # AuthProfile.name that was used
    success: bool                           # Whether a response was obtained
    response: Optional[str] = None          # The actual text response
    error: Optional[str] = None             # Error message if success is False
    failure_type: Optional[FailureType] = None
    latency_ms: float = 0.0                 # End-to-end latency in milliseconds
    attempts: int = 0                       # Total attempts across all models/profiles


# ---------------------------------------------------------------------------
# Model entry (a model with its ordered list of auth profiles)
# ---------------------------------------------------------------------------

@dataclass
class _ModelEntry:
    """Internal: a named model slot in the failover chain."""
    name: str
    provider: str
    profiles: List[AuthProfile] = field(default_factory=list)
    _profile_index: int = field(default=0, repr=False)


# ---------------------------------------------------------------------------
# Provider query dispatchers
# ---------------------------------------------------------------------------

def _classify_error(exc: Exception, status_code: Optional[int] = None) -> FailureType:
    """Determine the FailureType from an exception and/or HTTP status code."""
    if isinstance(exc, requests.exceptions.Timeout):
        return FailureType.TIMEOUT
    if isinstance(exc, (requests.exceptions.ConnectionError, OSError)):
        return FailureType.CONNECTION_ERROR

    if status_code is not None:
        if status_code in (401, 403):
            return FailureType.AUTH_FAILURE
        if status_code == 429:
            return FailureType.RATE_LIMIT
        if status_code >= 500:
            return FailureType.SERVER_ERROR

    msg = str(exc).lower()
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return FailureType.AUTH_FAILURE
    if "429" in msg or "rate" in msg or "quota" in msg:
        return FailureType.RATE_LIMIT
    if "timeout" in msg or "timed out" in msg:
        return FailureType.TIMEOUT

    return FailureType.UNKNOWN


def _query_ollama(profile: AuthProfile, prompt: str, **kwargs) -> str:
    """Send a generate request to an Ollama-compatible endpoint."""
    url = (profile.base_url or "http://localhost:11434").rstrip("/")
    timeout = kwargs.get("timeout", 60)
    model = profile.model or kwargs.get("model", "mistral:7b-instruct-q4_0")
    system_prompt = kwargs.get("system_prompt", "")

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": f"{system_prompt}\n\nUser: {prompt}\nAssistant:" if system_prompt else prompt,
        "stream": False,
        "options": {
            "temperature": kwargs.get("temperature", 0.7),
            "num_predict": kwargs.get("max_tokens", 500),
        },
    }

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"

    resp = requests.post(f"{url}/api/generate", json=payload, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise requests.exceptions.HTTPError(
            f"Ollama returned {resp.status_code}: {resp.text[:300]}", response=resp
        )
    data = resp.json()
    text = data.get("response", "").strip()
    if not text:
        raise ValueError("Empty response from Ollama")
    return text


def _query_gemini(profile: AuthProfile, prompt: str, **kwargs) -> str:
    """Query Google Gemini via the REST API (no SDK dependency)."""
    api_key = profile.api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise PermissionError("Gemini API key not configured")

    model = profile.model or kwargs.get("model", "gemini-2.0-flash")
    timeout = kwargs.get("timeout", 60)
    system_prompt = kwargs.get("system_prompt", "")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    # Build contents
    parts = []
    if system_prompt:
        parts.append({"text": f"{system_prompt}\n\n{prompt}"})
    else:
        parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": kwargs.get("temperature", 0.7),
            "maxOutputTokens": kwargs.get("max_tokens", 500),
        },
    }

    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise requests.exceptions.HTTPError(
            f"Gemini returned {resp.status_code}: {resp.text[:300]}", response=resp
        )

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    parts_out = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts_out).strip()
    if not text:
        raise ValueError("Empty response from Gemini")
    return text


def _query_groq(profile: AuthProfile, prompt: str, **kwargs) -> str:
    """Query Groq Cloud (OpenAI-compatible chat completions)."""
    api_key = profile.api_key or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise PermissionError("Groq API key not configured")

    url = (profile.base_url or "https://api.groq.com/openai/v1/chat/completions").rstrip("/")
    model = profile.model or kwargs.get("model", "llama-3.1-8b-instant")
    timeout = kwargs.get("timeout", 60)
    system_prompt = kwargs.get("system_prompt", "")

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 500),
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise requests.exceptions.HTTPError(
            f"Groq returned {resp.status_code}: {resp.text[:300]}", response=resp
        )

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("Groq returned no choices")
    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise ValueError("Empty response from Groq")
    return text


def _query_openai(profile: AuthProfile, prompt: str, **kwargs) -> str:
    """Query any OpenAI-compatible chat completions endpoint."""
    api_key = profile.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise PermissionError("OpenAI API key not configured")

    url = (profile.base_url or "https://api.openai.com/v1/chat/completions").rstrip("/")
    model = profile.model or kwargs.get("model", "gpt-3.5-turbo")
    timeout = kwargs.get("timeout", 60)
    system_prompt = kwargs.get("system_prompt", "")

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 500),
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise requests.exceptions.HTTPError(
            f"OpenAI returned {resp.status_code}: {resp.text[:300]}", response=resp
        )

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("OpenAI returned no choices")
    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise ValueError("Empty response from OpenAI")
    return text



# Map provider names to their dispatcher functions
_PROVIDER_DISPATCHERS: Dict[str, Callable[..., str]] = {
    Provider.OLLAMA.value: _query_ollama,
    Provider.GEMINI.value: _query_gemini,
    Provider.GROQ.value: _query_groq,
    Provider.OPENAI.value: _query_openai,
}


# ---------------------------------------------------------------------------
# Health check helpers (per provider)
# ---------------------------------------------------------------------------

def _health_check_ollama(profile: AuthProfile, timeout: float = 3.0) -> bool:
    url = (profile.base_url or "http://localhost:11434").rstrip("/")
    headers: Dict[str, str] = {}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"
    try:
        resp = requests.get(f"{url}/api/tags", headers=headers, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _health_check_gemini(profile: AuthProfile, timeout: float = 5.0) -> bool:
    api_key = profile.api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False
    model = profile.model or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}?key={api_key}"
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _health_check_groq(profile: AuthProfile, timeout: float = 5.0) -> bool:
    api_key = profile.api_key or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return False
    url = "https://api.groq.com/openai/v1/models"
    try:
        resp = requests.get(
            url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )
        return resp.status_code == 200
    except Exception:
        return False


def _health_check_openai(profile: AuthProfile, timeout: float = 5.0) -> bool:
    api_key = profile.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return False
    base = (profile.base_url or "https://api.openai.com/v1/chat/completions").rstrip("/")
    # Derive models URL from base
    if "/chat/completions" in base:
        models_url = base.replace("/chat/completions", "/models")
    else:
        models_url = base.rstrip("/") + "/models"
    try:
        resp = requests.get(
            models_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )
        return resp.status_code == 200
    except Exception:
        return False




_HEALTH_CHECKERS: Dict[str, Callable[..., bool]] = {
    Provider.OLLAMA.value: _health_check_ollama,
    Provider.GEMINI.value: _health_check_gemini,
    Provider.GROQ.value: _health_check_groq,
    Provider.OPENAI.value: _health_check_openai,
}


# ---------------------------------------------------------------------------
# ModelFailoverChain
# ---------------------------------------------------------------------------

class ModelFailoverChain:
    """
    Orchestrates model failover with auth profile rotation, cooldown tracking,
    health checks, and auto-recovery.

    Example::

        chain = ModelFailoverChain()

        # Add models with multiple auth profiles
        chain.add_model("gemini-flash", "gemini", profiles=[
            AuthProfile(name="gemini-key-1", provider="gemini",
                        api_key="AIza...", model="gemini-2.0-flash"),
            AuthProfile(name="gemini-key-2", provider="gemini",
                        api_key="AIza...", model="gemini-2.0-flash"),
        ])
        chain.add_model("groq-llama", "groq", profiles=[
            AuthProfile(name="groq-main", provider="groq",
                        api_key="gsk_...", model="llama-3.1-8b-instant"),
        ])

        result = chain.query("Explain quantum computing")
    """

    def __init__(
        self,
        config_dir: Optional[str] = None,
        billing_backoff_hours: float = _DEFAULT_BILLING_BACKOFF_HOURS,
        rate_limit_backoff_seconds: float = _DEFAULT_RATE_LIMIT_BACKOFF_SECONDS,
        timeout_backoff_seconds: float = _DEFAULT_TIMEOUT_BACKOFF_SECONDS,
        auto_recovery: bool = True,
        auto_recovery_interval: float = _AUTO_RECOVERY_INTERVAL_SECONDS,
        auto_load_env: bool = True,
    ):
        """
        Initialise the failover chain.

        Args:
            config_dir: Directory for auth-profiles.json persistence.
            billing_backoff_hours: Hours to cool down a profile after an auth/billing failure.
            rate_limit_backoff_seconds: Seconds to cool down after a rate-limit hit.
            timeout_backoff_seconds: Seconds to cool down after a timeout.
            auto_recovery: Whether to start the background auto-recovery thread.
            auto_recovery_interval: Seconds between auto-recovery sweeps.
            auto_load_env: If True, auto-configure default models from environment variables.
        """
        self._config_dir = Path(config_dir) if config_dir else _DEFAULT_CONFIG_DIR
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._profiles_path = self._config_dir / _AUTH_PROFILES_FILE

        self.billing_backoff_hours = billing_backoff_hours
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self.timeout_backoff_seconds = timeout_backoff_seconds

        # Ordered list of model entries (the failover chain)
        self._chain: List[_ModelEntry] = []
        self._chain_lock = threading.Lock()

        # Persistence lock
        self._persist_lock = threading.Lock()

        # Auto-recovery
        self._stop_recovery = threading.Event()
        self._recovery_thread: Optional[threading.Thread] = None

        # Load persisted profiles (cooldowns, stats) if they exist
        self._load_profiles()

        # Optionally bootstrap from environment variables
        if auto_load_env:
            self._bootstrap_from_env()

        # Start auto-recovery thread
        if auto_recovery:
            self._start_auto_recovery(auto_recovery_interval)

        logger.info(
            "[Failover] ModelFailoverChain initialised "
            f"({len(self._chain)} models, backoff={self.billing_backoff_hours}h)"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, prompt: str, **kwargs) -> FailoverResult:
        """
        Send *prompt* through the failover chain.  Tries each model in order,
        rotating auth profiles within a model before moving to the next model.

        Keyword arguments are forwarded to the provider dispatcher (e.g.
        ``temperature``, ``max_tokens``, ``system_prompt``, ``timeout``).

        Returns:
            A FailoverResult describing the outcome.
        """
        if not prompt or not prompt.strip():
            return FailoverResult(
                model_used="", profile_used="", success=False,
                error="Empty prompt provided", attempts=0,
            )

        attempts = 0

        with self._chain_lock:
            chain_snapshot = list(self._chain)

        for entry in chain_snapshot:
            # Try each profile for this model (rotation)
            profiles_to_try = self._get_rotated_profiles(entry)

            for profile in profiles_to_try:
                # Skip profiles on cooldown
                if not self._check_cooldown(entry.name, profile):
                    logger.debug(
                        f"[Failover] Skipping {entry.name}/{profile.name} (on cooldown)"
                    )
                    continue

                attempts += 1
                start = time.perf_counter()

                try:
                    dispatcher = _PROVIDER_DISPATCHERS.get(entry.provider)
                    if dispatcher is None:
                        logger.warning(
                            f"[Failover] No dispatcher for provider '{entry.provider}'"
                        )
                        continue

                    response_text = dispatcher(profile, prompt.strip(), **kwargs)
                    elapsed_ms = (time.perf_counter() - start) * 1000

                    # Record success
                    profile.usage_stats.record_success(elapsed_ms)
                    profile.is_healthy = True
                    profile.clear_cooldown()
                    self._persist_profiles()

                    logger.info(
                        f"[Failover] Success via {entry.name}/{profile.name} "
                        f"({elapsed_ms:.0f}ms)"
                    )
                    return FailoverResult(
                        model_used=entry.name,
                        profile_used=profile.name,
                        success=True,
                        response=response_text,
                        latency_ms=elapsed_ms,
                        attempts=attempts,
                    )

                except Exception as exc:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    status_code = None
                    if hasattr(exc, "response") and exc.response is not None:
                        status_code = getattr(exc.response, "status_code", None)
                    failure_type = _classify_error(exc, status_code)

                    self._record_failure(entry.name, profile, failure_type)

                    logger.warning(
                        f"[Failover] {entry.name}/{profile.name} failed "
                        f"({failure_type.value}): {exc}"
                    )

        # All models / profiles exhausted
        logger.error("[Failover] All models and profiles exhausted")
        return FailoverResult(
            model_used="",
            profile_used="",
            success=False,
            error="All models and auth profiles exhausted",
            attempts=attempts,
        )

    def add_model(
        self,
        name: str,
        provider: str,
        profiles: Optional[List[AuthProfile]] = None,
        position: Optional[int] = None,
    ) -> None:
        """
        Add a model to the failover chain.

        Args:
            name: Unique model slot name (e.g. "gemini-flash").
            provider: Provider identifier (one of Provider enum values or custom string).
            profiles: List of AuthProfile objects for this model.
            position: Optional index in the chain (default: append at end).
        """
        with self._chain_lock:
            # Prevent duplicates
            for entry in self._chain:
                if entry.name == name:
                    logger.warning(f"[Failover] Model '{name}' already exists; updating profiles")
                    if profiles:
                        entry.profiles = profiles
                    entry.provider = provider
                    self._persist_profiles()
                    return

            entry = _ModelEntry(name=name, provider=provider, profiles=profiles or [])
            if position is not None and 0 <= position <= len(self._chain):
                self._chain.insert(position, entry)
            else:
                self._chain.append(entry)

        self._persist_profiles()
        logger.info(
            f"[Failover] Added model '{name}' (provider={provider}, "
            f"{len(entry.profiles)} profiles)"
        )

    def remove_model(self, name: str) -> bool:
        """
        Remove a model from the failover chain.

        Returns:
            True if the model was found and removed.
        """
        with self._chain_lock:
            before = len(self._chain)
            self._chain = [e for e in self._chain if e.name != name]
            removed = len(self._chain) < before

        if removed:
            self._persist_profiles()
            logger.info(f"[Failover] Removed model '{name}'")
        else:
            logger.warning(f"[Failover] Model '{name}' not found in chain")
        return removed

    def get_status(self) -> Dict[str, Any]:
        """
        Return a status overview of every model and profile in the chain.

        Returns:
            Dict with per-model status including profile health, cooldowns,
            and usage statistics.
        """
        with self._chain_lock:
            chain_snapshot = list(self._chain)

        result: Dict[str, Any] = {}
        for entry in chain_snapshot:
            profiles_status = []
            for p in entry.profiles:
                profiles_status.append({
                    "name": p.name,
                    "provider": p.provider,
                    "model": p.model,
                    "is_healthy": p.is_healthy,
                    "on_cooldown": p.is_on_cooldown(),
                    "cooldown_until": p.cooldown_until,
                    "usage_stats": p.usage_stats.to_dict(),
                })
            result[entry.name] = {
                "provider": entry.provider,
                "profile_count": len(entry.profiles),
                "healthy_profiles": sum(
                    1 for p in entry.profiles if p.is_healthy and not p.is_on_cooldown()
                ),
                "profiles": profiles_status,
            }
        return result

    def health_check_all(self) -> Dict[str, Dict[str, bool]]:
        """
        Run health checks on every profile in the chain.

        Returns:
            Dict mapping model_name -> {profile_name: healthy_bool}.
        """
        results: Dict[str, Dict[str, bool]] = {}

        with self._chain_lock:
            chain_snapshot = list(self._chain)

        for entry in chain_snapshot:
            profile_results: Dict[str, bool] = {}
            checker = _HEALTH_CHECKERS.get(entry.provider)

            for profile in entry.profiles:
                if checker is None:
                    profile_results[profile.name] = False
                    continue

                try:
                    healthy = checker(profile)
                except Exception:
                    healthy = False

                profile.is_healthy = healthy
                if healthy:
                    profile.clear_cooldown()
                profile_results[profile.name] = healthy

            results[entry.name] = profile_results

        self._persist_profiles()
        logger.info(f"[Failover] Health check complete: {results}")
        return results

    def health_check_model(self, model_name: str) -> Dict[str, bool]:
        """
        Run health checks on all profiles for a specific model.

        Returns:
            Dict mapping profile_name to healthy boolean.
        """
        with self._chain_lock:
            entry = next((e for e in self._chain if e.name == model_name), None)

        if entry is None:
            logger.warning(f"[Failover] Model '{model_name}' not found")
            return {}

        checker = _HEALTH_CHECKERS.get(entry.provider)
        results: Dict[str, bool] = {}

        for profile in entry.profiles:
            if checker is None:
                results[profile.name] = False
                continue
            try:
                healthy = checker(profile)
            except Exception:
                healthy = False

            profile.is_healthy = healthy
            if healthy:
                profile.clear_cooldown()
            results[profile.name] = healthy

        self._persist_profiles()
        return results

    def shutdown(self) -> None:
        """Stop background threads and persist state."""
        self._stop_recovery.set()
        if self._recovery_thread and self._recovery_thread.is_alive():
            self._recovery_thread.join(timeout=5)
        self._persist_profiles()
        logger.info("[Failover] Shutdown complete")

    # ------------------------------------------------------------------
    # Internal: auth rotation
    # ------------------------------------------------------------------

    def _get_rotated_profiles(self, entry: _ModelEntry) -> List[AuthProfile]:
        """
        Return profiles in rotation order starting from the current index.
        This implements round-robin across profiles for a given model.
        """
        if not entry.profiles:
            return []

        n = len(entry.profiles)
        idx = entry._profile_index % n
        rotated = entry.profiles[idx:] + entry.profiles[:idx]
        # Advance index for next call (round-robin)
        entry._profile_index = (idx + 1) % n
        return rotated

    def _rotate_auth(self, provider: str) -> Optional[AuthProfile]:
        """
        Find the next usable auth profile for *provider* across all models
        in the chain.  Used when all profiles for the current model are
        exhausted but another model with the same provider might still work.

        Returns:
            The next healthy AuthProfile for the provider, or None.
        """
        with self._chain_lock:
            for entry in self._chain:
                if entry.provider != provider:
                    continue
                for profile in entry.profiles:
                    if profile.is_healthy and not profile.is_on_cooldown():
                        return profile
        return None

    # ------------------------------------------------------------------
    # Internal: failover control
    # ------------------------------------------------------------------

    def _failover_to_next(self, current_model: str) -> Optional[_ModelEntry]:
        """
        Return the next model entry in the chain after *current_model*.

        Returns:
            The next _ModelEntry, or None if we are at the end.
        """
        with self._chain_lock:
            found = False
            for entry in self._chain:
                if found:
                    return entry
                if entry.name == current_model:
                    found = True
        return None

    def _record_failure(
        self, model_name: str, profile: AuthProfile, failure_type: FailureType
    ) -> None:
        """
        Record a failure, apply the appropriate cooldown, and persist state.
        """
        profile.usage_stats.record_failure(failure_type)

        if failure_type == FailureType.AUTH_FAILURE:
            cooldown_secs = self.billing_backoff_hours * 3600
            profile.set_cooldown(cooldown_secs)
            logger.info(
                f"[Failover] Auth failure on {model_name}/{profile.name}; "
                f"cooldown {self.billing_backoff_hours}h"
            )
        elif failure_type == FailureType.RATE_LIMIT:
            profile.set_cooldown(self.rate_limit_backoff_seconds)
            logger.info(
                f"[Failover] Rate limit on {model_name}/{profile.name}; "
                f"cooldown {self.rate_limit_backoff_seconds}s"
            )
        elif failure_type == FailureType.TIMEOUT:
            profile.set_cooldown(self.timeout_backoff_seconds)
            logger.info(
                f"[Failover] Timeout on {model_name}/{profile.name}; "
                f"cooldown {self.timeout_backoff_seconds}s"
            )
        elif failure_type in (FailureType.SERVER_ERROR, FailureType.CONNECTION_ERROR):
            profile.set_cooldown(self.timeout_backoff_seconds)
            logger.info(
                f"[Failover] {failure_type.value} on {model_name}/{profile.name}; "
                f"cooldown {self.timeout_backoff_seconds}s"
            )
        else:
            # Unknown errors get a short cooldown
            profile.set_cooldown(30)

        self._persist_profiles()

    def _check_cooldown(self, model_name: str, profile: AuthProfile) -> bool:
        """
        Check whether a profile is available (not on cooldown).

        Returns:
            True if the profile can be used (no active cooldown).
        """
        if profile.is_on_cooldown():
            return False

        # If the cooldown has expired, auto-clear it
        if profile.cooldown_until is not None and not profile.is_on_cooldown():
            profile.clear_cooldown()
            logger.info(
                f"[Failover] Cooldown expired for {model_name}/{profile.name}; "
                "marking healthy"
            )
            self._persist_profiles()

        return True

    # ------------------------------------------------------------------
    # Internal: auto-recovery
    # ------------------------------------------------------------------

    def _start_auto_recovery(self, interval: float) -> None:
        """Launch a daemon thread that periodically re-checks cooled-down profiles."""

        def _recovery_loop():
            while not self._stop_recovery.wait(timeout=interval):
                self._run_recovery_sweep()

        self._recovery_thread = threading.Thread(
            target=_recovery_loop, daemon=True, name="failover-recovery"
        )
        self._recovery_thread.start()
        logger.debug(
            f"[Failover] Auto-recovery thread started (interval={interval}s)"
        )

    def _run_recovery_sweep(self) -> None:
        """
        Check all profiles that are on cooldown.  If their cooldown has
        expired, run a quick health check and potentially restore them.
        """
        with self._chain_lock:
            chain_snapshot = list(self._chain)

        recovered = 0
        for entry in chain_snapshot:
            checker = _HEALTH_CHECKERS.get(entry.provider)
            for profile in entry.profiles:
                if not profile.is_healthy or profile.is_on_cooldown():
                    # Cooldown expired?
                    if profile.cooldown_until and not profile.is_on_cooldown():
                        # Cooldown has passed -- run a health check
                        if checker:
                            try:
                                healthy = checker(profile)
                            except Exception:
                                healthy = False
                            if healthy:
                                profile.clear_cooldown()
                                recovered += 1
                                logger.info(
                                    f"[Failover] Recovered {entry.name}/{profile.name}"
                                )
                        else:
                            # No checker available; optimistically restore
                            profile.clear_cooldown()
                            recovered += 1

        if recovered:
            self._persist_profiles()
            logger.info(f"[Failover] Recovery sweep restored {recovered} profile(s)")

    # ------------------------------------------------------------------
    # Internal: persistence
    # ------------------------------------------------------------------

    def _persist_profiles(self) -> None:
        """Save current chain state to config/auth-profiles.json."""
        with self._persist_lock:
            try:
                data = {
                    "version": 1,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "billing_backoff_hours": self.billing_backoff_hours,
                    "rate_limit_backoff_seconds": self.rate_limit_backoff_seconds,
                    "timeout_backoff_seconds": self.timeout_backoff_seconds,
                    "chain": [],
                }
                with self._chain_lock:
                    for entry in self._chain:
                        data["chain"].append({
                            "name": entry.name,
                            "provider": entry.provider,
                            "profiles": [p.to_dict() for p in entry.profiles],
                        })

                # Write atomically via temp file
                tmp_path = self._profiles_path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                tmp_path.replace(self._profiles_path)

            except Exception as exc:
                logger.error(f"[Failover] Failed to persist profiles: {exc}")

    def _load_profiles(self) -> None:
        """Load chain state from config/auth-profiles.json if it exists."""
        if not self._profiles_path.exists():
            return

        try:
            with open(self._profiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.billing_backoff_hours = data.get(
                "billing_backoff_hours", self.billing_backoff_hours
            )
            self.rate_limit_backoff_seconds = data.get(
                "rate_limit_backoff_seconds", self.rate_limit_backoff_seconds
            )
            self.timeout_backoff_seconds = data.get(
                "timeout_backoff_seconds", self.timeout_backoff_seconds
            )

            with self._chain_lock:
                self._chain = []
                for entry_data in data.get("chain", []):
                    profiles = [
                        AuthProfile.from_dict(p)
                        for p in entry_data.get("profiles", [])
                    ]
                    self._chain.append(
                        _ModelEntry(
                            name=entry_data["name"],
                            provider=entry_data["provider"],
                            profiles=profiles,
                        )
                    )

            logger.info(
                f"[Failover] Loaded {len(self._chain)} models from "
                f"{self._profiles_path}"
            )

        except Exception as exc:
            logger.error(f"[Failover] Failed to load profiles: {exc}")

    # ------------------------------------------------------------------
    # Internal: environment bootstrap
    # ------------------------------------------------------------------

    def _bootstrap_from_env(self) -> None:
        """
        Auto-configure default models from environment variables so the
        failover chain is immediately usable alongside the existing
        HybridAIRouter configuration.

        Only adds models whose API keys / URLs are actually set.
        """
        # Track which models were loaded from the persisted file so we can
        # avoid duplicating them when bootstrapping from environment vars.
        existing_names = {e.name for e in self._chain}

        # -- Local Ollama --------------------------------------------------
        ollama_url = os.environ.get("LOCAL_OLLAMA_URL", "http://localhost:11434")
        ollama_model = os.environ.get(
            "LOCAL_FAST_MODEL", "mistral:7b-instruct-q4_0"
        )
        if "ollama-local" not in existing_names:
            self._chain.append(
                _ModelEntry(
                    name="ollama-local",
                    provider=Provider.OLLAMA.value,
                    profiles=[
                        AuthProfile(
                            name="ollama-local-default",
                            provider=Provider.OLLAMA.value,
                            base_url=ollama_url,
                            model=ollama_model,
                        )
                    ],
                )
            )

        # -- Gemini --------------------------------------------------------
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if gemini_key and "gemini-flash" not in existing_names:
            self._chain.append(
                _ModelEntry(
                    name="gemini-flash",
                    provider=Provider.GEMINI.value,
                    profiles=[
                        AuthProfile(
                            name="gemini-env",
                            provider=Provider.GEMINI.value,
                            api_key=gemini_key,
                            model="gemini-2.0-flash",
                        )
                    ],
                )
            )

        # -- Groq ----------------------------------------------------------
        groq_key = os.environ.get("GROQ_API_KEY", "")
        groq_model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        if groq_key and "groq-llama" not in existing_names:
            self._chain.append(
                _ModelEntry(
                    name="groq-llama",
                    provider=Provider.GROQ.value,
                    profiles=[
                        AuthProfile(
                            name="groq-env",
                            provider=Provider.GROQ.value,
                            api_key=groq_key,
                            model=groq_model,
                        )
                    ],
                )
            )

        # -- OpenAI --------------------------------------------------------
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
        if openai_key and "openai-gpt" not in existing_names:
            self._chain.append(
                _ModelEntry(
                    name="openai-gpt",
                    provider=Provider.OPENAI.value,
                    profiles=[
                        AuthProfile(
                            name="openai-env",
                            provider=Provider.OPENAI.value,
                            api_key=openai_key,
                            model=openai_model,
                        )
                    ],
                )
            )


        # -- Ollama Cloud --------------------------------------------------
        ollama_cloud_key = os.environ.get(
            "OLLAMA_CLOUD_KEY", os.environ.get("OLLAMA_API_KEY", "")
        )
        ollama_cloud_model = os.environ.get("OLLAMA_CLOUD_MODEL", "mistral")
        if ollama_cloud_key and "ollama-cloud" not in existing_names:
            self._chain.append(
                _ModelEntry(
                    name="ollama-cloud",
                    provider=Provider.OLLAMA.value,
                    profiles=[
                        AuthProfile(
                            name="ollama-cloud-env",
                            provider=Provider.OLLAMA.value,
                            api_key=ollama_cloud_key,
                            base_url="https://ollama.com",
                            model=ollama_cloud_model,
                        )
                    ],
                )
            )

    # ------------------------------------------------------------------
    # Dunder / utility
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        with self._chain_lock:
            names = [e.name for e in self._chain]
        return f"ModelFailoverChain(models={names})"

    def __len__(self) -> int:
        with self._chain_lock:
            return len(self._chain)

    def __contains__(self, model_name: str) -> bool:
        with self._chain_lock:
            return any(e.name == model_name for e in self._chain)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_chain: Optional[ModelFailoverChain] = None
_default_chain_lock = threading.Lock()


def get_default_chain(**kwargs) -> ModelFailoverChain:
    """Return (and lazily create) a module-level default failover chain."""
    global _default_chain
    with _default_chain_lock:
        if _default_chain is None:
            _default_chain = ModelFailoverChain(**kwargs)
        return _default_chain


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 60)
    print("LADA Model Failover Chain - Self Test")
    print("=" * 60)

    chain = ModelFailoverChain(auto_recovery=False)

    print(f"\nChain: {chain}")
    print(f"Models loaded: {len(chain)}")

    print("\n--- Status ---")
    status = chain.get_status()
    for model_name, info in status.items():
        print(f"  {model_name} ({info['provider']})")
        print(f"    Profiles: {info['profile_count']} total, "
              f"{info['healthy_profiles']} healthy")
        for p in info["profiles"]:
            cd = " [COOLDOWN]" if p["on_cooldown"] else ""
            h = "OK" if p["is_healthy"] else "DOWN"
            print(f"      - {p['name']}: {h}{cd} "
                  f"(requests={p['usage_stats']['total_requests']})")

    print("\n--- Health Check ---")
    health = chain.health_check_all()
    for model_name, profiles in health.items():
        for profile_name, healthy in profiles.items():
            symbol = "[OK]" if healthy else "[X]"
            print(f"  {symbol} {model_name}/{profile_name}")

    print("\n--- Test Query ---")
    result = chain.query("Hello, what AI model are you?", max_tokens=50, timeout=15)
    if result.success:
        print(f"  Model: {result.model_used}")
        print(f"  Profile: {result.profile_used}")
        print(f"  Latency: {result.latency_ms:.0f}ms")
        print(f"  Attempts: {result.attempts}")
        print(f"  Response: {result.response[:200]}")
    else:
        print(f"  Failed: {result.error} (attempts={result.attempts})")

    chain.shutdown()
    print("\nDone.")
