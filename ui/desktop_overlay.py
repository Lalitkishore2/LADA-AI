"""
LADA Desktop Overlay

A floating HUD overlay showing:
- Current status (listening/processing/idle)
- Voice waveform animation
- Response text overlay
- Minimal mode option

Requires: PyQt5 (already installed with LADA)
"""

import os
import sys
import math
import random
import logging
from typing import Optional, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)

# PyQt5 imports
try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QPushButton, QFrame, QGraphicsOpacityEffect
    )
    from PyQt5.QtCore import (
        Qt, QTimer, QPropertyAnimation, QEasingCurve, 
        pyqtSignal, QPoint, QRect
    )
    from PyQt5.QtGui import (
        QPainter, QColor, QPen, QBrush, QPainterPath,
        QFont, QFontMetrics, QLinearGradient
    )
    PYQT_OK = True
except ImportError:
    PYQT_OK = False
    logger.warning("PyQt5 not available. Desktop overlay disabled.")


class OverlayMode(Enum):
    """Overlay display modes"""
    FULL = "full"           # Full overlay with waveform
    MINIMAL = "minimal"     # Just status indicator
    HIDDEN = "hidden"       # Completely hidden
    TEXT_ONLY = "text_only" # Text response only


class OverlayPosition(Enum):
    """Overlay screen positions"""
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"


if PYQT_OK:
    class WaveformWidget(QWidget):
        """Animated voice waveform visualization"""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedSize(200, 60)
            self.setAttribute(Qt.WA_TranslucentBackground)
            
            # Waveform parameters
            self._bars = 20
            self._bar_values: List[float] = [0.0] * self._bars
            self._target_values: List[float] = [0.0] * self._bars
            self._is_active = False
            
            # Colors
            self._active_color = QColor(0, 200, 83)    # Green
            self._idle_color = QColor(128, 128, 128)   # Gray
            
            # Animation timer
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_animation)
            self._timer.start(50)  # 20 FPS
        
        def set_active(self, active: bool):
            """Set waveform active state"""
            self._is_active = active
            if not active:
                self._target_values = [0.0] * self._bars
        
        def set_level(self, level: float):
            """Set audio level (0.0 to 1.0) for visualization"""
            if self._is_active:
                # Create natural-looking waveform based on level
                for i in range(self._bars):
                    base = level * random.uniform(0.3, 1.0)
                    # Add some variation
                    variation = math.sin(i * 0.5 + random.random()) * 0.2
                    self._target_values[i] = min(1.0, max(0.0, base + variation))
        
        def _update_animation(self):
            """Smooth animation update"""
            changed = False
            for i in range(self._bars):
                diff = self._target_values[i] - self._bar_values[i]
                if abs(diff) > 0.01:
                    self._bar_values[i] += diff * 0.3
                    changed = True
                elif self._is_active:
                    # Add slight movement when active
                    self._target_values[i] = random.uniform(0.1, 0.4)
            
            if changed or self._is_active:
                self.update()
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            width = self.width()
            height = self.height()
            bar_width = (width - (self._bars - 1) * 2) / self._bars
            
            color = self._active_color if self._is_active else self._idle_color
            
            for i, value in enumerate(self._bar_values):
                x = i * (bar_width + 2)
                bar_height = max(4, value * (height - 4))
                y = (height - bar_height) / 2
                
                # Gradient for bar
                gradient = QLinearGradient(0, y, 0, y + bar_height)
                gradient.setColorAt(0, color.lighter(120))
                gradient.setColorAt(1, color)
                
                painter.setBrush(QBrush(gradient))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(int(x), int(y), int(bar_width), int(bar_height), 2, 2)
    
    
    class StatusIndicator(QWidget):
        """Status dot indicator with label"""
        
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedSize(120, 30)
            self.setAttribute(Qt.WA_TranslucentBackground)
            
            self._status = "idle"
            self._status_text = "Idle"
            
            # Status colors
            self._colors = {
                "idle": QColor(128, 128, 128),
                "listening": QColor(0, 200, 83),
                "processing": QColor(33, 150, 243),
                "error": QColor(244, 67, 54),
                "muted": QColor(255, 152, 0),
            }
        
        def set_status(self, status: str, text: str = ""):
            self._status = status
            self._status_text = text or status.title()
            self.update()
        
        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            color = self._colors.get(self._status, self._colors["idle"])
            
            # Draw status dot
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))
            painter.drawEllipse(5, 8, 14, 14)
            
            # Draw text
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Segoe UI", 10)
            painter.setFont(font)
            painter.drawText(25, 20, self._status_text)
    
    
    class LADAOverlay(QWidget):
        """
        Main overlay window for LADA status and feedback.
        
        Usage:
            overlay = LADAOverlay()
            overlay.set_mode(OverlayMode.FULL)
            overlay.set_position(OverlayPosition.TOP_CENTER)
            overlay.show()
            
            overlay.set_status("listening", "Listening...")
            overlay.show_response("The weather today is sunny.")
        """
        
        # Signals
        closed = pyqtSignal()
        minimized = pyqtSignal()
        
        def __init__(self, parent=None):
            super().__init__(parent)
            
            # Window flags for overlay behavior
            self.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.Tool |
                Qt.WindowTransparentForInput
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            
            # State
            self._mode = OverlayMode.FULL
            self._position = OverlayPosition.TOP_CENTER
            self._dragging = False
            self._drag_offset = QPoint()
            
            # Setup UI
            self._setup_ui()
            
            # Auto-hide timer
            self._hide_timer = QTimer(self)
            self._hide_timer.setSingleShot(True)
            self._hide_timer.timeout.connect(self._auto_hide)
            
            # Position on screen
            self._apply_position()
        
        def _setup_ui(self):
            """Initialize UI components"""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 15, 20, 15)
            layout.setSpacing(10)
            
            # Main container with background
            self._container = QFrame()
            self._container.setObjectName("overlay_container")
            self._container.setStyleSheet("""
                #overlay_container {
                    background-color: rgba(30, 30, 30, 220);
                    border-radius: 15px;
                    border: 1px solid rgba(255, 255, 255, 30);
                }
            """)
            
            container_layout = QVBoxLayout(self._container)
            container_layout.setContentsMargins(15, 12, 15, 12)
            container_layout.setSpacing(8)
            
            # Header with status and close button
            header = QHBoxLayout()
            
            self._status_indicator = StatusIndicator()
            header.addWidget(self._status_indicator)
            
            header.addStretch()
            
            # Mode toggle button
            self._mode_btn = QPushButton("−")
            self._mode_btn.setFixedSize(24, 24)
            self._mode_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 20);
                    border: none;
                    border-radius: 12px;
                    color: white;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 40);
                }
            """)
            self._mode_btn.clicked.connect(self._toggle_mode)
            header.addWidget(self._mode_btn)
            
            container_layout.addLayout(header)
            
            # Waveform
            self._waveform = WaveformWidget()
            container_layout.addWidget(self._waveform, alignment=Qt.AlignCenter)
            
            # Response text
            self._response_label = QLabel()
            self._response_label.setWordWrap(True)
            self._response_label.setAlignment(Qt.AlignCenter)
            self._response_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 13px;
                    padding: 5px;
                }
            """)
            self._response_label.setMaximumWidth(350)
            self._response_label.hide()
            container_layout.addWidget(self._response_label)
            
            layout.addWidget(self._container)
            
            # Set initial size
            self.setFixedWidth(400)
            self.adjustSize()
        
        def _apply_position(self):
            """Apply position on screen"""
            screen = QApplication.primaryScreen().geometry()
            
            if self._position == OverlayPosition.TOP_CENTER:
                x = (screen.width() - self.width()) // 2
                y = 50
            elif self._position == OverlayPosition.TOP_RIGHT:
                x = screen.width() - self.width() - 50
                y = 50
            elif self._position == OverlayPosition.BOTTOM_CENTER:
                x = (screen.width() - self.width()) // 2
                y = screen.height() - self.height() - 100
            elif self._position == OverlayPosition.BOTTOM_RIGHT:
                x = screen.width() - self.width() - 50
                y = screen.height() - self.height() - 100
            else:  # CENTER
                x = (screen.width() - self.width()) // 2
                y = (screen.height() - self.height()) // 2
            
            self.move(x, y)
        
        def set_mode(self, mode: OverlayMode):
            """Set overlay display mode"""
            self._mode = mode
            
            if mode == OverlayMode.HIDDEN:
                self.hide()
            elif mode == OverlayMode.MINIMAL:
                self._waveform.hide()
                self._response_label.hide()
                self._container.setFixedWidth(150)
                self.adjustSize()
                self.show()
            elif mode == OverlayMode.TEXT_ONLY:
                self._waveform.hide()
                self._container.setFixedWidth(400)
                self.adjustSize()
                self.show()
            else:  # FULL
                self._waveform.show()
                self._container.setFixedWidth(400)
                self.adjustSize()
                self.show()
            
            self._apply_position()
        
        def _toggle_mode(self):
            """Cycle through modes"""
            modes = [OverlayMode.FULL, OverlayMode.MINIMAL, OverlayMode.HIDDEN]
            current_idx = modes.index(self._mode) if self._mode in modes else 0
            next_idx = (current_idx + 1) % len(modes)
            self.set_mode(modes[next_idx])
            self.minimized.emit()
        
        def set_position(self, position: OverlayPosition):
            """Set overlay position"""
            self._position = position
            self._apply_position()
        
        def set_status(self, status: str, text: str = ""):
            """Update status display"""
            self._status_indicator.set_status(status, text)
            
            # Update waveform state
            is_listening = status == "listening"
            self._waveform.set_active(is_listening)
        
        def set_audio_level(self, level: float):
            """Update audio visualization level (0.0 to 1.0)"""
            self._waveform.set_level(level)
        
        def show_response(self, text: str, auto_hide_seconds: float = 5.0):
            """Show response text"""
            if not text:
                self._response_label.hide()
                return
            
            # Truncate long text
            if len(text) > 200:
                text = text[:197] + "..."
            
            self._response_label.setText(text)
            self._response_label.show()
            self.adjustSize()
            
            # Auto-hide after delay
            if auto_hide_seconds > 0:
                self._hide_timer.start(int(auto_hide_seconds * 1000))
        
        def _auto_hide(self):
            """Auto-hide response text"""
            self._response_label.hide()
            self.adjustSize()
        
        def clear_response(self):
            """Clear response text"""
            self._hide_timer.stop()
            self._response_label.hide()
            self.adjustSize()
        
        # Dragging support
        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._dragging = True
                self._drag_offset = event.pos()
                # Temporarily make clickable
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowTransparentForInput)
                self.show()
        
        def mouseMoveEvent(self, event):
            if self._dragging:
                self.move(self.mapToGlobal(event.pos() - self._drag_offset))
        
        def mouseReleaseEvent(self, event):
            self._dragging = False
            # Restore click-through
            self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
            self.show()
        
        def closeEvent(self, event):
            self.closed.emit()
            super().closeEvent(event)


# Module-level singleton
_overlay: Optional["LADAOverlay"] = None


def get_overlay() -> Optional["LADAOverlay"]:
    """Get or create the global overlay instance"""
    global _overlay
    if not PYQT_OK:
        logger.warning("PyQt5 not available - cannot create overlay")
        return None
    if _overlay is None:
        _overlay = LADAOverlay()
    return _overlay


if __name__ == "__main__":
    # Test the overlay
    if not PYQT_OK:
        print("PyQt5 required for overlay")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO)
    
    app = QApplication(sys.argv)
    
    overlay = get_overlay()
    overlay.set_mode(OverlayMode.FULL)
    overlay.set_position(OverlayPosition.TOP_CENTER)
    overlay.set_status("idle", "Ready")
    overlay.show()
    
    # Simulate activity
    def simulate():
        import random
        overlay.set_status("listening", "Listening...")
        overlay.set_audio_level(random.random())
        QTimer.singleShot(3000, lambda: overlay.set_status("processing", "Thinking..."))
        QTimer.singleShot(5000, lambda: (
            overlay.set_status("idle", "Ready"),
            overlay.show_response("The weather today is sunny with a high of 75°F")
        ))
    
    QTimer.singleShot(1000, simulate)
    
    sys.exit(app.exec_())
