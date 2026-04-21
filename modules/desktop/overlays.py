from modules.desktop.common import *

from modules.desktop.ui import OrbWidget

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



