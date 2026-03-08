"""
LADA v11.0 - Webhook & Event Integration System
Receive and react to external events from CI/CD, GitHub, monitoring, etc.

Features:
- HTTP webhook endpoint (FastAPI)
- Event routing to appropriate handlers
- GitHub webhook support (push, PR, issues)
- Custom webhook definitions
- Event history and replay
- Rate limiting and signature verification
"""

import os
import json
import time
import hmac
import hashlib
import logging
import threading
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Conditional imports
try:
    from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
    from fastapi.responses import JSONResponse
    import uvicorn
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False


@dataclass
class WebhookEvent:
    """A received webhook event."""
    event_id: str
    source: str  # "github", "jenkins", "custom", etc.
    event_type: str  # "push", "pull_request", "build_complete", etc.
    payload: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    processed: bool = False
    handler_result: Optional[str] = None


class WebhookManager:
    """
    Manage webhook endpoints and event processing.

    Features:
    - Register event handlers for specific sources/types
    - GitHub webhook signature verification (HMAC-SHA256)
    - Event history with search
    - Rate limiting per source
    - Background processing of events
    - Notification callbacks for real-time alerts
    """

    def __init__(self, secret_key: str = "", port: int = 8765):
        self.secret_key = secret_key or os.getenv("WEBHOOK_SECRET", "")
        self.port = port
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_history: List[WebhookEvent] = []
        self._notification_callbacks: List[Callable] = []
        self._rate_limits: Dict[str, List[float]] = defaultdict(list)
        self._app = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._max_history = 500
        self._rate_limit_per_minute = 60
        self._event_counter = 0

    def register_handler(self, source: str, event_type: str,
                         handler: Callable[[WebhookEvent], Any]):
        """
        Register a handler for a specific event source and type.

        Use "*" for source or event_type to match all.
        """
        key = f"{source}:{event_type}"
        self._handlers[key].append(handler)
        logger.info(f"[Webhook] Registered handler for {key}")

    def on_notification(self, callback: Callable[[str, Dict], None]):
        """Register a callback for real-time event notifications."""
        self._notification_callbacks.append(callback)

    def _verify_github_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not self.secret_key:
            return True  # No verification if no secret

        if not signature or not signature.startswith("sha256="):
            return False

        expected = "sha256=" + hmac.new(
            self.secret_key.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def _check_rate_limit(self, source: str) -> bool:
        """Check if source has exceeded rate limit."""
        now = time.time()
        window = self._rate_limits[source]

        # Remove entries older than 1 minute
        self._rate_limits[source] = [t for t in window if now - t < 60]

        if len(self._rate_limits[source]) >= self._rate_limit_per_minute:
            return False

        self._rate_limits[source].append(now)
        return True

    def process_event(self, event: WebhookEvent):
        """Process a webhook event by routing to registered handlers."""
        # Find matching handlers
        handlers = []
        handlers.extend(self._handlers.get(f"{event.source}:{event.event_type}", []))
        handlers.extend(self._handlers.get(f"{event.source}:*", []))
        handlers.extend(self._handlers.get(f"*:{event.event_type}", []))
        handlers.extend(self._handlers.get("*:*", []))

        results = []
        for handler in handlers:
            try:
                result = handler(event)
                results.append(str(result) if result else "ok")
            except Exception as e:
                logger.error(f"[Webhook] Handler error: {e}")
                results.append(f"error: {e}")

        event.processed = True
        event.handler_result = "; ".join(results) if results else "no handlers"

        # Notify callbacks
        for cb in self._notification_callbacks:
            try:
                cb(f"Webhook: {event.source}/{event.event_type}", {
                    "event_id": event.event_id,
                    "source": event.source,
                    "type": event.event_type,
                    "result": event.handler_result,
                })
            except Exception:
                pass

        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

    def _create_app(self) -> Optional[Any]:
        """Create FastAPI app with webhook endpoints."""
        if not FASTAPI_OK:
            logger.warning("[Webhook] FastAPI not available for webhook server")
            return None

        app = FastAPI(title="LADA Webhook Server", version="11.0")

        @app.post("/webhook/{source}")
        async def receive_webhook(source: str, request: Request,
                                  background_tasks: BackgroundTasks):
            # Rate limit check
            if not self._check_rate_limit(source):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            body = await request.body()
            headers = dict(request.headers)

            # GitHub signature verification
            if source == "github":
                sig = headers.get("x-hub-signature-256", "")
                if not self._verify_github_signature(body, sig):
                    raise HTTPException(status_code=401, detail="Invalid signature")

            # Parse payload
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {"raw": body.decode("utf-8", errors="ignore")}

            # Determine event type
            event_type = (
                headers.get("x-github-event", "") or
                payload.get("event_type", "") or
                payload.get("type", "") or
                "unknown"
            )

            self._event_counter += 1
            event = WebhookEvent(
                event_id=f"evt_{self._event_counter}_{int(time.time())}",
                source=source,
                event_type=event_type,
                payload=payload,
                headers={k: v for k, v in headers.items()
                         if k.startswith(("x-", "content-"))},
            )

            # Process in background
            background_tasks.add_task(self.process_event, event)

            return JSONResponse({
                "status": "accepted",
                "event_id": event.event_id,
            })

        @app.get("/webhook/events")
        async def list_events(limit: int = 20):
            events = self._event_history[-limit:]
            return [{
                "event_id": e.event_id,
                "source": e.source,
                "event_type": e.event_type,
                "timestamp": e.timestamp,
                "processed": e.processed,
                "result": e.handler_result,
            } for e in reversed(events)]

        @app.get("/webhook/health")
        async def health():
            return {
                "status": "running",
                "events_received": self._event_counter,
                "handlers_registered": sum(len(h) for h in self._handlers.values()),
            }

        return app

    def start_server(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """Start the webhook server in a background thread."""
        if self._running:
            return

        self._app = self._create_app()
        if not self._app:
            logger.error("[Webhook] Cannot start server (FastAPI not available)")
            return

        port = port or self.port

        def _run():
            try:
                uvicorn.run(self._app, host=host, port=port, log_level="warning")
            except Exception as e:
                logger.error(f"[Webhook] Server error: {e}")

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()
        self._running = True
        logger.info(f"[Webhook] Server started on {host}:{port}")

    def stop_server(self):
        """Stop the webhook server."""
        self._running = False
        # Note: uvicorn doesn't support graceful shutdown from outside easily
        # The daemon thread will be cleaned up on process exit

    def simulate_event(self, source: str, event_type: str,
                       payload: Dict[str, Any] = None) -> WebhookEvent:
        """Simulate a webhook event for testing."""
        self._event_counter += 1
        event = WebhookEvent(
            event_id=f"sim_{self._event_counter}",
            source=source,
            event_type=event_type,
            payload=payload or {},
        )
        self.process_event(event)
        return event

    def get_event_history(self, source: Optional[str] = None,
                          event_type: Optional[str] = None,
                          limit: int = 20) -> List[Dict[str, Any]]:
        """Get filtered event history."""
        events = self._event_history
        if source:
            events = [e for e in events if e.source == source]
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return [{
            "event_id": e.event_id,
            "source": e.source,
            "event_type": e.event_type,
            "timestamp": datetime.fromtimestamp(e.timestamp).isoformat(),
            "processed": e.processed,
            "result": e.handler_result,
        } for e in events[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "port": self.port,
            "events_received": self._event_counter,
            "events_in_history": len(self._event_history),
            "handlers_registered": sum(len(h) for h in self._handlers.values()),
            "notification_callbacks": len(self._notification_callbacks),
            "fastapi_available": FASTAPI_OK,
        }


# Default GitHub event handlers
def github_push_handler(event: WebhookEvent) -> str:
    """Handle GitHub push events."""
    payload = event.payload
    repo = payload.get("repository", {}).get("full_name", "unknown")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = len(payload.get("commits", []))
    ref = payload.get("ref", "").replace("refs/heads/", "")
    return f"Push to {repo}/{ref} by {pusher}: {commits} commit(s)"


def github_pr_handler(event: WebhookEvent) -> str:
    """Handle GitHub pull request events."""
    payload = event.payload
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    title = pr.get("title", "")
    number = pr.get("number", 0)
    repo = payload.get("repository", {}).get("full_name", "unknown")
    return f"PR #{number} {action} on {repo}: {title}"


# Singleton
_webhook_manager: Optional[WebhookManager] = None

def get_webhook_manager(secret_key: str = "", port: int = 8765) -> WebhookManager:
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager(secret_key=secret_key, port=port)
        # Register default GitHub handlers
        _webhook_manager.register_handler("github", "push", github_push_handler)
        _webhook_manager.register_handler("github", "pull_request", github_pr_handler)
    return _webhook_manager
