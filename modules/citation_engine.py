"""
LADA - Citation Engine
Perplexity-style inline citation system with source tracking.

Features:
- Numbered inline citations [1], [2], [3] in AI responses
- Source badge generation for GUI display
- Bibliography formatting
- Citation extraction and validation
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A single citation reference"""
    index: int
    title: str
    url: str
    domain: str
    snippet: str = ""


class CitationEngine:
    """
    Manages inline citations for AI-generated responses.

    Workflow:
    1. Sources are registered before AI query
    2. AI is instructed to use [N] markers
    3. Post-process AI response to validate/fix citations
    4. Generate bibliography and source badges
    """

    def __init__(self):
        self.citations: List[Citation] = []

    def register_sources(self, sources: List[Dict[str, str]]) -> str:
        """
        Register sources from deep research and return the citation instruction
        to prepend to AI context.

        Args:
            sources: List of dicts with 'index'/'title'/'url'/'domain'/'snippet' keys

        Returns:
            Formatted source context string for the AI
        """
        self.citations = []

        for s in sources:
            idx = int(s.get('index', len(self.citations) + 1))
            self.citations.append(Citation(
                index=idx,
                title=s.get('title', f'Source {idx}'),
                url=s.get('url', ''),
                domain=s.get('domain', ''),
                snippet=s.get('snippet', ''),
            ))

        return self._format_source_context()

    def _format_source_context(self) -> str:
        """Format registered sources as context for AI."""
        if not self.citations:
            return ""

        parts = []
        for c in self.citations:
            parts.append(f"[Source {c.index}: {c.title} ({c.domain})]\n{c.snippet}")

        return "\n\n".join(parts)

    def get_citation_instruction(self) -> str:
        """Return the system instruction for citation usage."""
        if not self.citations:
            return ""

        return (
            "CITATION RULES: When using information from the provided sources, "
            "add inline citations using [1], [2], etc. matching the source numbers. "
            "Place citations at the end of the sentence or claim they support. "
            "Synthesize across sources - don't just summarize one source at a time. "
            "If you're unsure about a fact, note it. Not every sentence needs a citation, "
            "only factual claims from the sources."
        )

    def post_process_response(self, response: str) -> str:
        """
        Validate and clean up citations in AI response.
        Removes references to non-existent source numbers.
        """
        if not self.citations or not response:
            return response

        valid_indices = {c.index for c in self.citations}
        max_idx = max(valid_indices) if valid_indices else 0

        def replace_citation(match):
            idx = int(match.group(1))
            if idx in valid_indices:
                return f"[{idx}]"
            # Remove invalid citations silently
            return ""

        # Fix citations: [N] format
        cleaned = re.sub(r'\[(\d+)\]', replace_citation, response)

        # Remove double spaces left by removed citations
        cleaned = re.sub(r'  +', ' ', cleaned)

        return cleaned.strip()

    def extract_used_citations(self, response: str) -> List[int]:
        """Extract which citation numbers were actually used in the response."""
        return sorted(set(
            int(m) for m in re.findall(r'\[(\d+)\]', response)
            if self.citations and int(m) <= len(self.citations)
        ))

    def get_bibliography(self, used_only: bool = True, response: str = "") -> str:
        """
        Generate a formatted bibliography.

        Args:
            used_only: If True, only include citations actually used in response
            response: The AI response to extract used citations from
        """
        if not self.citations:
            return ""

        if used_only and response:
            used = set(self.extract_used_citations(response))
            cites = [c for c in self.citations if c.index in used]
        else:
            cites = self.citations

        if not cites:
            return ""

        lines = ["\n---\n**Sources:**"]
        for c in cites:
            if c.url:
                lines.append(f"[{c.index}] [{c.title}]({c.url})")
            else:
                lines.append(f"[{c.index}] {c.title}")

        return "\n".join(lines)

    def get_source_badges(self, response: str = "") -> List[Dict[str, str]]:
        """
        Generate source badge data for GUI display.
        Returns only sources that were actually cited in the response.
        """
        if not self.citations:
            return []

        if response:
            used = set(self.extract_used_citations(response))
            cites = [c for c in self.citations if c.index in used]
        else:
            cites = self.citations

        return [
            {
                'index': str(c.index),
                'title': c.title[:50],
                'url': c.url,
                'domain': c.domain,
            }
            for c in cites
            if c.url
        ]

    def get_all_source_badges(self) -> List[Dict[str, str]]:
        """Get badge data for all registered sources (before response)."""
        return [
            {
                'index': str(c.index),
                'title': c.title[:50],
                'url': c.url,
                'domain': c.domain,
            }
            for c in self.citations
            if c.url
        ]


# Singleton
_citation_engine = None


def get_citation_engine() -> CitationEngine:
    """Get or create citation engine instance."""
    global _citation_engine
    if _citation_engine is None:
        _citation_engine = CitationEngine()
    return _citation_engine
