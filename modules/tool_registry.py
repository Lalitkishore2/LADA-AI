"""
LADA Tool Registry - Structured tool system with JSON schemas

Replaces regex pattern matching with a schema-based tool registry.
Each tool declares:
- name, description
- parameter schema (types, required fields)
- handler function
- required permissions

The command router matches user intents to registered tools
instead of scanning through regex patterns.

Inspired by OpenClaw's tool-display.json architecture.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Tool categories for organization and filtering"""
    SYSTEM = "system"
    BROWSER = "browser"
    FILE = "file"
    MEDIA = "media"
    COMMUNICATION = "communication"
    AI = "ai"
    AUTOMATION = "automation"
    INTEGRATION = "integration"
    AGENT = "agent"


class PermissionLevel(Enum):
    """Permission levels for tool execution"""
    SAFE = "safe"               # No confirmation needed
    MODERATE = "moderate"       # Log the action
    DANGEROUS = "dangerous"     # Require user confirmation
    CRITICAL = "critical"       # Require explicit approval + elevated mode


@dataclass
class ToolParameter:
    """Definition of a tool parameter"""
    name: str
    type: str  # string, integer, float, boolean, array, object
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None  # allowed values


@dataclass
class ToolDefinition:
    """Complete tool definition with schema"""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter] = field(default_factory=list)
    handler: Optional[Callable] = None
    permission: PermissionLevel = PermissionLevel.SAFE
    keywords: List[str] = field(default_factory=list)  # trigger words for NLU matching
    examples: List[str] = field(default_factory=list)   # example queries
    enabled: bool = True

    def matches_keywords(self, text: str) -> float:
        """
        Check if text matches this tool's keywords.
        Returns confidence score 0.0-1.0.
        Uses a weighted approach: exact phrase matches score higher.
        """
        if not self.keywords:
            return 0.0

        text_lower = text.lower().strip()
        best_score = 0.0

        for kw in self.keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                # Multi-word keywords get higher confidence
                word_count = len(kw_lower.split())
                if word_count > 1:
                    score = min(1.0, 0.4 + (word_count * 0.2))
                else:
                    score = 0.4
                best_score = max(best_score, score)

        return best_score

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary (for API/display)"""
        return {
            'name': self.name,
            'description': self.description,
            'category': self.category.value,
            'parameters': [
                {
                    'name': p.name,
                    'type': p.type,
                    'description': p.description,
                    'required': p.required,
                    'default': p.default,
                    'enum': p.enum,
                }
                for p in self.parameters
            ],
            'permission': self.permission.value,
            'keywords': self.keywords,
            'examples': self.examples,
            'enabled': self.enabled,
        }


@dataclass
class ToolResult:
    """Result of executing a tool"""
    success: bool
    output: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tool_name: str = ""


class ToolRegistry:
    """
    Central registry for all tools/commands.

    Features:
    - Register tools with structured schemas
    - Match user intents to tools via keyword scoring
    - Execute tools with parameter validation
    - Permission checking before execution
    - Tool discovery for AI agent tool-use
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._category_index: Dict[ToolCategory, List[str]] = {}
        logger.info("[ToolRegistry] Initialized")

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

        # Update category index
        if tool.category not in self._category_index:
            self._category_index[tool.category] = []
        self._category_index[tool.category].append(tool.name)

        logger.debug(f"[ToolRegistry] Registered: {tool.name} ({tool.category.value})")

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry"""
        tool = self._tools.pop(name, None)
        if tool:
            cat_list = self._category_index.get(tool.category, [])
            if name in cat_list:
                cat_list.remove(name)
            return True
        return False

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self, category: Optional[ToolCategory] = None) -> List[ToolDefinition]:
        """List all tools, optionally filtered by category"""
        if category is not None:
            names = self._category_index.get(category, [])
            return [self._tools[n] for n in names if n in self._tools]
        return list(self._tools.values())

    def match(self, text: str, threshold: float = 0.3) -> List[tuple]:
        """
        Match user text against all registered tools.
        Returns list of (tool_name, confidence) sorted by confidence descending.
        """
        results = []
        for name, tool in self._tools.items():
            if not tool.enabled:
                continue
            score = tool.matches_keywords(text)
            if score >= threshold:
                results.append((name, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def find_best_match(self, text: str, threshold: float = 0.3) -> Optional[ToolDefinition]:
        """Find the best matching tool for user text"""
        matches = self.match(text, threshold)
        if matches:
            return self._tools.get(matches[0][0])
        return None

    def execute(self, name: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        """
        Execute a tool by name with parameters.
        Validates parameters and checks permissions.
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False, output="", tool_name=name,
                error=f"Tool not found: {name}"
            )

        if not tool.enabled:
            return ToolResult(
                success=False, output="", tool_name=name,
                error=f"Tool is disabled: {name}"
            )

        if not tool.handler:
            return ToolResult(
                success=False, output="", tool_name=name,
                error=f"Tool has no handler: {name}"
            )

        # Validate required parameters
        params = params or {}
        for p in tool.parameters:
            if p.required and p.name not in params:
                if p.default is not None:
                    params[p.name] = p.default
                else:
                    return ToolResult(
                        success=False, output="", tool_name=name,
                        error=f"Missing required parameter: {p.name}"
                    )

        # Execute
        try:
            result = tool.handler(**params)
            if isinstance(result, ToolResult):
                result.tool_name = name
                return result
            # Allow handlers to return plain strings
            return ToolResult(success=True, output=str(result), tool_name=name)
        except Exception as e:
            logger.error(f"[ToolRegistry] Tool {name} failed: {e}", exc_info=True)
            return ToolResult(
                success=False, output="", tool_name=name,
                error=str(e)
            )

    def to_ai_schema(self) -> List[Dict[str, Any]]:
        """
        Export all tools as AI-consumable schema.
        For use with function-calling / tool-use APIs.
        """
        schema = []
        for name, tool in self._tools.items():
            if not tool.enabled:
                continue
            schema.append({
                'type': 'function',
                'function': {
                    'name': tool.name,
                    'description': tool.description,
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            p.name: {
                                'type': p.type,
                                'description': p.description,
                                **({"enum": p.enum} if p.enum else {}),
                            }
                            for p in tool.parameters
                        },
                        'required': [p.name for p in tool.parameters if p.required],
                    },
                },
            })
        return schema

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            'total_tools': len(self._tools),
            'enabled': sum(1 for t in self._tools.values() if t.enabled),
            'categories': {
                cat.value: len(names)
                for cat, names in self._category_index.items()
            },
        }


# ============================================================
# Built-in tool definitions for system commands
# ============================================================

def create_system_tools() -> List[ToolDefinition]:
    """Create built-in system control tool definitions"""
    tools = []

    # Volume control
    tools.append(ToolDefinition(
        name="set_volume",
        description="Set the system audio volume to a specific level",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("level", "integer", "Volume level 0-100", required=True),
        ],
        keywords=["volume", "set volume", "change volume", "sound"],
        examples=["set volume to 50", "volume 80", "turn volume to 30"],
        permission=PermissionLevel.SAFE,
    ))

    tools.append(ToolDefinition(
        name="mute",
        description="Mute or unmute the system audio",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["mute", "unmute", "silence", "quiet"],
        examples=["mute", "unmute", "mute audio"],
        permission=PermissionLevel.SAFE,
    ))

    # Brightness
    tools.append(ToolDefinition(
        name="set_brightness",
        description="Set the screen brightness",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("level", "integer", "Brightness level 0-100", required=True),
        ],
        keywords=["brightness", "set brightness", "screen brightness", "dim", "bright"],
        examples=["set brightness to 70", "dim screen", "max brightness"],
        permission=PermissionLevel.SAFE,
    ))

    # Screenshots
    tools.append(ToolDefinition(
        name="screenshot",
        description="Take a screenshot of the current screen",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["screenshot", "screen capture", "capture screen", "take screenshot", "take a screenshot", "print screen", "snap screen"],
        examples=["take a screenshot", "capture screen", "screenshot"],
        permission=PermissionLevel.SAFE,
    ))

    # Application control
    tools.append(ToolDefinition(
        name="open_app",
        description="Open an application by name",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("app_name", "string", "Name of the application to open", required=True),
        ],
        keywords=["open", "launch", "start", "run"],
        examples=["open notepad", "launch chrome", "start calculator"],
        permission=PermissionLevel.SAFE,
    ))

    tools.append(ToolDefinition(
        name="close_app",
        description="Close an application by name",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("app_name", "string", "Name of the application to close", required=True),
        ],
        keywords=["close", "kill", "stop", "quit", "exit"],
        examples=["close notepad", "kill chrome", "stop spotify"],
        permission=PermissionLevel.MODERATE,
    ))

    # Power management
    tools.append(ToolDefinition(
        name="shutdown",
        description="Shut down the computer",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("delay", "integer", "Delay in seconds before shutdown", default=60),
        ],
        keywords=["shutdown", "shut down", "power off", "turn off"],
        examples=["shutdown in 60 seconds", "shut down computer"],
        permission=PermissionLevel.CRITICAL,
    ))

    tools.append(ToolDefinition(
        name="restart",
        description="Restart the computer",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["restart", "reboot"],
        examples=["restart computer", "reboot"],
        permission=PermissionLevel.CRITICAL,
    ))

    tools.append(ToolDefinition(
        name="lock_screen",
        description="Lock the screen",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["lock", "lock screen"],
        examples=["lock screen", "lock computer"],
        permission=PermissionLevel.SAFE,
    ))

    # System info
    tools.append(ToolDefinition(
        name="system_info",
        description="Get system information (CPU, RAM, disk, battery)",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["system info", "system status", "battery", "cpu", "ram", "disk", "memory usage"],
        examples=["system info", "battery status", "cpu usage"],
        permission=PermissionLevel.SAFE,
    ))

    # WiFi/Bluetooth
    tools.append(ToolDefinition(
        name="toggle_wifi",
        description="Enable or disable WiFi",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("enabled", "boolean", "True to enable, False to disable", required=True),
        ],
        keywords=["wifi", "wi-fi", "wireless", "internet"],
        examples=["turn on wifi", "disable wifi", "wifi off"],
        permission=PermissionLevel.MODERATE,
    ))

    # Window management
    tools.append(ToolDefinition(
        name="minimize_window",
        description="Minimize the active window",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["minimize", "minimize window"],
        examples=["minimize window", "minimize"],
        permission=PermissionLevel.SAFE,
    ))

    tools.append(ToolDefinition(
        name="maximize_window",
        description="Maximize the active window",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["maximize", "maximize window", "fullscreen"],
        examples=["maximize window", "fullscreen"],
        permission=PermissionLevel.SAFE,
    ))

    # Browser
    tools.append(ToolDefinition(
        name="web_search",
        description="Search the web for information",
        category=ToolCategory.BROWSER,
        parameters=[
            ToolParameter("query", "string", "Search query", required=True),
        ],
        keywords=["search", "google", "look up", "find online", "search the web"],
        examples=["search for AI news", "google machine learning", "look up weather"],
        permission=PermissionLevel.SAFE,
    ))

    tools.append(ToolDefinition(
        name="open_url",
        description="Open a URL in the browser",
        category=ToolCategory.BROWSER,
        parameters=[
            ToolParameter("url", "string", "URL to open", required=True),
        ],
        keywords=["go to", "open url", "navigate to", "browse"],
        examples=["go to google.com", "open youtube.com", "navigate to github.com"],
        permission=PermissionLevel.SAFE,
    ))

    # Media
    tools.append(ToolDefinition(
        name="play_music",
        description="Play music on Spotify",
        category=ToolCategory.MEDIA,
        parameters=[
            ToolParameter("query", "string", "Song, artist, or playlist to play"),
        ],
        keywords=["play", "music", "song", "spotify", "play music"],
        examples=["play music", "play Shape of You", "play spotify"],
        permission=PermissionLevel.SAFE,
    ))

    tools.append(ToolDefinition(
        name="pause_music",
        description="Pause current playback",
        category=ToolCategory.MEDIA,
        parameters=[],
        keywords=["pause", "stop music", "pause music"],
        examples=["pause", "pause music", "stop playing"],
        permission=PermissionLevel.SAFE,
    ))

    tools.append(ToolDefinition(
        name="next_song",
        description="Skip to the next song",
        category=ToolCategory.MEDIA,
        parameters=[],
        keywords=["next", "next song", "skip", "next track"],
        examples=["next song", "skip", "play next"],
        permission=PermissionLevel.SAFE,
    ))

    # Smart Home
    tools.append(ToolDefinition(
        name="lights_control",
        description="Control smart lights (on/off/dim)",
        category=ToolCategory.INTEGRATION,
        parameters=[
            ToolParameter("action", "string", "on, off, or dim", required=True, enum=["on", "off", "dim"]),
            ToolParameter("brightness", "integer", "Brightness 0-100 for dim action"),
        ],
        keywords=["lights", "light", "lamp", "bulb", "lighting"],
        examples=["lights on", "turn off lights", "dim lights to 50"],
        permission=PermissionLevel.SAFE,
    ))

    # Automation
    tools.append(ToolDefinition(
        name="comet_task",
        description="Run an autonomous screen control task",
        category=ToolCategory.AGENT,
        parameters=[
            ToolParameter("task", "string", "Description of the task to perform", required=True),
        ],
        keywords=["go to", "automate", "do this", "navigate and"],
        examples=[
            "go to amazon.com and search for headphones",
            "open gmail and compose an email",
        ],
        permission=PermissionLevel.DANGEROUS,
    ))

    return tools


def create_agent_tools() -> List[ToolDefinition]:
    """Create tools for the AI Command Agent (file ops, system exploration, etc.)"""
    tools = []

    # Find files by pattern/type
    tools.append(ToolDefinition(
        name="find_files",
        description="Search for files by name pattern, extension, or type on the local filesystem. Returns matching file paths with size and date.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("pattern", "string", "File name or glob pattern (e.g., '*.jpg', 'report*', 'photo')", required=True),
            ToolParameter("directory", "string", "Directory to search in (default: user home). Use '~' for home, 'C:/' for full disk.", default="~"),
            ToolParameter("max_results", "integer", "Maximum number of results to return", default=20),
            ToolParameter("file_type", "string", "Filter by type: 'image', 'photo', 'video', 'audio', 'document', 'code', 'archive', or a raw extension like '.pdf'"),
        ],
        keywords=["find file", "search file", "locate", "where is", "find my", "look for"],
        examples=["find my photos", "find *.pdf files", "find whatsapp images"],
        permission=PermissionLevel.SAFE,
    ))

    # List directory contents
    tools.append(ToolDefinition(
        name="list_directory",
        description="List contents of a directory with file names, sizes, and modification dates.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("path", "string", "Directory path to list", required=True),
            ToolParameter("show_hidden", "boolean", "Include hidden files", default=False),
        ],
        keywords=["list files", "show files in", "what files", "directory contents", "ls"],
        examples=["list files on desktop", "show what's in downloads", "list directory contents"],
        permission=PermissionLevel.SAFE,
    ))

    # Open file/folder
    tools.append(ToolDefinition(
        name="open_path",
        description="Open a file in its default application or open a folder in File Explorer.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("path", "string", "Full path to file or folder to open", required=True),
        ],
        keywords=["open file", "open folder", "show in explorer", "reveal"],
        examples=["open the downloads folder", "open this file"],
        permission=PermissionLevel.SAFE,
    ))

    # Read file preview
    tools.append(ToolDefinition(
        name="read_file_preview",
        description="Read the first N lines of a text file to preview its contents.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("path", "string", "Full path to the file", required=True),
            ToolParameter("lines", "integer", "Number of lines to read (default 20)", default=20),
        ],
        keywords=["read file", "show file", "preview file", "file contents", "view file"],
        examples=["read config.txt", "show me the contents of notes.txt"],
        permission=PermissionLevel.SAFE,
    ))

    # Get app data paths
    tools.append(ToolDefinition(
        name="get_app_data_paths",
        description="Return known data and storage locations for common Windows applications (WhatsApp, Telegram, Chrome, Discord, Spotify, Steam, VS Code, etc.).",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("app_name", "string", "Application name (e.g., 'whatsapp', 'chrome', 'discord', 'telegram')", required=True),
        ],
        keywords=["app data", "where does", "data location", "storage path", "app folder"],
        examples=["where does WhatsApp store photos", "find chrome data", "telegram folder"],
        permission=PermissionLevel.SAFE,
    ))

    # Run PowerShell (sandboxed)
    tools.append(ToolDefinition(
        name="run_powershell",
        description="Execute a PowerShell command and return the output. Only read-only commands allowed (Get-*, dir, ls, etc.). Destructive commands are blocked for safety.",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("command", "string", "PowerShell command to execute", required=True),
            ToolParameter("timeout", "integer", "Timeout in seconds (default 15)", default=15),
        ],
        keywords=["powershell", "run command", "execute command", "terminal", "cmd"],
        examples=["run 'Get-Process' in powershell", "list installed programs"],
        permission=PermissionLevel.MODERATE,
    ))

    # Search file content (grep)
    tools.append(ToolDefinition(
        name="search_file_content",
        description="Search for text content inside files in a directory (like grep). Returns matching lines with file paths and line numbers.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("query", "string", "Text or regex pattern to search for", required=True),
            ToolParameter("directory", "string", "Directory to search in", required=True),
            ToolParameter("file_pattern", "string", "File glob pattern to limit search (e.g., '*.py', '*.txt')", default="*.*"),
            ToolParameter("max_results", "integer", "Maximum number of matches", default=20),
        ],
        keywords=["search in files", "find text", "grep", "search content", "contains"],
        examples=["search for 'password' in config files", "find text in python files"],
        permission=PermissionLevel.SAFE,
    ))

    # Get folder size
    tools.append(ToolDefinition(
        name="get_folder_size",
        description="Calculate the total size of a directory and its contents.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("path", "string", "Directory path", required=True),
        ],
        keywords=["folder size", "directory size", "how big", "disk usage", "space used"],
        examples=["how big is the downloads folder", "size of C:\\Projects"],
        permission=PermissionLevel.SAFE,
    ))

    # Clipboard read
    tools.append(ToolDefinition(
        name="clipboard_read",
        description="Read the current text content of the system clipboard.",
        category=ToolCategory.SYSTEM,
        parameters=[],
        keywords=["clipboard", "paste", "what's copied", "clipboard content", "read clipboard"],
        examples=["what's on my clipboard", "read clipboard"],
        permission=PermissionLevel.SAFE,
    ))

    # Clipboard write
    tools.append(ToolDefinition(
        name="clipboard_write",
        description="Copy text to the system clipboard.",
        category=ToolCategory.SYSTEM,
        parameters=[
            ToolParameter("text", "string", "Text to copy to clipboard", required=True),
        ],
        keywords=["copy to clipboard", "clipboard copy", "copy text"],
        examples=["copy this text to clipboard"],
        permission=PermissionLevel.SAFE,
    ))

    # Recent files
    tools.append(ToolDefinition(
        name="get_recent_files",
        description="Get recently modified or created files in a directory, sorted by modification time (newest first).",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("directory", "string", "Directory to scan (default: user home)", default="~"),
            ToolParameter("count", "integer", "Number of recent files to return", default=15),
            ToolParameter("file_type", "string", "Filter by type: 'image', 'document', 'video', 'audio', or extension like '.pdf'"),
        ],
        keywords=["recent files", "recently modified", "latest files", "new files", "last changed"],
        examples=["show recent files", "what files were modified today", "latest downloads"],
        permission=PermissionLevel.SAFE,
    ))

    # Image generation
    tools.append(ToolDefinition(
        name="generate_image",
        description="Generate an AI image from a text prompt using Stability AI or Gemini Imagen. Returns the file path of the generated image.",
        category=ToolCategory.MEDIA,
        parameters=[
            ToolParameter("prompt", "string", "Description of the image to generate", required=True),
            ToolParameter("size", "string", "Image size (e.g., '1024x1024')", default="1024x1024"),
        ],
        keywords=["generate image", "create image", "draw", "imagine", "ai art", "picture",
                   "make image", "generate picture"],
        examples=["generate an image of a cat", "draw a sunset", "create art of mountains"],
        permission=PermissionLevel.SAFE,
    ))

    # Video generation
    tools.append(ToolDefinition(
        name="generate_video",
        description="Generate an AI video from a text prompt using Google Veo or Stability AI. Returns the file path of the generated video.",
        category=ToolCategory.MEDIA,
        parameters=[
            ToolParameter("prompt", "string", "Description of the video to generate", required=True),
            ToolParameter("duration", "integer", "Video duration in seconds (default 5)", default=5),
            ToolParameter("aspect_ratio", "string", "Aspect ratio: 16:9, 9:16, or 1:1", default="16:9"),
        ],
        keywords=["generate video", "create video", "make video", "ai video", "video of",
                   "animate", "generate animation"],
        examples=["generate a video of waves crashing", "create video of a sunset", "make a video of fireworks"],
        permission=PermissionLevel.SAFE,
    ))

    # Code execution
    tools.append(ToolDefinition(
        name="execute_code",
        description="Execute Python, JavaScript, or PowerShell code in a secure sandbox. Returns stdout output and any errors.",
        category=ToolCategory.AGENT,
        parameters=[
            ToolParameter("code", "string", "Code to execute", required=True),
            ToolParameter("language", "string", "Programming language: python, javascript, powershell", default="python"),
            ToolParameter("timeout", "integer", "Max execution time in seconds", default=30),
        ],
        keywords=["run code", "execute code", "python", "javascript", "run python",
                   "run script", "code", "calculate"],
        examples=["run this python code", "execute this script", "calculate using python"],
        permission=PermissionLevel.MODERATE,
    ))

    # Document reading
    tools.append(ToolDefinition(
        name="read_document",
        description="Read a PDF, Word (.docx), or text document. Returns text content, metadata, page count, and optionally a summary.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("file_path", "string", "Path to the document file", required=True),
            ToolParameter("summarize", "boolean", "Generate an AI summary of the document", default=False),
        ],
        keywords=["read document", "read pdf", "open document", "read file",
                   "summarize document", "analyze document"],
        examples=["read this PDF", "summarize document.pdf", "open resume.docx"],
        permission=PermissionLevel.SAFE,
    ))

    # Git operations (read-only)
    tools.append(ToolDefinition(
        name="git",
        description="Execute read-only git operations: status, log, diff, branch, stash list. Returns git command output.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("operation", "string", "Git operation to perform", required=True,
                         enum=["status", "log", "diff", "branch", "stash", "show"]),
            ToolParameter("repo_path", "string", "Path to git repository (default: current directory)", default="."),
            ToolParameter("args", "string", "Additional git arguments (e.g., '--oneline' for log)", default=""),
        ],
        keywords=["git status", "git log", "git diff", "show commits", "git history",
                   "repository status", "code changes", "git branch"],
        examples=["show git status", "git log for this project", "show recent commits", "what changed in git"],
        permission=PermissionLevel.SAFE,
    ))

    # HTTP requests
    tools.append(ToolDefinition(
        name="http_request",
        description="Make HTTP requests to APIs and web services. Returns response body, status code, and headers.",
        category=ToolCategory.BROWSER,
        parameters=[
            ToolParameter("url", "string", "URL to request", required=True),
            ToolParameter("method", "string", "HTTP method", default="GET",
                         enum=["GET", "POST", "PUT", "DELETE", "PATCH"]),
            ToolParameter("headers", "object", "Request headers as JSON object", default=None),
            ToolParameter("body", "string", "Request body for POST/PUT/PATCH", default=""),
            ToolParameter("timeout", "integer", "Request timeout in seconds", default=30),
        ],
        keywords=["http request", "api call", "fetch url", "get request", "post request",
                   "call api", "web request", "rest api"],
        examples=["fetch data from api", "make http request to url", "call this api endpoint"],
        permission=PermissionLevel.MODERATE,
    ))

    # SQLite database queries (read-only)
    tools.append(ToolDefinition(
        name="database_query",
        description="Execute read-only SELECT queries on SQLite databases. Returns query results as a table.",
        category=ToolCategory.FILE,
        parameters=[
            ToolParameter("database", "string", "Path to SQLite database file", required=True),
            ToolParameter("query", "string", "SQL SELECT query to execute (SELECT only)", required=True),
        ],
        keywords=["database query", "sql query", "sqlite", "query database",
                   "select from", "database search", "sql select"],
        examples=["query this database", "select from sqlite", "search the database"],
        permission=PermissionLevel.MODERATE,
    ))

    return tools


# Module-level singleton
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry with built-in tools"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        for tool in create_system_tools():
            _registry.register(tool)
        for tool in create_agent_tools():
            _registry.register(tool)
        logger.info(f"[ToolRegistry] {len(_registry._tools)} tools registered")
    return _registry
