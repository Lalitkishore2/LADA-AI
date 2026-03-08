"""
LADA - Research Spaces
Perplexity-style organized research collections with persistent knowledge context.

Features:
- Named research spaces with descriptions
- Pin conversations, sources, and notes to spaces
- Upload files as persistent context
- Space-aware AI context injection
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SpaceNote:
    """A note within a research space"""
    content: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SpaceSource:
    """A pinned source/reference"""
    title: str
    url: str = ""
    snippet: str = ""
    pinned_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ResearchSpace:
    """A named research collection"""
    id: str
    name: str
    description: str = ""
    conversations: List[str] = field(default_factory=list)  # Conversation IDs
    sources: List[Dict[str, str]] = field(default_factory=list)
    notes: List[Dict[str, str]] = field(default_factory=list)
    files: List[str] = field(default_factory=list)  # File paths
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchSpace':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SpaceManager:
    """
    Manages research spaces for organized knowledge collections.
    """

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.path.dirname(os.path.dirname(__file__))) / 'data' / 'spaces'

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.spaces: Dict[str, ResearchSpace] = {}
        self._load_spaces()

    def _load_spaces(self):
        """Load all spaces from disk."""
        for space_dir in self.data_dir.iterdir():
            if space_dir.is_dir():
                meta_file = space_dir / 'space.json'
                if meta_file.exists():
                    try:
                        with open(meta_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        space = ResearchSpace.from_dict(data)
                        self.spaces[space.id] = space
                    except Exception as e:
                        logger.error(f"[Spaces] Failed to load {space_dir.name}: {e}")

        logger.info(f"[Spaces] Loaded {len(self.spaces)} spaces")

    def _save_space(self, space: ResearchSpace):
        """Save a space to disk."""
        space_dir = self.data_dir / space.id
        space_dir.mkdir(parents=True, exist_ok=True)
        with open(space_dir / 'space.json', 'w', encoding='utf-8') as f:
            json.dump(space.to_dict(), f, indent=2)

    def create_space(self, name: str, description: str = "") -> ResearchSpace:
        """Create a new research space."""
        space_id = f"space_{int(time.time())}_{name.lower().replace(' ', '_')[:20]}"
        space = ResearchSpace(id=space_id, name=name, description=description)
        self.spaces[space_id] = space
        self._save_space(space)
        logger.info(f"[Spaces] Created: {name} ({space_id})")
        return space

    def delete_space(self, space_id: str) -> bool:
        """Delete a research space."""
        if space_id in self.spaces:
            del self.spaces[space_id]
            space_dir = self.data_dir / space_id
            if space_dir.exists():
                import shutil
                shutil.rmtree(space_dir, ignore_errors=True)
            return True
        return False

    def add_conversation(self, space_id: str, conversation_id: str) -> bool:
        """Add a conversation to a space."""
        space = self.spaces.get(space_id)
        if not space:
            return False
        if conversation_id not in space.conversations:
            space.conversations.append(conversation_id)
            space.updated_at = datetime.now().isoformat()
            self._save_space(space)
        return True

    def pin_source(self, space_id: str, title: str, url: str = "",
                   snippet: str = "") -> bool:
        """Pin a source/reference to a space."""
        space = self.spaces.get(space_id)
        if not space:
            return False
        space.sources.append({
            'title': title, 'url': url, 'snippet': snippet,
            'pinned_at': datetime.now().isoformat(),
        })
        space.updated_at = datetime.now().isoformat()
        self._save_space(space)
        return True

    def add_note(self, space_id: str, content: str) -> bool:
        """Add a note to a space."""
        space = self.spaces.get(space_id)
        if not space:
            return False
        space.notes.append({
            'content': content,
            'created_at': datetime.now().isoformat(),
        })
        space.updated_at = datetime.now().isoformat()
        self._save_space(space)
        return True

    def add_file(self, space_id: str, file_path: str) -> bool:
        """Add a file reference to a space."""
        space = self.spaces.get(space_id)
        if not space:
            return False
        if file_path not in space.files:
            space.files.append(file_path)
            space.updated_at = datetime.now().isoformat()
            self._save_space(space)
        return True

    def get_context(self, space_id: str) -> str:
        """
        Build AI context from all space contents.
        Used to inject space knowledge into AI queries.
        """
        space = self.spaces.get(space_id)
        if not space:
            return ""

        parts = [f"[Research Space: {space.name}]"]

        if space.description:
            parts.append(f"Topic: {space.description}")

        if space.notes:
            parts.append("\nResearch Notes:")
            for note in space.notes[-5:]:  # Last 5 notes
                parts.append(f"- {note['content'][:200]}")

        if space.sources:
            parts.append("\nPinned Sources:")
            for src in space.sources[-5:]:
                parts.append(f"- {src['title']}: {src.get('snippet', '')[:100]}")

        return "\n".join(parts)

    def list_spaces(self) -> List[Dict[str, Any]]:
        """List all spaces for UI display."""
        return [
            {
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'conversations': len(s.conversations),
                'sources': len(s.sources),
                'notes': len(s.notes),
                'files': len(s.files),
                'updated_at': s.updated_at,
            }
            for s in sorted(self.spaces.values(),
                           key=lambda x: x.updated_at, reverse=True)
        ]

    def search_within_space(self, space_id: str, query: str) -> List[Dict[str, Any]]:
        """Search notes and sources within a space."""
        space = self.spaces.get(space_id)
        if not space:
            return []

        q = query.lower()
        results = []

        for note in space.notes:
            if q in note.get('content', '').lower():
                results.append({'type': 'note', 'content': note['content'][:200]})

        for src in space.sources:
            if q in src.get('title', '').lower() or q in src.get('snippet', '').lower():
                results.append({'type': 'source', 'title': src['title'], 'url': src.get('url', '')})

        return results


# Singleton
_space_manager = None


def get_space_manager(data_dir: Optional[str] = None) -> SpaceManager:
    """Get or create space manager instance."""
    global _space_manager
    if _space_manager is None:
        _space_manager = SpaceManager(data_dir=data_dir)
    return _space_manager
