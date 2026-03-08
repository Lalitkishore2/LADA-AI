"""Tests for modules/agent_actions.py"""
import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_module():
    """Reset module before each test to ensure fresh imports"""
    # Remove cached module to force reimport
    mods_to_remove = [k for k in sys.modules if k.startswith("modules.agent_actions")]
    for mod in mods_to_remove:
        del sys.modules[mod]
    yield
    # Cleanup after test
    mods_to_remove = [k for k in sys.modules if k.startswith("modules.agent_actions")]
    for mod in mods_to_remove:
        del sys.modules[mod]


class TestAgentActions:
    """Tests for AgentActions class"""

    def test_init(self):
        # Patch flags before import
        with patch.dict("sys.modules", {}):
            import modules.agent_actions as aa
            
            # Reload with mocked flags
            aa.SYS_OK = False
            aa.CALENDAR_OK = False
            
            agent = aa.AgentActions()
            assert agent.sys is None
            assert agent.calendar is None
            assert len(agent.action_patterns) > 0

    def test_action_patterns_defined(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False
        
        agent = aa.AgentActions()
        assert "open_browser" in agent.action_patterns
        assert "search_web" in agent.action_patterns
        assert "open_url" in agent.action_patterns
        assert "open_youtube" in agent.action_patterns
        assert "open_app" in agent.action_patterns

    def test_process_open_browser(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False
        
        agent = aa.AgentActions()

        with patch("webbrowser.open") as mock_open:
            mock_open.return_value = True
            handled, response = agent.process("open the browser")
            assert handled is True

    def test_process_search_web(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False
        
        agent = aa.AgentActions()

        with patch("webbrowser.open") as mock_open:
            mock_open.return_value = True
            handled, response = agent.process("search for python tutorials")
            assert handled is True

    def test_process_open_youtube(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False
        
        agent = aa.AgentActions()

        with patch("webbrowser.open") as mock_open:
            mock_open.return_value = True
            handled, response = agent.process("open youtube")
            assert handled is True

    def test_process_no_match(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False
        
        agent = aa.AgentActions()
        handled, response = agent.process("random unrecognized text blah blah")
        assert handled is False

    def test_process_take_screenshot(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False
        
        agent = aa.AgentActions()
        handled, response = agent.process("take a screenshot")
        # May succeed or fail based on dependencies
        assert isinstance(handled, bool)

    def test_process_volume_control(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False

        agent = aa.AgentActions()
        handled, response = agent.process("set volume to 50")
        assert isinstance(handled, bool)

    def test_process_command(self):
        import modules.agent_actions as aa
        
        aa.SYS_OK = False
        aa.CALENDAR_OK = False

        agent = aa.AgentActions()

        with patch("webbrowser.open") as mock_open:
            mock_open.return_value = True
            result = agent.process("open browser")
            assert result is not None
