from modules.desktop.common import *

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
            except Exception as e:
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
        
        # Theme toggle
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("🎨 Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Mode", "Light Mode"])
        # Load current theme
        from theme import get_theme_mode
        self.theme_combo.setCurrentIndex(0 if get_theme_mode() == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._change_theme)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        dlay.addLayout(theme_row)
        
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
        except Exception as e:
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
        except Exception as e:
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

        # System Health & Doctor Group (NEW)
        doctor_group = QGroupBox("System Health")
        doc_lay = QVBoxLayout(doctor_group)
        doc_lay.setSpacing(8)
        
        # Status summary
        self.health_status_lbl = QLabel("🩺 Click 'Run Diagnostics' to check system health")
        self.health_status_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        self.health_status_lbl.setWordWrap(True)
        doc_lay.addWidget(self.health_status_lbl)
        
        # Results list (hidden until diagnostics run)
        self.health_results = QListWidget()
        self.health_results.setMaximumHeight(120)
        self.health_results.setStyleSheet(f"""
            QListWidget {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                font-size: 11px;
            }}
            QListWidget::item {{ padding: 4px; }}
        """)
        self.health_results.setVisible(False)
        doc_lay.addWidget(self.health_results)
        
        # Buttons row
        doc_btn_row = QHBoxLayout()
        
        self.run_diagnostics_btn = QPushButton("🩺 Run Diagnostics")
        self.run_diagnostics_btn.setCursor(Qt.PointingHandCursor)
        self.run_diagnostics_btn.setToolTip("Run all system health checks")
        self.run_diagnostics_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN}; color: white;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {ACCENT_GRADIENT_END}; }}
        """)
        self.run_diagnostics_btn.clicked.connect(self._run_diagnostics)
        doc_btn_row.addWidget(self.run_diagnostics_btn)
        
        self.auto_fix_btn = QPushButton("🔧 Auto-Fix Issues")
        self.auto_fix_btn.setCursor(Qt.PointingHandCursor)
        self.auto_fix_btn.setToolTip("Attempt automatic fixes for detected issues")
        self.auto_fix_btn.setEnabled(False)
        self.auto_fix_btn.setStyleSheet(f"""
            QPushButton {{
                background: #3498db; color: white;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px;
            }}
            QPushButton:hover {{ background: #2980b9; }}
            QPushButton:disabled {{ background: {BG_INPUT}; color: {TEXT_DIM}; }}
        """)
        self.auto_fix_btn.clicked.connect(self._run_auto_fix)
        doc_btn_row.addWidget(self.auto_fix_btn)
        
        doc_btn_row.addStretch()
        doc_lay.addLayout(doc_btn_row)
        
        scroll_lay.addWidget(doctor_group)

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

        # ============ DLP Audit Log (Phase 2 UI) ============
        dlp_group = QGroupBox("🔒 Data Loss Prevention (DLP)")
        dlp_lay = QVBoxLayout(dlp_group)
        dlp_lay.setSpacing(8)

        dlp_desc = QLabel("View redacted screen regions. Sensitive data is blocked before reaching AI.")
        dlp_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        dlp_desc.setWordWrap(True)
        dlp_lay.addWidget(dlp_desc)

        # DLP sensitivity selector
        dlp_sens_row = QHBoxLayout()
        dlp_sens_row.addWidget(QLabel("Sensitivity:"))
        self.dlp_sensitivity_combo = QComboBox()
        self.dlp_sensitivity_combo.addItems(["Strict", "Normal", "Relaxed"])
        self.dlp_sensitivity_combo.setCurrentIndex(1)
        self.dlp_sensitivity_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }}
        """)
        dlp_sens_row.addWidget(self.dlp_sensitivity_combo)
        dlp_sens_row.addStretch()
        dlp_lay.addLayout(dlp_sens_row)

        # DLP audit list
        self.dlp_audit_list = QListWidget()
        self.dlp_audit_list.setMaximumHeight(100)
        self.dlp_audit_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                font-size: 11px; font-family: 'Consolas', monospace;
            }}
            QListWidget::item {{ padding: 3px; }}
        """)
        dlp_lay.addWidget(self.dlp_audit_list)

        dlp_btn_row = QHBoxLayout()
        self.dlp_refresh_btn = QPushButton("🔄 Refresh Log")
        self.dlp_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.dlp_refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN}; color: white;
                border: none; border-radius: 6px;
                padding: 6px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {ACCENT_GRADIENT_END}; }}
        """)
        self.dlp_refresh_btn.clicked.connect(self._refresh_dlp_log)
        dlp_btn_row.addWidget(self.dlp_refresh_btn)

        self.dlp_clear_btn = QPushButton("🗑️ Clear")
        self.dlp_clear_btn.setCursor(Qt.PointingHandCursor)
        self.dlp_clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: #e74c3c; color: white;
                border: none; border-radius: 6px;
                padding: 6px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ background: #c0392b; }}
        """)
        self.dlp_clear_btn.clicked.connect(self._clear_dlp_log)
        dlp_btn_row.addWidget(self.dlp_clear_btn)
        dlp_btn_row.addStretch()
        dlp_lay.addLayout(dlp_btn_row)

        scroll_lay.addWidget(dlp_group)

        # ============ MCP Interceptor Audit (Phase 7 UI) ============
        mcp_group = QGroupBox("🛡️ MCP Tool Interceptor")
        mcp_lay = QVBoxLayout(mcp_group)
        mcp_lay.setSpacing(8)

        mcp_desc = QLabel("Monitor tool calls: rate-limiting, sanitization, and audit trail.")
        mcp_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        mcp_desc.setWordWrap(True)
        mcp_lay.addWidget(mcp_desc)

        self.mcp_stats_lbl = QLabel("No MCP data yet — invoke a tool to see stats.")
        self.mcp_stats_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        mcp_lay.addWidget(self.mcp_stats_lbl)

        self.mcp_audit_list = QListWidget()
        self.mcp_audit_list.setMaximumHeight(100)
        self.mcp_audit_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                font-size: 11px; font-family: 'Consolas', monospace;
            }}
            QListWidget::item {{ padding: 3px; }}
        """)
        mcp_lay.addWidget(self.mcp_audit_list)

        mcp_btn_row = QHBoxLayout()
        self.mcp_refresh_btn = QPushButton("🔄 Refresh")
        self.mcp_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.mcp_refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN}; color: white;
                border: none; border-radius: 6px;
                padding: 6px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {ACCENT_GRADIENT_END}; }}
        """)
        self.mcp_refresh_btn.clicked.connect(self._refresh_mcp_log)
        mcp_btn_row.addWidget(self.mcp_refresh_btn)
        mcp_btn_row.addStretch()
        mcp_lay.addLayout(mcp_btn_row)

        scroll_lay.addWidget(mcp_group)

        # ============ YOLO Permission Overrides (Phase 6 UI) ============
        yolo_group = QGroupBox("⚡ Permission Classifier (YOLO)")
        yolo_lay = QVBoxLayout(yolo_group)
        yolo_lay.setSpacing(8)

        yolo_desc = QLabel("Override AI safety classifications. Commands are auto-classified into SAFE / CONFIRM / DENY tiers.")
        yolo_desc.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        yolo_desc.setWordWrap(True)
        yolo_lay.addWidget(yolo_desc)

        # Override form
        yolo_override_row = QHBoxLayout()
        yolo_override_row.addWidget(QLabel("Command pattern:"))
        self.yolo_pattern_input = QLineEdit()
        self.yolo_pattern_input.setPlaceholderText("e.g. shutdown, pip install ...")
        self.yolo_pattern_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {GREEN}; }}
        """)
        yolo_override_row.addWidget(self.yolo_pattern_input, 1)

        self.yolo_tier_combo = QComboBox()
        self.yolo_tier_combo.addItems(["SAFE", "CONFIRM", "DENY"])
        self.yolo_tier_combo.setCurrentIndex(1)
        self.yolo_tier_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }}
        """)
        yolo_override_row.addWidget(self.yolo_tier_combo)

        self.yolo_add_btn = QPushButton("➕ Add Override")
        self.yolo_add_btn.setCursor(Qt.PointingHandCursor)
        self.yolo_add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN}; color: white;
                border: none; border-radius: 6px;
                padding: 6px 14px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {ACCENT_GRADIENT_END}; }}
        """)
        self.yolo_add_btn.clicked.connect(self._add_yolo_override)
        yolo_override_row.addWidget(self.yolo_add_btn)
        yolo_lay.addLayout(yolo_override_row)

        # Active overrides list
        self.yolo_overrides_list = QListWidget()
        self.yolo_overrides_list.setMaximumHeight(80)
        self.yolo_overrides_list.setStyleSheet(f"""
            QListWidget {{
                background: {BG_INPUT}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 6px;
                font-size: 11px;
            }}
            QListWidget::item {{ padding: 3px; }}
        """)
        yolo_lay.addWidget(self.yolo_overrides_list)

        scroll_lay.addWidget(yolo_group)

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
                if hasattr(self.voice, "set_voice_speed"):
                    self.voice.set_voice_speed(self.spd_spin.value())
                elif hasattr(self.voice, "voice_speed"):
                    self.voice.voice_speed = self.spd_spin.value()
            except Exception as e:
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
    
    def _run_diagnostics(self):
        """Run system diagnostics and display results."""
        self.health_status_lbl.setText("🔄 Running diagnostics...")
        self.health_results.clear()
        self.health_results.setVisible(True)
        self.auto_fix_btn.setEnabled(False)
        QApplication.processEvents()
        
        try:
            from modules.doctor import DiagnosticsRunner
            
            runner = DiagnosticsRunner()
            report = runner.run_all()
            
            # Update status
            is_healthy = report.failed == 0
            status_icon = "✅" if is_healthy else "❌"
            status_text = "HEALTHY" if is_healthy else "UNHEALTHY"
            self.health_status_lbl.setText(
                f"{status_icon} System Status: {status_text} | "
                f"Checks: {report.passed}/{report.total_checks} passed | "
                f"Duration: {report.duration_ms:.0f}ms"
            )
            self.health_status_lbl.setStyleSheet(
                f"color: {GREEN if is_healthy else '#e74c3c'}; font-size: 12px; font-weight: bold;"
            )
            
            # Show results
            for result in report.results:
                icon = "✅" if result.passed else ("⚠️" if result.severity.value == "warning" else "❌")
                item = QListWidgetItem(f"{icon} {result.name}: {result.message}")
                if not result.passed:
                    item.setForeground(QColor("#e74c3c"))
                self.health_results.addItem(item)
            
            # Enable auto-fix if there are fixable issues
            fixable = [r for r in report.results if not r.passed and r.fixable]
            if fixable:
                self.auto_fix_btn.setEnabled(True)
                self.auto_fix_btn.setToolTip(f"{len(fixable)} issue(s) can be auto-fixed")
                self._fixable_issues = fixable
            else:
                self._fixable_issues = []
                
        except ImportError:
            self.health_status_lbl.setText("❌ Doctor module not available")
            self.health_status_lbl.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
        except Exception as e:
            self.health_status_lbl.setText(f"❌ Error running diagnostics: {str(e)[:50]}")
            self.health_status_lbl.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
    
    def _run_auto_fix(self):
        """Attempt to auto-fix detected issues."""
        if not hasattr(self, '_fixable_issues') or not self._fixable_issues:
            return
        
        reply = QMessageBox.question(
            self,
            "Auto-Fix Issues",
            f"Attempt to auto-fix {len(self._fixable_issues)} issue(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            from modules.doctor import AutoFixEngine
            
            engine = AutoFixEngine()
            fixed = 0
            failed = 0
            
            for issue in self._fixable_issues:
                if issue.fix_id:
                    result = engine.execute(issue.fix_id)
                    if result and result.success:
                        fixed += 1
                    else:
                        failed += 1
            
            QMessageBox.information(
                self,
                "Auto-Fix Complete",
                f"Fixed: {fixed}\nFailed: {failed}\n\nRe-run diagnostics to verify."
            )
            
            # Re-run diagnostics to show updated status
            self._run_diagnostics()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Auto-fix failed: {e}")

    # ---------- DLP Audit handlers (Phase 2) ----------

    def _refresh_dlp_log(self):
        """Load the latest DLP audit entries into the list widget."""
        self.dlp_audit_list.clear()
        try:
            from modules.dlp_filter import get_dlp_filter, DLPSensitivity
            dlp = get_dlp_filter()

            # Apply sensitivity from combo
            sens_map = {0: DLPSensitivity.STRICT, 1: DLPSensitivity.NORMAL, 2: DLPSensitivity.RELAXED}
            new_sens = sens_map.get(self.dlp_sensitivity_combo.currentIndex(), DLPSensitivity.NORMAL)
            dlp.set_sensitivity(new_sens)

            entries = dlp.get_audit_log(limit=30)
            if not entries:
                self.dlp_audit_list.addItem("No redaction events recorded yet.")
                return
            for e in reversed(entries):
                import datetime
                ts = datetime.datetime.fromtimestamp(e.get("timestamp", 0)).strftime("%H:%M:%S")
                region = e.get("region") or "text-only"
                self.dlp_audit_list.addItem(
                    f"[{ts}] {e.get('pattern', '?')}: {e.get('matched', '***')} | {region}"
                )
        except ImportError:
            self.dlp_audit_list.addItem("DLP module not available.")
        except Exception as ex:
            self.dlp_audit_list.addItem(f"Error loading DLP log: {ex}")

    def _clear_dlp_log(self):
        """Clear the DLP audit log."""
        try:
            from modules.dlp_filter import get_dlp_filter
            get_dlp_filter().clear_audit()
        except Exception:
            pass
        self.dlp_audit_list.clear()
        self.dlp_audit_list.addItem("Audit log cleared.")

    # ---------- MCP Interceptor handlers (Phase 7) ----------

    def _refresh_mcp_log(self):
        """Load the latest MCP interceptor audit entries."""
        self.mcp_audit_list.clear()
        try:
            from modules.mcp_interceptor import get_mcp_interceptor
            interceptor = get_mcp_interceptor()

            # Stats summary
            stats = interceptor.get_stats()
            self.mcp_stats_lbl.setText(
                f"Total calls: {stats.get('total_calls', 0)} | "
                f"Blocked: {stats.get('blocked', 0)} | "
                f"Errors: {stats.get('errors', 0)}"
            )

            entries = interceptor.get_audit_log(limit=30)
            if not entries:
                self.mcp_audit_list.addItem("No tool calls recorded yet.")
                return
            for e in reversed(entries):
                import datetime
                ts = datetime.datetime.fromtimestamp(e.get("timestamp", 0)).strftime("%H:%M:%S")
                status = "BLOCKED" if e.get("blocked") else ("ERR" if e.get("error") else "OK")
                dur = e.get("duration_ms", 0)
                self.mcp_audit_list.addItem(
                    f"[{ts}] {status} {e.get('tool', '?')} ({dur:.0f}ms)"
                )
        except ImportError:
            self.mcp_audit_list.addItem("MCP Interceptor module not available.")
        except Exception as ex:
            self.mcp_audit_list.addItem(f"Error: {ex}")

    # ---------- YOLO Permission Override handlers (Phase 6) ----------

    def _add_yolo_override(self):
        """Add a user-defined permission override for the YOLO classifier."""
        pattern = self.yolo_pattern_input.text().strip()
        if not pattern:
            return
        tier_name = self.yolo_tier_combo.currentText()

        try:
            from modules.yolo_permission_classifier import YOLOPermissionClassifier, PermissionTier
            from modules.safety_gate import SafetyGate

            tier_map = {"SAFE": PermissionTier.SAFE, "CONFIRM": PermissionTier.CONFIRM, "DENY": PermissionTier.DENY}
            tier = tier_map.get(tier_name, PermissionTier.CONFIRM)

            # Try to reach the classifier from the safety gate singleton
            try:
                gate = SafetyGate.__new__(SafetyGate)
                if hasattr(gate, '_yolo_classifier'):
                    gate._yolo_classifier.add_override(pattern, tier)
            except Exception:
                pass

            self.yolo_overrides_list.addItem(f"{pattern} → {tier_name}")
            self.yolo_pattern_input.clear()
        except ImportError:
            self.yolo_overrides_list.addItem("YOLO classifier module not available.")
        except Exception as ex:
            self.yolo_overrides_list.addItem(f"Error: {ex}")

    def get_settings(self):
        """Return current settings"""
        return getattr(self, 'settings_data', {})
    
    def _set_volume(self, val):
        self.vol_lbl.setText(f"{val}%")
        if self.sys:
            try:
                self.sys.set_volume(val)
            except Exception as e:
                pass
    
    def _update_font_label(self, val):
        """Update font size label when slider changes"""
        self.font_lbl.setText(f"{val}px")
    
    def _change_theme(self, index):
        """Change application theme (0=dark, 1=light)"""
        from theme import set_theme_mode
        new_mode = "dark" if index == 0 else "light"
        new_qss = set_theme_mode(new_mode)
        # Apply to main application
        app = QApplication.instance()
        if app:
            app.setStyleSheet(new_qss)
        # Save theme preference
        try:
            settings_file = Path("config/app_settings.json")
            settings_file.parent.mkdir(exist_ok=True)
            if settings_file.exists():
                saved = json.loads(settings_file.read_text())
            else:
                saved = {}
            saved['theme_mode'] = new_mode
            settings_file.write_text(json.dumps(saved, indent=2))
        except Exception:
            pass


Path("logs").mkdir(exist_ok=True)
Path("data/conversations").mkdir(parents=True, exist_ok=True)

logging.basicConfig(filename='logs/lada_gui.log', level=logging.INFO)
logger = logging.getLogger(__name__)


