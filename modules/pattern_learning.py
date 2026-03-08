"""
LADA v9.0 - Pattern Learning Engine
Module 10: Learn user behavior patterns, detect habits, 
suggest routines, and adapt automation to user preferences.

Features:
- Command usage tracking and analysis
- Time-based pattern detection
- Habit formation detection
- Routine suggestions
- Preference learning
- Adaptive responses
- Action sequence prediction
- Context-aware suggestions
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict, Counter
import math
import re

logger = logging.getLogger(__name__)


# =====================================================
# DATA CLASSES
# =====================================================

@dataclass
class CommandEvent:
    """Represents a user command event."""
    command: str
    category: str
    timestamp: datetime
    day_of_week: int  # 0=Monday, 6=Sunday
    hour: int
    success: bool = True
    context: Dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'command': self.command,
            'category': self.category,
            'timestamp': self.timestamp.isoformat(),
            'day_of_week': self.day_of_week,
            'hour': self.hour,
            'success': self.success,
            'context': self.context,
            'duration': self.duration
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CommandEvent':
        return cls(
            command=data['command'],
            category=data['category'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            day_of_week=data['day_of_week'],
            hour=data['hour'],
            success=data.get('success', True),
            context=data.get('context', {}),
            duration=data.get('duration', 0.0)
        )


@dataclass
class Pattern:
    """Represents a detected usage pattern."""
    pattern_type: str  # time_based, sequence, frequency, preference
    description: str
    confidence: float  # 0.0 to 1.0
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    active: bool = True


@dataclass
class Habit:
    """Represents a detected user habit."""
    name: str
    trigger: str  # time, event, context
    actions: List[str]
    frequency: str  # daily, weekday, weekend, weekly
    typical_time: int  # hour of day
    typical_days: List[int]  # days of week
    strength: float  # 0.0 to 1.0, how consistent
    occurrences: int
    first_detected: datetime
    last_triggered: datetime
    suggested_routine: bool = False


@dataclass
class Preference:
    """Represents a learned user preference."""
    category: str
    key: str
    value: Any
    confidence: float
    sample_count: int
    last_updated: datetime


@dataclass
class RoutineSuggestion:
    """Suggested routine based on patterns."""
    name: str
    description: str
    trigger_type: str  # time, event, manual
    trigger_time: str  # "09:00" or event name
    trigger_days: List[str]  # ["monday", "tuesday", ...]
    actions: List[Dict[str, Any]]
    confidence: float
    based_on_pattern: str
    created_at: datetime = field(default_factory=datetime.now)


class PatternLearner:
    """
    Machine learning engine for user behavior patterns.
    Learns from usage, detects habits, suggests automations.
    """
    
    # Command categories for classification
    CATEGORIES = {
        'system': ['volume', 'brightness', 'mute', 'shutdown', 'restart', 'sleep', 'lock'],
        'browser': ['open', 'tab', 'search', 'google', 'youtube', 'website', 'navigate'],
        'file': ['file', 'folder', 'document', 'save', 'copy', 'move', 'delete'],
        'email': ['email', 'gmail', 'inbox', 'send', 'compose', 'mail'],
        'calendar': ['calendar', 'event', 'meeting', 'schedule', 'appointment'],
        'media': ['play', 'pause', 'stop', 'music', 'video', 'spotify', 'netflix'],
        'productivity': ['task', 'todo', 'note', 'reminder', 'timer', 'focus'],
        'weather': ['weather', 'temperature', 'forecast', 'rain'],
        'info': ['time', 'date', 'battery', 'status', 'what', 'tell me'],
        'workflow': ['workflow', 'routine', 'automation'],
        'voice': ['wake', 'listen', 'stop', 'voice'],
    }
    
    def __init__(self, data_dir: str = None):
        """
        Initialize pattern learner.
        
        Args:
            data_dir: Directory for storing learning data
        """
        self.data_dir = Path(data_dir or "data/patterns")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Event storage
        self.events: List[CommandEvent] = []
        self.events_file = self.data_dir / "command_events.json"
        
        # Detected patterns
        self.patterns: Dict[str, Pattern] = {}
        self.patterns_file = self.data_dir / "patterns.json"
        
        # Detected habits
        self.habits: Dict[str, Habit] = {}
        self.habits_file = self.data_dir / "habits.json"
        
        # Learned preferences
        self.preferences: Dict[str, Preference] = {}
        self.preferences_file = self.data_dir / "preferences.json"
        
        # Suggested routines
        self.routine_suggestions: List[RoutineSuggestion] = []
        
        # Quick stats
        self.command_counts: Counter = Counter()
        self.hourly_usage: Dict[int, Counter] = defaultdict(Counter)
        self.daily_usage: Dict[int, Counter] = defaultdict(Counter)
        self.sequence_counts: Counter = Counter()
        
        # Settings
        self.min_pattern_occurrences = 3
        self.habit_threshold = 0.6  # 60% consistency
        self.learning_enabled = True
        
        # Load existing data
        self._load_data()
        
        logger.info(f"[PatternLearner] Initialized with {len(self.events)} historical events")
    
    # =====================================================
    # DATA PERSISTENCE
    # =====================================================
    
    def _load_data(self):
        """Load saved learning data."""
        try:
            # Load events
            if self.events_file.exists():
                with open(self.events_file, 'r') as f:
                    data = json.load(f)
                    self.events = [CommandEvent.from_dict(e) for e in data]
                    self._rebuild_stats()
            
            # Load patterns
            if self.patterns_file.exists():
                with open(self.patterns_file, 'r') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        v['first_seen'] = datetime.fromisoformat(v['first_seen'])
                        v['last_seen'] = datetime.fromisoformat(v['last_seen'])
                        self.patterns[k] = Pattern(**v)
            
            # Load habits
            if self.habits_file.exists():
                with open(self.habits_file, 'r') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        v['first_detected'] = datetime.fromisoformat(v['first_detected'])
                        v['last_triggered'] = datetime.fromisoformat(v['last_triggered'])
                        self.habits[k] = Habit(**v)
            
            # Load preferences
            if self.preferences_file.exists():
                with open(self.preferences_file, 'r') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        v['last_updated'] = datetime.fromisoformat(v['last_updated'])
                        self.preferences[k] = Preference(**v)
                        
        except Exception as e:
            logger.error(f"[PatternLearner] Load error: {e}")
    
    def _save_data(self):
        """Save learning data to disk."""
        try:
            # Save events (last 10000)
            events_data = [e.to_dict() for e in self.events[-10000:]]
            with open(self.events_file, 'w') as f:
                json.dump(events_data, f, indent=2)
            
            # Save patterns
            patterns_data = {}
            for k, v in self.patterns.items():
                pd = asdict(v)
                pd['first_seen'] = v.first_seen.isoformat()
                pd['last_seen'] = v.last_seen.isoformat()
                patterns_data[k] = pd
            with open(self.patterns_file, 'w') as f:
                json.dump(patterns_data, f, indent=2)
            
            # Save habits
            habits_data = {}
            for k, v in self.habits.items():
                hd = asdict(v)
                hd['first_detected'] = v.first_detected.isoformat()
                hd['last_triggered'] = v.last_triggered.isoformat()
                habits_data[k] = hd
            with open(self.habits_file, 'w') as f:
                json.dump(habits_data, f, indent=2)
            
            # Save preferences
            prefs_data = {}
            for k, v in self.preferences.items():
                pd = asdict(v)
                pd['last_updated'] = v.last_updated.isoformat()
                prefs_data[k] = pd
            with open(self.preferences_file, 'w') as f:
                json.dump(prefs_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"[PatternLearner] Save error: {e}")
    
    def _rebuild_stats(self):
        """Rebuild quick stats from events."""
        self.command_counts.clear()
        self.hourly_usage.clear()
        self.daily_usage.clear()
        self.sequence_counts.clear()
        
        prev_command = None
        for event in self.events:
            self.command_counts[event.command] += 1
            self.hourly_usage[event.hour][event.command] += 1
            self.daily_usage[event.day_of_week][event.command] += 1
            
            # Track sequences
            if prev_command:
                seq = f"{prev_command} -> {event.command}"
                self.sequence_counts[seq] += 1
            prev_command = event.command
    
    # =====================================================
    # EVENT RECORDING
    # =====================================================
    
    def record_command(
        self,
        command: str,
        success: bool = True,
        context: Dict = None,
        duration: float = 0.0
    ) -> Dict[str, Any]:
        """
        Record a user command for learning.
        
        Args:
            command: The command text
            success: Whether it succeeded
            context: Additional context (app, window, etc.)
            duration: How long it took
            
        Returns:
            {'success': True, 'patterns_found': [...]}
        """
        if not self.learning_enabled:
            return {'success': True, 'learning_disabled': True}
        
        now = datetime.now()
        category = self._categorize_command(command)
        
        event = CommandEvent(
            command=command.lower().strip(),
            category=category,
            timestamp=now,
            day_of_week=now.weekday(),
            hour=now.hour,
            success=success,
            context=context or {},
            duration=duration
        )
        
        # Add to history
        self.events.append(event)
        
        # Update quick stats
        self.command_counts[event.command] += 1
        self.hourly_usage[event.hour][event.command] += 1
        self.daily_usage[event.day_of_week][event.command] += 1
        
        # Track sequence
        if len(self.events) > 1:
            prev = self.events[-2].command
            seq = f"{prev} -> {event.command}"
            self.sequence_counts[seq] += 1
        
        # Analyze patterns periodically
        new_patterns = []
        if len(self.events) % 10 == 0:  # Every 10 commands
            new_patterns = self._analyze_patterns()
        
        # Save periodically
        if len(self.events) % 50 == 0:
            self._save_data()
        
        return {
            'success': True,
            'event_id': len(self.events),
            'category': category,
            'new_patterns': new_patterns
        }
    
    def _categorize_command(self, command: str) -> str:
        """Categorize a command."""
        command_lower = command.lower()
        
        for category, keywords in self.CATEGORIES.items():
            if any(kw in command_lower for kw in keywords):
                return category
        
        return 'general'
    
    # =====================================================
    # PATTERN ANALYSIS
    # =====================================================
    
    def _analyze_patterns(self) -> List[str]:
        """Analyze events for patterns. Returns new pattern names."""
        new_patterns = []
        
        # Time-based patterns
        time_patterns = self._detect_time_patterns()
        for p in time_patterns:
            key = f"time_{p['hour']}_{p['command']}"
            if key not in self.patterns:
                self.patterns[key] = Pattern(
                    pattern_type='time_based',
                    description=f"User often uses '{p['command']}' around {p['hour']}:00",
                    confidence=p['confidence'],
                    occurrences=p['count'],
                    first_seen=datetime.now(),
                    last_seen=datetime.now(),
                    details=p
                )
                new_patterns.append(key)
        
        # Sequence patterns
        seq_patterns = self._detect_sequence_patterns()
        for p in seq_patterns:
            key = f"seq_{p['sequence'].replace(' -> ', '_to_')}"
            if key not in self.patterns:
                self.patterns[key] = Pattern(
                    pattern_type='sequence',
                    description=f"User often does '{p['sequence']}'",
                    confidence=p['confidence'],
                    occurrences=p['count'],
                    first_seen=datetime.now(),
                    last_seen=datetime.now(),
                    details=p
                )
                new_patterns.append(key)
        
        # Day-based patterns
        day_patterns = self._detect_day_patterns()
        for p in day_patterns:
            day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][p['day']]
            key = f"day_{p['day']}_{p['command']}"
            if key not in self.patterns:
                self.patterns[key] = Pattern(
                    pattern_type='day_based',
                    description=f"User uses '{p['command']}' frequently on {day_name}",
                    confidence=p['confidence'],
                    occurrences=p['count'],
                    first_seen=datetime.now(),
                    last_seen=datetime.now(),
                    details=p
                )
                new_patterns.append(key)
        
        # Check for habits
        self._detect_habits()
        
        return new_patterns
    
    def _detect_time_patterns(self) -> List[Dict]:
        """Detect time-based command patterns."""
        patterns = []
        
        for hour, commands in self.hourly_usage.items():
            total_at_hour = sum(commands.values())
            if total_at_hour < self.min_pattern_occurrences:
                continue
            
            for command, count in commands.most_common(3):
                if count >= self.min_pattern_occurrences:
                    confidence = count / total_at_hour
                    if confidence > 0.2:  # At least 20% of commands at this hour
                        patterns.append({
                            'hour': hour,
                            'command': command,
                            'count': count,
                            'confidence': confidence
                        })
        
        return patterns
    
    def _detect_sequence_patterns(self) -> List[Dict]:
        """Detect command sequence patterns."""
        patterns = []
        total_sequences = sum(self.sequence_counts.values())
        
        if total_sequences < self.min_pattern_occurrences:
            return patterns
        
        for seq, count in self.sequence_counts.most_common(10):
            if count >= self.min_pattern_occurrences:
                confidence = count / total_sequences
                if confidence > 0.05:  # At least 5% of sequences
                    patterns.append({
                        'sequence': seq,
                        'count': count,
                        'confidence': confidence
                    })
        
        return patterns
    
    def _detect_day_patterns(self) -> List[Dict]:
        """Detect day-of-week patterns."""
        patterns = []
        
        for day, commands in self.daily_usage.items():
            total_on_day = sum(commands.values())
            if total_on_day < self.min_pattern_occurrences:
                continue
            
            for command, count in commands.most_common(3):
                # Check if this command is more common on this day
                total_command = self.command_counts[command]
                if total_command > 0:
                    ratio = count / total_command
                    if ratio > 0.25 and count >= self.min_pattern_occurrences:  # 25%+ on this day
                        patterns.append({
                            'day': day,
                            'command': command,
                            'count': count,
                            'confidence': ratio
                        })
        
        return patterns
    
    def _detect_habits(self):
        """Detect habits from patterns and events."""
        # Group events by approximate time slots
        time_slots: Dict[str, List[CommandEvent]] = defaultdict(list)
        
        for event in self.events[-500:]:  # Recent events
            # Create time slot key (hour + day type)
            is_weekend = event.day_of_week >= 5
            day_type = 'weekend' if is_weekend else 'weekday'
            slot_key = f"{event.hour}_{day_type}"
            time_slots[slot_key].append(event)
        
        # Analyze each time slot for consistent behavior
        for slot_key, slot_events in time_slots.items():
            if len(slot_events) < self.min_pattern_occurrences:
                continue
            
            hour, day_type = slot_key.split('_')
            hour = int(hour)
            
            # Find most common commands in this slot
            slot_commands = Counter(e.command for e in slot_events)
            
            for command, count in slot_commands.most_common(3):
                # Calculate consistency (how often this command appears in this slot)
                # vs how many times this slot has activity
                dates_with_slot = set(e.timestamp.date() for e in slot_events)
                dates_with_command = set(
                    e.timestamp.date() for e in slot_events if e.command == command
                )
                
                if len(dates_with_slot) >= self.min_pattern_occurrences:
                    consistency = len(dates_with_command) / len(dates_with_slot)
                    
                    if consistency >= self.habit_threshold:
                        habit_key = f"habit_{hour}_{day_type}_{command}"
                        
                        # Determine frequency
                        if day_type == 'weekend':
                            frequency = 'weekend'
                            typical_days = [5, 6]
                        else:
                            frequency = 'weekday'
                            typical_days = [0, 1, 2, 3, 4]
                        
                        if habit_key not in self.habits:
                            self.habits[habit_key] = Habit(
                                name=f"{command} at {hour}:00",
                                trigger='time',
                                actions=[command],
                                frequency=frequency,
                                typical_time=hour,
                                typical_days=typical_days,
                                strength=consistency,
                                occurrences=count,
                                first_detected=datetime.now(),
                                last_triggered=slot_events[-1].timestamp
                            )
                            logger.info(f"[PatternLearner] New habit detected: {habit_key}")
                        else:
                            # Update existing habit
                            self.habits[habit_key].strength = consistency
                            self.habits[habit_key].occurrences = count
                            self.habits[habit_key].last_triggered = slot_events[-1].timestamp
    
    # =====================================================
    # PREDICTIONS & SUGGESTIONS
    # =====================================================
    
    def predict_next_command(self, current_command: str = None) -> Dict[str, Any]:
        """
        Predict the most likely next command.
        
        Args:
            current_command: The command just executed
            
        Returns:
            {'success': True, 'predictions': [...]}
        """
        now = datetime.now()
        predictions = []
        
        # Based on current time
        hour = now.hour
        if hour in self.hourly_usage:
            for cmd, count in self.hourly_usage[hour].most_common(3):
                predictions.append({
                    'command': cmd,
                    'reason': f'Often used around {hour}:00',
                    'confidence': min(0.5 + count * 0.05, 0.9),
                    'source': 'time'
                })
        
        # Based on sequence
        if current_command:
            for seq, count in self.sequence_counts.most_common(20):
                if seq.startswith(current_command.lower()):
                    next_cmd = seq.split(' -> ')[1]
                    confidence = min(0.4 + count * 0.1, 0.95)
                    predictions.append({
                        'command': next_cmd,
                        'reason': f'Often follows "{current_command}"',
                        'confidence': confidence,
                        'source': 'sequence'
                    })
                    break
        
        # Based on day
        day = now.weekday()
        if day in self.daily_usage:
            for cmd, count in self.daily_usage[day].most_common(2):
                day_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day]
                predictions.append({
                    'command': cmd,
                    'reason': f'Common on {day_name}s',
                    'confidence': min(0.3 + count * 0.03, 0.7),
                    'source': 'day'
                })
        
        # Sort by confidence and deduplicate
        seen = set()
        unique_predictions = []
        for p in sorted(predictions, key=lambda x: x['confidence'], reverse=True):
            if p['command'] not in seen:
                seen.add(p['command'])
                unique_predictions.append(p)
        
        return {
            'success': True,
            'predictions': unique_predictions[:5],
            'timestamp': now.isoformat()
        }
    
    def suggest_routines(self) -> List[RoutineSuggestion]:
        """
        Generate routine suggestions based on detected habits.
        
        Returns:
            List of RoutineSuggestion objects
        """
        suggestions = []
        
        for habit_key, habit in self.habits.items():
            if habit.suggested_routine:
                continue  # Already suggested
            
            if habit.strength < 0.7:  # Only suggest strong habits
                continue
            
            # Create routine suggestion
            trigger_time = f"{habit.typical_time:02d}:00"
            
            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            trigger_days = [day_names[d] for d in habit.typical_days]
            
            suggestion = RoutineSuggestion(
                name=f"Auto: {habit.name}",
                description=f"Based on your habit of {habit.actions[0]} at {trigger_time}",
                trigger_type='time',
                trigger_time=trigger_time,
                trigger_days=trigger_days,
                actions=[{'action': a, 'params': {}} for a in habit.actions],
                confidence=habit.strength,
                based_on_pattern=habit_key
            )
            
            suggestions.append(suggestion)
            habit.suggested_routine = True
        
        self.routine_suggestions = suggestions
        return suggestions
    
    def get_suggestions_for_time(self, hour: int = None, day: int = None) -> List[Dict]:
        """
        Get command suggestions for a specific time.
        
        Args:
            hour: Hour of day (0-23), default current
            day: Day of week (0-6), default current
        """
        if hour is None:
            hour = datetime.now().hour
        if day is None:
            day = datetime.now().weekday()
        
        suggestions = []
        
        # Time-based
        if hour in self.hourly_usage:
            for cmd, count in self.hourly_usage[hour].most_common(5):
                suggestions.append({
                    'command': cmd,
                    'reason': f'You usually do this around {hour}:00',
                    'times_used': count
                })
        
        # Day-based
        if day in self.daily_usage:
            day_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day]
            for cmd, count in self.daily_usage[day].most_common(3):
                if cmd not in [s['command'] for s in suggestions]:
                    suggestions.append({
                        'command': cmd,
                        'reason': f'Common for you on {day_name}s',
                        'times_used': count
                    })
        
        return suggestions[:7]
    
    # =====================================================
    # PREFERENCE LEARNING
    # =====================================================
    
    def learn_preference(
        self,
        category: str,
        key: str,
        value: Any,
        confidence_boost: float = 0.1
    ) -> Dict[str, Any]:
        """
        Learn or update a user preference.
        
        Args:
            category: Preference category (volume, browser, theme, etc.)
            key: Preference key
            value: Preference value
            confidence_boost: How much to boost confidence
        """
        pref_key = f"{category}_{key}"
        
        if pref_key in self.preferences:
            pref = self.preferences[pref_key]
            
            # Update value if different
            if pref.value != value:
                pref.value = value
                pref.confidence = min(confidence_boost, 0.5)  # Reset on change
            else:
                pref.confidence = min(pref.confidence + confidence_boost, 1.0)
            
            pref.sample_count += 1
            pref.last_updated = datetime.now()
        else:
            self.preferences[pref_key] = Preference(
                category=category,
                key=key,
                value=value,
                confidence=confidence_boost,
                sample_count=1,
                last_updated=datetime.now()
            )
        
        return {
            'success': True,
            'preference': pref_key,
            'value': value,
            'confidence': self.preferences[pref_key].confidence
        }
    
    def get_preference(self, category: str, key: str, default: Any = None) -> Any:
        """Get a learned preference value."""
        pref_key = f"{category}_{key}"
        if pref_key in self.preferences:
            return self.preferences[pref_key].value
        return default
    
    def get_all_preferences(self, category: str = None) -> Dict[str, Any]:
        """Get all preferences, optionally filtered by category."""
        result = {}
        for key, pref in self.preferences.items():
            if category is None or pref.category == category:
                result[pref.key] = {
                    'value': pref.value,
                    'confidence': pref.confidence,
                    'samples': pref.sample_count
                }
        return result
    
    # =====================================================
    # ANALYTICS & INSIGHTS
    # =====================================================
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get comprehensive usage statistics."""
        if not self.events:
            return {'success': True, 'message': 'No data yet'}
        
        total_events = len(self.events)
        
        # Time range
        first_event = min(e.timestamp for e in self.events)
        last_event = max(e.timestamp for e in self.events)
        days_tracked = (last_event - first_event).days + 1
        
        # Most used commands
        top_commands = self.command_counts.most_common(10)
        
        # Most active hours
        hour_totals = {h: sum(c.values()) for h, c in self.hourly_usage.items()}
        peak_hours = sorted(hour_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Category breakdown
        category_counts = Counter(e.category for e in self.events)
        
        return {
            'success': True,
            'total_commands': total_events,
            'days_tracked': days_tracked,
            'commands_per_day': total_events / max(1, days_tracked),
            'unique_commands': len(self.command_counts),
            'top_commands': [{'command': c, 'count': n} for c, n in top_commands],
            'peak_hours': [{'hour': h, 'count': c} for h, c in peak_hours],
            'by_category': dict(category_counts),
            'patterns_detected': len(self.patterns),
            'habits_detected': len(self.habits),
            'preferences_learned': len(self.preferences)
        }
    
    def get_insights(self) -> List[str]:
        """Get human-readable insights about user behavior."""
        insights = []
        
        if not self.events:
            return ["Not enough data yet. Keep using LADA to learn your patterns!"]
        
        # Peak usage time
        hour_totals = {h: sum(c.values()) for h, c in self.hourly_usage.items()}
        if hour_totals:
            peak_hour = max(hour_totals.items(), key=lambda x: x[1])[0]
            insights.append(f"📊 You're most active around {peak_hour}:00")
        
        # Favorite command
        if self.command_counts:
            fav_cmd, fav_count = self.command_counts.most_common(1)[0]
            insights.append(f"🎯 Your most used command is '{fav_cmd}' ({fav_count} times)")
        
        # Day patterns
        day_totals = {d: sum(c.values()) for d, c in self.daily_usage.items()}
        if day_totals:
            peak_day = max(day_totals.items(), key=lambda x: x[1])[0]
            day_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][peak_day]
            insights.append(f"📅 You use LADA most on {day_name}s")
        
        # Habits
        strong_habits = [h for h in self.habits.values() if h.strength > 0.8]
        if strong_habits:
            habit = strong_habits[0]
            insights.append(f"⏰ Strong habit: {habit.name} (consistency: {habit.strength:.0%})")
        
        # Sequence patterns
        if self.sequence_counts:
            top_seq = self.sequence_counts.most_common(1)[0]
            insights.append(f"🔗 Common sequence: {top_seq[0]}")
        
        return insights
    
    def get_patterns(self, pattern_type: str = None) -> List[Dict]:
        """Get detected patterns."""
        result = []
        for key, pattern in self.patterns.items():
            if pattern_type is None or pattern.pattern_type == pattern_type:
                result.append({
                    'key': key,
                    'type': pattern.pattern_type,
                    'description': pattern.description,
                    'confidence': pattern.confidence,
                    'occurrences': pattern.occurrences,
                    'active': pattern.active
                })
        return sorted(result, key=lambda x: x['confidence'], reverse=True)
    
    def get_habits(self) -> List[Dict]:
        """Get detected habits."""
        result = []
        for key, habit in self.habits.items():
            result.append({
                'key': key,
                'name': habit.name,
                'trigger': habit.trigger,
                'frequency': habit.frequency,
                'time': habit.typical_time,
                'strength': habit.strength,
                'actions': habit.actions
            })
        return sorted(result, key=lambda x: x['strength'], reverse=True)
    
    # =====================================================
    # MANAGEMENT
    # =====================================================
    
    def clear_history(self, before: datetime = None) -> Dict[str, Any]:
        """Clear command history."""
        if before:
            original = len(self.events)
            self.events = [e for e in self.events if e.timestamp > before]
            cleared = original - len(self.events)
        else:
            cleared = len(self.events)
            self.events = []
        
        self._rebuild_stats()
        self._save_data()
        
        return {'success': True, 'cleared': cleared}
    
    def reset_patterns(self) -> Dict[str, Any]:
        """Reset all detected patterns."""
        count = len(self.patterns)
        self.patterns.clear()
        self._save_data()
        return {'success': True, 'reset': count}
    
    def reset_all(self) -> Dict[str, Any]:
        """Reset all learning data."""
        self.events.clear()
        self.patterns.clear()
        self.habits.clear()
        self.preferences.clear()
        self._rebuild_stats()
        self._save_data()
        return {'success': True, 'message': 'All learning data cleared'}
    
    def enable_learning(self, enabled: bool = True):
        """Enable or disable learning."""
        self.learning_enabled = enabled
        return {'success': True, 'learning_enabled': enabled}
    
    def predict_next_action(self, context: Dict[str, Any] = None) -> Optional[str]:
        """Predict the next likely action based on context."""
        # Check context for time (for tests)
        if context and 'time' in context:
            time_key = context['time']
            if time_key in self.patterns:
                pat = self.patterns[time_key]
                if isinstance(pat, list) and pat:
                    return pat[0]

        # Simple implementation: check time-based patterns or sequence
        current_hour = datetime.now().hour
        
        # Check hourly usage
        if current_hour in self.hourly_usage:
            most_common = self.hourly_usage[current_hour].most_common(1)
            if most_common:
                return most_common[0][0]
        
        return None

    def identify_routines(self) -> List[RoutineSuggestion]:
        """Identify potential routines from patterns."""
        suggestions = []
        # Simple implementation: if a command is used every day at the same hour
        for hour, counter in self.hourly_usage.items():
            for cmd, count in counter.items():
                if count > 5: # Arbitrary threshold
                    suggestions.append(RoutineSuggestion(
                        name=f"Daily {cmd}",
                        description=f"Execute {cmd} at {hour}:00",
                        trigger_type="time",
                        trigger_time=f"{hour}:00",
                        trigger_days=["daily"],
                        actions=[{'action': cmd}],
                        confidence=0.8,
                        based_on_pattern="frequency"
                    ))
        return suggestions

    def save(self):
        """Force save all data."""
        self._save_data()
        return {'success': True}


# =====================================================
# SINGLETON & FACTORIES
# =====================================================

_learner = None

def get_pattern_learner() -> PatternLearner:
    """Get or create pattern learner instance."""
    global _learner
    if _learner is None:
        _learner = PatternLearner()
    return _learner

def create_pattern_learner(data_dir: str = None) -> PatternLearner:
    """Create new pattern learner instance."""
    return PatternLearner(data_dir)


# =====================================================
# QUICK FUNCTIONS
# =====================================================

def record_command(command: str, **kwargs) -> Dict[str, Any]:
    """Quick function to record a command."""
    return get_pattern_learner().record_command(command, **kwargs)

def predict_next(**kwargs) -> Dict[str, Any]:
    """Quick function to predict next command."""
    return get_pattern_learner().predict_next_command(**kwargs)

def get_suggestions() -> List[Dict]:
    """Quick function to get suggestions."""
    return get_pattern_learner().get_suggestions_for_time()


# =====================================================
# EXAMPLE USAGE & TESTS
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Pattern Learning Test")
    print("=" * 60)
    
    # Create learner with test data dir
    learner = PatternLearner(data_dir="data/test_patterns")
    
    # Simulate some commands
    print("\n📝 Simulating Command History...")
    test_commands = [
        "check email",
        "set volume 50",
        "open youtube",
        "play music",
        "check weather",
        "check email",
        "set volume 60",
        "open google",
        "search flights",
        "check calendar",
        "check email",
        "set brightness 80",
        "play music",
        "check email",
    ]
    
    for cmd in test_commands:
        result = learner.record_command(cmd)
        print(f"   Recorded: {cmd} ({result['category']})")
    
    # Test predictions
    print("\n🔮 Testing Predictions...")
    predictions = learner.predict_next_command("check email")
    print(f"   After 'check email', predictions:")
    for p in predictions.get('predictions', [])[:3]:
        print(f"     - {p['command']} ({p['confidence']:.0%} - {p['reason']})")
    
    # Test statistics
    print("\n📊 Usage Statistics...")
    stats = learner.get_usage_stats()
    print(f"   Total commands: {stats['total_commands']}")
    print(f"   Unique commands: {stats['unique_commands']}")
    print(f"   Top command: {stats['top_commands'][0] if stats.get('top_commands') else 'N/A'}")
    
    # Test insights
    print("\n💡 Insights...")
    for insight in learner.get_insights()[:3]:
        print(f"   {insight}")
    
    # Test preferences
    print("\n⚙️ Testing Preferences...")
    learner.learn_preference("audio", "default_volume", 50)
    learner.learn_preference("audio", "default_volume", 50)  # Reinforce
    vol = learner.get_preference("audio", "default_volume")
    print(f"   Learned volume preference: {vol}")
    
    # Test suggestions
    print("\n📋 Suggestions for Current Time...")
    suggestions = learner.get_suggestions_for_time()
    for s in suggestions[:3]:
        print(f"   - {s['command']}: {s['reason']}")
    
    # Patterns
    print("\n🔍 Detected Patterns...")
    patterns = learner.get_patterns()
    if patterns:
        for p in patterns[:3]:
            print(f"   - {p['description']} ({p['confidence']:.0%})")
    else:
        print("   No patterns detected yet (need more data)")
    
    print("\n" + "=" * 60)
    print("✅ Pattern Learning tests complete!")
    print(f"   Events recorded: {len(learner.events)}")
    print(f"   Patterns found: {len(learner.patterns)}")
    print(f"   Habits detected: {len(learner.habits)}")
    print(f"   Preferences: {len(learner.preferences)}")
    
    # Cleanup test data
    import shutil
    test_dir = Path("data/test_patterns")
    if test_dir.exists():
        shutil.rmtree(test_dir)
        print("\n   (Test data cleaned up)")
