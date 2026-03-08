"""
AI-Powered Skill Generator for LADA

Generates complete plugins from natural language descriptions using the AI router.
Each generated skill includes a YAML manifest and Python handler, saved to plugins/.
Integrates with the existing plugin system for hot-reload.

Usage:
    generator = SkillGenerator(ai_router=router)
    result = generator.generate("A skill that tells programming jokes")
    # Creates plugins/joke_teller/ with manifest.yaml + plugin.py
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Templates ────────────────────────────────────────────────────────────────

MANIFEST_TEMPLATE = """name: {name}
version: "1.0.0"
description: "{description}"
author: "LADA Skill Generator"
generated: true
created_at: "{created_at}"

triggers:
{triggers_yaml}

permissions:
  - basic

entry_point: plugin.py
"""

HANDLER_TEMPLATE = '''"""
Auto-generated LADA skill: {name}
{description}
"""

import logging

logger = logging.getLogger(__name__)


class {class_name}:
    """Plugin handler for {name}."""

    def __init__(self):
        self.name = "{name}"
        self.description = "{description}"

    def handle(self, command: str, context: dict = None) -> str:
        """Process a command and return a response.

        Args:
            command: The user's input text.
            context: Optional context dict with session info.

        Returns:
            Response string.
        """
        context = context or {{}}
{handler_body}

    def get_info(self) -> dict:
        """Return plugin metadata."""
        return {{
            "name": self.name,
            "description": self.description,
            "version": "1.0.0",
            "generated": True,
        }}


# Factory function for plugin system
def create_plugin():
    """Create and return a plugin instance."""
    return {class_name}()
'''

GENERATION_PROMPT = """You are a plugin code generator for LADA, a Python AI assistant.

Given a skill description, return a JSON object with these fields:
- "name": short snake_case identifier (e.g., "joke_teller")
- "display_name": human-readable name (e.g., "Joke Teller")
- "description": one-line description
- "triggers": list of 3-5 trigger phrases that should activate this skill
- "handler_body": Python code (indented 8 spaces) for the handle() method body. It receives `command` (str) and `context` (dict). Must return a string. Use only stdlib imports. Keep it simple and functional.

IMPORTANT:
- handler_body must be valid Python, indented with 8 spaces
- Return ONLY the JSON object, no markdown or explanation
- Keep handler_body under 30 lines
- Do not use external APIs or require network access

Skill description: {description}
"""


class SkillGenerator:
    """Generates LADA plugins from natural language descriptions."""

    def __init__(self, ai_router=None):
        self.ai_router = ai_router
        self.plugins_dir = Path(__file__).parent.parent / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, description: str, name: str = None) -> dict:
        """Generate a complete plugin from a natural language description.

        Args:
            description: What the skill should do.
            name: Optional override for the plugin name.

        Returns:
            Dict with keys: name, path, manifest, code, success, error.
        """
        result = {"name": None, "path": None, "manifest": None,
                  "code": None, "success": False, "error": None}

        if not self.ai_router:
            result["error"] = "No AI router available"
            return result

        # Step 1: Ask AI to design the skill
        try:
            prompt = GENERATION_PROMPT.format(description=description)
            ai_response = self.ai_router.query(prompt)
            if not ai_response:
                result["error"] = "AI returned empty response"
                return result
        except Exception as e:
            result["error"] = f"AI query failed: {e}"
            return result

        # Step 2: Parse the AI response
        try:
            spec = self._parse_spec(ai_response)
            if not spec:
                result["error"] = "Could not parse AI response as JSON"
                return result
        except Exception as e:
            result["error"] = f"Parse error: {e}"
            return result

        skill_name = name or spec.get("name", "generated_skill")
        skill_name = re.sub(r'[^a-z0-9_]', '_', skill_name.lower().strip())

        # Step 3: Generate manifest
        triggers = spec.get("triggers", [f"run {skill_name}"])
        triggers_yaml = "\n".join(f'  - "{t}"' for t in triggers)
        manifest = MANIFEST_TEMPLATE.format(
            name=spec.get("display_name", skill_name),
            description=spec.get("description", description),
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            triggers_yaml=triggers_yaml,
        )

        # Step 4: Generate handler code
        class_name = "".join(
            w.capitalize() for w in skill_name.split("_")
        ) + "Plugin"
        handler_body = spec.get(
            "handler_body",
            '        return "Skill not implemented yet"'
        )
        if not handler_body.startswith("        "):
            lines = handler_body.strip().split("\n")
            handler_body = "\n".join("        " + line for line in lines)

        code = HANDLER_TEMPLATE.format(
            name=spec.get("display_name", skill_name),
            description=spec.get("description", description),
            class_name=class_name,
            handler_body=handler_body,
        )

        # Step 5: Save to plugins directory
        try:
            skill_dir = self.plugins_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            (skill_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")
            (skill_dir / "plugin.py").write_text(code, encoding="utf-8")

            result.update({
                "name": skill_name,
                "path": str(skill_dir),
                "manifest": manifest,
                "code": code,
                "success": True,
            })
            logger.info(f"Generated skill '{skill_name}' at {skill_dir}")

        except Exception as e:
            result["error"] = f"File write error: {e}"

        return result

    def _parse_spec(self, text: str) -> Optional[dict]:
        """Parse AI response into a skill specification dict."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Extract JSON from mixed text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    def list_generated(self) -> list:
        """List all generated skills in the plugins directory."""
        skills = []
        if not self.plugins_dir.exists():
            return skills

        for d in sorted(self.plugins_dir.iterdir()):
            if d.is_dir() and (d / "manifest.yaml").exists():
                manifest = (d / "manifest.yaml").read_text(encoding="utf-8")
                skills.append({
                    "name": d.name,
                    "path": str(d),
                    "generated": "generated: true" in manifest,
                    "has_manifest": True,
                    "has_code": (d / "plugin.py").exists(),
                })

        return skills

    def delete_skill(self, name: str) -> bool:
        """Delete a generated skill by name."""
        import shutil
        skill_dir = self.plugins_dir / name
        if skill_dir.exists() and skill_dir.is_dir():
            shutil.rmtree(skill_dir)
            logger.info(f"Deleted skill: {name}")
            return True
        return False


def create_skill_generator(ai_router=None) -> SkillGenerator:
    """Module-level factory."""
    return SkillGenerator(ai_router=ai_router)
