"""
LADA App Executor — Handles open/close/launch commands for apps and websites.

Extracted from JarvisCommandProcessor._handle_open_command, _launch_app, _handle_close_command.
"""

import os
import re
import subprocess
import webbrowser
import logging
from typing import Tuple
from pathlib import Path

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


class AppExecutor(BaseExecutor):
    """Handles app launch, close, website navigation commands."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        cmd_lower = cmd.lower().strip()

        # Open/launch commands
        if any(cmd_lower.startswith(p) for p in ['open ', 'launch ', 'start ', 'run ']):
            return self._handle_open(cmd_lower)

        # Close/quit commands
        if any(cmd_lower.startswith(p) for p in ['close ', 'quit ', 'exit ', 'kill ']):
            return self._handle_close(cmd_lower)

        return False, ""

    def _handle_open(self, cmd: str) -> Tuple[bool, str]:
        """Handle open/launch commands for apps and websites."""
        from lada_jarvis_core import LadaPersonality

        for prefix in ['open ', 'launch ', 'start ', 'run ']:
            if prefix in cmd:
                target = cmd.split(prefix, 1)[-1].strip()
                break
        else:
            return False, ""

        # Check websites first
        for site, url in self.core.websites.items():
            if site in target:
                webbrowser.open(url)
                return True, f"{LadaPersonality.get_acknowledgment()} Opening {site}."

        # Check apps
        for app_name, paths in self.core.apps.items():
            if app_name in target:
                return self._launch_app(app_name, paths)

        # Special handling
        try:
            if 'file' in target or 'folder' in target or 'explorer' in target:
                os.startfile('explorer')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening File Explorer."

            if 'browser' in target:
                webbrowser.open('https://google.com')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening your browser."

            subprocess.Popen(target, shell=True)
            return True, f"{LadaPersonality.get_acknowledgment()} Opening {target}."
        except Exception:
            return True, f"I couldn't find an app called '{target}'. Could you be more specific?"

    def _launch_app(self, app_name: str, paths: list) -> Tuple[bool, str]:
        """Launch an application from known paths."""
        from lada_jarvis_core import LadaPersonality
        import getpass
        username = getpass.getuser()

        for path in paths:
            path = path.replace('{user}', username)

            if path.startswith('ms-'):
                os.system(f'start {path}')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."

            if Path(path).exists():
                try:
                    subprocess.Popen([path], shell=True)
                    return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
                except Exception:
                    continue

            if path.endswith('.exe') and '\\' not in path:
                try:
                    subprocess.Popen(path, shell=True)
                    return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
                except Exception:
                    continue

        if app_name in ['chrome', 'firefox', 'edge', 'browser']:
            try:
                webbrowser.open('https://google.com')
                return True, f"{LadaPersonality.get_acknowledgment()} Opening your browser."
            except Exception:
                pass

        try:
            os.system(f'start {app_name}')
            return True, f"{LadaPersonality.get_acknowledgment()} Opening {app_name}."
        except Exception:
            return True, f"I couldn't open {app_name}. Make sure it's installed."

    def _handle_close(self, cmd: str) -> Tuple[bool, str]:
        """Handle close/quit commands."""
        from lada_jarvis_core import LadaPersonality

        for prefix in ['close ', 'quit ', 'exit ', 'kill ']:
            if prefix in cmd:
                target = cmd.split(prefix, 1)[-1].strip()
                break
        else:
            return False, ""

        process_map = {
            'chrome': 'chrome.exe', 'firefox': 'firefox.exe', 'edge': 'msedge.exe',
            'notepad': 'notepad.exe', 'spotify': 'Spotify.exe', 'discord': 'Discord.exe',
            'vscode': 'Code.exe', 'vs code': 'Code.exe', 'vlc': 'vlc.exe',
            'word': 'WINWORD.EXE', 'excel': 'EXCEL.EXE',
        }

        proc_name = process_map.get(target, f'{target}.exe')

        try:
            os.system(f'taskkill /im {proc_name} /f')
            return True, f"{LadaPersonality.get_confirmation()} Closed {target}."
        except Exception:
            return True, f"I couldn't close {target}."
