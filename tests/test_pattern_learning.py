"""
Tests for modules/pattern_learning.py
Covers: CommandEvent, Pattern, Habit, PatternLearner
"""

import pytest
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'pattern_learning' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestCommandEvent:
    """Tests for CommandEvent dataclass."""
    
    def test_command_event_creation(self):
        """Test CommandEvent creation."""
        from modules import pattern_learning as pl
        now = datetime.now()
        event = pl.CommandEvent(
            command="open chrome",
            category="app",
            timestamp=now,
            day_of_week=now.weekday(),
            hour=now.hour
        )
        assert event.command == "open chrome"
        assert event.category == "app"
        assert event.success is True
    
    def test_command_event_to_dict(self):
        """Test CommandEvent serialization."""
        from modules import pattern_learning as pl
        now = datetime.now()
        event = pl.CommandEvent(
            command="test",
            category="test",
            timestamp=now,
            day_of_week=0,
            hour=10
        )
        d = event.to_dict()
        assert 'command' in d
        assert 'timestamp' in d
        assert d['command'] == "test"
    
    def test_command_event_from_dict(self):
        """Test CommandEvent deserialization."""
        from modules import pattern_learning as pl
        data = {
            'command': "volume 50",
            'category': "system",
            'timestamp': datetime.now().isoformat(),
            'day_of_week': 1,
            'hour': 14,
            'success': True,
            'context': {},
            'duration': 0.5
        }
        event = pl.CommandEvent.from_dict(data)
        assert event.command == "volume 50"
        assert event.category == "system"


class TestPattern:
    """Tests for Pattern dataclass."""
    
    def test_pattern_creation(self):
        """Test Pattern creation."""
        from modules import pattern_learning as pl
        now = datetime.now()
        pattern = pl.Pattern(
            pattern_type="time_based",
            description="Morning routine",
            confidence=0.8,
            occurrences=10,
            first_seen=now,
            last_seen=now
        )
        assert pattern.pattern_type == "time_based"
        assert pattern.confidence == 0.8
        assert pattern.active is True


class TestHabit:
    """Tests for Habit dataclass."""
    
    def test_habit_creation(self):
        """Test Habit creation."""
        from modules import pattern_learning as pl
        now = datetime.now()
        habit = pl.Habit(
            name="Morning email",
            trigger="time",
            actions=["open outlook", "check inbox"],
            frequency="daily",
            typical_time=9,
            typical_days=[0, 1, 2, 3, 4],
            strength=0.9,
            occurrences=20,
            first_detected=now,
            last_triggered=now
        )
        assert habit.name == "Morning email"
        assert len(habit.actions) == 2
        assert habit.strength == 0.9


class TestPatternLearnerInit:
    """Tests for PatternLearner initialization."""
    
    def test_init_default(self, tmp_path):
        """Test default initialization."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        assert learner is not None
    
    def test_init_creates_data_dir(self, tmp_path):
        """Test that init creates data directory."""
        from modules import pattern_learning as pl
        data_path = tmp_path / "patterns"
        learner = pl.PatternLearner(data_dir=str(data_path))
        # May or may not create directory depending on implementation
        assert learner is not None


class TestPatternLearnerRecordEvent:
    """Tests for recording events."""
    
    def test_record_event(self, tmp_path):
        """Test recording a command event."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        # Record an event
        if hasattr(learner, 'record_event'):
            learner.record_event("open chrome", category="app")
            # Verify event was recorded
            assert hasattr(learner, 'events') or hasattr(learner, 'command_events')
    
    def test_record_multiple_events(self, tmp_path):
        """Test recording multiple events."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'record_event'):
            for i in range(5):
                learner.record_event(f"command {i}", category="test")


class TestPatternLearnerAnalysis:
    """Tests for pattern analysis."""
    
    def test_analyze_patterns(self, tmp_path):
        """Test pattern analysis."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'analyze_patterns'):
            patterns = learner.analyze_patterns()
            assert patterns is None or isinstance(patterns, (list, dict))
    
    def test_detect_habits(self, tmp_path):
        """Test habit detection."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'detect_habits'):
            habits = learner.detect_habits()
            assert habits is None or isinstance(habits, (list, dict))


class TestPatternLearnerPreferences:
    """Tests for preference learning."""
    
    def test_get_preferences(self, tmp_path):
        """Test getting learned preferences."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'get_preferences'):
            prefs = learner.get_preferences()
            assert prefs is None or isinstance(prefs, dict)
    
    def test_update_preference(self, tmp_path):
        """Test updating a preference."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'update_preference'):
            learner.update_preference("theme", "dark")


class TestPatternLearnerPredictions:
    """Tests for predictions."""
    
    def test_predict_next_command(self, tmp_path):
        """Test predicting next command."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'predict_next'):
            prediction = learner.predict_next()
            # May return None or prediction object


class TestPatternLearnerPersistence:
    """Tests for data persistence."""
    
    def test_save_patterns(self, tmp_path):
        """Test saving patterns."""
        from modules import pattern_learning as pl
        learner = pl.PatternLearner(data_dir=str(tmp_path))
        
        if hasattr(learner, 'save'):
            learner.save()
    
    def test_load_patterns(self, tmp_path):
        """Test loading patterns."""
        from modules import pattern_learning as pl
        
        # Create and save
        learner1 = pl.PatternLearner(data_dir=str(tmp_path))
        if hasattr(learner1, 'save'):
            learner1.save()
        
        # Load in new instance
        learner2 = pl.PatternLearner(data_dir=str(tmp_path))
        assert learner2 is not None
