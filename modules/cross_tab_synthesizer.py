"""
LADA v12.0 — Cross-Tab Synthesizer
Persistent intent memory across browser tabs for Comet-style agentic browsing.

The synthesizer maintains a rolling context of every tab the agent touches,
enabling multi-page reasoning (e.g. compare prices across Amazon vs Flipkart).

Features:
- Tab-level context snapshots (URL, title, extracted text, interactive elements)
- Intent tracking persisted across tab switches
- Automatic staleness detection and refresh signals
- Synthesis prompt builder for LLM multi-tab reasoning
"""

from __future__ import annotations

import logging
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TabSnapshot:
    """Snapshot of a single browser tab at a point in time."""
    tab_id: str
    url: str
    title: str
    text_excerpt: str = ""
    interactive_elements: int = 0
    semantic_yaml: str = ""
    captured_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.captured_at

    @property
    def is_stale(self) -> bool:
        """A snapshot older than 120 s is considered stale."""
        return self.age_seconds > 120.0

    def content_hash(self) -> str:
        payload = f"{self.url}|{self.title}|{self.text_excerpt[:256]}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Intent:
    """A user-level intent that persists across tab switches."""
    description: str
    created_at: float = field(default_factory=time.time)
    completed: bool = False
    result: Optional[str] = None
    related_tabs: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Synthesizer
# ---------------------------------------------------------------------------

class CrossTabSynthesizer:
    """
    Maintains rolling context across browser tabs for multi-page reasoning.

    Usage::

        synth = CrossTabSynthesizer()
        synth.register_intent("Compare laptop prices on Amazon and Flipkart")
        synth.snapshot_tab("tab1", url="...", title="...", text="...",
                           semantic_yaml="...")
        synth.snapshot_tab("tab2", url="...", title="...", text="...",
                           semantic_yaml="...")
        prompt = synth.build_synthesis_prompt()
    """

    MAX_SNAPSHOTS_PER_TAB = 5
    MAX_INTENTS = 20

    def __init__(self) -> None:
        self._tabs: Dict[str, List[TabSnapshot]] = {}
        self._intents: List[Intent] = []
        self._active_tab: Optional[str] = None

    # -- Tab management --

    def snapshot_tab(
        self,
        tab_id: str,
        url: str,
        title: str,
        text: str = "",
        interactive_elements: int = 0,
        semantic_yaml: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TabSnapshot:
        """Record a point-in-time snapshot of a tab."""
        snap = TabSnapshot(
            tab_id=tab_id,
            url=url,
            title=title,
            text_excerpt=text[:2000],
            interactive_elements=interactive_elements,
            semantic_yaml=semantic_yaml,
            metadata=metadata or {},
        )

        if tab_id not in self._tabs:
            self._tabs[tab_id] = []

        history = self._tabs[tab_id]

        # De-duplicate identical consecutive captures
        if history and history[-1].content_hash() == snap.content_hash():
            history[-1].captured_at = time.time()
            return history[-1]

        history.append(snap)

        # Trim old snapshots per tab
        if len(history) > self.MAX_SNAPSHOTS_PER_TAB:
            self._tabs[tab_id] = history[-self.MAX_SNAPSHOTS_PER_TAB:]

        self._active_tab = tab_id
        logger.debug(f"[CrossTab] Snapshot tab {tab_id}: {title}")
        return snap

    def close_tab(self, tab_id: str) -> None:
        """Remove all snapshots for a closed tab."""
        self._tabs.pop(tab_id, None)
        if self._active_tab == tab_id:
            self._active_tab = None

    def get_latest_snapshot(self, tab_id: str) -> Optional[TabSnapshot]:
        """Get latest snapshot for a tab (or None)."""
        history = self._tabs.get(tab_id, [])
        return history[-1] if history else None

    def stale_tabs(self) -> List[str]:
        """Return tab IDs whose latest snapshot is stale."""
        stale = []
        for tid, snaps in self._tabs.items():
            if snaps and snaps[-1].is_stale:
                stale.append(tid)
        return stale

    # -- Intent tracking --

    def register_intent(self, description: str) -> Intent:
        """Register a new user intent that spans multiple tabs."""
        intent = Intent(description=description)
        self._intents.append(intent)
        if len(self._intents) > self.MAX_INTENTS:
            self._intents = self._intents[-self.MAX_INTENTS:]
        logger.info(f"[CrossTab] Intent registered: {description}")
        return intent

    def complete_intent(self, description: str, result: str = "") -> None:
        """Mark an intent as completed."""
        for intent in reversed(self._intents):
            if intent.description == description and not intent.completed:
                intent.completed = True
                intent.result = result
                return

    def pending_intents(self) -> List[Intent]:
        """Return all incomplete intents."""
        return [i for i in self._intents if not i.completed]

    # -- LLM context builder --

    def build_synthesis_prompt(self, max_tokens_budget: int = 4000) -> str:
        """
        Build a compact prompt that summarizes all open tabs and active intents.

        This prompt is injected into the AI model context when the Comet agent
        needs to reason across tabs.
        """
        parts: List[str] = []

        # Active intents
        pending = self.pending_intents()
        if pending:
            parts.append("## Active Intents")
            for idx, intent in enumerate(pending, 1):
                parts.append(f"{idx}. {intent.description}")
            parts.append("")

        # Tab summaries
        parts.append("## Open Tabs")
        for tid, snaps in self._tabs.items():
            if not snaps:
                continue
            latest = snaps[-1]
            marker = "→ " if tid == self._active_tab else "  "
            stale_flag = " [STALE]" if latest.is_stale else ""
            parts.append(
                f"{marker}Tab {tid}: {latest.title} ({latest.url}){stale_flag}"
            )
            if latest.text_excerpt:
                excerpt = latest.text_excerpt[:300].replace("\n", " ")
                parts.append(f"    Text: {excerpt}…")
            if latest.interactive_elements:
                parts.append(
                    f"    Interactive elements: {latest.interactive_elements}"
                )
            if latest.semantic_yaml:
                # Include first few lines of semantic YAML
                yaml_lines = latest.semantic_yaml.strip().split("\n")[:8]
                parts.append("    Semantic:")
                for yl in yaml_lines:
                    parts.append(f"      {yl}")
        parts.append("")

        prompt = "\n".join(parts)

        # Rough token-budget guard (1 token ≈ 4 chars)
        char_budget = max_tokens_budget * 4
        if len(prompt) > char_budget:
            prompt = prompt[:char_budget] + "\n… (truncated)"

        return prompt

    # -- Utilities --

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostics."""
        return {
            "open_tabs": len(self._tabs),
            "active_tab": self._active_tab,
            "total_snapshots": sum(len(s) for s in self._tabs.values()),
            "pending_intents": len(self.pending_intents()),
            "stale_tabs": self.stale_tabs(),
        }

    def clear(self) -> None:
        """Reset all state."""
        self._tabs.clear()
        self._intents.clear()
        self._active_tab = None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[CrossTabSynthesizer] = None


def get_cross_tab_synthesizer() -> CrossTabSynthesizer:
    """Get or create the global CrossTabSynthesizer instance."""
    global _instance
    if _instance is None:
        _instance = CrossTabSynthesizer()
    return _instance
