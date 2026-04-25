"""
LADA v12.0 — Mem0 Context-Aware Memory Adapter
Bridges LADA's existing MemorySystem to Mem0's semantic memory layer.

Mem0 provides:
- Automatic fact extraction from conversations
- Semantic search over stored memories
- User-level, session-level, and agent-level scoping
- Graph-based knowledge linking

This adapter falls back gracefully when mem0 is not installed,
delegating to the legacy FAISS/JSON storage in lada_memory.py.
"""

from __future__ import annotations

import os
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Try to import mem0
try:
    from mem0 import Memory
    MEM0_OK = True
except ImportError:
    MEM0_OK = False
    Memory = None
    logger.info("[Mem0] mem0 not installed — using legacy memory backend")


@dataclass
class MemoryEntry:
    """A single memory item."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    source: str = "mem0"  # "mem0" or "legacy"
    created_at: float = field(default_factory=time.time)


class Mem0Adapter:
    """
    Unified memory interface that uses Mem0 when available,
    falling back to a simple JSON-based store otherwise.

    Usage::

        adapter = Mem0Adapter(user_id="lalit")
        adapter.add("The user prefers dark mode")
        results = adapter.search("What theme does the user prefer?")
    """

    LEGACY_FILE = "data/mem0_legacy.json"

    def __init__(
        self,
        user_id: str = "default",
        agent_id: str = "lada",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.user_id = user_id
        self.agent_id = agent_id
        self._mem0: Optional[Any] = None
        self._legacy_store: List[Dict[str, Any]] = []
        self._config = config or {}

        if MEM0_OK:
            try:
                mem0_cfg = {
                    "version": "v1.1",
                    **(self._config or {}),
                }
                self._mem0 = Memory.from_config(mem0_cfg)
                logger.info("[Mem0] Initialized Mem0 memory backend")
            except Exception as e:
                logger.warning(f"[Mem0] Failed to init Mem0, falling back: {e}")
                self._mem0 = None

        if self._mem0 is None:
            self._load_legacy()

    # -- Public API --

    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a memory.

        Returns the memory ID.
        """
        metadata = metadata or {}

        if self._mem0 is not None:
            try:
                result = self._mem0.add(
                    content,
                    user_id=self.user_id,
                    agent_id=self.agent_id,
                    metadata=metadata,
                )
                mid = result.get("id", "") if isinstance(result, dict) else str(result)
                logger.debug(f"[Mem0] Added memory: {mid}")
                return mid
            except Exception as e:
                logger.error(f"[Mem0] add failed, falling back: {e}")

        # Legacy fallback
        import uuid
        mid = str(uuid.uuid4())[:8]
        entry = {
            "id": mid,
            "content": content,
            "metadata": metadata,
            "created_at": time.time(),
        }
        self._legacy_store.append(entry)
        self._save_legacy()
        return mid

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> List[MemoryEntry]:
        """Semantic search over memories."""
        if self._mem0 is not None:
            try:
                results = self._mem0.search(
                    query,
                    user_id=self.user_id,
                    agent_id=self.agent_id,
                    limit=limit,
                )
                entries = []
                for r in results:
                    if isinstance(r, dict):
                        entries.append(MemoryEntry(
                            id=r.get("id", ""),
                            content=r.get("memory", r.get("content", "")),
                            metadata=r.get("metadata", {}),
                            score=r.get("score", 0.0),
                            source="mem0",
                        ))
                return entries
            except Exception as e:
                logger.error(f"[Mem0] search failed, falling back: {e}")

        # Legacy keyword search
        query_lower = query.lower()
        scored: List[MemoryEntry] = []
        for item in self._legacy_store:
            content = item.get("content", "")
            content_lower = content.lower()
            # Simple relevance: count keyword overlap
            overlap = sum(1 for w in query_lower.split() if w in content_lower)
            if overlap > 0:
                scored.append(MemoryEntry(
                    id=item.get("id", ""),
                    content=content,
                    metadata=item.get("metadata", {}),
                    score=overlap / max(len(query_lower.split()), 1),
                    source="legacy",
                ))
        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:limit]

    def get_all(self, limit: int = 100) -> List[MemoryEntry]:
        """Return all stored memories (most recent first)."""
        if self._mem0 is not None:
            try:
                results = self._mem0.get_all(
                    user_id=self.user_id,
                    agent_id=self.agent_id,
                )
                entries = []
                for r in (results or []):
                    if isinstance(r, dict):
                        entries.append(MemoryEntry(
                            id=r.get("id", ""),
                            content=r.get("memory", r.get("content", "")),
                            metadata=r.get("metadata", {}),
                            source="mem0",
                        ))
                return entries[:limit]
            except Exception as e:
                logger.error(f"[Mem0] get_all failed: {e}")

        return [
            MemoryEntry(
                id=item.get("id", ""),
                content=item.get("content", ""),
                metadata=item.get("metadata", {}),
                source="legacy",
                created_at=item.get("created_at", 0),
            )
            for item in self._legacy_store[-limit:]
        ]

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        if self._mem0 is not None:
            try:
                self._mem0.delete(memory_id)
                return True
            except Exception as e:
                logger.error(f"[Mem0] delete failed: {e}")

        before = len(self._legacy_store)
        self._legacy_store = [
            e for e in self._legacy_store if e.get("id") != memory_id
        ]
        if len(self._legacy_store) < before:
            self._save_legacy()
            return True
        return False

    def build_context_prompt(self, query: str, max_memories: int = 5) -> str:
        """
        Build a context-injection prompt from relevant memories.

        Suitable for prepending to the system prompt.
        """
        memories = self.search(query, limit=max_memories)
        if not memories:
            return ""

        lines = ["## Memory Context"]
        for m in memories:
            lines.append(f"- {m.content}")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostics."""
        backend = "mem0" if self._mem0 is not None else "legacy"
        count = len(self._legacy_store) if self._mem0 is None else "unknown"
        return {
            "backend": backend,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "memory_count": count,
        }

    # -- Legacy persistence --

    def _load_legacy(self) -> None:
        try:
            path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), self.LEGACY_FILE
            )
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._legacy_store = data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[Mem0] Legacy load failed: {e}")

    def _save_legacy(self) -> None:
        try:
            path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), self.LEGACY_FILE
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._legacy_store, f, indent=2)
        except Exception as e:
            logger.error(f"[Mem0] Legacy save failed: {e}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[Mem0Adapter] = None


def get_mem0_adapter(
    user_id: str = "default",
    agent_id: str = "lada",
) -> Mem0Adapter:
    """Get or create the global Mem0Adapter instance."""
    global _instance
    if _instance is None:
        _instance = Mem0Adapter(user_id=user_id, agent_id=agent_id)
    return _instance
