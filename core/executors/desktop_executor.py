"""
LADA Desktop Executor — Handles desktop control commands.

Covers five subsystems extracted from JarvisCommandProcessor.process():
  1. Advanced System Control (organize, find large/recent files, disk space, undo)
  2. Window Manager (list/open/switch/maximize/minimize/snap/arrange/close windows)
  3. Smart File Finder (search content, find/open files, recent by type, duplicates)
  4. Advanced Window Control (alt-tab, desktop, center, pin, resize, move, snap quarter)
  5. GUI Automator (screenshot, OCR, click, type, hotkeys, scroll)
"""

import re
import logging
from typing import Tuple

from core.executors import BaseExecutor
from modules.windows_capture_guard import (
    apply_foreground_capture_guard,
    WDA_EXCLUDEFROMCAPTURE,
)

logger = logging.getLogger(__name__)


class DesktopExecutor(BaseExecutor):
    """Handles desktop control commands across five subsystems."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        # Advanced system control
        if self.core.advanced_system:
            handled, response = self._handle_advanced_system(cmd)
            if handled:
                return True, response

        # Window manager
        if self.core.window_manager:
            handled, response = self._handle_window_manager(cmd)
            if handled:
                return True, response

        # Smart file finder
        if self.core.file_finder:
            handled, response = self._handle_file_finder(cmd)
            if handled:
                return True, response

        # Advanced window control
        if self.core.win_ctrl:
            handled, response = self._handle_win_ctrl(cmd)
            if handled:
                return True, response

        # GUI automator
        if self.core.gui_automator:
            handled, response = self._handle_gui_automator(cmd)
            if handled:
                return True, response

        return False, ""

    # ------------------------------------------------------------------
    # 1. Advanced System Control
    # ------------------------------------------------------------------

    def _handle_advanced_system(self, cmd: str) -> Tuple[bool, str]:
        """Organize downloads/folders, find large/recent files, disk space, undo."""

        # --- organize downloads ---
        if any(x in cmd for x in ['organize downloads', 'clean downloads',
                                   'sort downloads', 'tidy downloads']):
            result = self.core.advanced_system.organize_downloads()
            if result.get('success'):
                moved = result.get('files_moved', 0)
                return True, f"Organized downloads. Moved {moved} files."
            return True, f"Failed to organize downloads: {result.get('error', 'Unknown error')}"

        # --- organize folder / directory ---
        if any(x in cmd for x in ['organize folder', 'organize directory',
                                   'clean folder', 'sort folder']):
            match = re.search(
                r'(?:organize|clean|sort)\s+(?:folder|directory)\s+(.+)', cmd)
            if match:
                folder = match.group(1).strip()
                result = self.core.advanced_system.organize_directory(folder)
                if result.get('success'):
                    return True, f"Organized {folder}. Moved {result.get('files_moved', 0)} files."
                return True, f"Failed: {result.get('error', 'Unknown error')}"
            return True, "Which folder would you like me to organize?"

        # --- find large files ---
        if any(x in cmd for x in ['find large files', 'big files',
                                   'largest files', 'files taking space']):
            match = re.search(r'larger than\s+(\d+)\s*(?:mb|megabytes?)', cmd)
            min_size = int(match.group(1)) * 1024 * 1024 if match else 100 * 1024 * 1024
            result = self.core.advanced_system.find_large_files(min_size_bytes=min_size)
            if result.success and result.files:
                file_list = '\n'.join(
                    [f"  - {f.name}: {f.size // (1024*1024)}MB"
                     for f in result.files[:10]])
                return True, f"Found {result.total_found} large files:\n{file_list}"
            return True, "No large files found."

        # --- recent files ---
        if any(x in cmd for x in ['recent files', 'recently modified',
                                   'files from today', 'files from this week']):
            days = 1 if 'today' in cmd else 7
            result = self.core.advanced_system.find_recent_files(days=days)
            if result.success and result.files:
                file_list = '\n'.join(
                    [f"  - {f.name}" for f in result.files[:10]])
                return True, f"Recent files ({result.total_found} total):\n{file_list}"
            return True, "No recent files found."

        # --- disk space ---
        if any(x in cmd for x in ['disk space', 'storage space',
                                   'free space', 'how much space']):
            result = self.core.advanced_system.get_disk_space()
            if result.get('success'):
                free_gb = result.get('free_bytes', 0) / (1024 ** 3)
                used_pct = result.get('percent_used', 0)
                return True, f"Disk: {used_pct:.1f}% used, {free_gb:.1f} GB free"
            return True, "Couldn't get disk space information."

        # --- undo file action ---
        if cmd in ['undo file', 'undo file action', 'revert file']:
            result = self.core.advanced_system.undo_last_action()
            if result.get('success'):
                return True, f"Undone: {result.get('action', 'last action')}"
            return True, f"Nothing to undo or {result.get('error', 'failed')}"

        return False, ""

    # ------------------------------------------------------------------
    # 2. Window Manager
    # ------------------------------------------------------------------

    def _handle_window_manager(self, cmd: str) -> Tuple[bool, str]:
        """List windows, open/switch/maximize/minimize/snap/arrange/close."""

        # --- list windows ---
        if any(x in cmd for x in ['list windows', 'show windows',
                                   'what windows', 'open windows']):
            result = self.core.window_manager.list_windows()
            if result.get('success'):
                windows = result.get('windows', [])
                if windows:
                    window_list = '\n'.join(
                        [f"  - {w.get('title', 'Untitled')[:50]}"
                         for w in windows[:10]])
                    return True, f"Open windows ({len(windows)} total):\n{window_list}"
                return True, "No windows open."
            return True, "Couldn't list windows."

        # --- open app ---
        if any(x in cmd for x in ['open app', 'launch app', 'start app']):
            match = re.search(r'(?:open|launch|start)\s+(?:app\s+)?(.+)', cmd)
            if match:
                app_name = match.group(1).strip()
                result = self.core.window_manager.open_application(app_name)
                if result.get('success'):
                    return True, f"Opened {app_name}"
                return True, f"Couldn't open {app_name}: {result.get('error', 'Unknown error')}"

        # --- switch to / focus ---
        if any(x in cmd for x in ['switch to', 'focus on',
                                   'go to window', 'activate window']):
            match = re.search(
                r'(?:switch to|focus on|go to window|activate window|activate)\s+(.+)', cmd)
            if match:
                window_name = match.group(1).strip()
                result = self.core.window_manager.switch_to_window(window_name)
                if result.get('success'):
                    return True, f"Switched to {window_name}"
                return True, f"Couldn't find window '{window_name}'"

        # --- maximize ---
        if 'maximize' in cmd:
            match = re.search(r'maximize\s+(.+)', cmd)
            window_name = match.group(1).strip() if match else None
            result = self.core.window_manager.maximize_window(window_name)
            if result.get('success'):
                return True, "Window maximized"
            return True, "Couldn't maximize window"

        # --- minimize ---
        if 'minimize' in cmd:
            match = re.search(r'minimize\s+(.+)', cmd)
            window_name = match.group(1).strip() if match else None
            result = self.core.window_manager.minimize_window(window_name)
            if result.get('success'):
                return True, "Window minimized"
            return True, "Couldn't minimize window"

        # --- snap left / right ---
        if 'snap' in cmd:
            if 'left' in cmd:
                result = self.core.window_manager.snap_window('left')
            elif 'right' in cmd:
                result = self.core.window_manager.snap_window('right')
            else:
                return True, "Snap which direction? Say 'snap left' or 'snap right'."
            if result.get('success'):
                return True, "Window snapped"
            return True, "Couldn't snap window"

        # --- arrange / tile ---
        if any(x in cmd for x in ['side by side', 'tile windows',
                                   'arrange windows']):
            result = self.core.window_manager.arrange_windows('side_by_side')
            if result.get('success'):
                return True, "Windows arranged side by side"
            return True, "Couldn't arrange windows"

        # --- close all ---
        if any(x in cmd for x in ['close all apps', 'close all applications',
                                   'close everything']):
            result = self.core.window_manager.close_all_applications()
            if result.get('success'):
                return True, f"Closed {result.get('closed', 0)} applications"
            return True, "Couldn't close applications"

        return False, ""

    # ------------------------------------------------------------------
    # 3. Smart File Finder
    # ------------------------------------------------------------------

    def _handle_file_finder(self, cmd: str) -> Tuple[bool, str]:
        """Search file content, find/open files, recent by type, duplicates."""

        # --- search inside files (content search) ---
        if any(x in cmd for x in ['search inside', 'search content',
                                   'find text in files', 'grep for',
                                   'search in files']):
            match = re.search(
                r'(?:search inside|search content|find text in files'
                r'|grep for|search in files)\s+(?:for\s+)?["\']?(.+?)["\']?$',
                cmd)
            if match:
                query = match.group(1).strip()
                result = self.core.file_finder.search_by_content(query)
                if result.get('success') and result.get('files'):
                    file_list = '\n'.join(
                        [f"  - {f['name']}:{f['line']} -> {f['match'][:60]}"
                         for f in result['files'][:8]])
                    return True, f"Found '{query}' in {result['count']} files:\n{file_list}"
                return True, f"No files contain '{query}'."
            return True, "What text should I search for? Say 'search inside [text]'."

        # --- find file by name ---
        if any(x in cmd for x in ['find file', 'search file', 'look for file',
                                   'locate file', 'where is file', 'find my']):
            match = re.search(
                r'(?:find|search|look for|locate|where is)\s+'
                r'(?:file\s+|my\s+)?["\']?(.+?)["\']?$',
                cmd)
            if match:
                query = match.group(1).strip()
                file_type = None
                for t in ['document', 'image', 'video', 'audio', 'code',
                          'spreadsheet', 'presentation']:
                    if t in query:
                        file_type = t
                        query = query.replace(t, '').strip()
                        break
                result = self.core.file_finder.search_by_name(
                    query, file_type=file_type)
                if result.get('success') and result.get('files'):
                    file_list = '\n'.join(
                        [f"  - {f['name']} ({f['path']})"
                         for f in result['files'][:8]])
                    return True, f"Found {result['count']} files matching '{query}':\n{file_list}"
                return True, f"No files found matching '{query}'."
            return True, "What file should I find? Say 'find file [name]'."

        # --- open file in specific app ---
        if any(x in cmd for x in ['open in word', 'open in excel',
                                   'open in notepad', 'open in vscode',
                                   'open in vs code', 'open in chrome',
                                   'open in paint', 'open in vlc',
                                   'edit in', 'open with']):
            match = re.search(
                r'(?:open|edit)\s+(.+?)\s+(?:in|with)\s+(.+)', cmd)
            if match:
                file_name = match.group(1).strip().strip('"\'')
                app_name = match.group(2).strip()
                result = self.core.file_finder.open_file_by_name(
                    file_name, app=app_name)
                if result.get('success'):
                    return True, f"Opened {file_name} in {app_name}."
                return True, (f"Could not open '{file_name}' in {app_name}: "
                              f"{result.get('error', '')}")
            return True, "Say 'open [file name] in [app]'. Example: 'open resume in word'."

        # --- open file (default app) ---
        if any(x in cmd for x in ['open file', 'open document', 'open my']):
            match = re.search(
                r'(?:open)\s+(?:file|document|my)\s+["\']?(.+?)["\']?$', cmd)
            if match:
                file_name = match.group(1).strip()
                result = self.core.file_finder.open_file_by_name(file_name)
                if result.get('success'):
                    return True, f"Opened {file_name}."
                return True, f"Could not find '{file_name}': {result.get('error', '')}"

        # --- recent files by type ---
        if any(x in cmd for x in ['recent documents', 'recent images',
                                   'recent videos', 'recent code',
                                   'recent spreadsheets', 'recent presentations',
                                   'recent audio', 'recent photos',
                                   'recent downloads']):
            type_match = re.search(r'recent\s+(\w+)', cmd)
            if type_match:
                raw_type = type_match.group(1).strip().lower()
                type_map = {
                    'documents': 'document', 'docs': 'document',
                    'photos': 'image', 'images': 'image', 'pictures': 'image',
                    'videos': 'video', 'spreadsheets': 'spreadsheet',
                    'presentations': 'presentation', 'code': 'code',
                    'scripts': 'code', 'audio': 'audio', 'music': 'audio',
                    'downloads': None,
                }
                file_type = type_map.get(raw_type, raw_type)
                if file_type:
                    result = self.core.file_finder.find_recent_by_type(
                        file_type, days=7)
                    if result.get('success') and result.get('files'):
                        file_list = '\n'.join(
                            [f"  - {f['name']} ({f['modified'][:10]})"
                             for f in result['files'][:10]])
                        return True, f"Recent {raw_type} ({result['count']}):\n{file_list}"
                    return True, f"No recent {raw_type} found."

        # --- find duplicates ---
        if any(x in cmd for x in ['find duplicates', 'duplicate files',
                                   'find duplicate']):
            import os
            result = self.core.file_finder.find_duplicates()
            if result.get('success') and result.get('duplicates'):
                dup_list = '\n'.join(
                    [f"  - {os.path.basename(d['files'][0])} "
                     f"({d['count']} copies, {d['size'] // 1024}KB)"
                     for d in result['duplicates'][:8]])
                return True, f"Found {result['count']} duplicate groups:\n{dup_list}"
            return True, "No duplicate files found."

        return False, ""

    # ------------------------------------------------------------------
    # 4. Advanced Window Control
    # ------------------------------------------------------------------

    def _handle_win_ctrl(self, cmd: str) -> Tuple[bool, str]:
        """Alt-tab, desktop, restore, center, pin, close, fullscreen, resize, move, snap quarter."""

        # --- alt tab ---
        if any(x in cmd for x in ['alt tab', 'switch window',
                                   'alt-tab', 'next window']):
            result = self.core.win_ctrl.alt_tab()
            return True, result.get('message', 'Switched windows')

        # --- show desktop / minimize all ---
        if any(x in cmd for x in ['show desktop', 'minimize all',
                                   'minimize everything', 'hide all windows']):
            result = self.core.win_ctrl.minimize_all()
            return True, result.get('message', 'Desktop shown')

        # --- restore all ---
        if any(x in cmd for x in ['restore windows', 'restore all',
                                   'show all windows', 'unhide windows']):
            result = self.core.win_ctrl.restore_all()
            return True, result.get('message', 'Windows restored')

        # --- center window ---
        if any(x in cmd for x in ['center window', 'center this window']):
            result = self.core.win_ctrl.center_window()
            return True, result.get('message', 'Window centered')

        # --- always on top ---
        if any(x in cmd for x in ['always on top', 'pin window',
                                   'keep on top', 'stay on top']):
            result = self.core.win_ctrl.set_always_on_top(True)
            return True, result.get('message', 'Window pinned on top')

        # --- unpin window ---
        if any(x in cmd for x in ['unpin window', 'remove on top',
                                   'stop on top', 'not on top']):
            result = self.core.win_ctrl.set_always_on_top(False)
            return True, result.get('message', 'Window unpinned')

        # --- close active window ---
        if any(x in cmd for x in ['close this window', 'close window',
                                   'close active window']):
            result = self.core.win_ctrl.close_active_window()
            return True, result.get('message', 'Window closed')

        # --- fullscreen toggle ---
        if any(x in cmd for x in ['fullscreen', 'full screen',
                                   'toggle fullscreen']):
            result = self.core.win_ctrl.fullscreen_toggle()
            return True, result.get('message', 'Toggled fullscreen')

        # --- window info ---
        if any(x in cmd for x in ['window info', 'active window',
                                   'what window', 'which window']):
            result = self.core.win_ctrl.get_active_window_info()
            if result.get('success'):
                return True, (
                    f"Active window: {result.get('title', 'Unknown')}\n"
                    f"  Size: {result['size']['width']}x{result['size']['height']}\n"
                    f"  Position: ({result['position']['x']}, {result['position']['y']})")
            return True, "Could not get window info."

        # --- resize window ---
        if 'resize window' in cmd:
            match = re.search(
                r'resize window\s+(?:to\s+)?(\d+)\s*[x\u00d7]\s*(\d+)', cmd)
            if match:
                w, h = int(match.group(1)), int(match.group(2))
                result = self.core.win_ctrl.resize_window(w, h)
                return True, result.get('message', f'Resized to {w}x{h}')
            return True, "Specify size: 'resize window to 800x600'."

        # --- move window ---
        if 'move window' in cmd:
            match = re.search(
                r'move window\s+(?:to\s+)?(\d+)\s*,\s*(\d+)', cmd)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                result = self.core.win_ctrl.move_window(x, y)
                return True, result.get('message', f'Moved to ({x},{y})')
            return True, "Specify position: 'move window to 100,100'."

        # --- snap quarter positions ---
        if any(x in cmd for x in ['snap top left', 'snap top-left',
                                   'window top left']):
            return True, self.core.win_ctrl.snap_window_quarter(
                'top-left').get('message', 'Snapped')

        if any(x in cmd for x in ['snap top right', 'snap top-right',
                                   'window top right']):
            return True, self.core.win_ctrl.snap_window_quarter(
                'top-right').get('message', 'Snapped')

        if any(x in cmd for x in ['snap bottom left', 'snap bottom-left',
                                   'window bottom left']):
            return True, self.core.win_ctrl.snap_window_quarter(
                'bottom-left').get('message', 'Snapped')

        if any(x in cmd for x in ['snap bottom right', 'snap bottom-right',
                                   'window bottom right']):
            return True, self.core.win_ctrl.snap_window_quarter(
                'bottom-right').get('message', 'Snapped')

        return False, ""

    # ------------------------------------------------------------------
    # 5. GUI Automator
    # ------------------------------------------------------------------

    def _handle_gui_automator(self, cmd: str) -> Tuple[bool, str]:
        """Screenshot, OCR/read screen, click on text, type, hotkeys, scroll."""

        # --- screenshot ---
        if any(x in cmd for x in ['take screenshot', 'screenshot',
                                   'capture screen', 'screen capture']):
            # Best-effort DLP guard: mark active window as excluded before capture.
            guard = apply_foreground_capture_guard(WDA_EXCLUDEFROMCAPTURE)
            result = self.core.gui_automator.screenshot()
            if result.get('success'):
                guard_note = f" ({guard.message})" if guard.success else ""
                return True, f"Screenshot saved: {result.get('path', 'screenshots/')}{guard_note}"
            return True, f"Screenshot failed: {result.get('error', 'Unknown error')}"

        # --- read screen / OCR ---
        if any(x in cmd for x in ['read screen', 'read my screen',
                                   "what's on screen", 'screen text',
                                   'read the screen', 'what is on my screen']):
            result = self.core.gui_automator.extract_text_from_screen()
            if result.get('success'):
                text = result.get('text', '')[:500]
                return True, f"Screen text:\n{text}"
            return True, f"Couldn't read screen: {result.get('error', 'OCR not available')}"

        # --- click on ---
        if 'click on' in cmd:
            match = re.search(r'click on\s+["\']?(.+?)["\']?$', cmd)
            if match:
                target_text = match.group(1).strip()
                result = self.core.gui_automator.click_on_text(target_text)
                if result.get('success'):
                    return True, f"Clicked on '{target_text}'"
                return True, f"Couldn't find '{target_text}' on screen"

        # --- type text ---
        if cmd.startswith('type '):
            text_to_type = cmd[5:].strip().strip('"\'')
            result = self.core.gui_automator.type_text(text_to_type)
            if result.get('success'):
                return True, f"Typed {len(text_to_type)} characters"
            return True, "Couldn't type text"

        # --- hotkeys (ctrl combinations) ---
        if any(x in cmd for x in ['press ctrl', 'press alt', 'hotkey']):
            if 'ctrl c' in cmd or 'ctrl+c' in cmd or 'copy' in cmd:
                result = self.core.gui_automator.copy()
                return True, "Copied" if result.get('success') else "Copy failed"
            if 'ctrl v' in cmd or 'ctrl+v' in cmd or 'paste' in cmd:
                result = self.core.gui_automator.paste()
                return True, "Pasted" if result.get('success') else "Paste failed"
            if 'ctrl a' in cmd or 'ctrl+a' in cmd or 'select all' in cmd:
                result = self.core.gui_automator.select_all()
                return True, "Selected all" if result.get('success') else "Select all failed"
            if 'ctrl s' in cmd or 'ctrl+s' in cmd:
                result = self.core.gui_automator.save()
                return True, "Saved" if result.get('success') else "Save failed"
            if 'ctrl z' in cmd or 'ctrl+z' in cmd:
                result = self.core.gui_automator.undo()
                return True, "Undone" if result.get('success') else "Undo failed"

        # --- scroll ---
        if any(x in cmd for x in ['scroll up', 'scroll down']):
            direction = 'up' if 'up' in cmd else 'down'
            result = self.core.gui_automator.scroll(direction, 3)
            if result.get('success'):
                return True, f"Scrolled {direction}"
            return True, "Couldn't scroll"

        # Generic window command fallback (Phase 3)
        window_triggers = ['window', 'minimize', 'maximize', 'focus ', 'switch to ',
                           'snap ', 'list windows', 'show windows', 'show desktop', 'activate ']
        if any(x in cmd for x in window_triggers):
            if hasattr(self.core, '_handle_window_command'):
                handled, response = self.core._handle_window_command(cmd)
                if handled:
                    return True, response

        # Typing/key press commands
        if any(x in cmd for x in ['type ', 'type this', 'write this', 'enter this']):
            return self.core._handle_typing(cmd)
        if any(x in cmd for x in ['press enter', 'press key', 'press escape', 'press tab']):
            return self.core._handle_key_press(cmd)

        return False, ""
