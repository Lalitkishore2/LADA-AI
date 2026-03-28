"""
Tests for UI Components (Tray Icon and Overlay)
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys

# Mock pystray and PIL before import
sys.modules['pystray'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageDraw'] = MagicMock()

from ui.tray_icon import LADATrayIcon, TrayStatus, get_tray_icon


class TestLADATrayIcon:
    """Test system tray icon"""
    
    def test_tray_creation(self):
        """Test tray icon initializes"""
        tray = LADATrayIcon()
        assert tray is not None
        assert tray.app_name == "LADA"
    
    def test_custom_app_name(self):
        """Test custom app name"""
        tray = LADATrayIcon(app_name="My LADA")
        assert tray.app_name == "My LADA"
    
    def test_initial_status(self):
        """Test initial status is idle"""
        tray = LADATrayIcon()
        assert tray._status == TrayStatus.IDLE
    
    def test_set_status(self):
        """Test setting status"""
        tray = LADATrayIcon()
        tray.set_status(TrayStatus.LISTENING)
        assert tray._status == TrayStatus.LISTENING
    
    def test_all_status_values(self):
        """Test all status enum values"""
        assert TrayStatus.IDLE.value == "idle"
        assert TrayStatus.LISTENING.value == "listening"
        assert TrayStatus.PROCESSING.value == "processing"
        assert TrayStatus.ERROR.value == "error"
        assert TrayStatus.MUTED.value == "muted"
    
    def test_set_callbacks(self):
        """Test setting callbacks"""
        tray = LADATrayIcon()
        
        def on_exit():
            pass
        
        tray.set_callbacks(on_exit=on_exit)
        assert tray._on_exit is not None
    
    def test_update_tooltip(self):
        """Test updating tooltip"""
        tray = LADATrayIcon()
        tray.update_tooltip("Processing command...")
        assert tray._tooltip_extra == "Processing command..."
    
    def test_add_quick_command(self):
        """Test adding quick command"""
        tray = LADATrayIcon()
        initial_count = len(tray._quick_commands)
        tray.add_quick_command("🎵 Play Music", "play music")
        assert len(tray._quick_commands) == initial_count + 1
    
    def test_is_running_initially_false(self):
        """Test tray is not running initially"""
        tray = LADATrayIcon()
        assert tray.is_running == False


class TestGetTrayIcon:
    """Test tray icon singleton"""
    
    def test_singleton_pattern(self):
        """Test get_tray_icon returns singleton"""
        # Reset singleton
        import ui.tray_icon
        ui.tray_icon._tray_icon = None
        
        icon1 = get_tray_icon()
        icon2 = get_tray_icon()
        assert icon1 is icon2


class TestStatusColors:
    """Test status color mapping"""
    
    def test_status_colors_defined(self):
        """Test all statuses have colors"""
        from ui.tray_icon import STATUS_COLORS
        
        for status in TrayStatus:
            assert status in STATUS_COLORS
            color = STATUS_COLORS[status]
            assert len(color) == 3  # RGB tuple
