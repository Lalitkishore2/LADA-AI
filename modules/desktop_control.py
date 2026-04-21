# desktop_control.py
# Advanced Desktop Control Module
# File search with content, open-in-app, window management, smart browser, multi-step tasks

import os
import re
import subprocess
import logging
import time
import json
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

try:
    import pygetwindow as gw
    PYGETWINDOW_OK = True
except ImportError:
    PYGETWINDOW_OK = False


class SmartFileFinder:
    """Advanced file search with content search, fuzzy matching, and smart open."""

    # Common user directories
    SEARCH_ROOTS = [
        os.path.expanduser('~\\Documents'),
        os.path.expanduser('~\\Desktop'),
        os.path.expanduser('~\\Downloads'),
        os.path.expanduser('~\\Pictures'),
        os.path.expanduser('~\\Videos'),
        os.path.expanduser('~\\Music'),
        os.path.expanduser('~'),
    ]

    # File type groups
    FILE_TYPES = {
        'document': ['.docx', '.doc', '.pdf', '.txt', '.rtf', '.odt', '.md'],
        'spreadsheet': ['.xlsx', '.xls', '.csv', '.ods'],
        'presentation': ['.pptx', '.ppt', '.odp'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico'],
        'video': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'],
        'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
        'code': ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.html', '.css', '.json', '.xml'],
        'archive': ['.zip', '.rar', '.7z', '.tar', '.gz'],
        'executable': ['.exe', '.msi', '.bat', '.cmd', '.ps1'],
    }

    # App associations for "open X in Y"
    APP_MAP = {
        'word': {'cmd': 'WINWORD.EXE', 'exts': ['.docx', '.doc', '.rtf']},
        'excel': {'cmd': 'EXCEL.EXE', 'exts': ['.xlsx', '.xls', '.csv']},
        'powerpoint': {'cmd': 'POWERPNT.EXE', 'exts': ['.pptx', '.ppt']},
        'notepad': {'cmd': 'notepad.exe', 'exts': ['.txt', '.md', '.log', '.ini', '.cfg']},
        'vscode': {'cmd': 'code', 'exts': ['.py', '.js', '.ts', '.json', '.html', '.css', '.md']},
        'vs code': {'cmd': 'code', 'exts': ['.py', '.js', '.ts', '.json', '.html', '.css', '.md']},
        'paint': {'cmd': 'mspaint.exe', 'exts': ['.png', '.jpg', '.bmp']},
        'photos': {'cmd': 'ms-photos:', 'exts': ['.jpg', '.jpeg', '.png', '.gif']},
        'vlc': {'cmd': 'vlc.exe', 'exts': ['.mp4', '.avi', '.mkv', '.mp3', '.wav']},
        'chrome': {'cmd': 'chrome.exe', 'exts': ['.html', '.htm', '.pdf']},
        'edge': {'cmd': 'msedge.exe', 'exts': ['.html', '.htm', '.pdf']},
        'acrobat': {'cmd': 'Acrobat.exe', 'exts': ['.pdf']},
    }

    def __init__(self):
        self._index_cache = {}
        self._cache_time = None

    def search_by_name(self, query: str, file_type: str = None,
                       folder: str = None, limit: int = 20) -> Dict[str, Any]:
        """Search files by name with fuzzy matching."""
        try:
            search_dirs = [folder] if folder else self.SEARCH_ROOTS
            results = []
            extensions = self.FILE_TYPES.get(file_type, []) if file_type else []
            query_lower = query.lower()
            query_parts = query_lower.split()

            for search_dir in search_dirs:
                if not os.path.exists(search_dir):
                    continue
                try:
                    for root, dirs, files in os.walk(search_dir):
                        # Skip hidden and system dirs
                        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                                   ['node_modules', '__pycache__', '.git', 'venv', '.venv', 'AppData']]
                        for fname in files:
                            fname_lower = fname.lower()
                            # Extension filter
                            if extensions:
                                if not any(fname_lower.endswith(ext) for ext in extensions):
                                    continue
                            # Name matching - all query parts must appear
                            if all(part in fname_lower for part in query_parts):
                                fpath = os.path.join(root, fname)
                                try:
                                    stat = os.stat(fpath)
                                    results.append({
                                        'name': fname,
                                        'path': fpath,
                                        'size': stat.st_size,
                                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                        'extension': Path(fname).suffix,
                                    })
                                except OSError:
                                    pass
                            if len(results) >= limit * 3:
                                break
                except PermissionError:
                    continue

            # Score and sort: exact match > starts with > contains
            def score(r):
                n = r['name'].lower()
                s = 0
                if query_lower == n or query_lower == Path(n).stem:
                    s = 100
                elif n.startswith(query_lower):
                    s = 80
                elif query_lower in n:
                    s = 60
                else:
                    s = 40
                # Boost recent files
                try:
                    age_days = (datetime.now() - datetime.fromisoformat(r['modified'])).days
                    s += max(0, 10 - age_days)
                except Exception:
                    pass
                return s

            results.sort(key=score, reverse=True)
            results = results[:limit]
            return {'success': True, 'files': results, 'count': len(results)}
        except Exception as e:
            return {'success': False, 'error': str(e), 'files': []}

    def search_by_content(self, query: str, file_type: str = None,
                          folder: str = None, limit: int = 10) -> Dict[str, Any]:
        """Search inside file contents (text-based files)."""
        try:
            search_dirs = [folder] if folder else [
                os.path.expanduser('~\\Documents'),
                os.path.expanduser('~\\Desktop'),
            ]
            text_exts = ['.txt', '.md', '.py', '.js', '.ts', '.html', '.css',
                         '.json', '.xml', '.csv', '.log', '.ini', '.cfg',
                         '.java', '.cpp', '.c', '.h', '.bat', '.ps1', '.yaml', '.yml']
            if file_type:
                text_exts = self.FILE_TYPES.get(file_type, text_exts)

            results = []
            query_lower = query.lower()

            for search_dir in search_dirs:
                if not os.path.exists(search_dir):
                    continue
                for root, dirs, files in os.walk(search_dir):
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                               ['node_modules', '__pycache__', '.git', 'venv', '.venv']]
                    for fname in files:
                        if not any(fname.lower().endswith(ext) for ext in text_exts):
                            continue
                        fpath = os.path.join(root, fname)
                        try:
                            if os.path.getsize(fpath) > 5 * 1024 * 1024:  # Skip files > 5MB
                                continue
                            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(100000)  # Read first 100KB
                            if query_lower in content.lower():
                                # Find the matching line
                                for i, line in enumerate(content.splitlines()):
                                    if query_lower in line.lower():
                                        results.append({
                                            'name': fname,
                                            'path': fpath,
                                            'line': i + 1,
                                            'match': line.strip()[:200],
                                            'extension': Path(fname).suffix,
                                        })
                                        break
                        except (PermissionError, UnicodeDecodeError, OSError):
                            continue
                        if len(results) >= limit:
                            break
                    if len(results) >= limit:
                        break

            return {'success': True, 'files': results, 'count': len(results)}
        except Exception as e:
            return {'success': False, 'error': str(e), 'files': []}

    def find_recent_by_type(self, file_type: str, days: int = 7,
                            limit: int = 15) -> Dict[str, Any]:
        """Find recently modified files of a specific type."""
        try:
            extensions = self.FILE_TYPES.get(file_type, [])
            if not extensions:
                return {'success': False, 'error': f"Unknown file type: {file_type}"}

            cutoff = datetime.now() - timedelta(days=days)
            results = []

            for search_dir in self.SEARCH_ROOTS:
                if not os.path.exists(search_dir):
                    continue
                for root, dirs, files in os.walk(search_dir):
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                               ['node_modules', '__pycache__', '.git', 'venv', '.venv', 'AppData']]
                    for fname in files:
                        if not any(fname.lower().endswith(ext) for ext in extensions):
                            continue
                        fpath = os.path.join(root, fname)
                        try:
                            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                            if mtime >= cutoff:
                                results.append({
                                    'name': fname,
                                    'path': fpath,
                                    'modified': mtime.isoformat(),
                                    'size': os.path.getsize(fpath),
                                })
                        except OSError:
                            continue

            results.sort(key=lambda r: r['modified'], reverse=True)
            results = results[:limit]
            return {'success': True, 'files': results, 'count': len(results), 'type': file_type}
        except Exception as e:
            return {'success': False, 'error': str(e), 'files': []}

    def open_file(self, file_path: str, app: str = None) -> Dict[str, Any]:
        """Open a file, optionally in a specific application."""
        try:
            if not os.path.exists(file_path):
                return {'success': False, 'error': f'File not found: {file_path}'}

            if app:
                app_lower = app.lower().strip()
                app_info = self.APP_MAP.get(app_lower)
                if app_info:
                    cmd = app_info['cmd']
                    if cmd.startswith('ms-'):
                        # URI scheme
                        os.startfile(cmd)
                    elif cmd == 'code':
                        subprocess.Popen(['code', file_path])
                    else:
                        subprocess.Popen([cmd, file_path])
                    return {'success': True, 'file': file_path, 'app': app,
                            'message': f'Opened {os.path.basename(file_path)} in {app}'}
                else:
                    # Try the app name directly
                    subprocess.Popen([app, file_path])
                    return {'success': True, 'file': file_path, 'app': app,
                            'message': f'Opened {os.path.basename(file_path)} in {app}'}
            else:
                # Default: use Windows file association
                os.startfile(file_path)
                return {'success': True, 'file': file_path,
                        'message': f'Opened {os.path.basename(file_path)}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def open_file_by_name(self, name: str, app: str = None) -> Dict[str, Any]:
        """Find a file by name and open it."""
        result = self.search_by_name(name, limit=5)
        if result.get('success') and result.get('files'):
            best = result['files'][0]
            return self.open_file(best['path'], app)
        return {'success': False, 'error': f"File '{name}' not found"}

    def find_duplicates(self, folder: str = None,
                        limit: int = 20) -> Dict[str, Any]:
        """Find duplicate files by size + name similarity."""
        try:
            import hashlib
            search_dir = folder or os.path.expanduser('~\\Documents')
            size_map = {}

            for root, dirs, files in os.walk(search_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        size = os.path.getsize(fpath)
                        if size > 0:
                            size_map.setdefault(size, []).append(fpath)
                    except OSError:
                        continue

            duplicates = []
            for size, paths in size_map.items():
                if len(paths) < 2:
                    continue
                # Hash first 4KB for comparison
                hash_map = {}
                for p in paths:
                    try:
                        with open(p, 'rb') as f:
                            h = hashlib.md5(f.read(4096)).hexdigest()
                        hash_map.setdefault(h, []).append(p)
                    except Exception:
                        continue
                for h, dups in hash_map.items():
                    if len(dups) >= 2:
                        duplicates.append({
                            'files': dups,
                            'size': size,
                            'count': len(dups),
                        })
                if len(duplicates) >= limit:
                    break

            return {'success': True, 'duplicates': duplicates[:limit], 'count': len(duplicates)}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class WindowController:
    """Advanced window management beyond basic minimize/maximize."""

    def alt_tab(self) -> Dict[str, Any]:
        """Simulate Alt+Tab."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('alt', 'tab')
                return {'success': True, 'message': 'Switched windows (Alt+Tab)'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def resize_window(self, width: int, height: int) -> Dict[str, Any]:
        """Resize the active window to specific dimensions."""
        try:
            if PYGETWINDOW_OK:
                win = gw.getActiveWindow()
                if win:
                    win.resizeTo(width, height)
                    return {'success': True, 'message': f'Window resized to {width}x{height}'}
                return {'success': False, 'error': 'No active window found'}
            return {'success': False, 'error': 'pygetwindow not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def move_window(self, x: int, y: int) -> Dict[str, Any]:
        """Move the active window to specific position."""
        try:
            if PYGETWINDOW_OK:
                win = gw.getActiveWindow()
                if win:
                    win.moveTo(x, y)
                    return {'success': True, 'message': f'Window moved to ({x}, {y})'}
                return {'success': False, 'error': 'No active window found'}
            return {'success': False, 'error': 'pygetwindow not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def center_window(self) -> Dict[str, Any]:
        """Center the active window on screen."""
        try:
            if PYGETWINDOW_OK and PYAUTOGUI_OK:
                win = gw.getActiveWindow()
                if win:
                    screen_w, screen_h = pyautogui.size()
                    x = (screen_w - win.width) // 2
                    y = (screen_h - win.height) // 2
                    win.moveTo(x, y)
                    return {'success': True, 'message': 'Window centered'}
                return {'success': False, 'error': 'No active window found'}
            return {'success': False, 'error': 'Dependencies not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_always_on_top(self, enable: bool = True) -> Dict[str, Any]:
        """Set active window always on top (uses PowerShell/Windows API)."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                flag = HWND_TOPMOST if enable else HWND_NOTOPMOST
                user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                state = 'always on top' if enable else 'normal'
                return {'success': True, 'message': f'Window set to {state}'}
            return {'success': False, 'error': 'No active window'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def minimize_all(self) -> Dict[str, Any]:
        """Minimize all windows (show desktop)."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('win', 'd')
                return {'success': True, 'message': 'All windows minimized (desktop shown)'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def restore_all(self) -> Dict[str, Any]:
        """Restore all windows."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('win', 'd')  # Toggle
                return {'success': True, 'message': 'Windows restored'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def snap_window_quarter(self, position: str) -> Dict[str, Any]:
        """Snap window to a quarter of the screen (top-left, top-right, bottom-left, bottom-right)."""
        try:
            if PYGETWINDOW_OK and PYAUTOGUI_OK:
                screen_w, screen_h = pyautogui.size()
                win = gw.getActiveWindow()
                if not win:
                    return {'success': False, 'error': 'No active window'}
                half_w, half_h = screen_w // 2, screen_h // 2
                pos_map = {
                    'top-left': (0, 0), 'top left': (0, 0),
                    'top-right': (half_w, 0), 'top right': (half_w, 0),
                    'bottom-left': (0, half_h), 'bottom left': (0, half_h),
                    'bottom-right': (half_w, half_h), 'bottom right': (half_w, half_h),
                }
                coords = pos_map.get(position.lower())
                if coords:
                    win.moveTo(coords[0], coords[1])
                    win.resizeTo(half_w, half_h)
                    return {'success': True, 'message': f'Window snapped to {position}'}
                return {'success': False, 'error': f'Unknown position: {position}'}
            return {'success': False, 'error': 'Dependencies not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_active_window_info(self) -> Dict[str, Any]:
        """Get details about the active window."""
        try:
            if PYGETWINDOW_OK:
                win = gw.getActiveWindow()
                if win:
                    return {
                        'success': True,
                        'title': win.title,
                        'position': {'x': win.left, 'y': win.top},
                        'size': {'width': win.width, 'height': win.height},
                        'maximized': win.isMaximized,
                        'minimized': win.isMinimized,
                    }
                return {'success': False, 'error': 'No active window'}
            return {'success': False, 'error': 'pygetwindow not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def close_active_window(self) -> Dict[str, Any]:
        """Close the active window."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('alt', 'F4')
                return {'success': True, 'message': 'Active window closed'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def fullscreen_toggle(self) -> Dict[str, Any]:
        """Toggle fullscreen (F11)."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.press('f11')
                return {'success': True, 'message': 'Toggled fullscreen'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class SmartBrowser:
    """Enhanced browser control with natural language commands."""

    def open_url(self, url: str) -> Dict[str, Any]:
        """Open a URL, auto-adding https:// if needed."""
        try:
            import webbrowser
            if not url.startswith(('http://', 'https://')):
                if '.' in url:
                    url = f'https://{url}'
                else:
                    url = f'https://www.google.com/search?q={url.replace(" ", "+")}'
            webbrowser.open(url)
            return {'success': True, 'url': url, 'message': f'Opened {url}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def search_web(self, query: str, engine: str = 'google') -> Dict[str, Any]:
        """Search the web using various engines."""
        try:
            import webbrowser
            engines = {
                'google': f'https://www.google.com/search?q={query.replace(" ", "+")}',
                'bing': f'https://www.bing.com/search?q={query.replace(" ", "+")}',
                'duckduckgo': f'https://duckduckgo.com/?q={query.replace(" ", "+")}',
                'youtube': f'https://www.youtube.com/results?search_query={query.replace(" ", "+")}',
                'github': f'https://github.com/search?q={query.replace(" ", "+")}',
                'amazon': f'https://www.amazon.in/s?k={query.replace(" ", "+")}',
                'flipkart': f'https://www.flipkart.com/search?q={query.replace(" ", "+")}',
                'maps': f'https://www.google.com/maps/search/{query.replace(" ", "+")}',
                'images': f'https://www.google.com/search?tbm=isch&q={query.replace(" ", "+")}',
                'news': f'https://news.google.com/search?q={query.replace(" ", "+")}',
                'wikipedia': f'https://en.wikipedia.org/wiki/Special:Search?search={query.replace(" ", "+")}',
                'stackoverflow': f'https://stackoverflow.com/search?q={query.replace(" ", "+")}',
            }
            url = engines.get(engine.lower(), engines['google'])
            webbrowser.open(url)
            return {'success': True, 'query': query, 'engine': engine, 'url': url,
                    'message': f'Searching {engine} for: {query}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def open_incognito(self, url: str = None) -> Dict[str, Any]:
        """Open browser in incognito/private mode."""
        try:
            if url and not url.startswith(('http://', 'https://')):
                url = f'https://{url}'
            # Try Chrome first
            chrome_paths = [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    cmd = [path, '--incognito']
                    if url:
                        cmd.append(url)
                    subprocess.Popen(cmd)
                    return {'success': True, 'message': f'Opened incognito{" with " + url if url else ""}'}
            # Fallback: Edge
            edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
            if os.path.exists(edge_path):
                cmd = [edge_path, '--inprivate']
                if url:
                    cmd.append(url)
                subprocess.Popen(cmd)
                return {'success': True, 'message': f'Opened InPrivate{" with " + url if url else ""}'}
            return {'success': False, 'error': 'No supported browser found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def read_page_text(self) -> Dict[str, Any]:
        """Read the text content of the current browser page using Ctrl+A, Ctrl+C."""
        try:
            if not PYAUTOGUI_OK:
                return {'success': False, 'error': 'pyautogui not available'}
            # Select all and copy
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.3)
            # Read from clipboard
            proc = subprocess.run(
                ['powershell', '-Command', 'Get-Clipboard'],
                capture_output=True, text=True, timeout=5,
            )
            text = proc.stdout.strip()
            # Click to deselect
            pyautogui.click()
            return {'success': True, 'text': text, 'length': len(text)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def find_in_page(self, text: str) -> Dict[str, Any]:
        """Open Find dialog and search for text on the current page."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'f')
                time.sleep(0.5)
                pyautogui.typewrite(text, interval=0.03)
                pyautogui.press('enter')
                return {'success': True, 'message': f'Searching page for: {text}'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def zoom_in(self) -> Dict[str, Any]:
        """Zoom in on the current page."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'plus')
                return {'success': True, 'message': 'Zoomed in'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def zoom_out(self) -> Dict[str, Any]:
        """Zoom out on the current page."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'minus')
                return {'success': True, 'message': 'Zoomed out'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def reset_zoom(self) -> Dict[str, Any]:
        """Reset zoom to 100%."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', '0')
                return {'success': True, 'message': 'Zoom reset to 100%'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def bookmark_page(self) -> Dict[str, Any]:
        """Bookmark the current page."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'd')
                return {'success': True, 'message': 'Bookmark dialog opened'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def print_page(self) -> Dict[str, Any]:
        """Print the current page."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'p')
                return {'success': True, 'message': 'Print dialog opened'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def save_page(self) -> Dict[str, Any]:
        """Save the current page."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 's')
                return {'success': True, 'message': 'Save dialog opened'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def clear_browsing_data(self) -> Dict[str, Any]:
        """Open clear browsing data dialog."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'shift', 'delete')
                return {'success': True, 'message': 'Clear browsing data dialog opened'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def open_dev_tools(self) -> Dict[str, Any]:
        """Open browser developer tools."""
        try:
            if PYAUTOGUI_OK:
                pyautogui.press('f12')
                return {'success': True, 'message': 'Developer tools opened'}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class DesktopController:
    """Unified desktop control orchestrator."""

    def __init__(self):
        self.file_finder = SmartFileFinder()
        self.window_ctrl = WindowController()
        self.browser = SmartBrowser()

    def quick_launch(self, target: str) -> Dict[str, Any]:
        """Intelligently launch apps, files, or URLs based on target string."""
        # Check if it's a URL
        if any(target.endswith(x) for x in ['.com', '.org', '.net', '.io', '.ai', '.in', '.co']):
            return self.browser.open_url(target)
        if target.startswith(('http://', 'https://', 'www.')):
            return self.browser.open_url(target)
        # Check if it's a file path
        if os.path.exists(target):
            return self.file_finder.open_file(target)
        # Check if it's a file name (search and open)
        if '.' in target and len(target.split('.')[-1]) <= 5:
            result = self.file_finder.open_file_by_name(target)
            if result.get('success'):
                return result
        # Default: search for it
        return {'success': False, 'error': f'Could not determine how to open: {target}'}


# Singleton instances
_file_finder = None
_window_ctrl = None
_browser = None
_desktop_ctrl = None

def get_file_finder() -> SmartFileFinder:
    global _file_finder
    if _file_finder is None:
        _file_finder = SmartFileFinder()
    return _file_finder

def get_window_controller() -> WindowController:
    global _window_ctrl
    if _window_ctrl is None:
        _window_ctrl = WindowController()
    return _window_ctrl

def get_smart_browser() -> SmartBrowser:
    global _browser
    if _browser is None:
        _browser = SmartBrowser()
    return _browser

def get_desktop_controller() -> DesktopController:
    global _desktop_ctrl
    if _desktop_ctrl is None:
        _desktop_ctrl = DesktopController()
    return _desktop_ctrl
