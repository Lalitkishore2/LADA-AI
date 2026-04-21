"""OpenClaw SKILL.md compatibility adapter.

Converts SKILL.md metadata into a plugin-manifest-compatible dictionary
that can be consumed by the plugin registry.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DESCRIPTION_RE = re.compile(r"^#[^\n]+\n+([^\n#]+)", re.MULTILINE)
_ACTION_RE = re.compile(r"^###\s+([A-Za-z_][\w]*)\(([^)]*)\)\s*\n([^\n#]*)", re.MULTILINE)


def parse_skill_manifest(
    *,
    skill_path: Path,
    plugin_dir: Path,
    yaml_loader: Optional[Callable[[str], Any]] = None,
    default_plugin_api_version: str = "1",
) -> Optional[Dict[str, Any]]:
    """Parse a SKILL.md file into a plugin-manifest-compatible dictionary."""
    try:
        content = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[OpenClawSkillAdapter] Failed reading {skill_path}: {e}")
        return None

    frontmatter_match = _FRONTMATTER_RE.match(content)
    if not frontmatter_match:
        logger.warning(f"[OpenClawSkillAdapter] SKILL.md frontmatter missing: {skill_path}")
        return None

    frontmatter_text = frontmatter_match.group(1)
    frontmatter: Dict[str, Any] = _parse_frontmatter(frontmatter_text, yaml_loader)

    body = content[frontmatter_match.end():]
    description = _extract_description(body) or str(frontmatter.get("description", ""))
    actions = _extract_actions(body)

    triggers = _normalize_list(frontmatter.get("triggers", []))
    capabilities = []
    for action_name, action_desc in actions:
        keywords = list(triggers) if triggers else [action_name.replace("_", " ")]
        capabilities.append(
            {
                "intent": action_name,
                "keywords": keywords,
                "handler": action_name,
                "description": action_desc,
            }
        )

    plugin_api_version = frontmatter.get(
        "plugin_api_version",
        frontmatter.get("api_version", default_plugin_api_version),
    )

    return {
        "name": str(frontmatter.get("name") or plugin_dir.name),
        "version": str(frontmatter.get("version", "1.0.0")),
        "description": description,
        "author": str(frontmatter.get("author", "unknown")),
        "entry_point": _resolve_entry_point(frontmatter, plugin_dir),
        "class_name": str(frontmatter.get("class_name", "")),
        "capabilities": capabilities,
        "dependencies": _normalize_list(frontmatter.get("dependencies", [])),
        "permissions": _normalize_list(frontmatter.get("permissions", [])),
        "plugin_api_version": str(plugin_api_version or default_plugin_api_version),
        "min_lada_version": str(frontmatter.get("min_lada_version", "")),
        "max_lada_version": str(frontmatter.get("max_lada_version", "")),
        "enabled": _parse_bool(frontmatter.get("enabled", True), default=True),
    }


def _parse_frontmatter(text: str, yaml_loader: Optional[Callable[[str], Any]]) -> Dict[str, Any]:
    if yaml_loader:
        try:
            loaded = yaml_loader(text) or {}
            if isinstance(loaded, dict):
                return loaded
        except Exception as e:
            logger.warning(f"[OpenClawSkillAdapter] YAML frontmatter parse failed: {e}")

    return _parse_frontmatter_fallback(text)


def _parse_frontmatter_fallback(text: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    active_list_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if ":" in stripped and not stripped.startswith("-"):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if not value:
                parsed[key] = []
                active_list_key = key
                continue

            coerced = _coerce_scalar(value)
            parsed[key] = coerced
            active_list_key = key if isinstance(coerced, list) else None
            continue

        if stripped.startswith("- ") and active_list_key:
            parsed.setdefault(active_list_key, [])
            current = parsed.get(active_list_key)
            if not isinstance(current, list):
                current = [current]
                parsed[active_list_key] = current
            current.append(_coerce_scalar(stripped[2:].strip()))
            continue

        active_list_key = None

    return parsed


def _coerce_scalar(value: str) -> Any:
    text = value.strip()
    lower = text.lower()

    if lower == "true":
        return True
    if lower == "false":
        return False

    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text.replace("'", '"'))
        except Exception:
            return [text]

    if (text.startswith("\"") and text.endswith("\"")) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]

    return text


def _extract_description(body: str) -> str:
    match = _DESCRIPTION_RE.search(body)
    return match.group(1).strip() if match else ""


def _extract_actions(body: str) -> List[tuple[str, str]]:
    actions: List[tuple[str, str]] = []
    for match in _ACTION_RE.finditer(body):
        action_name = match.group(1).strip()
        action_desc = match.group(3).strip()
        actions.append((action_name, action_desc))
    return actions


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if cleaned.startswith("[") and cleaned.endswith("]"):
            try:
                parsed = json.loads(cleaned.replace("'", '"'))
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        if "," in cleaned:
            return [part.strip() for part in cleaned.split(",") if part.strip()]
        return [cleaned]

    return [str(value).strip()]


def _parse_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False

    return default


def _resolve_entry_point(frontmatter: Dict[str, Any], plugin_dir: Path) -> str:
    declared = str(frontmatter.get("entry_point", "")).strip()
    if declared:
        return declared

    for candidate in ("skill.py", "plugin.py", "main.py"):
        if (plugin_dir / candidate).exists():
            return candidate

    return "skill.py"
