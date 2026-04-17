"""
Tests for LADA Plugin Governance

Tests plugin trust, policy, scanner, and skill precedence.
"""

import os
import sys
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.plugins.trust import (
    PluginTrust,
    TrustLevel,
    TrustSource,
    RiskLevel,
    PluginTrustRegistry,
)
from modules.plugins.policy import (
    PluginPolicy,
    PolicyAction,
    PolicyMode,
    PolicyRule,
    PolicyDecision,
    PluginPolicyEngine,
    create_default_rules,
)
from modules.plugins.scanner import (
    ScanResult,
    ScanSeverity,
    ScanCategory,
    ScanFinding,
    PluginScanner,
)
from modules.plugins.skill_precedence import (
    SkillSource,
    SkillEntry,
    SkillPrecedence,
    SkillResolution,
    SkillPrecedenceManager,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def trust_registry(temp_dir):
    """Create a PluginTrustRegistry with temp storage."""
    trust_dir = Path(temp_dir) / "trust"
    plugins_dir = Path(temp_dir) / "plugins"
    trust_dir.mkdir(exist_ok=True)
    plugins_dir.mkdir(exist_ok=True)
    
    return PluginTrustRegistry(
        trust_dir=str(trust_dir),
        plugins_dir=str(plugins_dir),
    )


@pytest.fixture
def policy_engine(temp_dir):
    """Create a PluginPolicyEngine with temp storage."""
    policy_file = Path(temp_dir) / "policy.json"
    
    return PluginPolicyEngine(policy_file=str(policy_file))


@pytest.fixture
def scanner(temp_dir):
    """Create a PluginScanner with temp storage."""
    plugins_dir = Path(temp_dir) / "plugins"
    reports_dir = Path(temp_dir) / "reports"
    plugins_dir.mkdir()
    reports_dir.mkdir()
    
    return PluginScanner(
        plugins_dir=str(plugins_dir),
        reports_dir=str(reports_dir),
    )


@pytest.fixture
def precedence_manager(temp_dir):
    """Create a SkillPrecedenceManager with temp storage."""
    config_file = Path(temp_dir) / "precedence.json"
    skills_dir = Path(temp_dir) / "skills"
    skills_dir.mkdir()
    
    return SkillPrecedenceManager(
        config_file=str(config_file),
        skills_dir=str(skills_dir),
    )


# ============================================================================
# Trust Tests
# ============================================================================

class TestPluginTrust:
    """Tests for PluginTrust data class."""
    
    def test_trust_defaults(self):
        """Test default trust values."""
        trust = PluginTrust(plugin_id="test-plugin")
        
        assert trust.trust_level == TrustLevel.UNVERIFIED
        assert trust.source == TrustSource.UNKNOWN
        assert trust.risk_level == RiskLevel.MEDIUM
        assert not trust.is_trusted
    
    def test_trust_is_trusted(self):
        """Test is_trusted property."""
        assert not PluginTrust(plugin_id="a", trust_level=TrustLevel.UNTRUSTED).is_trusted
        assert not PluginTrust(plugin_id="b", trust_level=TrustLevel.UNVERIFIED).is_trusted
        assert PluginTrust(plugin_id="c", trust_level=TrustLevel.COMMUNITY).is_trusted
        assert PluginTrust(plugin_id="d", trust_level=TrustLevel.VERIFIED).is_trusted
        assert PluginTrust(plugin_id="e", trust_level=TrustLevel.BUILTIN).is_trusted
    
    def test_trust_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        trust = PluginTrust(
            plugin_id="test",
            trust_level=TrustLevel.VERIFIED,
            source=TrustSource.MARKETPLACE,
            risk_level=RiskLevel.LOW,
            content_hash="abc123",
            version="1.2.3",
            author="Test Author",
            capabilities=["cap1", "cap2"],
        )
        
        data = trust.to_dict()
        restored = PluginTrust.from_dict(data)
        
        assert restored.plugin_id == trust.plugin_id
        assert restored.trust_level == trust.trust_level
        assert restored.source == trust.source
        assert restored.content_hash == trust.content_hash
        assert restored.capabilities == trust.capabilities


class TestPluginTrustRegistry:
    """Tests for PluginTrustRegistry."""
    
    def test_register_and_get(self, trust_registry):
        """Test registering and retrieving trust."""
        trust = PluginTrust(
            plugin_id="test-plugin",
            trust_level=TrustLevel.VERIFIED,
            version="1.0.0",
        )
        
        assert trust_registry.register(trust)
        
        retrieved = trust_registry.get("test-plugin")
        assert retrieved is not None
        assert retrieved.trust_level == TrustLevel.VERIFIED
    
    def test_remove(self, trust_registry):
        """Test removing trust entry."""
        trust = PluginTrust(plugin_id="to-remove")
        trust_registry.register(trust)
        
        assert trust_registry.remove("to-remove")
        assert trust_registry.get("to-remove") is None
        assert not trust_registry.remove("nonexistent")
    
    def test_list_all(self, trust_registry):
        """Test listing trust entries."""
        trust_registry.register(PluginTrust(
            plugin_id="p1",
            trust_level=TrustLevel.VERIFIED,
        ))
        trust_registry.register(PluginTrust(
            plugin_id="p2",
            trust_level=TrustLevel.COMMUNITY,
        ))
        trust_registry.register(PluginTrust(
            plugin_id="p3",
            trust_level=TrustLevel.VERIFIED,
        ))
        
        all_entries = trust_registry.list_all()
        assert len(all_entries) == 3
        
        verified_only = trust_registry.list_all(trust_level=TrustLevel.VERIFIED)
        assert len(verified_only) == 2
    
    def test_update_trust_level(self, trust_registry):
        """Test updating trust level."""
        trust_registry.register(PluginTrust(
            plugin_id="upgradable",
            trust_level=TrustLevel.UNVERIFIED,
        ))
        
        updated = trust_registry.update_trust_level(
            "upgradable",
            TrustLevel.VERIFIED,
            verified_by="admin",
        )
        
        assert updated is not None
        assert updated.trust_level == TrustLevel.VERIFIED
        assert updated.verified_by == "admin"
        assert updated.verified_at is not None
    
    def test_compute_plugin_hash(self, trust_registry, temp_dir):
        """Test computing plugin hash."""
        # Create a plugin directory with files
        plugin_dir = Path(temp_dir) / "plugins" / "hash-test"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("print('hello')")
        (plugin_dir / "helper.py").write_text("def helper(): pass")
        
        hash1 = trust_registry.compute_plugin_hash("hash-test")
        assert hash1
        assert len(hash1) == 64  # SHA256 hex
        
        # Same content = same hash
        hash2 = trust_registry.compute_plugin_hash("hash-test")
        assert hash1 == hash2
        
        # Modify file = different hash
        (plugin_dir / "main.py").write_text("print('modified')")
        hash3 = trust_registry.compute_plugin_hash("hash-test")
        assert hash3 != hash1
    
    def test_persistence(self, temp_dir):
        """Test trust data persists across instances."""
        trust_dir = Path(temp_dir) / "trust2"
        plugins_dir = Path(temp_dir) / "plugins2"
        trust_dir.mkdir()
        plugins_dir.mkdir()
        
        # First instance
        reg1 = PluginTrustRegistry(str(trust_dir), str(plugins_dir))
        reg1.register(PluginTrust(
            plugin_id="persistent",
            trust_level=TrustLevel.VERIFIED,
        ))
        
        # Second instance should load persisted data
        reg2 = PluginTrustRegistry(str(trust_dir), str(plugins_dir))
        
        entry = reg2.get("persistent")
        assert entry is not None
        assert entry.trust_level == TrustLevel.VERIFIED


# ============================================================================
# Policy Tests
# ============================================================================

class TestPolicyRule:
    """Tests for PolicyRule."""
    
    def test_rule_matches_pattern(self):
        """Test glob pattern matching."""
        rule = PolicyRule(
            rule_id="test",
            pattern="lada-*",
            action=PolicyAction.ALLOW,
        )
        
        assert rule.matches("lada-plugin")
        assert rule.matches("lada-another")
        assert not rule.matches("other-plugin")
    
    def test_rule_matches_trust_level(self):
        """Test trust level filtering."""
        rule = PolicyRule(
            rule_id="test",
            pattern="*",
            action=PolicyAction.ALLOW,
            trust_levels=[TrustLevel.VERIFIED, TrustLevel.BUILTIN],
        )
        
        assert rule.matches("any", trust_level=TrustLevel.VERIFIED)
        assert rule.matches("any", trust_level=TrustLevel.BUILTIN)
        assert not rule.matches("any", trust_level=TrustLevel.COMMUNITY)
    
    def test_rule_matches_agent(self):
        """Test agent filtering."""
        rule = PolicyRule(
            rule_id="test",
            pattern="*",
            action=PolicyAction.ALLOW,
            agent_ids=["agent-1", "agent-2"],
        )
        
        assert rule.matches("any", agent_id="agent-1")
        assert not rule.matches("any", agent_id="agent-3")
    
    def test_rule_disabled(self):
        """Test disabled rule doesn't match."""
        rule = PolicyRule(
            rule_id="test",
            pattern="*",
            action=PolicyAction.ALLOW,
            enabled=False,
        )
        
        assert not rule.matches("any")


class TestPluginPolicyEngine:
    """Tests for PluginPolicyEngine."""
    
    def test_evaluate_allow_all_default(self, policy_engine):
        """Test default allow-all mode."""
        policy_engine.set_mode(PolicyMode.ALLOW_ALL)
        
        decision = policy_engine.evaluate("unknown-plugin")
        
        assert decision.allowed
        assert decision.action == PolicyAction.ALLOW
    
    def test_evaluate_deny_all_default(self, policy_engine):
        """Test deny-all mode."""
        policy_engine.set_mode(PolicyMode.DENY_ALL)
        
        decision = policy_engine.evaluate("unknown-plugin")
        
        assert not decision.allowed
        assert decision.action == PolicyAction.DENY
    
    def test_evaluate_explicit_allow(self, policy_engine):
        """Test explicit allow rule."""
        policy_engine.set_mode(PolicyMode.DENY_ALL)
        policy_engine.add_rule(PolicyRule(
            rule_id="allow-test",
            pattern="test-*",
            action=PolicyAction.ALLOW,
        ))
        
        decision = policy_engine.evaluate("test-plugin")
        
        assert decision.allowed
        assert decision.matched_rule is not None
        assert decision.matched_rule.rule_id == "allow-test"
    
    def test_evaluate_explicit_deny(self, policy_engine):
        """Test explicit deny rule."""
        policy_engine.set_mode(PolicyMode.ALLOW_ALL)
        policy_engine.add_rule(PolicyRule(
            rule_id="deny-test",
            pattern="bad-*",
            action=PolicyAction.DENY,
        ))
        
        decision = policy_engine.evaluate("bad-plugin")
        
        assert not decision.allowed
        assert decision.matched_rule.rule_id == "deny-test"
    
    def test_evaluate_priority(self, policy_engine):
        """Test rule priority."""
        policy_engine.add_rule(PolicyRule(
            rule_id="low-priority",
            pattern="*",
            action=PolicyAction.DENY,
            priority=10,
        ))
        policy_engine.add_rule(PolicyRule(
            rule_id="high-priority",
            pattern="allowed-*",
            action=PolicyAction.ALLOW,
            priority=100,
        ))
        
        # High priority rule wins
        decision = policy_engine.evaluate("allowed-plugin")
        assert decision.allowed
        assert decision.matched_rule.rule_id == "high-priority"
        
        # Other plugins denied
        decision = policy_engine.evaluate("other-plugin")
        assert not decision.allowed
    
    def test_evaluate_block_untrusted(self, policy_engine):
        """Test block_untrusted setting."""
        policy_engine.set_global_settings(block_untrusted=True)
        
        decision = policy_engine.evaluate(
            "any",
            trust_level=TrustLevel.UNTRUSTED,
        )
        
        assert not decision.allowed
        assert "Untrusted" in decision.reason
    
    def test_agent_mode_override(self, policy_engine):
        """Test per-agent mode override."""
        policy_engine.set_mode(PolicyMode.ALLOW_ALL)
        policy_engine.set_agent_mode("restricted-agent", PolicyMode.DENY_ALL)
        
        # Default agent allowed
        decision = policy_engine.evaluate("any", agent_id="normal-agent")
        assert decision.allowed
        
        # Restricted agent denied
        decision = policy_engine.evaluate("any", agent_id="restricted-agent")
        assert not decision.allowed
    
    def test_default_rules(self):
        """Test default rule creation."""
        rules = create_default_rules()
        
        assert len(rules) >= 4
        assert any(r.rule_id == "builtin-allow" for r in rules)
        assert any(r.rule_id == "marketplace-verified" for r in rules)


# ============================================================================
# Scanner Tests
# ============================================================================

class TestPluginScanner:
    """Tests for PluginScanner."""
    
    def test_scan_clean_plugin(self, scanner, temp_dir):
        """Test scanning a clean plugin."""
        # Create clean plugin
        plugin_dir = Path(temp_dir) / "plugins" / "clean-plugin"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("""
def greet(name):
    return f"Hello, {name}!"
""")
        
        result = scanner.scan("clean-plugin")
        
        assert result.passed
        assert result.risk_level == RiskLevel.LOW
        assert result.files_scanned == 1
        assert result.critical_count == 0
        assert result.error_count == 0
    
    def test_scan_dangerous_imports(self, scanner, temp_dir):
        """Test detecting dangerous imports."""
        plugin_dir = Path(temp_dir) / "plugins" / "import-plugin"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("""
import subprocess
import os
import socket
""")
        
        result = scanner.scan("import-plugin")
        
        assert result.warning_count >= 2
        assert any(f.category == ScanCategory.PROCESS_SPAWN for f in result.findings)
        assert any(f.category == ScanCategory.NETWORK_ACCESS for f in result.findings)
    
    def test_scan_dangerous_calls(self, scanner, temp_dir):
        """Test detecting dangerous function calls."""
        plugin_dir = Path(temp_dir) / "plugins" / "call-plugin"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("""
def run_code(code):
    eval(code)
    
def execute(cmd):
    import os
    os.system(cmd)
""")
        
        result = scanner.scan("call-plugin")
        
        assert not result.passed
        assert result.critical_count >= 2
        assert any(f.pattern_matched == "eval" for f in result.findings)
        assert any(f.pattern_matched == "os.system" for f in result.findings)
    
    def test_scan_obfuscation(self, scanner, temp_dir):
        """Test detecting obfuscation patterns."""
        plugin_dir = Path(temp_dir) / "plugins" / "obfuscated"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("""
import base64
data = base64.b64decode("SGVsbG8=")
""")
        
        result = scanner.scan("obfuscated")
        
        assert any(f.category == ScanCategory.OBFUSCATION for f in result.findings)
    
    def test_scan_credentials(self, scanner, temp_dir):
        """Test detecting hardcoded credentials."""
        plugin_dir = Path(temp_dir) / "plugins" / "creds"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("""
password = "secret123"
api_key = "sk-1234567890"
""")
        
        result = scanner.scan("creds")
        
        assert any(f.category == ScanCategory.CREDENTIAL_ACCESS for f in result.findings)
    
    def test_scan_permission_mismatch(self, scanner, temp_dir):
        """Test detecting permission mismatches."""
        plugin_dir = Path(temp_dir) / "plugins" / "mismatch"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("""
import socket
s = socket.socket()
""")
        
        result = scanner.scan(
            "mismatch",
            declared_permissions=["filesystem"],  # Declared filesystem, uses network
        )
        
        assert any(f.category == ScanCategory.PERMISSION_MISMATCH for f in result.findings)
    
    def test_scan_nonexistent(self, scanner):
        """Test scanning nonexistent plugin."""
        result = scanner.scan("nonexistent-plugin")
        
        assert not result.passed
        assert result.risk_level == RiskLevel.CRITICAL
    
    def test_report_persistence(self, scanner, temp_dir):
        """Test scan report is saved and retrievable."""
        plugin_dir = Path(temp_dir) / "plugins" / "report-test"
        plugin_dir.mkdir(parents=True)
        
        (plugin_dir / "main.py").write_text("print('hello')")
        
        scanner.scan("report-test")
        
        report = scanner.get_report("report-test")
        assert report is not None
        assert report.plugin_id == "report-test"


class TestScanFinding:
    """Tests for ScanFinding data class."""
    
    def test_finding_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        finding = ScanFinding(
            finding_id="SCAN-00001",
            category=ScanCategory.CODE_EXECUTION,
            severity=ScanSeverity.CRITICAL,
            message="Dangerous code",
            file_path="main.py",
            line_number=42,
            code_snippet="eval(user_input)",
            pattern_matched="eval",
        )
        
        data = finding.to_dict()
        restored = ScanFinding.from_dict(data)
        
        assert restored.finding_id == finding.finding_id
        assert restored.category == finding.category
        assert restored.severity == finding.severity
        assert restored.line_number == finding.line_number


# ============================================================================
# Skill Precedence Tests
# ============================================================================

class TestSkillEntry:
    """Tests for SkillEntry."""
    
    def test_entry_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        entry = SkillEntry(
            skill_id="my-skill",
            name="My Skill",
            source=SkillSource.PLUGIN,
            plugin_id="my-plugin",
            description="A test skill",
            version="2.0",
            priority=50,
        )
        
        data = entry.to_dict()
        restored = SkillEntry.from_dict(data)
        
        assert restored.skill_id == entry.skill_id
        assert restored.source == entry.source
        assert restored.plugin_id == entry.plugin_id
        assert restored.priority == entry.priority


class TestSkillPrecedenceManager:
    """Tests for SkillPrecedenceManager."""
    
    def test_register_and_resolve(self, precedence_manager):
        """Test registering and resolving skills."""
        entry = SkillEntry(
            skill_id="test-skill",
            name="Test Skill",
            source=SkillSource.PLUGIN,
            plugin_id="test-plugin",
        )
        
        precedence_manager.register_skill(entry)
        
        resolution = precedence_manager.resolve_skill("test-skill")
        
        assert resolution.found
        assert resolution.skill is not None
        assert resolution.skill.skill_id == "test-skill"
    
    def test_resolve_not_found(self, precedence_manager):
        """Test resolving nonexistent skill."""
        resolution = precedence_manager.resolve_skill("nonexistent")
        
        assert not resolution.found
        assert resolution.skill is None
    
    def test_precedence_builtin_wins(self, precedence_manager):
        """Test builtin skills have highest precedence."""
        # Register from multiple sources
        precedence_manager.register_skill(SkillEntry(
            skill_id="shared-skill",
            name="Shared Skill (Plugin)",
            source=SkillSource.PLUGIN,
            plugin_id="some-plugin",
        ))
        precedence_manager.register_skill(SkillEntry(
            skill_id="shared-skill",
            name="Shared Skill (Builtin)",
            source=SkillSource.BUILTIN,
        ))
        
        resolution = precedence_manager.resolve_skill("shared-skill")
        
        assert resolution.found
        assert resolution.conflict
        assert resolution.skill.source == SkillSource.BUILTIN
    
    def test_priority_within_source(self, precedence_manager):
        """Test priority affects resolution within same source."""
        precedence_manager.register_skill(SkillEntry(
            skill_id="priority-skill",
            name="Low Priority",
            source=SkillSource.PLUGIN,
            plugin_id="plugin-a",
            priority=10,
        ))
        precedence_manager.register_skill(SkillEntry(
            skill_id="priority-skill",
            name="High Priority",
            source=SkillSource.PLUGIN,
            plugin_id="plugin-b",
            priority=100,
        ))
        
        resolution = precedence_manager.resolve_skill("priority-skill")
        
        assert resolution.skill.priority == 100
        assert resolution.skill.plugin_id == "plugin-b"
    
    def test_unregister_skill(self, precedence_manager):
        """Test unregistering skills."""
        precedence_manager.register_skill(SkillEntry(
            skill_id="removable",
            name="Removable",
            source=SkillSource.CUSTOM,
        ))
        
        assert precedence_manager.unregister_skill("removable")
        
        resolution = precedence_manager.resolve_skill("removable")
        assert not resolution.found
    
    def test_agent_allowlist(self, precedence_manager):
        """Test agent-specific allowlists."""
        precedence_manager.register_skill(SkillEntry(
            skill_id="restricted-skill",
            name="Restricted",
            source=SkillSource.PLUGIN,
        ))
        precedence_manager.register_skill(SkillEntry(
            skill_id="allowed-skill",
            name="Allowed",
            source=SkillSource.PLUGIN,
        ))
        
        precedence_manager.set_agent_allowlist("agent-1", ["allowed-*"])
        
        # Allowed skill is visible
        allowed, _ = precedence_manager.is_skill_allowed_for_agent("allowed-skill", "agent-1")
        assert allowed
        
        # Restricted skill is not visible
        allowed, reason = precedence_manager.is_skill_allowed_for_agent("restricted-skill", "agent-1")
        assert not allowed
        assert "not in allowlist" in reason
    
    def test_agent_denylist(self, precedence_manager):
        """Test agent-specific denylists."""
        precedence_manager.register_skill(SkillEntry(
            skill_id="dangerous-skill",
            name="Dangerous",
            source=SkillSource.PLUGIN,
        ))
        
        precedence_manager.set_agent_denylist("agent-2", ["dangerous-*"])
        
        allowed, _ = precedence_manager.is_skill_allowed_for_agent("dangerous-skill", "agent-2")
        assert not allowed
    
    def test_list_skills_for_agent(self, precedence_manager):
        """Test listing skills for an agent."""
        precedence_manager.register_skill(SkillEntry(
            skill_id="skill-a",
            name="Skill A",
            source=SkillSource.PLUGIN,
        ))
        precedence_manager.register_skill(SkillEntry(
            skill_id="skill-b",
            name="Skill B",
            source=SkillSource.PLUGIN,
        ))
        
        precedence_manager.set_agent_denylist("agent-x", ["skill-b"])
        
        skills = precedence_manager.get_skills_for_agent("agent-x")
        
        assert len(skills) == 1
        assert skills[0].skill_id == "skill-a"
    
    def test_disabled_skill_not_resolved(self, precedence_manager):
        """Test disabled skills are not resolved."""
        precedence_manager.register_skill(SkillEntry(
            skill_id="disabled-skill",
            name="Disabled",
            source=SkillSource.PLUGIN,
            enabled=False,
        ))
        
        resolution = precedence_manager.resolve_skill("disabled-skill")
        
        assert not resolution.found
    
    def test_override_protection(self, precedence_manager):
        """Test builtin override protection."""
        # Disable plugin override of builtin
        prec = precedence_manager.get_precedence()
        prec.allow_plugin_override_builtin = False
        precedence_manager.set_precedence(prec)
        
        precedence_manager.register_skill(SkillEntry(
            skill_id="protected",
            name="Protected (Builtin)",
            source=SkillSource.BUILTIN,
        ))
        precedence_manager.register_skill(SkillEntry(
            skill_id="protected",
            name="Protected (Plugin)",
            source=SkillSource.PLUGIN,
            priority=1000,  # Even with high priority
        ))
        
        resolution = precedence_manager.resolve_skill("protected")
        
        # Builtin wins despite plugin priority
        assert resolution.skill.source == SkillSource.BUILTIN


# ============================================================================
# Integration Tests
# ============================================================================

class TestPluginGovernanceIntegration:
    """Integration tests for plugin governance."""
    
    def test_trust_to_policy_flow(self, trust_registry, policy_engine):
        """Test trust level affects policy decisions."""
        # Register plugin trust
        trust = PluginTrust(
            plugin_id="my-plugin",
            trust_level=TrustLevel.VERIFIED,
            source=TrustSource.MARKETPLACE,
        )
        trust_registry.register(trust)
        
        # Set up policy
        policy_engine.add_rule(PolicyRule(
            rule_id="verified-only",
            pattern="*",
            action=PolicyAction.DENY,
            trust_levels=[TrustLevel.UNVERIFIED, TrustLevel.UNTRUSTED],
        ))
        
        # Verified plugin allowed
        decision = policy_engine.evaluate(
            "my-plugin",
            trust_level=TrustLevel.VERIFIED,
        )
        assert decision.allowed
        
        # Unverified plugin denied
        decision = policy_engine.evaluate(
            "other-plugin",
            trust_level=TrustLevel.UNVERIFIED,
        )
        assert not decision.allowed
    
    def test_scan_updates_trust(self, scanner, trust_registry, temp_dir):
        """Test scan results update trust metadata."""
        # Create plugin
        plugin_dir = Path(temp_dir) / "plugins" / "scanned-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "main.py").write_text("print('safe')")
        
        # Create initial trust
        trust = trust_registry.create_trust_for_plugin(
            "scanned-plugin",
            source=TrustSource.LOCAL,
        )
        
        # Scan plugin
        result = scanner.scan("scanned-plugin")
        
        # Update trust with scan result
        trust_registry.mark_scanned(
            "scanned-plugin",
            passed=result.passed,
            risk_factors=[f.message for f in result.findings],
        )
        
        # Verify trust updated
        updated = trust_registry.get("scanned-plugin")
        assert updated.scan_passed == result.passed
        assert updated.last_scanned is not None
    
    def test_full_plugin_lifecycle(self, temp_dir):
        """Test complete plugin install lifecycle."""
        # Setup
        trust_dir = Path(temp_dir) / "trust"
        plugins_dir = Path(temp_dir) / "plugins"
        reports_dir = Path(temp_dir) / "reports"
        policy_file = Path(temp_dir) / "policy.json"
        
        trust_dir.mkdir()
        plugins_dir.mkdir()
        reports_dir.mkdir()
        
        registry = PluginTrustRegistry(str(trust_dir), str(plugins_dir))
        scanner = PluginScanner(str(plugins_dir), str(reports_dir))
        policy = PluginPolicyEngine(str(policy_file))
        
        # Create plugin to install
        plugin_dir = plugins_dir / "new-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text("""
def hello():
    return "Hello from plugin!"
""")
        
        # Step 1: Create trust entry
        trust = registry.create_trust_for_plugin(
            "new-plugin",
            source=TrustSource.LOCAL,
        )
        assert trust.trust_level == TrustLevel.UNVERIFIED
        
        # Step 2: Scan plugin
        scan_result = scanner.scan("new-plugin")
        registry.mark_scanned("new-plugin", scan_result.passed)
        
        # Step 3: Check policy
        decision = policy.evaluate(
            "new-plugin",
            trust_level=trust.trust_level,
            source=trust.source,
            scan_passed=scan_result.passed,
        )
        
        # Step 4: If allowed and scanned, upgrade trust
        if decision.allowed and scan_result.passed:
            registry.update_trust_level("new-plugin", TrustLevel.COMMUNITY)
        
        final_trust = registry.get("new-plugin")
        assert final_trust.trust_level == TrustLevel.COMMUNITY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
