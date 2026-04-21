from modules.desktop.common import *

class VState:
    IDLE, LISTEN, PROCESS, SPEAK = 0, 1, 2, 3



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
                        except Exception as e:
                            label = f"Voice session ({count})"
                        item = QListWidgetItem(f"🎤 {label}")
                        item.setData(Qt.UserRole, str(f))
                        self.voice_lst.addItem(item)
                except Exception as e:
                    pass

    def refresh(self):
        self._load()



class Msg(QFrame):
    """Full-width message row (modern chat style) with hover toolbar."""
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



