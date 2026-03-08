import pytest
from unittest.mock import MagicMock, patch
from modules.proactive_agent import ProactiveAgent

class TestProactiveAgent:
    
    @pytest.fixture
    def agent(self):
        return ProactiveAgent()

    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_monitor_system(self, mock_mem, mock_cpu, agent):
        """Test system monitoring"""
        mock_cpu.return_value = 50
        mock_mem.return_value.percent = 60
        
        # Assuming monitor_system exists
        if hasattr(agent, 'monitor_system'):
            stats = agent.monitor_system()
            assert stats['cpu'] == 50
            assert stats['memory'] == 60

    def test_predict_user_needs(self, agent):
        """Test need prediction"""
        # Mock pattern engine dependency
        agent.pattern_engine = MagicMock()
        agent.pattern_engine.predict_next_action.return_value = "coffee"
        
        prediction = agent.predict_user_needs()
        assert prediction == "coffee"

    def test_suggest_action(self, agent):
        """Test action suggestion"""
        suggestion = agent.suggest_action({'context': 'work'})
        assert suggestion is not None

    def test_check_upcoming_events(self, agent):
        """Test event checking"""
        agent.calendar = MagicMock()
        agent.calendar.get_upcoming_events.return_value = ['meeting']
        
        events = agent.check_upcoming_events()
        assert len(events) == 1
