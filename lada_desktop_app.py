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
except:
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
except:
    pass

try:
    from lada_ai_router import HybridAIRouter
    LADA_OK = True
except:
    LADA_OK = False
    HybridAIRouter = None

# Voice engine - try multiple backends
try:
    from voice_tamil_free import FreeNaturalVoice
    VOICE_OK = True
except ImportError:
    FreeNaturalVoice = None
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
                self._engine.setProperty('rate', 180)
                self._engine.setProperty('volume', 0.9)
                self._recognizer = _sr.Recognizer()
                self._recognizer.dynamic_energy_threshold = True
                self._recognizer.energy_threshold = 300

            def speak(self, text: str):
                if not text:
                    return
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception as e:
                    print(f"[Voice] TTS error: {e}")

            def listen_mixed(self, timeout=8):
                try:
                    with _sr.Microphone() as source:
                        self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
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
        FreeNaturalVoice = None
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
except:
    GoogleCalendar = None
    CALENDAR_OK = False

# Face recognition
try:
    from modules.face_recognition import FaceRecognition
    FACE_OK = True
except:
    FaceRecognition = None
    FACE_OK = False

# Weather briefing
try:
    from modules.weather_briefing import WeatherBriefing
    WEATHER_OK = True
except:
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


# ============ Settings Dialog ============

class SettingsDialog(QDialog):
    """Settings configuration dialog"""
    
    def __init__(self, parent=None, router=None, voice=None):
        super().__init__(parent)
        self.router = router
        self.voice = voice
        self.sys = SystemController() if SYS_OK else None
        self.setWindowTitle("LADA Settings")
        # Keep settings responsive on smaller displays.
        self.setMinimumSize(500, 600)
        self.resize(520, 640)
        # Minimal override - GLOBAL_QSS handles most styling
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_SURFACE}; }}
            QGroupBox::title {{ background: {BG_SURFACE}; }}
        """)
        self._build()
    
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        
        title = QLabel("⚙️ Settings")
        title.setFont(QFont(FONT_HEADING, 18, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT}; margin-bottom: 8px;")
        lay.addWidget(title)
        
        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")
        scroll_widget = QWidget()
        scroll_lay = QVBoxLayout(scroll_widget)
        scroll_lay.setSpacing(12)
        scroll_lay.setContentsMargins(0, 0, 8, 0)
        
        # System Controls Group
        sys_group = QGroupBox("System Controls")
        slay = QVBoxLayout(sys_group)
        slay.setSpacing(12)
        
        # Volume slider
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel("🔊 Volume:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        if self.sys:
            try:
                vol = self.sys.get_volume()
                if vol.get('success'):
                    self.vol_slider.setValue(vol.get('volume', 50))
            except:
                pass
        self.vol_slider.valueChanged.connect(self._set_volume)
        vrow.addWidget(self.vol_slider, 1)
        self.vol_lbl = QLabel(f"{self.vol_slider.value()}%")
        self.vol_lbl.setFixedWidth(45)
        vrow.addWidget(self.vol_lbl)
        slay.addLayout(vrow)
        
        # Voice speed
        spd_row = QHBoxLayout()
        spd_row.addWidget(QLabel("🗣️ Voice Speed:"))
        self.spd_spin = QSpinBox()
        self.spd_spin.setRange(100, 300)
        self.spd_spin.setValue(175)
        self.spd_spin.setSuffix(" wpm")
        self.spd_spin.setStyleSheet(f"background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 4px; padding: 6px; color: {TEXT};")
        if self.voice:
            self.spd_spin.setValue(getattr(self.voice, 'voice_speed', 175))
        spd_row.addWidget(self.spd_spin)
        spd_row.addStretch()
        slay.addLayout(spd_row)
        
        scroll_lay.addWidget(sys_group)
        
        # Display Settings Group (NEW)
        display_group = QGroupBox("Display Settings")
        dlay = QVBoxLayout(display_group)
        dlay.setSpacing(12)
        
        # Font size slider
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("📝 Chat Font Size:"))
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(12, 28)
        self.font_slider.setValue(18)
        self.font_slider.valueChanged.connect(self._update_font_label)
        font_row.addWidget(self.font_slider, 1)
        self.font_lbl = QLabel(f"{self.font_slider.value()}px")
        self.font_lbl.setFixedWidth(45)
        font_row.addWidget(self.font_lbl)
        dlay.addLayout(font_row)
        
        # Web search behavior
        self.browser_search_check = QCheckBox("Open browser for searches (instead of answering in chat)")
        self.browser_search_check.setChecked(False)
        self.browser_search_check.setToolTip("When disabled, LADA will answer searches in chat using AI with web context")
        dlay.addWidget(self.browser_search_check)
        
        scroll_lay.addWidget(display_group)
        
        # Personality Mode Group (NEW - LADA v10.0)
        personality_group = QGroupBox("AI Personality")
        pers_lay = QVBoxLayout(personality_group)
        pers_lay.setSpacing(8)
        
        pers_desc = QLabel("Choose how LADA responds to you:")
        pers_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        pers_lay.addWidget(pers_desc)
        
        pers_row = QHBoxLayout()
        pers_row.addWidget(QLabel("🎭 Mode:"))
        self.personality_combo = QComboBox()
        self.personality_combo.addItems([
            "JARVIS - Sophisticated & Proactive",
            "Friday - Modern & Efficient", 
            "Karen - Warm & Supportive",
            "Casual - Friendly & Relaxed"
        ])
        self.personality_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 8px 12px; font-size: 12px;
            }}
            QComboBox:hover {{ border-color: {GREEN}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {BG_SIDE}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 4px;
                selection-background-color: {BG_HOVER};
            }}
        """)
        # Load saved personality mode
        default_mode = 2
        if JARVIS_OK and LadaPersonality:
            mode_to_index = {
                "jarvis": 0,
                "friday": 1,
                "karen": 2,
                "casual": 3,
            }
            try:
                default_mode = mode_to_index.get(str(LadaPersonality.get_mode()).lower(), default_mode)
            except Exception:
                pass

        try:
            settings_file = Path("config/app_settings.json")
            if settings_file.exists():
                saved = json.loads(settings_file.read_text())
                saved_mode = int(saved.get('personality_mode', default_mode))
                if saved_mode < 0 or saved_mode >= self.personality_combo.count():
                    saved_mode = default_mode
                self.personality_combo.setCurrentIndex(saved_mode)
            else:
                self.personality_combo.setCurrentIndex(default_mode)
        except:
            self.personality_combo.setCurrentIndex(default_mode)
        pers_row.addWidget(self.personality_combo, 1)
        pers_lay.addLayout(pers_row)
        
        scroll_lay.addWidget(personality_group)
        
        # Voice Group
        voice_group = QGroupBox("Voice Settings")
        vlay = QVBoxLayout(voice_group)
        vlay.setSpacing(8)
        
        self.voice_enabled = QCheckBox("Enable Voice Responses")
        self.voice_enabled.setChecked(True)
        self.voice_enabled.setToolTip("Speak responses out loud")
        vlay.addWidget(self.voice_enabled)
        
        self.continuous_listen = QCheckBox("Continuous Listening (background)")
        self.continuous_listen.setChecked(True)
        self.continuous_listen.setToolTip("Always listen for voice commands")
        vlay.addWidget(self.continuous_listen)
        
        scroll_lay.addWidget(voice_group)
        
        # Privacy & Security Group
        privacy_group = QGroupBox("Privacy && Security")
        play = QVBoxLayout(privacy_group)
        play.setSpacing(8)
        
        self.privacy_check = QCheckBox("Privacy Mode (hide sensitive data)")
        self.privacy_check.setChecked(False)
        self.privacy_check.setToolTip("When enabled, LADA will mask passwords, credit cards, and personal info in logs")
        play.addWidget(self.privacy_check)
        
        self.confirm_check = QCheckBox("Confirm dangerous actions")
        self.confirm_check.setChecked(True)
        self.confirm_check.setToolTip("Ask for confirmation before deleting files, shutting down, etc.")
        play.addWidget(self.confirm_check)
        
        self.audit_check = QCheckBox("Log all commands (for undo)")
        self.audit_check.setChecked(True)
        play.addWidget(self.audit_check)
        
        # Face Unlock Settings
        face_unlock_row = QHBoxLayout()
        self.face_unlock_check = QCheckBox("Enable Face Unlock")
        self.face_unlock_check.setChecked(False)
        self.face_unlock_check.setToolTip("Require face verification to open LADA")
        face_unlock_row.addWidget(self.face_unlock_check)
        
        # Load current face unlock setting
        try:
            settings_file = Path("config/app_settings.json")
            if settings_file.exists():
                import json
                saved = json.loads(settings_file.read_text())
                self.face_unlock_check.setChecked(saved.get('face_unlock_enabled', False))
        except:
            pass
        
        face_unlock_row.addStretch()
        play.addLayout(face_unlock_row)
        
        # Reset Face Data Button
        self.reset_face_btn = QPushButton("🔄 Reset Face Data")
        self.reset_face_btn.setCursor(Qt.PointingHandCursor)
        self.reset_face_btn.setToolTip("Delete enrolled face and re-capture (requires password)")
        self.reset_face_btn.setStyleSheet(f"""
            QPushButton {{
                background: #e74c3c; color: white;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #c0392b; }}
        """)
        self.reset_face_btn.clicked.connect(self._reset_face_data)
        play.addWidget(self.reset_face_btn)
        
        scroll_lay.addWidget(privacy_group)
        
        # AI Backend Status
        ai_group = QGroupBox("AI Backends")
        alay = QVBoxLayout(ai_group)
        alay.setSpacing(6)
        
        if self.router:
            status = self.router.get_status()
            for k, v in status.items():
                icon = "✅" if v.get('available') else "❌"
                name = v.get('name', k)
                time_str = v.get('response_time', 'N/A')
                lbl = QLabel(f"{icon}  {name}  ({time_str})")
                alay.addWidget(lbl)
        else:
            alay.addWidget(QLabel("❌  AI Router not initialized"))
        
        scroll_lay.addWidget(ai_group)

        # API Keys & Configuration Group
        api_group = QGroupBox("API Keys && Configuration")
        api_lay = QVBoxLayout(api_group)
        api_lay.setSpacing(8)

        api_desc = QLabel("Edit API keys to change AI backends. Changes saved to .env file.")
        api_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        api_desc.setWordWrap(True)
        api_lay.addWidget(api_desc)

        _api_input_style = f"""
            QLineEdit {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 8px 12px; font-size: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
            }}
            QLineEdit:focus {{ border-color: {GREEN}; }}
        """

        self.api_fields = {}
        api_configs = [
            ("GEMINI_API_KEY", "Gemini API Key", os.getenv("GEMINI_API_KEY", "")),
            ("GROQ_API_KEY", "Groq API Key", os.getenv("GROQ_API_KEY", "")),
            ("OLLAMA_URL", "Ollama URL", os.getenv("LOCAL_OLLAMA_URL", "http://localhost:11434")),
            ("OPENAI_API_KEY", "OpenAI API Key (optional)", os.getenv("OPENAI_API_KEY", "")),
            ("SPOTIFY_CLIENT_ID", "Spotify Client ID", os.getenv("SPOTIFY_CLIENT_ID", "")),
            ("HA_URL", "Home Assistant URL", os.getenv("HA_URL", "")),
            ("HA_TOKEN", "Home Assistant Token", os.getenv("HA_TOKEN", "")),
        ]

        from PyQt5.QtWidgets import QLineEdit
        for env_key, label_text, current_val in api_configs:
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}:")
            lbl.setFixedWidth(140)
            lbl.setStyleSheet(f"font-size: 12px; color: {TEXT};")
            row.addWidget(lbl)

            inp = QLineEdit()
            # Show masked value for keys, full value for URLs
            if 'KEY' in env_key and current_val:
                inp.setText(current_val[:4] + "..." + current_val[-4:] if len(current_val) > 8 else current_val)
                inp.setPlaceholderText("Enter API key...")
            else:
                inp.setText(current_val)
                inp.setPlaceholderText("Enter URL or key...")
            inp.setStyleSheet(_api_input_style)
            inp.setProperty("env_key", env_key)
            inp.setProperty("original_val", current_val)
            row.addWidget(inp, 1)
            api_lay.addLayout(row)
            self.api_fields[env_key] = inp

        scroll_lay.addWidget(api_group)
        scroll_lay.addStretch()
        
        scroll.setWidget(scroll_widget)
        lay.addWidget(scroll, 1)
        
        # Close button
        close_btn = QPushButton("Save & Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GREEN}, stop:1 {ACCENT_GRADIENT_END});
                color: white;
                border: none; border-radius: 10px;
                padding: 12px 28px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {ACCENT_GRADIENT_END}; }}
        """)
        close_btn.clicked.connect(self._on_close)
        lay.addWidget(close_btn)
    
    def _on_close(self):
        """Apply settings on close"""
        # Apply voice speed if voice available
        if self.voice:
            try:
                self.voice.voice_speed = self.spd_spin.value()
            except:
                pass
        
        # Emit settings so main window can apply them
        self.settings_data = {
            'privacy_mode': self.privacy_check.isChecked(),
            'confirm_dangerous': self.confirm_check.isChecked(),
            'audit_logging': self.audit_check.isChecked(),
            'voice_speed': self.spd_spin.value(),
            'voice_enabled': self.voice_enabled.isChecked(),
            'continuous_listen': self.continuous_listen.isChecked(),
            'font_size': self.font_slider.value(),
            'browser_search': self.browser_search_check.isChecked(),
            'face_unlock_enabled': self.face_unlock_check.isChecked(),
            'personality_mode': self.personality_combo.currentIndex(),
            'personality_name': self.personality_combo.currentText().split(' - ')[0],
        }
        
        # Save settings to persistent storage
        try:
            import json
            settings_file = Path("config/app_settings.json")
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if settings_file.exists():
                existing = json.loads(settings_file.read_text())
            existing['face_unlock_enabled'] = self.face_unlock_check.isChecked()
            existing['personality_mode'] = self.personality_combo.currentIndex()
            existing['personality_name'] = self.personality_combo.currentText().split(' - ')[0]
            settings_file.write_text(json.dumps(existing, indent=2))
        except Exception as e:
            print(f"Could not save settings: {e}")

        # Save API keys to .env file
        try:
            self._save_api_keys()
        except Exception as e:
            print(f"Could not save API keys: {e}")

        self.accept()

    def _save_api_keys(self):
        """Save changed API keys to .env file and update os.environ"""
        env_file = Path(".env")
        env_lines = []
        existing_keys = {}

        # Read existing .env file
        if env_file.exists():
            env_lines = env_file.read_text(encoding='utf-8').splitlines()
            for i, line in enumerate(env_lines):
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    existing_keys[key] = i

        # Map our field names to .env key names
        env_key_map = {
            "GEMINI_API_KEY": "GEMINI_API_KEY",
            "GROQ_API_KEY": "GROQ_API_KEY",
            "OLLAMA_URL": "LOCAL_OLLAMA_URL",
            "OPENAI_API_KEY": "OPENAI_API_KEY",
            "SPOTIFY_CLIENT_ID": "SPOTIFY_CLIENT_ID",
            "HA_URL": "HA_URL",
            "HA_TOKEN": "HA_TOKEN",
        }

        changed = False
        for field_key, inp_widget in self.api_fields.items():
            new_val = inp_widget.text().strip()
            original_val = inp_widget.property("original_val") or ""

            # Skip if value looks masked (contains "...") and hasn't been fully retyped
            if "..." in new_val and new_val != original_val:
                continue

            # Skip if value unchanged
            if new_val == original_val:
                continue

            # Skip empty values
            if not new_val:
                continue

            env_key = env_key_map.get(field_key, field_key)

            # Update os.environ immediately
            os.environ[env_key] = new_val

            # Update .env file line
            new_line = f"{env_key}={new_val}"
            if env_key in existing_keys:
                env_lines[existing_keys[env_key]] = new_line
            else:
                env_lines.append(new_line)

            changed = True
            print(f"[LADA] Updated {env_key}")

        if changed:
            env_file.write_text('\n'.join(env_lines) + '\n', encoding='utf-8')
            print("[LADA] API keys saved to .env")
    
    def _reset_face_data(self):
        """Reset face data with password confirmation"""
        from PyQt5.QtWidgets import QInputDialog
        
        # Ask for password/PIN as confirmation
        password, ok = QInputDialog.getText(
            self, "Reset Face Data", 
            "Enter your system password to reset face data:",
            QTextEdit.Password if hasattr(QTextEdit, 'Password') else 0
        )
        
        if not ok or not password:
            return
        
        # Simple password verification (you can enhance this)
        # For now, accept any non-empty password as confirmation
        if len(password) < 4:
            QMessageBox.warning(self, "Error", "Password must be at least 4 characters")
            return
        
        # Reset face data
        try:
            from modules.face_recognition import FaceRecognition
            face_rec = FaceRecognition()
            if face_rec.reset_enrollment():
                QMessageBox.information(
                    self, "Success", 
                    "Face data has been reset. Next time you enable Face Unlock, you'll need to re-enroll your face."
                )
                self.face_unlock_check.setChecked(False)
            else:
                QMessageBox.warning(self, "Error", "Could not reset face data")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error: {e}")
    
    def get_settings(self):
        """Return current settings"""
        return getattr(self, 'settings_data', {})
    
    def _set_volume(self, val):
        self.vol_lbl.setText(f"{val}%")
        if self.sys:
            try:
                self.sys.set_volume(val)
            except:
                pass
    
    def _update_font_label(self, val):
        """Update font size label when slider changes"""
        self.font_lbl.setText(f"{val}px")


Path("logs").mkdir(exist_ok=True)
Path("data/conversations").mkdir(parents=True, exist_ok=True)

logging.basicConfig(filename='logs/lada_gui.log', level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Theme (colors, typography, GLOBAL_QSS) ──
from theme import (
    BG_MAIN, BG_SIDE, BG_INPUT, BG_HOVER, BG_CARD, BG_SURFACE,
    TEXT, TEXT_DIM, GREEN, ACCENT, ACCENT_GRADIENT_END, ACCENT_DARK, BLUE, RED, BORDER, FONT_FAMILY, FONT_HEADING, FONT_SIZE_SM, FONT_SIZE_MD, SUCCESS, WARNING, GLOBAL_QSS,
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL,
    CONTROL_ICON_SIZE, CONTROL_TOOLBAR_BUTTON_SIZE,
    APP_COLUMN_MAX_WIDTH, APP_INPUT_MAX_WIDTH, APP_WELCOME_GRID_MAX_WIDTH,
    APP_SUGGESTION_CARD_MIN_HEIGHT, APP_ASSISTANT_TEXT_MAX_WIDTH, APP_USER_TEXT_MAX_WIDTH,
)


class VState:
    IDLE, LISTEN, PROCESS, SPEAK = 0, 1, 2, 3


# ============ Orb Widget ============

class OrbWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self._state = VState.IDLE
        self._t = 0
        self._particles = [(random.uniform(0, 6.28), random.uniform(0, 3.14), 
                           random.uniform(0.01, 0.03), random.uniform(2, 4)) 
                          for _ in range(80)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(20)

    def set_state(self, s):
        self._state = s

    def _tick(self):
        self._t += 0.05
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy, r = 100, 100, 60

        colors = {
            VState.IDLE: QColor(150, 140, 100),
            VState.LISTEN: QColor(BLUE),
            VState.PROCESS: QColor(ACCENT),
            VState.SPEAK: QColor(SUCCESS),
        }
        color = colors.get(self._state, colors[VState.IDLE])
        intensity = 1.0 if self._state != VState.IDLE else 0.6
        speed = {VState.IDLE: 1, VState.LISTEN: 3, VState.PROCESS: 4, VState.SPEAK: 2}.get(self._state, 1)

        # Glow
        g = QRadialGradient(cx, cy, r * 1.8)
        c = QColor(color)
        c.setAlpha(int(50 * intensity))
        g.setColorAt(0, c)
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), r * 1.8, r * 1.8)

        # Core
        g2 = QRadialGradient(cx, cy, r)
        c2 = QColor(color)
        c2.setAlpha(int(100 * intensity))
        g2.setColorAt(0, c2)
        g2.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g2)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Particles
        for theta, phi, spd, sz in self._particles:
            t = theta + self._t * spd * speed
            x = cx + r * 0.9 * math.sin(phi) * math.cos(t)
            y = cy + r * 0.9 * math.cos(phi)
            z = math.sin(phi) * math.sin(t)
            alpha = int(180 * (0.5 + z * 0.5) * intensity)
            c = QColor(color)
            c.setAlpha(alpha)
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), sz * (0.7 + z * 0.3), sz * (0.7 + z * 0.3))


# ============ Workers ============

class AIWorker(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt, router, files=None, preferred_backend=None):
        super().__init__()
        self.prompt = prompt
        self.router = router
        self.files = files or []
        self.preferred_backend = preferred_backend  # Backend name from model selector

    def run(self):
        ctx = self.prompt
        for f in self.files:
            if f.get('type') == 'text':
                ctx = f"[File: {f['name']}]\n{f['content']}\n\n{ctx}"
            elif f.get('type') == 'image':
                ctx = f"[Attached image: {f['name']}]\n\n{ctx}"

        if not self.router:
            self.error.emit("AI not initialized")
            return

        # Get backend from name if specified
        backend = None
        if self.preferred_backend:
            backend = self.router.get_backend_from_name(self.preferred_backend)
        
        # Try up to 2 times
        for attempt in range(2):
            try:
                r = self.router.query(ctx, prefer_backend=backend)
                if r:
                    self.done.emit(r)
                    return
            except Exception as e:
                print(f"[LADA] Query attempt {attempt+1} failed: {e}")
                if attempt == 0:
                    import time
                    time.sleep(0.5)
        
        self.error.emit("Could not get response. Please try again.")


class StreamingAIWorker(QThread):
    """AI Worker with streaming support for ChatGPT-style typing effect."""
    chunk_received = pyqtSignal(str)  # Individual chunk
    done = pyqtSignal(str)  # Full response when complete
    error = pyqtSignal(str)
    source_detected = pyqtSignal(str)  # Backend source name
    web_sources = pyqtSignal(list)  # Web search sources for badges

    def __init__(self, prompt, router, files=None, preferred_backend=None):
        super().__init__()
        self.prompt = prompt
        self.router = router
        self.files = files or []
        self.preferred_backend = preferred_backend
        self._cancelled = False
        self.full_response = ""

    def cancel(self):
        """Cancel the streaming operation."""
        self._cancelled = True

    def run(self):
        ctx = self.prompt
        for f in self.files:
            if f.get('type') == 'text':
                ctx = f"[File: {f['name']}]\n{f['content']}\n\n{ctx}"
            elif f.get('type') == 'image':
                ctx = f"[Attached image: {f['name']}]\n\n{ctx}"

        if not self.router:
            self.error.emit("AI not initialized")
            return

        # Get backend from name if specified
        backend = None
        if self.preferred_backend:
            backend = self.router.get_backend_from_name(self.preferred_backend)
        
        try:
            # Check if router supports streaming
            if hasattr(self.router, 'stream_query'):
                for data in self.router.stream_query(ctx, prefer_backend=backend):
                    if self._cancelled:
                        break
                    
                    # Check for sources data
                    if isinstance(data, dict) and 'sources' in data:
                        sources = data.get('sources', [])
                        if sources:
                            self.web_sources.emit(sources)
                        continue
                    
                    chunk = data.get('chunk', '') if isinstance(data, dict) else data
                    source = data.get('source', '') if isinstance(data, dict) else ''
                    is_done = data.get('done', False) if isinstance(data, dict) else False
                    
                    if chunk:
                        self.full_response += chunk
                        self.chunk_received.emit(chunk)
                    
                    if source and not hasattr(self, '_source_sent'):
                        self._source_sent = True
                        self.source_detected.emit(source)
                    
                    if is_done:
                        break
                
                if not self._cancelled:
                    self.done.emit(self.full_response)
            else:
                # Fallback to non-streaming
                r = self.router.query(ctx, prefer_backend=backend)
                if r and not self._cancelled:
                    self.full_response = r
                    self.chunk_received.emit(r)  # Emit all at once
                    self.done.emit(r)
                elif not self._cancelled:
                    self.error.emit("No response received")
                    
        except Exception as e:
            print(f"[LADA] Streaming error: {e}")
            self.error.emit(f"Streaming error: {str(e)}")


class VoiceWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, voice=None):
        super().__init__()
        self.voice = voice
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if self.voice:
                txt = self.voice.listen_mixed()
                if txt and not self._stop:
                    self.result.emit(txt)
                elif not self._stop:
                    self.error.emit("No speech")
            else:
                import speech_recognition as sr
                rec = sr.Recognizer()
                with sr.Microphone() as src:
                    rec.adjust_for_ambient_noise(src, 0.3)
                    audio = rec.listen(src, timeout=8, phrase_time_limit=12)
                txt = rec.recognize_google(audio)
                if txt:
                    self.result.emit(txt)
        except Exception as e:
            if not self._stop:
                self.error.emit(str(e))


# ============ In-App Face Authentication Widget ============

class FaceAuthOverlay(QFrame):
    """Full-screen face authentication overlay (in-app, no OpenCV popup)"""
    auth_complete = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, parent, face_auth):
        super().__init__(parent)
        self.face_auth = face_auth
        self.setStyleSheet("background: rgba(0, 0, 0, 240);")
        self._running = False
        self._samples = []  # For enrollment
        self._match_count = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_frame)
        self._build()
    
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        
        # Top bar with skip button
        top = QHBoxLayout()
        top.setContentsMargins(20, 20, 20, 0)
        top.addStretch()
        
        self.skip_btn = QPushButton("Skip for now")
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.1); color: {TEXT_DIM};
                border: 1px solid {BORDER}; border-radius: 16px;
                padding: 8px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.2); }}
        """)
        self.skip_btn.clicked.connect(self._skip)
        top.addWidget(self.skip_btn)
        lay.addLayout(top)
        
        lay.addStretch()
        
        # Camera preview (QLabel for displaying frames)
        cam_container = QHBoxLayout()
        cam_container.addStretch()
        
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(480, 360)
        self.camera_label.setStyleSheet(f"""
            background: {BG_INPUT}; border: 3px solid {BORDER};
            border-radius: 16px;
        """)
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setText("📷 Initializing camera...")
        cam_container.addWidget(self.camera_label)
        
        cam_container.addStretch()
        lay.addLayout(cam_container)
        
        # Status label
        self.status_label = QLabel("Looking for your face...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont(FONT_FAMILY, 14))
        self.status_label.setStyleSheet(f"color: {TEXT}; margin-top: 20px;")
        lay.addWidget(self.status_label)
        
        # Progress indicator
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setFont(QFont("Segoe UI", 12))
        self.progress_label.setStyleSheet(f"color: {TEXT_DIM}; margin-top: 8px;")
        lay.addWidget(self.progress_label)
        
        lay.addStretch()
        
        # Bottom hint
        hint = QLabel("Face recognition keeps LADA secure • Press ESC to skip")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; margin-bottom: 30px;")
        lay.addWidget(hint)
    
    def start(self):
        """Start face verification/enrollment"""
        if not self.face_auth:
            self.auth_complete.emit(True, "Face auth not available")
            return
        
        # Start camera
        if not self.face_auth.start_camera():
            self.status_label.setText("⚠️ Could not access camera")
            self.progress_label.setText("Click 'Skip' to continue without face auth")
            return
        
        self._running = True
        self._samples = []
        self._match_count = 0
        
        if self.face_auth.is_enrolled:
            self.status_label.setText("🔐 Verifying your face...")
            self.progress_label.setText("Look at the camera")
        else:
            self.status_label.setText("👤 Let's set up face recognition")
            self.progress_label.setText("Look at the camera to enroll your face")
        
        # Start frame updates at 30fps
        self._timer.start(33)
    
    def _update_frame(self):
        """Update camera frame and process face detection"""
        if not self._running:
            return
        
        frame_rgb, detection = self.face_auth.get_frame_with_detection()
        
        if frame_rgb is None:
            return
        
        # Convert numpy array to QImage for display
        from PyQt5.QtGui import QImage, QPixmap
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.camera_label.width(), self.camera_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.camera_label.setPixmap(pixmap)
        
        # Process detection
        if detection and detection['has_face']:
            if self.face_auth.is_enrolled:
                # Verification mode
                similarity = detection['similarity']
                if similarity > 0.7:
                    self._match_count += 1
                    self.progress_label.setText(f"Match: {similarity*100:.0f}% ({self._match_count}/3)")
                    self.camera_label.setStyleSheet(f"""
                        background: {BG_INPUT}; border: 3px solid {GREEN};
                        border-radius: 16px;
                    """)
                    
                    if self._match_count >= 3:
                        self._success("Welcome back! 🔓")
                else:
                    self.progress_label.setText(f"Similarity: {similarity*100:.0f}% (need 70%+)")
                    self.camera_label.setStyleSheet(f"""
                        background: {BG_INPUT}; border: 3px solid orange;
                        border-radius: 16px;
                    """)
            else:
                # Enrollment mode
                sample = self.face_auth.capture_face_sample()
                if sample is not None:
                    self._samples.append(sample)
                    self.progress_label.setText(f"Captured {len(self._samples)}/5 samples")
                    
                    if len(self._samples) >= 5:
                        success, msg = self.face_auth.enroll_from_samples(self._samples)
                        if success:
                            self._success("Face enrolled! LADA will now recognize you. 🔐")
                        else:
                            self.status_label.setText(f"⚠️ {msg}")
    
    def _success(self, message):
        """Handle successful auth"""
        self._running = False
        self._timer.stop()
        self.face_auth.stop_camera()
        self.status_label.setText(f"✅ {message}")
        self.progress_label.setText("")
        self.camera_label.setStyleSheet(f"""
            background: {BG_INPUT}; border: 3px solid {GREEN};
            border-radius: 16px;
        """)
        QTimer.singleShot(1000, lambda: self.auth_complete.emit(True, message))
    
    def _skip(self):
        """Skip face auth"""
        self._running = False
        self._timer.stop()
        if hasattr(self, 'face_auth') and self.face_auth:
            self.face_auth.stop_camera()
        self.auth_complete.emit(True, "Skipped face auth")
    
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._skip()


# ============ Sidebar ============

class Sidebar(QFrame):
    new_chat = pyqtSignal()
    load_chat = pyqtSignal(str)
    load_voice_chat = pyqtSignal(str)
    open_settings = pyqtSignal()  # Settings signal
    export_chat = pyqtSignal()    # Export signal
    open_session = pyqtSignal()   # Session picker signal
    open_cost = pyqtSignal()      # Cost dialog signal
    open_canvas = pyqtSignal()    # Canvas signal
    collapse_toggled = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._collapsed = False
        self._full_width = 272
        self._mini_width = 60
        self._anim_target_width = self._full_width
        self._width_anim_group = QParallelAnimationGroup(self)
        self._min_width_anim = QPropertyAnimation(self, b"minimumWidth")
        self._max_width_anim = QPropertyAnimation(self, b"maximumWidth")
        self._width_anim_group.addAnimation(self._min_width_anim)
        self._width_anim_group.addAnimation(self._max_width_anim)
        self._width_anim_group.finished.connect(self._finalize_width_animation)
        self.setMinimumWidth(self._full_width)
        self.setMaximumWidth(self._full_width)
        self.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 rgba(18,25,35,245), stop:1 rgba(15,21,30,245));"
            f" border-right: 1px solid {BORDER};"
        )
        self._build()
        self._load()

    def is_collapsed(self) -> bool:
        return bool(self._collapsed)

    def set_collapsed(self, collapsed: bool, emit_signal: bool = True):
        self._set_collapsed_state(bool(collapsed), emit_signal=emit_signal)

    def _set_collapsed_state(self, collapsed: bool, emit_signal: bool = True):
        if self._collapsed == collapsed:
            return

        self._collapsed = collapsed
        if self._collapsed:
            self._collapse_btn.setToolTip("Expand sidebar")
            for w in self._collapsible_widgets:
                w.hide()
            self._animate_width(self._mini_width)
        else:
            self._collapse_btn.setToolTip("Collapse sidebar")
            for w in self._collapsible_widgets:
                w.show()
            self._animate_width(self._full_width)

        if emit_signal:
            self.collapse_toggled.emit(self._collapsed)

    def _animate_width(self, target_width: int):
        target = int(target_width)
        start = int(self.width()) if self.width() > 0 else target
        start = max(self._mini_width, start)
        self._anim_target_width = target
        self._width_anim_group.stop()
        for anim in (self._min_width_anim, self._max_width_anim):
            anim.setDuration(180)
            anim.setStartValue(start)
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._width_anim_group.start()

    def _finalize_width_animation(self):
        self.setMinimumWidth(self._anim_target_width)
        self.setMaximumWidth(self._anim_target_width)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(4)

        # ── Top row: collapse button, logo, title ──
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self._collapse_btn = QPushButton("\u2261")
        self._collapse_btn.setFixedSize(32, 32)
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 18px; "
            f"color: {TEXT_DIM}; }}"
            f" QPushButton:hover {{ color: {TEXT}; }}"
        )
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header.addWidget(self._collapse_btn)

        self._logo_label = QLabel()
        logo_path = Path("assets/lada_logo.png")
        if logo_path.exists():
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap(str(logo_path)).scaled(
                28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._logo_label.setPixmap(pixmap)
        else:
            self._logo_label.setText("L")
            self._logo_label.setAlignment(Qt.AlignCenter)
            self._logo_label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: white;"
                f" background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f" stop:0 {ACCENT}, stop:1 {ACCENT_DARK}); border-radius: 6px;"
            )
        self._logo_label.setFixedSize(28, 28)
        header.addWidget(self._logo_label)

        self._title_label = QLabel("LADA")
        self._title_label.setFont(QFont(FONT_HEADING, 15))
        self._title_label.setStyleSheet(f"color: {TEXT}; margin-left: 2px;")
        header.addWidget(self._title_label)
        header.addStretch()
        lay.addLayout(header)

        lay.addSpacing(16)

        # ── New chat button ──
        self._new_chat_btn = QPushButton("\uff0b  New chat")
        self._new_chat_btn.setCursor(Qt.PointingHandCursor)
        self._new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_DARK});
                color: white;
                border: 1px solid rgba(255,255,255,0.05); border-radius: 10px;
                padding: 10px 14px; font-size: {FONT_SIZE_MD}px; font-weight: 600;
                text-align: left;
            }}
            QPushButton:hover {{ border-color: rgba(255,255,255,0.2); }}
        """)
        self._new_chat_btn.clicked.connect(lambda: self.new_chat.emit())
        lay.addWidget(self._new_chat_btn)

        lay.addSpacing(10)

        # ── Search input ──
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search chats...")
        self.search_input.setFixedHeight(34)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(18,25,35,0.88); color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px;
                padding: 7px 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """)
        self.search_input.textChanged.connect(self._filter_chats)
        lay.addWidget(self.search_input)

        lay.addSpacing(10)

        # ── Chat list ──
        self.lst = QListWidget()
        self.lst.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst.customContextMenuRequested.connect(self._show_context_menu)
        self.lst.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self.lst, 2)

        # ── Voice sessions ──
        self._voice_label = QLabel("Voice Sessions")
        self._voice_label.setFont(QFont(FONT_FAMILY, FONT_SIZE_SM))
        self._voice_label.setStyleSheet(
            f"color: {TEXT_DIM}; padding-left: 8px; margin-top: 6px; font-weight: 500;"
        )
        lay.addWidget(self._voice_label)

        self.voice_lst = QListWidget()
        self.voice_lst.setMaximumHeight(120)
        self.voice_lst.itemClicked.connect(
            lambda i: self.load_voice_chat.emit(i.data(Qt.UserRole))
        )
        lay.addWidget(self.voice_lst, 1)

        lay.addStretch()

        # ── Separator ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER};")
        lay.addWidget(sep)
        lay.addSpacing(6)

        # ── Bottom buttons ──
        self._export_btn = QPushButton("  Export Chat")
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 8px;
                padding: 9px 10px; font-size: 13px; text-align: left;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
        """)
        self._export_btn.clicked.connect(lambda: self.export_chat.emit())
        lay.addWidget(self._export_btn)

        self._canvas_btn = QPushButton("  Canvas")
        self._canvas_btn.setCursor(Qt.PointingHandCursor)
        self._canvas_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 8px;
                padding: 9px 10px; font-size: 13px; text-align: left;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
        """)
        self._canvas_btn.clicked.connect(lambda: self.open_canvas.emit())
        lay.addWidget(self._canvas_btn)

        self._settings_btn = QPushButton("  Settings")
        self._settings_btn.setCursor(Qt.PointingHandCursor)
        self._settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 8px;
                padding: 9px 10px; font-size: 13px; text-align: left;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
        """)
        self._settings_btn.clicked.connect(lambda: self.open_settings.emit())
        lay.addWidget(self._settings_btn)

        # Session picker button
        self._session_btn = QPushButton("  Session")
        self._session_btn.setCursor(Qt.PointingHandCursor)
        self._session_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 8px;
                padding: 9px 10px; font-size: 13px; text-align: left;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
        """)
        self._session_btn.clicked.connect(lambda: self.open_session.emit())
        lay.addWidget(self._session_btn)

        # Cost monitor button
        self._cost_btn = QPushButton("  $0.00")
        self._cost_btn.setCursor(Qt.PointingHandCursor)
        self._cost_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 8px;
                padding: 9px 10px; font-size: 13px; text-align: left;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
        """)
        self._cost_btn.clicked.connect(lambda: self.open_cost.emit())
        lay.addWidget(self._cost_btn)

        # ── Collapsible widgets (hidden when sidebar is collapsed) ──
        self._collapsible_widgets = [
            self._title_label, self._new_chat_btn, self.search_input,
            self.lst, self._voice_label, self.voice_lst,
            self._export_btn, self._canvas_btn, self._settings_btn, self._session_btn, self._cost_btn,
        ]
    
    def _filter_chats(self):
        """Filter chat list based on search"""
        search_text = self.search_input.text().lower().strip()
        for i in range(self.lst.count()):
            item = self.lst.item(i)
            if search_text:
                item.setHidden(search_text not in item.text().lower())
            else:
                item.setHidden(False)

    def _on_item_clicked(self, item):
        """Handle chat item click - skip section headers."""
        if not (item.flags() & Qt.ItemIsSelectable):
            return
        path = item.data(Qt.UserRole)
        if path:
            self.load_chat.emit(path)

    def _toggle_collapse(self):
        """Toggle sidebar between full and mini mode."""
        self._set_collapsed_state(not self._collapsed, emit_signal=True)

    def _show_context_menu(self, pos):
        """Show right-click context menu for edit/delete"""
        from PyQt5.QtWidgets import QMenu, QInputDialog, QMessageBox
        item = self.lst.itemAt(pos)
        if not item:
            return
        
        menu = QMenu(self)
        
        rename_action = menu.addAction("✏️ Rename")
        delete_action = menu.addAction("🗑️ Delete")
        
        action = menu.exec_(self.lst.mapToGlobal(pos))
        file_path = item.data(Qt.UserRole)
        
        if action == rename_action:
            current_name = item.text().rstrip("...")
            new_name, ok = QInputDialog.getText(self, "Rename Chat", "Enter new name:", text=current_name)
            if ok and new_name:
                try:
                    data = json.loads(Path(file_path).read_text(encoding='utf-8'))
                    if data:
                        data[0]['title'] = new_name
                    Path(file_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
                    item.setText(new_name[:30] + "..." if len(new_name) > 30 else new_name)
                except Exception as e:
                    print(f"Rename error: {e}")
        elif action == delete_action:
            # Create styled message box
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Delete Chat")
            msg_box.setText("Are you sure you want to delete this conversation?")
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)
            reply = msg_box.exec_()
            if reply == QMessageBox.Yes:
                try:
                    Path(file_path).unlink()
                    self.refresh()
                except Exception as e:
                    print(f"Delete error: {e}")

    def _load(self):
        self.lst.clear()
        self.voice_lst.clear()

        # Load text conversations with date grouping
        d = Path("data/conversations")
        if d.exists():
            now = datetime.now()
            today = now.date()
            yesterday = today - timedelta(days=1)
            week_ago = today - timedelta(days=7)

            groups = {"Today": [], "Yesterday": [], "Previous 7 Days": [], "Older": []}
            for f in sorted(d.glob("*.json"), reverse=True)[:20]:
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    if not data:
                        continue
                    raw_title = data[0].get('title', data[0].get('message', ''))
                    t = raw_title[:35] + "..." if len(raw_title) > 35 else raw_title
                    # Try to get date from filename (YYYY-MM-DD format)
                    try:
                        file_date = datetime.strptime(f.stem[:10], "%Y-%m-%d").date()
                    except Exception:
                        file_date = datetime.fromtimestamp(f.stat().st_mtime).date()

                    if file_date == today:
                        groups["Today"].append((t, str(f)))
                    elif file_date == yesterday:
                        groups["Yesterday"].append((t, str(f)))
                    elif file_date >= week_ago:
                        groups["Previous 7 Days"].append((t, str(f)))
                    else:
                        groups["Older"].append((t, str(f)))
                except Exception:
                    pass

            for group_name, items in groups.items():
                if not items:
                    continue
                # Section header (non-selectable)
                header = QListWidgetItem(group_name)
                header.setFlags(Qt.NoItemFlags)
                header.setForeground(QColor(TEXT_DIM))
                font = QFont(FONT_FAMILY, FONT_SIZE_SM - 1)
                font.setBold(True)
                header.setFont(font)
                self.lst.addItem(header)
                for title, path in items:
                    item = QListWidgetItem("  " + title)
                    item.setData(Qt.UserRole, path)
                    self.lst.addItem(item)
        
        # Load voice sessions
        v = Path("data/voice_sessions")
        if v.exists():
            for f in sorted(v.glob("*.json"), reverse=True)[:8]:
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    if data:
                        # Format: "Dec 31, 2:30 PM (5 exchanges)"
                        ts = data[0].get('timestamp', '')
                        count = len(data) // 2  # Approximate exchanges
                        try:
                            dt = datetime.fromisoformat(ts)
                            label = dt.strftime("%b %d, %I:%M %p") + f" ({count})"
                        except:
                            label = f"Voice session ({count})"
                        item = QListWidgetItem(f"🎤 {label}")
                        item.setData(Qt.UserRole, str(f))
                        self.voice_lst.addItem(item)
                except:
                    pass

    def refresh(self):
        self._load()


# ============ Message ============

# Font for messages
MSG_FONT = FONT_FAMILY

# Import markdown renderer
try:
    from modules.markdown_renderer import MarkdownRenderer
    MARKDOWN_OK = True
    _md_renderer = MarkdownRenderer()
except ImportError:
    MARKDOWN_OK = False
    _md_renderer = None
    print("[LadaApp] MarkdownRenderer not available - using plain text")


class RichTextLabel(QTextBrowser):
    """QTextBrowser that renders markdown as HTML with code highlighting."""
    
    # Class-level font size (can be changed via settings)
    font_size = 15  # Default font size in pixels
    
    def __init__(self, text: str, is_ai: bool = True):
        super().__init__()
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)
        self._text = text
        self._is_ai = is_ai
        
        # CRITICAL: Enable word wrapping
        from PyQt5.QtGui import QTextOption
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setLineWrapMode(QTextBrowser.WidgetWidth)
        
        # Styling with configurable font size
        self.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                border: none;
                color: {TEXT};
                font-family: {MSG_FONT};
                font-size: {RichTextLabel.font_size}px;
                line-height: 1.7;
                selection-background-color: {GREEN};
            }}
            QTextBrowser a {{
                color: {GREEN};
                text-decoration: none;
            }}
            QTextBrowser a:hover {{
                text-decoration: underline;
            }}
            QTextBrowser p {{
                margin: 8px 0;
            }}
        """)
        
        # Size policy - allow vertical expansion naturally
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Set content
        if is_ai and text.startswith("IMAGE:"):
            # Inline image rendering for generated images
            lines = text.split("\n", 1)
            image_path = lines[0].replace("IMAGE:", "").strip()
            caption = lines[1].strip() if len(lines) > 1 else ""
            # Normalize path for file:/// URL
            image_url = image_path.replace("\\", "/")
            if caption and MARKDOWN_OK and _md_renderer:
                caption_html = _md_renderer.render(caption)
            else:
                caption_html = f"<p>{caption}</p>" if caption else ""
            html = f'<img src="file:///{image_url}" width="512" style="border-radius: 8px; max-width: 100%;"><br>{caption_html}'
            self.setHtml(html)
        elif is_ai and text.startswith("VIDEO:"):
            # Video display - show clickable link since QTextBrowser can't play video
            lines = text.split("\n", 1)
            video_path = lines[0].replace("VIDEO:", "").strip()
            caption = lines[1].strip() if len(lines) > 1 else ""
            # Normalize path for file:/// URL
            video_url = video_path.replace("\\", "/")
            if caption and MARKDOWN_OK and _md_renderer:
                caption_html = _md_renderer.render(caption)
            else:
                caption_html = f"<p>{caption}</p>" if caption else ""
            # Show video icon + clickable link
            video_filename = video_path.replace('\\', '/').split('/')[-1]
            html = f'''
                <div style="padding: 16px; background: #1a1a2e; border-radius: 12px; border: 1px solid #333;">
                    <p style="margin: 0 0 8px 0; font-size: 14px;">🎬 <b>Video Generated</b></p>
                    <a href="file:///{video_url}" style="color: #7c3aed; text-decoration: none;">
                        📁 {video_filename}
                    </a>
                    {caption_html}
                </div>
            '''
            self.setHtml(html)
        elif is_ai and text.startswith("PLOT:"):
            # Inline matplotlib plot rendering (base64-encoded PNG)
            lines = text.split("\n", 1)
            plot_b64 = lines[0].replace("PLOT:", "").strip()
            caption = lines[1].strip() if len(lines) > 1 else ""
            if caption and MARKDOWN_OK and _md_renderer:
                caption_html = _md_renderer.render(caption)
            else:
                caption_html = f"<p style='color: #888; font-size: 12px;'>{caption}</p>" if caption else ""
            # Render base64 image directly
            html = f'''
                <div style="padding: 12px; background: #1a1a2e; border-radius: 12px; border: 1px solid #333;">
                    <p style="margin: 0 0 8px 0; font-size: 14px; color: #10b981;">📊 <b>Code Output</b></p>
                    <img src="data:image/png;base64,{plot_b64}" style="max-width: 100%; border-radius: 8px;">
                    {caption_html}
                </div>
            '''
            self.setHtml(html)
        elif is_ai and MARKDOWN_OK and _md_renderer:
            html = _md_renderer.render(text)
            self.setHtml(html)
        else:
            # Plain text for user messages
            self.setPlainText(text)
        
        # Connect to document layout changes for proper height calculation
        self.document().documentLayout().documentSizeChanged.connect(self._on_doc_size_changed)
        
        # Deferred height adjustments to ensure proper layout
        QTimer.singleShot(0, self._adjust_height)
        QTimer.singleShot(50, self._adjust_height)
        QTimer.singleShot(150, self._adjust_height)
    
    def _on_doc_size_changed(self, size):
        """Called when document size changes."""
        self._adjust_height()
    
    def resizeEvent(self, event):
        """Handle resize - recalculate height when width changes."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._adjust_height)
    
    def _adjust_height(self):
        """Adjust height to fit content properly."""
        # Set document width to match viewport for proper text wrapping calculation
        viewport_width = self.viewport().width()
        if viewport_width > 0:
            self.document().setTextWidth(viewport_width)
        
        # Get the actual document height after width is set
        doc_height = int(self.document().size().height())
        
        # Ensure minimum height, add padding for comfortable viewing
        target_height = max(doc_height + 20, 40)
        
        # Set height constraints
        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height + 50)
        
        # Force geometry update
        self.updateGeometry()


class Msg(QFrame):
    """Full-width message row (ChatGPT/Claude style) with hover toolbar."""
    copy_clicked = pyqtSignal(str)
    regenerate_clicked = pyqtSignal()
    feedback_clicked = pyqtSignal(str)  # 'up' or 'down'

    def __init__(self, role, text, show_toolbar=True):
        super().__init__()
        self.role = role
        self.text = text
        is_ai = role == "assistant"

        # Full-width row, no bubble background
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Message content area
        msg_frame = QFrame()
        if is_ai:
            msg_frame.setStyleSheet(
                "background: rgba(17,25,35,160);"
                "border-top: 1px solid rgba(255,255,255,0.04);"
                "border-bottom: 1px solid rgba(255,255,255,0.04);"
            )
        else:
            msg_frame.setStyleSheet("background: transparent;")
        msg_lay = QHBoxLayout(msg_frame)
        msg_lay.setContentsMargins(0, 0, 0, 0)
        msg_lay.setSpacing(0)

        # Keep message content in a centered readable column instead of full-bleed text.
        center_wrap = QFrame()
        center_wrap.setStyleSheet("background: transparent; border: none;")
        center_wrap.setMaximumWidth(APP_COLUMN_MAX_WIDTH)
        center_lay = QHBoxLayout(center_wrap)
        center_lay.setContentsMargins(SPACING_LG, SPACING_MD, SPACING_LG, SPACING_MD)
        center_lay.setSpacing(SPACING_MD)

        msg_lay.addStretch(1)
        msg_lay.addWidget(center_wrap, 0)
        msg_lay.addStretch(1)

        # Avatar
        av = QLabel()
        av.setFixedSize(26, 26)
        av.setAlignment(Qt.AlignCenter)
        if is_ai:
            logo_path = Path("assets/lada_logo.png")
            if logo_path.exists():
                from PyQt5.QtGui import QPixmap
                pixmap = QPixmap(str(logo_path)).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                av.setPixmap(pixmap)
                av.setStyleSheet(f"background: {BG_HOVER}; border-radius: 6px;")
            else:
                av.setText("L")
                av.setStyleSheet(f"""
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_DARK});
                    color: white; border-radius: 6px; font-size: 12px; font-weight: bold;
                """)
        else:
            av.setText("U")
            av.setStyleSheet(f"""
                background: #233447; color: #dce9ff;
                border-radius: 6px; font-size: 12px; font-weight: bold;
            """)
        center_lay.addWidget(av, 0, Qt.AlignTop)

        # Content column
        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(4)
        if not is_ai:
            content_col.setAlignment(Qt.AlignRight)

        # Role label
        name_label = QLabel("LADA" if is_ai else "You")
        name_label.setStyleSheet(
            f"color: {TEXT_DIM if is_ai else '#b8d6ff'};"
            " font-size: 12px; font-weight: 600;"
        )
        name_label.setAlignment(Qt.AlignLeft if is_ai else Qt.AlignRight)
        content_col.addWidget(name_label)

        if is_ai:
            self.content = RichTextLabel(text, is_ai=True)
            self.content.setMaximumWidth(APP_ASSISTANT_TEXT_MAX_WIDTH)
            content_col.addWidget(self.content)
        else:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setMaximumWidth(APP_USER_TEXT_MAX_WIDTH)
            lbl.setStyleSheet(
                f"color: #dce9ff;"
                f" background: #233447;"
                " border: 1px solid rgba(255,255,255,0.1);"
                " border-radius: 12px;"
                " padding: 10px 12px;"
                f" font-size: {RichTextLabel.font_size}px;"
                " line-height: 1.6;"
            )
            content_col.addWidget(lbl)

        # Toolbar (hidden by default, shown on hover)
        if show_toolbar and is_ai:
            self._toolbar = QWidget()
            self._toolbar.setStyleSheet("background: transparent;")
            self._toolbar.setFixedHeight(CONTROL_TOOLBAR_BUTTON_SIZE + SPACING_SM)
            tb_lay = QHBoxLayout(self._toolbar)
            tb_lay.setContentsMargins(0, SPACING_XS, 0, 0)
            tb_lay.setSpacing(SPACING_XS)
            self._toolbar_buttons = []

            _tb_style = f"""
                QPushButton {{
                    background: transparent; border: none; border-radius: 4px;
                    font-size: 14px; color: {TEXT_DIM}; padding: 3px 6px;
                }}
                QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
            """
            for icon, tip, handler in [
                ("\u29C9", "Copy", lambda: self._on_copy()),
                ("\u21BB", "Regenerate", lambda: self.regenerate_clicked.emit()),
                ("\u2191", "Good response", lambda: self._on_feedback('up')),
                ("\u2193", "Bad response", lambda: self._on_feedback('down')),
            ]:
                btn = QPushButton(icon)
                btn.setToolTip(tip)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setFixedSize(CONTROL_TOOLBAR_BUTTON_SIZE, CONTROL_TOOLBAR_BUTTON_SIZE)
                btn.setStyleSheet(_tb_style)
                btn.clicked.connect(handler)
                btn.setVisible(False)
                tb_lay.addWidget(btn)
                self._toolbar_buttons.append(btn)
                if tip == "Good response":
                    self.up_btn = btn
                elif tip == "Bad response":
                    self.down_btn = btn

            tb_lay.addStretch()
            content_col.addWidget(self._toolbar)

        center_lay.addLayout(content_col, 1)
        outer.addWidget(msg_frame)

        # Keep separators only for assistant rows to reduce visual noise.
        if is_ai:
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: rgba(255,255,255,0.03);")
            outer.addWidget(sep)

    def enterEvent(self, event):
        """Show toolbar on hover."""
        if hasattr(self, '_toolbar_buttons'):
            for btn in self._toolbar_buttons:
                btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Hide toolbar on leave."""
        if hasattr(self, '_toolbar_buttons'):
            for btn in self._toolbar_buttons:
                btn.setVisible(False)
        super().leaveEvent(event)

    def _on_copy(self):
        """Copy message text to clipboard."""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text)
        self.copy_clicked.emit(self.text)

    def _on_feedback(self, feedback_type):
        """Handle feedback button click."""
        if feedback_type == 'up':
            self.up_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT}; border: none; border-radius: 4px;
                    font-size: 14px; color: white; padding: 3px 6px;
                }}
            """)
        else:
            self.down_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {RED}; border: none; border-radius: 4px;
                    font-size: 14px; color: white; padding: 3px 6px;
                }}
            """)
        self.feedback_clicked.emit(feedback_type)

    def update_content(self, new_text):
        """Update the message content (for streaming)."""
        self.text = new_text
        if hasattr(self, 'content'):
            if MARKDOWN_OK and _md_renderer:
                html = _md_renderer.render(new_text)
                self.content.setHtml(html)
            else:
                self.content.setPlainText(new_text)


# ============ ChatArea ============

class ChatArea(QScrollArea):
    suggestion_clicked = pyqtSignal(str)  # When a suggestion chip is clicked
    copy_clicked = pyqtSignal(str)
    regenerate_clicked = pyqtSignal()
    feedback_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(
            f"QScrollArea {{"
            f" background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f" stop:0 #0e141c, stop:0.45 #0c1118, stop:1 #0a0f14);"
            f" border: none; }}"
        )
        self.box = QWidget()
        self.box.setStyleSheet(
            "background: qradialgradient(cx:0.5, cy:0.0, radius:1.1,"
            " fx:0.5, fy:0.0,"
            " stop:0 rgba(255,255,255,12), stop:1 rgba(0,0,0,0));"
        )
        self.lay = QVBoxLayout(self.box)
        self.lay.setContentsMargins(0, SPACING_SM, 0, SPACING_MD)
        self.lay.setSpacing(2)

        # Welcome widget (modern centered hero with 2x2 suggestion cards)
        self.welcome = QWidget()
        welcome_lay = QVBoxLayout(self.welcome)
        welcome_lay.setAlignment(Qt.AlignCenter)
        welcome_lay.setSpacing(16)

        welcome_lay.addSpacing(26)

        # Large logo in accent-colored rounded square
        self._welcome_logo = QLabel()
        logo_path = Path("assets/lada_logo.png")
        if logo_path.exists():
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap(str(logo_path)).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._welcome_logo.setPixmap(pixmap)
        else:
            self._welcome_logo.setText("L")
            self._welcome_logo.setFont(QFont(FONT_HEADING, 36, QFont.Bold))
            self._welcome_logo.setStyleSheet(f"""
                color: white; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_DARK});
                border-radius: 18px; padding: 10px;
            """)
        self._welcome_logo.setFixedSize(72, 72)
        self._welcome_logo.setAlignment(Qt.AlignCenter)
        logo_wrap = QHBoxLayout()
        logo_wrap.addStretch()
        logo_wrap.addWidget(self._welcome_logo)
        logo_wrap.addStretch()
        welcome_lay.addLayout(logo_wrap)

        welcome_lay.addSpacing(8)

        # Title
        self._welcome_title = QLabel("What can I help with?")
        self._welcome_title.setAlignment(Qt.AlignCenter)
        self._welcome_title.setFont(QFont(FONT_HEADING, 28, QFont.Bold))
        self._welcome_title.setStyleSheet(f"color: {TEXT};")
        welcome_lay.addWidget(self._welcome_title)

        # Subtitle
        self._welcome_subtitle = QLabel("LADA — Your AI Desktop Assistant")
        self._welcome_subtitle.setAlignment(Qt.AlignCenter)
        self._welcome_subtitle.setFont(QFont(FONT_FAMILY, 13))
        self._welcome_subtitle.setStyleSheet(f"color: {TEXT_DIM};")
        welcome_lay.addWidget(self._welcome_subtitle)

        # 2x2 suggestion cards
        welcome_lay.addSpacing(SPACING_XL)
        self._suggestion_chips = []
        self._suggestion_items = [
            ("Search the web", "Find latest news and information", "search the web for latest AI news"),
            ("System info", "Check your system status", "show me system information"),
            ("Take screenshot", "Capture your screen", "take a screenshot"),
            ("Battery status", "Check power and battery", "battery status"),
        ]
        self._card_grid = QGridLayout()
        self._card_grid.setSpacing(SPACING_SM)
        self._card_grid.setContentsMargins(SPACING_SM, 0, SPACING_SM, 0)

        grid_container = QHBoxLayout()
        grid_container.addStretch()
        self._grid_widget = QWidget()
        self._grid_widget.setMaximumWidth(APP_WELCOME_GRID_MAX_WIDTH)
        self._grid_widget.setLayout(self._card_grid)
        grid_container.addWidget(self._grid_widget)
        grid_container.addStretch()
        welcome_lay.addLayout(grid_container)

        self._suggestion_columns = 0
        self._rebuild_suggestion_cards(columns=2)

        self.lay.addWidget(self.welcome, 1)
        self.lay.addStretch()
        self.setWidget(self.box)
        
        self._has_messages = False
        self._streaming_msg = None  # Track current streaming message
        self._typing_step = 0
        self._typing_timer = QTimer()
        self._welcome_animations = []
        self._welcome_intro_played = False

        QTimer.singleShot(0, self._apply_responsive_suggestion_layout)
        QTimer.singleShot(120, self._animate_welcome_intro)

    def _welcome_animation_targets(self):
        return [self._welcome_logo, self._welcome_title, self._welcome_subtitle] + list(self._suggestion_chips)

    def _set_widget_opacity(self, widget, value: float):
        if widget is None:
            return
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(float(value))

    def _reset_welcome_opacity(self):
        for widget in self._welcome_animation_targets():
            self._set_widget_opacity(widget, 1.0)

    def _release_welcome_animation(self, animation):
        if animation in self._welcome_animations:
            self._welcome_animations.remove(animation)

    def _start_welcome_animation(self, animation):
        if animation is not None:
            animation.start()

    def _stop_welcome_intro(self):
        for animation in list(self._welcome_animations):
            animation.stop()
        self._welcome_animations.clear()

    def _animate_welcome_intro(self, force: bool = False):
        if self._has_messages or not self.welcome.isVisible():
            return
        if self._welcome_intro_played and not force:
            return

        self._stop_welcome_intro()
        targets = self._welcome_animation_targets()
        for idx, widget in enumerate(targets):
            if widget is None:
                continue
            self._set_widget_opacity(widget, 0.0)
            effect = widget.graphicsEffect()
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(220 if idx < 3 else 180)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda a=anim: self._release_welcome_animation(a))
            self._welcome_animations.append(anim)
            QTimer.singleShot(60 * idx, lambda a=anim: self._start_welcome_animation(a))

        self._welcome_intro_played = True

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _rebuild_suggestion_cards(self, columns: int):
        columns = max(1, int(columns))
        self._suggestion_columns = columns
        self._clear_layout(self._card_grid)
        self._suggestion_chips.clear()

        target_width = self._grid_widget.maximumWidth() if hasattr(self, '_grid_widget') else APP_WELCOME_GRID_MAX_WIDTH
        card_min_width = 220 if columns > 1 else max(220, target_width - 40)

        for idx, (label, desc, cmd) in enumerate(self._suggestion_items):
            card = QPushButton()
            card.setCursor(Qt.PointingHandCursor)
            card.setProperty("chip_cmd", cmd)
            card.setMinimumWidth(card_min_width)
            card.setMinimumHeight(APP_SUGGESTION_CARD_MIN_HEIGHT)
            card.setStyleSheet(f"""
                QPushButton {{
                    background: {BG_CARD}; color: {TEXT};
                    border: 1px solid {BORDER}; border-radius: 12px;
                    padding: 14px 18px; font-size: 13px; text-align: left;
                }}
                QPushButton:hover {{
                    background: {BG_HOVER}; border-color: {ACCENT};
                }}
            """)

            card_content = QVBoxLayout(card)
            card_content.setContentsMargins(0, 0, 0, 0)
            card_content.setSpacing(SPACING_XS)
            title_lbl = QLabel(label)
            title_lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 600; background: transparent;")
            title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
            desc_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            card_content.addWidget(title_lbl)
            card_content.addWidget(desc_lbl)

            card.clicked.connect(lambda _, c=cmd: self._on_suggestion_click(c))

            row = idx // columns
            col = idx % columns
            self._card_grid.addWidget(card, row, col)
            self._suggestion_chips.append(card)

    def _apply_responsive_suggestion_layout(self):
        viewport_width = self.viewport().width() if self.viewport() else 0
        if viewport_width <= 0 or not hasattr(self, '_grid_widget'):
            return

        target_width = min(APP_WELCOME_GRID_MAX_WIDTH, max(340, viewport_width - 120))
        self._grid_widget.setMaximumWidth(target_width)
        columns = 2 if target_width >= 560 else 1
        if columns != self._suggestion_columns:
            self._rebuild_suggestion_cards(columns=columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_suggestion_layout()

    def add(self, role, text, show_toolbar=True):
        """Add a message to the chat area."""
        # Hide welcome on first message
        if not self._has_messages:
            self._stop_welcome_intro()
            self._reset_welcome_opacity()
            self.welcome.hide()
            self._has_messages = True
        
        msg = Msg(role, text, show_toolbar=show_toolbar)
        msg.copy_clicked.connect(self.copy_clicked.emit)
        msg.regenerate_clicked.connect(self.regenerate_clicked.emit)
        msg.feedback_clicked.connect(self.feedback_clicked.emit)
        self.lay.insertWidget(self.lay.count() - 1, msg)
        QTimer.singleShot(30, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))
        return msg
    
    def add_streaming_placeholder(self):
        """Add a placeholder for streaming response with animated typing indicator."""
        if not self._has_messages:
            self._stop_welcome_intro()
            self._reset_welcome_opacity()
            self.welcome.hide()
            self._has_messages = True

        # Create message with animated dots as typing indicator
        self._streaming_msg = Msg("assistant", "●", show_toolbar=False)
        self._streaming_msg.setProperty("typing", True)
        self.lay.insertWidget(self.lay.count() - 1, self._streaming_msg)
        QTimer.singleShot(30, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

        # Start dot animation
        self._typing_step = 0
        self._typing_timer = QTimer()
        self._typing_timer.timeout.connect(self._animate_typing)
        self._typing_timer.start(400)

        return self._streaming_msg

    def _animate_typing(self):
        """Animate typing indicator dots."""
        if self._streaming_msg and self._streaming_msg.property("typing"):
            dots = ["●", "● ●", "● ● ●"]
            self._typing_step = (self._typing_step + 1) % len(dots)
            self._streaming_msg.update_content(dots[self._typing_step])

    def _stop_typing_animation(self):
        """Stop the typing animation timer."""
        if hasattr(self, '_typing_timer') and self._typing_timer.isActive():
            self._typing_timer.stop()
        if self._streaming_msg:
            self._streaming_msg.setProperty("typing", False)
    
    def update_streaming(self, text):
        """Update the streaming message content."""
        if self._streaming_msg:
            # Stop typing animation on first real content
            if self._streaming_msg.property("typing"):
                self._stop_typing_animation()
            self._streaming_msg.update_content(text + "▌")
            QTimer.singleShot(10, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))
    
    def finalize_streaming(self, text):
        """Finalize the streaming message (remove cursor, add toolbar)."""
        self._stop_typing_animation()
        if self._streaming_msg:
            # Remove from layout immediately to avoid duplicate visible messages
            idx = self.lay.indexOf(self._streaming_msg)
            if idx >= 0:
                self.lay.takeAt(idx)
            self._streaming_msg.setParent(None)
            self._streaming_msg.deleteLater()
            self._streaming_msg = None

        # Add final message with toolbar
        return self.add("assistant", text, show_toolbar=True)

    def clear_all(self):
        while self.lay.count() > 1:
            w = self.lay.takeAt(0).widget()
            if w and w != self.welcome:
                w.deleteLater()
        # Show welcome again
        self.welcome.show()
        self._has_messages = False
        self._welcome_intro_played = False
        self._reset_welcome_opacity()
        QTimer.singleShot(80, self._animate_welcome_intro)

    def _on_suggestion_click(self, cmd):
        """Handle click on a suggestion chip."""
        self.suggestion_clicked.emit(cmd)


# ============ Quick Actions Popup ============

class QuickActionsPopup(QFrame):
    """Slash-command style popup for quick system actions."""
    action_selected = pyqtSignal(str)

    ACTIONS = [
        ("Stack health", "stack health"),
        ("Volume up", "increase volume by 20"),
        ("Volume down", "decrease volume by 20"),
        ("Mute", "mute"),
        ("Screenshot", "take a screenshot"),
        ("Dark mode", "set dark mode"),
        ("Light mode", "set light mode"),
        ("Battery", "battery status"),
        ("Wi-Fi status", "wifi status"),
        ("Bluetooth", "bluetooth status"),
        ("System info", "system information"),
        ("Open Notepad", "open notepad"),
        ("Open Chrome", "open chrome"),
        ("Show desktop", "show desktop"),
        ("Lock screen", "lock screen"),
        ("Now playing", "what is playing"),
        ("Next song", "next song"),
        ("Pause music", "pause music"),
        ("Smart home", "smart home status"),
        ("Heartbeat", "heartbeat status"),
        ("Hooks status", "list hooks"),
        ("Memory search", "search memory for"),
        ("List processes", "list processes"),
        ("Clear temp", "clear temp files"),
        ("Clipboard", "read clipboard"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(320)
        self.setMaximumHeight(360)
        self._build()

    def _build(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_SURFACE}; border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(2)

        title = QLabel("Quick Actions")
        title.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; padding: 4px 8px; font-family: '{FONT_FAMILY}';")
        lay.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        self.content_lay = QVBoxLayout(content)
        self.content_lay.setContentsMargins(0, 0, 0, 0)
        self.content_lay.setSpacing(1)

        for label, cmd in self.ACTIONS:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {TEXT};
                    border: none; border-radius: 8px;
                    padding: 8px 12px; font-size: 13px; text-align: left;
                    font-family: '{FONT_FAMILY}';
                }}
                QPushButton:hover {{
                    background: {BG_HOVER};
                }}
            """)
            btn.clicked.connect(lambda _, c=cmd: self._select(c))
            self.content_lay.addWidget(btn)

        scroll.setWidget(content)
        lay.addWidget(scroll)

    def _select(self, cmd):
        self.action_selected.emit(cmd)
        self.hide()


# ============ InputBar ============

class InputBar(QFrame):
    send = pyqtSignal(str, list)

    def __init__(self):
        super().__init__()
        self.files = []
        self._input_enabled = True
        self._input_min_height = 38
        self._input_max_height = 108
        self.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 rgba(18,25,35,194), stop:1 rgba(18,25,35,232));"
            f" border-top: 1px solid {BORDER};"
        )
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(6)

        # Files row
        self.file_row = QHBoxLayout()
        fc = QWidget()
        fc.setMaximumWidth(APP_INPUT_MAX_WIDTH)
        fc.setLayout(self.file_row)
        fr = QHBoxLayout()
        fr.addStretch()
        fr.addWidget(fc)
        fr.addStretch()
        lay.addLayout(fr)

        # Model selector (defined here, added to input row below)
        self.model_selector = QComboBox()
        self.model_selector.setMinimumWidth(140)
        self.model_selector.setMaximumWidth(280)
        self.model_selector.setFixedHeight(CONTROL_ICON_SIZE)
        self.model_selector.setMaxVisibleItems(15)
        self.model_selector.setStyleSheet(f"""
            QComboBox {{
                background: transparent; color: {TEXT_DIM};
                border: 1px solid transparent; border-radius: 15px;
                padding: 2px 20px 2px 10px; font-size: 11px; font-weight: 500;
            }}
            QComboBox:hover {{ background: {BG_HOVER}; border-color: {BORDER}; color: {TEXT}; }}
            QComboBox::drop-down {{
                border: none; width: 20px; subcontrol-position: right center;
            }}
            QComboBox::down-arrow {{
                image: none; width: 0; height: 0;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid {TEXT_DIM};
            }}
            QComboBox QAbstractItemView {{
                background: {BG_SURFACE}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px;
                selection-background-color: {BG_HOVER};
                padding: 4px; font-size: 11px;
            }}
        """)

        # Input row
        box = QFrame()
        box.setMaximumWidth(APP_INPUT_MAX_WIDTH)
        box.setStyleSheet(f"""
            QFrame {{
                background: rgba(26,36,49,220); border: 1px solid {BORDER};
                border-radius: 16px;
            }}
        """)
        row = QHBoxLayout(box)
        row.setContentsMargins(10, 7, 7, 7)
        row.setSpacing(6)

        self.attach_btn = QPushButton("+")
        self.attach_btn.setFixedSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 17px; font-size: 20px;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
        """)
        self.attach_btn.clicked.connect(self._attach)
        row.addWidget(self.attach_btn)

        # Model selector (inside input row, after attach button)
        row.addWidget(self.model_selector)

        # Quick actions button (slash commands)
        self.qa_btn = QPushButton("/")
        self.qa_btn.setFixedSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        self.qa_btn.setCursor(Qt.PointingHandCursor)
        self.qa_btn.setToolTip("Quick Actions")
        self.qa_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: none; border-radius: 17px; font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {ACCENT}; }}
        """)
        self.qa_popup = QuickActionsPopup()
        self.qa_popup.action_selected.connect(self._on_quick_action)
        self.qa_btn.clicked.connect(self._show_quick_actions)
        row.addWidget(self.qa_btn)

        self.inp = QTextEdit()
        self.inp.setPlaceholderText("Ask LADA anything...")
        self.inp.setMinimumHeight(self._input_min_height)
        self.inp.setMaximumHeight(self._input_max_height)
        self.inp.setFont(QFont(FONT_FAMILY, 13))
        self.inp.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {TEXT};
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 4px;
            }}
            QTextEdit:focus {{
                border: 1px solid rgba(16,163,127,0.55);
                background: rgba(16,163,127,0.06);
            }}
        """)
        self.inp.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inp.textChanged.connect(self._update_input_height)
        self.inp.textChanged.connect(self._refresh_send_state)
        self.inp.installEventFilter(self)
        row.addWidget(self.inp, 1)

        # Send button
        self.sbtn = QPushButton("↑")
        self.sbtn.setFixedSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        self.sbtn.setCursor(Qt.PointingHandCursor)
        self.sbtn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_DARK});
                color: white;
                border: none; border-radius: 10px; font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {ACCENT_DARK}; }}
            QPushButton:disabled {{
                background: rgba(95, 108, 122, 0.38);
                color: rgba(255, 255, 255, 0.45);
            }}
        """)
        self.sbtn.clicked.connect(self._send)
        row.addWidget(self.sbtn)
        
        # Stop button (hidden by default)
        self.stop_btn = QPushButton("■")
        self.stop_btn.setFixedSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RED}; color: white;
                border: none; border-radius: 10px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #dc2626; }}
        """)
        self.stop_btn.setToolTip("Stop generation")
        self.stop_btn.hide()
        row.addWidget(self.stop_btn)

        ir = QHBoxLayout()
        ir.addStretch()
        ir.addWidget(box, 1)
        ir.addStretch()
        lay.addLayout(ir)

        # Options row with web search toggle
        opts_row = QHBoxLayout()
        opts_row.addStretch()

        # Web search toggle (pill button, matching web app style)
        self.web_search_btn = QPushButton("Search web")
        self.web_search_btn.setCheckable(True)
        self.web_search_btn.setFixedHeight(26)
        self.web_search_btn.setCursor(Qt.PointingHandCursor)
        self.web_search_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: 1px solid {BORDER}; border-radius: 13px;
                font-size: 11px; padding: 2px 14px;
            }}
            QPushButton:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
            QPushButton:checked {{
                background: rgba(16,163,127,0.16); color: #c8f9eb;
                border-color: {ACCENT};
            }}
        """)
        self.web_search_btn.setToolTip("Enable web search for real-time answers")
        opts_row.addWidget(self.web_search_btn)
        
        opts_row.addSpacing(20)
        opts_row.addStretch()
        lay.addLayout(opts_row)

        note = QLabel("LADA can make mistakes. Check important info.")
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9px;")
        lay.addWidget(note)

        self._update_input_height()
        self._refresh_send_state()

    def _update_input_height(self):
        doc_height = int(self.inp.document().size().height()) + 10
        target_height = max(self._input_min_height, min(self._input_max_height, doc_height))
        self.inp.setFixedHeight(target_height)
        if target_height >= self._input_max_height:
            self.inp.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.inp.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def _refresh_send_state(self):
        has_text = bool(self.inp.toPlainText().strip())
        has_files = bool(self.files)
        can_send = self._input_enabled and (has_text or has_files)
        self.sbtn.setEnabled(can_send)

    def is_web_search_enabled(self):
        """Check if web search toggle is enabled."""
        return self.web_search_btn.isChecked() if hasattr(self, 'web_search_btn') else False

    def show_stop(self):
        """Show stop button, hide send button."""
        self.sbtn.hide()
        self.stop_btn.show()

    def hide_stop(self):
        """Hide stop button, show send button."""
        self.stop_btn.hide()
        self.sbtn.show()
        self._refresh_send_state()

    def enable(self, enabled=True):
        """Enable or disable the composer controls."""
        self._input_enabled = bool(enabled)
        self.inp.setEnabled(self._input_enabled)
        self.attach_btn.setEnabled(self._input_enabled)
        self.qa_btn.setEnabled(self._input_enabled)
        self.model_selector.setEnabled(self._input_enabled)
        self.stop_btn.setEnabled(self._input_enabled)
        self._refresh_send_state()

    def _attach(self):
        fs, _ = QFileDialog.getOpenFileNames(
            self, "Attach Files", "",
            "All Files (*);;Documents (*.pdf *.docx *.doc *.txt *.md *.csv *.json *.html);;Code (*.py *.js *.ts *.java *.cpp *.c *.h *.cs *.go *.rs *.rb);;Images (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        for f in fs:
            p = Path(f)
            d = {'name': p.name, 'path': str(p)}
            ext = p.suffix.lower()

            # Skip files larger than 50MB
            try:
                file_size = p.stat().st_size
                if file_size > 50 * 1024 * 1024:
                    d['type'] = 'text'
                    d['content'] = f"[File too large: {p.name} ({file_size // (1024*1024)}MB)]"
                    self.files.append(d)
                    chip = QPushButton(f"{p.name[:20]}")
                    chip.setStyleSheet(f"background: {BG_INPUT}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 15px; padding: 4px 10px; font-size: 11px;")
                    chip.clicked.connect(lambda _, c=chip, dd=d: self._rm(c, dd))
                    self.file_row.addWidget(chip)
                    continue
            except Exception:
                pass

            # Text-based files (read only first 12KB, not the whole file)
            if ext in ['.txt', '.py', '.json', '.md', '.csv', '.html', '.htm',
                       '.js', '.ts', '.java', '.cpp', '.c', '.h', '.cs', '.go',
                       '.rs', '.rb', '.xml', '.yaml', '.yml', '.toml', '.ini',
                       '.cfg', '.log', '.sql', '.sh', '.bat', '.ps1']:
                try:
                    d['type'] = 'text'
                    with open(str(p), 'r', encoding='utf-8', errors='ignore') as fh:
                        d['content'] = fh.read(12000)
                except Exception:
                    continue

            # PDF files - use document_reader if available
            elif ext == '.pdf':
                try:
                    from modules.document_reader import DocumentReader
                    reader = DocumentReader()
                    result = reader.read_file(str(p))
                    d['type'] = 'text'
                    d['content'] = result.get('content', '')[:12000] if isinstance(result, dict) else str(result)[:12000]
                except Exception:
                    try:
                        import subprocess
                        # Fallback: try pdfplumber
                        import pdfplumber
                        text_parts = []
                        with pdfplumber.open(str(p)) as pdf:
                            for page in pdf.pages[:20]:
                                t = page.extract_text()
                                if t:
                                    text_parts.append(t)
                        d['type'] = 'text'
                        d['content'] = '\n'.join(text_parts)[:12000]
                    except Exception:
                        d['type'] = 'text'
                        d['content'] = f"[PDF file: {p.name} - install pdfplumber to read content]"

            # DOCX files
            elif ext in ['.docx', '.doc']:
                try:
                    from modules.document_reader import DocumentReader
                    reader = DocumentReader()
                    result = reader.read_file(str(p))
                    d['type'] = 'text'
                    d['content'] = result.get('content', '')[:12000] if isinstance(result, dict) else str(result)[:12000]
                except Exception:
                    try:
                        import docx
                        doc = docx.Document(str(p))
                        text = '\n'.join(para.text for para in doc.paragraphs)
                        d['type'] = 'text'
                        d['content'] = text[:12000]
                    except Exception:
                        d['type'] = 'text'
                        d['content'] = f"[DOCX file: {p.name} - install python-docx to read content]"

            # Images
            elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                try:
                    d['type'] = 'image'
                    d['content'] = base64.b64encode(p.read_bytes()).decode()
                except Exception:
                    continue
            else:
                # Try to read as text (only first 8KB)
                try:
                    d['type'] = 'text'
                    with open(str(p), 'r', encoding='utf-8', errors='ignore') as fh:
                        d['content'] = fh.read(8000)
                except Exception:
                    continue

            self.files.append(d)
            chip = QPushButton(f"{p.name[:20]}")
            chip.setStyleSheet(f"background: {BG_INPUT}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 15px; padding: 4px 10px; font-size: 11px;")
            chip.clicked.connect(lambda _, c=chip, dd=d: self._rm(c, dd))
            self.file_row.addWidget(chip)

        self._refresh_send_state()

    def _show_quick_actions(self):
        """Show quick actions popup above the / button."""
        pos = self.qa_btn.mapToGlobal(self.qa_btn.rect().topLeft())
        self.qa_popup.move(pos.x(), pos.y() - self.qa_popup.maximumHeight())
        self.qa_popup.show()

    def _on_quick_action(self, cmd):
        """Handle quick action selection - send as message."""
        self.send.emit(cmd, [])

    def _rm(self, chip, d):
        if d in self.files:
            self.files.remove(d)
        chip.deleteLater()
        self._refresh_send_state()

    def _send(self):
        t = self.inp.toPlainText().strip()
        if t or self.files:
            self.send.emit(t, self.files.copy())
            self.inp.clear()
            while self.file_row.count():
                w = self.file_row.takeAt(0).widget()
                if w:
                    w.deleteLater()
            self.files.clear()
            self._update_input_height()
            self._refresh_send_state()

    def eventFilter(self, obj, event):
        if obj == self.inp and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self._send()
                return True
        return super().eventFilter(obj, event)


# ============ Voice Overlay ============

class VoiceOverlay(QFrame):
    """Gemini Live-style voice overlay with conversation history"""
    closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(f"background: rgba(10,10,10,245); border: 1px solid rgba(255,255,255,0.05);")
        self._history = []  # Voice conversation history
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Top bar with title and close
        top = QHBoxLayout()
        top.setContentsMargins(28, 24, 28, 0)
        
        title = QLabel("🎤 Voice Mode")
        title.setFont(QFont(FONT_HEADING, 17, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        top.addWidget(title)
        
        top.addStretch()
        
        cb = QPushButton("✕")
        cb.setFixedSize(36, 36)
        cb.setCursor(Qt.PointingHandCursor)
        cb.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.08); color: {TEXT_DIM};
                border: none; border-radius: 18px; font-size: 16px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.14); color: {TEXT}; }}
        """)
        cb.clicked.connect(lambda: self.closed.emit())
        top.addWidget(cb)
        lay.addLayout(top)

        # Conversation history (scrollable)
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.15); border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.history_widget = QWidget()
        self.history_lay = QVBoxLayout(self.history_widget)
        self.history_lay.setContentsMargins(24, 16, 24, 16)
        self.history_lay.setSpacing(12)
        self.history_lay.addStretch()
        self.history_scroll.setWidget(self.history_widget)
        lay.addWidget(self.history_scroll, 1)

        # Center orb area
        orb_container = QWidget()
        orb_container.setFixedHeight(220)
        orb_lay = QVBoxLayout(orb_container)
        orb_lay.setContentsMargins(0, 10, 0, 0)
        
        olay = QHBoxLayout()
        olay.addStretch()
        self.orb = OrbWidget()
        olay.addWidget(self.orb)
        olay.addStretch()
        orb_lay.addLayout(olay)

        # Status
        self.status = QLabel("Tap mic to speak")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont(FONT_FAMILY, 13))
        self.status.setStyleSheet(f"color: {TEXT_DIM}; margin-top: 8px;")
        orb_lay.addWidget(self.status)
        
        lay.addWidget(orb_container)

        # Bottom bar
        bot = QFrame()
        bot.setFixedHeight(110)
        bot.setStyleSheet(f"background: rgba(40,40,40,0.95); border-top: 1px solid rgba(255,255,255,0.06);")
        bl = QVBoxLayout(bot)
        bl.setContentsMargins(28, 14, 28, 18)
        bl.setSpacing(10)

        self.transcript = QLabel("")
        self.transcript.setAlignment(Qt.AlignCenter)
        self.transcript.setWordWrap(True)
        self.transcript.setFont(QFont(FONT_FAMILY, 14))
        self.transcript.setStyleSheet(f"color: {TEXT};")
        bl.addWidget(self.transcript)

        mr = QHBoxLayout()
        mr.addStretch()
        self.mic = QPushButton("🎤")
        self.mic.setFixedSize(56, 56)
        self.mic.setCursor(Qt.PointingHandCursor)
        self.mic.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BLUE}, stop:1 #2563eb);
                color: white; border: none; border-radius: 28px; font-size: 24px;
            }}
            QPushButton:hover {{ background: #2563eb; }}
        """)
        mr.addWidget(self.mic)
        mr.addStretch()
        bl.addLayout(mr)

        lay.addWidget(bot)

    def add_message(self, role: str, text: str):
        """Add message to voice history display"""
        msg = QLabel()
        msg.setWordWrap(True)
        msg.setFont(QFont(FONT_FAMILY, 12))
        
        if role == "user":
            msg.setText(f"🗣️ {text}")
            msg.setStyleSheet(f"color: {TEXT}; background: rgba(255,255,255,0.06); padding: 12px; border-radius: 12px;")
            msg.setAlignment(Qt.AlignRight)
        else:
            msg.setText(f"💬 {text[:150]}{'...' if len(text) > 150 else ''}")
            msg.setStyleSheet(f"color: {TEXT_DIM}; background: rgba(16,163,127,0.12); padding: 12px; border-radius: 12px;")
            msg.setAlignment(Qt.AlignLeft)
        
        # Insert before the stretch
        self.history_lay.insertWidget(self.history_lay.count() - 1, msg)
        self._history.append((role, text))
        
        # Scroll to bottom
        QTimer.singleShot(50, lambda: self.history_scroll.verticalScrollBar().setValue(
            self.history_scroll.verticalScrollBar().maximum()
        ))
    
    def clear_history(self):
        """Clear voice conversation history"""
        while self.history_lay.count() > 1:
            item = self.history_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._history = []

    def set_state(self, s):
        self.orb.set_state(s)
        txt = {
            VState.IDLE: "Tap mic to speak", 
            VState.LISTEN: "🎤 Listening... speak now", 
            VState.PROCESS: "⏳ Processing...", 
            VState.SPEAK: "🔊 Speaking..."
        }
        self.status.setText(txt.get(s, ""))
        if s == VState.LISTEN:
            self.mic.setStyleSheet(f"background: {RED}; color: white; border: none; border-radius: 28px; font-size: 24px;")
            self.mic.setText("⏹")
        else:
            self.mic.setStyleSheet(f"background: {BLUE}; color: white; border: none; border-radius: 28px; font-size: 24px;")
            self.mic.setText("🎤")

    def set_text(self, t):
        self.transcript.setText(f'"{t}"' if t else "")


# ============ On-Screen Click Effect Overlay ============

class ClickEffectOverlay(QWidget):
    """Frameless transparent window showing a ripple/circle at click coordinates.

    Appears on top of all windows at the exact screen position of a click,
    animates a growing circle, then fades out automatically.
    """

    def __init__(self, x: int, y: int, parent=None):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        try:
            flags |= Qt.WindowTransparentForInput
        except AttributeError:
            pass  # Older PyQt5 versions don't have this flag
        super().__init__(parent, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._radius = 10
        self._max_radius = 36
        self._opacity = 1.0
        self._color = QColor(ACCENT)  # LADA accent

        # Center the widget on the click point
        size = self._max_radius * 2 + 10
        self.setFixedSize(size, size)
        self.move(x - size // 2, y - size // 2)
        self.show()

        # Grow animation (radius 10 → 36, 350ms)
        self._grow_timer = QTimer(self)
        self._grow_timer.setInterval(16)  # ~60fps
        self._grow_timer.timeout.connect(self._animate)
        self._grow_timer.start()

    def _animate(self):
        """Expand circle and fade out."""
        self._radius += 2
        self._opacity -= 0.05
        if self._radius >= self._max_radius or self._opacity <= 0:
            self._grow_timer.stop()
            self.close()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._color, 2)
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        fill_color = QColor(self._color)
        fill_color.setAlphaF(max(0.0, self._opacity * 0.3))
        painter.setBrush(fill_color)
        center = self.rect().center()
        painter.setOpacity(max(0.0, self._opacity))
        painter.drawEllipse(center, self._radius, self._radius)

        # Inner dot
        inner_color = QColor(self._color)
        inner_color.setAlphaF(max(0.0, self._opacity * 0.8))
        painter.setBrush(inner_color)
        painter.drawEllipse(center, 5, 5)


# ============ Comet Screen Control Overlay ============

class CometOverlay(QFrame):
    """Comet-style overlay shown during autonomous screen control tasks.
    Displays live step log, phase indicator, screenshot preview, and stop button."""
    stop_requested = pyqtSignal()
    pause_requested = pyqtSignal()

    PHASE_COLORS = {
        'see': BLUE,        # Blue
        'think': ACCENT,    # Purple
        'act': SUCCESS,     # Green
        'verify': WARNING,  # Amber
        'retry': RED,       # Red
        'done': SUCCESS,    # Green
        'error': RED,       # Red
    }

    PHASE_ICONS = {
        'see': '👁',
        'think': '🧠',
        'act': '⚡',
        'verify': '✅',
        'retry': '🔄',
        'done': '✅',
        'error': '❌',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(10, 10, 10, 230);")
        self._steps = []  # List of (phase, detail) tuples for the log
        self._current_phase = 'see'
        self._is_paused = False
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Top bar: title + stop button
        top = QFrame()
        top.setFixedHeight(56)
        top.setStyleSheet(f"background: rgba(20, 20, 20, 240); border-bottom: 1px solid {BORDER};")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(24, 0, 24, 0)

        # Animated phase dot
        self.phase_dot = QLabel("  ")
        self.phase_dot.setFixedSize(12, 12)
        self.phase_dot.setStyleSheet(f"background: {GREEN}; border-radius: 6px;")
        top_lay.addWidget(self.phase_dot)

        title = QLabel("  Autonomous Control Active")
        title.setFont(QFont(FONT_HEADING, 15, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        top_lay.addWidget(title)

        top_lay.addStretch()

        # Phase label
        self.phase_label = QLabel("INITIALIZING")
        self.phase_label.setFont(QFont(FONT_FAMILY, 11))
        self.phase_label.setStyleSheet(f"color: {TEXT_DIM}; padding: 4px 12px; background: {BG_CARD}; border-radius: 10px;")
        top_lay.addWidget(self.phase_label)

        top_lay.addSpacing(16)

        # Step counter
        self.step_label = QLabel("Step 0 / 30")
        self.step_label.setFont(QFont(FONT_FAMILY, 11))
        self.step_label.setStyleSheet(f"color: {TEXT_DIM};")
        top_lay.addWidget(self.step_label)

        top_lay.addSpacing(16)

        # PAUSE button - toggles pause/resume
        self.pause_btn = QPushButton("  PAUSE  ")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedHeight(36)
        self.pause_btn.setStyleSheet(f"""
            QPushButton {{
                background: #f59e0b; color: white;
                border: none; border-radius: 18px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
                font-family: '{FONT_FAMILY}';
            }}
            QPushButton:hover {{ background: #d97706; }}
        """)
        self.pause_btn.clicked.connect(self._toggle_pause)
        top_lay.addWidget(self.pause_btn)

        top_lay.addSpacing(8)

        # STOP button - prominent red
        self.stop_btn = QPushButton("  STOP  ")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RED}; color: white;
                border: none; border-radius: 18px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
                font-family: '{FONT_FAMILY}';
            }}
            QPushButton:hover {{ background: #dc2626; }}
        """)
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        top_lay.addWidget(self.stop_btn)

        lay.addWidget(top)

        # Main content: side-by-side screenshot + step log
        content = QFrame()
        content.setStyleSheet("background: transparent;")
        content_lay = QHBoxLayout(content)
        content_lay.setContentsMargins(24, 16, 24, 16)
        content_lay.setSpacing(20)

        # LEFT: Screenshot preview
        screenshot_frame = QFrame()
        screenshot_frame.setStyleSheet(f"""
            QFrame {{
                background: {BG_CARD}; border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        ss_lay = QVBoxLayout(screenshot_frame)
        ss_lay.setContentsMargins(12, 12, 12, 12)
        ss_lay.setSpacing(8)

        ss_title = QLabel("Screen View")
        ss_title.setFont(QFont(FONT_FAMILY, 11))
        ss_title.setStyleSheet(f"color: {TEXT_DIM};")
        ss_lay.addWidget(ss_title)

        self.screenshot_label = QLabel()
        self.screenshot_label.setFixedSize(400, 260)
        self.screenshot_label.setAlignment(Qt.AlignCenter)
        self.screenshot_label.setStyleSheet(f"background: {BG_INPUT}; border-radius: 8px;")
        self.screenshot_label.setText("Waiting for screenshot...")
        ss_lay.addWidget(self.screenshot_label)

        # Current action indicator below screenshot
        self.current_action_label = QLabel("")
        self.current_action_label.setFont(QFont(FONT_FAMILY, 12))
        self.current_action_label.setWordWrap(True)
        self.current_action_label.setStyleSheet(f"color: {TEXT}; padding: 8px;")
        self.current_action_label.setMaximumHeight(60)
        ss_lay.addWidget(self.current_action_label)

        content_lay.addWidget(screenshot_frame, 3)

        # RIGHT: Step log (scrollable)
        log_frame = QFrame()
        log_frame.setStyleSheet(f"""
            QFrame {{
                background: {BG_CARD}; border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        log_lay = QVBoxLayout(log_frame)
        log_lay.setContentsMargins(12, 12, 12, 12)
        log_lay.setSpacing(8)

        log_title = QLabel("Action Log")
        log_title.setFont(QFont(FONT_FAMILY, 11))
        log_title.setStyleSheet(f"color: {TEXT_DIM};")
        log_lay.addWidget(log_title)

        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.15); border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.log_widget = QWidget()
        self.log_widget.setStyleSheet("background: transparent;")
        self.log_inner_lay = QVBoxLayout(self.log_widget)
        self.log_inner_lay.setContentsMargins(0, 0, 0, 0)
        self.log_inner_lay.setSpacing(4)
        self.log_inner_lay.addStretch()
        self.log_scroll.setWidget(self.log_widget)
        log_lay.addWidget(self.log_scroll, 1)

        content_lay.addWidget(log_frame, 2)

        lay.addWidget(content, 1)

        # Bottom: progress bar
        bottom = QFrame()
        bottom.setFixedHeight(40)
        bottom.setStyleSheet(f"background: rgba(20, 20, 20, 200); border-top: 1px solid {BORDER};")
        bot_lay = QHBoxLayout(bottom)
        bot_lay.setContentsMargins(24, 0, 24, 0)

        self.progress_bar = QFrame()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet(f"background: {GREEN}; border-radius: 2px;")
        self.progress_bar.setFixedWidth(0)

        progress_bg = QFrame()
        progress_bg.setFixedHeight(4)
        progress_bg.setStyleSheet(f"background: {BG_INPUT}; border-radius: 2px;")
        prog_lay = QHBoxLayout(progress_bg)
        prog_lay.setContentsMargins(0, 0, 0, 0)
        prog_lay.addWidget(self.progress_bar)
        prog_lay.addStretch()

        bot_lay.addWidget(progress_bg, 1)

        bot_lay.addSpacing(16)
        self.time_label = QLabel("")
        self.time_label.setFont(QFont(FONT_FAMILY, 10))
        self.time_label.setStyleSheet(f"color: {TEXT_DIM};")
        bot_lay.addWidget(self.time_label)

        lay.addWidget(bottom)

        # Timer for elapsed time
        self._start_time = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        # Pulse animation timer for phase dot
        self._pulse_timer = QTimer(self)
        self._pulse_on = True
        self._pulse_timer.timeout.connect(self._pulse_dot)
        self._pulse_timer.start(600)

    def _toggle_pause(self):
        """Toggle between paused and running state."""
        self.set_paused_state(not self._is_paused, add_log=True)
        self.pause_requested.emit()

    def set_paused_state(self, paused: bool, add_log: bool = False):
        """Set paused UI state without emitting signals."""
        self._is_paused = paused
        if self._is_paused:
            self.pause_btn.setText("  RESUME  ")
            self.pause_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #10a37f; color: white;
                    border: none; border-radius: 18px;
                    padding: 0 24px; font-size: 13px; font-weight: bold;
                    font-family: '{FONT_FAMILY}';
                }}
                QPushButton:hover {{ background: #059669; }}
            """)
            if add_log:
                self._add_log_entry('PAUSED', '⏸ Task paused by user', '#f59e0b')
        else:
            self.pause_btn.setText("  PAUSE  ")
            self.pause_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #f59e0b; color: white;
                    border: none; border-radius: 18px;
                    padding: 0 24px; font-size: 13px; font-weight: bold;
                    font-family: '{FONT_FAMILY}';
                }}
                QPushButton:hover {{ background: #d97706; }}
            """)
            if add_log:
                self._add_log_entry('RESUMED', '▶ Task resumed', '#10a37f')

    def start(self, task_description: str):
        """Start the overlay for a new task."""
        self._steps = []
        self.set_paused_state(False, add_log=False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setVisible(True)
        self._start_time = datetime.now()
        self._elapsed_timer.start(1000)
        self.current_action_label.setText(f"Task: {task_description}")
        self.step_label.setText("Step 0")
        self.phase_label.setText("STARTING")
        # Clear log
        while self.log_inner_lay.count() > 1:
            item = self.log_inner_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.show()
        self.raise_()

    def update_progress(self, step, max_steps, phase, detail, screenshot_path=None):
        """Update the overlay with new progress info. Called from main thread."""
        self._current_phase = phase
        color = self.PHASE_COLORS.get(phase, TEXT_DIM)
        icon = self.PHASE_ICONS.get(phase, '')

        # Update phase indicator
        self.phase_dot.setStyleSheet(f"background: {color}; border-radius: 6px;")
        self.phase_label.setText(f"{icon} {phase.upper()}")
        self.phase_label.setStyleSheet(
            f"color: white; padding: 4px 12px; background: {color}; border-radius: 10px; font-weight: bold;"
        )

        # Update step counter
        self.step_label.setText(f"Step {step} / {max_steps}")

        # Update current action
        if detail:
            self.current_action_label.setText(f"{icon} {detail}")

        # Update progress bar
        if max_steps > 0:
            pct = min(100, int(step / max_steps * 100))
            # Calculate width relative to parent
            parent_width = self.progress_bar.parent().width() if self.progress_bar.parent() else 600
            bar_width = max(4, int(parent_width * pct / 100))
            self.progress_bar.setFixedWidth(bar_width)

        # Add to log
        if detail:
            self._add_log_entry(phase, detail, color, icon)

        # Update screenshot if available
        if screenshot_path:
            self._update_screenshot(screenshot_path)

    def _add_log_entry(self, phase, detail, color, icon):
        """Add an entry to the action log."""
        entry = QLabel(f"{icon} [{phase.upper()}] {detail}")
        entry.setFont(QFont(FONT_FAMILY, 10))
        entry.setWordWrap(True)
        entry.setStyleSheet(f"color: {color}; padding: 4px 8px; background: rgba(255,255,255,0.03); border-radius: 4px;")
        # Insert before the stretch
        self.log_inner_lay.insertWidget(self.log_inner_lay.count() - 1, entry)
        self._steps.append((phase, detail))
        # Auto-scroll to bottom
        QTimer.singleShot(10, lambda: self.log_scroll.verticalScrollBar().setValue(
            self.log_scroll.verticalScrollBar().maximum()
        ))

    def _update_screenshot(self, path):
        """Update the screenshot preview."""
        try:
            from PyQt5.QtGui import QPixmap
            if Path(path).exists():
                pixmap = QPixmap(path).scaled(
                    self.screenshot_label.width(),
                    self.screenshot_label.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.screenshot_label.setPixmap(pixmap)
        except Exception:
            pass

    def _update_elapsed(self):
        """Update elapsed time display."""
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            mins = int(elapsed.total_seconds() // 60)
            secs = int(elapsed.total_seconds() % 60)
            self.time_label.setText(f"{mins}:{secs:02d}")

    def _pulse_dot(self):
        """Pulse animation for the phase dot."""
        self._pulse_on = not self._pulse_on
        color = self.PHASE_COLORS.get(self._current_phase, ACCENT)
        if self._pulse_on:
            self.phase_dot.setStyleSheet(f"background: {color}; border-radius: 6px;")
        else:
            self.phase_dot.setStyleSheet(f"background: transparent; border: 2px solid {color}; border-radius: 6px;")

    def finish(self, success: bool, message: str):
        """Finalize the overlay when task completes."""
        self._elapsed_timer.stop()
        self._pulse_timer.stop()
        phase = 'done' if success else 'error'
        color = self.PHASE_COLORS[phase]
        icon = self.PHASE_ICONS[phase]

        self.phase_dot.setStyleSheet(f"background: {color}; border-radius: 6px;")
        self.phase_label.setText(f"{icon} {'COMPLETE' if success else 'FAILED'}")
        self.phase_label.setStyleSheet(
            f"color: white; padding: 4px 12px; background: {color}; border-radius: 10px; font-weight: bold;"
        )
        self.current_action_label.setText(message)
        self.stop_btn.setText("  CLOSE  ")
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_HOVER}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 18px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
                font-family: '{FONT_FAMILY}';
            }}
            QPushButton:hover {{ background: {BG_CARD}; }}
        """)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setVisible(False)

        self._add_log_entry(phase, message, color, icon)

        # Fill progress bar
        parent_width = self.progress_bar.parent().width() if self.progress_bar.parent() else 600
        self.progress_bar.setFixedWidth(parent_width)
        self.progress_bar.setStyleSheet(f"background: {color}; border-radius: 2px;")


class AutonomousActionOverlay(QWidget):
    """Top-level floating overlay for autonomous action streaming on the desktop."""

    stop_requested = pyqtSignal()
    pause_requested = pyqtSignal()

    PHASE_COLORS = {
        'see': BLUE,
        'think': ACCENT,
        'act': SUCCESS,
        'verify': WARNING,
        'retry': RED,
        'done': SUCCESS,
        'error': RED,
    }

    def __init__(self):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("LADA Autonomous Overlay")

        self._drag_offset = None
        self._is_paused = False
        self._start_time = None
        self._last_event_key = None

        self.setFixedSize(460, 320)
        self._build()

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.panel = QFrame()
        self.panel.setObjectName("autonomousPanel")
        self.panel.setStyleSheet(f"""
            QFrame#autonomousPanel {{
                background: rgba(10, 10, 10, 236);
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
        """)
        root.addWidget(self.panel)

        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(12, 10, 12, 10)
        panel_lay.setSpacing(8)

        self.header = QFrame()
        header_lay = QHBoxLayout(self.header)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(8)

        title = QLabel("AUTONOMOUS CONTROL")
        title.setFont(QFont(FONT_HEADING, 10, QFont.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        header_lay.addWidget(title)

        header_lay.addStretch()

        self.phase_badge = QLabel("START")
        self.phase_badge.setFont(QFont(FONT_FAMILY, 9, QFont.Bold))
        self.phase_badge.setStyleSheet(f"color: white; background: {ACCENT}; border-radius: 8px; padding: 4px 10px;")
        header_lay.addWidget(self.phase_badge)

        self.step_label = QLabel("Step 0/0")
        self.step_label.setFont(QFont(FONT_FAMILY, 9))
        self.step_label.setStyleSheet(f"color: {TEXT_DIM};")
        header_lay.addWidget(self.step_label)

        self.pause_btn = QPushButton("PAUSE")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedHeight(26)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background: #f59e0b;
                color: white;
                border: none;
                border-radius: 13px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover { background: #d97706; }
        """)
        self.pause_btn.clicked.connect(self._toggle_pause)
        header_lay.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setFixedHeight(26)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RED};
                color: white;
                border: none;
                border-radius: 13px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #dc2626; }}
        """)
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        header_lay.addWidget(self.stop_btn)

        panel_lay.addWidget(self.header)

        self.task_label = QLabel("Task:")
        self.task_label.setWordWrap(True)
        self.task_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        panel_lay.addWidget(self.task_label)

        self.current_label = QLabel("Waiting...")
        self.current_label.setWordWrap(True)
        self.current_label.setStyleSheet(f"color: {TEXT}; font-size: 12px; font-weight: bold;")
        panel_lay.addWidget(self.current_label)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 6px;
                font-size: 11px;
                font-family: '{FONT_FAMILY}';
            }}
        """)
        panel_lay.addWidget(self.log, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)

        self.elapsed_label = QLabel("0:00")
        self.elapsed_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        bottom.addWidget(self.elapsed_label)

        bottom.addStretch()

        hint = QLabel("Drag header to move")
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        bottom.addWidget(hint)

        panel_lay.addLayout(bottom)

    def _set_default_position(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        self.move(geom.x() + geom.width() - self.width() - 24, geom.y() + 24)

    def _append_log(self, text: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"{timestamp}  {text}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _toggle_pause(self):
        self.set_paused_state(not self._is_paused, add_log=True)
        self.pause_requested.emit()

    def set_paused_state(self, paused: bool, add_log: bool = False):
        self._is_paused = paused
        if paused:
            self.pause_btn.setText("RESUME")
            self.pause_btn.setStyleSheet("""
                QPushButton {
                    background: #10a37f;
                    color: white;
                    border: none;
                    border-radius: 13px;
                    padding: 0 12px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #059669; }
            """)
            if add_log:
                self._append_log("[PAUSE] Paused by user")
        else:
            self.pause_btn.setText("PAUSE")
            self.pause_btn.setStyleSheet("""
                QPushButton {
                    background: #f59e0b;
                    color: white;
                    border: none;
                    border-radius: 13px;
                    padding: 0 12px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #d97706; }
            """)
            if add_log:
                self._append_log("[PAUSE] Resumed")

    def start(self, task_description: str):
        self._start_time = datetime.now()
        self._elapsed_timer.start(1000)
        self._last_event_key = None
        self.log.clear()
        self.set_paused_state(False, add_log=False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setVisible(True)
        self.stop_btn.setText("STOP")
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RED};
                color: white;
                border: none;
                border-radius: 13px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #dc2626; }}
        """)
        self.task_label.setText(f"Task: {task_description}")
        self.current_label.setText("Starting autonomous control...")
        self.step_label.setText("Step 0/0")
        self.phase_badge.setText("START")
        self.phase_badge.setStyleSheet(f"color: white; background: {ACCENT}; border-radius: 8px; padding: 4px 10px;")
        self._append_log("[START] Autonomous task started")
        self._set_default_position()
        self.show()
        self.raise_()

    def update_progress(self, step, max_steps, phase, detail):
        phase_name = (phase or "").upper()
        color = self.PHASE_COLORS.get(phase, TEXT_DIM)
        self.phase_badge.setText(phase_name or "RUN")
        self.phase_badge.setStyleSheet(
            f"color: white; background: {color}; border-radius: 8px; padding: 4px 10px;"
        )
        self.step_label.setText(f"Step {step}/{max_steps}")
        if detail:
            self.current_label.setText(detail)

        key = (step, phase, detail)
        if detail and key != self._last_event_key:
            self._append_log(f"[{phase_name}] {detail}")
            self._last_event_key = key

    def log_click(self, x: int, y: int):
        self._append_log(f"[CLICK] ({x}, {y})")

    def finish(self, success: bool, message: str):
        self._elapsed_timer.stop()
        phase = 'done' if success else 'error'
        color = self.PHASE_COLORS[phase]
        self.phase_badge.setText("DONE" if success else "FAILED")
        self.phase_badge.setStyleSheet(
            f"color: white; background: {color}; border-radius: 8px; padding: 4px 10px;"
        )
        self.current_label.setText(message)
        self._append_log(f"[{self.phase_badge.text()}] {message}")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setVisible(False)
        self.stop_btn.setText("CLOSE")
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_HOVER};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 13px;
                padding: 0 12px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {BG_CARD}; }}
        """)

    def _update_elapsed(self):
        if not self._start_time:
            return
        elapsed = datetime.now() - self._start_time
        mins = int(elapsed.total_seconds() // 60)
        secs = int(elapsed.total_seconds() % 60)
        self.elapsed_label.setText(f"{mins}:{secs:02d}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.header.geometry().contains(event.pos()):
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


# ============ Main App ============

class LadaApp(QMainWindow):
    wake_triggered = pyqtSignal(str)  # Signal for wake word commands
    
    def __init__(self):
        super().__init__()

        # ── Lightweight state (set immediately so _build/_wire work) ──
        self.router = None
        self.voice = None
        self.conv = []
        self.conv_file = None
        self.v_state = VState.IDLE
        self.v_worker = None
        self.ai_worker = None
        self.sys_ctrl = None
        self.jarvis = None
        self.voice_nlu = None
        self.ai_agent = None
        self.flight_agent = None
        self.product_agent = None
        self.safety_gate = None
        self._optional_init_complete = False
        self._cost_tracker = None
        self._last_prompt = ""
        self._wakeup_active = False
        self._voice_enabled = True  # Master voice on/off flag (starts ON)
        self._autonomous_event_log = []
        self._sidebar_auto_collapsed = False
        self._sidebar_responsive_adjusting = False

        # Standalone bus/orchestrator (feature-gated)
        self._standalone_orchestrator_enabled = os.getenv(
            "LADA_STANDALONE_ORCHESTRATOR", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.standalone_command_bus = None
        self.standalone_orchestrator = None

        # Apply saved personality mode before first UI greeting.
        self._apply_saved_personality_mode()

        # Build UI immediately so window appears right away
        self._build()
        self._wire()

        # Defer all heavy module loading so window is visible first
        QTimer.singleShot(200, self._deferred_heavy_init)

    @staticmethod
    def _personality_mode_from_index(index: int) -> str:
        """Map personality combo index to personality mode key."""
        mapping = {
            0: "jarvis",
            1: "friday",
            2: "karen",
            3: "casual",
        }
        return mapping.get(int(index), "karen")

    def _apply_saved_personality_mode(self):
        """Load and apply persisted personality mode for consistent runtime tone."""
        if not (JARVIS_OK and LadaPersonality):
            return

        mode_index = 2  # Default to KAREN tone when no config is present.
        try:
            settings_file = Path("config/app_settings.json")
            if settings_file.exists():
                saved = json.loads(settings_file.read_text(encoding="utf-8"))
                mode_index = int(saved.get("personality_mode", mode_index))
        except Exception as e:
            logger.debug(f"[LADA] Could not load saved personality mode: {e}")

        mode_name = self._personality_mode_from_index(mode_index)
        try:
            LadaPersonality.set_mode(mode_name)
        except Exception as e:
            logger.warning(f"[LADA] Could not apply personality mode '{mode_name}': {e}")
    
    def _deferred_heavy_init(self):
        """Initialize core runtime quickly, then defer optional modules.

        This first stage keeps startup responsive so chat UI is usable while
        heavier optional features are initialized in a second phase.
        """
        # Auto-start Ollama if not running
        self._start_ollama()

        # Core router
        if LADA_OK:
            try:
                self.router = HybridAIRouter()
                print("[LADA] AI Router initialized")
            except Exception as e:
                logger.error(f"Router init: {e}")
                print(f"[LADA] Router init error: {e}")

        # Core system services
        self.sys_ctrl = SystemController() if SYS_OK else None

        # Core command path
        self.jarvis = JarvisCommandProcessor(ai_router=self.router) if JARVIS_OK else None
        if self.jarvis:
            print("[LADA] JARVIS command processor initialized")

        # Voice NLU for command routing
        self.voice_nlu = VoiceCommandProcessor(ai_router=self.router) if VOICE_NLU_OK else None
        if self.voice_nlu:
            print("[LADA] Voice NLU initialized")

        # Refresh model/status UI once the router is up.
        try:
            self._load_models()
            self._update_status()
            self._update_header_status()
            self._show_startup_runtime_health()
        except Exception as e:
            print(f"[LADA] Core post-init UI refresh error: {e}")

    def _collect_runtime_health(self):
        """Collect startup health details for model/provider readiness messaging."""
        summary = {
            "router_ready": bool(self.router),
            "providers_total": 0,
            "providers_available": 0,
            "missing_keys": [],
        }

        if not self.router:
            return summary

        status = {}
        try:
            status = self.router.get_status() if hasattr(self.router, 'get_status') else {}
        except Exception as e:
            logger.warning(f"[LADA] Could not read provider status: {e}")

        if isinstance(status, dict):
            summary["providers_total"] = len(status)
            summary["providers_available"] = sum(
                1 for info in status.values() if isinstance(info, dict) and info.get('available')
            )

        provider_manager = getattr(self.router, 'provider_manager', None)
        model_registry = getattr(provider_manager, 'model_registry', None) or getattr(self.router, 'model_registry', None)
        if model_registry and hasattr(model_registry, 'providers') and hasattr(model_registry, 'get_available_providers'):
            try:
                availability = model_registry.get_available_providers()
                missing = set()
                for provider_id, is_ready in availability.items():
                    if is_ready:
                        continue
                    provider = model_registry.providers.get(provider_id)
                    for key in getattr(provider, 'config_keys', []):
                        if not os.getenv(str(key), '').strip():
                            missing.add(str(key))
                summary["missing_keys"] = sorted(missing)
            except Exception as e:
                logger.debug(f"[LADA] Could not collect missing provider keys: {e}")

        return summary

    def _show_startup_runtime_health(self):
        """Show concise startup health guidance for common model/backend issues."""
        summary = self._collect_runtime_health()

        if not summary.get("router_ready"):
            message = "AI router failed to initialize. Check logs for provider setup errors."
        elif summary.get("providers_total", 0) == 0:
            message = "No AI providers loaded. Check models.json and provider configuration."
        elif summary.get("providers_available", 0) == 0:
            missing = summary.get("missing_keys", [])
            if missing:
                hint = ", ".join(missing[:3])
                if len(missing) > 3:
                    hint += ", ..."
                message = f"No AI backends are ready. Missing API keys: {hint}"
            else:
                message = "No AI backends are ready. Check API keys and local model services."
        else:
            message = (
                f"AI backends ready: {summary.get('providers_available', 0)}"
                f"/{summary.get('providers_total', 0)}"
            )

        try:
            if hasattr(self, 'statusbar') and self.statusbar:
                self.statusbar.showMessage(message, 12000)
        except Exception:
            pass
        logger.info(f"[LADA] Startup health: {message}")

        # Defer optional modules to keep first-render snappy.
        try:
            optional_delay_ms = int(os.getenv("LADA_OPTIONAL_INIT_DELAY_MS", "450"))
        except Exception:
            optional_delay_ms = 450
        optional_delay_ms = max(100, optional_delay_ms)
        QTimer.singleShot(optional_delay_ms, self._deferred_optional_init)

    def _deferred_optional_init(self):
        """Initialize optional features after core startup is complete."""
        # Voice engine
        if VOICE_OK and FreeNaturalVoice:
            try:
                self.voice = FreeNaturalVoice(tamil_mode=False, auto_detect=False)
                print("[LADA] Voice engine initialized")
            except Exception as e:
                logger.error(f"Voice init: {e}")
                print(f"[LADA] Voice init error: {e}")

        # Agents
        if AGENTS_OK and self.router:
            try:
                self.flight_agent = FlightAgent(self.router)
                self.product_agent = ProductAgent(self.router)
                self.safety_gate = SafetyGate(ui_callback=self._safety_ui_callback)
                print("[LADA] v7.0 Agents initialized (Flight, Product)")
            except Exception as e:
                print(f"[LADA] Agent init error: {e}")

        # AI Command Agent — AI-first command execution with tool calling
        self.ai_agent = None
        try:
            from modules.ai_command_agent import AICommandAgent
            if self.router and hasattr(self.router, 'provider_manager') and self.router.provider_manager:
                self.ai_agent = AICommandAgent(
                    provider_manager=self.router.provider_manager,
                    tool_registry=self.router.tool_registry,
                    config={
                        'enabled': os.getenv('LADA_AI_AGENT_ENABLED', '1') == '1',
                        'max_rounds': int(os.getenv('LADA_AI_AGENT_MAX_ROUNDS', '5')),
                    }
                )
                print("[LADA] AI Command Agent initialized")
        except Exception as e:
            logger.warning(f"[LADA] AI Command Agent not available: {e}")

        # Standalone orchestrator bridge (opt-in)
        if self._standalone_orchestrator_enabled:
            self._init_standalone_orchestrator()

        # Advanced modules (continuous listener, calendar, weather, face, etc.)
        self._init_advanced_modules()

        # Cost tracker
        if COST_TRACKER_OK:
            self._cost_tracker = CostTracker(
                budget_usd=float(os.getenv('AI_BUDGET_USD', '0')),
                persist_path="data/cost_history.json"
            )

        # Proactive agent — intelligent suggestions and notifications
        self._proactive_agent = None
        if PROACTIVE_AGENT_OK:
            try:
                self._proactive_agent = get_proactive_agent(jarvis_core=self.jarvis)
                self._proactive_agent.register_callback(self._on_proactive_suggestion)
                self._proactive_agent.start()
                print("[LADA] Proactive Agent initialized and started")
            except Exception as e:
                logger.warning(f"[LADA] Proactive Agent init failed: {e}")

        self._optional_init_complete = True
        print("[LADA] Ready.")

        # Start wake word detection
        QTimer.singleShot(800, self._start_wake_detection)

        # Morning briefing
        QTimer.singleShot(1800, self._check_morning_briefing)

    def _init_standalone_orchestrator(self):
        """Initialize standalone command bus + orchestrator for desktop dispatch."""
        if self.standalone_orchestrator is not None:
            return

        try:
            from modules.standalone.command_bus import create_command_bus
            from modules.standalone.orchestrator import create_orchestrator

            self.standalone_command_bus = create_command_bus()
            self.standalone_orchestrator = create_orchestrator(
                command_bus=self.standalone_command_bus,
                jarvis_getter=lambda: self.jarvis,
                ai_router_getter=lambda: self.router,
                autostart=True,
            )
            print("[LADA] Standalone orchestrator enabled")
        except Exception as e:
            logger.warning(f"[LADA] Standalone orchestrator init failed: {e}")
            self.standalone_orchestrator = None
            if self.standalone_command_bus is not None:
                try:
                    self.standalone_command_bus.stop()
                except Exception:
                    pass
                self.standalone_command_bus = None

    def _stop_standalone_orchestrator(self):
        """Stop standalone orchestrator and command bus if initialized."""
        if self.standalone_orchestrator is not None:
            try:
                self.standalone_orchestrator.stop()
            except Exception:
                pass
            self.standalone_orchestrator = None

        if self.standalone_command_bus is not None:
            try:
                self.standalone_command_bus.stop()
            except Exception:
                pass
            self.standalone_command_bus = None

    def _dispatch_system_command(self, text: str) -> tuple:
        """Dispatch system commands via standalone orchestrator when enabled, fallback to Jarvis."""
        if not text:
            return False, ""

        if self._standalone_orchestrator_enabled and self.standalone_orchestrator is not None:
            try:
                from modules.standalone.contracts import CommandEnvelope

                timeout_ms = int(os.getenv("LADA_STANDALONE_TIMEOUT_MS", "60000"))
                timeout_ms = max(1000, timeout_ms)

                envelope = CommandEnvelope.from_dict({
                    "source": "desktop",
                    "target": "system",
                    "action": "execute",
                    "payload": {"command": text},
                    "timeout_ms": timeout_ms,
                    "metadata": {
                        "channel": "desktop_app",
                    },
                })

                event = self.standalone_orchestrator.submit(
                    envelope,
                    wait_for_result=True,
                    timeout_ms=timeout_ms,
                )

                if event is not None:
                    payload = event.payload or {}
                    message = str(payload.get("message", ""))
                    error = str(payload.get("error", ""))

                    if event.status == "completed":
                        return True, message

                    # Not handled should continue through existing fallback chain.
                    if error == "not_handled":
                        return False, message
            except Exception as e:
                logger.warning(f"[LADA] Standalone system dispatch failed, using fallback: {e}")

        if self.jarvis:
            try:
                return self.jarvis.process(text)
            except Exception as e:
                logger.warning(f"[LADA] Jarvis system dispatch failed: {e}")

        return False, ""

    def _handle_openclaw_alias_command(self, text: str) -> tuple:
        """Handle OpenClaw-prefixed commands as native LADA aliases.

        This keeps user continuity while enforcing native-only runtime behavior.
        """
        command = text.strip()
        lc = command.lower()

        adapter = None
        try:
            from integrations.openclaw_adapter import get_openclaw_adapter
            adapter = get_openclaw_adapter()
        except Exception as e:
            logger.debug(f"[LADA] OpenClaw adapter unavailable: {e}")

        if lc in {"openclaw", "openclaw help"}:
            return True, (
                "OpenClaw compatibility commands:\n"
                "- openclaw status\n"
                "- openclaw connect\n"
                "- openclaw disconnect\n"
                "- openclaw navigate <url>\n"
                "- openclaw snapshot\n"
                "- openclaw click <selector>\n"
                "- openclaw type <selector> :: <text>\n"
                "- openclaw scroll <up|down> [pixels]\n"
                "- openclaw extract [selector]"
            )

        if lc == "openclaw status":
            lines = ["OpenClaw compatibility status:"]
            if adapter:
                status = adapter.status()
                lines.append(f"- adapter enabled: {status.get('enabled', False)}")
                lines.append(f"- adapter state: {status.get('state', 'unknown')}")
                lines.append(f"- adapter connected: {status.get('connected', False)}")
                if status.get('url'):
                    lines.append(f"- gateway: {status.get('url')}")
            else:
                lines.append("- adapter: disabled (set LADA_OPENCLAW_ADAPTER_ENABLED=true to enable gateway mode)")
            handled, backend = self._handle_backend_status()
            if handled:
                lines.append("")
                lines.append(backend)
            return True, "\n".join(lines)

        if lc == "openclaw connect":
            if not adapter:
                return True, "OpenClaw adapter is disabled. Set LADA_OPENCLAW_ADAPTER_ENABLED=true and restart."
            ok = adapter.connect()
            return True, "OpenClaw adapter connected." if ok else "OpenClaw adapter connection failed."

        if lc == "openclaw disconnect":
            if not adapter:
                return True, "OpenClaw adapter is not active."
            adapter.disconnect()
            return True, "OpenClaw adapter disconnected."

        if lc.startswith("openclaw navigate "):
            url = command[len("openclaw navigate "):].strip()
            if not url:
                return True, "Usage: openclaw navigate <url>"
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            if adapter and adapter.navigate(url):
                return True, f"OpenClaw adapter navigated to {url}."

            handled, response = self._dispatch_system_command(f"open {url}")
            if handled:
                return True, response
            if self.voice_nlu:
                handled, response = self.voice_nlu.process(f"open url {url}")
                if handled:
                    return True, response
            return True, f"Tried native navigation to {url}, but could not complete it."

        if lc == "openclaw snapshot":
            if adapter:
                snapshot = adapter.snapshot_summary()
                if snapshot:
                    return True, (
                        "OpenClaw snapshot summary:\n"
                        f"- URL: {snapshot.get('url', '')}\n"
                        f"- Title: {snapshot.get('title', '')}\n"
                        f"- Interactive elements: {snapshot.get('interactive_elements', 0)}\n"
                        f"- Text chars: {snapshot.get('text_chars', 0)}"
                    )

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                page = browser.get_page_content()
                if page.get('success'):
                    shot = browser.screenshot()
                    msg = (
                        "Native snapshot summary:\n"
                        f"- URL: {page.get('url', '')}\n"
                        f"- Title: {page.get('title', '')}\n"
                        f"- Text chars: {len(str(page.get('text', '')))}"
                    )
                    if shot.get('success'):
                        msg += f"\n- Screenshot: {shot.get('path', '')}"
                    return True, msg
            except Exception:
                pass

            handled, response = self._dispatch_system_command("take a screenshot")
            if handled:
                return True, response
            return True, "Native screenshot command is currently unavailable."

        if lc.startswith("openclaw click "):
            selector = command[len("openclaw click "):].strip()
            if not selector:
                return True, "Usage: openclaw click <selector>"

            if adapter and adapter.click(selector):
                return True, f"OpenClaw adapter clicked: {selector}"

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.click(selector)
                if result.get('success'):
                    return True, f"Stealth click successful: {selector}"
            except Exception:
                pass

            return True, f"Could not click selector: {selector}"

        if lc.startswith("openclaw type "):
            payload = command[len("openclaw type "):].strip()
            separator = "::" if "::" in payload else "|" if "|" in payload else ""
            if not separator:
                return True, "Usage: openclaw type <selector> :: <text>"

            selector, typed = [p.strip() for p in payload.split(separator, 1)]
            if not selector:
                return True, "Usage: openclaw type <selector> :: <text>"

            if adapter and adapter.type_text(selector, typed):
                return True, f"OpenClaw adapter typed into {selector}."

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.type_text(selector=selector, text=typed)
                if result.get('success'):
                    return True, f"Stealth typed into {selector}."
            except Exception:
                pass

            return True, f"Could not type into selector: {selector}"

        if lc.startswith("openclaw scroll "):
            payload = command[len("openclaw scroll "):].strip().split()
            direction = payload[0].lower() if payload else "down"
            if direction not in {"up", "down"}:
                direction = "down"
            amount = 500
            if len(payload) > 1:
                try:
                    amount = int(payload[1])
                except Exception:
                    amount = 500

            if adapter and adapter.scroll(direction=direction, amount=amount):
                return True, f"OpenClaw adapter scrolled {direction} by {amount}px."

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.scroll(direction=direction, amount=amount)
                if result.get('success'):
                    return True, f"Stealth scrolled {direction} by {amount}px."
            except Exception:
                pass

            return True, f"Could not scroll {direction}."

        if lc.startswith("openclaw extract"):
            selector = command[len("openclaw extract"):].strip()

            if adapter:
                text_out = adapter.extract_text(selector=selector or None)
                if text_out:
                    return True, text_out[:4000]

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                if selector:
                    result = browser.execute_js(
                        "const el=document.querySelector(arguments[0]); return el ? el.innerText : '';",
                        selector,
                    )
                    if result:
                        return True, str(result)[:4000]
                page = browser.get_page_content()
                if page.get('success'):
                    return True, str(page.get('text', ''))[:4000]
            except Exception:
                pass

            return True, "Could not extract page content."

        return True, (
            "OpenClaw compatibility command not recognized. "
            "Use 'openclaw help' for supported commands."
        )

    def _start_ollama(self):
        """Auto-start Ollama in background if not running"""
        import subprocess, threading
        def _bg_start():
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=1)
                if response.status_code == 200:
                    return
            except:
                pass
            try:
                subprocess.Popen(
                    ['ollama', 'serve'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
            except:
                pass
        threading.Thread(target=_bg_start, daemon=True).start()
    
    def _init_advanced_modules(self):
        """Initialize JARVIS-like advanced modules"""
        # Continuous Listener (always listening, no wake word needed)
        self.continuous_listener = None
        if WAKE_OK:
            try:
                self.continuous_listener = ContinuousListener()
                print("[LADA] Continuous listener ready - always listening")
            except Exception as e:
                print(f"[LADA] Continuous listener init error: {e}")
        
        # Google Calendar
        self.calendar = None
        if CALENDAR_OK:
            try:
                self.calendar = GoogleCalendar()
                print("[LADA] Google Calendar ready")
            except Exception as e:
                print(f"[LADA] Calendar init error: {e}")
        
        # Weather briefing
        self.weather = None
        if WEATHER_OK:
            try:
                self.weather = WeatherBriefing()
                print("[LADA] Weather module ready")
            except Exception as e:
                print(f"[LADA] Weather init error: {e}")
        
        # Face recognition (for future use)
        self.face_auth = None
        if FACE_OK:
            try:
                self.face_auth = FaceRecognition()
                print("[LADA] Face recognition ready")
            except Exception as e:
                print(f"[LADA] Face recognition init error: {e}")
        
        # Continuous monitoring (Phase 6)
        self.monitor = None
        try:
            from modules.continuous_monitor import ContinuousMonitor
            self.monitor = ContinuousMonitor(alert_callback=self._on_system_alert)
            self.monitor.start()
            print("[LADA] Continuous monitoring active")
        except ImportError:
            print("[LADA] Continuous monitoring not available")
        except Exception as e:
            print(f"[LADA] Monitor init error: {e}")
        
        # === ALEXA/ECHO INTEGRATION - Background Services ===
        self._start_alexa_services()
    
    def _start_alexa_services(self):
        """Start Alexa integration services in background (feature-flagged)."""
        enabled = os.getenv("LADA_ALEXA_AUTOSTART", "0").strip().lower() in {
            "1", "true", "yes", "on"
        }
        if not enabled:
            print("[LADA] Alexa autostart disabled (set LADA_ALEXA_AUTOSTART=1 to enable)")
            return

        import socket
        import sys
        import time

        # Track background processes for cleanup
        self.alexa_processes = []

        def _port_in_use(port: int) -> bool:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    return s.connect_ex(('localhost', port)) == 0
            except Exception:
                return False

        def _worker():
            base_dir = Path(__file__).parent if "__file__" in dir() else Path(".")
            if not base_dir.exists():
                base_dir = Path("c:/lada ai")

            python_exe = sys.executable
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            child_env = os.environ.copy()
            child_env.setdefault("PYTHONIOENCODING", "utf-8")
            child_env.setdefault("PYTHONUTF8", "1")

            api_running = _port_in_use(5000)
            alexa_running = _port_in_use(5001)

            # 1. Start API Server (port 5000) if not running
            if not api_running:
                try:
                    api_server_path = base_dir / "modules" / "api_server.py"
                    if api_server_path.exists():
                        proc = subprocess.Popen(
                            [python_exe, str(api_server_path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=creationflags,
                            cwd=str(base_dir),
                            env=child_env,
                        )
                        self.alexa_processes.append(proc)
                        print("[LADA] API Server started (port 5000) - hidden")
                except Exception as e:
                    print(f"[LADA] API Server start error: {e}")
            else:
                print("[LADA] API Server already running on port 5000")

            # 2. Start Alexa Bridge (port 5001) if not running
            if not alexa_running:
                try:
                    alexa_server_path = base_dir / "integrations" / "alexa_server.py"
                    if alexa_server_path.exists():
                        proc = subprocess.Popen(
                            [python_exe, str(alexa_server_path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=creationflags,
                            cwd=str(base_dir),
                            env=child_env,
                        )
                        self.alexa_processes.append(proc)
                        print("[LADA] Alexa Bridge started (port 5001) - hidden")
                except Exception as e:
                    print(f"[LADA] Alexa Bridge start error: {e}")
            else:
                print("[LADA] Alexa Bridge already running on port 5001")

            # 3. Start ngrok tunnel (if ngrok is installed)
            try:
                try:
                    resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
                    tunnels = resp.json().get("tunnels", [])
                    if tunnels:
                        print(f"[LADA] ngrok already running: {tunnels[0].get('public_url', 'active')}")
                        return
                except Exception:
                    pass

                proc = subprocess.Popen(
                    ["ngrok", "http", "5001", "--log=stdout"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    env=child_env,
                )
                self.alexa_processes.append(proc)
                print("[LADA] ngrok tunnel started (5001 -> HTTPS) - hidden")

                time.sleep(2)
                try:
                    resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
                    tunnels = resp.json().get("tunnels", [])
                    if tunnels:
                        ngrok_url = tunnels[0].get("public_url", "")
                        print(f"[LADA] Alexa endpoint: {ngrok_url}/")
                except Exception:
                    print("[LADA] ngrok running (check http://127.0.0.1:4040 for URL)")

            except FileNotFoundError:
                print("[LADA] ngrok not installed - Alexa works on local network only")
            except Exception as e:
                print(f"[LADA] ngrok start error: {e}")

        threading.Thread(target=_worker, daemon=True, name="LADA-AlexaAutostart").start()
    
    def _on_system_alert(self, alert):
        """Handle system alerts from continuous monitor"""
        try:
            # Show alert in status bar
            icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(alert.level.value, "📢")
            message = f"{icon} {alert.title}: {alert.message}"
            QTimer.singleShot(0, lambda: self.statusbar.showMessage(message, 10000))
        except Exception as e:
            print(f"[LADA] Alert display error: {e}")
    
    def _start_wake_detection(self):
        """Start continuous background listening.

        WAKEUP behavior (Phase 1):
        - STANDBY: only responds to "LADA wakeup"
        - ACTIVE: processes commands; "LADA turn off" returns to standby
        """
        if not self.continuous_listener:
            return
        
        self.wake_triggered.connect(self._on_wake_command)
        
        def on_command(cmd):
            """Called when any speech is recognized"""
            if cmd:
                print(f"[LADA] Command: {cmd}")
                self.wake_triggered.emit(cmd)
        
        def on_listening():
            """Called when starting to listen"""
            pass  # Can add visual feedback here
        
        def on_processing():
            """Called when processing speech"""
            pass  # Can add visual feedback here
        
        self.continuous_listener.on_command = on_command
        self.continuous_listener.on_listening = on_listening
        self.continuous_listener.on_processing = on_processing
        
        try:
            self.continuous_listener.start()
            self._set_wakeup_active(False)
            print("[LADA] Continuous listening active - say 'LADA wakeup' to activate")
        except Exception as e:
            print(f"[LADA] Could not start continuous listening: {e}")

    def _normalize_voice_text(self, text: str) -> str:
        """Normalize recognized text for robust phrase matching."""
        try:
            import re
            t = (text or "").strip().lower()
            t = re.sub(r"[^a-z0-9\s]", " ", t)
            t = re.sub(r"\s+", " ", t).strip()
            return t
        except Exception:
            return (text or "").strip().lower()

    def _is_wakeup_phrase(self, normalized_text: str) -> bool:
        wake_phrases = {
            "hey lada", "lada wakeup", "lada wake up",
            "hi lada", "hello lada", "ok lada", "okay lada",
            "hey lara", "hey lotta",  # common misrecognitions
        }
        return normalized_text in wake_phrases or normalized_text.startswith("hey lada")

    def _is_turn_off_phrase(self, normalized_text: str) -> bool:
        off_phrases = {
            "lada turn off", "lada turnoff", "lada close",
            "lada stop", "lada sleep", "lada shut up",
            "stop listening", "stop lada", "close lada",
            "lada go to sleep", "lada standby",
        }
        return normalized_text in off_phrases

    def _set_wakeup_active(self, active: bool):
        self._wakeup_active = bool(active)
        try:
            self._update_status()
            if hasattr(self, 'tray_icon') and self.tray_icon:
                tip = "LADA AI - Say 'Hey LADA'" if not self._wakeup_active else "LADA AI - ACTIVE (say 'LADA stop')"
                self.tray_icon.setToolTip(tip)
            # Update header voice toggle button
            if hasattr(self, 'voice_toggle_btn'):
                if self._wakeup_active:
                    self.voice_toggle_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {GREEN}; color: white;
                            border: none; border-radius: 13px; font-size: 11px; font-weight: bold;
                            padding: 4px 14px; font-family: '{FONT_FAMILY}';
                        }}
                        QPushButton:hover {{ background: {ACCENT_GRADIENT_END}; }}
                    """)
                    self.voice_toggle_btn.setText("Voice ON")
                    self.voice_toggle_btn.setToolTip("Voice active - say 'LADA stop' to deactivate")
                else:
                    self.voice_toggle_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {BG_HOVER}; color: {TEXT_DIM};
                            border: none; border-radius: 13px; font-size: 11px;
                            padding: 4px 14px; font-family: '{FONT_FAMILY}';
                        }}
                        QPushButton:hover {{ background: {BG_CARD}; color: {TEXT}; }}
                    """)
                    self.voice_toggle_btn.setText("Voice OFF")
                    self.voice_toggle_btn.setToolTip("Click to enable always-on voice (or say 'Hey LADA')")
        except Exception:
            pass

    def _toggle_always_on_voice(self):
        """Master voice ON/OFF toggle. When OFF, ALL voice is silenced."""
        if self._voice_enabled:
            # === TURN VOICE OFF ===
            self._voice_enabled = False

            # Fully stop always-on listener (not just standby)
            if hasattr(self, 'continuous_listener') and self.continuous_listener:
                try:
                    self.continuous_listener.stop()
                except Exception:
                    pass
            self._set_wakeup_active(False)

            # Close voice overlay if it's open
            if hasattr(self, 'vlay') and self.vlay.isVisible():
                self._close_voice()

            # Disable the Mic button so user cannot re-open overlay
            if hasattr(self, 'voice_btn'):
                self.voice_btn.setEnabled(False)

            self.statusbar.showMessage("Voice OFF — click 'Voice OFF' to re-enable", 4000)
            # Do NOT speak — voice is being turned off

        else:
            # === TURN VOICE ON ===
            self._voice_enabled = True

            # Try to create listener if not available
            if not hasattr(self, 'continuous_listener') or not self.continuous_listener:
                if WAKE_OK and ContinuousListener:
                    try:
                        self.continuous_listener = ContinuousListener()
                    except Exception as e:
                        self.statusbar.showMessage(f"Could not start voice: {e}", 5000)
                        self._voice_enabled = False
                        return
                else:
                    self.statusbar.showMessage("Voice not available - install SpeechRecognition", 5000)
                    self._voice_enabled = False
                    return

            # Re-enable always-on listening
            self._set_wakeup_active(True)
            self._start_wake_detection()

            # Re-enable Mic button
            if hasattr(self, 'voice_btn'):
                self.voice_btn.setEnabled(True)

            self.statusbar.showMessage("Voice ON — listening for commands", 3000)
            if self.voice:
                threading.Thread(
                    target=lambda: self.voice.speak("Voice control on. I'm listening."),
                    daemon=True
                ).start()


    def _on_wake_command(self, cmd):
        """Handle command from continuous listener - execute and speak response"""
        if not cmd:
            return

        normalized = self._normalize_voice_text(cmd)

        # WAKEUP gating: ignore everything until explicitly activated.
        if not self._wakeup_active:
            if self._is_wakeup_phrase(normalized):
                if hasattr(self, 'continuous_listener') and self.continuous_listener:
                    self.continuous_listener.pause()
                self._set_wakeup_active(True)
                response = "Activated. I'm listening."
                print(f"[LADA] WAKEUP -> ACTIVE")
                if self.voice and self._voice_enabled:
                    def speak_and_resume():
                        self.voice.speak(response)
                        if hasattr(self, 'continuous_listener') and self.continuous_listener:
                            self.continuous_listener.resume()
                    threading.Thread(target=speak_and_resume, daemon=True).start()
            else:
                if hasattr(self, 'continuous_listener') and self.continuous_listener:
                    self.continuous_listener.resume()
            return
            return

        # While ACTIVE, allow explicit turn-off.
        if self._is_turn_off_phrase(normalized):
            if hasattr(self, 'continuous_listener') and self.continuous_listener:
                self.continuous_listener.pause()
            self._set_wakeup_active(False)
            response = "Standing by."
            print(f"[LADA] WAKEUP -> STANDBY")
            if self.voice and self._voice_enabled:
                def speak_and_resume():
                    self.voice.speak(response)
                    if hasattr(self, 'continuous_listener') and self.continuous_listener:
                        self.continuous_listener.resume()
                threading.Thread(target=speak_and_resume, daemon=True).start()
            else:
                if hasattr(self, 'continuous_listener') and self.continuous_listener:
                    self.continuous_listener.resume()
            return

        # Strip wake word prefix from command if present
        clean_cmd = cmd
        for prefix in ['hey lada ', 'hi lada ', 'ok lada ', 'okay lada ', 'lada ']:
            if cmd.lower().startswith(prefix):
                clean_cmd = cmd[len(prefix):].strip()
                break
        if not clean_cmd:
            return

        # Pause listening while processing
        if hasattr(self, 'continuous_listener') and self.continuous_listener:
            self.continuous_listener.pause()

        # Also show command in main chat area for visibility
        QTimer.singleShot(0, lambda c=clean_cmd: self._show_voice_in_chat(c))

        # Check for system commands first (Voice NLU -> JARVIS -> AI)
        try:
            # Check for autonomous tasks first (browser control, multi-step)
            if self._is_agent_task(clean_cmd):
                QTimer.singleShot(0, lambda c=clean_cmd: self._run_agent_task(c))
                if self.voice and self._voice_enabled:
                    threading.Thread(
                        target=lambda: self.voice.speak("Starting autonomous task now."),
                        daemon=True
                    ).start()
                if hasattr(self, 'continuous_listener') and self.continuous_listener:
                    self.continuous_listener.resume()
                return

            handled, response = self._check_system_command(clean_cmd)

            if handled:
                print(f"[LADA] Response: {response}")
                QTimer.singleShot(0, lambda r=response: self._show_voice_response_in_chat(r))
                if self.voice and self._voice_enabled:
                    def speak_and_resume():
                        self.voice.speak(response)
                        if hasattr(self, 'continuous_listener') and self.continuous_listener:
                            self.continuous_listener.resume()
                    threading.Thread(target=speak_and_resume, daemon=True).start()
                else:
                    if hasattr(self, 'continuous_listener') and self.continuous_listener:
                        self.continuous_listener.resume()
            else:
                # Use AI for complex queries
                def ai_query():
                    try:
                        if self.router:
                            selected_model = self.model.currentData() if hasattr(self, 'model') else None
                            if selected_model and selected_model != 'auto':
                                backend = self.router.get_backend_from_name(selected_model)
                            else:
                                backend = None
                            ai_response = self.router.query(clean_cmd, prefer_backend=backend)
                            print(f"[LADA] AI: {ai_response[:100]}...")
                            QTimer.singleShot(0, lambda r=ai_response: self._show_voice_response_in_chat(r))
                            if self.voice and self._voice_enabled:
                                self.voice.speak(ai_response)
                    except Exception as e:
                        print(f"[LADA] AI error: {e}")
                    finally:
                        if hasattr(self, 'continuous_listener') and self.continuous_listener:
                            self.continuous_listener.resume()

                threading.Thread(target=ai_query, daemon=True).start()
        except Exception as e:
            print(f"[LADA] Voice command error: {e}")
            # Always resume listening even on error
            if hasattr(self, 'continuous_listener') and self.continuous_listener:
                self.continuous_listener.resume()

    def _show_voice_in_chat(self, cmd):
        """Show voice command in the main chat area."""
        self.chat.add("user", f"[Voice] {cmd}")
        self.conv.append({"role": "user", "message": f"[Voice] {cmd}"})

    def _show_voice_response_in_chat(self, response):
        """Show voice response in the main chat area."""
        self.chat.add("assistant", response)
        self.conv.append({"role": "assistant", "message": response})
    
    def _check_morning_briefing(self):
        """Give morning briefing on first open of the day"""
        if not hasattr(self, 'weather') or not self.weather:
            return
        
        if not self.weather.should_give_briefing():
            return  # Already gave briefing today
        
        # Get briefing
        briefing = self.weather.get_morning_briefing(self.calendar)
        
        if briefing:
            # Add to chat (but NOT to conv - don't save briefing)
            self.chat.add("assistant", briefing)
            # Don't append to self.conv - briefing should not be saved
            
            # Speak if voice available
            if self.voice:
                def speak():
                    self.voice.speak(briefing)
                threading.Thread(target=speak, daemon=True).start()
            
            # Mark briefing given
            self.weather.mark_briefing_given()
            print("[LADA] ☀️ Morning briefing delivered")

    def _is_agent_task(self, text: str) -> bool:
        """Check if a command needs the CometAgent (long-running autonomous task).
        These need background execution to avoid freezing the UI.
        """
        if not hasattr(self, 'jarvis') or not self.jarvis or not getattr(self.jarvis, 'comet_agent', None):
            return False

        t = text.lower().strip()

        # Explicit autonomous triggers
        if any(x in t for x in ['autonomously', 'automatically do', 'do this for me',
                                 'take over', 'auto complete', 'control my screen',
                                 'control the screen', 'screen control',
                                 'do it for me', 'help me do this',
                                 'do it yourself', 'you do it', 'handle it']):
            return True

        # Multi-step or browser-interaction tasks
        action_indicators = [
            'on google', 'in browser', 'on the browser', 'in chrome',
            'go to ', 'navigate to ', 'open and ', 'go to and ',
            'click on ', 'type in ', 'type into ', 'fill ',
            'log in', 'login', 'sign in', 'sign up',
            'add to cart', 'checkout', 'buy from', 'purchase from',
            'book a ', 'order from', 'order a ',
            ' and then ', ' then click', ' then type', ' then search',
            'find and click', 'search on ', 'find on ',
            'look up on ', 'look for on ',
            'open ', 'launch ', 'start ',
        ]
        has_action = any(x in t for x in action_indicators)

        # Multi-step sequence detection
        has_sequence = any(x in t for x in [
            ' and then ', ' then ', ' after that ', ' followed by '
        ])
        has_website = any(x in t for x in [
            '.com', '.org', '.net', '.io', '.ai',
            'amazon', 'google', 'youtube', 'gmail', 'twitter',
            'facebook', 'instagram', 'linkedin', 'github',
            'flipkart', 'swiggy', 'zomato', 'maps', 'chrome',
            'browser', 'website', 'website', 'web page',
        ])

        # Complex actions (multi-step implies agent)
        if has_action and has_website:
            return True
        if has_sequence and has_website:
            return True
        if has_sequence and has_action:
            return True

        # "search for X on google/browser" pattern
        if 'search' in t and any(x in t for x in ['on google', 'in browser', 'on the browser', 'in chrome', 'on maps']):
            return True

        # "find my X" location / file / data patterns that need screen control
        if any(x in t for x in ['find my location', 'find my address', 'find my ip',
                                  'my location on', 'my address on', 'show my location',
                                  'where am i', 'current location on']):
            return True

        # "open X and do Y" patterns
        if ('open ' in t or 'launch ' in t) and any(a in t for a in [' and ', ' then ', ' to ']):
            return True

        return False

    def _run_agent_task(self, text: str):
        """Run a CometAgent task in a background thread with Comet overlay UI."""
        self.inp.enable(False)
        self.inp.show_stop()
        self.chat.add("assistant", "Starting autonomous task... I'll control the screen now.")
        self._autonomous_event_log = []

        # Show global floating overlay by default; fall back to in-app overlay if unavailable.
        use_floating = hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay is not None
        if use_floating:
            self.floating_comet_overlay.start(text)
            self.comet_overlay.hide()
        else:
            self.comet_overlay.setGeometry(
                self.side.width(), 0,
                self.width() - self.side.width(), self.height()
            )
            self.comet_overlay.start(text)

        # Track the active comet agent for stop/pause
        self._active_comet_agent = None

        def progress_callback(step, max_steps, phase, detail, screenshot_path=None):
            """Thread-safe progress callback - schedules UI update on main thread."""
            QTimer.singleShot(0, lambda s=step, m=max_steps, p=phase, d=detail, ss=screenshot_path:
                self._on_comet_progress(s, m, p, d, ss))

        def on_pause_toggle():
            """Handle pause/resume button from overlay - call agent pause/resume."""
            sender = self.sender()
            paused = False

            if sender is self.comet_overlay:
                paused = self.comet_overlay._is_paused
                if use_floating:
                    self.floating_comet_overlay.set_paused_state(paused, add_log=False)
            elif use_floating and sender is self.floating_comet_overlay:
                paused = self.floating_comet_overlay._is_paused
                self.comet_overlay.set_paused_state(paused, add_log=False)
            else:
                paused = self.comet_overlay._is_paused

            agent = getattr(self, '_active_comet_agent', None)
            if agent:
                if paused:
                    agent.pause()
                else:
                    agent.resume()

        # Connect pause signal (disconnect first to avoid duplicate connections)
        try:
            self.comet_overlay.pause_requested.disconnect()
        except Exception:
            pass
        self.comet_overlay.pause_requested.connect(on_pause_toggle)

        if use_floating:
            try:
                self.floating_comet_overlay.pause_requested.disconnect()
            except Exception:
                pass
            self.floating_comet_overlay.pause_requested.connect(on_pause_toggle)

        def run():
            try:
                agent = self.jarvis.comet_agent
                # Set progress callback
                agent.progress_callback = progress_callback
                self._active_comet_agent = agent

                # Set click effect callback - schedules UI on main thread
                def click_effect(x, y):
                    QTimer.singleShot(0, lambda cx=x, cy=y: self._on_comet_click(cx, cy))
                agent.click_effect_callback = click_effect

                result = agent.execute_task_sync(text, max_steps=30)
                if result.success:
                    response = f"Task completed: {result.message}"
                    success = True
                else:
                    response = f"Task did not fully complete: {result.message}"
                    success = False
            except Exception as e:
                response = f"Autonomous task failed: {str(e)}"
                success = False

            self._active_comet_agent = None
            # Schedule UI update on the main thread
            QTimer.singleShot(0, lambda r=response, s=success: self._on_agent_done(r, s))

        threading.Thread(target=run, daemon=True, name="CometAgent-Task").start()

    def _on_comet_progress(self, step, max_steps, phase, detail, screenshot_path=None):
        """Fan out agent progress updates to visible overlays and local event history."""
        if self.comet_overlay.isVisible():
            self.comet_overlay.update_progress(step, max_steps, phase, detail, screenshot_path)

        if hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay:
            if self.floating_comet_overlay.isVisible():
                self.floating_comet_overlay.update_progress(step, max_steps, phase, detail)

        self._autonomous_event_log.append({
            'time': datetime.now().isoformat(timespec='seconds'),
            'step': int(step),
            'max_steps': int(max_steps),
            'phase': str(phase),
            'detail': str(detail or ''),
        })
        self._autonomous_event_log = self._autonomous_event_log[-200:]

    def _on_comet_click(self, x: int, y: int):
        """Handle click feedback for both ripple effect and floating action stream."""
        self._show_click_effect(x, y)

        if hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay:
            if self.floating_comet_overlay.isVisible():
                self.floating_comet_overlay.log_click(x, y)

        self._autonomous_event_log.append({
            'time': datetime.now().isoformat(timespec='seconds'),
            'step': None,
            'max_steps': None,
            'phase': 'click',
            'detail': f'({x}, {y})',
        })
        self._autonomous_event_log = self._autonomous_event_log[-200:]

    def _stop_comet_task(self):
        """Stop the running Comet agent task or close overlay."""
        if hasattr(self, '_active_comet_agent') and self._active_comet_agent:
            self._active_comet_agent.stop()
            self._active_comet_agent = None
            # Overlay will be closed when _on_agent_done fires
        else:
            # No active agent - just close the overlay
            self.comet_overlay.hide()
            if hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay:
                self.floating_comet_overlay.hide()
            self.inp.enable(True)
            self.inp.hide_stop()

    def _show_click_effect(self, x: int, y: int):
        """Show an on-screen click ripple effect at the given screen coordinates."""
        try:
            effect = ClickEffectOverlay(x, y)
            # Keep a reference so it is not garbage-collected before animation ends
            if not hasattr(self, '_click_effects'):
                self._click_effects = []
            # Prune finished effects
            self._click_effects = [e for e in self._click_effects if not e.isHidden()]
            self._click_effects.append(effect)
        except Exception as e:
            print(f"[LADA] Click effect error: {e}")

    def _on_agent_done(self, response: str, success: bool = True):
        """Handle CometAgent task completion on the main thread."""
        # Update overlay
        if self.comet_overlay.isVisible():
            self.comet_overlay.finish(success, response)
            # Auto-hide overlay after 3 seconds on success, keep visible on failure
            if success:
                QTimer.singleShot(3000, self.comet_overlay.hide)
            # On failure, user clicks CLOSE to dismiss

        if hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay:
            if self.floating_comet_overlay.isVisible():
                self.floating_comet_overlay.finish(success, response)
                if success:
                    QTimer.singleShot(3000, self.floating_comet_overlay.hide)

        self.chat.add("assistant", response)
        self.conv.append({"role": "assistant", "message": response})
        self.inp.enable(True)
        self.inp.hide_stop()
        self._save()

    def _check_system_command(self, text: str) -> tuple:
        """Check if user input is a system command and execute it.
        Uses Voice NLU for fast pattern matching, falls back to JARVIS.
        Returns (handled: bool, response: str)
        """
        t = text.lower().strip()

        # Native-only runtime: OpenClaw-prefixed commands map to native aliases.
        if t.startswith("openclaw"):
            return self._handle_openclaw_alias_command(text)

        # === SYSTEM COMMAND KEYWORDS - always try JARVIS first for these ===
        system_keywords = [
            'volume', 'brightness', 'mute', 'unmute', 'screenshot',
            'bluetooth', 'wifi', 'airplane', 'hotspot', 'nightlight', 'night light',
            'dark mode', 'light mode', 'theme', 'touchpad',
            'battery', 'power plan', 'clipboard', 'recycle bin',
            'dnd', 'do not disturb', 'screen timeout',
            'virtual desktop', 'task view', 'show desktop',
            'lock screen', 'hibernate', 'log off', 'logoff',
            'open notepad', 'open chrome', 'open edge', 'open calculator',
            'open settings', 'open task manager', 'open file explorer',
            'close window', 'minimize', 'maximize', 'fullscreen',
            'alt tab', 'snap window', 'center window', 'always on top',
            'find file', 'search file', 'find document', 'recent files',
            'file manager', 'file explorer', 'locate file', 'where is file',
            'kill process', 'list process', 'startup apps',
            'screen recording', 'start recording', 'stop recording',
            'set timer', 'set alarm', 'set reminder',
            'incognito', 'bookmark', 'zoom in', 'zoom out',
            # Action/task commands - route through JARVIS for execution
            'open ', 'launch ', 'create ', 'make a ', 'make folder', 'make file',
            'new folder', 'new file', 'create folder', 'create file',
            'write a ', 'write to ', 'rename ', 'delete ',
            'move file', 'copy file', 'run ', 'execute ',
            'play ', 'pause ', 'stop ', 'skip ', 'next ',
            'close ', 'quit ', 'exit ',
            'find my location', 'my location', 'show my location', 'where am i',
            # Image generation, code execution, document reading
            'generate image', 'create image', 'draw ', 'imagine ', 'ai image',
            'generate picture', 'make an image', 'generate art',
            'run code', 'execute code', 'run python', 'run javascript', 'run script',
            'read document', 'read pdf', 'summarize document', 'summarize file',
            'chat with document', 'chat with file', 'analyze document',
            'deep research', 'research in depth', 'weather briefing',
            'focus mode', 'export conversation', 'export to pdf',
            # Video generation
            'generate video', 'create video', 'make video', 'ai video',
            'animate ', 'generate animation',
        ]
        is_system_cmd = any(x in t for x in system_keywords)

        # If it looks like a system command, try JARVIS/NLU first
        if is_system_cmd:
            handled, response = self._dispatch_system_command(text)
            if handled:
                return True, response
            if self.voice_nlu:
                handled, response = self.voice_nlu.process(text)
                if handled:
                    return True, response

        # === AI COMMAND AGENT — handles complex commands patterns couldn't ===
        if hasattr(self, 'ai_agent') and self.ai_agent:
            try:
                agent_result = self.ai_agent.try_handle(text)
                if agent_result.handled:
                    logger.info(f"[Agent] Handled: {agent_result.tool_calls_made} tool calls, "
                                f"{agent_result.tier_used} tier, {agent_result.elapsed_ms:.0f}ms")
                    return True, agent_result.response
            except Exception as e:
                logger.warning(f"[Agent] Error: {e}")

        # === DETECT ACTION COMMANDS that need browser/agent control ===
        action_indicators = [
            'on google', 'in browser', 'on the browser', 'in chrome',
            'go to ', 'navigate to ', 'open website',
            'click on ', 'click ', 'type in ', 'type into ', 'fill ',
            'log in', 'login', 'sign in', 'sign up',
            'add to cart', 'checkout', 'buy from', 'purchase from',
            'book a ', 'order from', 'order a ',
            'download from', 'upload to',
            ' and then ', ' then click', ' then type', ' then search',
            'do this for me', 'take over', 'autonomously', 'automatically',
        ]
        is_action_command = any(x in t for x in action_indicators)

        # If user explicitly wants browser, let JARVIS handle it
        if any(x in t for x in ['open browser', 'open google', 'google it', 'in browser', 'in the browser']):
            handled, response = self._dispatch_system_command(text)
            if handled:
                return True, response

        # Action commands always go to JARVIS
        if is_action_command:
            handled, response = self._dispatch_system_command(text)
            if handled:
                return True, response

        # === SEARCH QUERY DETECTION ===
        search_indicators = [
            'search for ', 'what is ', 'who is ', 'when is ', 'where is ', 'why is ', 'how to ',
            'tell me about ', 'what are ', 'how does ', 'explain ', 'define ', 'meaning of ',
            'best ', 'top ', 'latest ', 'news about ', 'price of ', 'weather in ',
            'which is the best', 'compare ', 'difference between', 'how much ',
        ]
        is_search_query = any(t.startswith(x) or f' {x}' in t for x in search_indicators)

        # Only send to AI if it's a search query AND not already handled as system command
        if is_search_query and not is_action_command and not is_system_cmd:
            if self.router and hasattr(self.router, 'web_search_enabled'):
                self.router.web_search_enabled = True
            return False, ""  # Let AI handle it with web context
        
        # === COMET-STYLE SELF-AWARENESS COMMANDS ===
        if any(x in t for x in ['which model', 'what model', 'what ai', 'who are you', 'what are you running']):
            return self._handle_self_awareness(t)

        if any(x in t for x in ['stack health', 'stack status', 'language stack', 'tech stack', 'architecture health', 'language suitability']):
            return self._handle_stack_health()
        
        if any(x in t for x in ['backend status', 'ai status', 'system status', 'what backends']):
            return self._handle_backend_status()
        
        # Calendar commands (priority)
        if self.calendar and any(x in t for x in ['schedule', 'calendar', 'events', 'appointment', 'meeting']):
            return self._handle_calendar_command(t)
        
        # Weather commands (priority)
        if self.weather and any(x in t for x in ['weather', 'temperature', 'forecast', 'outside']):
            weather = self.weather.get_weather()
            response = self.weather.format_weather_speech(weather)
            return True, response
        
        # Try JARVIS first for typed commands (better local execution behavior),
        # then fall back to Voice NLU.
        handled, response = self._dispatch_system_command(text)
        if handled:
            return True, response

        if self.voice_nlu:
            handled, response = self.voice_nlu.process(text)
            if handled:
                return True, response
        
        # Fallback to basic system control if nothing else available
        if not self.sys_ctrl:
            return False, ""

        # Basic volume commands
        if any(x in t for x in ['set volume', 'volume to', 'make volume']):
            import re
            m = re.search(r'(\d+)', t)
            if m:
                level = int(m.group(1))
                result = self.sys_ctrl.set_volume(level)
                if result.get('success'):
                    return True, f"Volume set to {level}%."
                return True, f"Could not set volume: {result.get('error', 'Unknown error')}"

        if 'mute' in t and 'unmute' not in t:
            self.sys_ctrl.set_volume(0)
            return True, "Volume muted."

        if 'unmute' in t:
            self.sys_ctrl.set_volume(50)
            return True, "Volume unmuted and set to 50%."

        if 'max volume' in t or 'full volume' in t:
            self.sys_ctrl.set_volume(100)
            return True, "Volume set to maximum."

        if 'volume up' in t:
            result = self.sys_ctrl.get_volume()
            current = result.get('volume', 50)
            new_level = min(100, current + 10)
            self.sys_ctrl.set_volume(new_level)
            return True, f"Volume increased to {new_level}%."

        if 'volume down' in t:
            result = self.sys_ctrl.get_volume()
            current = result.get('volume', 50)
            new_level = max(0, current - 10)
            self.sys_ctrl.set_volume(new_level)
            return True, f"Volume decreased to {new_level}%."

        # Brightness commands
        if any(x in t for x in ['set brightness', 'brightness to', 'make brightness']):
            import re
            m = re.search(r'(\d+)', t)
            if m:
                level = int(m.group(1))
                result = self.sys_ctrl.set_brightness(level)
                if result.get('success'):
                    return True, f"Brightness set to {level}%."
                return True, f"Could not set brightness: {result.get('error', 'Unknown error')}"

        # Open common apps
        if 'open notepad' in t:
            import subprocess
            subprocess.Popen('notepad.exe')
            return True, "Notepad opened."

        if 'open calculator' in t:
            import subprocess
            subprocess.Popen('calc.exe')
            return True, "Calculator opened."

        if 'open file explorer' in t or 'open explorer' in t:
            import subprocess
            subprocess.Popen('explorer.exe')
            return True, "File Explorer opened."

        if any(x in t for x in ['open settings', 'open system settings']):
            result = self.sys_ctrl.open_settings()
            if result.get('success'):
                return True, "Settings opened."

        if 'open task manager' in t:
            import subprocess
            subprocess.Popen('taskmgr.exe')
            return True, "Task Manager opened."

        # Battery status
        if 'battery' in t:
            result = self.sys_ctrl.get_system_info()
            battery = result.get('battery', {})
            pct = battery.get('percent', 'unknown')
            plugged = battery.get('plugged', False)
            status = "plugged in" if plugged else "on battery"
            return True, f"Battery is at {pct}%, {status}."

        return False, ""
    
    def _handle_calendar_command(self, text: str) -> tuple:
        """Handle calendar-related commands"""
        if not self.calendar:
            return True, "Calendar is not set up. Please add credentials.json from Google Cloud Console to the config folder."
        
        # Get today's events
        if any(x in text for x in ["today's", 'today', 'my schedule', 'my events']):
            events = self.calendar.get_todays_events()
            if events:
                response = self.calendar.format_events_speech(events)
            else:
                response = "You have no events scheduled for today."
            return True, response
        
        # Get upcoming events
        if any(x in text for x in ['upcoming', 'next', 'coming up', 'this week']):
            events = self.calendar.get_upcoming_events(days=7)
            if events:
                response = f"You have {len(events)} events in the next week. " + self.calendar.format_events_speech(events[:5])
            else:
                response = "You have no upcoming events in the next week."
            return True, response
        
        # Add event
        if any(x in text for x in ['add', 'create', 'schedule', 'set up']):
            parsed = self.calendar.parse_event_from_text(text)
            if parsed and parsed.get('summary'):
                success, msg = self.calendar.add_event(
                    summary=parsed['summary'],
                    start_time=parsed.get('start_time'),
                    end_time=parsed.get('end_time'),
                    description=parsed.get('description', '')
                )
                if success:
                    return True, f"Done! I've added '{parsed['summary']}' to your calendar."
                else:
                    return True, f"Could not add event: {msg}"
            return True, "I couldn't understand the event details. Try saying 'Add meeting with John tomorrow at 3 PM'."
        
        # Default: show today's events
        events = self.calendar.get_todays_events()
        if events:
            return True, self.calendar.format_events_speech(events)
        return True, "You have no events scheduled for today."
    
    def _handle_self_awareness(self, text: str) -> tuple:
        """Handle Comet-style self-awareness questions"""
        if not self.router:
            return True, "I'm LADA, your local AI assistant. I'm currently starting up."
        
        current_backend = getattr(self.router, 'current_backend_name', 'Auto')
        status = self.router.get_status()
        available = [v['name'] for k, v in status.items() if v.get('available')]
        
        if 'who are you' in text or 'what are you' in text:
            return True, f"I'm LADA, your Local AI Desktop Assistant. I'm running on your computer with {len(available)} AI backends available. Right now I'm using {current_backend}."
        
        return True, f"I'm currently using {current_backend}. You have {len(available)} backends available: {', '.join(available[:3])}."
    
    def _handle_backend_status(self) -> tuple:
        """Show detailed AI backend status"""
        if not self.router:
            return True, "AI router is not initialized."
        
        status = self.router.get_status()
        lines = ["**AI Backend Status:**", ""]
        total = len(status)
        available_count = 0
        for key, info in status.items():
            icon = "✅" if info.get('available') else "❌"
            name = info.get('name', key)
            rt = info.get('response_time', 'N/A')
            if info.get('available'):
                available_count += 1
            lines.append(f"{icon} {name}: {rt}")

        if total == 0:
            lines.append("⚠️ No providers loaded. Check models.json and provider initialization.")
            return True, "\n".join(lines)

        lines.extend(["", f"Ready backends: {available_count}/{total}"])

        if available_count == 0:
            health = self._collect_runtime_health()
            missing_keys = health.get("missing_keys", [])
            if missing_keys:
                preview = ", ".join(missing_keys[:3])
                if len(missing_keys) > 3:
                    preview += ", ..."
                lines.append(f"Missing API keys: {preview}")
            else:
                lines.append("No backend is currently ready. Check local model services and provider settings.")
        
        return True, "\n".join(lines)

    def _handle_stack_health(self) -> tuple:
        """Return a concise runtime stack health report and language-fit guidance."""
        lines = ["**LADA Stack Health:**", ""]

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        lines.append(f"✅ Python runtime: {py_ver} (core desktop/orchestration)")

        if self.router:
            try:
                status = self.router.get_status()
                total = len(status)
                available = sum(1 for info in status.values() if info.get('available'))
                lines.append(f"✅ AI provider layer: {available}/{total} backends available")
            except Exception as e:
                lines.append(f"⚠️ AI provider layer: status unavailable ({e})")
        else:
            lines.append("⚠️ AI provider layer: router not initialized yet")

        frontend_pkg = Path("frontend/package.json")
        if frontend_pkg.exists():
            try:
                pkg = json.loads(frontend_pkg.read_text(encoding="utf-8"))
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                next_v = deps.get("next", "unknown")
                ts_v = dev_deps.get("typescript", "unknown")
                lines.append(f"✅ Web stack: Next.js {next_v}, TypeScript {ts_v}, Tailwind CSS")
            except Exception as e:
                lines.append(f"⚠️ Web stack: could not read package metadata ({e})")
        else:
            lines.append("⚠️ Web stack: frontend/package.json not found")

        lines.extend([
            "",
            "**Language fit recommendation:**",
            "- Keep Python as the core for voice, system automation, and agent orchestration.",
            "- Keep TypeScript + CSS for web/frontend surfaces.",
            "- Avoid full rewrites now; prioritize capability parity and reliability.",
        ])

        return True, "\n".join(lines)

    def _build(self):
        self.setWindowTitle("LADA AI")
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)
        self.setStyleSheet(f"background: {BG_SIDE};")
        
        # Set app icon - use new assets folder
        from PyQt5.QtGui import QIcon
        icon_path = Path("assets/lada_logo.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            # Try PNG as fallback
            icon_png = Path("assets/lada_logo.png")
            if icon_png.exists():
                self.setWindowIcon(QIcon(str(icon_png)))
            else:
                # Try old config path
                old_icon = Path("config/lada_icon.ico")
                if old_icon.exists():
                    self.setWindowIcon(QIcon(str(old_icon)))
                else:
                    self.setWindowIcon(self.style().standardIcon(self.style().SP_ComputerIcon))

        cw = QWidget()
        self.setCentralWidget(cw)
        main = QHBoxLayout(cw)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Sidebar
        self.side = Sidebar()
        # Expose sidebar buttons as MainWindow properties for backward compat
        self.session_btn = self.side._session_btn
        self.cost_btn = self.side._cost_btn
        self.canvas_btn = self.side._canvas_btn
        main.addWidget(self.side)

        # Content
        content = QFrame()
        content.setStyleSheet(f"background: {BG_MAIN};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Header - clean, minimal (44px)
        hdr = QFrame()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet(f"background: {BG_MAIN}; border-bottom: 1px solid {BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(8)

        self._hdr_sidebar_btn = QPushButton("\u2261")
        self._hdr_sidebar_btn.setFixedSize(30, 30)
        self._hdr_sidebar_btn.setCursor(Qt.PointingHandCursor)
        self._hdr_sidebar_btn.setToolTip("Toggle sidebar (Ctrl+B)")
        self._hdr_sidebar_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: 1px solid transparent; border-radius: 15px;
                font-size: 15px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; border-color: {BORDER}; }}
        """)
        self._hdr_sidebar_btn.clicked.connect(self._toggle_sidebar_from_header)
        hl.addWidget(self._hdr_sidebar_btn)

        # Left: LADA text logo
        hdr_logo = QLabel("LADA")
        hdr_logo.setFont(QFont(FONT_HEADING, 14, QFont.Bold))
        hdr_logo.setStyleSheet(f"color: {TEXT};")
        hl.addWidget(hdr_logo)

        # Visible active-model pill, similar to modern chat apps.
        self._active_model_label = QLabel("Model: Auto")
        self._active_model_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                background: rgba(26,36,49,220);
                border: 1px solid {BORDER};
                border-radius: 12px;
                font-size: 11px;
                padding: 3px 10px;
            }}
        """)
        hl.addWidget(self._active_model_label)

        hl.addStretch()

        # System status indicators
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        hl.addWidget(self._status_label)
        # Update status every 30 seconds
        self._header_timer = QTimer(self)
        self._header_timer.timeout.connect(self._update_header_status)
        self._header_timer.start(30000)
        QTimer.singleShot(500, self._update_header_status)

        # Voice always-on toggle button
        self.voice_toggle_btn = QPushButton("Voice ON")
        self.voice_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.voice_toggle_btn.setFixedHeight(26)
        self.voice_toggle_btn.setMinimumWidth(80)
        self.voice_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 13px; font-size: 11px;
                padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {ACCENT_DARK}; }}
        """)
        self.voice_toggle_btn.setToolTip("Toggle always-on voice (or say 'Hey LADA')")
        self.voice_toggle_btn.clicked.connect(self._toggle_always_on_voice)
        hl.addWidget(self.voice_toggle_btn)

        # Voice button
        self.voice_btn = QPushButton("Mic")
        self.voice_btn.setFixedSize(32, 32)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setToolTip("Voice Mode (Ctrl+M)")
        self.voice_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM};
                border: 1px solid {BORDER}; border-radius: 16px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; border-color: {TEXT_DIM}; }}
        """)
        hl.addWidget(self.voice_btn)

        cl.addWidget(hdr)

        # Chat
        self.chat = ChatArea()
        cl.addWidget(self.chat, 1)

        # Input
        self.inp = InputBar()
        cl.addWidget(self.inp)

        # Wire model selector: alias self.model to InputBar's model_selector
        self.model = self.inp.model_selector
        self.model.currentIndexChanged.connect(self._on_model_selector_changed)
        self._load_models()
        self._update_header_model_label()

        main.addWidget(content, 1)

        # Voice overlay
        self.vlay = VoiceOverlay(self)
        self.vlay.hide()

        # Comet-style screen control overlay
        self.comet_overlay = CometOverlay(self)
        self.comet_overlay.hide()
        self.comet_overlay.stop_requested.connect(self._stop_comet_task)

        # Global floating overlay (outside app window) for autonomous actions
        self.floating_comet_overlay = AutonomousActionOverlay()
        self.floating_comet_overlay.hide()
        self.floating_comet_overlay.stop_requested.connect(self._stop_comet_task)

        # Welcome message with time-based greeting
        if JARVIS_OK and LadaPersonality:
            greeting = LadaPersonality.get_time_greeting()
        else:
            greeting = "Hello! I'm LADA. How can I help you?"
        self.chat.add("assistant", greeting)
        
        # Check for proactive alerts (battery low, etc.)
        if self.jarvis:
            alerts = self.jarvis.get_proactive_alerts()
            if alerts:
                self.chat.add("assistant", alerts)

        # Status bar
        self.statusbar = QStatusBar()
        self.statusbar.setStyleSheet(f"background: {BG_SURFACE}; color: {TEXT_DIM}; font-size: 10px; padding: 2px 8px; font-family: '{FONT_FAMILY}';")
        self.setStatusBar(self.statusbar)
        self._update_status()

        # Setup keyboard shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts - Comet-style"""
        # Ctrl+N: New chat
        QShortcut(QKeySequence("Ctrl+N"), self, self._new)
        # Ctrl+B: Toggle sidebar
        QShortcut(QKeySequence("Ctrl+B"), self, self._toggle_sidebar_from_header)
        # Ctrl+M: Toggle voice (alternative)
        QShortcut(QKeySequence("Ctrl+M"), self, self._toggle_voice)
        # Shift+Alt+V: Voice mode (Comet-style)
        QShortcut(QKeySequence("Shift+Alt+V"), self, self._toggle_voice)
        # Ctrl+,: Open settings
        QShortcut(QKeySequence("Ctrl+,"), self, self._open_settings)
        # Ctrl+J: Open Assistant (Comet-style)
        QShortcut(QKeySequence("Ctrl+J"), self, lambda: self.inp.inp.setFocus())
        # Ctrl+K: Command palette feel - focus input
        QShortcut(QKeySequence("Ctrl+K"), self, lambda: self.inp.inp.setFocus())
        
        # Setup GLOBAL hotkeys (work even when app is minimized)
        self._setup_global_hotkeys()
        
        # Setup system tray for background mode
        self._setup_tray()
    
    def _setup_global_hotkeys(self):
        """Setup global keyboard shortcuts that work system-wide"""
        if not HOTKEY_OK or not kb_global:
            print("[LADA] Global hotkeys disabled - keyboard module not available")
            return
        
        try:
            # Ctrl+Shift+L: Show/Focus LADA window (primary activation)
            kb_global.add_hotkey('ctrl+shift+l', self._global_show_lada, suppress=False)
            
            # Ctrl+Shift+V: Start voice input globally
            kb_global.add_hotkey('ctrl+shift+v', self._global_voice_input, suppress=False)
            
            # Ctrl+Shift+Space: Quick command (focus input)
            kb_global.add_hotkey('ctrl+shift+space', self._global_quick_command, suppress=False)
            
            # Ctrl+Alt+L: Toggle listening mode
            kb_global.add_hotkey('ctrl+alt+l', self._global_toggle_listening, suppress=False)
            
            print("[LADA] Global hotkeys registered:")
            print("       Ctrl+Shift+L: Show LADA")
            print("       Ctrl+Shift+V: Voice input")
            print("       Ctrl+Shift+Space: Quick command")
            print("       Ctrl+Alt+L: Toggle listening")
            
        except Exception as e:
            print(f"[LADA] Could not register global hotkeys: {e}")
            print("       Try running as Administrator for global hotkey support")
    
    def _global_show_lada(self):
        """Global hotkey handler to show/focus LADA window"""
        QTimer.singleShot(0, self._show_from_tray)
    
    def _global_voice_input(self):
        """Global hotkey handler to start voice input"""
        QTimer.singleShot(0, lambda: (
            self._show_from_tray(),
            QTimer.singleShot(100, self._toggle_voice)
        ))
    
    def _global_quick_command(self):
        """Global hotkey handler for quick command input"""
        QTimer.singleShot(0, lambda: (
            self._show_from_tray(),
            QTimer.singleShot(100, lambda: self.inp.inp.setFocus())
        ))
    
    def _global_toggle_listening(self):
        """Global hotkey handler to toggle continuous listening"""
        if hasattr(self, 'continuous_listener') and self.continuous_listener:
            if self._wakeup_active:
                self._set_wakeup_active(False)
                QTimer.singleShot(0, lambda: self.statusbar.showMessage("🔇 Listening paused", 3000))
            else:
                self._set_wakeup_active(True)
                QTimer.singleShot(0, lambda: self.statusbar.showMessage("🎤 Listening active", 3000))
    
    def _setup_tray(self):
        """Setup system tray icon for background mode"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # Set tray icon - use new assets folder
        icon_path = Path("assets/lada_logo.ico")
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            icon_png = Path("assets/lada_logo.png")
            if icon_png.exists():
                self.tray_icon.setIcon(QIcon(str(icon_png)))
            else:
                # Try old config path
                old_icon = Path("config/lada_icon.ico")
                if old_icon.exists():
                    self.tray_icon.setIcon(QIcon(str(old_icon)))
                else:
                    self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        
        # Create tray menu
        tray_menu = QMenu()
        tray_menu.setStyleSheet(f"""
            QMenu {{
                background: {BG_SURFACE}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 10px;
                padding: 6px; font-family: '{FONT_FAMILY}';
            }}
            QMenu::item {{ padding: 8px 20px; border-radius: 6px; }}
            QMenu::item:selected {{ background: {BG_HOVER}; }}
        """)
        
        show_action = tray_menu.addAction("🖥️ Show LADA")
        show_action.triggered.connect(self._show_from_tray)
        
        tray_menu.addSeparator()
        
        wake_action = tray_menu.addAction("🎤 Wake Word: ON" if WAKE_OK else "🎤 Wake Word: OFF")
        wake_action.setEnabled(False)
        
        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("❌ Quit LADA")
        quit_action.triggered.connect(self._quit_app)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.setToolTip("LADA AI - Say 'LADA' to activate")
        self.tray_icon.show()
        
        print("[LADA] System tray active - close window to minimize, wake word stays active")
    
    def _show_from_tray(self):
        """Restore window from system tray"""
        self.showNormal()
        self.activateWindow()
        self.raise_()
    
    def _tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()
    
    def _quit_app(self):
        """Actually quit the application"""
        self._save()
        self._close_voice()

        # Stop standalone command bus/orchestrator if enabled
        self._stop_standalone_orchestrator()
        
        # Stop wake word detection
        if hasattr(self, 'wake_detector') and self.wake_detector:
            try:
                self.wake_detector.stop()
            except:
                pass
        
        # Stop Alexa background services
        if hasattr(self, 'alexa_processes'):
            for proc in self.alexa_processes:
                try:
                    proc.terminate()
                except:
                    pass
            print("[LADA] Alexa services stopped")

        # Stop proactive agent
        if hasattr(self, '_proactive_agent') and self._proactive_agent:
            try:
                self._proactive_agent.stop()
                print("[LADA] Proactive Agent stopped")
            except:
                pass

        # Hide tray icon
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()

        if hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay:
            self.floating_comet_overlay.hide()
            self.floating_comet_overlay.close()

        QApplication.quit()
    
    def _check_face_auth(self):
        """Check face recognition using in-app overlay (no OpenCV popup)"""
        if not hasattr(self, 'face_auth') or not self.face_auth:
            return
        
        # Check if face unlock is enabled in settings
        try:
            import json
            settings_file = Path("config/app_settings.json")
            if settings_file.exists():
                saved = json.loads(settings_file.read_text())
                if not saved.get('face_unlock_enabled', False):
                    return  # Face unlock disabled, skip
            else:
                return  # No settings, skip face auth
        except:
            return  # Error reading settings, skip
        
        try:
            # Create and show in-app face auth overlay
            self.face_overlay = FaceAuthOverlay(self, self.face_auth)
            self.face_overlay.setGeometry(0, 0, self.width(), self.height())
            self.face_overlay.auth_complete.connect(self._on_face_auth_complete)
            self.face_overlay.show()
            self.face_overlay.raise_()
            self.face_overlay.start()
        except Exception as e:
            print(f"[LADA] Face auth error: {e}")
    
    def _on_face_auth_complete(self, success: bool, message: str):
        """Handle face auth completion"""
        if hasattr(self, 'face_overlay'):
            self.face_overlay.hide()
            self.face_overlay.deleteLater()
        
        if success and "Welcome" in message:
            self.chat.add("assistant", f"🔓 {message}")
        elif success and "enrolled" in message.lower():
            self.chat.add("assistant", f"🔐 {message}")
        # Don't show message if skipped
        
        # Escape: Close voice overlay
        QShortcut(QKeySequence("Escape"), self, self._close_voice)

    def _update_status(self):
        """Update status bar with backend info"""
        prefix = ""
        if hasattr(self, '_wakeup_active') and WAKE_OK and hasattr(self, 'continuous_listener') and self.continuous_listener:
            prefix = "ACTIVE" if self._wakeup_active else "STANDBY"

        if self.router:
            if hasattr(self.router, '_ensure_backends_checked'):
                try:
                    self.router._ensure_backends_checked()
                except Exception:
                    pass
            status = self.router.get_status()
            parts = []
            for k, v in status.items():
                if v.get('available'):
                    parts.append(v.get('name', k))
            if parts:
                base = " | ".join(parts)
            else:
                health = self._collect_runtime_health()
                missing_keys = health.get("missing_keys", [])
                if missing_keys:
                    preview = ", ".join(missing_keys[:2])
                    base = f"No backends available - add API keys ({preview})"
                else:
                    base = "No backends available - check provider services"
            self.statusbar.showMessage(f"{prefix}  |  {base}" if prefix else base)
        else:
            self.statusbar.showMessage(f"{prefix}  |  AI Router not initialized" if prefix else "AI Router not initialized")

    def _update_header_status(self):
        """Update header status bar with battery, time, and connection info."""
        parts = []
        try:
            if self.router:
                status = self.router.get_status()
                total = len(status)
                available = sum(1 for v in status.values() if v.get('available'))
                if total > 0:
                    parts.append(f"AI: {available}/{total} ready")
        except Exception:
            pass
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt:
                pct = int(batt.percent)
                charging = " +" if batt.power_plugged else ""
                parts.append(f"Battery: {pct}%{charging}")
        except:
            pass
        try:
            from datetime import datetime
            parts.append(datetime.now().strftime("%I:%M %p"))
        except:
            pass
        if parts:
            self._status_label.setText("  |  ".join(parts))
        else:
            self._status_label.setText("")

    def _get_selected_model_label(self):
        """Return a clean display label for the currently selected model."""
        if not hasattr(self, 'model'):
            return "Auto"

        idx = self.model.currentIndex()
        if idx < 0:
            return "Auto"

        model_data = self.model.itemData(idx)
        model_text = (self.model.itemText(idx) or "").strip()

        if isinstance(model_data, str) and model_data == "auto":
            return "Auto"
        if not model_text or model_text.startswith("──"):
            return "Auto"
        return model_text

    def _update_header_model_label(self):
        """Sync the header model pill with the input model selector."""
        if hasattr(self, '_active_model_label'):
            self._active_model_label.setText(f"Model: {self._get_selected_model_label()}")

    def _open_settings(self):
        """Open settings dialog"""
        dlg = SettingsDialog(self, self.router, self.voice)
        if dlg.exec_():
            settings = dlg.get_settings()
            self._apply_settings(settings)
    
    def _export_conversation(self):
        """Export current conversation to file"""
        if not self.conv:
            QMessageBox.information(self, "Export", "No conversation to export.")
            return
        
        # Show format selection dialog
        from PyQt5.QtWidgets import QInputDialog
        formats = ["Markdown (.md)", "JSON (.json)", "Text (.txt)"]
        if EXPORT_OK and ExportManager:
            formats.insert(0, "PDF (.pdf)")
            formats.insert(2, "Word (.docx)")
        
        format_choice, ok = QInputDialog.getItem(
            self, "Export Format", "Choose export format:", formats, 0, False
        )
        
        if not ok:
            return
        
        # Determine file extension
        if "PDF" in format_choice:
            ext, fmt = ".pdf", "pdf"
        elif "Word" in format_choice:
            ext, fmt = ".docx", "docx"
        elif "Markdown" in format_choice:
            ext, fmt = ".md", "markdown"
        elif "JSON" in format_choice:
            ext, fmt = ".json", "json"
        else:
            ext, fmt = ".txt", "text"
        
        # Get save path
        default_name = f"LADA_Chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Conversation", default_name, f"*{ext}"
        )
        
        if not save_path:
            return
        
        try:
            if EXPORT_OK and ExportManager and fmt in ["pdf", "docx", "markdown", "json"]:
                # Use ExportManager for rich exports
                exporter = ExportManager()
                # Convert conv to Conversation object
                from modules.chat_manager import Conversation, Message
                conv_obj = Conversation(
                    id=datetime.now().strftime('%Y%m%d_%H%M%S'),
                    title=self.conv[0].get('message', 'Chat')[:30] if self.conv else 'Chat'
                )
                for msg in self.conv:
                    conv_obj.messages.append(Message(
                        role=msg.get('role', 'user'),
                        content=msg.get('message', '')
                    ))
                exporter.export_conversation(conv_obj, fmt, Path(save_path).parent)
                # Rename to user's chosen path
                import shutil
                exported_file = list(Path(save_path).parent.glob(f"*{ext}"))[-1]
                if exported_file.name != Path(save_path).name:
                    shutil.move(str(exported_file), save_path)
            else:
                # Simple text/markdown/json export
                with open(save_path, 'w', encoding='utf-8') as f:
                    if fmt == "json":
                        json.dump(self.conv, f, indent=2, ensure_ascii=False)
                    elif fmt == "markdown":
                        f.write(f"# LADA Conversation\n\n")
                        f.write(f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n---\n\n")
                        for msg in self.conv:
                            role = "**You:**" if msg.get('role') == 'user' else "**LADA:**"
                            f.write(f"{role}\n\n{msg.get('message', '')}\n\n---\n\n")
                    else:
                        f.write(f"LADA Conversation\nExported: {datetime.now()}\n\n")
                        for msg in self.conv:
                            role = "You:" if msg.get('role') == 'user' else "LADA:"
                            f.write(f"{role}\n{msg.get('message', '')}\n\n")
            
            QMessageBox.information(self, "Export Complete", f"Conversation saved to:\n{save_path}")
            
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export: {e}")
    
    def _apply_settings(self, settings: dict):
        """Apply settings from dialog"""
        if not settings:
            return
        
        # Apply privacy mode
        if hasattr(self, 'jarvis') and self.jarvis:
            self.jarvis.set_privacy_mode(settings.get('privacy_mode', False))
        
        # Apply voice settings
        if self.voice:
            if hasattr(self.voice, 'voice_speed'):
                self.voice.voice_speed = settings.get('voice_speed', 175)
        
        # Apply font size to chat messages
        new_font_size = settings.get('font_size', 18)
        if new_font_size != RichTextLabel.font_size:
            RichTextLabel.font_size = new_font_size
            # Update markdown renderer font size too
            if _md_renderer:
                _md_renderer.set_font_size(new_font_size)
        
        # Apply browser search preference
        self.browser_search_mode = settings.get('browser_search', False)

        # Apply personality mode immediately so tone changes at runtime.
        personality_mode_index = int(settings.get('personality_mode', 2))
        personality_mode_name = self._personality_mode_from_index(personality_mode_index)
        if JARVIS_OK and LadaPersonality:
            try:
                LadaPersonality.set_mode(personality_mode_name)
            except Exception as e:
                logger.warning(f"[LADA] Could not set personality mode '{personality_mode_name}': {e}")
        
        # Store settings for later
        self.current_settings = settings
        
        # Show confirmation
        mode = "🔒 Private" if settings.get('privacy_mode') else "🌐 Public"
        self.statusbar.showMessage(
            f"Settings applied. Mode: {mode} | Personality: {personality_mode_name.title()} | Font: {new_font_size}px",
            3000,
        )

    def _load_models(self):
        self.model.clear()
        self.model.addItem("Auto (Best Available)", "auto")
        if not self.router:
            print("[LADA] Router not available - no models to display")
            self._update_header_model_label()
            return

        normalized = []
        if hasattr(self.router, 'get_all_available_models'):
            try:
                for model in (self.router.get_all_available_models() or []):
                    model_id = str(model.get('id', '')).strip()
                    if not model_id:
                        continue
                    normalized.append({
                        'id': model_id,
                        'provider': str(model.get('provider', '')).strip(),
                        'provider_name': str(model.get('provider_name', model.get('provider', 'Provider'))).strip(),
                        'name': str(model.get('name', model_id)).replace(' (offline)', '').strip(),
                        'available': bool(model.get('available', True)),
                    })
            except Exception as e:
                print(f"[LADA] get_all_available_models error: {e}")

        # Fallback for cases where registry entries are empty but provider dropdown exists.
        if not normalized and hasattr(self.router, 'get_provider_dropdown_items'):
            try:
                for item in (self.router.get_provider_dropdown_items() or []):
                    model_id = str(item.get('value', '')).strip()
                    if not model_id or model_id == 'auto':
                        continue

                    label = str(item.get('label', model_id)).strip()
                    is_available = bool(item.get('available', True)) and '(offline)' not in label.lower()
                    normalized.append({
                        'id': model_id,
                        'provider': str(item.get('provider', 'lada')).strip(),
                        'provider_name': str(item.get('provider', 'lada')).strip(),
                        'name': label.replace(' (offline)', '').strip(),
                        'available': is_available,
                    })
            except Exception as e:
                print(f"[LADA] get_provider_dropdown_items error: {e}")

        if not normalized:
            self.model.addItem("No models available", "")
            idx = self.model.count() - 1
            self.model.setItemData(idx, 0, Qt.UserRole - 1)
            print("[LADA] Model dropdown: no models found")
            self.model.setCurrentIndex(0)
            self._update_header_model_label()
            return

        current_provider = None
        added = 0
        any_available = any(m.get('available', False) for m in normalized)

        for model in normalized:
            # If at least one model is available, suppress offline rows to reduce confusion.
            if any_available and not model.get('available', False):
                continue

            provider = model.get('provider', '')
            if provider != current_provider:
                current_provider = provider
                provider_label = model.get('provider_name', provider) or provider or 'Provider'
                sep = f"\u2500\u2500 {provider_label} \u2500\u2500"
                self.model.addItem(sep, "")
                idx = self.model.count() - 1
                self.model.setItemData(idx, 0, Qt.UserRole - 1)

            display_name = model.get('name', model.get('id', ''))
            if not model.get('available', False) and '(offline)' not in display_name.lower():
                display_name = f"{display_name} (offline)"

            self.model.addItem(f"  {display_name}", model.get('id', ''))
            idx = self.model.count() - 1
            if not model.get('available', False):
                self.model.setItemData(idx, 0, Qt.UserRole - 1)
            added += 1

        print(f"[LADA] Model dropdown: {added} models loaded")
        self.model.setCurrentIndex(0)
        self._update_header_model_label()

    def _on_model_selector_changed(self, index):
        """Handle model selector change."""
        if not hasattr(self, 'model'):
            return

        # Skip provider separator rows if selected accidentally.
        text = (self.model.itemText(index) or "").strip()
        data = self.model.itemData(index)
        if text.startswith("──") or not isinstance(data, str) or not data or '(offline)' in text.lower():
            for i in range(index + 1, self.model.count()):
                next_data = self.model.itemData(i)
                next_text = (self.model.itemText(i) or "").strip().lower()
                if isinstance(next_data, str) and next_data and '(offline)' not in next_text:
                    self.model.setCurrentIndex(i)
                    return
            self.model.setCurrentIndex(0)
            return

        self._update_header_model_label()

    def _wire(self):
        self.side.new_chat.connect(self._new)
        self.side.load_chat.connect(self._load)
        self.side.load_voice_chat.connect(self._load_voice_session)
        self.side.collapse_toggled.connect(self._on_sidebar_collapse_changed)
        self.side.open_settings.connect(self._open_settings)  # Settings from sidebar
        self.side.export_chat.connect(self._export_conversation)  # Export from sidebar
        self.side.open_session.connect(self._open_session_picker)  # Session from sidebar
        self.side.open_cost.connect(self._show_cost_dialog)  # Cost from sidebar
        self.side.open_canvas.connect(self._open_canvas)  # Canvas from sidebar
        self.inp.send.connect(self._send)
        self.voice_btn.clicked.connect(self._toggle_voice)
        self.inp.stop_btn.clicked.connect(self._stop_generation)  # Stop button
        self.vlay.closed.connect(self._close_voice)
        self.vlay.mic.clicked.connect(self._toggle_listen)
        self.chat.suggestion_clicked.connect(self._on_suggestion_chip)
        self.chat.copy_clicked.connect(self._on_chat_copy)
        self.chat.regenerate_clicked.connect(self._on_chat_regenerate)
        self.chat.feedback_clicked.connect(self._on_chat_feedback)

        self._on_sidebar_collapse_changed(self.side.is_collapsed())
        QTimer.singleShot(0, self._apply_responsive_sidebar)

    def _toggle_sidebar_from_header(self):
        if hasattr(self, 'side') and self.side:
            self.side.set_collapsed(not self.side.is_collapsed(), emit_signal=True)

    def _on_sidebar_collapse_changed(self, collapsed: bool):
        if hasattr(self, '_hdr_sidebar_btn') and self._hdr_sidebar_btn:
            self._hdr_sidebar_btn.setText(">" if collapsed else "<")
            self._hdr_sidebar_btn.setToolTip(
                "Expand sidebar (Ctrl+B)" if collapsed else "Collapse sidebar (Ctrl+B)"
            )

        if not self._sidebar_responsive_adjusting:
            self._sidebar_auto_collapsed = False

        self._apply_header_compact_mode()
        self._update_overlay_geometry()

    def _apply_responsive_sidebar(self):
        if not hasattr(self, 'side') or not self.side:
            return

        win_width = self.width()
        collapse_threshold = 1040
        expand_threshold = 1260

        if win_width <= collapse_threshold and not self.side.is_collapsed():
            self._sidebar_responsive_adjusting = True
            self.side.set_collapsed(True, emit_signal=True)
            self._sidebar_responsive_adjusting = False
            self._sidebar_auto_collapsed = True
        elif (
            win_width >= expand_threshold
            and self._sidebar_auto_collapsed
            and self.side.is_collapsed()
        ):
            self._sidebar_responsive_adjusting = True
            self.side.set_collapsed(False, emit_signal=True)
            self._sidebar_responsive_adjusting = False
            self._sidebar_auto_collapsed = False

    def _update_overlay_geometry(self):
        if not hasattr(self, 'side') or not self.side:
            return

        content_x = self.side.width()
        content_w = max(1, self.width() - content_x)

        if hasattr(self, 'vlay') and self.vlay:
            self.vlay.setGeometry(content_x, 0, content_w, self.height())

        if hasattr(self, 'comet_overlay') and self.comet_overlay:
            self.comet_overlay.setGeometry(content_x, 0, content_w, self.height())

    def _apply_header_compact_mode(self):
        win_width = self.width()

        show_model_pill = win_width >= 980
        show_status_line = win_width >= 1180

        if hasattr(self, '_active_model_label') and self._active_model_label:
            self._active_model_label.setVisible(show_model_pill)

        if hasattr(self, '_status_label') and self._status_label:
            self._status_label.setVisible(show_status_line)

    def _on_chat_copy(self, text: str):
        """Handle copy action from chat message toolbar."""
        self.statusbar.showMessage("Copied response to clipboard", 1800)

    def _on_chat_regenerate(self):
        """Regenerate based on the latest user message."""
        if getattr(self, 'ai_worker', None) and self.ai_worker.isRunning():
            self.statusbar.showMessage("Already generating a response...", 2000)
            return

        last_user = None
        for msg in reversed(self.conv):
            if msg.get('role') == 'user':
                candidate = (msg.get('message') or '').strip()
                if candidate and not candidate.startswith('[Voice]'):
                    last_user = candidate
                    break

        if not last_user:
            self.statusbar.showMessage("No recent user message found to regenerate", 2500)
            return

        self.statusbar.showMessage("Regenerating response...", 2000)
        self._send(last_user, files=[])

    def _on_chat_feedback(self, feedback: str):
        """Handle feedback action from chat message toolbar."""
        label = "Thanks for the feedback" if feedback == 'up' else "Got it — I'll improve"
        self.statusbar.showMessage(label, 2000)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_responsive_sidebar()
        self._apply_header_compact_mode()
        self._update_overlay_geometry()

    def _new(self):
        self._save()
        self.conv = []
        self.conv_file = None
        self.chat.clear_all()
        self.chat.add("assistant", "Hello! I'm LADA. How can I help you?")
        self.side.refresh()

    def _load(self, path):
        self._save()
        try:
            self.conv = json.loads(Path(path).read_text(encoding='utf-8'))
            self.conv_file = path
            self.chat.clear_all()
            for m in self.conv:
                self.chat.add(m['role'], m['message'])
        except:
            pass
    
    def _load_voice_session(self, path):
        """Load a voice session for viewing"""
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            self.chat.clear_all()
            self.chat.add("assistant", "🎤 Voice Session History:")
            for m in data:
                self.chat.add(m['role'], m['message'])
        except:
            pass

    def _save(self):
        if not self.conv:
            return
        try:
            p = self.conv_file or f"data/conversations/{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
            Path(p).write_text(json.dumps(self.conv, indent=2, ensure_ascii=False), encoding='utf-8')
        except:
            pass
        # Auto-save to named session file if one is active
        try:
            current_name = getattr(self, '_current_session_name', None)
            if current_name:
                session_path = Path('data/sessions') / f'{current_name}.json'
                session_path.parent.mkdir(parents=True, exist_ok=True)
                session_data = {
                    'session_name': current_name,
                    'updated_at': datetime.now().isoformat(),
                    'messages': self.conv,
                }
                session_path.write_text(
                    json.dumps(session_data, indent=2, ensure_ascii=False), encoding='utf-8'
                )
        except Exception:
            pass

    def _on_suggestion_chip(self, cmd):
        """Handle suggestion chip click - send it as a message."""
        self._send(cmd, [])

    def _send(self, text, files):
        if not text and not files:
            return
        disp = text
        if files:
            disp = f"[{', '.join(f['name'] for f in files)}]\n{text}" if text else f"[{', '.join(f['name'] for f in files)}]"
        self.chat.add("user", disp)
        self.conv.append({"role": "user", "message": disp})

        # Check if this is a long-running autonomous/agent task
        # If so, run it in a background thread to avoid UI freeze
        if self._is_agent_task(text):
            self._run_agent_task(text)
            return

        # Check for system commands first
        handled, response = self._check_system_command(text)
        if handled:
            self.chat.add("assistant", response)
            self.conv.append({"role": "assistant", "message": response})
            if self.vlay.isVisible() and self.voice:
                self._set_v(VState.SPEAK)
                self.vlay.set_text(response)
                def speak():
                    self.voice.speak(response)
                    if self.vlay.isVisible():
                        QTimer.singleShot(200, self._listen)
                    else:
                        self._set_v(VState.IDLE)
                threading.Thread(target=speak, daemon=True).start()
            return
        
        # LADA v7.0: Check for agent intents (flight, hotel, restaurant, email, calendar, product)
        if not files:
            agent_type, params = self._detect_agent_intent(text)
            if agent_type:
                if agent_type == 'flight' and AGENTS_OK and self.flight_agent:
                    self._handle_flight_agent(params)
                    return
                elif agent_type == 'product' and AGENTS_OK and self.product_agent:
                    self._handle_product_agent(params)
                    return
                elif agent_type == 'hotel':
                    self._handle_hotel_agent(params)
                    return
                elif agent_type == 'restaurant':
                    self._handle_restaurant_agent(params)
                    return
                elif agent_type == 'email':
                    self._handle_email_agent(params)
                    return
                elif agent_type == 'calendar':
                    self._handle_calendar_agent(params)
                    return
        
        self.inp.enable(False)
        self.inp.show_stop()  # Show stop button during generation

        # Add streaming placeholder (typing indicator)
        self.chat.add_streaming_placeholder()
        
        # Get selected model from dropdown (use itemData for Phase 2 model ID)
        selected_model = None
        if hasattr(self, 'model'):
            model_data = self.model.currentData()
            if model_data and model_data != 'auto':
                selected_model = model_data  # Phase 2 model ID (e.g. "llama-3.3-70b-versatile")
            elif self.model.currentText() and 'auto' not in self.model.currentText().lower():
                selected_model = self.model.currentText()  # Legacy name fallback
        
        # Check if web search is enabled
        use_web_search = self.inp.is_web_search_enabled() if hasattr(self.inp, 'is_web_search_enabled') else False
        
        # Enable/disable web search in router
        if self.router and hasattr(self.router, 'web_search_enabled'):
            self.router.web_search_enabled = use_web_search

        # Use StreamingAIWorker for ChatGPT-style typing effect
        self._last_prompt = text  # Track for cost recording
        self.ai_worker = StreamingAIWorker(text, self.router, files, preferred_backend=selected_model)
        self.ai_worker.chunk_received.connect(self._on_ai_chunk)
        self.ai_worker.done.connect(self._on_ai_done)
        self.ai_worker.error.connect(self._on_ai_err)
        self.ai_worker.source_detected.connect(self._on_ai_source)
        self.ai_worker.web_sources.connect(self._on_web_sources)
        self.ai_worker.start()

    def _on_web_sources(self, sources):
        """Handle web search sources - store for display with response."""
        self._pending_sources = sources
        # Show "Searching..." indicator
        self.statusbar.showMessage(f"🔍 Searching web... ({len(sources)} sources found)", 3000)

    def _on_ai_chunk(self, chunk):
        """Handle streaming chunk - update the typing message."""
        self.chat.update_streaming(getattr(self, '_streaming_text', '') + chunk)
        self._streaming_text = getattr(self, '_streaming_text', '') + chunk

    def _on_ai_done(self, full_response):
        """Handle streaming completion - finalize message with toolbar."""
        self._streaming_text = ''  # Reset

        # If we have pending sources, append them to the response
        if hasattr(self, '_pending_sources') and self._pending_sources and _md_renderer:
            sources_html = _md_renderer.render_citations(self._pending_sources)
            if sources_html:
                full_response = full_response + "\n\n" + "---" + "\n" + sources_html
            self._pending_sources = None

        # Add source attribution label
        source = getattr(self, '_last_ai_source', '')
        if source:
            full_response = full_response + f"\n\n*Powered by {source}*"
            self._last_ai_source = ''

        self.chat.finalize_streaming(full_response)
        self.conv.append({"role": "assistant", "message": full_response})
        self.inp.enable(True)
        self.inp.hide_stop()

        # Save conversation
        self._save()

        # Record token cost and update cost button
        if self._cost_tracker:
            try:
                prompt = getattr(self, '_last_prompt', '')
                backend = getattr(self.router, 'current_backend_name', 'unknown') if self.router else 'unknown'
                # Extract model/provider from "Provider (model)" format
                provider = backend.split('(')[0].strip() if '(' in backend else backend
                model_id = backend.split('(')[1].rstrip(')') if '(' in backend else backend
                # Get cost rates from model registry if available
                cost_in, cost_out = 0.0, 0.0
                if self.router and hasattr(self.router, 'model_registry') and self.router.model_registry:
                    m = self.router.model_registry.get_model(model_id)
                    if m:
                        cost_in, cost_out = getattr(m, 'cost_input', 0.0), getattr(m, 'cost_output', 0.0)
                self._cost_tracker.record_from_text(
                    prompt, full_response, model_id, provider,
                    cost_input_per_m=cost_in, cost_output_per_m=cost_out
                )
                # Update cost button text
                summary = self._cost_tracker.get_summary()
                total_cost = summary.get('total_cost_usd', 0)
                self.cost_btn.setText(f"${total_cost:.4f}")
                # Also show token summary in status bar briefly
                status_text = self._cost_tracker.get_status_text()
                if status_text:
                    self.statusbar.showMessage(status_text, 8000)
            except Exception:
                pass

        # Voice response if in voice mode
        if self.vlay.isVisible() and self.voice and self._voice_enabled:
            self._set_v(VState.SPEAK)
            self.vlay.set_text(full_response[:60] + "..." if len(full_response) > 60 else full_response)

            def speak():
                self.voice.speak(full_response)
                if self.vlay.isVisible():
                    QTimer.singleShot(200, self._listen)
                else:
                    self._set_v(VState.IDLE)
            threading.Thread(target=speak, daemon=True).start()

    def _on_ai_source(self, source_name):
        """Handle source detection from streaming."""
        self._last_ai_source = source_name
        # Update status bar with AI source
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage(f"Using: {source_name}", 5000)

    def _show_cost_dialog(self):
        """Show token usage and cost summary dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Token Usage & Cost")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(f"background: {BG_SURFACE}; color: {TEXT};")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        if not self._cost_tracker:
            lay.addWidget(QLabel("Cost tracking is not available."))
        else:
            summary = self._cost_tracker.get_summary()
            total_tokens = summary.get('total_tokens', 0)
            total_cost = summary.get('total_cost_usd', 0)
            budget = summary.get('budget_usd', 0)
            remaining = summary.get('budget_remaining')
            requests_count = summary.get('total_requests', 0)
            by_provider = summary.get('costs_by_provider', {})

            # Title
            title = QLabel("Session Token Usage")
            title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT};")
            lay.addWidget(title)

            # Main stats grid
            def add_row(label, value):
                row = QHBoxLayout()
                lbl = QLabel(label)
                lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
                val = QLabel(str(value))
                val.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 500;")
                val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(lbl)
                row.addStretch()
                row.addWidget(val)
                lay.addLayout(row)

            add_row("Total Requests:", str(requests_count))
            add_row("Total Tokens:", f"{total_tokens:,}")
            add_row("Input Tokens:", f"{summary.get('total_input_tokens', 0):,}")
            add_row("Output Tokens:", f"{summary.get('total_output_tokens', 0):,}")
            add_row("Estimated Cost:", f"${total_cost:.6f}")
            if budget > 0:
                add_row("Budget:", f"${budget:.2f}")
                if remaining is not None:
                    add_row("Remaining:", f"${remaining:.6f}")

            # Provider breakdown
            if by_provider:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(f"color: {BORDER};")
                lay.addWidget(sep)
                prov_title = QLabel("By Provider:")
                prov_title.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; font-weight: 600;")
                lay.addWidget(prov_title)
                for prov, cost in by_provider.items():
                    add_row(f"  {prov}", f"${cost:.6f}")

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_HOVER}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px;
                font-size: 13px; padding: 4px 20px;
            }}
            QPushButton:hover {{ background: {BG_CARD}; }}
        """)
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec_()

    def _open_canvas(self):
        """Open the AI Canvas in a floating window."""
        if not CANVAS_OK:
            self.chat.add_message("system", "Canvas requires PyQt5 (already installed).")
            return

        # Use a persistent window so it doesn't get garbage collected
        if not hasattr(self, '_canvas_window') or self._canvas_window is None:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout as _VL
            self._canvas_window = QDialog(self)
            self._canvas_window.setWindowTitle("AI Canvas")
            self._canvas_window.setMinimumSize(900, 600)
            self._canvas_window.setStyleSheet(f"background: {BG_SURFACE}; color: {TEXT};")
            canvas_layout = _VL(self._canvas_window)
            canvas_layout.setContentsMargins(0, 0, 0, 0)

            # Build canvas with AI router
            router = getattr(self, 'router', None)
            canvas = create_canvas(ai_router=router) if create_canvas else None
            if canvas:
                canvas_layout.addWidget(canvas)
            else:
                from PyQt5.QtWidgets import QLabel as _QL
                canvas_layout.addWidget(_QL("Canvas not available."))

        self._canvas_window.show()
        self._canvas_window.raise_()
        self._canvas_window.activateWindow()

    def _open_session_picker(self):
        """Open dialog to switch to or create a named topic session."""
        from pathlib import Path as _Path

        sessions_dir = _Path("data/sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(p.stem for p in sessions_dir.glob("*.json"))

        dlg = QDialog(self)
        dlg.setWindowTitle("Named Sessions")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(f"background: {BG_SURFACE}; color: {TEXT};")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Your topic sessions")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT};")
        lay.addWidget(title)

        # Existing sessions list
        session_list = QListWidget()
        session_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_MAIN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px;
                font-size: 13px; padding: 4px;
            }}
            QListWidget::item:selected {{ background: {BG_HOVER}; }}
            QListWidget::item:hover {{ background: {BG_HOVER}; }}
        """)
        session_list.setMaximumHeight(160)
        for name in existing:
            item = QListWidgetItem(name)
            session_list.addItem(item)
        lay.addWidget(session_list)

        # New session input
        new_lbl = QLabel("Create / switch to:")
        new_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        lay.addWidget(new_lbl)

        new_inp = QLineEdit()
        new_inp.setPlaceholderText("e.g. website project, trip planning, code review")
        new_inp.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_MAIN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 6px 10px; font-size: 13px;
                font-family: '{FONT_FAMILY}';
            }}
            QLineEdit:focus {{ border-color: {TEXT_DIM}; }}
        """)
        lay.addWidget(new_inp)

        # Populate input when list item is clicked
        def _on_list_click(item):
            new_inp.setText(item.text())
        session_list.itemClicked.connect(_on_list_click)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        start_btn = QPushButton("Switch / Start")
        start_btn.setFixedHeight(32)
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_HOVER}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px;
                font-size: 13px; padding: 4px 16px;
            }}
            QPushButton:hover {{ background: {BG_CARD}; }}
        """)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(32)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(start_btn.styleSheet())

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(start_btn)
        lay.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)

        def _do_switch():
            name = new_inp.text().strip()
            if not name:
                return
            dlg.accept()
            self._switch_to_session(name)

        start_btn.clicked.connect(_do_switch)
        new_inp.returnPressed.connect(_do_switch)

        dlg.exec_()

    def _switch_to_session(self, name: str):
        """Save current conversation and load a named topic session."""
        from pathlib import Path as _Path
        import json as _json

        sessions_dir = _Path("data/sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Save current conversation to its session file or default save
        self._save()
        current_name = getattr(self, '_current_session_name', None)
        if current_name and self.conv:
            try:
                data = {
                    'session_name': current_name,
                    'updated_at': datetime.now().isoformat(),
                    'messages': self.conv,
                }
                (sessions_dir / f"{current_name}.json").write_text(
                    _json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8'
                )
            except Exception:
                pass

        # Load the target session
        self._current_session_name = name
        session_path = sessions_dir / f"{name}.json"
        self.chat.clear_all()
        self.conv = []

        if session_path.exists():
            try:
                data = _json.loads(session_path.read_text(encoding='utf-8'))
                self.conv = data.get('messages', [])
                self.conv_file = None  # Don't overwrite session file with daily save
                for m in self.conv:
                    self.chat.add(m['role'], m['message'])
                self.statusbar.showMessage(
                    f"Resumed session: {name} ({len(self.conv)//2} exchanges)", 4000
                )
            except Exception as e:
                self.chat.add("assistant", f"Could not load session '{name}': {e}")
        else:
            self.chat.add("assistant",
                          f"Started new session: **{name}**\nThis conversation will be saved and resumed next time you select this session.")
            self.statusbar.showMessage(f"New session: {name}", 3000)

        # Update session button label
        short = name if len(name) <= 16 else name[:14] + ".."
        self.session_btn.setText(short)

    def _on_ai(self, r):
        # Legacy handler - kept for backward compatibility
        # Remove typing
        if self.chat.lay.count() > 1:
            w = self.chat.lay.itemAt(self.chat.lay.count() - 2).widget()
            if w:
                w.deleteLater()
        self.chat.add("assistant", r)
        self.conv.append({"role": "assistant", "message": r})
        self.inp.enable(True)
        self.inp.hide_stop()  # Hide stop button, show send button

        if self.vlay.isVisible() and self.voice:
            self._set_v(VState.SPEAK)
            self.vlay.set_text(r[:60] + "..." if len(r) > 60 else r)

            def speak():
                self.voice.speak(r)
                if self.vlay.isVisible():
                    QTimer.singleShot(200, self._listen)
                else:
                    self._set_v(VState.IDLE)
            threading.Thread(target=speak, daemon=True).start()

    def _on_ai_err(self, e):
        if self.chat.lay.count() > 1:
            w = self.chat.lay.itemAt(self.chat.lay.count() - 2).widget()
            if w:
                w.deleteLater()
        self.chat.add("assistant", f"Error: {e}")
        self.inp.enable(True)
        self.inp.hide_stop()  # Hide stop button, show send button
        if self.vlay.isVisible():
            self._set_v(VState.IDLE)
    
    def _stop_generation(self):
        """Stop AI generation immediately"""
        if hasattr(self, 'ai_worker') and self.ai_worker and self.ai_worker.isRunning():
            # For StreamingAIWorker, use cancel() for graceful stop
            if hasattr(self.ai_worker, 'cancel'):
                self.ai_worker.cancel()
            self.ai_worker.terminate()  # Then force terminate
            self.ai_worker.wait(500)  # Wait up to 500ms
            
            # Finalize with partial response or stopped message
            partial_text = getattr(self, '_streaming_text', '')
            self._streaming_text = ''  # Reset
            
            # Remove streaming placeholder if exists
            if hasattr(self.chat, '_streaming_msg') and self.chat._streaming_msg:
                self.chat._streaming_msg.deleteLater()
                self.chat._streaming_msg = None
            
            # Add stopped message with any partial response
            if partial_text:
                self.chat.add("assistant", f"{partial_text}\n\n*[Generation stopped]*")
            else:
                self.chat.add("assistant", "⚠️ **Generation stopped by user**")
            
            self.inp.enable(True)
            self.inp.hide_stop()
            if self.vlay.isVisible():
                self._set_v(VState.IDLE)

    # ============ LADA v7.0 Agent Methods ============
    
    def _safety_ui_callback(self, message: str, risk_level: str) -> bool:
        """UI callback for safety gate permission requests"""
        reply = QMessageBox.question(
            self, 
            f"Permission Required ({risk_level.upper()})",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes
    
    def _detect_agent_intent(self, text: str) -> tuple:
        """Detect if text requires an agent (flight, product, hotel, restaurant, email, calendar)"""
        text_lower = text.lower()
        
        # Use AgentOrchestrator for smarter detection if available
        if ORCHESTRATOR_OK and AgentOrchestrator:
            try:
                orchestrator = AgentOrchestrator()
                result = orchestrator.detect_intent(text)
                # Result can be IntentType enum or tuple (type, params)
                if result:
                    if hasattr(result, 'value'):
                        # It's an enum
                        if result.value != 'general':
                            return (result.value, {'query': text})
                    elif isinstance(result, tuple) and len(result) >= 2:
                        # It's already a tuple
                        agent_type = result[0]
                        if hasattr(agent_type, 'value'):
                            agent_type = agent_type.value
                        if agent_type and agent_type != 'general':
                            return (agent_type, result[1] if result[1] else {'query': text})
            except Exception as e:
                print(f"[LADA] Orchestrator detection failed: {e}")
        
        # Fallback to keyword-based detection
        # Flight keywords
        flight_keywords = ['flight', 'flights', 'fly', 'flying', 'airline', 'airport', 'book flight']
        if any(kw in text_lower for kw in flight_keywords):
            return ('flight', self._extract_flight_params(text))
        
        # Hotel keywords
        hotel_keywords = ['hotel', 'hotels', 'stay', 'accommodation', 'book room', 'booking', 'resort']
        if any(kw in text_lower for kw in hotel_keywords):
            return ('hotel', {'query': text})
        
        # Restaurant keywords
        restaurant_keywords = ['restaurant', 'restaurants', 'food', 'dinner', 'lunch', 'breakfast', 
                              'reservation', 'table', 'cuisine', 'order food', 'delivery']
        if any(kw in text_lower for kw in restaurant_keywords):
            return ('restaurant', {'query': text})
        
        # Email keywords
        email_keywords = ['email', 'mail', 'send email', 'compose', 'inbox', 'gmail']
        if any(kw in text_lower for kw in email_keywords):
            return ('email', {'query': text})
        
        # Calendar keywords
        calendar_keywords = ['calendar', 'schedule', 'meeting', 'appointment', 'event', 'remind me']
        if any(kw in text_lower for kw in calendar_keywords):
            return ('calendar', {'query': text})
        
        # Product keywords
        product_keywords = ['buy', 'purchase', 'shop', 'price', 'product', 'phone', 'laptop', 
                           'mobile', 'computer', 'amazon', 'flipkart', 'best', 'cheapest',
                           'under', 'budget']
        if any(kw in text_lower for kw in product_keywords):
            return ('product', self._extract_product_params(text))
        
        return (None, None)
    
    def _extract_flight_params(self, text: str) -> dict:
        """Extract flight search parameters from text using AI"""
        prompt = f"""Extract flight search details from: "{text}"
Return JSON only: {{"from_city": "Delhi", "to_city": "Bangalore", "date": "tomorrow", "passengers": 1}}
If not specified, use reasonable defaults. Return ONLY the JSON."""
        
        try:
            response = self.router.query(prompt)
            import json
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except:
            pass
        
        return {"from_city": "Delhi", "to_city": "Bangalore", "date": "tomorrow", "passengers": 1}
    
    def _extract_product_params(self, text: str) -> dict:
        """Extract product search parameters from text"""
        import re
        
        # Extract price limit
        price_match = re.search(r'under\s*₹?\s*(\d+)', text.lower())
        max_price = int(price_match.group(1)) if price_match else None
        
        # Use the query as-is for search
        return {"query": text, "max_price": max_price}
    
    def _handle_flight_agent(self, params: dict):
        """Handle flight search using fast web API"""
        from_city = params.get('from_city', 'Delhi')
        to_city = params.get('to_city', 'Mumbai')
        date = params.get('date', 'tomorrow')
        
        self.chat.add("assistant", f"✈️ Searching flights from **{from_city}** to **{to_city}**...")
        self.inp.enable(False)
        self.inp.show_stop()
        
        def run_agent():
            try:
                from modules.web_search import WebSearchEngine
                ws = WebSearchEngine()
                
                # Build search query for flights
                search_q = f"flights from {from_city} to {to_city} {date} price India 2025"
                
                # Fast API search (1-2 seconds)
                result = ws.search(search_q)
                
                response = f"✈️ **Flight Search: {from_city} → {to_city}**\n\n"
                
                if result.get('success') and (result.get('abstract') or result.get('results')):
                    if result.get('abstract'):
                        response += f"{result['abstract']}\n\n"
                    
                    if result.get('results'):
                        response += "**Search Results:**\n"
                        for i, r in enumerate(result['results'][:5], 1):
                            title = r.get('title', 'Flight')
                            snippet = r.get('snippet', '')[:100]
                            response += f"{i}. **{title}**\n   {snippet}...\n\n"
                    
                    response += "\n💡 *For booking, try: 'open MakeMyTrip and search flights to {to_city}'*"
                else:
                    # Fallback to AI
                    if self.router:
                        ai_q = f"What are the current flight prices from {from_city} to {to_city}? Include airlines and approximate prices in INR."
                        ai_response = self.router.query(ai_q)
                        if ai_response:
                            response += ai_response
                        else:
                            response = f"❌ Could not find flight information"
                    else:
                        response = f"❌ Could not find flight information"
                
                QTimer.singleShot(0, lambda r=response: self._agent_complete(r))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                err_msg = f"❌ Flight search error: {e}"
                QTimer.singleShot(0, lambda m=err_msg: self._agent_complete(m))
        
        threading.Thread(target=run_agent, daemon=True).start()
    
    def _handle_product_agent(self, params: dict):
        """Handle product search using fast web API"""
        query = params.get('query', '')
        max_price = params.get('max_price')
        
        print(f"[LADA] Product agent: query='{query}', max_price={max_price}")
        self.chat.add("assistant", f"🔍 Searching for **{query}**...")
        self.inp.enable(False)
        self.inp.show_stop()
        
        def run_agent():
            try:
                from modules.web_search import WebSearchEngine
                ws = WebSearchEngine()
                
                # Build optimized search query
                search_q = f"{query} price buy India 2025"
                if max_price:
                    search_q += f" under ₹{max_price}"
                
                print(f"[LADA] Product search query: '{search_q}'")
                # Fast API search (1-2 seconds)
                result = ws.search(search_q)
                print(f"[LADA] Product search result: success={result.get('success')}, has_answer={bool(result.get('answer'))}, has_abstract={bool(result.get('abstract'))}, has_results={bool(result.get('results'))}")
                
                response = f"🛍️ **Product Search: {query}**\n\n"
                
                if result.get('success') and (result.get('abstract') or result.get('answer') or result.get('results')):
                    if result.get('answer'):
                        response += f"**Quick Answer:** {result['answer']}\n\n"
                    
                    if result.get('abstract'):
                        response += f"{result['abstract']}\n\n"
                    
                    if result.get('infobox'):
                        response += "**Key Info:**\n"
                        for fact in result['infobox'][:5]:
                            response += f"• {fact}\n"
                        response += "\n"
                    
                    if result.get('results'):
                        response += "**Search Results:**\n"
                        for i, r in enumerate(result['results'][:5], 1):
                            title = r.get('title', 'Result')
                            snippet = r.get('snippet', '')[:100]
                            response += f"{i}. **{title}**\n   {snippet}...\n\n"
                    
                    response += f"\n💡 *Say 'open Amazon and search for {query}' to browse directly*"
                else:
                    # Fallback to AI for product info
                    print("[LADA] Product search: No web results, falling back to AI")
                    if self.router:
                        ai_q = f"What are the best {query} products available in India with approximate prices in INR? List top 5 options."
                        ai_response = self.router.query(ai_q)
                        print(f"[LADA] AI fallback response length: {len(ai_response) if ai_response else 0}")
                        if ai_response:
                            response += ai_response
                        else:
                            response = f"❌ Could not find product information for: {query}"
                    else:
                        response = f"❌ Could not find product information for: {query}"
                
                print(f"[LADA] Final product response length: {len(response)}")
                print(f"[LADA] Final product response preview: {response[:200] if response else 'EMPTY'}...")
                QTimer.singleShot(0, lambda r=response: self._agent_complete(r))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                err_msg = f"❌ Search error: {e}"
                QTimer.singleShot(0, lambda m=err_msg: self._agent_complete(m))
        
        threading.Thread(target=run_agent, daemon=True).start()
    
    def _handle_hotel_agent(self, params: dict):
        """Handle hotel search using fast web API"""
        query = params.get('query', '')
        self.chat.add("assistant", f"🏨 Searching hotels...")
        self.inp.enable(False)
        self.inp.show_stop()
        
        def run_agent():
            try:
                from modules.web_search import WebSearchEngine
                ws = WebSearchEngine()
                
                # Build optimized search query for hotels
                search_q = f"hotels {query} prices India 2025 booking"
                
                # Fast API search (1-2 seconds)
                result = ws.search(search_q)
                
                response = f"🏨 **Hotel Search**\n\n"
                
                if result.get('success') and (result.get('abstract') or result.get('results')):
                    if result.get('abstract'):
                        response += f"{result['abstract']}\n\n"
                    
                    if result.get('infobox'):
                        response += "**Key Information:**\n"
                        for fact in result['infobox'][:5]:
                            response += f"• {fact}\n"
                        response += "\n"
                    
                    if result.get('results'):
                        response += "**Search Results:**\n"
                        for i, r in enumerate(result['results'][:5], 1):
                            title = r.get('title', 'Hotel')
                            snippet = r.get('snippet', '')[:100]
                            response += f"{i}. **{title}**\n   {snippet}...\n\n"
                    
                    response += "\n💡 *For booking, say 'open MakeMyTrip hotels' or 'open Booking.com'*"
                else:
                    # Fallback to AI for hotel info
                    if self.router:
                        ai_q = f"What are the best hotels {query}? Include approximate prices in INR and ratings."
                        ai_response = self.router.query(ai_q)
                        if ai_response:
                            response += ai_response
                        else:
                            response = f"❌ Could not find hotel information"
                    else:
                        response = f"❌ Could not find hotel information"
                
                QTimer.singleShot(0, lambda r=response: self._agent_complete(r))
            except Exception as e:
                import traceback
                traceback.print_exc()
                err_msg = f"❌ Hotel search error: {e}"
                QTimer.singleShot(0, lambda m=err_msg: self._agent_complete(m))
        
        threading.Thread(target=run_agent, daemon=True).start()
    
    def _handle_restaurant_agent(self, params: dict):
        """Handle restaurant search using fast web API"""
        query = params.get('query', '')
        self.chat.add("assistant", f"🍽️ Searching restaurants...")
        self.inp.enable(False)
        self.inp.show_stop()
        
        def run_agent():
            try:
                from modules.web_search import WebSearchEngine
                ws = WebSearchEngine()
                
                # Build optimized search query for restaurants
                search_q = f"restaurants {query} ratings reviews India 2025"
                
                # Fast API search (1-2 seconds)
                result = ws.search(search_q)
                
                response = f"🍽️ **Restaurant Search**\n\n"
                
                if result.get('success') and (result.get('abstract') or result.get('results')):
                    if result.get('abstract'):
                        response += f"{result['abstract']}\n\n"
                    
                    if result.get('infobox'):
                        response += "**Key Information:**\n"
                        for fact in result['infobox'][:5]:
                            response += f"• {fact}\n"
                        response += "\n"
                    
                    if result.get('results'):
                        response += "**Search Results:**\n"
                        for i, r in enumerate(result['results'][:5], 1):
                            title = r.get('title', 'Restaurant')
                            snippet = r.get('snippet', '')[:100]
                            response += f"{i}. **{title}**\n   {snippet}...\n\n"
                    
                    response += "\n💡 *For reservations, say 'open Zomato' or 'open Swiggy'*"
                else:
                    # Fallback to AI for restaurant info
                    if self.router:
                        ai_q = f"What are the best restaurants {query}? Include ratings and approximate cost for two in INR."
                        ai_response = self.router.query(ai_q)
                        if ai_response:
                            response += ai_response
                        else:
                            response = f"❌ Could not find restaurant information"
                    else:
                        response = f"❌ Could not find restaurant information"
                
                QTimer.singleShot(0, lambda r=response: self._agent_complete(r))
            except Exception as e:
                import traceback
                traceback.print_exc()
                err_msg = f"❌ Restaurant search error: {e}"
                QTimer.singleShot(0, lambda m=err_msg: self._agent_complete(m))
        
        threading.Thread(target=run_agent, daemon=True).start()
    
    def _handle_email_agent(self, params: dict):
        """Handle email operations"""
        self.chat.add("assistant", f"📧 Processing email request...")
        self.inp.enable(False)
        self.inp.show_stop()
        
        def run_agent():
            try:
                from modules.agents.email_agent import EmailAgent
                agent = EmailAgent()
                result = agent.process(params.get('query', ''))
                
                if result.get('success'):
                    response = f"📧 **Email Result**\n\n"
                    response += result.get('message', 'Done')
                    
                    if result.get('emails'):
                        response += "\n\n**Recent Emails:**\n"
                        for i, e in enumerate(result['emails'][:5], 1):
                            response += f"{i}. {e.get('subject', 'No Subject')}\n"
                            response += f"   From: {e.get('from', 'Unknown')}\n"
                    
                    if result.get('draft_path'):
                        response += f"\n📝 Draft saved to: {result['draft_path']}"
                else:
                    response = f"❌ Email error: {result.get('message', 'Unknown error')}"
                
                QTimer.singleShot(0, lambda r=response: self._agent_complete(r))
            except Exception as e:
                err_msg = f"❌ Error: {e}"
                QTimer.singleShot(0, lambda m=err_msg: self._agent_complete(m))
        
        threading.Thread(target=run_agent, daemon=True).start()
    
    def _handle_calendar_agent(self, params: dict):
        """Handle calendar operations"""
        self.chat.add("assistant", f"📅 Checking calendar...")
        self.inp.enable(False)
        self.inp.show_stop()
        
        def run_agent():
            try:
                from modules.agents.calendar_agent import CalendarAgent
                agent = CalendarAgent()
                result = agent.process(params.get('query', ''))
                
                if result.get('success'):
                    response = f"📅 **Calendar**\n\n"
                    response += result.get('message', result.get('summary', 'Done'))
                    
                    if result.get('events'):
                        response += "\n\n**Upcoming Events:**\n"
                        for e in result['events'][:5]:
                            response += f"• {e.get('summary', 'Event')} - {e.get('start', 'TBD')}\n"
                    
                    if result.get('event_id'):
                        response += f"\n✅ Event ID: {result['event_id']}"
                else:
                    response = f"❌ Calendar error: {result.get('message', 'Unknown error')}"
                
                QTimer.singleShot(0, lambda r=response: self._agent_complete(r))
            except Exception as e:
                err_msg = f"❌ Error: {e}"
                QTimer.singleShot(0, lambda m=err_msg: self._agent_complete(m))
        
        threading.Thread(target=run_agent, daemon=True).start()
    
    def _agent_complete(self, response: str):
        """Called when agent completes - update UI"""
        print(f"[LADA] _agent_complete called with response length: {len(response) if response else 0}")
        
        # Remove "searching" message
        if self.chat.lay.count() > 1:
            w = self.chat.lay.itemAt(self.chat.lay.count() - 2).widget()
            if w:
                w.deleteLater()
        
        # Ensure we have a valid response
        if not response or len(response.strip()) == 0:
            response = "❌ No response received. Please try again."
            print("[LADA] Warning: Empty response, using fallback message")
        
        self.chat.add("assistant", response)
        self.conv.append({"role": "assistant", "message": response})
        self.inp.enable(True)
        self.inp.hide_stop()
        
        # Speak if in voice mode
        if self.vlay.isVisible() and self.voice:
            self._set_v(VState.SPEAK)
            # Speak a short summary
            short_response = response.split('\n')[0][:100]
            self.vlay.set_text(short_response)
            def speak():
                self.voice.speak(short_response)
                if self.vlay.isVisible():
                    QTimer.singleShot(200, self._listen)
                else:
                    self._set_v(VState.IDLE)
            threading.Thread(target=speak, daemon=True).start()

    def _set_v(self, s):
        self.v_state = s
        self.vlay.set_state(s)

    def _toggle_voice(self):
        if not self._voice_enabled:
            self.statusbar.showMessage("Voice is OFF — enable voice first.", 3000)
            return
        if self.vlay.isVisible():
            self._close_voice()
        else:
            # Start new voice session
            self.voice_session = []
            if hasattr(self, 'voice_session_file'):
                delattr(self, 'voice_session_file')
            self.vlay.clear_history()
            
            self.vlay.setGeometry(self.side.width(), 0, self.width() - self.side.width(), self.height())
            self.vlay.show()
            self.vlay.raise_()
            self.vlay.set_text("")
            self._set_v(VState.IDLE)
            QTimer.singleShot(200, self._listen)

    def _close_voice(self):
        self.vlay.hide()
        if self.v_worker:
            self.v_worker.stop()
        self._set_v(VState.IDLE)
        # Refresh sidebar to show new voice session
        self.side.refresh()

    def _toggle_listen(self):
        if self.v_state == VState.LISTEN:
            if self.v_worker:
                self.v_worker.stop()
            self._set_v(VState.IDLE)
        else:
            self._listen()

    def _listen(self):
        if not self._voice_enabled:
            return
        if not self.vlay.isVisible():
            return
        self._set_v(VState.LISTEN)
        self.vlay.set_text("")
        self.v_worker = VoiceWorker(self.voice)
        self.v_worker.result.connect(self._on_voice)
        self.v_worker.error.connect(self._on_voice_err)
        self.v_worker.start()

    def _on_voice(self, t):
        self.vlay.set_text(t)
        self.vlay.add_message("user", t)  # Add to overlay history
        self._set_v(VState.PROCESS)
        # Use voice-only send (doesn't save to main chat history)
        self._send_voice(t)

    def _send_voice(self, text):
        """Handle voice input - stays in overlay, saved to separate voice history"""
        if not text:
            return
        
        # Add to voice session history (separate from text chat)
        if not hasattr(self, 'voice_session'):
            self.voice_session = []
        self.voice_session.append({
            "role": "user", 
            "message": text,
            "timestamp": datetime.now().isoformat()
        })
        
        # Check for system commands first (execute but don't show in main chat)
        handled, response = self._check_system_command(text)
        if handled:
            # Check for stop listening signal
            if response.startswith("__STOP_LISTENING__"):
                actual_response = response.replace("__STOP_LISTENING__", "")
                self.voice_session.append({
                    "role": "assistant", 
                    "message": actual_response,
                    "timestamp": datetime.now().isoformat()
                })
                self._save_voice_session()
                self.vlay.add_message("assistant", actual_response)
                
                if self.voice:
                    self._set_v(VState.SPEAK)
                    self.vlay.set_text(actual_response)
                    def speak_and_pause():
                        self.voice.speak(actual_response)
                        # Don't auto-restart - go to idle
                        self._set_v(VState.IDLE)
                        self.vlay.set_text("Tap mic to speak")
                    threading.Thread(target=speak_and_pause, daemon=True).start()
                else:
                    self._set_v(VState.IDLE)
                    self.vlay.set_text("Tap mic to speak")
                return
            
            self.voice_session.append({
                "role": "assistant", 
                "message": response,
                "timestamp": datetime.now().isoformat()
            })
            self._save_voice_session()
            self.vlay.add_message("assistant", response)  # Add to overlay history
            
            if self.voice:
                self._set_v(VState.SPEAK)
                self.vlay.set_text(response[:80] + "..." if len(response) > 80 else response)
                def speak():
                    self.voice.speak(response)
                    if self.vlay.isVisible():
                        QTimer.singleShot(200, self._listen)  # Continuous: auto-restart
                    else:
                        self._set_v(VState.IDLE)
                threading.Thread(target=speak, daemon=True).start()
            else:
                # No voice - auto-restart listening anyway
                if self.vlay.isVisible():
                    QTimer.singleShot(500, self._listen)
            return
        
        # AI query for voice (doesn't show in main chat)
        self.vlay.set_text("Thinking...")
        selected_model = self.model.currentData() if hasattr(self, 'model') else None
        if selected_model == 'auto':
            selected_model = None
        self.ai_worker = AIWorker(text, self.router, [], preferred_backend=selected_model)
        self.ai_worker.done.connect(self._on_voice_ai)
        self.ai_worker.error.connect(self._on_voice_ai_err)
        self.ai_worker.start()
    
    def _on_voice_ai(self, r):
        """Handle AI response for voice - stays in overlay only"""
        # Add to voice session
        if hasattr(self, 'voice_session'):
            self.voice_session.append({
                "role": "assistant", 
                "message": r,
                "timestamp": datetime.now().isoformat()
            })
            self._save_voice_session()
        
        self.vlay.add_message("assistant", r)  # Add to overlay history
        
        if self.voice:
            self._set_v(VState.SPEAK)
            self.vlay.set_text(r[:80] + "..." if len(r) > 80 else r)
            def speak():
                self.voice.speak(r)
                if self.vlay.isVisible():
                    QTimer.singleShot(200, self._listen)
                else:
                    self._set_v(VState.IDLE)
            threading.Thread(target=speak, daemon=True).start()
    
    def _on_voice_ai_err(self, e):
        """Handle AI error for voice"""
        self.vlay.set_text(f"Error: {e}")
        if self.vlay.isVisible():
            QTimer.singleShot(1500, self._listen)
    
    def _save_voice_session(self):
        """Save voice session to separate folder"""
        if not hasattr(self, 'voice_session') or not self.voice_session:
            return
        try:
            voice_dir = Path("data/voice_sessions")
            voice_dir.mkdir(parents=True, exist_ok=True)
            
            # Use session start timestamp for filename
            if not hasattr(self, 'voice_session_file'):
                self.voice_session_file = voice_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
            
            self.voice_session_file.write_text(
                json.dumps(self.voice_session, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            print(f"[LADA] Could not save voice session: {e}")

    def _on_voice_err(self, e):
        self.vlay.set_text(f"({e})")
        self._set_v(VState.IDLE)
        if self.vlay.isVisible():
            QTimer.singleShot(1200, self._listen)

    def _on_proactive_suggestion(self, suggestion):
        """
        Handle proactive suggestions from the ProactiveAgent.
        Displays as a notification or chat message based on priority.
        """
        if suggestion is None:
            return

        try:
            title = getattr(suggestion, 'title', 'Suggestion')
            message = getattr(suggestion, 'message', '')
            priority = getattr(suggestion, 'priority', None)
            action = getattr(suggestion, 'action', None)

            # Critical/High priority: Show as system notification + chat
            if priority and hasattr(priority, 'value') and priority.value <= 2:
                # Show system tray notification
                if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                    self.tray_icon.showMessage(
                        f"LADA: {title}",
                        message[:200],
                        QSystemTrayIcon.Information,
                        5000
                    )
                # Also add to chat
                self.chat.add("assistant", f"💡 **{title}**\n\n{message}")
            else:
                # Normal/Low priority: Just add to chat
                self.chat.add("assistant", f"💡 {title}: {message}")

            # If there's an action, offer to execute it
            if action:
                logger.info(f"[ProactiveAgent] Suggestion action available: {action}")

        except Exception as e:
            logger.warning(f"[LADA] Proactive suggestion display error: {e}")

    def closeEvent(self, e):
        """Minimize to system tray instead of closing"""
        # Minimize to tray instead of quitting
        e.ignore()
        self.hide()

        # Keep global autonomous overlay visible only while an active task is running.
        if hasattr(self, 'floating_comet_overlay') and self.floating_comet_overlay:
            if not getattr(self, '_active_comet_agent', None):
                self.floating_comet_overlay.hide()
        
        # Show tray notification on first minimize
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "LADA AI",
                "Running in background. Say 'LADA' to activate, or double-click tray icon to open.",
                QSystemTrayIcon.Information,
                2000
            )


# Backwards/launcher compatibility: the optimized launcher expects this symbol.
LadaDesktopApp = LadaApp


def main():
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
    app.setStyleSheet(GLOBAL_QSS)
    
    # Don't quit when main window closes (for system tray)
    app.setQuitOnLastWindowClosed(False)

    w = LadaApp()
    w.show()
    
    # Show face verification dialog inside app (non-blocking)
    if FACE_OK:
        QTimer.singleShot(500, lambda: w._check_face_auth())
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
