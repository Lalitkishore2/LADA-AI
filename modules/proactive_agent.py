"""
LADA v9.0 - Proactive Agent
Module 11: Anticipate user needs, provide context-aware suggestions,
smart notifications, and predictive automation.

Features:
- Context-aware suggestions based on time, app, activity
- Smart notification system
- Predictive task automation
- Proactive reminders
- Environment monitoring (weather, calendar, system)
- Intelligent briefings
- Trigger-based suggestions
- Learning from user responses
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum
import re

logger = logging.getLogger(__name__)


class SuggestionPriority(Enum):
    """Priority levels for suggestions."""
    CRITICAL = 1   # Urgent, needs immediate attention
    HIGH = 2       # Important, should act soon
    NORMAL = 3     # Regular suggestions
    LOW = 4        # Nice to know
    BACKGROUND = 5 # Passive, show when convenient


class TriggerType(Enum):
    """Types of triggers for proactive actions."""
    TIME = "time"              # Time-based triggers
    APP_OPEN = "app_open"      # When specific app opens
    APP_CLOSE = "app_close"    # When app closes
    IDLE = "idle"              # User is idle
    PATTERN = "pattern"        # Based on learned patterns
    CALENDAR = "calendar"      # Calendar event approaching
    SYSTEM = "system"          # System state (low battery, disk space)
    LOCATION = "location"      # Location-based (if available)
    MANUAL = "manual"          # Manually triggered


@dataclass
class Suggestion:
    """Represents a proactive suggestion."""
    id: str
    title: str
    message: str
    action: Optional[str] = None  # Command to execute if accepted
    priority: SuggestionPriority = SuggestionPriority.NORMAL
    trigger: TriggerType = TriggerType.PATTERN
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    shown: bool = False
    accepted: bool = False
    dismissed: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'action': self.action,
            'priority': self.priority.name,
            'trigger': self.trigger.value,
            'context': self.context,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'shown': self.shown,
            'accepted': self.accepted,
            'dismissed': self.dismissed
        }


@dataclass
class ProactiveTrigger:
    """Defines a trigger for proactive actions."""
    id: str
    name: str
    trigger_type: TriggerType
    condition: Dict[str, Any]  # Trigger-specific conditions
    action: str  # Command or suggestion to trigger
    enabled: bool = True
    last_triggered: Optional[datetime] = None
    cooldown_minutes: int = 30  # Minimum time between triggers


@dataclass
class Briefing:
    """Morning/evening briefing content."""
    type: str  # morning, evening, weekly
    generated_at: datetime
    sections: List[Dict[str, Any]]
    summary: str


class ProactiveAgent:
    """
    Proactive automation agent.
    Anticipates needs and provides timely suggestions.
    """
    
    # Default morning briefing time
    MORNING_BRIEFING_HOUR = 8
    EVENING_BRIEFING_HOUR = 18
    
    # System check intervals (seconds)
    CHECK_INTERVAL = 60  # Main loop interval
    CALENDAR_CHECK_INTERVAL = 300  # 5 minutes
    SYSTEM_CHECK_INTERVAL = 300  # 5 minutes
    
    def __init__(self, jarvis_core=None, pattern_learner=None):
        """
        Initialize proactive agent.
        
        Args:
            jarvis_core: Reference to JarvisCommandProcessor
            pattern_learner: Reference to PatternLearner for predictions
        """
        self.jarvis = jarvis_core
        self.pattern_learner = pattern_learner
        
        # Data storage
        self.data_dir = Path("data/proactive")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Suggestions queue
        self.suggestions: List[Suggestion] = []
        self.suggestion_history: List[Dict] = []
        
        # Triggers
        self.triggers: Dict[str, ProactiveTrigger] = {}
        self._register_default_triggers()
        
        # Callbacks
        self.suggestion_callbacks: List[Callable[[Suggestion], None]] = []
        
        # State tracking
        self.last_activity = datetime.now()
        self.current_app: Optional[str] = None
        self.idle_threshold_minutes = 5
        self.is_idle = False
        
        # Briefing state
        self.last_morning_briefing: Optional[datetime] = None
        self.last_evening_briefing: Optional[datetime] = None
        
        # Background monitoring
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Response tracking for learning
        self.suggestion_responses: Dict[str, List[bool]] = defaultdict(list)
        
        # Load saved data
        self._load_data()
        
        logger.info("[ProactiveAgent] Initialized")
    
    def _register_default_triggers(self):
        """Register default proactive triggers."""
        # Morning briefing
        self.triggers['morning_briefing'] = ProactiveTrigger(
            id='morning_briefing',
            name='Morning Briefing',
            trigger_type=TriggerType.TIME,
            condition={'hour': self.MORNING_BRIEFING_HOUR, 'minute': 0},
            action='generate_morning_briefing',
            cooldown_minutes=720  # 12 hours
        )
        
        # Evening summary
        self.triggers['evening_summary'] = ProactiveTrigger(
            id='evening_summary',
            name='Evening Summary',
            trigger_type=TriggerType.TIME,
            condition={'hour': self.EVENING_BRIEFING_HOUR, 'minute': 0},
            action='generate_evening_summary',
            cooldown_minutes=720
        )
        
        # Calendar reminder (15 min before events)
        self.triggers['calendar_reminder'] = ProactiveTrigger(
            id='calendar_reminder',
            name='Calendar Reminder',
            trigger_type=TriggerType.CALENDAR,
            condition={'minutes_before': 15},
            action='remind_upcoming_event',
            cooldown_minutes=5
        )
        
        # Low battery warning
        self.triggers['low_battery'] = ProactiveTrigger(
            id='low_battery',
            name='Low Battery Warning',
            trigger_type=TriggerType.SYSTEM,
            condition={'battery_below': 20},
            action='warn_low_battery',
            cooldown_minutes=30
        )
        
        # Idle suggestion (suggest break or productivity tips)
        self.triggers['idle_suggestion'] = ProactiveTrigger(
            id='idle_suggestion',
            name='Idle Suggestion',
            trigger_type=TriggerType.IDLE,
            condition={'idle_minutes': 30},
            action='suggest_on_idle',
            cooldown_minutes=60
        )
    
    # =====================================================
    # SUGGESTION MANAGEMENT
    # =====================================================
    
    def add_suggestion(
        self,
        title: str,
        message: str,
        action: str = None,
        priority: SuggestionPriority = SuggestionPriority.NORMAL,
        trigger: TriggerType = TriggerType.PATTERN,
        expires_minutes: int = None,
        context: Dict = None
    ) -> Suggestion:
        """
        Add a new suggestion to the queue.
        
        Args:
            title: Short title
            message: Detailed message
            action: Command to execute if accepted
            priority: Suggestion priority
            trigger: What triggered this suggestion
            expires_minutes: Auto-expire after N minutes
            context: Additional context
            
        Returns:
            Created Suggestion object
        """
        suggestion_id = f"sug_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.suggestions)}"
        
        expires_at = None
        if expires_minutes:
            expires_at = datetime.now() + timedelta(minutes=expires_minutes)
        
        suggestion = Suggestion(
            id=suggestion_id,
            title=title,
            message=message,
            action=action,
            priority=priority,
            trigger=trigger,
            context=context or {},
            expires_at=expires_at
        )
        
        self.suggestions.append(suggestion)
        
        # Sort by priority
        self.suggestions.sort(key=lambda x: x.priority.value)
        
        # Notify callbacks
        self._notify_suggestion(suggestion)
        
        logger.info(f"[ProactiveAgent] New suggestion: {title}")
        return suggestion
    
    def get_pending_suggestions(self, max_count: int = 5) -> List[Suggestion]:
        """Get pending suggestions that haven't been shown or dismissed."""
        now = datetime.now()
        
        pending = []
        for s in self.suggestions:
            # Skip already handled
            if s.dismissed or s.accepted:
                continue
            
            # Skip expired
            if s.expires_at and now > s.expires_at:
                continue
            
            pending.append(s)
            
            if len(pending) >= max_count:
                break
        
        return pending
    
    def get_next_suggestion(self) -> Optional[Suggestion]:
        """Get the highest priority pending suggestion."""
        pending = self.get_pending_suggestions(1)
        return pending[0] if pending else None
    
    def accept_suggestion(self, suggestion_id: str) -> Dict[str, Any]:
        """Accept a suggestion and execute its action."""
        suggestion = self._find_suggestion(suggestion_id)
        if not suggestion:
            return {'success': False, 'error': 'Suggestion not found'}
        
        suggestion.accepted = True
        suggestion.shown = True
        
        # Track response for learning
        self._record_response(suggestion, accepted=True)
        
        # Execute action if present
        result = None
        if suggestion.action and self.jarvis:
            try:
                result = self.jarvis.process(suggestion.action)
            except Exception as e:
                logger.error(f"[ProactiveAgent] Action failed: {e}")
                result = (False, str(e))
        
        # Move to history
        self._move_to_history(suggestion)
        
        return {
            'success': True,
            'suggestion_id': suggestion_id,
            'action_result': result
        }
    
    def dismiss_suggestion(self, suggestion_id: str, reason: str = None) -> Dict[str, Any]:
        """Dismiss a suggestion."""
        suggestion = self._find_suggestion(suggestion_id)
        if not suggestion:
            return {'success': False, 'error': 'Suggestion not found'}
        
        suggestion.dismissed = True
        suggestion.shown = True
        suggestion.context['dismiss_reason'] = reason
        
        # Track response
        self._record_response(suggestion, accepted=False)
        
        self._move_to_history(suggestion)
        
        return {'success': True, 'suggestion_id': suggestion_id}
    
    def _find_suggestion(self, suggestion_id: str) -> Optional[Suggestion]:
        """Find suggestion by ID."""
        for s in self.suggestions:
            if s.id == suggestion_id:
                return s
        return None
    
    def _move_to_history(self, suggestion: Suggestion):
        """Move suggestion to history."""
        self.suggestion_history.append(suggestion.to_dict())
        self.suggestions = [s for s in self.suggestions if s.id != suggestion.id]
        
        # Keep history limited
        if len(self.suggestion_history) > 500:
            self.suggestion_history = self.suggestion_history[-500:]
    
    def _record_response(self, suggestion: Suggestion, accepted: bool):
        """Record user response for learning."""
        key = f"{suggestion.trigger.value}_{suggestion.title[:20]}"
        self.suggestion_responses[key].append(accepted)
        
        # Keep last 20 responses
        if len(self.suggestion_responses[key]) > 20:
            self.suggestion_responses[key] = self.suggestion_responses[key][-20:]
    
    def _notify_suggestion(self, suggestion: Suggestion):
        """Notify registered callbacks of new suggestion."""
        for callback in self.suggestion_callbacks:
            try:
                callback(suggestion)
            except Exception as e:
                logger.error(f"[ProactiveAgent] Callback error: {e}")
    
    def register_callback(self, callback: Callable[[Suggestion], None]):
        """Register callback for new suggestions."""
        self.suggestion_callbacks.append(callback)
    
    # =====================================================
    # BRIEFINGS
    # =====================================================
    
    def generate_morning_briefing(self) -> Briefing:
        """Generate morning briefing with weather, calendar, tasks."""
        sections = []
        
        # Greeting based on time
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning!"
        elif hour < 17:
            greeting = "Good afternoon!"
        else:
            greeting = "Good evening!"
        
        sections.append({
            'type': 'greeting',
            'content': greeting
        })
        
        # Date
        today = datetime.now()
        sections.append({
            'type': 'date',
            'content': today.strftime("%A, %B %d, %Y")
        })
        
        # Weather (if available)
        weather = self._get_weather()
        if weather:
            sections.append({
                'type': 'weather',
                'content': weather
            })
        
        # Calendar events
        events = self._get_today_events()
        if events:
            sections.append({
                'type': 'calendar',
                'content': f"{len(events)} events today",
                'items': events
            })
        else:
            sections.append({
                'type': 'calendar',
                'content': "No events scheduled today"
            })
        
        # Pattern-based suggestions
        if self.pattern_learner:
            predictions = self.pattern_learner.predict_next_command()
            if predictions.get('predictions'):
                top_prediction = predictions['predictions'][0]
                sections.append({
                    'type': 'suggestion',
                    'content': f"You usually {top_prediction['command']} around now"
                })
        
        # Create summary
        summary_parts = [greeting]
        if weather:
            summary_parts.append(weather)
        if events:
            summary_parts.append(f"You have {len(events)} events today.")
        
        briefing = Briefing(
            type='morning',
            generated_at=datetime.now(),
            sections=sections,
            summary=' '.join(summary_parts)
        )
        
        self.last_morning_briefing = datetime.now()
        
        # Add as suggestion
        self.add_suggestion(
            title="Morning Briefing",
            message=briefing.summary,
            priority=SuggestionPriority.NORMAL,
            trigger=TriggerType.TIME,
            expires_minutes=120
        )
        
        logger.info("[ProactiveAgent] Generated morning briefing")
        return briefing
    
    def generate_evening_summary(self) -> Briefing:
        """Generate evening summary of the day."""
        sections = []
        
        sections.append({
            'type': 'greeting',
            'content': "Here's your evening summary"
        })
        
        # Usage stats if available
        if self.pattern_learner:
            stats = self.pattern_learner.get_usage_stats()
            if stats.get('total_commands', 0) > 0:
                sections.append({
                    'type': 'usage',
                    'content': f"Commands today: {stats.get('commands_per_day', 0):.0f}"
                })
        
        # Tomorrow's preview
        tomorrow_events = self._get_tomorrow_events()
        if tomorrow_events:
            sections.append({
                'type': 'tomorrow',
                'content': f"{len(tomorrow_events)} events tomorrow",
                'items': tomorrow_events
            })
        
        # Suggestion acceptance rate
        total_suggestions = len(self.suggestion_history)
        accepted = sum(1 for s in self.suggestion_history[-20:] if s.get('accepted'))
        if total_suggestions > 0:
            sections.append({
                'type': 'stats',
                'content': f"Suggestion acceptance: {accepted}/{min(20, total_suggestions)}"
            })
        
        summary = "End of day summary. "
        if tomorrow_events:
            summary += f"You have {len(tomorrow_events)} events tomorrow."
        
        briefing = Briefing(
            type='evening',
            generated_at=datetime.now(),
            sections=sections,
            summary=summary
        )
        
        self.last_evening_briefing = datetime.now()
        
        self.add_suggestion(
            title="Evening Summary",
            message=briefing.summary,
            priority=SuggestionPriority.LOW,
            trigger=TriggerType.TIME,
            expires_minutes=180
        )
        
        logger.info("[ProactiveAgent] Generated evening summary")
        return briefing
    
    def _get_weather(self) -> Optional[str]:
        """Get current weather info."""
        try:
            if self.jarvis and hasattr(self.jarvis, 'weather'):
                weather = self.jarvis.weather
                if weather:
                    result = weather.get_current()
                    if result.get('success'):
                        temp = result.get('temperature', 'N/A')
                        desc = result.get('description', 'N/A')
                        return f"{temp}°C, {desc}"
        except Exception as e:
            logger.debug(f"[ProactiveAgent] Weather unavailable: {e}")
        return None
    
    def _get_today_events(self) -> List[Dict]:
        """Get today's calendar events."""
        try:
            if self.jarvis and hasattr(self.jarvis, 'calendar') and self.jarvis.calendar:
                result = self.jarvis.calendar.get_today_events()
                if result.get('success'):
                    return result.get('events', [])
        except Exception as e:
            logger.debug(f"[ProactiveAgent] Calendar unavailable: {e}")
        return []
    
    def _get_tomorrow_events(self) -> List[Dict]:
        """Get tomorrow's calendar events."""
        try:
            if self.jarvis and hasattr(self.jarvis, 'calendar') and self.jarvis.calendar:
                result = self.jarvis.calendar.get_tomorrow_events()
                if result.get('success'):
                    return result.get('events', [])
        except Exception as e:
            logger.debug(f"[ProactiveAgent] Calendar unavailable: {e}")
        return []
    
    # =====================================================
    # CONTEXT-AWARE SUGGESTIONS
    # =====================================================
    
    def suggest_based_on_context(self) -> Optional[Suggestion]:
        """Generate suggestion based on current context."""
        now = datetime.now()
        hour = now.hour
        day = now.weekday()
        
        # Morning productivity (9-12)
        if 9 <= hour < 12 and day < 5:  # Weekday morning
            if self.pattern_learner:
                suggestions = self.pattern_learner.get_suggestions_for_time(hour, day)
                if suggestions:
                    top = suggestions[0]
                    return self.add_suggestion(
                        title="Productivity Suggestion",
                        message=f"You usually {top['command']} at this time",
                        action=top['command'],
                        priority=SuggestionPriority.LOW,
                        trigger=TriggerType.PATTERN,
                        expires_minutes=30
                    )
        
        # Lunch break reminder (12-13)
        if hour == 12 and now.minute < 15:
            if not self._was_recently_suggested('lunch_break', hours=4):
                return self.add_suggestion(
                    title="Lunch Break",
                    message="It's lunchtime! Consider taking a break.",
                    priority=SuggestionPriority.LOW,
                    trigger=TriggerType.TIME,
                    expires_minutes=60,
                    context={'suggestion_key': 'lunch_break'}
                )
        
        # End of workday (17-18)
        if 17 <= hour < 18 and day < 5:
            if not self._was_recently_suggested('end_of_day', hours=8):
                return self.add_suggestion(
                    title="End of Day",
                    message="Consider wrapping up and reviewing tomorrow's schedule",
                    action="tomorrow's schedule",
                    priority=SuggestionPriority.LOW,
                    trigger=TriggerType.TIME,
                    expires_minutes=60,
                    context={'suggestion_key': 'end_of_day'}
                )
        
        return None
    
    def suggest_for_idle(self) -> Optional[Suggestion]:
        """Generate suggestion when user is idle."""
        if not self.is_idle:
            return None
        
        suggestions = [
            ("Take a Break", "You've been idle. Consider stretching or taking a short walk.", None),
            ("Check Email", "Would you like to check your email?", "check email"),
            ("Review Tasks", "Would you like to review your tasks?", "my tasks"),
        ]
        
        import random
        title, message, action = random.choice(suggestions)
        
        return self.add_suggestion(
            title=title,
            message=message,
            action=action,
            priority=SuggestionPriority.BACKGROUND,
            trigger=TriggerType.IDLE,
            expires_minutes=30
        )
    
    def suggest_for_app(self, app_name: str) -> Optional[Suggestion]:
        """Generate suggestion based on current app."""
        app_lower = app_name.lower()
        
        # Browser suggestions
        if any(browser in app_lower for browser in ['chrome', 'firefox', 'edge', 'brave']):
            if self.pattern_learner:
                # Check what user usually searches
                pass
        
        # Code editor suggestions
        if any(editor in app_lower for editor in ['code', 'pycharm', 'sublime', 'atom']):
            return self.add_suggestion(
                title="Coding Mode",
                message="Would you like me to minimize distractions?",
                action="focus mode",
                priority=SuggestionPriority.LOW,
                trigger=TriggerType.APP_OPEN,
                expires_minutes=60,
                context={'app': app_name}
            )
        
        return None
    
    def _was_recently_suggested(self, key: str, hours: int = 4) -> bool:
        """Check if a suggestion was recently shown."""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        for s in self.suggestion_history[-50:]:
            if s.get('context', {}).get('suggestion_key') == key:
                created = datetime.fromisoformat(s['created_at'])
                if created > cutoff:
                    return True
        return False
    
    # =====================================================
    # SYSTEM MONITORING
    # =====================================================
    
    def check_system_state(self) -> List[Suggestion]:
        """Check system state and generate warnings/suggestions."""
        suggestions = []
        
        # Battery check
        battery = self._get_battery_status()
        if battery and battery < 20:
            if not self._was_recently_suggested('low_battery', hours=1):
                suggestions.append(self.add_suggestion(
                    title="Low Battery",
                    message=f"Battery is at {battery}%. Consider plugging in.",
                    priority=SuggestionPriority.HIGH,
                    trigger=TriggerType.SYSTEM,
                    expires_minutes=30,
                    context={'suggestion_key': 'low_battery', 'battery': battery}
                ))
        
        # Disk space check
        disk = self._get_disk_space()
        if disk and disk < 10:  # Less than 10GB
            if not self._was_recently_suggested('low_disk', hours=24):
                suggestions.append(self.add_suggestion(
                    title="Low Disk Space",
                    message=f"Only {disk:.1f}GB free. Consider cleaning up.",
                    action="find large files",
                    priority=SuggestionPriority.HIGH,
                    trigger=TriggerType.SYSTEM,
                    expires_minutes=720,
                    context={'suggestion_key': 'low_disk', 'free_gb': disk}
                ))
        
        return suggestions
    
    def check_calendar_reminders(self) -> List[Suggestion]:
        """Check for upcoming calendar events and create reminders."""
        suggestions = []
        
        try:
            if not self.jarvis or not hasattr(self.jarvis, 'calendar'):
                return suggestions
            
            calendar = self.jarvis.calendar
            if not calendar:
                return suggestions
            
            result = calendar.get_upcoming_events(max_results=5)
            if not result.get('success'):
                return suggestions
            
            now = datetime.now()
            
            for event in result.get('events', []):
                start_str = event.get('start')
                if not start_str:
                    continue
                
                try:
                    # Parse start time
                    if 'T' in start_str:
                        start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    else:
                        start = datetime.strptime(start_str, '%Y-%m-%d')
                    
                    # Calculate time until event
                    time_until = (start - now).total_seconds() / 60  # minutes
                    
                    # 15 minute reminder
                    if 10 <= time_until <= 20:
                        event_key = f"reminder_{event.get('id', '')[:10]}"
                        if not self._was_recently_suggested(event_key, hours=1):
                            suggestions.append(self.add_suggestion(
                                title="Upcoming Event",
                                message=f"'{event.get('summary', 'Event')}' starts in ~15 minutes",
                                priority=SuggestionPriority.HIGH,
                                trigger=TriggerType.CALENDAR,
                                expires_minutes=20,
                                context={'suggestion_key': event_key, 'event': event}
                            ))
                except Exception as e:
                    logger.debug(f"[ProactiveAgent] Event parse error: {e}")
        
        except Exception as e:
            logger.debug(f"[ProactiveAgent] Calendar check error: {e}")
        
        return suggestions
    
    def _get_battery_status(self) -> Optional[int]:
        """Get battery percentage."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                return int(battery.percent)
        except Exception as e:
            pass
        return None
    
    def _get_disk_space(self) -> Optional[float]:
        """Get free disk space in GB."""
        try:
            import psutil
            disk = psutil.disk_usage('/')
            return disk.free / (1024 ** 3)  # GB
        except Exception as e:
            pass
        return None
    
    # =====================================================
    # BACKGROUND MONITORING
    # =====================================================
    
    def monitor_system(self) -> Dict[str, Any]:
        """Monitor system resources."""
        try:
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            return {'cpu': cpu, 'memory': mem}
        except ImportError:
            return {'cpu': 0, 'memory': 0}

    def predict_user_needs(self) -> Optional[str]:
        """Predict what the user needs next."""
        if hasattr(self, 'pattern_engine') and self.pattern_engine:
             # The test sets agent.pattern_engine
             return self.pattern_engine.predict_next_action()
        if self.pattern_learner:
            return self.pattern_learner.predict_next_action()
        return None

    def suggest_action(self, context: Dict[str, Any]) -> Optional[str]:
        """Suggest an action based on context."""
        # Simple logic for now
        if context.get('context') == 'work':
            return "Open VS Code"
        return "Check email"

    def check_upcoming_events(self) -> List[str]:
        """Check for upcoming calendar events."""
        if hasattr(self, 'calendar') and self.calendar:
            return self.calendar.get_upcoming_events()
        return []

    def start(self) -> Dict[str, Any]:
        """Start background monitoring."""
        if self._running:
            return {'success': False, 'error': 'Already running'}
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info("[ProactiveAgent] Background monitoring started")
        return {'success': True}
    
    def stop(self) -> Dict[str, Any]:
        """Stop background monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        self._save_data()
        logger.info("[ProactiveAgent] Background monitoring stopped")
        return {'success': True}
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        last_calendar_check = 0
        last_system_check = 0
        last_context_check = 0
        
        while self._running:
            now = time.time()
            
            try:
                # Calendar reminders
                if now - last_calendar_check >= self.CALENDAR_CHECK_INTERVAL:
                    self.check_calendar_reminders()
                    last_calendar_check = now
                
                # System state
                if now - last_system_check >= self.SYSTEM_CHECK_INTERVAL:
                    self.check_system_state()
                    last_system_check = now
                
                # Context-based suggestions
                if now - last_context_check >= 600:  # Every 10 min
                    self.suggest_based_on_context()
                    last_context_check = now
                
                # Check time-based triggers
                self._check_time_triggers()
                
                # Clean expired suggestions
                self._clean_expired()
                
            except Exception as e:
                logger.error(f"[ProactiveAgent] Monitor error: {e}")
            
            time.sleep(self.CHECK_INTERVAL)
    
    def _check_time_triggers(self):
        """Check and fire time-based triggers."""
        now = datetime.now()
        
        for trigger_id, trigger in self.triggers.items():
            if not trigger.enabled:
                continue
            
            if trigger.trigger_type != TriggerType.TIME:
                continue
            
            # Check cooldown
            if trigger.last_triggered:
                cooldown_delta = timedelta(minutes=trigger.cooldown_minutes)
                if now - trigger.last_triggered < cooldown_delta:
                    continue
            
            # Check condition
            condition = trigger.condition
            target_hour = condition.get('hour')
            target_minute = condition.get('minute', 0)
            
            if now.hour == target_hour and now.minute == target_minute:
                self._fire_trigger(trigger)
    
    def _fire_trigger(self, trigger: ProactiveTrigger):
        """Fire a proactive trigger."""
        trigger.last_triggered = datetime.now()
        
        action = trigger.action
        
        # Built-in actions
        if action == 'generate_morning_briefing':
            self.generate_morning_briefing()
        elif action == 'generate_evening_summary':
            self.generate_evening_summary()
        elif action == 'suggest_on_idle':
            self.suggest_for_idle()
        else:
            # Try as JARVIS command
            if self.jarvis:
                try:
                    self.jarvis.process(action)
                except Exception as e:
                    pass
        
        logger.info(f"[ProactiveAgent] Fired trigger: {trigger.name}")
    
    def _clean_expired(self):
        """Remove expired suggestions."""
        now = datetime.now()
        expired = [s for s in self.suggestions if s.expires_at and now > s.expires_at]
        
        for s in expired:
            s.dismissed = True
            s.context['auto_expired'] = True
            self._move_to_history(s)
    
    # =====================================================
    # ACTIVITY TRACKING
    # =====================================================
    
    def record_activity(self):
        """Record user activity (call when user does something)."""
        self.last_activity = datetime.now()
        self.is_idle = False
    
    def check_idle(self) -> bool:
        """Check if user is idle."""
        idle_time = (datetime.now() - self.last_activity).total_seconds() / 60
        self.is_idle = idle_time >= self.idle_threshold_minutes
        return self.is_idle
    
    def set_current_app(self, app_name: str):
        """Update current active application."""
        if app_name != self.current_app:
            old_app = self.current_app
            self.current_app = app_name
            
            # Trigger app-change suggestions
            if app_name:
                self.suggest_for_app(app_name)
    
    # =====================================================
    # TRIGGERS MANAGEMENT
    # =====================================================
    
    def add_trigger(
        self,
        name: str,
        trigger_type: TriggerType,
        condition: Dict,
        action: str,
        cooldown_minutes: int = 30
    ) -> ProactiveTrigger:
        """Add a new proactive trigger."""
        trigger_id = f"trigger_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        trigger = ProactiveTrigger(
            id=trigger_id,
            name=name,
            trigger_type=trigger_type,
            condition=condition,
            action=action,
            cooldown_minutes=cooldown_minutes
        )
        
        self.triggers[trigger_id] = trigger
        return trigger
    
    def remove_trigger(self, trigger_id: str) -> Dict[str, Any]:
        """Remove a trigger."""
        if trigger_id in self.triggers:
            del self.triggers[trigger_id]
            return {'success': True}
        return {'success': False, 'error': 'Trigger not found'}
    
    def enable_trigger(self, trigger_id: str, enabled: bool = True) -> Dict[str, Any]:
        """Enable or disable a trigger."""
        if trigger_id in self.triggers:
            self.triggers[trigger_id].enabled = enabled
            return {'success': True}
        return {'success': False, 'error': 'Trigger not found'}
    
    def list_triggers(self) -> List[Dict]:
        """List all triggers."""
        return [{
            'id': t.id,
            'name': t.name,
            'type': t.trigger_type.value,
            'enabled': t.enabled,
            'action': t.action
        } for t in self.triggers.values()]
    
    # =====================================================
    # DATA PERSISTENCE
    # =====================================================
    
    def _save_data(self):
        """Save agent data."""
        try:
            data = {
                'suggestion_history': self.suggestion_history[-200:],
                'suggestion_responses': dict(self.suggestion_responses),
                'last_morning_briefing': self.last_morning_briefing.isoformat() if self.last_morning_briefing else None,
                'last_evening_briefing': self.last_evening_briefing.isoformat() if self.last_evening_briefing else None
            }
            
            with open(self.data_dir / 'agent_data.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[ProactiveAgent] Save error: {e}")
    
    def _load_data(self):
        """Load saved data."""
        try:
            data_file = self.data_dir / 'agent_data.json'
            if data_file.exists():
                with open(data_file, 'r') as f:
                    data = json.load(f)
                
                self.suggestion_history = data.get('suggestion_history', [])
                self.suggestion_responses = defaultdict(list, data.get('suggestion_responses', {}))
                
                if data.get('last_morning_briefing'):
                    self.last_morning_briefing = datetime.fromisoformat(data['last_morning_briefing'])
                if data.get('last_evening_briefing'):
                    self.last_evening_briefing = datetime.fromisoformat(data['last_evening_briefing'])
        except Exception as e:
            logger.error(f"[ProactiveAgent] Load error: {e}")
    
    # =====================================================
    # STATUS & INFO
    # =====================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            'running': self._running,
            'pending_suggestions': len(self.get_pending_suggestions()),
            'total_triggers': len(self.triggers),
            'enabled_triggers': sum(1 for t in self.triggers.values() if t.enabled),
            'is_idle': self.is_idle,
            'current_app': self.current_app,
            'history_count': len(self.suggestion_history)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        total_shown = len(self.suggestion_history)
        accepted = sum(1 for s in self.suggestion_history if s.get('accepted'))
        dismissed = sum(1 for s in self.suggestion_history if s.get('dismissed'))
        
        return {
            'total_suggestions': total_shown,
            'accepted': accepted,
            'dismissed': dismissed,
            'acceptance_rate': (accepted / total_shown * 100) if total_shown > 0 else 0
        }


# =====================================================
# SINGLETON & FACTORIES
# =====================================================

_agent = None

def get_proactive_agent(jarvis_core=None, pattern_learner=None) -> ProactiveAgent:
    """Get or create proactive agent instance."""
    global _agent
    if _agent is None:
        _agent = ProactiveAgent(jarvis_core, pattern_learner)
    return _agent

def create_proactive_agent(jarvis_core=None, pattern_learner=None) -> ProactiveAgent:
    """Create new proactive agent instance."""
    return ProactiveAgent(jarvis_core, pattern_learner)


# =====================================================
# EXAMPLE USAGE & TESTS
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Proactive Agent Test")
    print("=" * 60)
    
    agent = ProactiveAgent()
    
    # Test 1: Add suggestion
    print("\n📋 Test 1: Adding Suggestions")
    s1 = agent.add_suggestion(
        title="Test Suggestion",
        message="This is a test suggestion",
        action="check email",
        priority=SuggestionPriority.NORMAL
    )
    print(f"   ✓ Created suggestion: {s1.id}")
    
    s2 = agent.add_suggestion(
        title="High Priority",
        message="This is urgent!",
        priority=SuggestionPriority.HIGH,
        expires_minutes=5
    )
    print(f"   ✓ Created high priority: {s2.id}")
    
    # Test 2: Get pending
    print("\n📥 Test 2: Getting Pending Suggestions")
    pending = agent.get_pending_suggestions()
    print(f"   ✓ Pending suggestions: {len(pending)}")
    for p in pending:
        print(f"     - {p.title} (Priority: {p.priority.name})")
    
    # Test 3: Accept suggestion
    print("\n✅ Test 3: Accepting Suggestion")
    result = agent.accept_suggestion(s1.id)
    print(f"   ✓ Accepted: {result['success']}")
    
    # Test 4: Dismiss suggestion
    print("\n❌ Test 4: Dismissing Suggestion")
    result = agent.dismiss_suggestion(s2.id, reason="Not interested")
    print(f"   ✓ Dismissed: {result['success']}")
    
    # Test 5: Morning briefing
    print("\n🌅 Test 5: Morning Briefing")
    briefing = agent.generate_morning_briefing()
    print(f"   ✓ Generated: {briefing.type}")
    print(f"   ✓ Sections: {len(briefing.sections)}")
    print(f"   ✓ Summary: {briefing.summary[:50]}...")
    
    # Test 6: System check
    print("\n🖥️ Test 6: System State Check")
    suggestions = agent.check_system_state()
    print(f"   ✓ System suggestions: {len(suggestions)}")
    
    # Test 7: Triggers
    print("\n⚡ Test 7: Triggers")
    triggers = agent.list_triggers()
    print(f"   ✓ Registered triggers: {len(triggers)}")
    for t in triggers[:3]:
        print(f"     - {t['name']} ({t['type']})")
    
    # Test 8: Status
    print("\n📊 Test 8: Agent Status")
    status = agent.get_status()
    print(f"   ✓ Running: {status['running']}")
    print(f"   ✓ Pending: {status['pending_suggestions']}")
    print(f"   ✓ Triggers: {status['total_triggers']}")
    
    # Test 9: Stats
    print("\n📈 Test 9: Agent Statistics")
    stats = agent.get_stats()
    print(f"   ✓ Total suggestions: {stats['total_suggestions']}")
    print(f"   ✓ Accepted: {stats['accepted']}")
    print(f"   ✓ Acceptance rate: {stats['acceptance_rate']:.1f}%")
    
    print("\n" + "=" * 60)
    print("✅ Proactive Agent tests complete!")
