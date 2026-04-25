"""
LADA v12.0 — Data Loss Prevention (DLP) Filter
Bounding-box based redaction for screen captures before they reach the AI model.

Prevents sensitive data (credit-card numbers, passwords, personal IDs, medical
records) from being transmitted to cloud-based vision models by detecting and
blacking-out regions that match known patterns.

Features:
- Regex-based text pattern detection (CC numbers, SSNs, API keys, etc.)
- Bounding-box blackout on PIL Images before base64 encoding
- Configurable sensitivity levels (strict / normal / relaxed)
- Audit log of every redaction event
"""

from __future__ import annotations

import re
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class DLPSensitivity(Enum):
    STRICT = "strict"       # Block almost everything suspicious
    NORMAL = "normal"       # Standard PII/PCI patterns
    RELAXED = "relaxed"     # Only block high-confidence matches


@dataclass
class DLPConfig:
    """DLP filter configuration."""
    sensitivity: DLPSensitivity = DLPSensitivity.NORMAL
    redact_color: Tuple[int, int, int] = (0, 0, 0)  # Solid black
    log_redactions: bool = True
    max_audit_entries: int = 500


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

@dataclass
class SensitivePattern:
    """One regex-based detection rule."""
    name: str
    pattern: str
    severity: str = "high"  # "high", "medium", "low"
    min_sensitivity: DLPSensitivity = DLPSensitivity.NORMAL
    _compiled_regex: Optional[re.Pattern] = field(default=None, init=False, repr=False)

    def compiled(self) -> re.Pattern:
        """Lazy load and cache the compiled regex."""
        if self._compiled_regex is None:
            self._compiled_regex = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled_regex


# Master list of patterns (order does not matter; every pattern is evaluated).
_BUILTIN_PATTERNS: List[SensitivePattern] = [
    # Financial
    SensitivePattern("credit_card_visa", r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "high"),
    SensitivePattern("credit_card_mc", r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "high"),
    SensitivePattern("credit_card_amex", r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b", "high"),
    SensitivePattern("cvv", r"\bCVV[\s:]*\d{3,4}\b", "high"),
    SensitivePattern("bank_account_in", r"\b\d{9,18}\b(?=.*(?:account|acct|a/c))", "medium"),

    # Identity
    SensitivePattern("ssn_us", r"\b\d{3}-\d{2}-\d{4}\b", "high"),
    SensitivePattern("aadhaar_in", r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "high"),
    SensitivePattern("pan_in", r"\b[A-Z]{5}\d{4}[A-Z]\b", "medium"),
    SensitivePattern("passport", r"\b[A-Z]\d{7}\b", "low", DLPSensitivity.STRICT),

    # Credentials
    SensitivePattern("api_key_generic", r"(?:api[_-]?key|apikey|token|secret)[\s:=]+['\"]?[\w\-]{20,}['\"]?", "high"),
    SensitivePattern("password_field", r"(?:password|passwd|pwd)[\s:=]+\S+", "high"),
    SensitivePattern("bearer_token", r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "high"),
    SensitivePattern("aws_key", r"AKIA[0-9A-Z]{16}", "high"),

    # Medical (STRICT only)
    SensitivePattern("medical_id", r"\b(?:MRN|patient\s*id|medical\s*record)[\s:#]*\d+", "medium", DLPSensitivity.STRICT),

    # Email / Phone (STRICT only — common and high false-positive)
    SensitivePattern("email", r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "low", DLPSensitivity.STRICT),
    SensitivePattern("phone_in", r"\b(?:\+91[\s-]?)?\d{5}[\s-]?\d{5}\b", "low", DLPSensitivity.STRICT),
]


# ---------------------------------------------------------------------------
# Redaction result
# ---------------------------------------------------------------------------

@dataclass
class RedactionEvent:
    """Record of one redacted region."""
    pattern_name: str
    matched_text: str  # first 6 chars + mask
    region: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# DLP Filter
# ---------------------------------------------------------------------------

class DLPFilter:
    """
    Screen-capture DLP filter.

    Operates in two modes:
    1. **Text-only**: scan extracted OCR text and return matches.
    2. **Image redact**: given bounding-box coordinates of text blocks,
       black-out regions in a PIL Image that match sensitive patterns.
    """

    def __init__(self, config: Optional[DLPConfig] = None) -> None:
        self.config = config or DLPConfig()
        self._audit: List[RedactionEvent] = []
        self._patterns = self._active_patterns()

    def _active_patterns(self) -> List[SensitivePattern]:
        """Return patterns that are active at the current sensitivity level."""
        level_order = [DLPSensitivity.RELAXED, DLPSensitivity.NORMAL, DLPSensitivity.STRICT]
        current_idx = level_order.index(self.config.sensitivity)
        return [
            p for p in _BUILTIN_PATTERNS
            if level_order.index(p.min_sensitivity) <= current_idx
        ]

    # -- Text scanning --

    def scan_text(self, text: str) -> List[RedactionEvent]:
        """Scan raw text for sensitive patterns. Returns list of matches."""
        events: List[RedactionEvent] = []
        for pat in self._patterns:
            for match in pat.compiled().finditer(text):
                raw = match.group()
                masked = raw[:4] + "•" * max(0, len(raw) - 4)
                evt = RedactionEvent(
                    pattern_name=pat.name,
                    matched_text=masked,
                )
                events.append(evt)
        return events

    def contains_sensitive(self, text: str) -> bool:
        """Quick predicate: does text contain anything sensitive?"""
        for pat in self._patterns:
            if pat.compiled().search(text):
                return True
        return False

    # -- Image redaction --

    def redact_image(
        self,
        image: "Image.Image",
        text_blocks: List[Dict[str, Any]],
    ) -> Tuple["Image.Image", List[RedactionEvent]]:
        """
        Black-out sensitive regions in an image.

        Args:
            image: PIL Image (will be copied — original is not mutated).
            text_blocks: list of dicts, each with keys:
                - ``text``: the OCR'd string for that block
                - ``x``, ``y``, ``width``, ``height``: bounding box

        Returns:
            (redacted_image, list_of_redaction_events)
        """
        if not PIL_OK:
            logger.warning("[DLP] PIL not available — skipping image redaction")
            return image, []

        redacted = image.copy()
        draw = ImageDraw.Draw(redacted)
        events: List[RedactionEvent] = []

        for block in text_blocks:
            block_text = block.get("text", "")
            if not block_text:
                continue

            for pat in self._patterns:
                if pat.compiled().search(block_text):
                    x = block.get("x", 0)
                    y = block.get("y", 0)
                    w = block.get("width", 0)
                    h = block.get("height", 0)
                    draw.rectangle(
                        [x, y, x + w, y + h],
                        fill=self.config.redact_color,
                    )
                    masked = block_text[:4] + "•" * max(0, len(block_text) - 4)
                    evt = RedactionEvent(
                        pattern_name=pat.name,
                        matched_text=masked,
                        region=(x, y, w, h),
                    )
                    events.append(evt)
                    break  # one match per block is enough to redact

        # Audit
        if self.config.log_redactions:
            self._audit.extend(events)
            if len(self._audit) > self.config.max_audit_entries:
                self._audit = self._audit[-self.config.max_audit_entries:]

        if events:
            logger.info(f"[DLP] Redacted {len(events)} region(s) from image")
        return redacted, events

    # -- Audit --

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent redaction events."""
        return [
            {
                "pattern": e.pattern_name,
                "matched": e.matched_text,
                "region": e.region,
                "timestamp": e.timestamp,
            }
            for e in self._audit[-limit:]
        ]

    def clear_audit(self) -> None:
        self._audit.clear()

    def set_sensitivity(self, level: DLPSensitivity) -> None:
        """Change sensitivity at runtime."""
        self.config.sensitivity = level
        self._patterns = self._active_patterns()
        logger.info(f"[DLP] Sensitivity set to {level.value}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[DLPFilter] = None


def get_dlp_filter(config: Optional[DLPConfig] = None) -> DLPFilter:
    """Get or create the global DLPFilter instance."""
    global _instance
    if _instance is None:
        _instance = DLPFilter(config)
    return _instance
