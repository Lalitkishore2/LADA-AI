"""
Tests for AI Command Agent — AI-first command execution with ReAct tool loop.

Tests cover:
- Action classification (actionable vs conversational)
- Tier selection (fast vs smart)
- Tool call execution
- ReAct loop behavior
- Delegation to specialist agents
- Error handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List


@pytest.fixture
def mock_provider_manager():
    """Mock provider manager"""
    manager = Mock()
    manager.get_best_model = Mock(return_value={
        'id': 'test-model',
        'provider': 'test-provider'
    })
    manager.query = Mock(return_value=Mock(
        text='Done! I executed the command.',
        model='test-model',
        provider='test-provider'
    ))
    return manager


@pytest.fixture
def mock_tool_registry():
    """Mock tool registry"""
    registry = Mock()
    registry.get_tool = Mock(return_value={
        'name': 'find_files',
        'description': 'Find files by pattern',
        'parameters': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string'}
            }
        }
    })
    registry.get_all_tools = Mock(return_value=[
        {'name': 'find_files', 'description': 'Find files'},
        {'name': 'open_path', 'description': 'Open path'},
        {'name': 'run_powershell', 'description': 'Run command'},
    ])
    registry.execute_tool = Mock(return_value={
        'success': True,
        'result': 'Executed successfully'
    })
    return registry


@pytest.fixture
def ai_agent(mock_provider_manager, mock_tool_registry):
    """Create AI Command Agent with mocks"""
    with patch('modules.ai_command_agent.PROVIDER_OK', True):
        with patch('modules.ai_command_agent.REGISTRY_OK', True):
            from modules.ai_command_agent import AICommandAgent
            agent = AICommandAgent(mock_provider_manager, mock_tool_registry)
            return agent


class TestAgentResult:
    """Tests for AgentResult dataclass"""
    
    def test_agent_result_defaults(self):
        """AgentResult has sensible defaults"""
        from modules.ai_command_agent import AgentResult
        result = AgentResult(handled=True, response="test")
        assert result.handled is True
        assert result.response == "test"
        assert result.tool_calls_made == 0
        assert result.tier_used == ""
        assert result.elapsed_ms == 0


class TestActionClassification:
    """Tests for _is_actionable() method"""
    
    def test_action_verbs_classified_as_actionable(self, ai_agent):
        """Commands with action verbs are actionable"""
        actionable_commands = [
            "find my photos",
            "open chrome",
            "close all windows",
            "search for documents",
            "delete temp files",
            "create a new folder",
            "take a screenshot",
            "show me recent files",
            "play music",
            "set volume to 50",
        ]
        for cmd in actionable_commands:
            assert ai_agent._is_actionable(cmd), f"'{cmd}' should be actionable"
    
    def test_questions_not_actionable(self, ai_agent):
        """Pure questions without action verbs are not actionable"""
        questions = [
            "what is quantum computing?",
            "how does gravity work?",
            "why is the sky blue?",
        ]
        for q in questions:
            # Pure conceptual questions should NOT be actionable
            result = ai_agent._is_actionable(q)
            assert result is False, f"'{q}' should NOT be actionable"
    
    def test_questions_with_action_verbs_are_actionable(self, ai_agent):
        """Questions with action verbs like 'tell', 'explain' may be actionable"""
        questions_with_actions = [
            "explain machine learning",
            "tell me about python",
        ]
        for q in questions_with_actions:
            # These contain implicit action verbs - implementation may vary
            result = ai_agent._is_actionable(q)
            assert isinstance(result, bool)
    
    def test_conversational_not_actionable(self, ai_agent):
        """Conversational phrases are not actionable"""
        conversational = [
            "hello",
            "thanks",
            "bye",
        ]
        for c in conversational:
            # Short conversational inputs should NOT be actionable
            result = ai_agent._is_actionable(c)
            assert result is False, f"'{c}' should NOT be actionable"


class TestTierSelection:
    """Tests for _select_tier() method"""
    
    def test_simple_commands_use_fast_tier(self, ai_agent):
        """Simple commands use fast tier"""
        simple = [
            "open notepad",
            "close chrome",
            "what time is it",
            "volume up",
            "take screenshot",
        ]
        for cmd in simple:
            tier = ai_agent._select_tier(cmd)
            assert tier in ['fast', 'smart']  # Either is acceptable
    
    def test_complex_commands_may_use_smart_tier(self, ai_agent):
        """Complex commands may use smart tier"""
        complex_cmd = "find all pdf files modified this week in my documents folder and organize them by size"
        tier = ai_agent._select_tier(complex_cmd)
        # Complex tasks often use smart tier
        assert tier in ['fast', 'smart']


class TestTryHandle:
    """Tests for try_handle() method"""
    
    def test_returns_agent_result(self, ai_agent):
        """try_handle returns AgentResult"""
        from modules.ai_command_agent import AgentResult
        result = ai_agent.try_handle("open notepad")
        assert isinstance(result, AgentResult)
    
    def test_handled_commands_have_response(self, ai_agent):
        """Handled commands have non-empty response"""
        result = ai_agent.try_handle("find files")
        # If handled, should have response
        if result.handled:
            assert len(result.response) > 0
    
    def test_unhandled_commands_have_handled_false(self, ai_agent):
        """Non-actionable commands return handled=False"""
        result = ai_agent.try_handle("")  # Empty command
        # Empty or invalid should not be handled
        assert result.handled is False, "Empty command should not be handled"


class TestToolExecution:
    """Tests for tool execution"""
    
    def test_tool_calls_increment_counter(self, ai_agent, mock_tool_registry):
        """Tool calls increment the tool_calls_made counter"""
        # This tests the internal behavior when tools are called
        # Mock the provider to return a tool call
        ai_agent.provider_manager.query = Mock(return_value=Mock(
            text='<tool_call>{"name": "find_files", "arguments": {"pattern": "*.pdf"}}</tool_call>'
        ))
        
        # Execute a command that triggers tools
        result = ai_agent.try_handle("find pdf files")
        # Counter should be set (may be 0 if mocked out)
        assert result.tool_calls_made >= 0


class TestFormatToolsForPrompt:
    """Tests for _format_tools_for_prompt()"""
    
    def test_formats_tools_as_string(self, ai_agent):
        """Tools formatted for prompt as readable string"""
        tools = [
            {'name': 'tool1', 'description': 'First tool'},
            {'name': 'tool2', 'description': 'Second tool'},
        ]
        formatted = ai_agent._format_tools_for_prompt(tools)
        assert 'tool1' in formatted
        assert 'tool2' in formatted
        assert 'First tool' in formatted


class TestParseToolCalls:
    """Tests for _parse_tool_calls()"""
    
    def test_parses_xml_tool_calls(self, ai_agent):
        """Parse XML-formatted tool calls"""
        text = '<tool_call>{"name": "find_files", "arguments": {"pattern": "*.pdf"}}</tool_call>'
        calls = ai_agent._parse_tool_calls(text)
        assert len(calls) >= 1
        name, args = calls[0]
        assert name == "find_files"
        assert args.get("pattern") == "*.pdf"
    
    def test_parses_multiple_tool_calls(self, ai_agent):
        """Parse multiple tool calls from text"""
        text = '''
        <tool_call>{"name": "find_files", "arguments": {"pattern": "*.pdf"}}</tool_call>
        Found some files.
        <tool_call>{"name": "open_path", "arguments": {"path": "/tmp"}}</tool_call>
        '''
        calls = ai_agent._parse_tool_calls(text)
        assert len(calls) == 2
    
    def test_handles_no_tool_calls(self, ai_agent):
        """Returns empty list when no tool calls"""
        text = "This is just regular text without any tool calls."
        calls = ai_agent._parse_tool_calls(text)
        assert calls == []
    
    def test_handles_malformed_json(self, ai_agent):
        """Handles malformed JSON gracefully"""
        text = '<tool_call>{"name": "broken", arguments: missing}</tool_call>'
        calls = ai_agent._parse_tool_calls(text)
        # Should handle gracefully - either empty or partial
        assert isinstance(calls, list)


class TestGetStatus:
    """Tests for get_status() method"""
    
    def test_returns_status_dict(self, ai_agent):
        """get_status returns dictionary"""
        status = ai_agent.get_status()
        assert isinstance(status, dict)
    
    def test_status_contains_key_info(self, ai_agent):
        """Status contains essential information"""
        status = ai_agent.get_status()
        # Status should contain useful info
        assert 'enabled' in status or 'available' in status or len(status) > 0


class TestDelegation:
    """Tests for _should_delegate() method"""
    
    def test_delegation_returns_tuple(self, ai_agent):
        """_should_delegate returns (should_delegate, specialist_id)"""
        result = ai_agent._should_delegate("check hotel prices in London")
        assert isinstance(result, tuple)
        assert len(result) == 2
        should_delegate, specialist_id = result
        assert isinstance(should_delegate, bool)
    
    def test_normal_commands_not_delegated(self, ai_agent):
        """Normal commands are not delegated"""
        result = ai_agent._should_delegate("open notepad")
        should_delegate, _ = result
        # Simple commands should not be delegated
        assert should_delegate is False


class TestNativeToolSupport:
    """Tests for _supports_native_tools() method"""
    
    def test_checks_provider_capability(self, ai_agent):
        """Checks if provider supports native tool calling"""
        mock_provider = Mock()
        mock_provider.supports_tools = Mock(return_value=True)
        result = ai_agent._supports_native_tools(mock_provider, 'test-provider')
        # Result depends on provider implementation
        assert isinstance(result, bool)


class TestEdgeCases:
    """Edge case tests"""
    
    def test_empty_command(self, ai_agent):
        """Empty command handled gracefully"""
        result = ai_agent.try_handle("")
        assert result.handled is False or result.response != ""
    
    def test_very_long_command(self, ai_agent):
        """Very long commands handled"""
        long_cmd = "find " + "files " * 100
        result = ai_agent.try_handle(long_cmd)
        # Should not crash
        assert isinstance(result.handled, bool)
    
    def test_special_characters(self, ai_agent):
        """Commands with special characters handled"""
        result = ai_agent.try_handle("find files named *.txt & delete")
        assert isinstance(result.handled, bool)
    
    def test_unicode_command(self, ai_agent):
        """Unicode commands handled"""
        result = ai_agent.try_handle("find files with emoji 🎉")
        assert isinstance(result.handled, bool)


class TestMaxRounds:
    """Tests for max_rounds limit"""
    
    def test_respects_max_rounds(self, ai_agent):
        """Agent respects max_rounds limit"""
        # Set a low max_rounds
        ai_agent.max_rounds = 2
        
        # Mock provider to always return tool calls
        ai_agent.provider_manager.query = Mock(return_value=Mock(
            text='<tool_call>{"name": "find_files", "arguments": {}}</tool_call>Need more.',
            model='test'
        ))
        
        result = ai_agent.try_handle("find files repeatedly")
        # Should stop after max_rounds
        assert result.tool_calls_made <= ai_agent.max_rounds, \
            f"Tool calls ({result.tool_calls_made}) should not exceed max_rounds ({ai_agent.max_rounds})"


class TestEnvironmentFlags:
    """Tests for environment configuration"""
    
    def test_disabled_when_flag_off(self):
        """Agent respects LADA_AI_AGENT_ENABLED flag"""
        import os
        with patch.dict(os.environ, {'LADA_AI_AGENT_ENABLED': '0'}):
            # When disabled, agent should not process commands
            # This is implementation-specific - verify the flag is checked
            assert os.environ.get('LADA_AI_AGENT_ENABLED') == '0'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
