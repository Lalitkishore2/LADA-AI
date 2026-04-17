"""
LADA Plugin Trust System

Manages trust metadata and verification for plugins.

Features:
- Trust levels (untrusted → verified)
- Source tracking (marketplace, local, remote)
- Hash verification
- Trust persistence
"""

import os
import json
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class TrustLevel(str, Enum):
    """Plugin trust levels."""
    UNTRUSTED = "untrusted"       # Unknown or suspicious
    UNVERIFIED = "unverified"     # Not yet verified
    COMMUNITY = "community"       # Community-reviewed
    VERIFIED = "verified"         # Officially verified
    BUILTIN = "builtin"           # Built-in to LADA


class TrustSource(str, Enum):
    """Where the plugin came from."""
    BUILTIN = "builtin"           # Built into LADA
    MARKETPLACE = "marketplace"   # Official marketplace
    LOCAL = "local"               # Local file system
    GIT = "git"                   # Git repository
    URL = "url"                   # Direct URL download
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Plugin risk assessment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PluginTrust:
    """
    Trust metadata for a plugin.
    """
    plugin_id: str
    
    # Trust info
    trust_level: TrustLevel = TrustLevel.UNVERIFIED
    source: TrustSource = TrustSource.UNKNOWN
    risk_level: RiskLevel = RiskLevel.MEDIUM
    
    # Verification
    content_hash: str = ""           # SHA256 of plugin contents
    signature: str = ""              # Optional signature
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    
    # Metadata
    version: str = ""
    author: str = ""
    homepage: str = ""
    repository: str = ""
    
    # Capabilities declared
    capabilities: List[str] = field(default_factory=list)
    permissions_requested: List[str] = field(default_factory=list)
    
    # Risk factors
    risk_factors: List[str] = field(default_factory=list)
    
    # State
    installed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_scanned: Optional[str] = None
    scan_passed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "trust_level": self.trust_level.value,
            "source": self.source.value,
            "risk_level": self.risk_level.value,
            "content_hash": self.content_hash,
            "signature": self.signature,
            "verified_at": self.verified_at,
            "verified_by": self.verified_by,
            "version": self.version,
            "author": self.author,
            "homepage": self.homepage,
            "repository": self.repository,
            "capabilities": self.capabilities,
            "permissions_requested": self.permissions_requested,
            "risk_factors": self.risk_factors,
            "installed_at": self.installed_at,
            "last_scanned": self.last_scanned,
            "scan_passed": self.scan_passed,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginTrust":
        return cls(
            plugin_id=data["plugin_id"],
            trust_level=TrustLevel(data.get("trust_level", "unverified")),
            source=TrustSource(data.get("source", "unknown")),
            risk_level=RiskLevel(data.get("risk_level", "medium")),
            content_hash=data.get("content_hash", ""),
            signature=data.get("signature", ""),
            verified_at=data.get("verified_at"),
            verified_by=data.get("verified_by"),
            version=data.get("version", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            repository=data.get("repository", ""),
            capabilities=data.get("capabilities", []),
            permissions_requested=data.get("permissions_requested", []),
            risk_factors=data.get("risk_factors", []),
            installed_at=data.get("installed_at", datetime.now().isoformat()),
            last_scanned=data.get("last_scanned"),
            scan_passed=data.get("scan_passed", False),
        )
    
    @property
    def is_trusted(self) -> bool:
        """Check if plugin is sufficiently trusted."""
        return self.trust_level in (
            TrustLevel.COMMUNITY,
            TrustLevel.VERIFIED,
            TrustLevel.BUILTIN,
        )


# ============================================================================
# Trust Registry
# ============================================================================

class PluginTrustRegistry:
    """
    Registry for plugin trust metadata.
    
    Features:
    - Trust level tracking
    - Hash verification
    - Persistence
    """
    
    def __init__(
        self,
        trust_dir: Optional[str] = None,
        plugins_dir: Optional[str] = None,
    ):
        self._trust_dir = Path(trust_dir or os.getenv("LADA_PLUGIN_TRUST_DIR", "data/plugin_trust"))
        self._plugins_dir = Path(plugins_dir or os.getenv("LADA_PLUGINS_DIR", "plugins"))
        
        self._trust_dir.mkdir(parents=True, exist_ok=True)
        
        self._trust: Dict[str, PluginTrust] = {}
        self._lock = threading.RLock()
        
        # Load existing trust data
        self._load_trust_data()
        
        logger.info(f"[PluginTrustRegistry] Initialized with {len(self._trust)} entries")
    
    def register(self, trust: PluginTrust) -> bool:
        """Register or update trust metadata for a plugin."""
        with self._lock:
            self._trust[trust.plugin_id] = trust
            self._save_trust(trust)
        return True
    
    def get(self, plugin_id: str) -> Optional[PluginTrust]:
        """Get trust metadata for a plugin."""
        with self._lock:
            return self._trust.get(plugin_id)
    
    def remove(self, plugin_id: str) -> bool:
        """Remove trust metadata for a plugin."""
        with self._lock:
            if plugin_id in self._trust:
                del self._trust[plugin_id]
                trust_file = self._trust_dir / f"{plugin_id}.json"
                if trust_file.exists():
                    trust_file.unlink()
                return True
        return False
    
    def list_all(
        self,
        trust_level: Optional[TrustLevel] = None,
        source: Optional[TrustSource] = None,
    ) -> List[PluginTrust]:
        """List all trust entries with optional filtering."""
        with self._lock:
            entries = list(self._trust.values())
        
        if trust_level:
            entries = [e for e in entries if e.trust_level == trust_level]
        
        if source:
            entries = [e for e in entries if e.source == source]
        
        return entries
    
    def verify_hash(self, plugin_id: str) -> bool:
        """Verify plugin content hash matches stored hash."""
        trust = self.get(plugin_id)
        if not trust or not trust.content_hash:
            return False
        
        current_hash = self.compute_plugin_hash(plugin_id)
        return current_hash == trust.content_hash
    
    def compute_plugin_hash(self, plugin_id: str) -> str:
        """Compute SHA256 hash of plugin contents."""
        plugin_dir = self._plugins_dir / plugin_id
        if not plugin_dir.exists():
            return ""
        
        hasher = hashlib.sha256()
        
        # Hash all Python files in sorted order for determinism
        for py_file in sorted(plugin_dir.rglob("*.py")):
            try:
                hasher.update(py_file.read_bytes())
            except Exception:
                pass
        
        # Also hash manifest if present
        for manifest in ["manifest.yaml", "manifest.json", "plugin.json"]:
            manifest_file = plugin_dir / manifest
            if manifest_file.exists():
                try:
                    hasher.update(manifest_file.read_bytes())
                except Exception:
                    pass
        
        return hasher.hexdigest()
    
    def update_trust_level(
        self,
        plugin_id: str,
        trust_level: TrustLevel,
        verified_by: Optional[str] = None,
    ) -> Optional[PluginTrust]:
        """Update trust level for a plugin."""
        with self._lock:
            trust = self._trust.get(plugin_id)
            if not trust:
                return None
            
            trust.trust_level = trust_level
            if verified_by:
                trust.verified_by = verified_by
                trust.verified_at = datetime.now().isoformat()
            
            self._save_trust(trust)
            return trust
    
    def mark_scanned(
        self,
        plugin_id: str,
        passed: bool,
        risk_factors: Optional[List[str]] = None,
    ) -> Optional[PluginTrust]:
        """Mark plugin as scanned."""
        with self._lock:
            trust = self._trust.get(plugin_id)
            if not trust:
                return None
            
            trust.last_scanned = datetime.now().isoformat()
            trust.scan_passed = passed
            if risk_factors:
                trust.risk_factors = risk_factors
            
            self._save_trust(trust)
            return trust
    
    def create_trust_for_plugin(
        self,
        plugin_id: str,
        source: TrustSource = TrustSource.LOCAL,
        version: str = "",
        author: str = "",
    ) -> PluginTrust:
        """Create initial trust entry for a new plugin."""
        content_hash = self.compute_plugin_hash(plugin_id)
        
        trust = PluginTrust(
            plugin_id=plugin_id,
            trust_level=TrustLevel.UNVERIFIED,
            source=source,
            content_hash=content_hash,
            version=version,
            author=author,
        )
        
        self.register(trust)
        return trust
    
    def _load_trust_data(self):
        """Load all trust data from disk."""
        for trust_file in self._trust_dir.glob("*.json"):
            try:
                with open(trust_file, 'r') as f:
                    data = json.load(f)
                trust = PluginTrust.from_dict(data)
                self._trust[trust.plugin_id] = trust
            except Exception as e:
                logger.warning(f"[PluginTrustRegistry] Failed to load {trust_file}: {e}")
    
    def _save_trust(self, trust: PluginTrust):
        """Save trust data to disk."""
        trust_file = self._trust_dir / f"{trust.plugin_id}.json"
        try:
            with open(trust_file, 'w') as f:
                json.dump(trust.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[PluginTrustRegistry] Failed to save {trust.plugin_id}: {e}")


# ============================================================================
# Singleton
# ============================================================================

_registry_instance: Optional[PluginTrustRegistry] = None
_registry_lock = threading.Lock()


def get_trust_registry() -> PluginTrustRegistry:
    """Get singleton PluginTrustRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = PluginTrustRegistry()
    return _registry_instance
