"""
LADA Tool Handlers — Binds tool_registry ToolDefinitions to actual implementations.

Wires SystemController methods to registered tools and implements new
file/system tool handlers for the AI Command Agent.

Usage:
    from modules.tool_handlers import wire_tool_handlers
    from modules.tool_registry import get_tool_registry
    registry = get_tool_registry()
    wired = wire_tool_handlers(registry)
"""

import os
import re
import glob
import json
import time
import logging
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from threading import Lock

logger = logging.getLogger(__name__)
HANDLER_CONTRACT_VERSION = os.getenv("LADA_TOOL_HANDLER_CONTRACT_VERSION", "1.0")
_todo_lock = Lock()
_session_todos: List[Dict[str, Any]] = []


def _major_from_version(version_text: str) -> int:
    token = str(version_text or "").strip().split(".")[0]
    try:
        return int(token)
    except (TypeError, ValueError):
        return 0

# Try imports
try:
    from modules.tool_registry import ToolRegistry, ToolResult
    REGISTRY_OK = True
except ImportError:
    REGISTRY_OK = False

try:
    from modules.system_control import SystemController
    _sys_ctrl = SystemController()
    SYS_CTRL_OK = True
except Exception:
    _sys_ctrl = None
    SYS_CTRL_OK = False

try:
    from modules.file_operations import FileSystemController
    _file_ctrl = FileSystemController()
    FILE_CTRL_OK = True
except Exception:
    _file_ctrl = None
    FILE_CTRL_OK = False

# ============================================================
# Helper: convert SystemController dict returns to ToolResult
# ============================================================

def _wrap(result: Dict[str, Any]) -> ToolResult:
    """Convert SystemController return dict to ToolResult."""
    if not isinstance(result, dict):
        return ToolResult(success=True, output=str(result))
    success = result.get('success', True)
    message = result.get('message', '')
    error = result.get('error', None) if not success else None
    data = {k: v for k, v in result.items() if k not in ('success', 'message', 'error')}
    return ToolResult(success=success, output=message, data=data or None, error=error)


# ============================================================
# Handlers for EXISTING tools (20 tools registered in tool_registry)
# ============================================================

def _handle_set_volume(level: int = 50) -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    return _wrap(_sys_ctrl.set_volume(level))


def _handle_mute() -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    return _wrap(_sys_ctrl.mute())


# ============================================================
# File System Operations Handlers
# ============================================================

def _handle_file_create(path: str, content: str = "", overwrite: bool = False) -> ToolResult:
    if not _file_ctrl:
        return ToolResult(success=False, output="", error="File system control not available")
    return _wrap(_file_ctrl.create_file(path, content, overwrite))

def _handle_file_delete(path: str, permanent: bool = False) -> ToolResult:
    if not _file_ctrl:
        return ToolResult(success=False, output="", error="File system control not available")
    return _wrap(_file_ctrl.delete_file(path, permanent))

def _handle_file_copy(source: str, destination: str) -> ToolResult:
    if not _file_ctrl:
        return ToolResult(success=False, output="", error="File system control not available")
    return _wrap(_file_ctrl.copy_file(source, destination))

def _handle_file_move(source: str, destination: str) -> ToolResult:
    if not _file_ctrl:
        return ToolResult(success=False, output="", error="File system control not available")
    return _wrap(_file_ctrl.move_file(source, destination))

def _handle_file_properties(path: str) -> ToolResult:
    if not _file_ctrl:
        return ToolResult(success=False, output="", error="File system control not available")
    return _wrap(_file_ctrl.get_file_properties(path))


def _handle_set_brightness(level: int = 50) -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    return _wrap(_sys_ctrl.set_brightness(level))


def _handle_screenshot() -> ToolResult:
    try:
        import pyautogui
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = Path.home() / "Pictures" / "Screenshots"
        save_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_dir / f"screenshot_{ts}.png"
        img = pyautogui.screenshot()
        img.save(str(filepath))
        return ToolResult(success=True, output=f"Screenshot saved to {filepath}",
                          data={"path": str(filepath)})
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Screenshot failed: {e}")

def _handle_take_camera_photo() -> ToolResult:
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return ToolResult(success=False, output="", error="No camera device found or access denied")
        
        # Discard couple of frames to let camera auto-adjust exposure
        for _ in range(5):
            cap.read()
            
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return ToolResult(success=False, output="", error="Failed to capture image from camera")
            
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = Path.home() / "Pictures" / "Camera Roll"
        save_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_dir / f"photo_{ts}.png"
        cv2.imwrite(str(filepath), frame)
        return ToolResult(success=True, output=f"Photo saved to {filepath}", data={"path": str(filepath)})
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Camera capture failed: {e}")

def _handle_send_notification(title: str = "LADA", message: str = "") -> ToolResult:
    if not message:
        return ToolResult(success=False, output="", error="No message provided")
    try:
        import subprocess
        # Use PowerShell to show a Toast Notification
        ps_script = f"""
        [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
        $objNotifyIcon = New-Object System.Windows.Forms.NotifyIcon
        $objNotifyIcon.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon("shell32.dll")
        $objNotifyIcon.BalloonTipTitle = "{title.replace('"', '')}"
        $objNotifyIcon.BalloonTipText = "{message.replace('"', '')}"
        $objNotifyIcon.Visible = $True
        $objNotifyIcon.ShowBalloonTip(10000)
        """
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)
        return ToolResult(success=True, output=f"Notification sent: '{title}: {message}'")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Failed to send notification: {e}")

def _handle_record_screen(duration_seconds: int = 5) -> ToolResult:
    try:
        import pyautogui
        import cv2
        import numpy as np
        
        duration = min(max(1, int(duration_seconds)), 30)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = Path.home() / "Videos" / "Captures"
        save_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_dir / f"screen_record_{ts}.avi"
        
        # Get screen size
        screen_size = pyautogui.size()
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        out = cv2.VideoWriter(str(filepath), fourcc, 10.0, (screen_size.width, screen_size.height))
        
        frames = duration * 10
        for _ in range(frames):
            img = pyautogui.screenshot()
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            out.write(frame)
            time.sleep(0.1)  # Approximate 10 fps target
            
        out.release()
        return ToolResult(success=True, output=f"Recorded {duration}s of screen to {filepath}", data={"path": str(filepath)})
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Screen recording failed: {e}")

def _handle_open_app(app_name: str = "") -> ToolResult:
    if not app_name:
        return ToolResult(success=False, output="", error="No app name provided")
    try:
        app_lower = app_name.lower().strip()
        # Common app shortcuts
        app_map = {
            'notepad': 'notepad.exe',
            'calculator': 'calc.exe',
            'calc': 'calc.exe',
            'paint': 'mspaint.exe',
            'cmd': 'cmd.exe',
            'terminal': 'wt.exe',
            'powershell': 'powershell.exe',
            'explorer': 'explorer.exe',
            'file explorer': 'explorer.exe',
            'task manager': 'taskmgr.exe',
            'settings': 'ms-settings:',
            'chrome': 'chrome',
            'edge': 'msedge',
            'firefox': 'firefox',
            'code': 'code',
            'vscode': 'code',
            'spotify': 'spotify',
            'discord': 'discord',
            'slack': 'slack',
            'teams': 'teams',
        }
        exe = app_map.get(app_lower, app_lower)
        if exe.startswith('ms-'):
            os.startfile(exe)
        else:
            subprocess.Popen([exe])
        return ToolResult(success=True, output=f"Opened {app_name}")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Could not open {app_name}: {e}")


def _handle_close_app(app_name: str = "") -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    if not app_name:
        return ToolResult(success=False, output="", error="No app name provided")
    return _wrap(_sys_ctrl.kill_process(app_name))


def _handle_shutdown(delay: int = 60) -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    return _wrap(_sys_ctrl.power_action('shutdown', delay))


def _handle_restart() -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    return _wrap(_sys_ctrl.power_action('restart'))


def _handle_lock_screen() -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    return _wrap(_sys_ctrl.power_action('lock'))


def _handle_system_info() -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    result = _sys_ctrl.get_system_status()
    if isinstance(result, dict) and result.get('success'):
        data = result.get('data', result)
        lines = []
        for key, value in data.items():
            if key not in ('success', 'message'):
                lines.append(f"{key}: {value}")
        return ToolResult(success=True, output='\n'.join(lines) if lines else result.get('message', 'OK'),
                          data=data)
    return _wrap(result)


def _handle_toggle_wifi(enabled: bool = True) -> ToolResult:
    if not _sys_ctrl:
        return ToolResult(success=False, output="", error="System control not available")
    if enabled:
        return _wrap(_sys_ctrl.connect_wifi("", ""))
    else:
        return _wrap(_sys_ctrl.disconnect_wifi())


def _handle_minimize_window() -> ToolResult:
    try:
        import pyautogui
        pyautogui.hotkey('win', 'down')
        return ToolResult(success=True, output="Window minimized")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_maximize_window() -> ToolResult:
    try:
        import pyautogui
        pyautogui.hotkey('win', 'up')
        return ToolResult(success=True, output="Window maximized")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_web_search(query: str = "") -> ToolResult:
    if not query:
        return ToolResult(success=False, output="", error="No search query provided")
    import urllib.parse
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return ToolResult(success=True, output=f"Searching for: {query}")


def _handle_open_url(url: str = "") -> ToolResult:
    if not url:
        return ToolResult(success=False, output="", error="No URL provided")
    webbrowser.open(url)
    return ToolResult(success=True, output=f"Opened {url}")


def _handle_play_music(query: str = "") -> ToolResult:
    try:
        if query:
            import urllib.parse
            webbrowser.open(f"https://open.spotify.com/search/{urllib.parse.quote(query)}")
            return ToolResult(success=True, output=f"Searching Spotify for: {query}")
        else:
            subprocess.Popen(["spotify"])
            return ToolResult(success=True, output="Opening Spotify")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_pause_music() -> ToolResult:
    try:
        import pyautogui
        pyautogui.hotkey('playpause')
        return ToolResult(success=True, output="Toggled playback")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_next_song() -> ToolResult:
    try:
        import pyautogui
        pyautogui.hotkey('nexttrack')
        return ToolResult(success=True, output="Skipped to next track")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_lights_control(action: str = "on", brightness: int = 100) -> ToolResult:
    return ToolResult(success=False, output="",
                      error="Smart home lights not configured. Set up in .env.")


def _handle_comet_task(task: str = "") -> ToolResult:
    try:
        from modules.comet_agent import CometAgent
        agent = CometAgent()
        result = agent.execute(task)
        return ToolResult(success=True, output=result or f"Completed task: {task}")
    except ImportError:
        return ToolResult(success=False, output="", error="Comet agent not available")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_task(prompt: str = "", agent_type: str = "task",
                 files: Optional[List[str]] = None, timeout: int = 120) -> ToolResult:
    """
    Spawn a local subagent task with strict depth=1 isolation.
    """
    if not prompt.strip():
        return ToolResult(success=False, output="", error="Task prompt is required")
    try:
        from modules.subagents.runtime import get_subagent_runtime, SubagentConfig

        runtime = get_subagent_runtime()
        config = SubagentConfig(
            agent_type=(agent_type or "task").strip(),
            task_description=prompt.strip(),
            timeout_seconds=max(10, int(timeout or 120)),
            context={"files": files or [], "transport": "local-runtime"},
            allow_subagents=False,
            inherit_context=False,
            session_id="tool-task",
        )
        state = runtime.spawn_and_get(config=config)
        result = runtime.wait(state.id, timeout=max(10, int(timeout or 120)))

        if result and result.success:
            return ToolResult(
                success=True,
                output=result.output or f"Subagent {state.id} completed",
                data={"subagent_id": state.id, "agent_type": config.agent_type, "depth": state.depth},
            )

        err = result.error if result else "Subagent did not produce a result"
        return ToolResult(
            success=False,
            output="",
            error=err,
            data={"subagent_id": state.id, "agent_type": config.agent_type, "depth": state.depth},
        )
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_todo_write(action: str = "list", id: str = "", title: str = "",
                       description: str = "", status: str = "pending") -> ToolResult:
    """
    In-memory todo tracker for the AI command loop.
    """
    action_key = (action or "").strip().lower()
    with _todo_lock:
        if action_key == "add":
            if not title.strip():
                return ToolResult(success=False, output="", error="title is required for add")
            todo_id = id.strip() or f"todo-{len(_session_todos) + 1}"
            if any(t["id"] == todo_id for t in _session_todos):
                return ToolResult(success=False, output="", error=f"Todo ID already exists: {todo_id}")
            item = {
                "id": todo_id,
                "title": title.strip(),
                "description": (description or "").strip(),
                "status": status if status in {"pending", "in_progress", "done", "blocked"} else "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            _session_todos.append(item)
            return ToolResult(success=True, output=f"Added todo {todo_id}: {item['title']}", data={"todo": item})

        if action_key == "update":
            todo_id = id.strip()
            if not todo_id:
                return ToolResult(success=False, output="", error="id is required for update")
            for item in _session_todos:
                if item["id"] == todo_id:
                    if title.strip():
                        item["title"] = title.strip()
                    if description.strip():
                        item["description"] = description.strip()
                    if status in {"pending", "in_progress", "done", "blocked"}:
                        item["status"] = status
                    item["updated_at"] = datetime.now().isoformat()
                    return ToolResult(success=True, output=f"Updated todo {todo_id}", data={"todo": item})
            return ToolResult(success=False, output="", error=f"Todo not found: {todo_id}")

        if action_key == "complete":
            todo_id = id.strip()
            if not todo_id:
                return ToolResult(success=False, output="", error="id is required for complete")
            for item in _session_todos:
                if item["id"] == todo_id:
                    item["status"] = "done"
                    item["updated_at"] = datetime.now().isoformat()
                    return ToolResult(success=True, output=f"Completed todo {todo_id}", data={"todo": item})
            return ToolResult(success=False, output="", error=f"Todo not found: {todo_id}")

        if action_key == "delete":
            todo_id = id.strip()
            if not todo_id:
                return ToolResult(success=False, output="", error="id is required for delete")
            before = len(_session_todos)
            _session_todos[:] = [t for t in _session_todos if t["id"] != todo_id]
            if len(_session_todos) == before:
                return ToolResult(success=False, output="", error=f"Todo not found: {todo_id}")
            return ToolResult(success=True, output=f"Deleted todo {todo_id}")

        if action_key == "list":
            if not _session_todos:
                return ToolResult(success=True, output="No todos yet.", data={"todos": []})
            lines = ["Session todos:"]
            for item in _session_todos:
                lines.append(f"- [{item['status']}] {item['id']}: {item['title']}")
            return ToolResult(success=True, output="\n".join(lines), data={"todos": list(_session_todos)})

    return ToolResult(success=False, output="", error=f"Unsupported action: {action}")


# ============================================================
# Handlers for NEW tools (11 tools for AI Command Agent)
# ============================================================

# --- File type extension mappings ---
FILE_TYPE_MAP = {
    'image': ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp', '*.heic', '*.svg', '*.ico'],
    'photo': ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp', '*.heic'],
    'video': ['*.mp4', '*.avi', '*.mkv', '*.mov', '*.wmv', '*.flv', '*.webm'],
    'audio': ['*.mp3', '*.wav', '*.flac', '*.aac', '*.ogg', '*.m4a', '*.wma'],
    'document': ['*.pdf', '*.doc', '*.docx', '*.txt', '*.xlsx', '*.xls', '*.pptx', '*.ppt', '*.csv', '*.rtf'],
    'code': ['*.py', '*.js', '*.ts', '*.java', '*.cpp', '*.c', '*.h', '*.cs', '*.go', '*.rs', '*.html', '*.css'],
    'archive': ['*.zip', '*.rar', '*.7z', '*.tar', '*.gz', '*.bz2'],
}


def _handle_find_files(pattern: str = "*", directory: str = "~",
                       max_results: int = 20, file_type: str = None) -> ToolResult:
    """Search for files by pattern, type, or name."""
    try:
        search_dir = Path(os.path.expanduser(directory)).resolve()
        if not search_dir.exists():
            return ToolResult(success=False, output="",
                              error=f"Directory not found: {directory}")

        # Build glob patterns
        patterns = []
        if file_type:
            ft = file_type.lower().strip()
            if ft in FILE_TYPE_MAP:
                patterns = FILE_TYPE_MAP[ft]
            elif ft.startswith('.'):
                patterns = [f'*{ft}']
            else:
                patterns = [f'*.{ft}']
        else:
            # If pattern has no wildcard, wrap it
            if '*' not in pattern and '?' not in pattern:
                patterns = [f'*{pattern}*']
            else:
                patterns = [pattern]

        results = []
        for p in patterns:
            if len(results) >= max_results:
                break
            try:
                for match in search_dir.rglob(p):
                    if len(results) >= max_results:
                        break
                    if match.is_file():
                        try:
                            stat = match.stat()
                            size_kb = round(stat.st_size / 1024, 1)
                            modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                            results.append({
                                'path': str(match),
                                'name': match.name,
                                'size_kb': size_kb,
                                'modified': modified,
                            })
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        if not results:
            return ToolResult(success=True,
                              output=f"No files matching '{pattern}' found in {search_dir}")

        lines = [f"Found {len(results)} file(s):"]
        for r in results:
            size_str = f"{r['size_kb']} KB" if r['size_kb'] < 1024 else f"{round(r['size_kb']/1024, 1)} MB"
            lines.append(f"  {r['name']} ({size_str}, {r['modified']}) — {r['path']}")

        return ToolResult(success=True, output='\n'.join(lines),
                          data={'files': results, 'count': len(results)})

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_list_directory(path: str = "~", show_hidden: bool = False) -> ToolResult:
    """List directory contents with details."""
    try:
        dir_path = Path(os.path.expanduser(path)).resolve()
        if not dir_path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        if not dir_path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")

        entries = []
        for entry in sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if not show_hidden and entry.name.startswith('.'):
                continue
            try:
                stat = entry.stat()
                is_dir = entry.is_dir()
                size = stat.st_size if not is_dir else 0
                modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                entries.append({
                    'name': entry.name,
                    'type': 'DIR' if is_dir else 'FILE',
                    'size': size,
                    'modified': modified,
                })
            except (PermissionError, OSError):
                continue

        if not entries:
            return ToolResult(success=True, output=f"Directory is empty: {dir_path}")

        lines = [f"Contents of {dir_path} ({len(entries)} items):"]
        for e in entries:
            if e['type'] == 'DIR':
                lines.append(f"  [DIR]  {e['name']}/  ({e['modified']})")
            else:
                size = e['size']
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{round(size/1024, 1)} KB"
                else:
                    size_str = f"{round(size/(1024*1024), 1)} MB"
                lines.append(f"  [FILE] {e['name']}  ({size_str}, {e['modified']})")

        return ToolResult(success=True, output='\n'.join(lines),
                          data={'entries': entries, 'path': str(dir_path)})

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_open_path(path: str = "") -> ToolResult:
    """Open a file or folder in its default application."""
    if not path:
        return ToolResult(success=False, output="", error="No path provided")
    try:
        target = Path(os.path.expanduser(path)).resolve()
        if not target.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        os.startfile(str(target))
        return ToolResult(success=True, output=f"Opened: {target}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_read_file_preview(path: str = "", lines: int = 20) -> ToolResult:
    """Read first N lines of a text file."""
    if not path:
        return ToolResult(success=False, output="", error="No file path provided")
    try:
        filepath = Path(os.path.expanduser(path)).resolve()
        if not filepath.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        if not filepath.is_file():
            return ToolResult(success=False, output="", error=f"Not a file: {path}")

        # Try reading with different encodings
        content = None
        for enc in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    content = f.readlines()[:lines]
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            return ToolResult(success=False, output="",
                              error="Could not read file (binary or unknown encoding)")

        text = ''.join(content)
        total_lines = len(content)
        return ToolResult(success=True,
                          output=f"File: {filepath.name} ({total_lines} lines shown):\n{text}",
                          data={'path': str(filepath), 'lines_read': total_lines})

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


# --- Known app data paths on Windows ---
APP_DATA_PATHS = {
    'whatsapp': {
        'description': 'WhatsApp Desktop media and data',
        'paths': [
            '~/AppData/Local/Packages/5319275A.WhatsAppDesktop_cv1g1gvanyjgm/LocalState',
            '~/AppData/Local/WhatsApp',
            '~/Documents/WhatsApp',
            '~/Downloads/WhatsApp Images',
            '~/Downloads',
        ],
    },
    'telegram': {
        'description': 'Telegram Desktop data and downloads',
        'paths': [
            '~/AppData/Roaming/Telegram Desktop',
            '~/Downloads/Telegram Desktop',
        ],
    },
    'chrome': {
        'description': 'Google Chrome user data (bookmarks, history, cache)',
        'paths': [
            '~/AppData/Local/Google/Chrome/User Data/Default',
            '~/AppData/Local/Google/Chrome/User Data',
        ],
    },
    'edge': {
        'description': 'Microsoft Edge user data',
        'paths': [
            '~/AppData/Local/Microsoft/Edge/User Data/Default',
        ],
    },
    'firefox': {
        'description': 'Firefox profiles and data',
        'paths': [
            '~/AppData/Roaming/Mozilla/Firefox/Profiles',
        ],
    },
    'discord': {
        'description': 'Discord app data and cache',
        'paths': [
            '~/AppData/Roaming/discord',
            '~/AppData/Local/Discord',
        ],
    },
    'spotify': {
        'description': 'Spotify app data and cache',
        'paths': [
            '~/AppData/Roaming/Spotify',
            '~/AppData/Local/Spotify',
        ],
    },
    'steam': {
        'description': 'Steam games and data',
        'paths': [
            'C:/Program Files (x86)/Steam',
            'C:/Program Files/Steam',
            '~/AppData/Local/Steam',
        ],
    },
    'vscode': {
        'description': 'Visual Studio Code settings and extensions',
        'paths': [
            '~/AppData/Roaming/Code/User',
            '~/.vscode/extensions',
        ],
    },
    'obs': {
        'description': 'OBS Studio recordings and settings',
        'paths': [
            '~/AppData/Roaming/obs-studio',
            '~/Videos',
        ],
    },
    'minecraft': {
        'description': 'Minecraft game data',
        'paths': [
            '~/AppData/Roaming/.minecraft',
        ],
    },
    'blender': {
        'description': 'Blender config and addons',
        'paths': [
            '~/AppData/Roaming/Blender Foundation/Blender',
        ],
    },
    'outlook': {
        'description': 'Outlook data files',
        'paths': [
            '~/Documents/Outlook Files',
            '~/AppData/Local/Microsoft/Outlook',
        ],
    },
    'onedrive': {
        'description': 'OneDrive synced files',
        'paths': [
            '~/OneDrive',
            '~/OneDrive - Personal',
        ],
    },
    'downloads': {
        'description': 'User downloads folder',
        'paths': [
            '~/Downloads',
        ],
    },
}


def _handle_get_app_data_paths(app_name: str = "") -> ToolResult:
    """Return known data locations for common Windows applications."""
    if not app_name:
        # List all known apps
        known = ', '.join(sorted(APP_DATA_PATHS.keys()))
        return ToolResult(success=True,
                          output=f"Known apps: {known}\nProvide an app name to get its data paths.")

    key = app_name.lower().strip()
    # Fuzzy match: try partial matching
    matched_key = None
    for k in APP_DATA_PATHS:
        if k == key or key in k or k in key:
            matched_key = k
            break

    if not matched_key:
        known = ', '.join(sorted(APP_DATA_PATHS.keys()))
        return ToolResult(success=True,
                          output=f"No known paths for '{app_name}'. Known apps: {known}")

    info = APP_DATA_PATHS[matched_key]
    existing_paths = []
    for p in info['paths']:
        expanded = Path(os.path.expanduser(p)).resolve()
        # Handle glob patterns in path
        if '*' in str(expanded):
            matches = glob.glob(str(expanded))
            for m in matches:
                mp = Path(m)
                if mp.exists():
                    existing_paths.append(str(mp))
        elif expanded.exists():
            existing_paths.append(str(expanded))

    if not existing_paths:
        return ToolResult(success=True,
                          output=f"{matched_key.title()} — {info['description']}\n"
                                 f"None of the known paths exist on this machine.\n"
                                 f"Checked: {', '.join(info['paths'])}")

    lines = [f"{matched_key.title()} — {info['description']}",
             f"Found {len(existing_paths)} location(s):"]
    for p in existing_paths:
        lines.append(f"  {p}")

    return ToolResult(success=True, output='\n'.join(lines),
                      data={'app': matched_key, 'paths': existing_paths})


# --- PowerShell sandboxing ---
POWERSHELL_BLOCKED = [
    'remove-item', 'remove-', 'delete-', 'del ', 'rd ', 'rmdir',
    'stop-process', 'stop-service', 'stop-computer',
    'kill', 'taskkill',
    'set-executionpolicy', 'invoke-expression', 'iex ',
    'invoke-webrequest', 'invoke-restmethod',
    'start-process', 'new-object net.webclient',
    'downloadfile', 'downloadstring',
    'format-volume', 'clear-disk', 'initialize-disk',
    'clear-content', 'clear-recyclebin',
    'set-mppreference', 'add-mppreference',  # Defender tampering
    'reg delete', 'reg add',
    'shutdown', 'restart-computer',
    'new-psdrive', 'net user', 'net localgroup',
]


def _validate_powershell_command(command: str) -> Tuple[bool, str]:
    """Validate that a PowerShell command is safe to execute."""
    cmd_lower = command.lower().strip()

    for blocked in POWERSHELL_BLOCKED:
        if blocked in cmd_lower:
            return False, f"Blocked for safety: command contains '{blocked}'"

    # Block piping to dangerous commands
    if '|' in cmd_lower:
        pipe_parts = cmd_lower.split('|')
        for part in pipe_parts[1:]:
            part = part.strip()
            for blocked in POWERSHELL_BLOCKED:
                if part.startswith(blocked):
                    return False, f"Blocked: pipeline to '{blocked}'"

    return True, ""


def _handle_run_powershell(command: str = "", timeout: int = 15) -> ToolResult:
    """Execute a sandboxed PowerShell command."""
    if not command:
        return ToolResult(success=False, output="", error="No command provided")

    safe, reason = _validate_powershell_command(command)
    if not safe:
        return ToolResult(success=False, output="", error=reason)

    try:
        proc = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        output = proc.stdout.strip()
        error = proc.stderr.strip() if proc.returncode != 0 else None

        if proc.returncode == 0:
            return ToolResult(success=True, output=output or "(no output)",
                              data={'return_code': proc.returncode})
        else:
            return ToolResult(success=False, output=output,
                              error=error or f"Exit code {proc.returncode}")

    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="",
                          error=f"Command timed out after {timeout}s")
    except FileNotFoundError:
        return ToolResult(success=False, output="",
                          error="PowerShell not found on this system")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_search_file_content(query: str = "", directory: str = "~",
                                file_pattern: str = "*.*",
                                max_results: int = 20) -> ToolResult:
    """Search for text content inside files (grep-like)."""
    if not query:
        return ToolResult(success=False, output="", error="No search query provided")

    try:
        search_dir = Path(os.path.expanduser(directory)).resolve()
        if not search_dir.exists():
            return ToolResult(success=False, output="",
                              error=f"Directory not found: {directory}")

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        matches = []
        for filepath in search_dir.rglob(file_pattern):
            if len(matches) >= max_results:
                break
            if not filepath.is_file():
                continue
            # Skip binary/large files
            try:
                if filepath.stat().st_size > 10 * 1024 * 1024:  # 10 MB limit
                    continue
            except (PermissionError, OSError):
                continue

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if len(matches) >= max_results:
                            break
                        if pattern.search(line):
                            matches.append({
                                'file': str(filepath),
                                'line': line_num,
                                'text': line.strip()[:200],
                            })
            except (PermissionError, OSError, UnicodeDecodeError):
                continue

        if not matches:
            return ToolResult(success=True,
                              output=f"No matches for '{query}' in {search_dir}")

        lines = [f"Found {len(matches)} match(es) for '{query}':"]
        for m in matches:
            lines.append(f"  {m['file']}:{m['line']} — {m['text']}")

        return ToolResult(success=True, output='\n'.join(lines),
                          data={'matches': matches})

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_get_folder_size(path: str = "") -> ToolResult:
    """Calculate the total size of a directory."""
    if not path:
        return ToolResult(success=False, output="", error="No path provided")
    try:
        dir_path = Path(os.path.expanduser(path)).resolve()
        if not dir_path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        if not dir_path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")

        total_size = 0
        file_count = 0
        for f in dir_path.rglob('*'):
            if f.is_file():
                try:
                    total_size += f.stat().st_size
                    file_count += 1
                except (PermissionError, OSError):
                    continue

        if total_size < 1024:
            size_str = f"{total_size} bytes"
        elif total_size < 1024 * 1024:
            size_str = f"{round(total_size/1024, 1)} KB"
        elif total_size < 1024 * 1024 * 1024:
            size_str = f"{round(total_size/(1024*1024), 1)} MB"
        else:
            size_str = f"{round(total_size/(1024*1024*1024), 2)} GB"

        return ToolResult(success=True,
                          output=f"{dir_path}: {size_str} ({file_count} files)",
                          data={'path': str(dir_path), 'size_bytes': total_size,
                                'file_count': file_count})

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_clipboard_read() -> ToolResult:
    """Read current clipboard text content."""
    if _sys_ctrl:
        try:
            result = _sys_ctrl.get_clipboard_text()
            return _wrap(result)
        except Exception:
            pass
    # Fallback: use PowerShell
    try:
        proc = subprocess.run(
            ['powershell', '-NoProfile', '-Command', 'Get-Clipboard'],
            capture_output=True, text=True, timeout=5,
        )
        text = proc.stdout.strip()
        return ToolResult(success=True, output=text or "(clipboard is empty)")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_clipboard_write(text: str = "") -> ToolResult:
    """Write text to the system clipboard."""
    if not text:
        return ToolResult(success=False, output="", error="No text provided")
    if _sys_ctrl:
        try:
            result = _sys_ctrl.set_clipboard_text(text)
            return _wrap(result)
        except Exception:
            pass
    # Fallback: use PowerShell
    try:
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', f'Set-Clipboard -Value "{text}"'],
            capture_output=True, text=True, timeout=5,
        )
        return ToolResult(success=True, output=f"Copied to clipboard ({len(text)} chars)")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_get_recent_files(directory: str = "~", count: int = 15,
                             file_type: str = None) -> ToolResult:
    """Get recently modified files in a directory."""
    try:
        search_dir = Path(os.path.expanduser(directory)).resolve()
        if not search_dir.exists():
            return ToolResult(success=False, output="",
                              error=f"Directory not found: {directory}")

        # Get file extension patterns
        patterns = ['*']
        if file_type:
            ft = file_type.lower().strip()
            if ft in FILE_TYPE_MAP:
                patterns = FILE_TYPE_MAP[ft]
            elif ft.startswith('.'):
                patterns = [f'*{ft}']
            else:
                patterns = [f'*.{ft}']

        files = []
        for p in patterns:
            for f in search_dir.rglob(p):
                if f.is_file():
                    try:
                        stat = f.stat()
                        files.append((f, stat.st_mtime, stat.st_size))
                    except (PermissionError, OSError):
                        continue

        # Sort by modification time (newest first) and take top N
        files.sort(key=lambda x: x[1], reverse=True)
        files = files[:count]

        if not files:
            return ToolResult(success=True,
                              output=f"No recent files found in {search_dir}")

        lines = [f"Recent files in {search_dir}:"]
        for f, mtime, size in files:
            modified = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
            size_kb = round(size / 1024, 1)
            size_str = f"{size_kb} KB" if size_kb < 1024 else f"{round(size_kb/1024, 1)} MB"
            lines.append(f"  {f.name} ({size_str}, {modified}) — {f}")

        return ToolResult(success=True, output='\n'.join(lines),
                          data={'count': len(files)})

    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


# ============================================================
# Handlers for gap-closing tools (image gen, code sandbox, doc reader)
# ============================================================

def _handle_generate_image(prompt: str = "", size: str = "1024x1024") -> ToolResult:
    """Generate an AI image from a text prompt."""
    try:
        from modules.image_generation import get_image_generator
        gen = get_image_generator()
        if not gen.is_available():
            return ToolResult(success=False, output="",
                              error="No image generation backend available. Set STABILITY_API_KEY or GEMINI_API_KEY.")
        result = gen.generate(prompt, size=size)
        if result:
            return ToolResult(success=True,
                              output=f"Image generated: {result['path']} (backend: {result['backend']})",
                              data=result)
        return ToolResult(success=False, output="", error="Image generation failed — backend returned no image")
    except ImportError:
        return ToolResult(success=False, output="", error="Image generation module not available")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_generate_video(prompt: str = "", duration: int = 5, aspect_ratio: str = "16:9") -> ToolResult:
    """Generate an AI video from a text prompt."""
    try:
        from modules.video_generation import get_video_generator
        gen = get_video_generator()
        if not gen.is_available():
            return ToolResult(success=False, output="",
                              error="No video generation backend available. Set STABILITY_API_KEY or GEMINI_API_KEY.")
        result = gen.generate(prompt, duration=duration, aspect_ratio=aspect_ratio)
        if result:
            return ToolResult(success=True,
                              output=f"Video generated: {result['path']} (backend: {result['backend']}, {result.get('duration', duration)}s)",
                              data=result)
        return ToolResult(success=False, output="", error="Video generation failed — backend returned no video")
    except ImportError:
        return ToolResult(success=False, output="", error="Video generation module not available")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_execute_code(code: str = "", language: str = "python", timeout: int = 30) -> ToolResult:
    """Execute code in a secure sandbox with rich output support (plots, tables)."""
    try:
        from modules.code_sandbox import CodeSandbox, ExecutionMode

        sandbox = CodeSandbox(timeout=timeout, mode=ExecutionMode.SUBPROCESS)

        # Validate first
        validation = sandbox.validate_code(code, language)
        if not validation.get('safe', True):
            issues = '; '.join(validation.get('issues', ['Unknown safety issue']))
            return ToolResult(success=False, output="",
                              error=f"Code validation failed: {issues}")

        # Use rich output for Python to capture plots/dataframes
        if language.lower() == "python":
            result = sandbox.execute_with_rich_output(code, language=language, timeout=timeout)
            output = result.output or "(no output)"

            if result.success:
                data = {'output': result.output, 'time': result.execution_time}

                # Include rich output if present
                if result.has_rich_output:
                    if result.plot_data:
                        data['plot_data'] = result.plot_data
                        output += "\n\n[Plot generated - see inline image]"
                    if result.table_html:
                        data['table_html'] = result.table_html
                        output += "\n\n[DataFrame rendered - see table]"

                return ToolResult(success=True,
                                  output=f"Output:\n{output}\n\nExecution time: {result.execution_time:.2f}s",
                                  data=data)
            else:
                return ToolResult(success=False, output=output,
                                  error=result.error or "Execution failed")
        else:
            # Non-Python: use standard execution
            result = sandbox.execute(code, language=language, timeout=timeout)
            output = result.output or "(no output)"
            if result.success:
                return ToolResult(success=True,
                                  output=f"Output:\n{output}\n\nExecution time: {result.execution_time:.2f}s",
                                  data={'output': result.output, 'time': result.execution_time})
            else:
                return ToolResult(success=False, output=output,
                                  error=result.error or "Execution failed")

    except ImportError:
        return ToolResult(success=False, output="", error="Code sandbox not available")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_read_document(file_path: str = "", summarize: bool = False) -> ToolResult:
    """Read a PDF, Word, or text document."""
    try:
        from modules.document_reader import DocumentReader
        reader = DocumentReader()
        if not reader.can_read(file_path):
            return ToolResult(success=False, output="",
                              error=f"Unsupported format. Supported: {', '.join(reader.SUPPORTED_FORMATS.keys())}")
        result = reader.read_document(file_path, summarize=summarize)
        if result.success:
            info = result.info
            output = f"Document: {info.title} ({info.format}, {info.page_count} pages)\n"
            if result.summary:
                output += f"Summary: {result.summary}\n\n"
            text = result.full_text[:3000] if len(result.full_text) > 3000 else result.full_text
            output += text
            return ToolResult(success=True, output=output,
                              data={'title': info.title, 'pages': info.page_count,
                                    'words': len(result.full_text.split())})
        return ToolResult(success=False, output="", error=result.error)
    except ImportError:
        return ToolResult(success=False, output="", error="Document reader not available (install pymupdf)")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_git(operation: str = "status", repo_path: str = ".", args: str = "") -> ToolResult:
    """Execute read-only git operations."""
    import subprocess

    # Only allow read-only operations
    allowed_ops = ['status', 'log', 'diff', 'branch', 'stash', 'show']
    if operation not in allowed_ops:
        return ToolResult(success=False, output="",
                          error=f"Operation '{operation}' not allowed. Allowed: {', '.join(allowed_ops)}")

    try:
        # Build command
        cmd = ['git', operation]
        if args:
            cmd.extend(args.split())

        # Add sensible defaults for some operations
        if operation == 'log' and '--oneline' not in args and '-n' not in args:
            cmd.extend(['--oneline', '-20'])  # Default to last 20 commits
        if operation == 'stash':
            cmd.append('list')  # Only allow stash list

        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
        )

        output = result.stdout.strip() or "(no output)"
        if result.returncode == 0:
            return ToolResult(success=True, output=output,
                              data={'operation': operation, 'repo': repo_path})
        else:
            error = result.stderr.strip() or f"git {operation} failed"
            return ToolResult(success=False, output=output, error=error)

    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error="Git command timed out (30s)")
    except FileNotFoundError:
        return ToolResult(success=False, output="", error="Git not found. Is git installed?")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_http_request(url: str = "", method: str = "GET", headers: dict = None,
                         body: str = "", timeout: int = 30) -> ToolResult:
    """Make HTTP requests to APIs."""
    import urllib.request
    import urllib.error
    import json as json_mod

    if not url:
        return ToolResult(success=False, output="", error="URL is required")

    # Validate URL (basic check)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # Build request
        req = urllib.request.Request(url, method=method.upper())

        # Add headers
        default_headers = {'User-Agent': 'LADA-AI/1.0'}
        if headers:
            default_headers.update(headers)
        for key, val in default_headers.items():
            req.add_header(key, val)

        # Add body for POST/PUT/PATCH
        data = None
        if body and method.upper() in ['POST', 'PUT', 'PATCH']:
            data = body.encode('utf-8')
            if 'Content-Type' not in default_headers:
                req.add_header('Content-Type', 'application/json')

        # Make request
        with urllib.request.urlopen(req, data=data, timeout=timeout) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8', errors='replace')

            # Truncate very long responses
            if len(response_body) > 5000:
                response_body = response_body[:5000] + "\n... (truncated)"

            return ToolResult(
                success=True,
                output=f"Status: {status_code}\n\n{response_body}",
                data={'status': status_code, 'url': url, 'method': method}
            )

    except urllib.error.HTTPError as e:
        return ToolResult(success=False, output="",
                          error=f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return ToolResult(success=False, output="",
                          error=f"URL Error: {e.reason}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _handle_database_query(database: str = "", query: str = "") -> ToolResult:
    """Execute read-only SELECT queries on SQLite databases."""
    import sqlite3

    if not database:
        return ToolResult(success=False, output="", error="Database path is required")
    if not query:
        return ToolResult(success=False, output="", error="SQL query is required")

    # Security: Only allow SELECT queries (read-only)
    query_upper = query.strip().upper()
    if not query_upper.startswith('SELECT'):
        return ToolResult(success=False, output="",
                          error="Only SELECT queries allowed (read-only)")

    # Block dangerous keywords
    dangerous = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC']
    for word in dangerous:
        if word in query_upper:
            return ToolResult(success=False, output="",
                              error=f"Keyword '{word}' not allowed in query")

    try:
        # Check if database exists
        if not os.path.exists(database):
            return ToolResult(success=False, output="",
                              error=f"Database not found: {database}")

        # Execute query
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return ToolResult(success=True, output="Query returned no results.",
                              data={'rows': 0})

        # Format as table
        columns = rows[0].keys()
        header = ' | '.join(columns)
        separator = '-+-'.join(['-' * len(c) for c in columns])

        lines = [header, separator]
        for row in rows[:100]:  # Limit to 100 rows
            line = ' | '.join(str(row[c]) for c in columns)
            lines.append(line)

        if len(rows) > 100:
            lines.append(f"... ({len(rows)} total rows, showing first 100)")

        output = '\n'.join(lines)
        return ToolResult(success=True, output=output,
                          data={'rows': len(rows), 'columns': list(columns)})

    except sqlite3.Error as e:
        return ToolResult(success=False, output="", error=f"SQLite error: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


def _get_stealth_browser():
    """Lazily load stealth browser singleton to avoid hard startup dependency."""
    from modules.stealth_browser import get_stealth_browser
    return get_stealth_browser()


def _handle_stealth_navigate(url: str = "") -> ToolResult:
    if not url:
        return ToolResult(success=False, output="", error="URL is required")

    try:
        browser = _get_stealth_browser()
        result = browser.navigate(url)
        if result.get('success'):
            title = result.get('title', '')
            opened_url = result.get('url', url)
            msg = f"Stealth navigation successful: {opened_url}"
            if title:
                msg += f"\nTitle: {title}"
            return ToolResult(success=True, output=msg, data=result)
        return ToolResult(success=False, output="", error=result.get('error', 'Stealth navigation failed'))
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Stealth navigation failed: {e}")


def _handle_stealth_click(selector: str = "", by: str = "css") -> ToolResult:
    if not selector:
        return ToolResult(success=False, output="", error="Selector is required")

    try:
        browser = _get_stealth_browser()
        result = browser.click(selector=selector, by=by)
        if result.get('success'):
            return ToolResult(success=True, output=f"Stealth click successful on {selector}", data=result)
        return ToolResult(success=False, output="", error=result.get('error', 'Stealth click failed'))
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Stealth click failed: {e}")


def _handle_stealth_type(selector: str = "", text: str = "", by: str = "css", clear_first: bool = True) -> ToolResult:
    if not selector:
        return ToolResult(success=False, output="", error="Selector is required")
    if text is None:
        return ToolResult(success=False, output="", error="Text is required")

    try:
        browser = _get_stealth_browser()
        result = browser.type_text(selector=selector, text=text, by=by, clear_first=clear_first)
        if result.get('success'):
            return ToolResult(success=True, output=f"Stealth typed into {selector}", data=result)
        return ToolResult(success=False, output="", error=result.get('error', 'Stealth type failed'))
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Stealth type failed: {e}")


def _handle_stealth_scroll(direction: str = "down", amount: int = 300) -> ToolResult:
    try:
        browser = _get_stealth_browser()
        result = browser.scroll(direction=direction, amount=amount)
        if result.get('success'):
            return ToolResult(success=True, output=f"Stealth scrolled {direction} by {amount}px", data=result)
        return ToolResult(success=False, output="", error=result.get('error', 'Stealth scroll failed'))
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Stealth scroll failed: {e}")


def _handle_stealth_extract(selector: str = "") -> ToolResult:
    try:
        browser = _get_stealth_browser()
        if selector:
            text = browser.execute_js(
                "const el=document.querySelector(arguments[0]); return el ? el.innerText : null;",
                selector,
            )
            if text is None:
                return ToolResult(success=False, output="", error=f"Element not found for selector: {selector}")
            content = str(text)
            return ToolResult(success=True, output=content[:4000], data={"selector": selector, "length": len(content)})

        result = browser.get_page_content()
        if not result.get('success'):
            return ToolResult(success=False, output="", error=result.get('error', 'Stealth extract failed'))

        text = str(result.get('text', ''))
        preview = text[:4000] if text else ""
        return ToolResult(
            success=True,
            output=preview,
            data={
                "url": result.get('url', ''),
                "title": result.get('title', ''),
                "length": len(text),
            },
        )
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Stealth extract failed: {e}")


# ============================================================
# Main wiring function
# ============================================================

def wire_tool_handlers(registry: ToolRegistry) -> int:
    """
    Wire handler functions to all registered tools.
    Returns count of successfully wired handlers.
    """
    registry_major = getattr(registry, "contract_major", 1)
    handler_major = _major_from_version(HANDLER_CONTRACT_VERSION)
    if registry_major != handler_major:
        logger.error(
            "[ToolHandlers] Contract mismatch: registry major=%s, handler major=%s. Skipping handler wiring.",
            registry_major,
            handler_major,
        )
        return 0

    handler_map = {
        # Existing tools
        'set_volume': _handle_set_volume,
        'mute': _handle_mute,
        'set_brightness': _handle_set_brightness,
        'screenshot': _handle_screenshot,
        'take_camera_photo': _handle_take_camera_photo,
        'send_notification': _handle_send_notification,
        'record_screen': _handle_record_screen,
        'open_app': _handle_open_app,
        'close_app': _handle_close_app,
        'shutdown': _handle_shutdown,
        'restart': _handle_restart,
        'lock_screen': _handle_lock_screen,
        'system_info': _handle_system_info,
        'toggle_wifi': _handle_toggle_wifi,
        'minimize_window': _handle_minimize_window,
        'maximize_window': _handle_maximize_window,
        'web_search': _handle_web_search,
        'open_url': _handle_open_url,
        'play_music': _handle_play_music,
        'pause_music': _handle_pause_music,
        'next_song': _handle_next_song,
        'lights_control': _handle_lights_control,
        'comet_task': _handle_comet_task,
        
        # New File Tools
        'file_create': _handle_file_create,
        'file_delete': _handle_file_delete,
        'file_copy': _handle_file_copy,
        'file_move': _handle_file_move,
        'file_properties': _handle_file_properties,
        'task': _handle_task,
        'todo_write': _handle_todo_write,
        # New tools (AI Command Agent)
        'find_files': _handle_find_files,
        'list_directory': _handle_list_directory,
        'open_path': _handle_open_path,
        'read_file_preview': _handle_read_file_preview,
        'get_app_data_paths': _handle_get_app_data_paths,
        'run_powershell': _handle_run_powershell,
        'search_file_content': _handle_search_file_content,
        'get_folder_size': _handle_get_folder_size,
        'clipboard_read': _handle_clipboard_read,
        'clipboard_write': _handle_clipboard_write,
        'get_recent_files': _handle_get_recent_files,
        # Gap-closing tools
        'generate_image': _handle_generate_image,
        'generate_video': _handle_generate_video,
        'execute_code': _handle_execute_code,
        'read_document': _handle_read_document,
        # Extended tools (Phase 6)
        'git': _handle_git,
        'http_request': _handle_http_request,
        'database_query': _handle_database_query,
        # Stealth browser tools
        'stealth_navigate': _handle_stealth_navigate,
        'stealth_click': _handle_stealth_click,
        'stealth_type': _handle_stealth_type,
        'stealth_scroll': _handle_stealth_scroll,
        'stealth_extract': _handle_stealth_extract,
    }

    wired = 0
    for tool_name, handler_fn in handler_map.items():
        tool = registry.get(tool_name)
        if tool:
            tool.handler = handler_fn
            wired += 1
        else:
            logger.debug(f"[ToolHandlers] Tool '{tool_name}' not found in registry (skipped)")

    logger.info(f"[ToolHandlers] Wired {wired} tool handlers "
                f"(sys_ctrl={'OK' if SYS_CTRL_OK else 'N/A'})")
    return wired
