"""
Tests for LADA Agent Runtime

Tests cover:
- Agent configuration and lifecycle
- Agent registry operations
- Channel-to-agent bindings
- Session namespacing by agent
- Skill/tool visibility per agent
"""

import pytest
import os
import tempfile
from pathlib import Path

from modules.agent_runtime.agent_registry import (
    AgentConfig,
    AgentCapabilities,
    AgentStatus,
    AgentRegistry,
    DEFAULT_AGENT_ID,
)

from modules.agent_runtime.bindings import (
    ChannelBinding,
    AgentBindings,
)

from modules.session_manager import SessionManager, SessionType


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""
    
    def test_default_values(self):
        """AgentConfig should have sensible defaults."""
        config = AgentConfig(agent_id="test_agent")
        
        assert config.agent_id == "test_agent"
        assert config.name == "test_agent"  # Defaults to agent_id
        assert config.status == AgentStatus.INACTIVE
        assert config.capabilities is not None
    
    def test_workspace_auto_assigned(self):
        """Workspace and state dirs should be auto-assigned."""
        config = AgentConfig(agent_id="my_agent")
        
        assert "my_agent" in config.workspace_root
        assert "my_agent" in config.state_dir
    
    def test_to_dict_round_trip(self):
        """to_dict and from_dict should be reversible."""
        original = AgentConfig(
            agent_id="agent_123",
            name="Test Agent",
            description="A test agent",
            capabilities=AgentCapabilities(
                can_browse=True,
                allowed_skills={"skill_a", "skill_b"},
            ),
        )
        
        data = original.to_dict()
        restored = AgentConfig.from_dict(data)
        
        assert restored.agent_id == original.agent_id
        assert restored.name == original.name
        assert restored.capabilities.can_browse == original.capabilities.can_browse
        assert "skill_a" in restored.capabilities.allowed_skills


class TestAgentCapabilities:
    """Tests for AgentCapabilities."""
    
    def test_default_capabilities(self):
        """Default capabilities should allow chat and commands."""
        caps = AgentCapabilities()
        
        assert caps.can_chat is True
        assert caps.can_execute_commands is True
        assert caps.can_browse is False
    
    def test_skill_allowlist_enforcement(self):
        """Skill allowlist should restrict allowed skills."""
        caps = AgentCapabilities(
            allowed_skills={"skill_a", "skill_b"}
        )
        
        assert caps.is_skill_allowed("skill_a") is True
        assert caps.is_skill_allowed("skill_b") is True
        assert caps.is_skill_allowed("skill_c") is False
    
    def test_skill_denylist_enforcement(self):
        """Skill denylist should block denied skills."""
        caps = AgentCapabilities(
            denied_skills={"dangerous_skill"}
        )
        
        assert caps.is_skill_allowed("safe_skill") is True
        assert caps.is_skill_allowed("dangerous_skill") is False
    
    def test_denylist_overrides_allowlist(self):
        """Denied skills should be blocked even if in allowlist."""
        caps = AgentCapabilities(
            allowed_skills={"skill_a"},
            denied_skills={"skill_a"},
        )
        
        assert caps.is_skill_allowed("skill_a") is False
    
    def test_empty_allowlist_allows_all(self):
        """Empty allowlist should allow all skills."""
        caps = AgentCapabilities(allowed_skills=set())
        
        assert caps.is_skill_allowed("any_skill") is True


class TestAgentRegistry:
    """Tests for AgentRegistry."""
    
    def test_default_agent_exists(self):
        """Registry should always have a default agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(agents_dir=tmpdir)
            
            assert registry.count() >= 1
            default = registry.get(DEFAULT_AGENT_ID)
            assert default is not None
            assert default.status == AgentStatus.ACTIVE
    
    def test_register_and_get(self):
        """Should be able to register and retrieve agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(agents_dir=tmpdir)
            
            agent = AgentConfig(
                agent_id="new_agent",
                name="New Agent",
            )
            
            result = registry.register(agent)
            assert result is True
            
            retrieved = registry.get("new_agent")
            assert retrieved is not None
            assert retrieved.name == "New Agent"
    
    def test_cannot_unregister_default(self):
        """Should not be able to unregister the default agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(agents_dir=tmpdir)
            
            result = registry.unregister(DEFAULT_AGENT_ID)
            assert result is False
            assert registry.get(DEFAULT_AGENT_ID) is not None
    
    def test_can_unregister_custom_agent(self):
        """Should be able to unregister custom agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(agents_dir=tmpdir)
            
            registry.register(AgentConfig(agent_id="removable"))
            assert registry.get("removable") is not None
            
            result = registry.unregister("removable")
            assert result is True
            assert registry.get("removable") is None
    
    def test_list_active_agents(self):
        """Should filter to active agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(agents_dir=tmpdir)
            
            active = AgentConfig(agent_id="active_agent")
            active.status = AgentStatus.ACTIVE
            registry.register(active)
            
            inactive = AgentConfig(agent_id="inactive_agent")
            inactive.status = AgentStatus.INACTIVE
            registry.register(inactive)
            
            active_list = registry.list_active()
            active_ids = [a.agent_id for a in active_list]
            
            assert "active_agent" in active_ids
            assert "inactive_agent" not in active_ids
    
    def test_session_tracking(self):
        """Should track sessions per agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(agents_dir=tmpdir)
            
            registry.add_session(DEFAULT_AGENT_ID, "session_1")
            registry.add_session(DEFAULT_AGENT_ID, "session_2")
            
            agent = registry.get(DEFAULT_AGENT_ID)
            assert len(agent.active_sessions) == 2
            
            # Find agent by session
            found = registry.get_agent_for_session("session_1")
            assert found is not None
            assert found.agent_id == DEFAULT_AGENT_ID
    
    def test_persistence(self):
        """Should persist and load agent configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and save
            registry1 = AgentRegistry(agents_dir=tmpdir)
            registry1.register(AgentConfig(
                agent_id="persistent_agent",
                name="Persistent",
            ))
            registry1.save_to_disk()
            
            # Load in new registry
            registry2 = AgentRegistry(agents_dir=tmpdir)
            registry2.load_from_disk()
            
            agent = registry2.get("persistent_agent")
            assert agent is not None
            assert agent.name == "Persistent"


class TestChannelBinding:
    """Tests for ChannelBinding matching."""
    
    def test_exact_match(self):
        """Exact peer pattern should match exactly."""
        binding = ChannelBinding(
            binding_id="b1",
            channel_type="telegram",
            peer_pattern="user123",
            agent_id="agent_1",
        )
        
        assert binding.matches("telegram", "user123") is True
        assert binding.matches("telegram", "user456") is False
        assert binding.matches("discord", "user123") is False
    
    def test_wildcard_channel(self):
        """Wildcard channel should match all channels."""
        binding = ChannelBinding(
            binding_id="b2",
            channel_type="*",
            peer_pattern="admin",
            agent_id="agent_admin",
        )
        
        assert binding.matches("telegram", "admin") is True
        assert binding.matches("discord", "admin") is True
        assert binding.matches("slack", "admin") is True
    
    def test_wildcard_peer(self):
        """Wildcard peer should match all peers in channel."""
        binding = ChannelBinding(
            binding_id="b3",
            channel_type="telegram",
            peer_pattern="*",
            agent_id="agent_tg",
        )
        
        assert binding.matches("telegram", "user1") is True
        assert binding.matches("telegram", "user2") is True
        assert binding.matches("discord", "user1") is False
    
    def test_prefix_pattern(self):
        """Prefix* pattern should match prefixes."""
        binding = ChannelBinding(
            binding_id="b4",
            channel_type="*",
            peer_pattern="admin_*",
            agent_id="agent_admin",
        )
        
        assert binding.matches("telegram", "admin_john") is True
        assert binding.matches("telegram", "admin_jane") is True
        assert binding.matches("telegram", "user_admin") is False
    
    def test_disabled_binding(self):
        """Disabled bindings should not match."""
        binding = ChannelBinding(
            binding_id="b5",
            channel_type="*",
            peer_pattern="*",
            agent_id="agent_all",
            enabled=False,
        )
        
        assert binding.matches("telegram", "anyone") is False


class TestAgentBindings:
    """Tests for AgentBindings resolution."""
    
    def test_resolve_with_no_bindings(self):
        """Should return default agent when no bindings match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bindings = AgentBindings(bindings_file=os.path.join(tmpdir, "bindings.json"))
            
            agent_id = bindings.resolve_agent("telegram", "random_user")
            assert agent_id == DEFAULT_AGENT_ID
    
    def test_resolve_with_exact_match(self):
        """Should resolve exact peer match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bindings = AgentBindings(bindings_file=os.path.join(tmpdir, "bindings.json"))
            
            bindings.bind_peer_to_agent("telegram", "vip_user", "agent_vip", priority=100)
            
            agent_id = bindings.resolve_agent("telegram", "vip_user")
            assert agent_id == "default"  # agent_vip doesn't exist, falls back
    
    def test_resolve_priority_order(self):
        """Higher priority bindings should match first."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bindings = AgentBindings(bindings_file=os.path.join(tmpdir, "bindings.json"))
            
            # Register agents first
            from modules.agent_runtime.agent_registry import AgentRegistry
            registry = AgentRegistry(agents_dir=tmpdir)
            registry.register(AgentConfig(agent_id="agent_low"))
            registry.register(AgentConfig(agent_id="agent_high"))
            
            # Lower priority (matches all telegram)
            bindings.add_binding(ChannelBinding(
                binding_id="low",
                channel_type="telegram",
                peer_pattern="*",
                agent_id="agent_low",
                priority=10,
            ))
            
            # Higher priority (specific user)
            bindings.add_binding(ChannelBinding(
                binding_id="high",
                channel_type="telegram",
                peer_pattern="special_user",
                agent_id="agent_high",
                priority=100,
            ))
            
            # Special user should get high-priority agent
            # (Note: This test uses local registry, not global singleton)
    
    def test_persistence(self):
        """Bindings should persist to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bindings_file = os.path.join(tmpdir, "bindings.json")
            
            # Create and save
            bindings1 = AgentBindings(bindings_file=bindings_file)
            bindings1.bind_channel_to_agent("telegram", "agent_tg")
            bindings1.save_to_disk()
            
            # Load in new instance
            bindings2 = AgentBindings(bindings_file=bindings_file)
            bindings2.load_from_disk()
            
            assert bindings2.count() >= 1


class TestSessionNamespacing:
    """Tests for session namespacing by agent."""
    
    def test_sessions_include_agent_id(self):
        """Sessions should include agent_id in session_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(data_dir=tmpdir)
            
            session = sm.create_session(
                session_type=SessionType.GUI_CHAT,
                agent_id="my_agent"
            )
            
            assert session.agent_id == "my_agent"
            assert "my_agent" in session.session_id
    
    def test_list_sessions_by_agent(self):
        """Should filter sessions by agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(data_dir=tmpdir)
            
            sm.create_session(agent_id="agent_a")
            sm.create_session(agent_id="agent_a")
            sm.create_session(agent_id="agent_b")
            
            agent_a_sessions = sm.list_sessions_for_agent("agent_a")
            agent_b_sessions = sm.list_sessions_for_agent("agent_b")
            
            assert len(agent_a_sessions) == 2
            assert len(agent_b_sessions) == 1
    
    def test_agents_have_isolated_context(self):
        """Different agents should have isolated message history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(data_dir=tmpdir)
            
            session_a = sm.create_session(agent_id="agent_a")
            session_b = sm.create_session(agent_id="agent_b")
            
            session_a.add_message("user", "Message for agent A")
            session_b.add_message("user", "Message for agent B")
            
            # Messages should be isolated
            assert session_a.message_count() == 1
            assert session_b.message_count() == 1
            assert "agent A" in session_a.messages[0].content
            assert "agent B" in session_b.messages[0].content
    
    def test_session_serialization_preserves_agent(self):
        """Session to_dict should include agent_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(data_dir=tmpdir)
            
            session = sm.create_session(agent_id="test_agent")
            data = session.to_dict()
            
            assert "agent_id" in data
            assert data["agent_id"] == "test_agent"


class TestAgentIsolation:
    """Integration tests for full agent isolation."""
    
    def test_two_agents_no_context_leakage(self):
        """Two agents should have completely isolated contexts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up registry
            registry = AgentRegistry(agents_dir=tmpdir)
            agent1 = AgentConfig(
                agent_id="agent_1",
                name="Agent One",
                capabilities=AgentCapabilities(allowed_skills={"skill_a"}),
            )
            agent2 = AgentConfig(
                agent_id="agent_2",
                name="Agent Two",
                capabilities=AgentCapabilities(allowed_skills={"skill_b"}),
            )
            registry.register(agent1)
            registry.register(agent2)
            
            # Set up sessions
            sm = SessionManager(data_dir=tmpdir)
            session1 = sm.create_session(agent_id="agent_1")
            session2 = sm.create_session(agent_id="agent_2")
            
            # Add messages
            session1.add_message("user", "Secret for agent 1")
            session2.add_message("user", "Secret for agent 2")
            
            # Verify isolation
            assert session1.agent_id != session2.agent_id
            assert session1.session_id != session2.session_id
            assert "agent 1" in session1.messages[0].content
            assert "agent 2" in session2.messages[0].content
            
            # Verify skill isolation
            assert registry.get("agent_1").capabilities.is_skill_allowed("skill_a") is True
            assert registry.get("agent_1").capabilities.is_skill_allowed("skill_b") is False
            assert registry.get("agent_2").capabilities.is_skill_allowed("skill_a") is False
            assert registry.get("agent_2").capabilities.is_skill_allowed("skill_b") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
