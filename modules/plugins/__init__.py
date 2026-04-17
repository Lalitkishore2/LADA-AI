"""
LADA Plugin Governance Module

Provides security governance for plugins and skills.

Features:
- Plugin trust metadata and verification
- Allow/deny policy enforcement
- Install-time security scanning
- Skill source precedence
"""

from modules.plugins.trust import (
    PluginTrust,
    TrustLevel,
    TrustSource,
    PluginTrustRegistry,
    get_trust_registry,
)

from modules.plugins.policy import (
    PluginPolicy,
    PolicyAction,
    PolicyRule,
    PluginPolicyEngine,
    get_policy_engine,
)

from modules.plugins.scanner import (
    ScanResult,
    ScanSeverity,
    ScanFinding,
    PluginScanner,
    get_scanner,
)

from modules.plugins.skill_precedence import (
    SkillSource,
    SkillPrecedence,
    SkillPrecedenceManager,
    get_precedence_manager,
)

__all__ = [
    # Trust
    'PluginTrust',
    'TrustLevel',
    'TrustSource',
    'PluginTrustRegistry',
    'get_trust_registry',
    # Policy
    'PluginPolicy',
    'PolicyAction',
    'PolicyRule',
    'PluginPolicyEngine',
    'get_policy_engine',
    # Scanner
    'ScanResult',
    'ScanSeverity',
    'ScanFinding',
    'PluginScanner',
    'get_scanner',
    # Skill Precedence
    'SkillSource',
    'SkillPrecedence',
    'SkillPrecedenceManager',
    'get_precedence_manager',
]
