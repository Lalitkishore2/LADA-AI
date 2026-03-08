"""
LADA - Heartbeat System (OpenClaw-Inspired)
Periodic proactive check-ins where the AI agent reviews pending work
and surfaces anything needing the user's attention.

Features:
- Configurable heartbeat interval (default 30 minutes)
- Active hours with timezone awareness (e.g., 9am-10pm)
- HEARTBEAT.md checklist the agent consults each cycle
- Dual response modes: HEARTBEAT_OK vs actionable alerts
- Notification callbacks for UI integration
- Background daemon thread for the heartbeat loop
- Config persistence via config/heartbeat_config.json
- Daily memory log (memory/YYYY-MM-DD.md)
- Curated MEMORY.md for long-term facts
- Semantic keyword search across memory files

Integration:
- Works alongside proactive_agent.py
- Uses HybridAIRouter for AI-powered heartbeat analysis
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional AI router import (graceful fallback)
# ---------------------------------------------------------------------------
try:
    from lada_ai_router import HybridAIRouter
    AI_ROUTER_AVAILABLE = True
except ImportError:
    HybridAIRouter = None
    AI_ROUTER_AVAILABLE = False
    logger.debug("[HeartbeatSystem] lada_ai_router not available; AI analysis disabled")


# ===========================================================================
# Constants
# ===========================================================================

HEARTBEAT_OK = "HEARTBEAT_OK"
HEARTBEAT_ALERT = "HEARTBEAT_ALERT"

DEFAULT_INTERVAL_MINUTES = 30
DEFAULT_ACTIVE_HOURS_START = 9    # 9 AM
DEFAULT_ACTIVE_HOURS_END = 22    # 10 PM
DEFAULT_TIMEZONE = "UTC"

CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "heartbeat_config.json"
HEARTBEAT_MD = Path("HEARTBEAT.md")
MEMORY_DIR = Path("memory")
MEMORY_CURATED = MEMORY_DIR / "MEMORY.md"


# ===========================================================================
# Data Classes
# ===========================================================================

class HeartbeatResponseType(Enum):
    """Classification of a heartbeat cycle result."""
    OK = "HEARTBEAT_OK"
    ALERT = "HEARTBEAT_ALERT"
    ERROR = "HEARTBEAT_ERROR"
    SKIPPED = "HEARTBEAT_SKIPPED"


@dataclass
class HeartbeatAlert:
    """A single actionable item surfaced during a heartbeat cycle."""
    category: str          # e.g. "email", "calendar", "task", "system", "weather", "custom"
    title: str
    detail: str
    severity: str = "info"  # "info", "warning", "critical"
    suggested_action: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "severity": self.severity,
            "suggested_action": self.suggested_action,
            "timestamp": self.timestamp,
        }


@dataclass
class HeartbeatResult:
    """Complete result from a single heartbeat cycle."""
    response_type: HeartbeatResponseType
    alerts: List[HeartbeatAlert] = field(default_factory=list)
    ai_summary: str = ""
    checklist_items_checked: int = 0
    cycle_number: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_type": self.response_type.value,
            "alerts": [a.to_dict() for a in self.alerts],
            "ai_summary": self.ai_summary,
            "checklist_items_checked": self.checklist_items_checked,
            "cycle_number": self.cycle_number,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
        }


# ===========================================================================
# Daily Memory Log
# ===========================================================================

class DailyMemoryLog:
    """
    Markdown-based daily memory log.

    Structure:
        memory/
            MEMORY.md          -- curated long-term facts
            2026-02-18.md      -- timestamped daily notes
            2026-02-17.md
            ...
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = Path(memory_dir) if memory_dir else MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.curated_path = self.memory_dir / "MEMORY.md"
        self._ensure_curated_file()

    # ----- file helpers ----

    def _ensure_curated_file(self):
        """Create MEMORY.md if it does not exist."""
        if not self.curated_path.exists():
            self.curated_path.write_text(
                "# LADA Long-Term Memory\n\n"
                "This file stores curated facts the assistant should always remember.\n\n"
                "## User Preferences\n\n"
                "## Important Dates\n\n"
                "## Project Notes\n\n",
                encoding="utf-8",
            )

    def _daily_path(self, date: Optional[datetime] = None) -> Path:
        """Return the path for a given date's log file."""
        d = date or datetime.now()
        filename = d.strftime("%Y-%m-%d") + ".md"
        return self.memory_dir / filename

    # ----- write -----

    def append_note(self, note: str, category: str = "heartbeat",
                    date: Optional[datetime] = None) -> Path:
        """
        Append a timestamped note to today's (or the given date's) log file.

        Returns the path of the written file.
        """
        path = self._daily_path(date)
        now = datetime.now()

        if not path.exists():
            header = f"# LADA Daily Log - {now.strftime('%A, %B %d, %Y')}\n\n"
            path.write_text(header, encoding="utf-8")

        timestamp_str = now.strftime("%H:%M:%S")
        entry = f"- **[{timestamp_str}]** `[{category}]` {note}\n"

        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)

        logger.debug(f"[DailyMemoryLog] Wrote note to {path.name}")
        return path

    def append_curated(self, section: str, fact: str):
        """
        Append a fact under a given section in the curated MEMORY.md.

        If the section heading does not exist it will be appended at the end.
        """
        content = self.curated_path.read_text(encoding="utf-8")
        heading = f"## {section}"

        if heading in content:
            # Insert right after the heading line
            idx = content.index(heading) + len(heading)
            # Find next newline after heading
            nl = content.index("\n", idx) + 1
            updated = content[:nl] + f"- {fact}\n" + content[nl:]
        else:
            updated = content.rstrip() + f"\n\n{heading}\n\n- {fact}\n"

        self.curated_path.write_text(updated, encoding="utf-8")
        logger.info(f"[DailyMemoryLog] Curated fact added under '{section}'")

    # ----- read ------

    def read_today(self) -> str:
        """Read today's log content. Returns empty string if no log exists."""
        path = self._daily_path()
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def read_yesterday(self) -> str:
        """Read yesterday's log content."""
        yesterday = datetime.now() - timedelta(days=1)
        path = self._daily_path(yesterday)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def read_recent(self, days: int = 3) -> Dict[str, str]:
        """
        Read the last N days of logs.

        Returns dict mapping date strings to their content.
        """
        results: Dict[str, str] = {}
        for offset in range(days):
            d = datetime.now() - timedelta(days=offset)
            path = self._daily_path(d)
            date_key = d.strftime("%Y-%m-%d")
            if path.exists():
                results[date_key] = path.read_text(encoding="utf-8")
        return results

    def read_curated(self) -> str:
        """Read the curated long-term MEMORY.md."""
        if self.curated_path.exists():
            return self.curated_path.read_text(encoding="utf-8")
        return ""

    # ----- search -----

    def search(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Basic semantic search across all memory files using keyword matching.

        Splits the query into keywords and scores each line by how many
        keywords it contains.  Returns the top-scoring lines with metadata.
        """
        keywords = [kw.lower().strip() for kw in query.split() if len(kw.strip()) >= 2]
        if not keywords:
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []

        for md_file in sorted(self.memory_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            for line_num, line in enumerate(content.splitlines(), start=1):
                line_lower = line.lower()
                if not line_lower.strip():
                    continue

                hits = sum(1 for kw in keywords if kw in line_lower)
                if hits == 0:
                    continue

                # Score: fraction of keywords found, with bonus for more hits
                score = hits / len(keywords)

                scored.append((score, {
                    "file": md_file.name,
                    "line_number": line_num,
                    "content": line.strip(),
                    "score": round(score, 3),
                }))

        # Sort by score descending, then by recency (filename descending)
        scored.sort(key=lambda x: (-x[0], x[1]["file"]), reverse=False)
        scored.sort(key=lambda x: x[0], reverse=True)

        return [item for _, item in scored[:max_results]]

    def list_log_files(self) -> List[str]:
        """Return sorted list of daily log filenames."""
        files = sorted(self.memory_dir.glob("????-??-??.md"), reverse=True)
        return [f.name for f in files]


# ===========================================================================
# Heartbeat System
# ===========================================================================

class HeartbeatSystem:
    """
    OpenClaw-inspired periodic heartbeat for LADA.

    Every N minutes (during active hours) the system:
    1. Reads the HEARTBEAT.md checklist
    2. Builds a prompt asking the AI to check relevant domains
    3. Sends the prompt to HybridAIRouter
    4. Classifies the response as HEARTBEAT_OK or HEARTBEAT_ALERT
    5. Fires notification callbacks for any alerts
    6. Logs the result to the daily memory log
    """

    def __init__(
        self,
        ai_router: Optional[Any] = None,
        notification_callback: Optional[Callable[[HeartbeatResult], None]] = None,
        config_path: Optional[Path] = None,
        heartbeat_md_path: Optional[Path] = None,
        memory_dir: Optional[Path] = None,
    ):
        """
        Initialize HeartbeatSystem.

        Args:
            ai_router: HybridAIRouter instance (or any object with a .query() method).
            notification_callback: Called with HeartbeatResult when alerts surface.
            config_path: Custom path for heartbeat_config.json.
            heartbeat_md_path: Custom path for HEARTBEAT.md checklist.
            memory_dir: Custom directory for daily memory logs.
        """
        # AI backend
        self.ai_router = ai_router

        # Callbacks
        self._notification_callbacks: List[Callable[[HeartbeatResult], None]] = []
        if notification_callback:
            self._notification_callbacks.append(notification_callback)

        # Paths
        self._config_path = Path(config_path) if config_path else CONFIG_FILE
        self._heartbeat_md_path = Path(heartbeat_md_path) if heartbeat_md_path else HEARTBEAT_MD
        self._memory_dir = Path(memory_dir) if memory_dir else MEMORY_DIR

        # Memory log
        self.memory_log = DailyMemoryLog(self._memory_dir)

        # Configuration (loaded from disk or defaults)
        self._config: Dict[str, Any] = self._load_config()

        # Runtime state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cycle_count = 0
        self._last_heartbeat: Optional[datetime] = None
        self._last_result: Optional[HeartbeatResult] = None
        self._history: List[Dict[str, Any]] = []
        self._max_history = 100

        logger.info("[HeartbeatSystem] Initialized (interval=%d min, active %02d:00-%02d:00 %s)",
                     self.interval_minutes,
                     self.active_hours_start,
                     self.active_hours_end,
                     self.timezone_name)

    # ==================================================================
    # Configuration Properties
    # ==================================================================

    @property
    def interval_minutes(self) -> int:
        return self._config.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)

    @property
    def active_hours_start(self) -> int:
        return self._config.get("active_hours_start", DEFAULT_ACTIVE_HOURS_START)

    @property
    def active_hours_end(self) -> int:
        return self._config.get("active_hours_end", DEFAULT_ACTIVE_HOURS_END)

    @property
    def timezone_name(self) -> str:
        return self._config.get("timezone", DEFAULT_TIMEZONE)

    @property
    def enabled(self) -> bool:
        return self._config.get("enabled", True)

    @property
    def check_domains(self) -> List[str]:
        """Domains the heartbeat prompt should inspect."""
        return self._config.get("check_domains", [
            "unread_emails",
            "upcoming_calendar_events",
            "pending_tasks",
            "system_health",
            "weather_changes",
            "heartbeat_md_items",
        ])

    # ==================================================================
    # Config Persistence
    # ==================================================================

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "interval_minutes": DEFAULT_INTERVAL_MINUTES,
            "active_hours_start": DEFAULT_ACTIVE_HOURS_START,
            "active_hours_end": DEFAULT_ACTIVE_HOURS_END,
            "timezone": DEFAULT_TIMEZONE,
            "check_domains": [
                "unread_emails",
                "upcoming_calendar_events",
                "pending_tasks",
                "system_health",
                "weather_changes",
                "heartbeat_md_items",
            ],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def _load_config(self) -> Dict[str, Any]:
        """Load config from disk, falling back to defaults."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                logger.debug("[HeartbeatSystem] Config loaded from %s", self._config_path)
                # Merge with defaults so new keys are always present
                merged = self._default_config()
                merged.update(loaded)
                return merged
            except Exception as e:
                logger.warning("[HeartbeatSystem] Failed to load config: %s", e)

        return self._default_config()

    def _save_config(self):
        """Persist current config to disk."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config["updated_at"] = datetime.now().isoformat()
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            logger.debug("[HeartbeatSystem] Config saved to %s", self._config_path)
        except Exception as e:
            logger.error("[HeartbeatSystem] Failed to save config: %s", e)

    def update_config(self, **kwargs) -> Dict[str, Any]:
        """
        Update heartbeat configuration.

        Accepted keys:
            interval_minutes, active_hours_start, active_hours_end,
            timezone, enabled, check_domains

        Returns the updated config dict.
        """
        allowed_keys = {
            "interval_minutes", "active_hours_start", "active_hours_end",
            "timezone", "enabled", "check_domains",
        }
        with self._lock:
            for key, value in kwargs.items():
                if key in allowed_keys:
                    self._config[key] = value
                else:
                    logger.warning("[HeartbeatSystem] Ignoring unknown config key: %s", key)

            self._save_config()

        logger.info("[HeartbeatSystem] Config updated: %s",
                     {k: v for k, v in kwargs.items() if k in allowed_keys})
        return dict(self._config)

    # ==================================================================
    # HEARTBEAT.md Checklist
    # ==================================================================

    def _read_heartbeat_md(self) -> List[str]:
        """
        Read HEARTBEAT.md and extract checklist items.

        Expected format (GitHub-flavored markdown checkboxes):
            - [ ] Check unread emails
            - [x] Review calendar (already done - skipped)
            - [ ] Monitor disk space

        Returns list of unchecked item strings.
        """
        if not self._heartbeat_md_path.exists():
            return []

        try:
            content = self._heartbeat_md_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("[HeartbeatSystem] Could not read HEARTBEAT.md: %s", e)
            return []

        items: List[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            # Match unchecked items: - [ ] ... or * [ ] ...
            if stripped.startswith(("- [ ]", "* [ ]")):
                item_text = stripped.split("]", 1)[1].strip()
                if item_text:
                    items.append(item_text)

        return items

    def _get_heartbeat_md_content(self) -> str:
        """Return full HEARTBEAT.md content for the AI prompt."""
        if not self._heartbeat_md_path.exists():
            return ""
        try:
            return self._heartbeat_md_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    # ==================================================================
    # Active Hours / Timezone
    # ==================================================================

    def _get_current_hour(self) -> int:
        """Get the current hour in the configured timezone."""
        try:
            # Try using zoneinfo (Python 3.9+)
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.timezone_name)
            return datetime.now(tz).hour
        except Exception:
            pass

        try:
            # Fallback: try dateutil
            from dateutil import tz as dateutil_tz
            tz = dateutil_tz.gettz(self.timezone_name)
            if tz:
                return datetime.now(tz).hour
        except ImportError:
            pass

        # Final fallback: local system time
        return datetime.now().hour

    def _is_within_active_hours(self) -> bool:
        """Check whether the current time falls within the active window."""
        current_hour = self._get_current_hour()
        start = self.active_hours_start
        end = self.active_hours_end

        if start <= end:
            # Simple range, e.g. 9-22
            return start <= current_hour < end
        else:
            # Wraps around midnight, e.g. 22-6
            return current_hour >= start or current_hour < end

    # ==================================================================
    # Heartbeat Prompt Construction
    # ==================================================================

    def _build_heartbeat_prompt(self) -> str:
        """
        Construct the prompt sent to the AI router each heartbeat cycle.

        The prompt instructs the AI to check several domains and respond
        with either HEARTBEAT_OK or a structured list of alerts.
        """
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

        # Read checklist items from HEARTBEAT.md
        checklist_items = self._read_heartbeat_md()
        heartbeat_md_section = ""
        if checklist_items:
            items_formatted = "\n".join(f"  - {item}" for item in checklist_items)
            heartbeat_md_section = (
                f"\n## HEARTBEAT.md Checklist\n"
                f"The user has defined these items to check each cycle:\n"
                f"{items_formatted}\n"
            )

        # Read today's memory for context
        today_notes = self.memory_log.read_today()
        memory_section = ""
        if today_notes:
            # Limit context to last 30 lines to avoid token bloat
            recent_lines = today_notes.strip().splitlines()[-30:]
            memory_section = (
                f"\n## Today's Activity Log (last entries)\n"
                f"{chr(10).join(recent_lines)}\n"
            )

        # Read curated memory for relevant context
        curated = self.memory_log.read_curated()
        curated_section = ""
        if curated and len(curated.strip()) > 50:
            # Only include first 2000 chars of curated memory
            curated_section = (
                f"\n## Long-Term Memory (excerpt)\n"
                f"{curated[:2000]}\n"
            )

        # Full HEARTBEAT.md content
        full_heartbeat_content = self._get_heartbeat_md_content()
        full_heartbeat_section = ""
        if full_heartbeat_content:
            full_heartbeat_section = (
                f"\n## Full HEARTBEAT.md\n"
                f"```\n{full_heartbeat_content}\n```\n"
            )

        prompt = f"""You are LADA's heartbeat system. Current time: {date_str}.
This is heartbeat cycle #{self._cycle_count + 1}.

Your job is to perform a proactive check-in. Review the following domains and
report anything that needs the user's attention.

## Domains to Check
1. **Unread Emails**: Are there any important unread emails or messages?
2. **Upcoming Calendar Events**: Any events in the next 2 hours?
3. **Pending Tasks**: Are there overdue or high-priority tasks?
4. **System Health**: CPU, memory, disk space -- anything concerning?
5. **Weather Changes**: Any significant weather alerts or changes?
6. **Custom Items**: Check the HEARTBEAT.md checklist below.
{heartbeat_md_section}{full_heartbeat_section}{memory_section}{curated_section}
## Response Format

If nothing needs attention, respond with exactly:
HEARTBEAT_OK

If there ARE items needing attention, respond with:
HEARTBEAT_ALERT
Then list each alert in this format:
- [CATEGORY] TITLE: Detail text (severity: info|warning|critical)

Categories: email, calendar, task, system, weather, custom

Example:
HEARTBEAT_ALERT
- [calendar] Meeting in 30 min: Standup meeting with team starts at 2:30 PM (severity: warning)
- [system] Disk space low: Only 5GB remaining on C: drive (severity: warning)

Be concise.  Only flag genuinely important or time-sensitive items.
Do not invent alerts -- if everything looks fine, say HEARTBEAT_OK.
"""
        return prompt

    # ==================================================================
    # Response Parsing
    # ==================================================================

    def _parse_ai_response(self, raw_response: str) -> HeartbeatResult:
        """
        Parse the AI's heartbeat response into a structured HeartbeatResult.
        """
        result = HeartbeatResult(
            response_type=HeartbeatResponseType.OK,
            cycle_number=self._cycle_count,
        )

        if not raw_response or not raw_response.strip():
            result.response_type = HeartbeatResponseType.ERROR
            result.ai_summary = "Empty response from AI"
            return result

        cleaned = raw_response.strip()
        result.ai_summary = cleaned

        # Determine response type
        if HEARTBEAT_ALERT in cleaned.upper() or "HEARTBEAT_ALERT" in cleaned:
            result.response_type = HeartbeatResponseType.ALERT
        elif HEARTBEAT_OK in cleaned.upper() or "HEARTBEAT_OK" in cleaned:
            result.response_type = HeartbeatResponseType.OK
            return result
        else:
            # Heuristic: if the response contains alert-like patterns, treat as alert
            alert_indicators = ["[email]", "[calendar]", "[task]", "[system]", "[weather]", "[custom]"]
            if any(indicator in cleaned.lower() for indicator in alert_indicators):
                result.response_type = HeartbeatResponseType.ALERT
            else:
                # Default to OK if we can't determine
                result.response_type = HeartbeatResponseType.OK
                return result

        # Parse individual alerts
        for line in cleaned.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue

            # Try to parse: - [CATEGORY] TITLE: Detail (severity: level)
            alert = self._parse_alert_line(line)
            if alert:
                result.alerts.append(alert)

        # Count checklist items checked
        result.checklist_items_checked = len(self._read_heartbeat_md())

        return result

    def _parse_alert_line(self, line: str) -> Optional[HeartbeatAlert]:
        """
        Parse a single alert line.

        Expected: - [category] Title: Detail text (severity: level)
        """
        import re

        # Remove leading dash and whitespace
        text = line.lstrip("-").strip()

        # Extract category
        cat_match = re.match(r'\[(\w+)\]\s*(.*)', text)
        if not cat_match:
            return None

        category = cat_match.group(1).lower()
        remainder = cat_match.group(2)

        # Extract severity if present
        severity = "info"
        sev_match = re.search(r'\(severity:\s*(\w+)\)', remainder)
        if sev_match:
            severity = sev_match.group(1).lower()
            remainder = remainder[:sev_match.start()].strip()

        # Split title and detail at first colon
        if ":" in remainder:
            title, detail = remainder.split(":", 1)
            title = title.strip()
            detail = detail.strip()
        else:
            title = remainder.strip()
            detail = ""

        return HeartbeatAlert(
            category=category,
            title=title,
            detail=detail,
            severity=severity,
        )

    # ==================================================================
    # Core Heartbeat Execution
    # ==================================================================

    def _execute_heartbeat(self) -> HeartbeatResult:
        """
        Execute a single heartbeat cycle:
        1. Build prompt
        2. Query AI router
        3. Parse response
        4. Log to daily memory
        5. Fire callbacks
        """
        start_time = time.monotonic()
        self._cycle_count += 1

        logger.info("[HeartbeatSystem] Starting heartbeat cycle #%d", self._cycle_count)

        # Build the prompt
        prompt = self._build_heartbeat_prompt()

        # Query AI
        ai_response = ""
        if self.ai_router and hasattr(self.ai_router, "query"):
            try:
                ai_response = self.ai_router.query(prompt)
                logger.debug("[HeartbeatSystem] AI response length: %d chars", len(ai_response))
            except Exception as e:
                logger.error("[HeartbeatSystem] AI query failed: %s", e)
                ai_response = ""
        else:
            # No AI router -- generate a synthetic HEARTBEAT_OK
            logger.debug("[HeartbeatSystem] No AI router, generating synthetic OK")
            ai_response = HEARTBEAT_OK

        # Parse the response
        result = self._parse_ai_response(ai_response)
        result.duration_seconds = round(time.monotonic() - start_time, 2)
        result.cycle_number = self._cycle_count

        # Update state
        self._last_heartbeat = datetime.now()
        self._last_result = result

        # Store in history
        self._history.append(result.to_dict())
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Log to daily memory
        if result.response_type == HeartbeatResponseType.OK:
            self.memory_log.append_note(
                f"Heartbeat #{self._cycle_count}: OK (took {result.duration_seconds}s)",
                category="heartbeat",
            )
        elif result.response_type == HeartbeatResponseType.ALERT:
            alert_summary = "; ".join(
                f"{a.category}/{a.title}" for a in result.alerts
            )
            self.memory_log.append_note(
                f"Heartbeat #{self._cycle_count}: ALERT -- {alert_summary} "
                f"(took {result.duration_seconds}s)",
                category="heartbeat",
            )
        else:
            self.memory_log.append_note(
                f"Heartbeat #{self._cycle_count}: {result.response_type.value} "
                f"({result.ai_summary[:100]})",
                category="heartbeat",
            )

        # Fire notification callbacks for alerts
        if result.response_type == HeartbeatResponseType.ALERT and result.alerts:
            self._fire_notification_callbacks(result)

        logger.info(
            "[HeartbeatSystem] Cycle #%d complete: %s (%d alerts, %.2fs)",
            self._cycle_count,
            result.response_type.value,
            len(result.alerts),
            result.duration_seconds,
        )

        return result

    # ==================================================================
    # Notification Callbacks
    # ==================================================================

    def register_callback(self, callback: Callable[[HeartbeatResult], None]):
        """Register a callback to be invoked when heartbeat produces alerts."""
        self._notification_callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[HeartbeatResult], None]):
        """Remove a previously registered callback."""
        try:
            self._notification_callbacks.remove(callback)
        except ValueError:
            pass

    def _fire_notification_callbacks(self, result: HeartbeatResult):
        """Invoke all registered notification callbacks."""
        for cb in self._notification_callbacks:
            try:
                cb(result)
            except Exception as e:
                logger.error("[HeartbeatSystem] Callback error: %s", e)

    # ==================================================================
    # Background Thread
    # ==================================================================

    def _heartbeat_loop(self):
        """
        Background loop that runs heartbeat cycles at the configured interval.

        Respects active hours -- sleeps through inactive periods.
        """
        logger.info("[HeartbeatSystem] Background loop started")

        while not self._stop_event.is_set():
            try:
                if not self.enabled:
                    # Disabled -- check every 60 seconds if re-enabled
                    self._stop_event.wait(timeout=60)
                    continue

                if not self._is_within_active_hours():
                    logger.debug(
                        "[HeartbeatSystem] Outside active hours (%02d:00-%02d:00), sleeping",
                        self.active_hours_start, self.active_hours_end,
                    )
                    # Sleep for 5 minutes and re-check
                    self._stop_event.wait(timeout=300)
                    continue

                # Execute heartbeat
                try:
                    self._execute_heartbeat()
                except Exception as e:
                    logger.error("[HeartbeatSystem] Heartbeat execution error: %s", e)

                # Sleep for the configured interval
                sleep_seconds = self.interval_minutes * 60
                self._stop_event.wait(timeout=sleep_seconds)

            except Exception as e:
                logger.error("[HeartbeatSystem] Loop error: %s", e)
                # Avoid tight error loop
                self._stop_event.wait(timeout=30)

        logger.info("[HeartbeatSystem] Background loop stopped")

    # ==================================================================
    # Public API: start / stop / trigger_now / get_status
    # ==================================================================

    def start(self) -> Dict[str, Any]:
        """
        Start the heartbeat background thread.

        Returns dict with success status.
        """
        with self._lock:
            if self._running:
                return {"success": False, "error": "Heartbeat already running"}

            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._heartbeat_loop,
                name="LADA-Heartbeat",
                daemon=True,
            )
            self._thread.start()

        self.memory_log.append_note("Heartbeat system started", category="system")
        logger.info("[HeartbeatSystem] Started")

        return {
            "success": True,
            "interval_minutes": self.interval_minutes,
            "active_hours": f"{self.active_hours_start:02d}:00-{self.active_hours_end:02d}:00",
            "timezone": self.timezone_name,
        }

    def stop(self) -> Dict[str, Any]:
        """
        Stop the heartbeat background thread.

        Returns dict with success status.
        """
        with self._lock:
            if not self._running:
                return {"success": False, "error": "Heartbeat not running"}

            self._running = False
            self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

        self.memory_log.append_note(
            f"Heartbeat system stopped after {self._cycle_count} cycles", category="system"
        )
        logger.info("[HeartbeatSystem] Stopped")

        return {"success": True, "cycles_completed": self._cycle_count}

    def trigger_now(self) -> HeartbeatResult:
        """
        Trigger an immediate heartbeat cycle regardless of schedule.

        Can be called whether or not the background thread is running.
        """
        logger.info("[HeartbeatSystem] Manual trigger requested")
        return self._execute_heartbeat()

    def get_status(self) -> Dict[str, Any]:
        """
        Get current heartbeat system status.

        Returns comprehensive status dict.
        """
        return {
            "running": self._running,
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "active_hours": f"{self.active_hours_start:02d}:00-{self.active_hours_end:02d}:00",
            "timezone": self.timezone_name,
            "within_active_hours": self._is_within_active_hours(),
            "cycle_count": self._cycle_count,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "last_result": self._last_result.response_type.value if self._last_result else None,
            "last_alert_count": len(self._last_result.alerts) if self._last_result else 0,
            "check_domains": self.check_domains,
            "heartbeat_md_exists": self._heartbeat_md_path.exists(),
            "heartbeat_md_items": len(self._read_heartbeat_md()),
            "ai_router_available": self.ai_router is not None,
            "notification_callbacks": len(self._notification_callbacks),
            "history_size": len(self._history),
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent heartbeat history."""
        return self._history[-limit:]

    # ==================================================================
    # Integration Helpers
    # ==================================================================

    def set_ai_router(self, router: Any):
        """Set or replace the AI router at runtime."""
        self.ai_router = router
        logger.info("[HeartbeatSystem] AI router updated")

    def create_default_heartbeat_md(self) -> Path:
        """
        Create a default HEARTBEAT.md if none exists.

        Returns the path to the file.
        """
        if self._heartbeat_md_path.exists():
            logger.debug("[HeartbeatSystem] HEARTBEAT.md already exists")
            return self._heartbeat_md_path

        default_content = """# LADA Heartbeat Checklist

Items checked automatically each heartbeat cycle.
Uncheck items (change [x] to [ ]) to include them in the next pass.

## Communication
- [ ] Check for unread important emails
- [ ] Review any pending Slack/Teams messages

## Schedule
- [ ] Review upcoming calendar events (next 2 hours)
- [ ] Check for schedule conflicts

## Tasks
- [ ] Review overdue tasks
- [ ] Check high-priority pending items

## System
- [ ] Monitor disk space (warn below 10GB)
- [ ] Check for pending system updates
- [ ] Monitor CPU/RAM usage

## Environment
- [ ] Check for weather alerts
- [ ] Note any significant weather changes

## Custom
- [ ] (Add your own items here)
"""
        self._heartbeat_md_path.write_text(default_content, encoding="utf-8")
        logger.info("[HeartbeatSystem] Created default HEARTBEAT.md")
        return self._heartbeat_md_path


# ===========================================================================
# Module-level Factory Functions
# ===========================================================================

_heartbeat_instance: Optional[HeartbeatSystem] = None


def get_heartbeat_system(
    ai_router: Optional[Any] = None,
    notification_callback: Optional[Callable] = None,
) -> HeartbeatSystem:
    """Get or create the singleton HeartbeatSystem instance."""
    global _heartbeat_instance
    if _heartbeat_instance is None:
        _heartbeat_instance = HeartbeatSystem(
            ai_router=ai_router,
            notification_callback=notification_callback,
        )
    return _heartbeat_instance


def create_heartbeat_system(
    ai_router: Optional[Any] = None,
    notification_callback: Optional[Callable] = None,
    **kwargs,
) -> HeartbeatSystem:
    """Create a new HeartbeatSystem instance (non-singleton)."""
    return HeartbeatSystem(
        ai_router=ai_router,
        notification_callback=notification_callback,
        **kwargs,
    )


# ===========================================================================
# CLI Test / Demo
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 65)
    print("  LADA Heartbeat System - Test Suite")
    print("=" * 65)

    # ---- Test 1: DailyMemoryLog ----
    print("\n[Test 1] DailyMemoryLog")
    test_memory_dir = Path("memory")
    ml = DailyMemoryLog(test_memory_dir)
    ml.append_note("System started for testing", category="test")
    ml.append_note("Heartbeat module loaded", category="test")
    print(f"  Log path: {ml._daily_path()}")
    print(f"  Today's log exists: {ml._daily_path().exists()}")

    today_content = ml.read_today()
    line_count = len(today_content.strip().splitlines()) if today_content else 0
    print(f"  Today's log lines: {line_count}")

    yesterday_content = ml.read_yesterday()
    print(f"  Yesterday's log exists: {bool(yesterday_content)}")

    # Search test
    results = ml.search("heartbeat system")
    print(f"  Search 'heartbeat system': {len(results)} results")

    # Curated memory
    ml.append_curated("Test Notes", "HeartbeatSystem test ran successfully")
    curated = ml.read_curated()
    print(f"  Curated memory length: {len(curated)} chars")

    # List files
    files = ml.list_log_files()
    print(f"  Log files: {files[:5]}")

    # ---- Test 2: HeartbeatSystem Config ----
    print("\n[Test 2] HeartbeatSystem Configuration")
    hb = HeartbeatSystem()
    print(f"  Interval: {hb.interval_minutes} min")
    print(f"  Active hours: {hb.active_hours_start:02d}:00-{hb.active_hours_end:02d}:00")
    print(f"  Timezone: {hb.timezone_name}")
    print(f"  Enabled: {hb.enabled}")
    print(f"  Check domains: {hb.check_domains}")
    print(f"  Within active hours: {hb._is_within_active_hours()}")

    # ---- Test 3: Config Update ----
    print("\n[Test 3] Config Update")
    new_config = hb.update_config(interval_minutes=15, active_hours_start=8)
    print(f"  Updated interval: {hb.interval_minutes} min")
    print(f"  Updated start hour: {hb.active_hours_start}")

    # Restore default
    hb.update_config(interval_minutes=30, active_hours_start=9)

    # ---- Test 4: HEARTBEAT.md ----
    print("\n[Test 4] HEARTBEAT.md")
    if not hb._heartbeat_md_path.exists():
        created_path = hb.create_default_heartbeat_md()
        print(f"  Created default: {created_path}")
    items = hb._read_heartbeat_md()
    print(f"  Checklist items: {len(items)}")
    for item in items[:3]:
        print(f"    - {item}")

    # ---- Test 5: Manual Trigger (no AI) ----
    print("\n[Test 5] Manual Heartbeat Trigger (no AI router)")
    result = hb.trigger_now()
    print(f"  Response type: {result.response_type.value}")
    print(f"  Cycle number: {result.cycle_number}")
    print(f"  Duration: {result.duration_seconds}s")
    print(f"  Alerts: {len(result.alerts)}")

    # ---- Test 6: Alert Parsing ----
    print("\n[Test 6] Alert Line Parsing")
    test_response = """HEARTBEAT_ALERT
- [email] Important email from boss: Project deadline moved to Friday (severity: warning)
- [calendar] Team standup: Starts in 15 minutes (severity: info)
- [system] Low disk space: Only 4.2GB remaining on C: drive (severity: critical)
"""
    parsed = hb._parse_ai_response(test_response)
    print(f"  Response type: {parsed.response_type.value}")
    print(f"  Alerts parsed: {len(parsed.alerts)}")
    for alert in parsed.alerts:
        print(f"    [{alert.severity}] {alert.category}: {alert.title} -- {alert.detail}")

    # ---- Test 7: Notification Callbacks ----
    print("\n[Test 7] Notification Callbacks")
    callback_results = []

    def test_callback(r: HeartbeatResult):
        callback_results.append(r)

    hb.register_callback(test_callback)
    hb._fire_notification_callbacks(parsed)
    print(f"  Callback invoked: {len(callback_results)} times")
    hb.unregister_callback(test_callback)

    # ---- Test 8: Status ----
    print("\n[Test 8] System Status")
    status = hb.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")

    # ---- Test 9: History ----
    print("\n[Test 9] History")
    history = hb.get_history()
    print(f"  History entries: {len(history)}")

    # ---- Test 10: Start / Stop ----
    print("\n[Test 10] Start / Stop")
    start_result = hb.start()
    print(f"  Start: {start_result}")
    time.sleep(1)
    status = hb.get_status()
    print(f"  Running: {status['running']}")
    stop_result = hb.stop()
    print(f"  Stop: {stop_result}")
    status = hb.get_status()
    print(f"  Running after stop: {status['running']}")

    # ---- Test 11: Singleton ----
    print("\n[Test 11] Singleton Factory")
    hb1 = get_heartbeat_system()
    hb2 = get_heartbeat_system()
    print(f"  Same instance: {hb1 is hb2}")

    # ---- Test 12: HEARTBEAT_OK Parsing ----
    print("\n[Test 12] HEARTBEAT_OK Parsing")
    ok_result = hb._parse_ai_response("HEARTBEAT_OK")
    print(f"  Response type: {ok_result.response_type.value}")
    print(f"  Alerts: {len(ok_result.alerts)}")

    # ---- Test 13: Memory Search ----
    print("\n[Test 13] Memory Search Across Files")
    ml.append_note("Deployed version 2.5 to production server", category="deploy")
    ml.append_note("User prefers dark mode for all applications", category="preference")
    search_results = ml.search("production deploy")
    print(f"  Search 'production deploy': {len(search_results)} results")
    for sr in search_results[:3]:
        print(f"    [{sr['score']}] {sr['file']}:{sr['line_number']} -- {sr['content'][:60]}")

    print("\n" + "=" * 65)
    print("  All tests completed successfully.")
    print("=" * 65)
