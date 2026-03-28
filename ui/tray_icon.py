"""
LADA System Tray Icon

Provides a system tray icon with:
- Status indicator (listening/processing/idle)
- Quick command menu
- Dashboard shortcut
- Exit option

Requires: pystray>=0.19.0, Pillow
"""

import os
import sys
import logging
import threading
import webbrowser
from typing import Optional, Callable, Dict, Any
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional imports
try:
    import pystray
    from pystray import MenuItem as item
    PYSTRAY_OK = True
except ImportError:
    PYSTRAY_OK = False
    logger.warning("pystray not installed. System tray disabled. pip install pystray")

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False
    logger.warning("Pillow not installed. Icon generation disabled. pip install Pillow")


class TrayStatus(Enum):
    """Tray icon status states"""
    IDLE = "idle"           # Gray - waiting for input
    LISTENING = "listening"  # Green - voice active
    PROCESSING = "processing"  # Blue - thinking
    ERROR = "error"         # Red - error state
    MUTED = "muted"         # Orange - voice disabled


# Status colors (RGB)
STATUS_COLORS = {
    TrayStatus.IDLE: (128, 128, 128),       # Gray
    TrayStatus.LISTENING: (0, 200, 83),     # Green
    TrayStatus.PROCESSING: (33, 150, 243),  # Blue
    TrayStatus.ERROR: (244, 67, 54),        # Red
    TrayStatus.MUTED: (255, 152, 0),        # Orange
}


class LADATrayIcon:
    """
    System tray icon for LADA with status indication and quick actions.
    
    Usage:
        tray = LADATrayIcon()
        tray.set_callbacks(
            on_open_dashboard=lambda: webbrowser.open("http://localhost:5000/app"),
            on_toggle_voice=lambda: toggle_voice(),
            on_exit=lambda: sys.exit(0)
        )
        tray.start()
        
        # Update status
        tray.set_status(TrayStatus.LISTENING)
        tray.update_tooltip("Listening...")
    """
    
    def __init__(self, app_name: str = "LADA"):
        self.app_name = app_name
        self._status = TrayStatus.IDLE
        self._icon: Optional["pystray.Icon"] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        # Callbacks
        self._on_open_dashboard: Optional[Callable] = None
        self._on_toggle_voice: Optional[Callable] = None
        self._on_toggle_listening: Optional[Callable] = None
        self._on_quick_command: Optional[Callable[[str], None]] = None
        self._on_exit: Optional[Callable] = None
        
        # Quick commands
        self._quick_commands = [
            ("🔍 Search the web", "search the web"),
            ("📅 What's on my calendar", "what's on my calendar"),
            ("☀️ Weather today", "what's the weather"),
            ("📧 Check email", "check my email"),
            ("⏰ Set a timer", "set a timer"),
        ]
        
        # Status info for tooltip
        self._tooltip_extra = ""
    
    def set_callbacks(
        self,
        on_open_dashboard: Optional[Callable] = None,
        on_toggle_voice: Optional[Callable] = None,
        on_toggle_listening: Optional[Callable] = None,
        on_quick_command: Optional[Callable[[str], None]] = None,
        on_exit: Optional[Callable] = None,
    ):
        """Set callback functions for menu actions"""
        self._on_open_dashboard = on_open_dashboard
        self._on_toggle_voice = on_toggle_voice
        self._on_toggle_listening = on_toggle_listening
        self._on_quick_command = on_quick_command
        self._on_exit = on_exit
    
    def _create_icon_image(self, status: TrayStatus) -> "Image.Image":
        """Generate icon image based on status"""
        if not PIL_OK:
            raise RuntimeError("Pillow required for icon generation")
        
        # Create 64x64 icon
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        color = STATUS_COLORS.get(status, STATUS_COLORS[TrayStatus.IDLE])
        
        # Draw circle with border
        padding = 4
        draw.ellipse(
            [padding, padding, size - padding, size - padding],
            fill=color,
            outline=(255, 255, 255),
            width=2
        )
        
        # Draw "L" for LADA
        text_color = (255, 255, 255)
        # Simple L shape (no font required)
        draw.rectangle([22, 18, 28, 46], fill=text_color)  # Vertical
        draw.rectangle([22, 40, 42, 46], fill=text_color)  # Horizontal
        
        return img
    
    def _get_icon_path(self) -> Optional[Path]:
        """Get path to custom icon file if it exists"""
        possible_paths = [
            Path("assets/lada_icon.ico"),
            Path("assets/lada_icon.png"),
            Path("assets/icon.ico"),
            Path("assets/icon.png"),
        ]
        for p in possible_paths:
            if p.exists():
                return p
        return None
    
    def _load_icon(self) -> "Image.Image":
        """Load icon from file or generate dynamically"""
        if not PIL_OK:
            raise RuntimeError("Pillow required")
        
        icon_path = self._get_icon_path()
        if icon_path:
            try:
                return Image.open(icon_path)
            except Exception as e:
                logger.warning(f"Failed to load icon {icon_path}: {e}")
        
        return self._create_icon_image(self._status)
    
    def _build_menu(self) -> "pystray.Menu":
        """Build the tray icon context menu"""
        if not PYSTRAY_OK:
            raise RuntimeError("pystray required")
        
        menu_items = []
        
        # Status header
        status_text = f"Status: {self._status.value.title()}"
        menu_items.append(item(status_text, None, enabled=False))
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # Dashboard
        menu_items.append(item(
            "🖥️ Open Dashboard",
            self._handle_open_dashboard
        ))
        
        # Voice controls
        voice_label = "🎤 Toggle Voice" 
        menu_items.append(item(voice_label, self._handle_toggle_voice))
        
        listen_label = "👂 Start Listening" if self._status != TrayStatus.LISTENING else "🔇 Stop Listening"
        menu_items.append(item(listen_label, self._handle_toggle_listening))
        
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # Quick commands submenu
        quick_items = [
            item(label, lambda _, cmd=cmd: self._handle_quick_command(cmd))
            for label, cmd in self._quick_commands
        ]
        menu_items.append(item(
            "⚡ Quick Commands",
            pystray.Menu(*quick_items)
        ))
        
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # Exit
        menu_items.append(item("❌ Exit LADA", self._handle_exit))
        
        return pystray.Menu(*menu_items)
    
    def _handle_open_dashboard(self, icon, item):
        """Handle dashboard menu click"""
        if self._on_open_dashboard:
            self._on_open_dashboard()
        else:
            webbrowser.open("http://localhost:5000/app")
    
    def _handle_toggle_voice(self, icon, item):
        """Handle voice toggle"""
        if self._on_toggle_voice:
            self._on_toggle_voice()
    
    def _handle_toggle_listening(self, icon, item):
        """Handle listening toggle"""
        if self._on_toggle_listening:
            self._on_toggle_listening()
    
    def _handle_quick_command(self, command: str):
        """Handle quick command selection"""
        if self._on_quick_command:
            self._on_quick_command(command)
        else:
            logger.info(f"Quick command: {command}")
    
    def _handle_exit(self, icon, item):
        """Handle exit menu click"""
        self.stop()
        if self._on_exit:
            self._on_exit()
    
    def set_status(self, status: TrayStatus):
        """Update the tray icon status"""
        self._status = status
        if self._icon and PIL_OK:
            self._icon.icon = self._create_icon_image(status)
            self._update_tooltip()
    
    def _update_tooltip(self):
        """Update tooltip text"""
        if not self._icon:
            return
        
        tooltip = f"LADA - {self._status.value.title()}"
        if self._tooltip_extra:
            tooltip += f"\n{self._tooltip_extra}"
        self._icon.title = tooltip
    
    def update_tooltip(self, extra: str = ""):
        """Set extra tooltip text"""
        self._tooltip_extra = extra
        self._update_tooltip()
    
    def add_quick_command(self, label: str, command: str):
        """Add a quick command to the menu"""
        self._quick_commands.append((label, command))
        if self._icon:
            self._icon.menu = self._build_menu()
    
    def show_notification(self, title: str, message: str):
        """Show a system notification"""
        if self._icon and hasattr(self._icon, 'notify'):
            try:
                self._icon.notify(message, title)
            except Exception as e:
                logger.warning(f"Notification failed: {e}")
    
    def start(self, blocking: bool = False):
        """Start the tray icon"""
        if not PYSTRAY_OK or not PIL_OK:
            logger.error("Cannot start tray: pystray and Pillow required")
            return False
        
        if self._running:
            return True
        
        try:
            self._icon = pystray.Icon(
                self.app_name,
                self._load_icon(),
                self.app_name,
                menu=self._build_menu()
            )
            self._running = True
            
            if blocking:
                self._icon.run()
            else:
                self._thread = threading.Thread(target=self._icon.run, daemon=True)
                self._thread.start()
            
            logger.info("System tray icon started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start tray icon: {e}")
            return False
    
    def stop(self):
        """Stop the tray icon"""
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        logger.info("System tray icon stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running


# Module-level singleton
_tray_icon: Optional[LADATrayIcon] = None


def get_tray_icon() -> LADATrayIcon:
    """Get or create the global tray icon instance"""
    global _tray_icon
    if _tray_icon is None:
        _tray_icon = LADATrayIcon()
    return _tray_icon


if __name__ == "__main__":
    # Test the tray icon
    logging.basicConfig(level=logging.INFO)
    
    tray = get_tray_icon()
    tray.set_callbacks(
        on_exit=lambda: sys.exit(0)
    )
    
    print("Starting LADA tray icon...")
    print("Right-click the tray icon for options")
    
    # Start and run until exit
    tray.start(blocking=True)
