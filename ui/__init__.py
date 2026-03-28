"""
LADA UI Package
Desktop UI components including system tray and overlay
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tray_icon import LADATrayIcon, get_tray_icon
    from .desktop_overlay import LADAOverlay, get_overlay

__all__ = [
    'LADATrayIcon',
    'get_tray_icon',
    'LADAOverlay', 
    'get_overlay',
]
