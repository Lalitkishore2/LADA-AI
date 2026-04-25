#!/usr/bin/env python3
"""LADA Screen Agent - Standalone Copilot-like overlay agent.

A floating transparent overlay that provides AI-powered screen control,
independent of the main LADA desktop application.

Features:
- Hotkey activation (Win+Shift+L by default)
- Screenshot → AI analysis → action execution
- Floating command input with response area
- Works as a separate process from LADA
- Can use local Ollama or LADA API

Usage:
    python screen_agent.py                  # Run with GUI overlay
    python screen_agent.py --headless       # Run as hotkey listener only
    python screen_agent.py --api-url URL    # Connect to specific LADA API

Requirements:
    pip install pyautogui pillow keyboard requests
    Optional: pip install PyQt5  (for GUI overlay)
"""

from __future__ import annotations

import os
import sys
import json
import time
import base64
import logging
import threading
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable, List, Dict, Any

try:
    from modules.dlp_filter import get_dlp_filter
    DLP_FILTER_OK = True
except ImportError:
    DLP_FILTER_OK = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Optional imports with graceful degradation
try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    logger.warning("pyautogui not available - screen capture disabled")

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False
    logger.warning("PIL not available - image processing disabled")

try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False
    logger.warning("keyboard not available - hotkeys disabled")

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    logger.warning("requests not available - API calls disabled")

# Qt imports for GUI
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QSystemTrayIcon, QMenu
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QPoint
    from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QCursor
    QT_OK = True
except ImportError:
    QT_OK = False
    logger.warning("PyQt5 not available - GUI overlay disabled")


@dataclass
class ScreenAgentConfig:
    """Configuration for the screen agent."""
    api_url: str = "http://localhost:5000"
    hotkey: str = "win+shift+l"
    ollama_url: str = "http://localhost:11434"
    model: str = "llava"  # Vision model for screenshots
    use_local: bool = True  # Try local Ollama first
    window_opacity: float = 0.95
    window_width: int = 500
    window_height: int = 400


class ScreenCapture:
    """Handles screenshot capture and processing."""
    
    @staticmethod
    def capture_screen() -> Optional[Image.Image]:
        """Capture the entire screen."""
        if not PYAUTOGUI_OK or not PIL_OK:
            return None
        try:
            screenshot = pyautogui.screenshot()
            return screenshot
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None
    
    @staticmethod
    def capture_region(x: int, y: int, width: int, height: int) -> Optional[Image.Image]:
        """Capture a specific region of the screen."""
        if not PYAUTOGUI_OK or not PIL_OK:
            return None
        try:
            screenshot = pyautogui.screenshot(region=(x, y, width, height))
            return screenshot
        except Exception as e:
            logger.error(f"Region capture failed: {e}")
            return None
    
    @staticmethod
    def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
        """Convert PIL Image to base64 string."""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    @staticmethod
    def extract_text_blocks(image: Image.Image) -> List[Dict[str, Any]]:
        """Extract text blocks using pytesseract for DLP redaction."""
        try:
            import pytesseract
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            blocks = []
            n = len(data["text"])
            for i in range(n):
                text = (data["text"][i] or "").strip()
                if not text or len(text) < 2:
                    continue
                blocks.append({
                    "text": text,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                })
            return blocks
        except Exception as e:
            logger.debug(f"OCR text extraction failed: {e}")
            return []


class AIBackend:
    """Handles AI inference - local Ollama or LADA API."""
    
    def __init__(self, config: ScreenAgentConfig):
        self.config = config
        self._ollama_available = False
        self._check_ollama()
    
    def _check_ollama(self):
        """Check if local Ollama is available."""
        if not REQUESTS_OK:
            return
        try:
            resp = requests.get(f"{self.config.ollama_url}/api/tags", timeout=2)
            self._ollama_available = resp.status_code == 200
            if self._ollama_available:
                logger.info("Local Ollama detected")
        except Exception:
            self._ollama_available = False
    
    def analyze_screenshot(self, image: Image.Image, prompt: str) -> str:
        """Analyze a screenshot with AI vision."""
        if self.config.use_local and self._ollama_available:
            return self._analyze_with_ollama(image, prompt)
        else:
            return self._analyze_with_api(image, prompt)
    
    def _analyze_with_ollama(self, image: Image.Image, prompt: str) -> str:
        """Use local Ollama for vision analysis."""
        if not REQUESTS_OK:
            return "Error: requests library not available"
        
        try:
            # Convert image to base64
            img_b64 = ScreenCapture.image_to_base64(image)
            
            # Call Ollama API
            payload = {
                "model": self.config.model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False
            }
            
            resp = requests.post(
                f"{self.config.ollama_url}/api/generate",
                json=payload,
                timeout=60
            )
            
            if resp.status_code == 200:
                return resp.json().get("response", "No response")
            else:
                logger.error(f"Ollama error: {resp.status_code}")
                return f"Error: Ollama returned {resp.status_code}"
                
        except Exception as e:
            logger.error(f"Ollama analysis failed: {e}")
            return f"Error: {e}"
    
    def _analyze_with_api(self, image: Image.Image, prompt: str) -> str:
        """Use LADA API for vision analysis."""
        if not REQUESTS_OK:
            return "Error: requests library not available"
        
        try:
            img_b64 = ScreenCapture.image_to_base64(image)
            
            payload = {
                "message": prompt,
                "image": img_b64,
                "stream": False
            }
            
            resp = requests.post(
                f"{self.config.api_url}/chat",
                json=payload,
                timeout=60
            )
            
            if resp.status_code == 200:
                return resp.json().get("response", "No response")
            else:
                return f"API error: {resp.status_code}"
                
        except Exception as e:
            logger.error(f"API analysis failed: {e}")
            return f"Error: {e}"
    
    def execute_command(self, command: str) -> str:
        """Execute a text command via LADA API."""
        if not REQUESTS_OK:
            return "Error: requests library not available"
        
        try:
            payload = {
                "message": command,
                "stream": False
            }
            
            resp = requests.post(
                f"{self.config.api_url}/chat",
                json=payload,
                timeout=30
            )
            
            if resp.status_code == 200:
                return resp.json().get("response", "Command executed")
            else:
                return f"API error: {resp.status_code}"
                
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return f"Error: {e}"


class GUIAutomator:
    """Executes GUI actions based on AI decisions."""
    
    @staticmethod
    def click(x: int, y: int):
        """Click at position."""
        if PYAUTOGUI_OK:
            pyautogui.click(x, y)
    
    @staticmethod
    def double_click(x: int, y: int):
        """Double-click at position."""
        if PYAUTOGUI_OK:
            pyautogui.doubleClick(x, y)
    
    @staticmethod
    def right_click(x: int, y: int):
        """Right-click at position."""
        if PYAUTOGUI_OK:
            pyautogui.rightClick(x, y)
    
    @staticmethod
    def type_text(text: str, interval: float = 0.02):
        """Type text with human-like delays."""
        if PYAUTOGUI_OK:
            pyautogui.write(text, interval=interval)
    
    @staticmethod
    def hotkey(*keys):
        """Press a hotkey combination."""
        if PYAUTOGUI_OK:
            pyautogui.hotkey(*keys)
    
    @staticmethod
    def scroll(clicks: int, x: Optional[int] = None, y: Optional[int] = None):
        """Scroll up (positive) or down (negative)."""
        if PYAUTOGUI_OK:
            pyautogui.scroll(clicks, x, y)
    
    @staticmethod
    def move_to(x: int, y: int, duration: float = 0.2):
        """Move mouse to position."""
        if PYAUTOGUI_OK:
            pyautogui.moveTo(x, y, duration=duration)


if QT_OK:
    class WorkerThread(QThread):
        """Background worker for AI operations."""
        finished = pyqtSignal(str)
        
        def __init__(self, func: Callable, *args):
            super().__init__()
            self.func = func
            self.args = args
        
        def run(self):
            try:
                result = self.func(*self.args)
                self.finished.emit(result)
            except Exception as e:
                self.finished.emit(f"Error: {e}")
    
    
    class OverlayWindow(QMainWindow):
        """Floating transparent overlay window."""
        
        def __init__(self, config: ScreenAgentConfig, ai_backend: AIBackend):
            super().__init__()
            self.config = config
            self.ai = ai_backend
            self.worker = None
            self.drag_position = None
            
            self._setup_window()
            self._setup_ui()
            self._apply_styles()
        
        def _setup_window(self):
            """Configure window properties."""
            self.setWindowTitle("LADA Screen Agent")
            self.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.Tool
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedSize(self.config.window_width, self.config.window_height)
            
            # Position in bottom-right corner
            screen = QApplication.primaryScreen().geometry()
            self.move(
                screen.width() - self.config.window_width - 20,
                screen.height() - self.config.window_height - 60
            )
        
        def _setup_ui(self):
            """Build the UI."""
            # Central widget with rounded corners
            central = QWidget()
            central.setObjectName("central")
            self.setCentralWidget(central)
            
            layout = QVBoxLayout(central)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            
            # Header bar
            header = QFrame()
            header.setObjectName("header")
            header.setFixedHeight(40)
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(15, 0, 10, 0)
            
            title = QLabel("LADA Screen Agent")
            title.setObjectName("title")
            header_layout.addWidget(title)
            
            header_layout.addStretch()
            
            # Screenshot button
            screenshot_btn = QPushButton("📷")
            screenshot_btn.setObjectName("iconBtn")
            screenshot_btn.setFixedSize(30, 30)
            screenshot_btn.setToolTip("Analyze screen")
            screenshot_btn.clicked.connect(self._analyze_screen)
            header_layout.addWidget(screenshot_btn)
            
            # Minimize button
            min_btn = QPushButton("−")
            min_btn.setObjectName("iconBtn")
            min_btn.setFixedSize(30, 30)
            min_btn.clicked.connect(self.hide)
            header_layout.addWidget(min_btn)
            
            # Close button
            close_btn = QPushButton("×")
            close_btn.setObjectName("closeBtn")
            close_btn.setFixedSize(30, 30)
            close_btn.clicked.connect(QApplication.quit)
            header_layout.addWidget(close_btn)
            
            layout.addWidget(header)
            
            # Response area
            self.response_area = QTextEdit()
            self.response_area.setObjectName("response")
            self.response_area.setReadOnly(True)
            self.response_area.setPlaceholderText(
                "Press 📷 to analyze your screen, or type a command below.\n\n"
                "Examples:\n"
                "• What's on my screen?\n"
                "• Click the search button\n"
                "• Type 'hello' in the text field\n"
                "• Open Chrome"
            )
            layout.addWidget(self.response_area)
            
            # Input area
            input_frame = QFrame()
            input_frame.setObjectName("inputFrame")
            input_layout = QHBoxLayout(input_frame)
            input_layout.setContentsMargins(10, 10, 10, 10)
            
            self.input_field = QLineEdit()
            self.input_field.setObjectName("input")
            self.input_field.setPlaceholderText("Type a command...")
            self.input_field.returnPressed.connect(self._execute_command)
            input_layout.addWidget(self.input_field)
            
            send_btn = QPushButton("→")
            send_btn.setObjectName("sendBtn")
            send_btn.setFixedSize(36, 36)
            send_btn.clicked.connect(self._execute_command)
            input_layout.addWidget(send_btn)
            
            layout.addWidget(input_frame)
        
        def _apply_styles(self):
            """Apply dark theme styles."""
            self.setStyleSheet("""
                #central {
                    background-color: rgba(15, 15, 20, 0.95);
                    border-radius: 12px;
                    border: 1px solid rgba(80, 80, 100, 0.3);
                }
                #header {
                    background-color: rgba(20, 20, 30, 0.95);
                    border-top-left-radius: 12px;
                    border-top-right-radius: 12px;
                    border-bottom: 1px solid rgba(80, 80, 100, 0.2);
                }
                #title {
                    color: #a5b4fc;
                    font-size: 13px;
                    font-weight: bold;
                }
                #iconBtn {
                    background: rgba(50, 50, 70, 0.5);
                    border: none;
                    border-radius: 6px;
                    color: #9ca3af;
                    font-size: 16px;
                }
                #iconBtn:hover {
                    background: rgba(70, 70, 100, 0.7);
                    color: #e5e7eb;
                }
                #closeBtn {
                    background: rgba(50, 50, 70, 0.5);
                    border: none;
                    border-radius: 6px;
                    color: #9ca3af;
                    font-size: 18px;
                }
                #closeBtn:hover {
                    background: rgba(220, 38, 38, 0.8);
                    color: white;
                }
                #response {
                    background-color: rgba(25, 25, 35, 0.9);
                    border: none;
                    color: #d1d5db;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                    padding: 15px;
                }
                #inputFrame {
                    background-color: rgba(20, 20, 30, 0.95);
                    border-bottom-left-radius: 12px;
                    border-bottom-right-radius: 12px;
                    border-top: 1px solid rgba(80, 80, 100, 0.2);
                }
                #input {
                    background-color: rgba(40, 40, 60, 0.8);
                    border: 1px solid rgba(80, 80, 100, 0.3);
                    border-radius: 8px;
                    color: #e5e7eb;
                    font-size: 13px;
                    padding: 8px 12px;
                }
                #input:focus {
                    border-color: #6366f1;
                }
                #sendBtn {
                    background: linear-gradient(135deg, #6366f1, #8b5cf6);
                    border: none;
                    border-radius: 8px;
                    color: white;
                    font-size: 16px;
                    font-weight: bold;
                }
                #sendBtn:hover {
                    background: linear-gradient(135deg, #818cf8, #a78bfa);
                }
                #sendBtn:pressed {
                    background: linear-gradient(135deg, #4f46e5, #7c3aed);
                }
            """)
        
        def _analyze_screen(self):
            """Capture and analyze the current screen."""
            self.response_area.setText("📷 Capturing screen...")
            
            # Hide window temporarily
            self.hide()
            time.sleep(0.3)
            
            # Capture
            screenshot = ScreenCapture.capture_screen()
            
            # Show window again
            self.show()

            # Phase 8: DLP Redaction before AI processing
            if screenshot and DLP_FILTER_OK:
                blocks = ScreenCapture.extract_text_blocks(screenshot)
                dlp = get_dlp_filter()
                # Run text check first to log warnings
                screenshot, redacted_evts = dlp.redact_image(screenshot, blocks)
                if redacted_evts:
                    self.response_area.append(f"⚠️ DLP Filter redacted {len(redacted_evts)} sensitive regions.")
            
            if screenshot is None:
                self.response_area.setText("❌ Failed to capture screen")
                return
            
            self.response_area.setText("🔍 Analyzing screen...")
            
            # Run analysis in background
            prompt = (
                "Analyze this screenshot. Describe what you see on the screen, "
                "including any windows, applications, text, buttons, and UI elements. "
                "If there are actionable items, suggest what the user might want to do."
            )
            
            self.worker = WorkerThread(self.ai.analyze_screenshot, screenshot, prompt)
            self.worker.finished.connect(self._on_analysis_complete)
            self.worker.start()
        
        def _on_analysis_complete(self, result: str):
            """Handle analysis completion."""
            self.response_area.setText(result)
        
        def _execute_command(self):
            """Execute the user's command."""
            command = self.input_field.text().strip()
            if not command:
                return
            
            self.input_field.clear()
            self.response_area.setText(f"⚡ Executing: {command}")
            
            # Check if it's a screen-related command
            if any(word in command.lower() for word in ['screen', 'see', 'look', 'show', 'what']):
                # Capture screen for context
                self.hide()
                time.sleep(0.3)
                screenshot = ScreenCapture.capture_screen()
                self.show()
                
                # Phase 8: DLP Redaction before AI processing
                if screenshot and DLP_FILTER_OK:
                    blocks = ScreenCapture.extract_text_blocks(screenshot)
                    dlp = get_dlp_filter()
                    screenshot, redacted_evts = dlp.redact_image(screenshot, blocks)
                    if redacted_evts:
                        self.response_area.append(f"⚠️ DLP Filter redacted {len(redacted_evts)} sensitive regions.")
                
                if screenshot:
                    self.worker = WorkerThread(self.ai.analyze_screenshot, screenshot, command)
                    self.worker.finished.connect(self._on_command_complete)
                    self.worker.start()
                    return
            
            # Regular command
            self.worker = WorkerThread(self.ai.execute_command, command)
            self.worker.finished.connect(self._on_command_complete)
            self.worker.start()
        
        def _on_command_complete(self, result: str):
            """Handle command completion."""
            self.response_area.setText(result)
        
        def mousePressEvent(self, event):
            """Handle mouse press for dragging."""
            if event.button() == Qt.LeftButton:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
        
        def mouseMoveEvent(self, event):
            """Handle mouse move for dragging."""
            if event.buttons() == Qt.LeftButton and self.drag_position:
                self.move(event.globalPos() - self.drag_position)


class ScreenAgent:
    """Main screen agent controller."""
    
    def __init__(self, config: Optional[ScreenAgentConfig] = None):
        self.config = config or ScreenAgentConfig()
        self.ai = AIBackend(self.config)
        self.running = False
        self.overlay = None
        self.app = None
    
    def start(self, headless: bool = False):
        """Start the screen agent."""
        if headless:
            self._start_headless()
        else:
            self._start_gui()
    
    def _start_headless(self):
        """Run as background hotkey listener."""
        if not KEYBOARD_OK:
            logger.error("keyboard module required for headless mode")
            return
        
        logger.info(f"Screen Agent running in headless mode")
        logger.info(f"Press {self.config.hotkey} to capture and analyze screen")
        logger.info("Press Ctrl+C to exit")
        
        self.running = True
        keyboard.add_hotkey(self.config.hotkey, self._on_hotkey)
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
    
    def _start_gui(self):
        """Run with GUI overlay."""
        if not QT_OK:
            logger.error("PyQt5 required for GUI mode. Use --headless for CLI mode.")
            return
        
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Create overlay
        self.overlay = OverlayWindow(self.config, self.ai)
        
        # Setup system tray
        tray = QSystemTrayIcon(self.app)
        tray.setToolTip("LADA Screen Agent")
        
        # Tray menu
        menu = QMenu()
        show_action = menu.addAction("Show")
        show_action.triggered.connect(self.overlay.show)
        
        menu.addSeparator()
        
        capture_action = menu.addAction("Analyze Screen")
        capture_action.triggered.connect(self.overlay._analyze_screen)
        
        menu.addSeparator()
        
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.app.quit)
        
        tray.setContextMenu(menu)
        tray.show()
        
        # Setup hotkey if available
        if KEYBOARD_OK:
            keyboard.add_hotkey(self.config.hotkey, self._toggle_overlay)
            logger.info(f"Hotkey registered: {self.config.hotkey}")
        
        # Show overlay
        self.overlay.show()
        
        logger.info("Screen Agent started with GUI overlay")
        sys.exit(self.app.exec_())
    
    def _toggle_overlay(self):
        """Toggle overlay visibility."""
        if self.overlay:
            if self.overlay.isVisible():
                self.overlay.hide()
            else:
                self.overlay.show()
                self.overlay.activateWindow()
                self.overlay.input_field.setFocus()
    
    def _on_hotkey(self):
        """Handle hotkey in headless mode."""
        logger.info("Hotkey pressed - capturing screen...")
        
        screenshot = ScreenCapture.capture_screen()
        if screenshot is None:
            logger.error("Failed to capture screen")
            return
        
        logger.info("Analyzing screen...")
        result = self.ai.analyze_screenshot(
            screenshot,
            "Describe what you see on this screen in detail."
        )
        
        print("\n" + "=" * 60)
        print("Screen Analysis:")
        print("=" * 60)
        print(result)
        print("=" * 60 + "\n")


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="LADA Screen Agent - AI-powered screen control overlay"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run as background hotkey listener without GUI"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:5000",
        help="LADA API URL (default: http://localhost:5000)"
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama URL (default: http://localhost:11434)"
    )
    parser.add_argument(
        "--model",
        default="llava",
        help="Vision model to use (default: llava)"
    )
    parser.add_argument(
        "--hotkey",
        default="win+shift+l",
        help="Hotkey to toggle overlay (default: win+shift+l)"
    )
    
    args = parser.parse_args()
    
    config = ScreenAgentConfig(
        api_url=args.api_url,
        ollama_url=args.ollama_url,
        model=args.model,
        hotkey=args.hotkey
    )
    
    agent = ScreenAgent(config)
    agent.start(headless=args.headless)


if __name__ == "__main__":
    main()
