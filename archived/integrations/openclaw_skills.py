"""LADA OpenClaw Skills Loader

Load and execute SKILL.md format skills from local directory.

Features:
- Load SKILL.md files from skills directory
- Parse skill triggers and actions
- Hot-reload on file changes
- ClawHub-compatible format
- Skill installation from URL

SKILL.md format:
```markdown
---
name: skill_name
version: 1.0.0
author: author_name
triggers: ["trigger phrase", "another trigger"]
tags: ["category", "type"]
---

# Skill Title

Description of the skill.

## Actions

### action_name(param1, param2)
Description of what this action does.

## Examples
- "trigger phrase" → action_name("value")
```

Environment variables:
- LADA_SKILLS_DIR: Skills directory (default: ~/.lada/skills)
- LADA_SKILLS_HOTRELOAD: Enable hot-reload (default: true)

Usage:
    from integrations.openclaw_skills import SkillsManager
    
    skills = SkillsManager()
    skills.load_all()
    
    # Find skill for command
    skill, action = skills.match("search for python tutorials")
    if skill:
        result = await skills.execute(skill, action, {"query": "python tutorials"})
"""

from __future__ import annotations

import os
import re
import yaml
import json
import asyncio
import logging
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Optional dependency for hot-reload
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    Observer = None
    FileSystemEventHandler = object
    WATCHDOG_AVAILABLE = False


@dataclass
class SkillAction:
    """Represents a skill action/function."""
    name: str
    description: str
    parameters: List[str] = field(default_factory=list)
    handler: Optional[Callable] = None


@dataclass
class Skill:
    """Represents a loaded skill."""
    name: str
    version: str
    author: str
    description: str
    triggers: List[str]
    tags: List[str]
    actions: Dict[str, SkillAction]
    path: Path
    enabled: bool = True
    
    @classmethod
    def from_markdown(cls, content: str, path: Path) -> Optional["Skill"]:
        """Parse skill from SKILL.md content.
        
        Args:
            content: Markdown content
            path: Path to skill file
            
        Returns:
            Skill object or None
        """
        try:
            # Extract YAML frontmatter
            frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not frontmatter_match:
                logger.warning(f"[Skills] No frontmatter in {path}")
                return None
            
            frontmatter = yaml.safe_load(frontmatter_match.group(1))
            body = content[frontmatter_match.end():]
            
            # Extract description (first paragraph after title)
            desc_match = re.search(r'^#[^\n]+\n+([^\n#]+)', body, re.MULTILINE)
            description = desc_match.group(1).strip() if desc_match else ""
            
            # Extract actions
            actions = {}
            action_pattern = r'###\s+(\w+)\(([^)]*)\)\s*\n([^\n#]*)'
            for match in re.finditer(action_pattern, body):
                action_name = match.group(1)
                params = [p.strip() for p in match.group(2).split(',') if p.strip()]
                action_desc = match.group(3).strip()
                
                actions[action_name] = SkillAction(
                    name=action_name,
                    description=action_desc,
                    parameters=params,
                )
            
            return cls(
                name=frontmatter.get("name", path.stem),
                version=frontmatter.get("version", "1.0.0"),
                author=frontmatter.get("author", "unknown"),
                description=description,
                triggers=frontmatter.get("triggers", []),
                tags=frontmatter.get("tags", []),
                actions=actions,
                path=path,
            )
            
        except Exception as e:
            logger.error(f"[Skills] Failed to parse {path}: {e}")
            return None


class SkillsFileHandler(FileSystemEventHandler):
    """File system watcher for skill hot-reload."""
    
    def __init__(self, manager: "SkillsManager"):
        self.manager = manager
        self._debounce_tasks: Dict[str, asyncio.TimerHandle] = {}
    
    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".md"):
            self._schedule_reload(event.src_path)
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self._schedule_reload(event.src_path)
    
    def _schedule_reload(self, path: str):
        """Debounced reload."""
        if path in self._debounce_tasks:
            return
        
        def reload():
            self._debounce_tasks.pop(path, None)
            self.manager.reload_skill(Path(path))
        
        # Schedule reload after 500ms
        loop = asyncio.get_event_loop()
        handle = loop.call_later(0.5, reload)
        self._debounce_tasks[path] = handle


class SkillsManager:
    """Manager for loading and executing SKILL.md skills."""
    
    def __init__(self, skills_dir: Optional[Path] = None, hot_reload: bool = None):
        """Initialize skills manager.
        
        Args:
            skills_dir: Directory containing skills
            hot_reload: Enable hot-reload (default from env)
        """
        default_dir = Path.home() / ".lada" / "skills"
        self.skills_dir = skills_dir or Path(os.getenv("LADA_SKILLS_DIR", str(default_dir)))
        self.hot_reload = hot_reload if hot_reload is not None else \
            os.getenv("LADA_SKILLS_HOTRELOAD", "true").lower() == "true"
        
        self.skills: Dict[str, Skill] = {}
        self._trigger_index: Dict[str, Tuple[str, str]] = {}  # trigger phrase -> (skill_name, action)
        self._observer = None
        
        # Ensure skills directory exists
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[Skills] Manager init: {self.skills_dir}")
    
    def load_all(self) -> int:
        """Load all skills from directory.
        
        Returns:
            Number of skills loaded
        """
        count = 0
        
        # Find all SKILL.md files
        for skill_file in self.skills_dir.rglob("SKILL.md"):
            if self._load_skill_file(skill_file):
                count += 1
        
        # Also check for *.skill.md files
        for skill_file in self.skills_dir.rglob("*.skill.md"):
            if self._load_skill_file(skill_file):
                count += 1
        
        # Build trigger index
        self._build_trigger_index()
        
        # Start hot-reload if enabled
        if self.hot_reload and WATCHDOG_AVAILABLE:
            self._start_watcher()
        
        logger.info(f"[Skills] Loaded {count} skills")
        return count
    
    def _load_skill_file(self, path: Path) -> bool:
        """Load skill from file.
        
        Args:
            path: Path to skill file
            
        Returns:
            True if loaded successfully
        """
        try:
            content = path.read_text(encoding="utf-8")
            skill = Skill.from_markdown(content, path)
            
            if skill:
                self.skills[skill.name] = skill
                
                # Try to load Python handler
                handler_path = path.parent / "skill.py"
                if handler_path.exists():
                    self._load_skill_handler(skill, handler_path)
                
                logger.debug(f"[Skills] Loaded: {skill.name} ({len(skill.actions)} actions)")
                return True
                
        except Exception as e:
            logger.error(f"[Skills] Failed to load {path}: {e}")
        
        return False
    
    def _load_skill_handler(self, skill: Skill, handler_path: Path):
        """Load Python handler for skill.
        
        Args:
            skill: Skill object
            handler_path: Path to skill.py
        """
        try:
            spec = importlib.util.spec_from_file_location(
                f"skill_{skill.name}",
                handler_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Bind handlers to actions
            for action_name, action in skill.actions.items():
                if hasattr(module, action_name):
                    action.handler = getattr(module, action_name)
                    logger.debug(f"[Skills] Bound handler: {skill.name}.{action_name}")
                    
        except Exception as e:
            logger.warning(f"[Skills] Handler load failed for {skill.name}: {e}")
    
    def _build_trigger_index(self):
        """Build index of trigger phrases."""
        self._trigger_index.clear()
        
        for skill in self.skills.values():
            if not skill.enabled:
                continue
            
            for trigger in skill.triggers:
                # Normalize trigger
                key = trigger.lower().strip()
                
                # Map to first action by default
                first_action = next(iter(skill.actions.keys()), None)
                if first_action:
                    self._trigger_index[key] = (skill.name, first_action)
    
    def _start_watcher(self):
        """Start file watcher for hot-reload."""
        if not WATCHDOG_AVAILABLE:
            return
        
        self._observer = Observer()
        handler = SkillsFileHandler(self)
        self._observer.schedule(handler, str(self.skills_dir), recursive=True)
        self._observer.start()
        
        logger.info("[Skills] Hot-reload enabled")
    
    def stop_watcher(self):
        """Stop file watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
    
    def reload_skill(self, path: Path):
        """Reload single skill.
        
        Args:
            path: Path to skill file
        """
        logger.info(f"[Skills] Reloading: {path}")
        
        # Remove old skill by path
        for name, skill in list(self.skills.items()):
            if skill.path == path:
                del self.skills[name]
                break
        
        # Load new version
        self._load_skill_file(path)
        self._build_trigger_index()
    
    def match(self, command: str) -> Optional[Tuple[Skill, SkillAction]]:
        """Find skill matching command.
        
        Args:
            command: User command text
            
        Returns:
            (Skill, SkillAction) or None
        """
        command_lower = command.lower().strip()
        
        # Exact trigger match
        if command_lower in self._trigger_index:
            skill_name, action_name = self._trigger_index[command_lower]
            skill = self.skills[skill_name]
            action = skill.actions[action_name]
            return (skill, action)
        
        # Prefix match
        for trigger, (skill_name, action_name) in self._trigger_index.items():
            if command_lower.startswith(trigger):
                skill = self.skills[skill_name]
                action = skill.actions[action_name]
                return (skill, action)
        
        return None
    
    async def execute(
        self, 
        skill: Skill, 
        action: SkillAction, 
        params: Dict[str, Any] = None
    ) -> Optional[Any]:
        """Execute skill action.
        
        Args:
            skill: Skill object
            action: Action to execute
            params: Action parameters
            
        Returns:
            Action result
        """
        if not action.handler:
            logger.warning(f"[Skills] No handler for {skill.name}.{action.name}")
            return None
        
        try:
            # Call handler
            if asyncio.iscoroutinefunction(action.handler):
                result = await action.handler(**(params or {}))
            else:
                result = action.handler(**(params or {}))
            
            logger.debug(f"[Skills] Executed: {skill.name}.{action.name}")
            return result
            
        except Exception as e:
            logger.error(f"[Skills] Execution failed: {skill.name}.{action.name}: {e}")
            return None
    
    def list_skills(self) -> List[Dict]:
        """List all loaded skills.
        
        Returns:
            List of skill info dicts
        """
        return [
            {
                "name": skill.name,
                "version": skill.version,
                "author": skill.author,
                "description": skill.description,
                "triggers": skill.triggers,
                "tags": skill.tags,
                "actions": list(skill.actions.keys()),
                "enabled": skill.enabled,
            }
            for skill in self.skills.values()
        ]
    
    def enable_skill(self, name: str) -> bool:
        """Enable skill.
        
        Args:
            name: Skill name
            
        Returns:
            True if enabled
        """
        if name in self.skills:
            self.skills[name].enabled = True
            self._build_trigger_index()
            return True
        return False
    
    def disable_skill(self, name: str) -> bool:
        """Disable skill.
        
        Args:
            name: Skill name
            
        Returns:
            True if disabled
        """
        if name in self.skills:
            self.skills[name].enabled = False
            self._build_trigger_index()
            return True
        return False
    
    async def install_from_url(self, url: str) -> bool:
        """Install skill from URL.
        
        Args:
            url: URL to skill (GitHub, etc.)
            
        Returns:
            True if installed
        """
        try:
            import aiohttp
            
            # Determine skill name from URL
            skill_name = url.rstrip("/").split("/")[-1].replace(".git", "")
            skill_dir = self.skills_dir / skill_name
            
            if skill_dir.exists():
                logger.warning(f"[Skills] Skill already exists: {skill_name}")
                return False
            
            # Clone or download
            if "github.com" in url:
                # Clone git repo
                import subprocess
                result = subprocess.run(
                    ["git", "clone", url, str(skill_dir)],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    raise Exception(f"Git clone failed: {result.stderr}")
            else:
                # Download SKILL.md directly
                skill_dir.mkdir(parents=True, exist_ok=True)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            content = await response.text()
                            (skill_dir / "SKILL.md").write_text(content)
                        else:
                            raise Exception(f"Download failed: {response.status}")
            
            # Load the new skill
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                if self._load_skill_file(skill_file):
                    self._build_trigger_index()
                    logger.info(f"[Skills] Installed: {skill_name}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"[Skills] Install failed: {e}")
            return False
    
    def uninstall(self, name: str) -> bool:
        """Uninstall skill.
        
        Args:
            name: Skill name
            
        Returns:
            True if uninstalled
        """
        if name not in self.skills:
            return False
        
        skill = self.skills[name]
        
        try:
            import shutil
            shutil.rmtree(skill.path.parent)
            del self.skills[name]
            self._build_trigger_index()
            logger.info(f"[Skills] Uninstalled: {name}")
            return True
            
        except Exception as e:
            logger.error(f"[Skills] Uninstall failed: {e}")
            return False


# Singleton instance
_manager: Optional[SkillsManager] = None


def get_skills_manager(**kwargs) -> SkillsManager:
    """Get or create skills manager singleton."""
    global _manager
    if _manager is None:
        _manager = SkillsManager(**kwargs)
    return _manager


def load_skills() -> int:
    """Load all skills (convenience function)."""
    return get_skills_manager().load_all()


def match_skill(command: str) -> Optional[Tuple[Skill, SkillAction]]:
    """Match command to skill (convenience function)."""
    return get_skills_manager().match(command)
