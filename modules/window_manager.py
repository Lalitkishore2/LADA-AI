"""
LADA v9.0 - Window Manager Module
Complete window and application control for JARVIS-level automation.

Features:
- List all open windows
- Open/close applications
- Switch between windows
- Maximize/minimize/restore windows
- Arrange windows (side-by-side, grid)
- Window focus management
- Application launching with arguments
"""

import os
import subprocess
import logging
import time
import getpass
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import pygetwindow
try:
    import pygetwindow as gw
    PYGETWINDOW_OK = True
except ImportError:
    gw = None
    PYGETWINDOW_OK = False
    logger.warning("[!] pygetwindow not available - window management limited")

# Try to import psutil for process management
try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    psutil = None
    PSUTIL_OK = False


@dataclass
class WindowInfo:
    """Information about a window"""
    title: str
    handle: int
    x: int
    y: int
    width: int
    height: int
    is_active: bool
    is_minimized: bool
    is_maximized: bool
    process_name: str = ""


# Common application paths on Windows
APP_PATHS = {
    # System
    'file explorer': 'explorer.exe',
    'explorer': 'explorer.exe',
    'cmd': 'cmd.exe',
    'command prompt': 'cmd.exe',
    'powershell': 'powershell.exe',
    'terminal': 'wt.exe',
    'windows terminal': 'wt.exe',
    'settings': 'ms-settings:',
    'control panel': 'control.exe',
    'task manager': 'taskmgr.exe',
    'calculator': 'calc.exe',
    'notepad': 'notepad.exe',
    'paint': 'mspaint.exe',
    'snipping tool': 'snippingtool.exe',
    
    # Browsers
    'chrome': [
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    ],
    'firefox': [
        'C:\\Program Files\\Mozilla Firefox\\firefox.exe',
        'C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe',
    ],
    'edge': 'msedge.exe',
    'microsoft edge': 'msedge.exe',
    'brave': [
        'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
    ],
    
    # Development
    'vscode': [
        'C:\\Users\\{user}\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
        'C:\\Program Files\\Microsoft VS Code\\Code.exe',
    ],
    'visual studio code': [
        'C:\\Users\\{user}\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
        'C:\\Program Files\\Microsoft VS Code\\Code.exe',
    ],
    'code': [
        'C:\\Users\\{user}\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
        'C:\\Program Files\\Microsoft VS Code\\Code.exe',
    ],
    
    # Media
    'vlc': [
        'C:\\Program Files\\VideoLAN\\VLC\\vlc.exe',
        'C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe',
    ],
    'spotify': [
        'C:\\Users\\{user}\\AppData\\Roaming\\Spotify\\Spotify.exe',
    ],
    
    # Communication
    'discord': [
        'C:\\Users\\{user}\\AppData\\Local\\Discord\\Update.exe --processStart Discord.exe',
    ],
    'teams': [
        'C:\\Users\\{user}\\AppData\\Local\\Microsoft\\Teams\\Update.exe --processStart Teams.exe',
    ],
    'zoom': [
        'C:\\Users\\{user}\\AppData\\Roaming\\Zoom\\bin\\Zoom.exe',
    ],
    'whatsapp': [
        'C:\\Users\\{user}\\AppData\\Local\\WhatsApp\\WhatsApp.exe',
    ],
    'slack': [
        'C:\\Users\\{user}\\AppData\\Local\\slack\\slack.exe',
    ],
    
    # Office
    'word': [
        'C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE',
        'C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\WINWORD.EXE',
    ],
    'excel': [
        'C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE',
        'C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\EXCEL.EXE',
    ],
    'powerpoint': [
        'C:\\Program Files\\Microsoft Office\\root\\Office16\\POWERPNT.EXE',
        'C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\POWERPNT.EXE',
    ],
    'outlook': [
        'C:\\Program Files\\Microsoft Office\\root\\Office16\\OUTLOOK.EXE',
        'C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\OUTLOOK.EXE',
    ],
}


class WindowManager:
    """
    Complete window and application management.
    Enables JARVIS-level application control via voice commands.
    """
    
    def __init__(self):
        """Initialize the window manager"""
        self.username = getpass.getuser()
        self._last_active_window = None
        
        if PYGETWINDOW_OK:
            logger.info("[OK] Window Manager initialized with pygetwindow")
        else:
            logger.warning("[!] Window Manager running in limited mode")
    
    # ==================== WINDOW LISTING ====================
    
    def list_windows(self, include_hidden: bool = False) -> Dict[str, Any]:
        """
        List all open windows.
        
        Args:
            include_hidden: Include windows with empty titles
        
        Returns:
            Dict with list of windows
        """
        if not PYGETWINDOW_OK:
            return self._list_windows_fallback()
        
        try:
            windows = []
            active_window = gw.getActiveWindow()
            active_title = active_window.title if active_window else ""
            
            for win in gw.getAllWindows():
                if not include_hidden and not win.title.strip():
                    continue
                
                try:
                    windows.append(WindowInfo(
                        title=win.title,
                        handle=win._hWnd,
                        x=win.left,
                        y=win.top,
                        width=win.width,
                        height=win.height,
                        is_active=(win.title == active_title),
                        is_minimized=win.isMinimized,
                        is_maximized=win.isMaximized,
                        process_name=""
                    ))
                except Exception as e:
                    continue
            
            return {
                'success': True,
                'count': len(windows),
                'windows': windows,
                'active': active_title
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to list windows: {e}")
            return {'success': False, 'error': str(e)}
    
    def _list_windows_fallback(self) -> Dict[str, Any]:
        """Fallback window listing using tasklist"""
        try:
            result = subprocess.run(
                ['tasklist', '/FO', 'CSV', '/NH'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            processes = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.replace('"', '').split(',')
                    if len(parts) >= 2:
                        processes.append({
                            'name': parts[0],
                            'pid': parts[1]
                        })
            
            return {
                'success': True,
                'count': len(processes),
                'processes': processes[:50],
                'note': 'Limited mode - showing processes, not windows'
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_active_window(self) -> Dict[str, Any]:
        """
        Get information about the currently active window.
        
        Returns:
            Dict with active window info
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            win = gw.getActiveWindow()
            if not win:
                return {'success': False, 'error': 'No active window'}
            
            return {
                'success': True,
                'title': win.title,
                'handle': win._hWnd,
                'x': win.left,
                'y': win.top,
                'width': win.width,
                'height': win.height,
                'is_minimized': win.isMinimized,
                'is_maximized': win.isMaximized
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to get active window: {e}")
            return {'success': False, 'error': str(e)}
    
    def find_window(self, search_term: str) -> Dict[str, Any]:
        """
        Find a window by partial title match.
        
        Args:
            search_term: Text to search for in window titles
        
        Returns:
            Dict with matching windows
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            search_lower = search_term.lower()
            matches = []
            
            for win in gw.getAllWindows():
                if search_lower in win.title.lower():
                    matches.append({
                        'title': win.title,
                        'handle': win._hWnd
                    })
            
            return {
                'success': True,
                'search': search_term,
                'count': len(matches),
                'matches': matches
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== WINDOW CONTROL ====================
    
    def switch_to_window(self, window_name: str) -> Dict[str, Any]:
        """
        Switch to a window by name (partial match).
        
        Args:
            window_name: Name/title of window to switch to
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return self._switch_window_fallback(window_name)
        
        try:
            # Save current window for potential switch back
            current = gw.getActiveWindow()
            if current:
                self._last_active_window = current.title
            
            # Find matching windows
            search_lower = window_name.lower()
            
            for win in gw.getAllWindows():
                if search_lower in win.title.lower():
                    try:
                        # Restore if minimized
                        if win.isMinimized:
                            win.restore()
                        
                        # Bring to front
                        win.activate()
                        
                        logger.info(f"[OK] Switched to: {win.title}")
                        return {
                            'success': True,
                            'window': win.title,
                            'message': f"Switched to {win.title}"
                        }
                    except Exception as e:
                        continue
            
            return {
                'success': False,
                'error': f"No window found matching '{window_name}'"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to switch window: {e}")
            return {'success': False, 'error': str(e)}
    
    def _switch_window_fallback(self, window_name: str) -> Dict[str, Any]:
        """Fallback window switching using Alt+Tab simulation"""
        try:
            import pyautogui
            pyautogui.hotkey('alt', 'tab')
            time.sleep(0.3)
            return {
                'success': True,
                'message': f"Attempted to switch windows (limited mode)",
                'note': 'Install pygetwindow for precise window control'
            }
        except Exception as e:
            return {'success': False, 'error': 'Window switching not available'}
    
    def switch_back(self) -> Dict[str, Any]:
        """Switch back to the previously active window"""
        if self._last_active_window:
            return self.switch_to_window(self._last_active_window)
        return {'success': False, 'error': 'No previous window recorded'}
    
    def maximize_window(self, window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Maximize a window (current window if no name given).
        
        Args:
            window_name: Window to maximize (optional)
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            if window_name:
                # Find and maximize specific window
                for win in gw.getAllWindows():
                    if window_name.lower() in win.title.lower():
                        win.maximize()
                        return {'success': True, 'window': win.title, 'action': 'maximized'}
                return {'success': False, 'error': f"Window '{window_name}' not found"}
            else:
                # Maximize current window
                win = gw.getActiveWindow()
                if win:
                    win.maximize()
                    return {'success': True, 'window': win.title, 'action': 'maximized'}
                return {'success': False, 'error': 'No active window'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def minimize_window(self, window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Minimize a window (current window if no name given).
        
        Args:
            window_name: Window to minimize (optional)
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            if window_name:
                for win in gw.getAllWindows():
                    if window_name.lower() in win.title.lower():
                        win.minimize()
                        return {'success': True, 'window': win.title, 'action': 'minimized'}
                return {'success': False, 'error': f"Window '{window_name}' not found"}
            else:
                win = gw.getActiveWindow()
                if win:
                    win.minimize()
                    return {'success': True, 'window': win.title, 'action': 'minimized'}
                return {'success': False, 'error': 'No active window'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def restore_window(self, window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Restore a minimized window.
        
        Args:
            window_name: Window to restore (optional)
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            if window_name:
                for win in gw.getAllWindows():
                    if window_name.lower() in win.title.lower():
                        win.restore()
                        win.activate()
                        return {'success': True, 'window': win.title, 'action': 'restored'}
                return {'success': False, 'error': f"Window '{window_name}' not found"}
            else:
                win = gw.getActiveWindow()
                if win:
                    win.restore()
                    return {'success': True, 'window': win.title, 'action': 'restored'}
                return {'success': False, 'error': 'No active window'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def close_window(self, window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Close a window (current window if no name given).
        
        Args:
            window_name: Window to close (optional)
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return self._close_window_fallback(window_name)
        
        try:
            if window_name:
                for win in gw.getAllWindows():
                    if window_name.lower() in win.title.lower():
                        win.close()
                        return {'success': True, 'window': win.title, 'action': 'closed'}
                return {'success': False, 'error': f"Window '{window_name}' not found"}
            else:
                win = gw.getActiveWindow()
                if win:
                    title = win.title
                    win.close()
                    return {'success': True, 'window': title, 'action': 'closed'}
                return {'success': False, 'error': 'No active window'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _close_window_fallback(self, window_name: Optional[str] = None) -> Dict[str, Any]:
        """Fallback window closing using Alt+F4"""
        try:
            import pyautogui
            pyautogui.hotkey('alt', 'F4')
            return {'success': True, 'message': 'Sent close command (Alt+F4)'}
        except Exception as e:
            return {'success': False, 'error': 'Cannot close window'}
    
    def minimize_all_windows(self) -> Dict[str, Any]:
        """Minimize all windows (show desktop)"""
        try:
            import pyautogui
            pyautogui.hotkey('win', 'd')
            return {'success': True, 'message': 'Minimized all windows'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== WINDOW ARRANGEMENT ====================
    
    def move_window(self, window_name: str, x: int, y: int) -> Dict[str, Any]:
        """
        Move a window to a specific position.
        
        Args:
            window_name: Window to move
            x: X position
            y: Y position
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            for win in gw.getAllWindows():
                if window_name.lower() in win.title.lower():
                    win.moveTo(x, y)
                    return {
                        'success': True,
                        'window': win.title,
                        'position': {'x': x, 'y': y}
                    }
            
            return {'success': False, 'error': f"Window '{window_name}' not found"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def resize_window(self, window_name: str, width: int, height: int) -> Dict[str, Any]:
        """
        Resize a window.
        
        Args:
            window_name: Window to resize
            width: New width
            height: New height
        
        Returns:
            Dict with success status
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        try:
            for win in gw.getAllWindows():
                if window_name.lower() in win.title.lower():
                    win.resizeTo(width, height)
                    return {
                        'success': True,
                        'window': win.title,
                        'size': {'width': width, 'height': height}
                    }
            
            return {'success': False, 'error': f"Window '{window_name}' not found"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def arrange_windows(self, layout: str = 'side_by_side', window_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Arrange windows in a specific layout.
        
        Args:
            layout: 'side_by_side', 'grid', 'cascade'
            window_names: Optional list of window names (uses first 2-4 if not specified)
        
        Returns:
            Dict with arrangement result
        """
        if not PYGETWINDOW_OK:
            return self._arrange_windows_fallback(layout)
        
        try:
            # Get screen size
            import pyautogui
            screen_width, screen_height = pyautogui.size()
            
            # Get windows to arrange
            if window_names:
                windows = []
                for name in window_names:
                    for win in gw.getAllWindows():
                        if name.lower() in win.title.lower():
                            windows.append(win)
                            break
            else:
                # Get visible windows (exclude minimized and empty titles)
                windows = [w for w in gw.getAllWindows() 
                          if w.title.strip() and not w.isMinimized][:4]
            
            if len(windows) < 2:
                return {'success': False, 'error': 'Need at least 2 windows to arrange'}
            
            arranged = []
            
            if layout == 'side_by_side':
                # Two windows side by side
                half_width = screen_width // 2
                
                if len(windows) >= 1:
                    windows[0].restore()
                    windows[0].moveTo(0, 0)
                    windows[0].resizeTo(half_width, screen_height - 40)
                    arranged.append(windows[0].title)
                
                if len(windows) >= 2:
                    windows[1].restore()
                    windows[1].moveTo(half_width, 0)
                    windows[1].resizeTo(half_width, screen_height - 40)
                    arranged.append(windows[1].title)
            
            elif layout == 'grid':
                # Four windows in a grid
                half_width = screen_width // 2
                half_height = (screen_height - 40) // 2
                
                positions = [
                    (0, 0),
                    (half_width, 0),
                    (0, half_height),
                    (half_width, half_height)
                ]
                
                for i, win in enumerate(windows[:4]):
                    x, y = positions[i]
                    win.restore()
                    win.moveTo(x, y)
                    win.resizeTo(half_width, half_height)
                    arranged.append(win.title)
            
            elif layout == 'cascade':
                # Cascade windows with offset
                offset = 30
                win_width = screen_width - 200
                win_height = screen_height - 200
                
                for i, win in enumerate(windows):
                    win.restore()
                    win.moveTo(i * offset, i * offset)
                    win.resizeTo(win_width - i * offset, win_height - i * offset)
                    arranged.append(win.title)
            
            return {
                'success': True,
                'layout': layout,
                'arranged': arranged,
                'message': f"Arranged {len(arranged)} windows in {layout} layout"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to arrange windows: {e}")
            return {'success': False, 'error': str(e)}
    
    def _arrange_windows_fallback(self, layout: str) -> Dict[str, Any]:
        """Fallback window arrangement using Windows snap shortcuts"""
        try:
            import pyautogui
            
            if layout == 'side_by_side':
                # Snap current window to left
                pyautogui.hotkey('win', 'left')
                time.sleep(0.3)
                
                return {
                    'success': True,
                    'message': 'Snapped window to left. Use Win+Right for the second window.',
                    'note': 'Install pygetwindow for full arrangement control'
                }
            
            return {'success': False, 'error': f'Layout {layout} not supported in fallback mode'}
        
        except Exception as e:
            return {'success': False, 'error': 'Window arrangement not available'}
    
    def snap_window(self, direction: str, window_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Snap window to screen edge using Windows shortcuts.
        
        Args:
            direction: 'left', 'right', 'top', 'bottom'
            window_name: Optional window to snap (switches to it first)
        
        Returns:
            Dict with success status
        """
        try:
            import pyautogui
            
            if window_name:
                self.switch_to_window(window_name)
                time.sleep(0.2)
            
            key_map = {
                'left': 'left',
                'right': 'right',
                'top': 'up',
                'up': 'up',
                'bottom': 'down',
                'down': 'down'
            }
            
            key = key_map.get(direction.lower())
            if not key:
                return {'success': False, 'error': f"Invalid direction: {direction}"}
            
            pyautogui.hotkey('win', key)
            return {
                'success': True,
                'direction': direction,
                'message': f"Snapped window to {direction}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== APPLICATION CONTROL ====================
    
    def open_application(self, app_name: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Open an application by name.
        
        Args:
            app_name: Name of application to open
            args: Optional arguments to pass
        
        Returns:
            Dict with success status
        """
        try:
            app_key = app_name.lower()
            
            # Check if we know this app
            if app_key in APP_PATHS:
                paths = APP_PATHS[app_key]
                
                # Handle string or list of paths
                if isinstance(paths, str):
                    paths = [paths]
                
                for path in paths:
                    # Replace {user} placeholder
                    path = path.replace('{user}', self.username)
                    
                    # Handle special URI schemes (ms-settings:, etc.)
                    if path.startswith('ms-'):
                        os.startfile(path)
                        return {
                            'success': True,
                            'app': app_name,
                            'message': f"Opened {app_name}"
                        }
                    
                    # Check if path exists or is a command
                    if Path(path).exists() or not path.endswith('.exe'):
                        try:
                            if args:
                                subprocess.Popen([path] + args)
                            else:
                                subprocess.Popen([path])
                            
                            logger.info(f"[OK] Opened: {app_name}")
                            return {
                                'success': True,
                                'app': app_name,
                                'path': path,
                                'message': f"Opened {app_name}"
                            }
                        except Exception as e:
                            continue
                
                return {'success': False, 'error': f"Could not find {app_name} installation"}
            
            # Try to run as a command
            try:
                if args:
                    subprocess.Popen([app_name] + args)
                else:
                    subprocess.Popen([app_name])
                
                return {
                    'success': True,
                    'app': app_name,
                    'message': f"Opened {app_name}"
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Unknown application: {app_name}"
                }
        
        except Exception as e:
            logger.error(f"[X] Failed to open application: {e}")
            return {'success': False, 'error': str(e)}
    
    def close_application(self, app_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Close an application by name.
        
        Args:
            app_name: Name of application to close
            force: Force close (kill process)
        
        Returns:
            Dict with success status
        """
        if not PSUTIL_OK:
            return self._close_app_fallback(app_name)
        
        try:
            app_lower = app_name.lower()
            closed = []
            
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    proc_name = proc.info['name'].lower()
                    
                    # Check for partial match
                    if app_lower in proc_name or app_lower in proc_name.replace('.exe', ''):
                        if force:
                            proc.kill()
                        else:
                            proc.terminate()
                        closed.append(proc.info['name'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if closed:
                logger.info(f"[OK] Closed: {closed}")
                return {
                    'success': True,
                    'closed': closed,
                    'message': f"Closed {len(closed)} instance(s) of {app_name}"
                }
            
            return {'success': False, 'error': f"No running process found for {app_name}"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _close_app_fallback(self, app_name: str) -> Dict[str, Any]:
        """Fallback application closing using taskkill"""
        try:
            result = subprocess.run(
                ['taskkill', '/IM', f'{app_name}.exe', '/T'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return {'success': True, 'message': f"Closed {app_name}"}
            else:
                return {'success': False, 'error': result.stderr or f"Could not close {app_name}"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def close_all_applications(self, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Close all non-system applications.
        
        Args:
            exclude: List of app names to exclude from closing
        
        Returns:
            Dict with closed applications
        """
        # System processes to never close
        system_processes = {
            'explorer.exe', 'system', 'csrss.exe', 'smss.exe', 'lsass.exe',
            'services.exe', 'winlogon.exe', 'dwm.exe', 'svchost.exe',
            'conhost.exe', 'python.exe', 'pythonw.exe'
        }
        
        if exclude:
            system_processes.update(x.lower() for x in exclude)
        
        if not PSUTIL_OK:
            return {'success': False, 'error': 'psutil not available'}
        
        closed = []
        
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    proc_name = proc.info['name'].lower()
                    
                    if proc_name not in system_processes:
                        proc.terminate()
                        closed.append(proc.info['name'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return {
                'success': True,
                'closed': closed[:20],  # Limit output
                'count': len(closed),
                'message': f"Closed {len(closed)} applications"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_running_apps(self) -> Dict[str, Any]:
        """Get list of running applications"""
        if not PSUTIL_OK:
            return {'success': False, 'error': 'psutil not available'}
        
        try:
            apps = set()
            
            for proc in psutil.process_iter(['name']):
                try:
                    name = proc.info['name']
                    if name.endswith('.exe'):
                        apps.add(name)
                except Exception as e:
                    continue
            
            return {
                'success': True,
                'count': len(apps),
                'apps': sorted(list(apps))
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def wait_for_window(self, window_title: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Wait for a window to appear.
        
        Args:
            window_title: Title to wait for (partial match)
            timeout: Maximum seconds to wait
        
        Returns:
            Dict with result
        """
        if not PYGETWINDOW_OK:
            return {'success': False, 'error': 'pygetwindow not available'}
        
        start_time = time.time()
        search_lower = window_title.lower()
        
        while time.time() - start_time < timeout:
            for win in gw.getAllWindows():
                if search_lower in win.title.lower():
                    return {
                        'success': True,
                        'window': win.title,
                        'wait_time': time.time() - start_time
                    }
            time.sleep(0.5)
        
        return {
            'success': False,
            'error': f"Window '{window_title}' did not appear within {timeout}s"
        }


# Factory function for workflow engine integration
def create_window_manager() -> WindowManager:
    """Create and return a WindowManager instance"""
    return WindowManager()


if __name__ == '__main__':
    # Test the window manager
    logging.basicConfig(level=logging.INFO)
    wm = WindowManager()
    
    print("\n=== Testing Window Manager ===")
    
    # List windows
    result = wm.list_windows()
    print(f"Open windows: {result.get('count', 0)}")
    if result.get('windows'):
        for w in result['windows'][:5]:
            status = "[ACTIVE]" if w.is_active else ""
            print(f"  - {w.title[:50]} {status}")
    
    # Get active window
    result = wm.get_active_window()
    print(f"\nActive window: {result.get('title', 'N/A')}")
    
    # Get running apps
    result = wm.get_running_apps()
    print(f"\nRunning apps: {result.get('count', 0)}")
    
    print("\n[OK] Window Manager tests complete!")
