"""
LADA v7.0 - Clean ChatGPT-Style Desktop App
"""

import sys
import json
import os
import math
import random
import subprocess
import requests
import warnings
from datetime import datetime, timedelta
from pathlib import Path

# Best-effort UTF-8 console output so status lines and child-process messages
# cannot crash on Windows terminals using legacy code pages.
try:
    from modules.console_encoding import configure_console_utf8

    configure_console_utf8()
except Exception:
    pass

# Suppress non-critical warnings
warnings.filterwarnings('ignore', category=UserWarning, module='screen_brightness_control')
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
warnings.filterwarnings('ignore', message='file_cache is only supported')

# Windows taskbar icon fix - must be before QApplication
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('lada.ai.desktop.v9')
except Exception as e:
    pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QPushButton, QLabel, QFrame, QScrollArea,
    QDialog, QFileDialog, QComboBox, QListWidget, QListWidgetItem,
    QSlider, QCheckBox, QSpinBox, QGroupBox, QShortcut, QStatusBar,
    QSystemTrayIcon, QMenu, QMessageBox, QSizePolicy,
    QTextBrowser, QLineEdit, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF, QEvent, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QRadialGradient, QPalette, QKeySequence, QIcon

import threading
import logging
import base64

logger = logging.getLogger(__name__)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

# Global hotkey support
try:
    import keyboard as kb_global
    HOTKEY_OK = True
except ImportError:
    kb_global = None
    HOTKEY_OK = False
    print("[LADA] keyboard module not installed - global hotkeys disabled. Install with: pip install keyboard")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    pass

try:
    from lada_ai_router import HybridAIRouter
    LADA_OK = True
except Exception as e:
    LADA_OK = False
    HybridAIRouter = None

# Voice engine - try multiple backends
try:
    from voice_tamil_free import FreeNaturalVoice  # type: ignore
    VOICE_OK = True
except ImportError:
    FreeNaturalVoice = None  # type: ignore
    VOICE_OK = False

# Fallback voice using pyttsx3 + speech_recognition
if not VOICE_OK:
    try:
        import pyttsx3
        import speech_recognition as _sr

        class FreeNaturalVoice:
            """Simple voice wrapper using pyttsx3 for TTS and speech_recognition for STT"""
            def __init__(self, tamil_mode=False, auto_detect=False):
                self._engine = pyttsx3.init()
                self._engine.setProperty('rate', int(os.getenv("VOICE_RATE", "205")))
                self._engine.setProperty('volume', 0.9)
                try:
                    voices = self._engine.getProperty('voices') or []
                    for voice in voices:
                        voice_name = str(getattr(voice, "name", "")).lower()
                        if "zira" in voice_name or "female" in voice_name:
                            self._engine.setProperty('voice', voice.id)
                            break
                except Exception:
                    pass
                self._recognizer = _sr.Recognizer()
                self._recognizer.dynamic_energy_threshold = True
                self._recognizer.energy_threshold = 300
                self._speak_lock = threading.Lock()

            def speak(self, text: str):
                if not text:
                    return
                try:
                    with self._speak_lock:
                        self._engine.say(text)
                        self._engine.runAndWait()
                except Exception as e:
                    print(f"[Voice] TTS error: {e}")

            def listen_mixed(self, timeout=8):
                try:
                    with _sr.Microphone() as source:
                        self._recognizer.adjust_for_ambient_noise(source, duration=0.3)  # type: ignore
                        audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=12)
                    return self._recognizer.recognize_google(audio, language='en-US')
                except _sr.UnknownValueError:
                    return None
                except _sr.WaitTimeoutError:
                    return None
                except Exception as e:
                    print(f"[Voice] STT error: {e}")
                    return None

        VOICE_OK = True
        print("[LADA] Using pyttsx3 voice engine")
    except ImportError:
        FreeNaturalVoice = None  # type: ignore
        VOICE_OK = False

try:
    from modules.system_control import SystemController
    SYS_OK = True
except Exception as e:
    SystemController = None
    SYS_OK = False
    print(f"[LADA] SystemController not loaded: {e}")

try:
    from lada_jarvis_core import JarvisCommandProcessor, LadaPersonality
    JARVIS_OK = True
except Exception as e:
    JarvisCommandProcessor = None
    LadaPersonality = None
    JARVIS_OK = False
    print(f"[LADA] JARVIS not loaded: {e}")

# Voice NLU (new optimized voice command processor)
try:
    from modules.voice_nlu import VoiceCommandProcessor
    VOICE_NLU_OK = True
except Exception as e:
    VoiceCommandProcessor = None
    VOICE_NLU_OK = False
    print(f"[LADA] Voice NLU not loaded: {e}")

# Wake word detection -> Continuous Listener (always listening, no wake word)
try:
    from modules.continuous_listener import ContinuousListener
    WAKE_OK = True
except Exception as e:
    ContinuousListener = None
    WAKE_OK = False
    print(f"[LADA] ContinuousListener not loaded: {e}")

# Google Calendar integration
try:
    from modules.google_calendar import GoogleCalendar
    CALENDAR_OK = True
except Exception as e:
    GoogleCalendar = None
    CALENDAR_OK = False

# Face recognition
try:
    from modules.face_recognition import FaceRecognition
    FACE_OK = True
except Exception as e:
    FaceRecognition = None
    FACE_OK = False

# Weather briefing
try:
    from modules.weather_briefing import WeatherBriefing
    WEATHER_OK = True
except Exception as e:
    WeatherBriefing = None
    WEATHER_OK = False

# LADA v7.0 - Browser Automation Agents
try:
    from modules.agents.flight_agent import FlightAgent
    from modules.agents.product_agent import ProductAgent
    from modules.safety_gate import SafetyGate
    AGENTS_OK = True
except Exception as e:
    FlightAgent = None
    ProductAgent = None
    SafetyGate = None
    AGENTS_OK = False
    print(f"[LADA] Agents not loaded: {e}")

# LADA v7.0 - ChatManager for conversation persistence
try:
    from modules.chat_manager import ChatManager
    CHAT_MANAGER_OK = True
except Exception as e:
    ChatManager = None
    CHAT_MANAGER_OK = False
    print(f"[LADA] ChatManager not loaded: {e}")

# LADA v7.0 - Agent Orchestrator for smart routing
try:
    from modules.agent_orchestrator import AgentOrchestrator, AgentType
    ORCHESTRATOR_OK = True
except Exception as e:
    AgentOrchestrator = None
    AgentType = None
    ORCHESTRATOR_OK = False
    print(f"[LADA] AgentOrchestrator not loaded: {e}")

# LADA v7.0 - Export Manager
try:
    from modules.export_manager import ExportManager
    EXPORT_OK = True
except Exception as e:
    ExportManager = None
    EXPORT_OK = False
    print(f"[LADA] ExportManager not loaded: {e}")

# Cost tracker for token/cost monitoring
try:
    from modules.token_counter import CostTracker
    COST_TRACKER_OK = True
except Exception:
    CostTracker = None
    COST_TRACKER_OK = False

# Proactive agent for intelligent suggestions
try:
    from modules.proactive_agent import ProactiveAgent, Suggestion, SuggestionPriority, get_proactive_agent
    PROACTIVE_AGENT_OK = True
except Exception as e:
    ProactiveAgent = None
    Suggestion = None
    SuggestionPriority = None
    get_proactive_agent = None
    PROACTIVE_AGENT_OK = False
    print(f"[LADA] ProactiveAgent not loaded: {e}")

# Canvas widget
try:
    from modules.canvas_widget import AICanvas, ContentType, create_canvas
    CANVAS_OK = True
except Exception as e:
    AICanvas = None
    ContentType = None
    create_canvas = None
    CANVAS_OK = False
    print(f"[LADA] Canvas not loaded: {e}")

# Remote bridge client (Render -> local device)
try:
    from modules.remote_bridge_client import RemoteBridgeClient
    REMOTE_BRIDGE_OK = True
except Exception as e:
    RemoteBridgeClient = None
    REMOTE_BRIDGE_OK = False
    print(f"[LADA] Remote bridge not loaded: {e}")


# ============ Settings Dialog ============

from theme import (
    BG_MAIN, BG_SIDE, BG_INPUT, BG_HOVER, BG_CARD, BG_SURFACE,
    TEXT, TEXT_DIM, GREEN, ACCENT, ACCENT_GRADIENT_END, ACCENT_DARK, BLUE, RED, BORDER, FONT_FAMILY, FONT_HEADING, FONT_SIZE_SM, FONT_SIZE_MD, SUCCESS, WARNING, GLOBAL_QSS,
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL,
    CONTROL_ICON_SIZE, CONTROL_TOOLBAR_BUTTON_SIZE,
    APP_COLUMN_MAX_WIDTH, APP_INPUT_MAX_WIDTH, APP_WELCOME_GRID_MAX_WIDTH,
    APP_SUGGESTION_CARD_MIN_HEIGHT, APP_ASSISTANT_TEXT_MAX_WIDTH, APP_USER_TEXT_MAX_WIDTH,
    get_theme_mode, set_theme_mode, get_theme_colors,
)

from modules.desktop.settings import SettingsDialog
from modules.desktop.ui import VState, OrbWidget, RichTextLabel, Sidebar, Msg, ChatArea, QuickActionsPopup, InputBar
from modules.desktop.workers import AIWorker, StreamingAIWorker, VoiceWorker, RemoteBridgeWorker
from modules.desktop.overlays import FaceAuthOverlay, VoiceOverlay, ClickEffectOverlay, CometOverlay, AutonomousActionOverlay
from modules.desktop.app import LadaApp

def _log_uncaught_exception(exc_type, exc_value, exc_traceback):
    """Capture uncaught exceptions so runtime failures are logged instead of silent exits."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.exception(
        "[LADA] Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    try:
        print(f"[LADA] Uncaught exception: {exc_value}")
    except Exception:
        pass


def _log_thread_exception(args):
    """Capture uncaught background-thread exceptions for crash diagnostics."""
    logger.exception(
        "[LADA] Uncaught thread exception",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    try:
        print(f"[LADA] Background thread error ({args.thread.name}): {args.exc_value}")
    except Exception:
        pass


def main():
    # Install global exception handlers early so startup/runtime crashes are logged.
    sys.excepthook = _log_uncaught_exception
    if hasattr(threading, 'excepthook'):
        threading.excepthook = _log_thread_exception

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set application icon globally
    icon_path = Path("assets/lada_logo.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    elif Path("assets/lada_logo.png").exists():
        app.setWindowIcon(QIcon("assets/lada_logo.png"))
    
    p = app.palette()
    p.setColor(QPalette.Window, QColor(BG_SIDE))
    p.setColor(QPalette.WindowText, QColor(TEXT))
    app.setPalette(p)
    
    # Load saved theme preference
    try:
        settings_file = Path("config/app_settings.json")
        if settings_file.exists():
            saved = json.loads(settings_file.read_text())
            saved_mode = saved.get('theme_mode', 'dark')
            if saved_mode in ('dark', 'light'):
                qss = set_theme_mode(saved_mode)
                app.setStyleSheet(qss)
            else:
                app.setStyleSheet(GLOBAL_QSS)
        else:
            app.setStyleSheet(GLOBAL_QSS)
    except Exception:
        app.setStyleSheet(GLOBAL_QSS)
    
    # Don't quit when main window closes (for system tray)
    app.setQuitOnLastWindowClosed(False)

    try:
        w = LadaApp()
        w.show()
    except Exception as e:
        logger.exception("[LADA] Fatal startup error")
        QMessageBox.critical(
            None,
            "LADA Startup Error",
            f"LADA failed to start:\n{e}\n\nCheck logs/lada_gui.log for details.",
        )
        sys.exit(1)
    
    # Show face verification dialog inside app (non-blocking)
    if FACE_OK:
        QTimer.singleShot(500, lambda: w._check_face_auth())
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
