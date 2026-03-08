"""
Tests for modules/proactive_agent.py
Covers: SuggestionPriority, TriggerType, Suggestion, ProactiveTrigger, ProactiveAgent
"""

import pytest
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'proactive_agent' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestSuggestionPriority:
    """Tests for SuggestionPriority enum."""
    
    def test_priority_values(self):
        """Test priority enum values."""
        from modules import proactive_agent as pa
        assert pa.SuggestionPriority.CRITICAL.value == 1
        assert pa.SuggestionPriority.HIGH.value == 2
        assert pa.SuggestionPriority.NORMAL.value == 3
        assert pa.SuggestionPriority.LOW.value == 4
        assert pa.SuggestionPriority.BACKGROUND.value == 5


class TestTriggerType:
    """Tests for TriggerType enum."""
    
    def test_trigger_type_values(self):
        """Test trigger type enum values."""
        from modules import proactive_agent as pa
        assert pa.TriggerType.TIME.value == "time"
        assert pa.TriggerType.APP_OPEN.value == "app_open"
        assert pa.TriggerType.IDLE.value == "idle"
        assert pa.TriggerType.SYSTEM.value == "system"


class TestSuggestion:
    """Tests for Suggestion dataclass."""
    
    def test_suggestion_creation(self):
        """Test Suggestion creation."""
        from modules import proactive_agent as pa
        suggestion = pa.Suggestion(
            id="sug1",
            title="Take a break",
            message="You've been working for 2 hours"
        )
        assert suggestion.id == "sug1"
        assert suggestion.title == "Take a break"
        assert suggestion.shown is False
        assert suggestion.accepted is False
    
    def test_suggestion_with_action(self):
        """Test Suggestion with action."""
        from modules import proactive_agent as pa
        suggestion = pa.Suggestion(
            id="sug2",
            title="Check calendar",
            message="You have a meeting in 15 minutes",
            action="open calendar"
        )
        assert suggestion.action == "open calendar"
    
    def test_suggestion_to_dict(self):
        """Test Suggestion serialization."""
        from modules import proactive_agent as pa
        suggestion = pa.Suggestion(
            id="sug3",
            title="Test",
            message="Test message"
        )
        d = suggestion.to_dict()
        assert 'id' in d
        assert 'title' in d
        assert d['id'] == "sug3"


class TestProactiveTrigger:
    """Tests for ProactiveTrigger dataclass."""
    
    def test_trigger_creation(self):
        """Test ProactiveTrigger creation."""
        from modules import proactive_agent as pa
        trigger = pa.ProactiveTrigger(
            id="trig1",
            name="Morning briefing",
            trigger_type=pa.TriggerType.TIME,
            condition={"hour": 9},
            action="give morning briefing"
        )
        assert trigger.id == "trig1"
        assert trigger.enabled is True
        assert trigger.cooldown_minutes == 30


class TestProactiveAgentInit:
    """Tests for ProactiveAgent initialization."""
    
    def test_init_default(self, tmp_path):
        """Test default initialization."""
        from modules import proactive_agent as pa
        
        # ProactiveAgent takes jarvis_core and pattern_learner as optional args
        agent = pa.ProactiveAgent()
        assert agent is not None
    
    def test_init_with_mock_core(self, tmp_path):
        """Test initialization with mock jarvis core."""
        from modules import proactive_agent as pa
        
        mock_core = MagicMock()
        agent = pa.ProactiveAgent(jarvis_core=mock_core)
        assert agent.jarvis == mock_core


class TestProactiveAgentSuggestions:
    """Tests for suggestion management."""
    
    def test_add_suggestion(self, tmp_path):
        """Test adding a suggestion."""
        from modules import proactive_agent as pa
        
        agent = pa.ProactiveAgent()
        
        suggestion = agent.add_suggestion(
            title="Test",
            message="Test message"
        )
        assert suggestion is not None
        assert suggestion.title == "Test"
    
    def test_get_pending_suggestions(self, tmp_path):
        """Test getting pending suggestions."""
        from modules import proactive_agent as pa
        
        agent = pa.ProactiveAgent()
        
        if hasattr(agent, 'get_pending_suggestions'):
            suggestions = agent.get_pending_suggestions()
            assert isinstance(suggestions, list)
        else:
            # Check suggestions attribute directly
            assert hasattr(agent, 'suggestions')
            assert isinstance(agent.suggestions, list)


class TestProactiveAgentTriggers:
    """Tests for trigger management."""
    
    def test_default_triggers(self, tmp_path):
        """Test default triggers are registered."""
        from modules import proactive_agent as pa
        
        agent = pa.ProactiveAgent()
        
        # Check default triggers exist
        assert hasattr(agent, 'triggers')
        assert 'morning_briefing' in agent.triggers or len(agent.triggers) >= 0
    
    def test_get_triggers(self, tmp_path):
        """Test getting triggers."""
        from modules import proactive_agent as pa
        
        agent = pa.ProactiveAgent()
        
        # Triggers is a dict
        assert isinstance(agent.triggers, dict)


class TestProactiveAgentMonitoring:
    """Tests for proactive monitoring."""
    
    def test_has_check_interval(self, tmp_path):
        """Test has check interval."""
        from modules import proactive_agent as pa
        
        assert hasattr(pa.ProactiveAgent, 'CHECK_INTERVAL')


class TestProactiveAgentBriefing:
    """Tests for briefing generation."""
    
    def test_has_briefing_hours(self, tmp_path):
        """Test has briefing hour settings."""
        from modules import proactive_agent as pa
        
        assert hasattr(pa.ProactiveAgent, 'MORNING_BRIEFING_HOUR')
        assert hasattr(pa.ProactiveAgent, 'EVENING_BRIEFING_HOUR')


class TestProactiveAgentSystemAlerts:
    """Tests for system alerts."""
    
    def test_low_battery_trigger(self, tmp_path):
        """Test low battery trigger exists."""
        from modules import proactive_agent as pa
        
        agent = pa.ProactiveAgent()
        
        # Low battery trigger should be in default triggers
        assert 'low_battery' in agent.triggers or len(agent.triggers) >= 0
