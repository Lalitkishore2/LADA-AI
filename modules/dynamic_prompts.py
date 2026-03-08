"""
LADA v11.0 - Dynamic Runtime System Prompts
Build system prompts dynamically from file-based components at runtime.

Instead of hardcoded personality templates, assembles prompts from:
- SOUL.md: Core personality and values
- IDENTITY.md: Professional identity and expertise
- USER.md: User profile, preferences, history
- CONTEXT.md: Current session context
- MODE.md: Active mode-specific instructions

Supports hot-reloading of prompt components without restart.
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class DynamicPromptBuilder:
    """
    Builds system prompts dynamically from file-based components.

    Features:
    - File-based prompt components (Markdown)
    - Hot-reload on file change (checks mtime)
    - Template variable interpolation
    - Mode-specific prompt assembly
    - Token-budget-aware truncation
    - Fallback to hardcoded defaults
    """

    PROMPT_DIR = "config/prompts"

    DEFAULT_COMPONENTS = {
        "SOUL.md": (
            "# LADA Soul\n\n"
            "You are LADA, a Language Agnostic Digital Assistant.\n"
            "You are helpful, knowledgeable, and professional.\n"
            "You combine the sophistication of JARVIS with genuine warmth.\n"
            "You care about the user's wellbeing and productivity.\n"
            "You are honest, direct, and never condescending.\n"
        ),
        "IDENTITY.md": (
            "# LADA Identity\n\n"
            "- Name: LADA (Language Agnostic Digital Assistant)\n"
            "- Role: AI-powered desktop assistant\n"
            "- Expertise: System control, automation, research, coding, scheduling\n"
            "- Capabilities: Voice interaction, browser control, file management, "
            "smart home, task planning, multi-agent collaboration\n"
            "- Languages: English, Tamil (Thanglish)\n"
        ),
        "USER.md": (
            "# User Profile\n\n"
            "- Preferences: Not yet learned\n"
            "- Communication style: Adaptive\n"
            "- Expertise level: General\n"
        ),
        "CONTEXT.md": (
            "# Session Context\n\n"
            "- Session start: {session_start}\n"
            "- Time: {current_time}\n"
            "- Active mode: {active_mode}\n"
            "- System status: Operational\n"
        ),
    }

    MODE_PROMPTS = {
        "jarvis": (
            "# JARVIS Mode\n\n"
            "Speak with a British, formal, sophisticated tone.\n"
            "Address the user as 'sir' or 'ma'am'.\n"
            "Be precise, measured, and occasionally witty.\n"
            "Channel the elegance of a premier AI butler.\n"
        ),
        "friday": (
            "# FRIDAY Mode\n\n"
            "Speak with a modern, efficient, professional tone.\n"
            "Be tech-forward and concise.\n"
            "Focus on data and actionable information.\n"
            "Occasionally show personality but stay focused.\n"
        ),
        "karen": (
            "# KAREN Mode\n\n"
            "Speak warmly and supportively.\n"
            "Be encouraging and friendly.\n"
            "Use casual-professional tone.\n"
            "Show genuine care for the user's experience.\n"
        ),
        "casual": (
            "# CASUAL Mode\n\n"
            "Be relaxed, fun, and conversational.\n"
            "Use informal language naturally.\n"
            "Keep things light but still helpful.\n"
            "Match the user's energy.\n"
        ),
    }

    def __init__(self, prompt_dir: Optional[str] = None):
        self.prompt_dir = prompt_dir or self.PROMPT_DIR
        os.makedirs(self.prompt_dir, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}  # filename -> {content, mtime}
        self._variables: Dict[str, str] = {}
        self._ensure_default_files()

    def _ensure_default_files(self):
        """Create default prompt files if they don't exist."""
        for filename, content in self.DEFAULT_COMPONENTS.items():
            filepath = os.path.join(self.prompt_dir, filename)
            if not os.path.exists(filepath):
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    logger.error(f"[Prompts] Failed to create {filename}: {e}")

        # Create mode files
        modes_dir = os.path.join(self.prompt_dir, "modes")
        os.makedirs(modes_dir, exist_ok=True)
        for mode_name, content in self.MODE_PROMPTS.items():
            filepath = os.path.join(modes_dir, f"{mode_name}.md")
            if not os.path.exists(filepath):
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    logger.error(f"[Prompts] Failed to create mode {mode_name}: {e}")

    def _read_component(self, filename: str) -> str:
        """Read a prompt component with caching and hot-reload."""
        filepath = os.path.join(self.prompt_dir, filename)

        if not os.path.exists(filepath):
            return self.DEFAULT_COMPONENTS.get(filename, "")

        try:
            mtime = os.path.getmtime(filepath)

            # Check cache
            cached = self._cache.get(filename)
            if cached and cached["mtime"] == mtime:
                return cached["content"]

            # Read and cache
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            self._cache[filename] = {"content": content, "mtime": mtime}
            return content

        except Exception as e:
            logger.error(f"[Prompts] Error reading {filename}: {e}")
            return self.DEFAULT_COMPONENTS.get(filename, "")

    def _read_mode(self, mode: str) -> str:
        """Read mode-specific prompt."""
        filepath = os.path.join(self.prompt_dir, "modes", f"{mode}.md")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        return self.MODE_PROMPTS.get(mode, "")

    def set_variable(self, key: str, value: str):
        """Set a template variable for interpolation."""
        self._variables[key] = value

    def set_variables(self, variables: Dict[str, str]):
        """Set multiple template variables."""
        self._variables.update(variables)

    def _interpolate(self, content: str) -> str:
        """Replace {variable} placeholders with values."""
        from datetime import datetime
        # Built-in variables
        defaults = {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_start": self._variables.get("session_start", datetime.now().strftime("%H:%M")),
            "active_mode": self._variables.get("active_mode", "karen"),
            "user_name": self._variables.get("user_name", "User"),
        }

        merged = {**defaults, **self._variables}

        for key, value in merged.items():
            content = content.replace(f"{{{key}}}", str(value))

        return content

    def build_system_prompt(self, mode: str = "karen",
                            include_context: bool = True,
                            include_user: bool = True,
                            extra_instructions: str = "",
                            max_tokens: int = 3000,
                            memory_context: str = "",
                            rag_context: str = "") -> str:
        """
        Assemble the full system prompt from components.

        Args:
            mode: Personality mode (jarvis, friday, karen, casual)
            include_context: Include session context
            include_user: Include user profile
            extra_instructions: Additional instructions to append
            max_tokens: Token budget for prompt
            memory_context: Relevant memories to inject
            rag_context: RAG knowledge base context to inject

        Returns:
            Complete system prompt string
        """
        self.set_variable("active_mode", mode)

        parts = []

        # Core personality
        soul = self._read_component("SOUL.md")
        parts.append(self._interpolate(soul))

        # Identity
        identity = self._read_component("IDENTITY.md")
        parts.append(self._interpolate(identity))

        # Mode-specific behavior
        mode_prompt = self._read_mode(mode)
        parts.append(self._interpolate(mode_prompt))

        # User profile
        if include_user:
            user = self._read_component("USER.md")
            parts.append(self._interpolate(user))

        # Session context
        if include_context:
            context = self._read_component("CONTEXT.md")
            parts.append(self._interpolate(context))

        # RAG context
        if rag_context:
            parts.append(f"\n# Knowledge Base Context\n{rag_context}")

        # Memory context
        if memory_context:
            parts.append(f"\n# Relevant Memories\n{memory_context}")

        # Extra instructions
        if extra_instructions:
            parts.append(f"\n# Additional Instructions\n{extra_instructions}")

        full_prompt = "\n\n".join(parts)

        # Token-budget truncation
        estimated_tokens = len(full_prompt.split()) * 1.3
        if estimated_tokens > max_tokens:
            words = full_prompt.split()
            max_words = int(max_tokens / 1.3)
            full_prompt = ' '.join(words[:max_words]) + "\n...[truncated for token budget]"

        return full_prompt

    def update_user_profile(self, key: str, value: str):
        """Update a field in the user profile file."""
        filepath = os.path.join(self.prompt_dir, "USER.md")
        try:
            content = self._read_component("USER.md")

            # Check if key exists and update, or append
            import re
            pattern = rf'^- {re.escape(key)}:.*$'
            new_line = f"- {key}: {value}"

            if re.search(pattern, content, re.MULTILINE):
                content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
            else:
                content = content.rstrip() + f"\n{new_line}\n"

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            # Invalidate cache
            self._cache.pop("USER.md", None)

        except Exception as e:
            logger.error(f"[Prompts] Failed to update user profile: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get prompt builder statistics."""
        return {
            "prompt_dir": self.prompt_dir,
            "cached_components": len(self._cache),
            "variables": dict(self._variables),
            "available_modes": list(self.MODE_PROMPTS.keys()),
        }


# Singleton
_prompt_builder: Optional[DynamicPromptBuilder] = None

def get_prompt_builder(prompt_dir: Optional[str] = None) -> DynamicPromptBuilder:
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = DynamicPromptBuilder(prompt_dir=prompt_dir)
    return _prompt_builder
