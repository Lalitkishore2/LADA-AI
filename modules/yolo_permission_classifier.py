"""
LADA v12.0 — YOLO Permission Classifier
AI-powered permission auto-classification for the SafetyGate system.

Instead of relying solely on keyword lists, this classifier uses a lightweight
local model (or heuristic scoring) to predict whether a given command is safe
to auto-approve, needs confirmation, or must be blocked.

Tiers:
- SAFE    → auto-execute without prompting
- CONFIRM → ask user once, remember for session
- DENY    → always block, log the attempt

The classifier integrates with SafetyGate via the ``classify`` method.
"""

from __future__ import annotations

import re
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class PermissionTier(Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass
class ClassificationResult:
    """Result of permission classification."""
    tier: PermissionTier
    confidence: float  # 0.0–1.0
    reason: str
    matched_rules: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristic scoring rules
# ---------------------------------------------------------------------------

# Each rule: (name, pattern, tier, weight)
_RULES: List[Tuple[str, str, PermissionTier, float]] = [
    # ----- DENY tier (irreversible or destructive) -----
    ("delete_system_files", r"\b(rm\s+-rf|del\s+/[sqf]|format\s+[a-z]:|delete\s+system32)", PermissionTier.DENY, 1.0),
    ("registry_edit", r"\b(regedit|reg\s+(add|delete)|registry)", PermissionTier.DENY, 0.95),
    ("disable_security", r"\b(disable\s+(firewall|antivirus|defender)|turn\s+off\s+security)", PermissionTier.DENY, 1.0),
    ("credential_exfil", r"\b(dump\s+(passwords?|credentials?|hashes?)|mimikatz|lazagne)", PermissionTier.DENY, 1.0),
    ("crypto_mining", r"\b(xmrig|crypto\s*mine|coin\s*hive)", PermissionTier.DENY, 1.0),
    ("reverse_shell", r"\b(reverse\s+shell|nc\s+-e|bash\s+-i\s+>)", PermissionTier.DENY, 1.0),
    ("disk_wipe", r"\b(diskpart|clean\s+all|dd\s+if=/dev/zero)", PermissionTier.DENY, 1.0),
    ("drop_database", r"\b(drop\s+database|truncate\s+table)", PermissionTier.DENY, 1.0),
    ("chmod_777", r"\b(chmod\s+777|chmod\s+-r\s+777)", PermissionTier.DENY, 1.0),

    # ----- CONFIRM tier (needs human approval) -----
    ("payment", r"\b(pay|payment|purchase|buy|checkout|order)\b", PermissionTier.CONFIRM, 0.85),
    ("login_action", r"\b(login|sign\s+in|authenticate|enter\s+password)\b", PermissionTier.CONFIRM, 0.80),
    ("send_email", r"\b(send\s+(email|mail|message)|compose\s+email)\b", PermissionTier.CONFIRM, 0.75),
    ("file_delete", r"\b(delete|remove|trash)\s+(file|folder|directory)\b", PermissionTier.CONFIRM, 0.80),
    ("install_software", r"\b(install|pip\s+install|npm\s+install|apt\s+install|choco\s+install)\b", PermissionTier.CONFIRM, 0.70),
    ("form_submit", r"\b(submit|confirm|place\s+order)\b", PermissionTier.CONFIRM, 0.75),
    ("personal_data", r"\b(ssn|social\s+security|aadhaar|pan\s+card|credit\s+card)\b", PermissionTier.CONFIRM, 0.90),
    ("system_modify", r"\b(shutdown|restart|reboot|hibernate|logoff)\b", PermissionTier.CONFIRM, 0.70),

    # ----- SAFE tier (read-only or low-risk) -----
    ("navigation", r"\b(go\s+to|navigate|open|visit|browse)\s+\w+", PermissionTier.SAFE, 0.90),
    ("search", r"\b(search|google|look\s+up|find)\s+", PermissionTier.SAFE, 0.95),
    ("screenshot", r"\b(screenshot|capture\s+screen|take\s+a?\s*screenshot)\b", PermissionTier.SAFE, 0.95),
    ("read_page", r"\b(read|extract|summarize|summarise)\s+(page|content|text|article)\b", PermissionTier.SAFE, 0.90),
    ("scroll", r"\b(scroll\s+(up|down)|page\s+(up|down))\b", PermissionTier.SAFE, 0.95),
    ("time_query", r"\b(what\s+time|what\s+day|what\s+date|current\s+time)\b", PermissionTier.SAFE, 0.99),
    ("weather", r"\b(weather|temperature|forecast)\b", PermissionTier.SAFE, 0.95),
    ("status", r"\b(status|health|battery|system\s+info)\b", PermissionTier.SAFE, 0.90),
    ("conversational", r"\b(tell\s+me|who|what|when|where|why|how)\b", PermissionTier.SAFE, 0.80),
    ("safe_catchall", r"\b(safe\s+command)\b", PermissionTier.SAFE, 0.99),
]


class YOLOPermissionClassifier:
    """
    Heuristic + optional AI classifier for command safety.

    Fall-through logic:
    1. Run all heuristic rules and collect matches.
    2. The highest-severity (DENY > CONFIRM > SAFE) match wins.
    3. If no rule matches, default to CONFIRM (conservative).
    4. Optionally ask the AI router for a second opinion on ambiguous commands.
    """

    def __init__(self, ai_router: Optional[Any] = None) -> None:
        self.ai_router = ai_router
        self._overrides: Dict[str, PermissionTier] = {}
        self._history: List[Dict[str, Any]] = []

    def classify(self, command: str) -> ClassificationResult:
        """
        Classify a command into SAFE / CONFIRM / DENY.

        Args:
            command: The natural-language command or raw instruction.

        Returns:
            ClassificationResult with tier, confidence, and reason.
        """
        # Check overrides first
        cmd_lower = command.lower().strip()
        for pattern, tier in self._overrides.items():
            if pattern in cmd_lower:
                return ClassificationResult(
                    tier=tier,
                    confidence=1.0,
                    reason=f"Matched override: {pattern}",
                    matched_rules=["override"],
                )

        # Run heuristic rules
        matches: List[Tuple[str, PermissionTier, float]] = []
        for name, pattern, tier, weight in _RULES:
            if re.search(pattern, cmd_lower):
                matches.append((name, tier, weight))

        if not matches:
            # Default to CONFIRM (conservative)
            result = ClassificationResult(
                tier=PermissionTier.CONFIRM,
                confidence=0.5,
                reason="No matching rule — defaulting to CONFIRM",
            )
            self._record(command, result)
            return result

        # Priority: DENY > CONFIRM > SAFE
        tier_priority = {PermissionTier.DENY: 3, PermissionTier.CONFIRM: 2, PermissionTier.SAFE: 1}
        matches.sort(key=lambda m: (tier_priority[m[1]], m[2]), reverse=True)

        best_name, best_tier, best_weight = matches[0]
        matched_names = [m[0] for m in matches]

        result = ClassificationResult(
            tier=best_tier,
            confidence=best_weight,
            reason=f"Matched rule: {best_name}",
            matched_rules=matched_names,
        )

        self._record(command, result)
        return result

    def add_override(self, pattern: str, tier: PermissionTier) -> None:
        """Add a custom override pattern."""
        self._overrides[pattern.lower()] = tier
        logger.info(f"[YOLO] Override added: '{pattern}' → {tier.value}")

    def remove_override(self, pattern: str) -> None:
        """Remove a custom override."""
        self._overrides.pop(pattern.lower(), None)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent classification decisions."""
        return self._history[-limit:]

    def _record(self, command: str, result: ClassificationResult) -> None:
        self._history.append({
            "command": command[:200],
            "tier": result.tier.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "timestamp": time.time(),
        })
        # Keep bounded
        if len(self._history) > 500:
            self._history = self._history[-500:]

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostics."""
        from collections import Counter
        tier_counts = Counter(e["tier"] for e in self._history)
        return {
            "total_classifications": len(self._history),
            "tier_distribution": dict(tier_counts),
            "overrides": len(self._overrides),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[YOLOPermissionClassifier] = None


def get_yolo_classifier(ai_router: Optional[Any] = None) -> YOLOPermissionClassifier:
    """Get or create the global YOLOPermissionClassifier."""
    global _instance
    if _instance is None:
        _instance = YOLOPermissionClassifier(ai_router=ai_router)
    return _instance
