"""
Tests for Comet Agent - Autonomous AI Control
Tests the See → Think → Act loop for autonomous task execution
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.comet_agent import (
    CometAgent, ActionType, Action, ScreenState, TaskResult,
    QuickActions, create_comet_agent
)


class TestActionType:
    """Test ActionType enum"""
    
    def test_action_types_exist(self):
        assert ActionType.CLICK.value == "click"
        assert ActionType.TYPE.value == "type"
        assert ActionType.NAVIGATE.value == "navigate"
        assert ActionType.SCROLL.value == "scroll"
        assert ActionType.WAIT.value == "wait"
        assert ActionType.EXTRACT.value == "extract"
        assert ActionType.SCREENSHOT.value == "screenshot"
        assert ActionType.KEYBOARD.value == "keyboard"
        assert ActionType.OPEN_APP.value == "open_app"
        assert ActionType.COMPLETE.value == "complete"
        assert ActionType.ERROR.value == "error"


class TestAction:
    """Test Action dataclass"""
    
    def test_action_creation(self):
        action = Action(
            type=ActionType.CLICK,
            target="Submit button",
            confidence=0.95,
            reasoning="Need to submit form"
        )
        assert action.type == ActionType.CLICK
        assert action.target == "Submit button"
        assert action.confidence == 0.95
        
    def test_action_defaults(self):
        action = Action(type=ActionType.WAIT)
        assert action.target is None
        assert action.value is None
        assert action.confidence == 1.0
        assert action.reasoning == ""


class TestScreenState:
    """Test ScreenState dataclass"""
    
    def test_screen_state_creation(self):
        state = ScreenState(
            visible_text="Hello World",
            current_url="https://example.com",
            active_window="Chrome"
        )
        assert state.visible_text == "Hello World"
        assert state.current_url == "https://example.com"
        assert state.active_window == "Chrome"
        
    def test_screen_state_defaults(self):
        state = ScreenState()
        assert state.screenshot_path is None
        assert state.visible_text == ""
        assert state.detected_elements == []
        assert state.timestamp > 0


class TestTaskResult:
    """Test TaskResult dataclass"""
    
    def test_successful_result(self):
        result = TaskResult(
            success=True,
            message="Task completed",
            steps_taken=5
        )
        assert result.success == True
        assert result.steps_taken == 5
        
    def test_failed_result(self):
        result = TaskResult(
            success=False,
            message="Task failed",
            steps_taken=3,
            error="Could not find element"
        )
        assert result.success == False
        assert result.error == "Could not find element"


class TestCometAgent:
    """Test CometAgent class"""
    
    @pytest.fixture
    def agent(self):
        agent = CometAgent(ai_router=None, headless=True)
        yield agent
        agent.cleanup()
        
    def test_agent_creation(self, agent):
        assert agent is not None
        assert agent.is_running == False
        assert agent.action_history == []
        assert agent.state_history == []
        
    def test_capture_screen_state(self, agent):
        # Mock the screen capture components
        with patch.object(agent, 'screenshot_analyzer', None):
            with patch.object(agent, 'screen_vision', None):
                state = agent._capture_screen_state()
                assert isinstance(state, ScreenState)
                assert state.timestamp > 0
                
    def test_basic_planning_navigate(self, agent):
        state = ScreenState()
        actions = agent._basic_planning("go to google.com", state)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.NAVIGATE
        assert "google.com" in actions[0].value
        
    def test_basic_planning_search(self, agent):
        state = ScreenState()
        actions = agent._basic_planning("search for python tutorials", state)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.NAVIGATE
        assert "google.com/search" in actions[0].value
        
    def test_basic_planning_click(self, agent):
        state = ScreenState()
        actions = agent._basic_planning("click on submit button", state)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.CLICK
        
    def test_basic_planning_type(self, agent):
        state = ScreenState()
        actions = agent._basic_planning("type hello world", state)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.TYPE
        
    def test_basic_planning_open_app(self, agent):
        state = ScreenState()
        actions = agent._basic_planning("open chrome", state)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.OPEN_APP
        
    def test_basic_planning_unknown(self, agent):
        state = ScreenState()
        actions = agent._basic_planning("do something weird", state)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.ERROR
        
    def test_execute_navigate_action(self, agent):
        with patch('webbrowser.open') as mock_browser:
            action = Action(type=ActionType.NAVIGATE, value="https://example.com")
            success, message = agent._execute_action(action)
            assert success == True
            # Browser should have been called (either via browser agent or webbrowser)
            assert "Navigate" in message or mock_browser.called
        
    def test_execute_wait_action(self, agent):
        action = Action(type=ActionType.WAIT, value="0.1")
        success, message = agent._execute_action(action)
        assert success == True
        assert "Waited" in message
        
    def test_execute_complete_action(self, agent):
        action = Action(type=ActionType.COMPLETE)
        success, message = agent._execute_action(action)
        assert success == True
        assert "completed" in message.lower()
        
    def test_execute_error_action(self, agent):
        action = Action(type=ActionType.ERROR, reasoning="Test error")
        success, message = agent._execute_action(action)
        assert success == False
        assert message == "Test error"
        
    def test_verify_action(self, agent):
        action = Action(type=ActionType.WAIT)
        before_state = ScreenState()
        
        with patch.object(agent, '_capture_screen_state', return_value=ScreenState()):
            verified, after_state = agent._verify_action(action, before_state)
            assert verified == True
            assert isinstance(after_state, ScreenState)
            
    def test_stop(self, agent):
        agent.is_running = True
        agent.stop()
        assert agent.is_running == False


class TestCometAgentAsync:
    """Test async methods of CometAgent"""
    
    @pytest.fixture
    def agent(self):
        agent = CometAgent(ai_router=None, headless=True)
        yield agent
        agent.cleanup()
        
    @pytest.mark.asyncio
    async def test_execute_task_simple(self, agent):
        # Mock components
        with patch.object(agent, '_capture_screen_state', return_value=ScreenState()):
            with patch.object(agent, '_basic_planning') as mock_plan:
                mock_plan.return_value = [Action(type=ActionType.COMPLETE)]
                
                result = await agent.execute_task("test task", max_steps=5)
                assert result.success == True
                assert result.steps_taken > 0
                
    @pytest.mark.asyncio
    async def test_execute_task_error(self, agent):
        with patch.object(agent, '_capture_screen_state', return_value=ScreenState()):
            with patch.object(agent, '_basic_planning') as mock_plan:
                mock_plan.return_value = [
                    Action(type=ActionType.ERROR, reasoning="Test error")
                ]
                
                result = await agent.execute_task("fail task", max_steps=5)
                assert result.success == False
                assert "error" in result.message.lower() or result.error is not None
                
    @pytest.mark.asyncio
    async def test_execute_task_max_steps(self, agent):
        with patch.object(agent, '_capture_screen_state', return_value=ScreenState()):
            with patch.object(agent, '_basic_planning') as mock_plan:
                # Return thinking action that never completes
                mock_plan.return_value = [Action(type=ActionType.THINK)]
                
                result = await agent.execute_task("infinite task", max_steps=3)
                assert result.success == False
                assert "max steps" in result.message.lower()


class TestCometAgentWithAI:
    """Test CometAgent with AI router"""
    
    @pytest.fixture
    def mock_ai_router(self):
        router = Mock()
        router.route_query = Mock(return_value='{"action": "complete", "reasoning": "Done"}')
        return router
        
    @pytest.fixture
    def agent_with_ai(self, mock_ai_router):
        agent = CometAgent(ai_router=mock_ai_router, headless=True)
        yield agent
        agent.cleanup()
        
    def test_think_with_ai(self, agent_with_ai, mock_ai_router):
        state = ScreenState(visible_text="Test page", current_url="https://test.com")
        actions = agent_with_ai._think("do something", state, [])
        
        # Should have called the AI router
        mock_ai_router.route_query.assert_called_once()
        assert len(actions) >= 1
        
    def test_parse_ai_response_valid(self, agent_with_ai):
        response = '{"action": "click", "target": "button", "reasoning": "Need to click"}'
        actions = agent_with_ai._parse_ai_response(response)
        assert len(actions) == 1
        assert actions[0].type == ActionType.CLICK
        assert actions[0].target == "button"
        
    def test_parse_ai_response_invalid(self, agent_with_ai):
        response = "This is not JSON"
        actions = agent_with_ai._parse_ai_response(response)
        assert len(actions) >= 1
        assert actions[0].type == ActionType.THINK
        
    def test_build_ai_context(self, agent_with_ai):
        state = ScreenState(
            current_url="https://test.com",
            active_window="Chrome",
            visible_text="Some text here"
        )
        history = [
            Action(type=ActionType.NAVIGATE, value="https://test.com")
        ]
        
        context = agent_with_ai._build_ai_context("test task", state, history)
        assert context["task"] == "test task"
        assert context["current_state"]["url"] == "https://test.com"
        assert context["history_length"] == 1


class TestQuickActions:
    """Test QuickActions helper class"""
    
    @pytest.fixture
    def quick_actions(self):
        agent = CometAgent(ai_router=None, headless=True)
        qa = QuickActions(agent)
        yield qa
        agent.cleanup()
        
    @pytest.mark.asyncio
    async def test_google_search(self, quick_actions):
        with patch.object(quick_actions.agent, 'execute_task') as mock_exec:
            mock_exec.return_value = TaskResult(success=True, message="Done", steps_taken=1)
            
            result = await quick_actions.google_search("python")
            mock_exec.assert_called_once()
            assert "google" in str(mock_exec.call_args).lower()
            
    @pytest.mark.asyncio
    async def test_open_website(self, quick_actions):
        with patch.object(quick_actions.agent, 'execute_task') as mock_exec:
            mock_exec.return_value = TaskResult(success=True, message="Done", steps_taken=1)
            
            result = await quick_actions.open_website("example.com")
            mock_exec.assert_called_once()
            assert "https://example.com" in str(mock_exec.call_args)


class TestCreateCometAgent:
    """Test factory function"""
    
    def test_create_without_router(self):
        agent = create_comet_agent()
        assert agent is not None
        assert agent.ai_router is None
        agent.cleanup()
        
    def test_create_with_router(self):
        mock_router = Mock()
        agent = create_comet_agent(ai_router=mock_router)
        assert agent.ai_router == mock_router
        agent.cleanup()


class TestCometAgentSync:
    """Test synchronous wrapper"""
    
    def test_execute_task_sync(self):
        agent = CometAgent(ai_router=None, headless=True)
        
        with patch.object(agent, '_capture_screen_state', return_value=ScreenState()):
            with patch.object(agent, '_basic_planning') as mock_plan:
                mock_plan.return_value = [Action(type=ActionType.COMPLETE)]
                
                result = agent.execute_task_sync("test sync", max_steps=3)
                assert result.success == True
                
        agent.cleanup()
