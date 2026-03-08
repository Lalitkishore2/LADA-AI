"""
LADA - Focus Modes
Perplexity-style focus modes that tailor search sources, AI behavior,
and output formatting based on query context.

Features:
- GENERAL: All sources, balanced behavior
- ACADEMIC: Scholar, arXiv, Wikipedia; cite papers
- CODE: StackOverflow, GitHub, MDN; code examples
- WRITING: Grammar/style focus; prose quality
- MATH: Wolfram Alpha; LaTeX-friendly output
- NEWS: Current events, news sources
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class FocusMode(Enum):
    GENERAL = "general"
    ACADEMIC = "academic"
    CODE = "code"
    WRITING = "writing"
    MATH = "math"
    NEWS = "news"


@dataclass
class FocusModeConfig:
    """Configuration for a focus mode"""
    name: str
    display_name: str
    icon: str  # Emoji or icon identifier
    description: str
    search_sources: List[str]  # Which search backends to use
    system_prompt_addition: str  # Added to AI system prompt
    output_format: str  # Hints for response formatting
    search_keywords: List[str] = field(default_factory=list)  # Extra keywords to add to searches
    allowed_domains: List[str] = field(default_factory=list)  # Domain whitelist (empty = all)


# Predefined focus mode configurations
FOCUS_CONFIGS: Dict[FocusMode, FocusModeConfig] = {
    FocusMode.GENERAL: FocusModeConfig(
        name="general",
        display_name="General",
        icon="G",
        description="Search all sources with balanced AI behavior",
        search_sources=["duckduckgo", "wikipedia"],
        system_prompt_addition="",
        output_format="balanced",
    ),
    FocusMode.ACADEMIC: FocusModeConfig(
        name="academic",
        display_name="Academic",
        icon="A",
        description="Scholarly sources, research papers, citations",
        search_sources=["duckduckgo", "wikipedia"],
        system_prompt_addition=(
            "ACADEMIC MODE: Focus on scholarly, peer-reviewed, and authoritative sources. "
            "Cite specific studies, papers, or academic sources when possible. "
            "Use formal academic language. Include DOIs or paper titles when referencing research. "
            "Distinguish between established facts and ongoing research debates."
        ),
        output_format="academic",
        search_keywords=["research", "study", "paper", "journal"],
        allowed_domains=["scholar.google.com", "arxiv.org", "wikipedia.org",
                         "ncbi.nlm.nih.gov", "nature.com", "sciencedirect.com"],
    ),
    FocusMode.CODE: FocusModeConfig(
        name="code",
        display_name="Code",
        icon="<>",
        description="Programming help with code examples",
        search_sources=["duckduckgo"],
        system_prompt_addition=(
            "CODE MODE: Focus on providing working code examples and technical solutions. "
            "Always include syntax-highlighted code blocks with the language specified. "
            "Explain code step by step. Mention common pitfalls and best practices. "
            "Prefer modern, idiomatic approaches. Include imports and dependencies."
        ),
        output_format="code",
        search_keywords=["programming", "code", "example", "stackoverflow"],
        allowed_domains=["stackoverflow.com", "github.com", "developer.mozilla.org",
                         "docs.python.org", "learn.microsoft.com"],
    ),
    FocusMode.WRITING: FocusModeConfig(
        name="writing",
        display_name="Writing",
        icon="W",
        description="Writing assistance and content creation",
        search_sources=["duckduckgo", "wikipedia"],
        system_prompt_addition=(
            "WRITING MODE: Focus on clear, engaging prose. Help with grammar, style, "
            "structure, and tone. When asked to write, produce polished content. "
            "Suggest improvements to existing text. Use varied sentence structures. "
            "Tailor tone to the specified audience (formal, casual, persuasive, etc.)."
        ),
        output_format="prose",
    ),
    FocusMode.MATH: FocusModeConfig(
        name="math",
        display_name="Math",
        icon="M",
        description="Mathematical calculations and explanations",
        search_sources=["duckduckgo", "wikipedia"],
        system_prompt_addition=(
            "MATH MODE: Show all mathematical work step by step. "
            "Use clear notation. For complex expressions, use code blocks for readability. "
            "Verify calculations. Explain the reasoning behind each step. "
            "Include formulas and their derivations when relevant."
        ),
        output_format="math",
        search_keywords=["math", "formula", "calculation", "theorem"],
    ),
    FocusMode.NEWS: FocusModeConfig(
        name="news",
        display_name="News",
        icon="N",
        description="Current events and latest news",
        search_sources=["duckduckgo"],
        system_prompt_addition=(
            "NEWS MODE: Focus on current events and recent developments. "
            "Always mention dates and sources. Present multiple perspectives on controversial topics. "
            "Distinguish between facts, analysis, and opinion. "
            "Note when information might be outdated."
        ),
        output_format="news",
        search_keywords=["news", "latest", "today", "update"],
        allowed_domains=["reuters.com", "apnews.com", "bbc.com",
                         "nytimes.com", "theguardian.com"],
    ),
}


class FocusModeManager:
    """
    Manages focus modes for the AI assistant.
    Configures search sources, system prompts, and output formatting.
    """

    def __init__(self):
        self.current_mode: FocusMode = FocusMode.GENERAL
        self.configs = FOCUS_CONFIGS.copy()

    def set_mode(self, mode: FocusMode):
        """Set the active focus mode."""
        self.current_mode = mode
        logger.info(f"[FocusMode] Switched to: {mode.value}")

    def set_mode_by_name(self, name: str) -> bool:
        """Set focus mode by string name. Returns True on success."""
        try:
            mode = FocusMode(name.lower())
            self.set_mode(mode)
            return True
        except ValueError:
            logger.warning(f"[FocusMode] Unknown mode: {name}")
            return False

    def get_current_mode(self) -> FocusMode:
        return self.current_mode

    def get_current_config(self) -> FocusModeConfig:
        return self.configs[self.current_mode]

    def get_system_prompt_addition(self) -> str:
        """Get the system prompt addition for the current mode."""
        return self.configs[self.current_mode].system_prompt_addition

    def get_search_sources(self) -> List[str]:
        """Get search sources for the current mode."""
        return self.configs[self.current_mode].search_sources

    def enhance_search_query(self, query: str) -> str:
        """Add mode-specific keywords to a search query."""
        config = self.configs[self.current_mode]
        if not config.search_keywords:
            return query

        # Only add keywords if they're not already in the query
        q_lower = query.lower()
        additions = [kw for kw in config.search_keywords if kw not in q_lower]
        if additions:
            return f"{query} {' '.join(additions[:2])}"
        return query

    def get_all_modes(self) -> List[Dict[str, str]]:
        """Get list of all available modes for UI display."""
        return [
            {
                'name': mode.value,
                'display_name': config.display_name,
                'icon': config.icon,
                'description': config.description,
                'active': mode == self.current_mode,
            }
            for mode, config in self.configs.items()
        ]

    def auto_detect_mode(self, query: str) -> Optional[FocusMode]:
        """
        Auto-detect the best focus mode based on query content.
        Returns None if no strong signal detected (stay in current mode).
        """
        q = query.lower()

        # Code detection
        code_signals = ['code', 'function', 'class', 'bug', 'error', 'python',
                        'javascript', 'html', 'css', 'api', 'debug', 'compile',
                        'import', 'library', 'framework', 'syntax']
        if sum(1 for s in code_signals if s in q) >= 2:
            return FocusMode.CODE

        # Academic detection
        academic_signals = ['research', 'study', 'paper', 'journal', 'thesis',
                           'peer-reviewed', 'citation', 'methodology', 'hypothesis',
                           'literature review', 'abstract']
        if sum(1 for s in academic_signals if s in q) >= 2:
            return FocusMode.ACADEMIC

        # Math detection
        math_signals = ['calculate', 'equation', 'formula', 'integral', 'derivative',
                       'solve', 'math', 'algebra', 'geometry', 'statistics',
                       'probability', 'matrix']
        if sum(1 for s in math_signals if s in q) >= 2:
            return FocusMode.MATH

        # News detection
        news_signals = ['news', 'latest', 'breaking', 'today', 'yesterday',
                       'election', 'market', 'announced', 'report']
        if sum(1 for s in news_signals if s in q) >= 2:
            return FocusMode.NEWS

        # Writing detection
        writing_signals = ['write', 'essay', 'article', 'draft', 'edit',
                          'proofread', 'rewrite', 'tone', 'paragraph']
        if sum(1 for s in writing_signals if s in q) >= 2:
            return FocusMode.WRITING

        return None


# Singleton
_focus_manager = None


def get_focus_manager() -> FocusModeManager:
    """Get or create focus mode manager instance."""
    global _focus_manager
    if _focus_manager is None:
        _focus_manager = FocusModeManager()
    return _focus_manager
