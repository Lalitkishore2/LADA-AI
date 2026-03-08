"""
LADA - Task Scheduler
Cron-style background task scheduling with natural language support.

Features:
- Cron expression scheduling
- Interval-based scheduling
- One-time scheduled execution
- Natural language schedule parsing
- Job persistence across restarts
- Execution history tracking
"""

import os
import json
import time
import logging
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    INTERVAL = "interval"  # Every N seconds/minutes/hours
    DAILY = "daily"  # At specific time each day
    WEEKLY = "weekly"  # At specific time on specific days
    ONCE = "once"  # One-time execution at specific datetime
    CRON = "cron"  # Cron-style expression


@dataclass
class ScheduledTask:
    """A scheduled task definition"""
    name: str
    schedule_type: str  # ScheduleType value
    action: str  # Command/workflow to execute
    schedule_config: Dict[str, Any] = field(default_factory=dict)
    # For INTERVAL: {'seconds': int}
    # For DAILY: {'hour': int, 'minute': int}
    # For WEEKLY: {'day_of_week': int (0=Mon), 'hour': int, 'minute': int}
    # For ONCE: {'datetime': ISO string}
    # For CRON: {'expression': str}
    enabled: bool = True
    last_run: Optional[str] = None  # ISO datetime
    next_run: Optional[str] = None  # ISO datetime
    run_count: int = 0
    max_retries: int = 2
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledTask':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExecutionRecord:
    """Record of a task execution"""
    task_name: str
    started_at: str
    completed_at: Optional[str] = None
    success: bool = False
    result: str = ""
    error: Optional[str] = None


class TaskScheduler:
    """
    Background task scheduler with cron-style capabilities.

    Runs a background thread that checks for due tasks and executes them.
    Persists schedules and history to disk.
    """

    def __init__(self, data_dir: Optional[str] = None, action_handler: Optional[Callable] = None):
        """
        Args:
            data_dir: Directory for persistence files
            action_handler: Callback(action_string) -> str for executing actions
        """
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.path.dirname(os.path.dirname(__file__))) / 'data'

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.schedules_file = self.data_dir / 'schedules.json'
        self.history_file = self.data_dir / 'schedule_history.json'

        self.tasks: Dict[str, ScheduledTask] = {}
        self.history: List[ExecutionRecord] = []
        self.action_handler = action_handler

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._check_interval = 30  # Check every 30 seconds

        self._load_schedules()
        logger.info(f"[Scheduler] Initialized with {len(self.tasks)} tasks")

    def _load_schedules(self):
        """Load saved schedules from disk."""
        if self.schedules_file.exists():
            try:
                with open(self.schedules_file, 'r') as f:
                    data = json.load(f)
                for name, task_data in data.items():
                    self.tasks[name] = ScheduledTask.from_dict(task_data)
                logger.info(f"[Scheduler] Loaded {len(self.tasks)} schedules")
            except Exception as e:
                logger.error(f"[Scheduler] Failed to load schedules: {e}")

    def _save_schedules(self):
        """Save schedules to disk."""
        try:
            data = {name: task.to_dict() for name, task in self.tasks.items()}
            with open(self.schedules_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[Scheduler] Failed to save schedules: {e}")

    def _save_history(self):
        """Save execution history to disk."""
        try:
            # Keep last 100 records
            records = [asdict(r) for r in self.history[-100:]]
            with open(self.history_file, 'w') as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            logger.error(f"[Scheduler] Failed to save history: {e}")

    def schedule_interval(self, name: str, action: str, seconds: int) -> ScheduledTask:
        """Schedule a task to run at a fixed interval."""
        task = ScheduledTask(
            name=name,
            schedule_type=ScheduleType.INTERVAL.value,
            action=action,
            schedule_config={'seconds': seconds},
            next_run=(datetime.now() + timedelta(seconds=seconds)).isoformat(),
        )
        self.tasks[name] = task
        self._save_schedules()
        logger.info(f"[Scheduler] Scheduled '{name}' every {seconds}s")
        return task

    def schedule_daily(self, name: str, action: str, hour: int, minute: int = 0) -> ScheduledTask:
        """Schedule a task to run daily at a specific time."""
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        task = ScheduledTask(
            name=name,
            schedule_type=ScheduleType.DAILY.value,
            action=action,
            schedule_config={'hour': hour, 'minute': minute},
            next_run=next_run.isoformat(),
        )
        self.tasks[name] = task
        self._save_schedules()
        logger.info(f"[Scheduler] Scheduled '{name}' daily at {hour:02d}:{minute:02d}")
        return task

    def schedule_weekly(self, name: str, action: str, day_of_week: int,
                       hour: int, minute: int = 0) -> ScheduledTask:
        """Schedule a weekly task. day_of_week: 0=Monday, 6=Sunday."""
        now = datetime.now()
        days_ahead = day_of_week - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        next_run += timedelta(days=days_ahead)
        if next_run <= now:
            next_run += timedelta(weeks=1)

        task = ScheduledTask(
            name=name,
            schedule_type=ScheduleType.WEEKLY.value,
            action=action,
            schedule_config={'day_of_week': day_of_week, 'hour': hour, 'minute': minute},
            next_run=next_run.isoformat(),
        )
        self.tasks[name] = task
        self._save_schedules()
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        logger.info(f"[Scheduler] Scheduled '{name}' weekly on {days[day_of_week]} at {hour:02d}:{minute:02d}")
        return task

    def schedule_once(self, name: str, action: str, run_at: datetime) -> ScheduledTask:
        """Schedule a one-time task."""
        task = ScheduledTask(
            name=name,
            schedule_type=ScheduleType.ONCE.value,
            action=action,
            schedule_config={'datetime': run_at.isoformat()},
            next_run=run_at.isoformat(),
        )
        self.tasks[name] = task
        self._save_schedules()
        logger.info(f"[Scheduler] Scheduled '{name}' once at {run_at}")
        return task

    def cancel_task(self, name: str) -> bool:
        """Cancel a scheduled task."""
        if name in self.tasks:
            del self.tasks[name]
            self._save_schedules()
            logger.info(f"[Scheduler] Cancelled '{name}'")
            return True
        return False

    def list_scheduled(self) -> List[Dict[str, Any]]:
        """List all scheduled tasks."""
        return [
            {
                'name': t.name,
                'type': t.schedule_type,
                'action': t.action,
                'enabled': t.enabled,
                'next_run': t.next_run,
                'last_run': t.last_run,
                'run_count': t.run_count,
            }
            for t in self.tasks.values()
        ]

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent execution history."""
        return [asdict(r) for r in self.history[-limit:]]

    def parse_natural_language(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse natural language schedule descriptions.
        Returns schedule config or None if not parseable.

        Examples:
        - "every 30 minutes" -> interval 1800s
        - "every day at 9am" -> daily at 09:00
        - "every Monday at 3pm" -> weekly on Monday at 15:00
        """
        import re
        text_lower = text.lower().strip()

        # "every N minutes/hours/seconds"
        interval_match = re.search(
            r'every\s+(\d+)\s*(second|minute|hour|sec|min|hr)s?', text_lower
        )
        if interval_match:
            amount = int(interval_match.group(1))
            unit = interval_match.group(2)
            multipliers = {
                'second': 1, 'sec': 1,
                'minute': 60, 'min': 60,
                'hour': 3600, 'hr': 3600,
            }
            seconds = amount * multipliers.get(unit, 60)
            return {'type': 'interval', 'seconds': seconds}

        # "every day at HH:MM" or "daily at HH AM/PM"
        daily_match = re.search(
            r'(?:every\s+day|daily)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',
            text_lower
        )
        if daily_match:
            hour = int(daily_match.group(1))
            minute = int(daily_match.group(2) or 0)
            ampm = daily_match.group(3)
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            return {'type': 'daily', 'hour': hour, 'minute': minute}

        # "every Monday/Tuesday/... at HH:MM"
        days = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6}
        weekly_match = re.search(
            r'every\s+(' + '|'.join(days.keys()) + r')\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',
            text_lower
        )
        if weekly_match:
            day = days[weekly_match.group(1)]
            hour = int(weekly_match.group(2))
            minute = int(weekly_match.group(3) or 0)
            ampm = weekly_match.group(4)
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            return {'type': 'weekly', 'day_of_week': day, 'hour': hour, 'minute': minute}

        return None

    def _is_due(self, task: ScheduledTask) -> bool:
        """Check if a task is due for execution."""
        if not task.enabled or not task.next_run:
            return False
        try:
            next_run = datetime.fromisoformat(task.next_run)
            return datetime.now() >= next_run
        except (ValueError, TypeError):
            return False

    def _update_next_run(self, task: ScheduledTask):
        """Calculate and set the next run time after execution."""
        now = datetime.now()
        config = task.schedule_config

        if task.schedule_type == ScheduleType.INTERVAL.value:
            seconds = config.get('seconds', 60)
            task.next_run = (now + timedelta(seconds=seconds)).isoformat()

        elif task.schedule_type == ScheduleType.DAILY.value:
            next_run = now.replace(
                hour=config.get('hour', 0),
                minute=config.get('minute', 0),
                second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            task.next_run = next_run.isoformat()

        elif task.schedule_type == ScheduleType.WEEKLY.value:
            dow = config.get('day_of_week', 0)
            days_ahead = dow - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run = now.replace(
                hour=config.get('hour', 0),
                minute=config.get('minute', 0),
                second=0, microsecond=0
            ) + timedelta(days=days_ahead)
            task.next_run = next_run.isoformat()

        elif task.schedule_type == ScheduleType.ONCE.value:
            task.enabled = False  # One-time tasks disable after running
            task.next_run = None

    def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task."""
        record = ExecutionRecord(
            task_name=task.name,
            started_at=datetime.now().isoformat(),
        )

        try:
            if self.action_handler:
                result = self.action_handler(task.action)
                record.success = True
                record.result = str(result) if result else "OK"
            else:
                record.success = True
                record.result = "No handler configured"
                logger.warning(f"[Scheduler] No action handler for: {task.action}")

        except Exception as e:
            record.success = False
            record.error = str(e)
            logger.error(f"[Scheduler] Task '{task.name}' failed: {e}")

        record.completed_at = datetime.now().isoformat()
        self.history.append(record)

        # Update task metadata
        task.last_run = datetime.now().isoformat()
        task.run_count += 1
        self._update_next_run(task)
        self._save_schedules()
        self._save_history()

        logger.info(f"[Scheduler] Executed '{task.name}': {'OK' if record.success else 'FAILED'}")

    def _scheduler_loop(self):
        """Main scheduler loop running in background thread."""
        logger.info("[Scheduler] Background scheduler started")
        while self._running:
            try:
                for task in list(self.tasks.values()):
                    if self._is_due(task):
                        self._execute_task(task)
            except Exception as e:
                logger.error(f"[Scheduler] Loop error: {e}")

            # Sleep in small increments for responsive shutdown
            for _ in range(self._check_interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("[Scheduler] Background scheduler stopped")

    def start(self):
        """Start the background scheduler."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        logger.info("[Scheduler] Started")

    def stop(self):
        """Stop the background scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Scheduler] Stopped")


# Singleton
_scheduler = None


def get_scheduler(data_dir: Optional[str] = None,
                  action_handler: Optional[Callable] = None) -> TaskScheduler:
    """Get or create task scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler(data_dir=data_dir, action_handler=action_handler)
    return _scheduler
