"""
Tests for LADA Subagents and ACP Bridge

Tests subagent runtime, limits, and ACP protocol.
"""

import os
import sys
import json
import pytest
import asyncio
import tempfile
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.subagents.runtime import (
    SubagentConfig,
    SubagentState,
    SubagentStatus,
    SubagentResult,
    SubagentRuntime,
)
from modules.subagents.limits import (
    SubagentLimits,
    LimitExceeded,
    DepthLimitExceeded,
    ConcurrencyLimitExceeded,
    TimeoutLimitExceeded,
    TokenLimitExceeded,
    CostLimitExceeded,
    LimitTracker,
)
from modules.acp_bridge.protocol import (
    ACPRequest,
    ACPResponse,
    ACPNotification,
    ACPError,
    ACPErrorCode,
    ACPMethod,
    ACPContext,
    ACPToolDefinition,
    ACPChatMessage,
)
from modules.acp_bridge.server import (
    ACPSession,
    ACPMessage,
    ACPMessageType,
    ACPServer,
    SessionStatus,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def subagent_runtime():
    """Create a SubagentRuntime for tests."""
    runtime = SubagentRuntime(
        max_depth=3,
        max_concurrent=5,
        max_total=20,
    )
    yield runtime
    runtime.shutdown()


@pytest.fixture
def acp_server():
    """Create an ACPServer for tests."""
    return ACPServer(
        session_ttl=300,
        max_sessions=10,
    )


# ============================================================================
# Subagent Config Tests
# ============================================================================

class TestSubagentConfig:
    """Tests for SubagentConfig."""
    
    def test_config_defaults(self):
        """Test default config values."""
        config = SubagentConfig(
            agent_type="research",
            task_description="Find information",
        )
        
        assert config.timeout_seconds == 300
        assert config.max_tokens == 4096
        assert config.model_tier == "balanced"
        assert config.allow_subagents is True
    
    def test_config_serialization(self):
        """Test config serialization."""
        config = SubagentConfig(
            agent_type="code",
            task_description="Write tests",
            timeout_seconds=120,
            tools=["grep", "view"],
        )
        
        data = config.to_dict()
        
        assert data["agent_type"] == "code"
        assert data["timeout_seconds"] == 120
        assert "grep" in data["tools"]


# ============================================================================
# Subagent Result Tests
# ============================================================================

class TestSubagentResult:
    """Tests for SubagentResult."""
    
    def test_success_result(self):
        """Test successful result."""
        result = SubagentResult(
            success=True,
            output="Task completed",
            tokens_used=500,
            duration_ms=1500,
        )
        
        assert result.success
        assert result.error is None
    
    def test_failure_result(self):
        """Test failed result."""
        result = SubagentResult(
            success=False,
            error="Something went wrong",
            error_type="RuntimeError",
        )
        
        assert not result.success
        assert result.error_type == "RuntimeError"
    
    def test_result_serialization(self):
        """Test result serialization."""
        result = SubagentResult(
            success=True,
            output="Done",
            data={"key": "value"},
        )
        
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["data"]["key"] == "value"


# ============================================================================
# Subagent Runtime Tests
# ============================================================================

class TestSubagentRuntime:
    """Tests for SubagentRuntime."""
    
    def test_spawn_subagent(self, subagent_runtime):
        """Test spawning a subagent."""
        config = SubagentConfig(
            agent_type="test",
            task_description="Test task",
            timeout_seconds=5,
        )
        
        subagent_id = subagent_runtime.spawn(config)
        
        assert subagent_id.startswith("sub_")
        
        state = subagent_runtime.get(subagent_id)
        assert state is not None
        assert state.config.agent_type == "test"
    
    def test_spawn_with_parent(self, subagent_runtime):
        """Test spawning nested subagent."""
        # Spawn parent
        parent_config = SubagentConfig(
            agent_type="parent",
            task_description="Parent task",
        )
        parent_id = subagent_runtime.spawn(parent_config)
        
        # Spawn child
        child_config = SubagentConfig(
            agent_type="child",
            task_description="Child task",
            parent_id=parent_id,
        )
        child_id = subagent_runtime.spawn(child_config)
        
        parent = subagent_runtime.get(parent_id)
        child = subagent_runtime.get(child_id)
        
        assert child.depth == 1
        assert child_id in parent.children
    
    def test_depth_limit(self, subagent_runtime):
        """Test depth limit enforcement."""
        # Spawn chain up to limit
        current_id = None
        for i in range(3):  # max_depth=3
            config = SubagentConfig(
                agent_type=f"level-{i}",
                task_description="Task",
                parent_id=current_id,
            )
            current_id = subagent_runtime.spawn(config)
        
        # Next spawn should fail
        with pytest.raises(DepthLimitExceeded):
            subagent_runtime.spawn(SubagentConfig(
                agent_type="too-deep",
                task_description="Task",
                parent_id=current_id,
            ))
    
    def test_concurrency_limit(self, subagent_runtime):
        """Test concurrency limit enforcement."""
        # Mock executor to not complete
        async def slow_executor(config):
            await asyncio.sleep(100)
            return SubagentResult(success=True, output="Done")
        
        subagent_runtime.set_executor(slow_executor)
        
        # Spawn up to limit
        for i in range(5):  # max_concurrent=5
            subagent_runtime.spawn(SubagentConfig(
                agent_type=f"agent-{i}",
                task_description="Task",
            ))
        
        # Wait for spawning to start
        time.sleep(0.1)
        
        # Next spawn should fail
        with pytest.raises(ConcurrencyLimitExceeded):
            subagent_runtime.spawn(SubagentConfig(
                agent_type="too-many",
                task_description="Task",
            ))
    
    def test_cancel_subagent(self, subagent_runtime):
        """Test cancelling a subagent."""
        async def slow_executor(config):
            await asyncio.sleep(100)
            return SubagentResult(success=True, output="Done")
        
        subagent_runtime.set_executor(slow_executor)
        
        subagent_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="cancellable",
            task_description="Task",
        ))
        
        # Wait for spawn
        time.sleep(0.1)
        
        # Cancel
        assert subagent_runtime.cancel(subagent_id)
        
        state = subagent_runtime.get(subagent_id)
        assert state.status == SubagentStatus.CANCELLED
        assert state.result.error == "Cancelled by user"
    
    def test_cancel_with_children(self, subagent_runtime):
        """Test cancelling cascades to children."""
        async def slow_executor(config):
            await asyncio.sleep(100)
            return SubagentResult(success=True, output="Done")
        
        subagent_runtime.set_executor(slow_executor)
        
        # Spawn parent and children
        parent_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="parent",
            task_description="Parent",
        ))
        
        child1_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="child1",
            task_description="Child 1",
            parent_id=parent_id,
        ))
        
        child2_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="child2",
            task_description="Child 2",
            parent_id=parent_id,
        ))
        
        time.sleep(0.1)
        
        # Cancel parent
        subagent_runtime.cancel(parent_id)
        
        # All should be cancelled
        assert subagent_runtime.get(parent_id).status == SubagentStatus.CANCELLED
        assert subagent_runtime.get(child1_id).status == SubagentStatus.CANCELLED
        assert subagent_runtime.get(child2_id).status == SubagentStatus.CANCELLED
    
    def test_list_subagents(self, subagent_runtime):
        """Test listing subagents."""
        for i in range(3):
            subagent_runtime.spawn(SubagentConfig(
                agent_type=f"agent-{i}",
                task_description="Task",
                session_id="session-1",
            ))
        
        all_agents = subagent_runtime.list_subagents()
        assert len(all_agents) == 3
        
        session_agents = subagent_runtime.list_subagents(session_id="session-1")
        assert len(session_agents) == 3
    
    def test_get_tree(self, subagent_runtime):
        """Test getting subagent tree."""
        parent_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="root",
            task_description="Root",
        ))
        
        child_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="child",
            task_description="Child",
            parent_id=parent_id,
        ))
        
        tree = subagent_runtime.get_tree(parent_id)
        
        assert tree["subagent"]["subagent_id"] == parent_id
        assert len(tree["children"]) == 1
        assert tree["children"][0]["subagent"]["subagent_id"] == child_id
    
    def test_cleanup_session(self, subagent_runtime):
        """Test cleaning up session subagents."""
        for i in range(3):
            subagent_runtime.spawn(SubagentConfig(
                agent_type=f"agent-{i}",
                task_description="Task",
                session_id="cleanup-session",
            ))
        
        count = subagent_runtime.cleanup_session("cleanup-session")
        
        assert count == 3
        assert len(subagent_runtime.list_subagents(session_id="cleanup-session")) == 0
    
    def test_context_inheritance(self, subagent_runtime):
        """Test context inheritance from parent."""
        parent_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="parent",
            task_description="Parent",
            context={"key1": "value1"},
        ))
        
        child_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="child",
            task_description="Child",
            parent_id=parent_id,
            context={"key2": "value2"},
            inherit_context=True,
        ))
        
        child = subagent_runtime.get(child_id)
        
        # Should have both parent and child context
        assert child.config.context["key1"] == "value1"
        assert child.config.context["key2"] == "value2"
    
    def test_stats(self, subagent_runtime):
        """Test runtime statistics."""
        subagent_runtime.spawn(SubagentConfig(
            agent_type="test",
            task_description="Task",
            session_id="stats-session",
        ))
        
        stats = subagent_runtime.get_stats()
        
        assert stats["total"] == 1
        assert stats["sessions"] == 1
        assert stats["limits"]["max_depth"] == 3


# ============================================================================
# Limits Tests
# ============================================================================

class TestSubagentLimits:
    """Tests for SubagentLimits."""
    
    def test_limits_defaults(self):
        """Test default limit values."""
        limits = SubagentLimits()
        
        assert limits.max_depth == 5
        assert limits.max_concurrent == 10
        assert limits.default_timeout_seconds == 300
    
    def test_validate_depth(self):
        """Test depth validation."""
        limits = SubagentLimits(max_depth=3)
        
        limits.validate_depth(0)  # OK
        limits.validate_depth(2)  # OK
        
        with pytest.raises(DepthLimitExceeded):
            limits.validate_depth(3)
    
    def test_validate_concurrency(self):
        """Test concurrency validation."""
        limits = SubagentLimits(max_concurrent=5)
        
        limits.validate_concurrency(4)  # OK
        
        with pytest.raises(ConcurrencyLimitExceeded):
            limits.validate_concurrency(5)
    
    def test_validate_timeout(self):
        """Test timeout validation and clamping."""
        limits = SubagentLimits(
            min_timeout_seconds=10,
            max_timeout_seconds=3600,
        )
        
        assert limits.validate_timeout(100) == 100
        assert limits.validate_timeout(5) == 10  # Clamped up
        assert limits.validate_timeout(5000) == 3600  # Clamped down
    
    def test_validate_tokens(self):
        """Test token validation."""
        limits = SubagentLimits(
            max_tokens_per_subagent=1000,
            max_total_tokens_per_session=5000,
        )
        
        limits.validate_tokens(500)  # OK
        limits.validate_tokens(500, session_total=4000)  # OK
        
        with pytest.raises(TokenLimitExceeded):
            limits.validate_tokens(1500)  # Too many per subagent
        
        with pytest.raises(TokenLimitExceeded):
            limits.validate_tokens(500, session_total=4600)  # Would exceed session total
    
    def test_validate_cost(self):
        """Test cost validation."""
        limits = SubagentLimits(max_cost_per_session=10.0)
        
        limits.validate_cost(5.0)  # OK
        limits.validate_cost(9.0, 0.5)  # OK
        
        with pytest.raises(CostLimitExceeded):
            limits.validate_cost(8.0, 3.0)


class TestLimitTracker:
    """Tests for LimitTracker."""
    
    def test_check_can_spawn(self):
        """Test spawn check."""
        limits = SubagentLimits(max_depth=3, max_concurrent=5)
        tracker = LimitTracker(limits)
        
        assert tracker.check_can_spawn("session-1", depth=0)
        assert tracker.check_can_spawn("session-1", depth=2)
        
        with pytest.raises(DepthLimitExceeded):
            tracker.check_can_spawn("session-1", depth=3)
    
    def test_record_spawn_and_complete(self):
        """Test recording spawn and completion."""
        limits = SubagentLimits()
        tracker = LimitTracker(limits)
        
        tracker.record_spawn("session-1", depth=1)
        assert tracker.current_concurrent == 1
        assert tracker.session_totals["session-1"] == 1
        
        tracker.record_complete("session-1", tokens=100, cost=0.01)
        assert tracker.current_concurrent == 0
        assert tracker.session_tokens["session-1"] == 100
        assert tracker.session_costs["session-1"] == 0.01
    
    def test_get_usage(self):
        """Test getting usage stats."""
        limits = SubagentLimits()
        tracker = LimitTracker(limits)
        
        tracker.record_spawn("session-1", depth=2)
        tracker.record_complete("session-1", tokens=500)
        
        usage = tracker.get_usage("session-1")
        
        assert usage["current_depth"] == 2
        assert usage["session"]["tokens"] == 500


# ============================================================================
# ACP Protocol Tests
# ============================================================================

class TestACPProtocol:
    """Tests for ACP protocol types."""
    
    def test_request_serialization(self):
        """Test ACPRequest serialization."""
        request = ACPRequest(
            method="chat/complete",
            params={"message": "Hello"},
            session_id="session-123",
        )
        
        data = request.to_dict()
        
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "chat/complete"
        assert data["params"]["message"] == "Hello"
        assert data["session_id"] == "session-123"
    
    def test_request_deserialization(self):
        """Test ACPRequest deserialization."""
        data = {
            "method": "tool/invoke",
            "id": "req-123",
            "params": {"name": "grep"},
        }
        
        request = ACPRequest.from_dict(data)
        
        assert request.method == "tool/invoke"
        assert request.id == "req-123"
        assert request.params["name"] == "grep"
    
    def test_response_success(self):
        """Test success response."""
        response = ACPResponse.success_response(
            "req-123",
            {"output": "Done"},
            duration_ms=100,
        )
        
        data = response.to_dict()
        
        assert response.success
        assert data["id"] == "req-123"
        assert data["result"]["output"] == "Done"
        assert "error" not in data
    
    def test_response_error(self):
        """Test error response."""
        response = ACPResponse.error_response(
            "req-123",
            ACPErrorCode.METHOD_NOT_FOUND,
            "Method not found",
        )
        
        data = response.to_dict()
        
        assert not response.success
        assert "result" not in data
        assert data["error"]["code"] == ACPErrorCode.METHOD_NOT_FOUND.value
    
    def test_notification(self):
        """Test ACPNotification."""
        notif = ACPNotification(
            method="notify/progress",
            params={"progress": 0.5},
            session_id="session-123",
        )
        
        data = notif.to_dict()
        
        assert data["method"] == "notify/progress"
        assert "id" not in data  # Notifications don't have ID
    
    def test_context(self):
        """Test ACPContext."""
        context = ACPContext(
            workspace_root="/project",
            current_file="/project/main.py",
            language="python",
        )
        
        data = context.to_dict()
        restored = ACPContext.from_dict(data)
        
        assert restored.workspace_root == "/project"
        assert restored.language == "python"
    
    def test_tool_definition(self):
        """Test ACPToolDefinition."""
        tool = ACPToolDefinition(
            name="file_read",
            description="Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            requires_approval=True,
        )
        
        data = tool.to_dict()
        
        assert data["name"] == "file_read"
        assert data["requires_approval"] is True
    
    def test_chat_message(self):
        """Test ACPChatMessage."""
        msg = ACPChatMessage(
            role="assistant",
            content="Hello!",
            tool_calls=[{"name": "search", "arguments": "{}"}],
        )
        
        data = msg.to_dict()
        restored = ACPChatMessage.from_dict(data)
        
        assert restored.role == "assistant"
        assert len(restored.tool_calls) == 1


# ============================================================================
# ACP Server Tests
# ============================================================================

class TestACPServer:
    """Tests for ACPServer."""
    
    def test_create_session(self, acp_server):
        """Test session creation."""
        session = acp_server.create_session(
            client_name="test-client",
            client_version="1.0",
        )
        
        assert session.session_id.startswith("acp_")
        assert session.client_name == "test-client"
        assert session.status == SessionStatus.ACTIVE
    
    def test_get_session(self, acp_server):
        """Test getting session."""
        session = acp_server.create_session()
        
        retrieved = acp_server.get_session(session.session_id)
        
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
    
    def test_destroy_session(self, acp_server):
        """Test session destruction."""
        session = acp_server.create_session()
        session_id = session.session_id
        
        assert acp_server.destroy_session(session_id)
        assert acp_server.get_session(session_id) is None
    
    def test_session_limit(self, acp_server):
        """Test max session limit."""
        # Create up to limit
        for i in range(10):  # max_sessions=10
            acp_server.create_session()
        
        # Next should fail
        with pytest.raises(RuntimeError, match="Max sessions"):
            acp_server.create_session()
    
    @pytest.mark.asyncio
    async def test_handle_session_status(self, acp_server):
        """Test session/status request."""
        session = acp_server.create_session(client_name="test")
        
        request = ACPRequest(
            method=ACPMethod.SESSION_STATUS.value,
        )
        
        response = await acp_server.handle_request(session.session_id, request)
        
        assert response.success
        assert response.result["client_name"] == "test"
    
    @pytest.mark.asyncio
    async def test_handle_context_set(self, acp_server):
        """Test context/set request."""
        session = acp_server.create_session()
        
        request = ACPRequest(
            method=ACPMethod.CONTEXT_SET.value,
            params={
                "context": {
                    "workspace_root": "/project",
                    "language": "typescript",
                }
            },
        )
        
        response = await acp_server.handle_request(session.session_id, request)
        
        assert response.success
        
        # Verify context updated
        updated = acp_server.get_session(session.session_id)
        assert updated.context.workspace_root == "/project"
        assert updated.context.language == "typescript"
    
    @pytest.mark.asyncio
    async def test_handle_chat_complete(self, acp_server):
        """Test chat/complete request."""
        # Set custom chat handler
        async def echo_handler(session, message):
            return f"Response: {message}"
        
        acp_server.set_chat_handler(echo_handler)
        
        session = acp_server.create_session()
        
        request = ACPRequest(
            method=ACPMethod.CHAT_COMPLETE.value,
            params={
                "messages": [
                    {"role": "user", "content": "Hello!"}
                ]
            },
        )
        
        response = await acp_server.handle_request(session.session_id, request)
        
        assert response.success
        assert response.result["message"]["content"] == "Response: Hello!"
    
    @pytest.mark.asyncio
    async def test_handle_tool_list(self, acp_server):
        """Test tool/list request."""
        # Register a tool
        acp_server.register_tool(ACPToolDefinition(
            name="test_tool",
            description="A test tool",
        ))
        
        session = acp_server.create_session()
        
        request = ACPRequest(
            method=ACPMethod.TOOL_LIST.value,
        )
        
        response = await acp_server.handle_request(session.session_id, request)
        
        assert response.success
        assert len(response.result["tools"]) == 1
        assert response.result["tools"][0]["name"] == "test_tool"
    
    @pytest.mark.asyncio
    async def test_handle_unknown_method(self, acp_server):
        """Test handling unknown method."""
        session = acp_server.create_session()
        
        request = ACPRequest(
            method="unknown/method",
        )
        
        response = await acp_server.handle_request(session.session_id, request)
        
        assert not response.success
        assert response.error.code == ACPErrorCode.METHOD_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_handle_invalid_session(self, acp_server):
        """Test handling request for invalid session."""
        request = ACPRequest(
            method=ACPMethod.SESSION_STATUS.value,
        )
        
        response = await acp_server.handle_request("nonexistent", request)
        
        assert not response.success
        assert response.error.code == ACPErrorCode.SESSION_NOT_FOUND
    
    def test_register_custom_handler(self, acp_server):
        """Test registering custom handler."""
        async def custom_handler(session, request):
            return ACPResponse.success_response(request.id, {"custom": True})
        
        acp_server.register_handler("custom/method", custom_handler)
        
        # Verify registered
        assert "custom/method" in acp_server._handlers
    
    def test_stats(self, acp_server):
        """Test server statistics."""
        acp_server.create_session()
        acp_server.create_session()
        acp_server.register_tool(ACPToolDefinition(name="tool1", description=""))
        
        stats = acp_server.get_stats()
        
        assert stats["total_sessions"] == 2
        assert stats["active_sessions"] == 2
        assert stats["registered_tools"] == 1


# ============================================================================
# Integration Tests
# ============================================================================

class TestSubagentACPIntegration:
    """Integration tests for subagents and ACP."""
    
    def test_subagent_in_acp_session(self, subagent_runtime, acp_server):
        """Test spawning subagent within ACP session."""
        # Create ACP session
        session = acp_server.create_session()
        
        # Spawn subagent with session ID
        subagent_id = subagent_runtime.spawn(SubagentConfig(
            agent_type="research",
            task_description="Research topic",
            session_id=session.session_id,
        ))
        
        # Verify association
        subagent = subagent_runtime.get(subagent_id)
        assert subagent.config.session_id == session.session_id
        
        # Cleanup session should affect subagents
        subagent_runtime.cleanup_session(session.session_id)
        assert len(subagent_runtime.list_subagents(session_id=session.session_id)) == 0
    
    @pytest.mark.asyncio
    async def test_acp_chat_spawns_subagent(self, subagent_runtime, acp_server):
        """Test ACP chat that triggers subagent spawn."""
        spawned_ids = []
        
        async def research_handler(session, message):
            if "research" in message.lower():
                # Spawn subagent
                subagent_id = subagent_runtime.spawn(SubagentConfig(
                    agent_type="research",
                    task_description=message,
                    session_id=session.session_id,
                ))
                spawned_ids.append(subagent_id)
                return f"Started research: {subagent_id}"
            return "I can help with research."
        
        acp_server.set_chat_handler(research_handler)
        
        session = acp_server.create_session()
        
        request = ACPRequest(
            method=ACPMethod.CHAT_COMPLETE.value,
            params={
                "messages": [
                    {"role": "user", "content": "Research Python async"}
                ]
            },
        )
        
        response = await acp_server.handle_request(session.session_id, request)
        
        assert response.success
        assert len(spawned_ids) == 1
        assert spawned_ids[0] in response.result["message"]["content"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
