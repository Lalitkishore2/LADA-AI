"""
LADA v11.0 - Interactive AI Canvas Widget
A collaborative editing canvas with AI-assisted suggestions for code, markdown, and diagrams.

Features:
- Syntax-highlighted code editor
- AI suggestion panel with inline completions
- Multiple content types (code, markdown, diagram)
- Export to file functionality
- Real-time AI assistance
"""

import os
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Try PyQt5 imports
try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit,
        QPushButton, QComboBox, QLabel, QSplitter, QFrame, QFileDialog,
        QToolBar, QAction, QMenu, QFontDialog, QInputDialog
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    from PyQt5.QtGui import (
        QFont, QColor, QTextCharFormat, QSyntaxHighlighter,
        QTextDocument, QPalette, QTextCursor, QKeySequence
    )
    PYQT_OK = True
except ImportError:
    PYQT_OK = False
    logger.warning("[Canvas] PyQt5 not available")

# Try theme import
try:
    from theme import (
        BG_MAIN, BG_INPUT, BG_SURFACE, BG_CARD, TEXT, TEXT_DIM,
        ACCENT, BORDER, FONT_FAMILY, FONT_SIZE_MD
    )
except ImportError:
    # Fallback theme values
    BG_MAIN = "#0f0f0f"
    BG_INPUT = "#1a1a1a"
    BG_SURFACE = "#141414"
    BG_CARD = "#1a1a1a"
    TEXT = "#e8e8e8"
    TEXT_DIM = "#9a9a9a"
    ACCENT = "#7c3aed"
    BORDER = "#252525"
    FONT_FAMILY = "Segoe UI"
    FONT_SIZE_MD = 14


class ContentType(Enum):
    """Supported content types for the canvas."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    MARKDOWN = "markdown"
    JSON = "json"
    TEXT = "text"


@dataclass
class CanvasState:
    """State of the canvas for persistence."""
    content: str = ""
    content_type: ContentType = ContentType.TEXT
    cursor_position: int = 0
    file_path: Optional[str] = None
    modified: bool = False


if PYQT_OK:
    class PythonHighlighter(QSyntaxHighlighter):
        """Syntax highlighter for Python code."""

        def __init__(self, document: QTextDocument):
            super().__init__(document)
            self._setup_formats()

        def _setup_formats(self):
            """Setup text formats for different token types."""
            # Keywords
            self.keyword_format = QTextCharFormat()
            self.keyword_format.setForeground(QColor("#c678dd"))  # Purple
            self.keyword_format.setFontWeight(QFont.Bold)

            # Strings
            self.string_format = QTextCharFormat()
            self.string_format.setForeground(QColor("#98c379"))  # Green

            # Comments
            self.comment_format = QTextCharFormat()
            self.comment_format.setForeground(QColor("#5c6370"))  # Gray
            self.comment_format.setFontItalic(True)

            # Functions
            self.function_format = QTextCharFormat()
            self.function_format.setForeground(QColor("#61afef"))  # Blue

            # Numbers
            self.number_format = QTextCharFormat()
            self.number_format.setForeground(QColor("#d19a66"))  # Orange

            # Decorators
            self.decorator_format = QTextCharFormat()
            self.decorator_format.setForeground(QColor("#e5c07b"))  # Yellow

            # Keywords list
            self.keywords = [
                'and', 'as', 'assert', 'async', 'await', 'break', 'class',
                'continue', 'def', 'del', 'elif', 'else', 'except', 'False',
                'finally', 'for', 'from', 'global', 'if', 'import', 'in',
                'is', 'lambda', 'None', 'nonlocal', 'not', 'or', 'pass',
                'raise', 'return', 'True', 'try', 'while', 'with', 'yield'
            ]

        def highlightBlock(self, text: str):
            """Apply syntax highlighting to a block of text."""
            import re

            # Keywords
            for keyword in self.keywords:
                pattern = rf'\b{keyword}\b'
                for match in re.finditer(pattern, text):
                    self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)

            # Strings (single and double quotes)
            string_patterns = [
                r'""".*?"""', r"'''.*?'''",  # Triple quotes
                r'"[^"\\]*(?:\\.[^"\\]*)*"',  # Double quotes
                r"'[^'\\]*(?:\\.[^'\\]*)*'"   # Single quotes
            ]
            for pattern in string_patterns:
                for match in re.finditer(pattern, text, re.DOTALL):
                    self.setFormat(match.start(), match.end() - match.start(), self.string_format)

            # Comments
            comment_pattern = r'#.*$'
            for match in re.finditer(comment_pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.comment_format)

            # Function definitions
            func_pattern = r'\bdef\s+(\w+)'
            for match in re.finditer(func_pattern, text):
                self.setFormat(match.start(1), match.end(1) - match.start(1), self.function_format)

            # Class definitions
            class_pattern = r'\bclass\s+(\w+)'
            for match in re.finditer(class_pattern, text):
                self.setFormat(match.start(1), match.end(1) - match.start(1), self.function_format)

            # Numbers
            number_pattern = r'\b\d+\.?\d*\b'
            for match in re.finditer(number_pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.number_format)

            # Decorators
            decorator_pattern = r'@\w+'
            for match in re.finditer(decorator_pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.decorator_format)


    class AICanvas(QWidget):
        """
        Interactive AI-assisted editing canvas.

        Features:
        - Syntax-highlighted code editor
        - AI suggestion panel
        - Multiple content types
        - Export functionality
        """

        # Signals
        content_changed = pyqtSignal(str)
        ai_request = pyqtSignal(str)  # Emitted when user requests AI help

        def __init__(self, ai_router=None, parent=None):
            super().__init__(parent)
            self.ai_router = ai_router
            self.state = CanvasState()
            self.highlighter = None
            self._suggestion_timer = None
            self._setup_ui()
            self._setup_connections()

        def _setup_ui(self):
            """Build the canvas UI."""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Toolbar
            toolbar = self._create_toolbar()
            layout.addWidget(toolbar)

            # Main splitter (editor + suggestions)
            splitter = QSplitter(Qt.Horizontal)
            splitter.setStyleSheet(f"""
                QSplitter::handle {{
                    background-color: {BORDER};
                    width: 2px;
                }}
            """)

            # Editor panel
            editor_frame = QFrame()
            editor_frame.setStyleSheet(f"background-color: {BG_INPUT}; border: none;")
            editor_layout = QVBoxLayout(editor_frame)
            editor_layout.setContentsMargins(8, 8, 8, 8)

            self.editor = QPlainTextEdit()
            self.editor.setFont(QFont("Consolas, Monaco, monospace", 12))
            self.editor.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {BG_INPUT};
                    color: {TEXT};
                    border: none;
                    selection-background-color: {ACCENT};
                    selection-color: white;
                }}
            """)
            self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.editor.setTabStopWidth(40)
            editor_layout.addWidget(self.editor)

            # Line number display
            self.status_bar = QLabel("Line 1, Col 1 | Text")
            self.status_bar.setStyleSheet(f"""
                QLabel {{
                    color: {TEXT_DIM};
                    font-size: 11px;
                    padding: 4px;
                    background-color: {BG_SURFACE};
                }}
            """)
            editor_layout.addWidget(self.status_bar)

            splitter.addWidget(editor_frame)

            # AI Suggestions panel
            suggestions_frame = QFrame()
            suggestions_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {BG_SURFACE};
                    border-left: 1px solid {BORDER};
                }}
            """)
            suggestions_layout = QVBoxLayout(suggestions_frame)
            suggestions_layout.setContentsMargins(8, 8, 8, 8)

            suggestions_header = QLabel("AI Suggestions")
            suggestions_header.setStyleSheet(f"""
                QLabel {{
                    color: {TEXT};
                    font-weight: bold;
                    font-size: 13px;
                    padding: 4px 0;
                }}
            """)
            suggestions_layout.addWidget(suggestions_header)

            self.suggestions_text = QTextEdit()
            self.suggestions_text.setReadOnly(True)
            self.suggestions_text.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {BG_CARD};
                    color: {TEXT};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                }}
            """)
            self.suggestions_text.setPlaceholderText("Select code and press Ctrl+Space for AI suggestions...")
            suggestions_layout.addWidget(self.suggestions_text)

            # Quick action buttons
            actions_layout = QHBoxLayout()
            actions_layout.setSpacing(8)

            self.explain_btn = QPushButton("Explain")
            self.fix_btn = QPushButton("Fix Issues")
            self.improve_btn = QPushButton("Improve")

            for btn in [self.explain_btn, self.fix_btn, self.improve_btn]:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {BG_INPUT};
                        color: {TEXT};
                        border: 1px solid {BORDER};
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        background-color: {ACCENT};
                        border-color: {ACCENT};
                    }}
                """)
                actions_layout.addWidget(btn)

            suggestions_layout.addLayout(actions_layout)
            splitter.addWidget(suggestions_frame)

            # Set splitter proportions (70% editor, 30% suggestions)
            splitter.setSizes([700, 300])
            layout.addWidget(splitter)

        def _create_toolbar(self) -> QToolBar:
            """Create the canvas toolbar."""
            toolbar = QToolBar()
            toolbar.setStyleSheet(f"""
                QToolBar {{
                    background-color: {BG_SURFACE};
                    border-bottom: 1px solid {BORDER};
                    padding: 4px;
                    spacing: 8px;
                }}
                QToolButton {{
                    background-color: transparent;
                    color: {TEXT};
                    border: none;
                    padding: 6px 10px;
                    border-radius: 4px;
                }}
                QToolButton:hover {{
                    background-color: {BG_INPUT};
                }}
            """)

            # Content type selector
            type_label = QLabel("Type: ")
            type_label.setStyleSheet(f"color: {TEXT_DIM}; margin-left: 8px;")
            toolbar.addWidget(type_label)

            self.type_selector = QComboBox()
            self.type_selector.addItems(["Python", "JavaScript", "Markdown", "JSON", "Text"])
            self.type_selector.setStyleSheet(f"""
                QComboBox {{
                    background-color: {BG_INPUT};
                    color: {TEXT};
                    border: 1px solid {BORDER};
                    border-radius: 4px;
                    padding: 4px 8px;
                    min-width: 100px;
                }}
                QComboBox::drop-down {{
                    border: none;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {BG_CARD};
                    color: {TEXT};
                    selection-background-color: {ACCENT};
                }}
            """)
            toolbar.addWidget(self.type_selector)

            toolbar.addSeparator()

            # File operations
            new_action = QAction("New", self)
            new_action.setShortcut(QKeySequence.New)
            new_action.triggered.connect(self.new_document)
            toolbar.addAction(new_action)

            open_action = QAction("Open", self)
            open_action.setShortcut(QKeySequence.Open)
            open_action.triggered.connect(self.open_file)
            toolbar.addAction(open_action)

            save_action = QAction("Save", self)
            save_action.setShortcut(QKeySequence.Save)
            save_action.triggered.connect(self.save_file)
            toolbar.addAction(save_action)

            toolbar.addSeparator()

            # AI actions
            ai_help = QAction("AI Help (Ctrl+Space)", self)
            ai_help.triggered.connect(self.request_ai_help)
            toolbar.addAction(ai_help)

            return toolbar

        def _setup_connections(self):
            """Setup signal/slot connections."""
            self.editor.textChanged.connect(self._on_text_changed)
            self.editor.cursorPositionChanged.connect(self._update_status)
            self.type_selector.currentTextChanged.connect(self._on_type_changed)

            self.explain_btn.clicked.connect(lambda: self._ai_action("explain"))
            self.fix_btn.clicked.connect(lambda: self._ai_action("fix"))
            self.improve_btn.clicked.connect(lambda: self._ai_action("improve"))

            # Setup suggestion timer for debounced AI suggestions
            self._suggestion_timer = QTimer()
            self._suggestion_timer.setSingleShot(True)
            self._suggestion_timer.timeout.connect(self._auto_suggest)

        def _on_text_changed(self):
            """Handle text changes."""
            self.state.content = self.editor.toPlainText()
            self.state.modified = True
            self.content_changed.emit(self.state.content)

            # Debounce auto-suggestions (2 second delay)
            if self._suggestion_timer:
                self._suggestion_timer.start(2000)

        def _on_type_changed(self, text: str):
            """Handle content type change."""
            type_map = {
                "Python": ContentType.PYTHON,
                "JavaScript": ContentType.JAVASCRIPT,
                "Markdown": ContentType.MARKDOWN,
                "JSON": ContentType.JSON,
                "Text": ContentType.TEXT,
            }
            self.state.content_type = type_map.get(text, ContentType.TEXT)
            self._apply_highlighter()
            self._update_status()

        def _apply_highlighter(self):
            """Apply syntax highlighter based on content type."""
            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None

            if self.state.content_type == ContentType.PYTHON:
                self.highlighter = PythonHighlighter(self.editor.document())

        def _update_status(self):
            """Update status bar with cursor position and type."""
            cursor = self.editor.textCursor()
            line = cursor.blockNumber() + 1
            col = cursor.columnNumber() + 1
            type_name = self.state.content_type.value.title()
            modified = "* " if self.state.modified else ""
            self.status_bar.setText(f"{modified}Line {line}, Col {col} | {type_name}")

        def _auto_suggest(self):
            """Auto-suggest improvements based on current code."""
            if not self.ai_router:
                return

            # Only suggest for code content
            if self.state.content_type not in [ContentType.PYTHON, ContentType.JAVASCRIPT]:
                return

            code = self.editor.toPlainText().strip()
            if len(code) < 20:
                return

            # Get suggestions in background
            self._ai_action("suggest", silent=True)

        def _ai_action(self, action: str, silent: bool = False):
            """Perform an AI action on the selected or all code."""
            if not self.ai_router:
                self.suggestions_text.setText("AI router not available.")
                return

            cursor = self.editor.textCursor()
            code = cursor.selectedText() if cursor.hasSelection() else self.editor.toPlainText()

            if not code.strip():
                if not silent:
                    self.suggestions_text.setText("No code to analyze.")
                return

            prompts = {
                "explain": f"Explain this {self.state.content_type.value} code clearly and concisely:\n\n{code}",
                "fix": f"Find and fix any bugs or issues in this {self.state.content_type.value} code. Return the corrected code with brief explanations:\n\n{code}",
                "improve": f"Suggest improvements for this {self.state.content_type.value} code (performance, readability, best practices):\n\n{code}",
                "suggest": f"Provide quick tips for this {self.state.content_type.value} code (max 3 bullet points):\n\n{code[:500]}",
            }

            prompt = prompts.get(action, prompts["explain"])

            try:
                if not silent:
                    self.suggestions_text.setText("Analyzing...")

                response = self.ai_router.query(prompt)
                self.suggestions_text.setText(response)
            except Exception as e:
                if not silent:
                    self.suggestions_text.setText(f"AI Error: {e}")

        def request_ai_help(self):
            """Request AI help for selected code."""
            self._ai_action("explain")
            self.ai_request.emit(self.editor.textCursor().selectedText() or self.editor.toPlainText())

        def new_document(self):
            """Create a new document."""
            self.editor.clear()
            self.state = CanvasState()
            self.suggestions_text.clear()
            self._update_status()

        def open_file(self):
            """Open a file into the canvas."""
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Open File", "",
                "Python (*.py);;JavaScript (*.js);;Markdown (*.md);;JSON (*.json);;All Files (*.*)"
            )

            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.editor.setPlainText(content)
                    self.state.file_path = file_path
                    self.state.modified = False

                    # Auto-detect type
                    ext = os.path.splitext(file_path)[1].lower()
                    type_map = {".py": "Python", ".js": "JavaScript", ".md": "Markdown", ".json": "JSON"}
                    if ext in type_map:
                        self.type_selector.setCurrentText(type_map[ext])

                    self._update_status()
                except Exception as e:
                    self.suggestions_text.setText(f"Error opening file: {e}")

        def save_file(self):
            """Save the current document."""
            if not self.state.file_path:
                self.state.file_path, _ = QFileDialog.getSaveFileName(
                    self, "Save File", "",
                    "Python (*.py);;JavaScript (*.js);;Markdown (*.md);;JSON (*.json);;All Files (*.*)"
                )

            if self.state.file_path:
                try:
                    with open(self.state.file_path, 'w', encoding='utf-8') as f:
                        f.write(self.editor.toPlainText())
                    self.state.modified = False
                    self._update_status()
                    self.suggestions_text.setText(f"Saved: {self.state.file_path}")
                except Exception as e:
                    self.suggestions_text.setText(f"Error saving file: {e}")

        def set_content(self, content: str, content_type: ContentType = ContentType.TEXT):
            """Set the canvas content programmatically."""
            self.editor.setPlainText(content)
            self.state.content = content
            self.state.content_type = content_type

            type_names = {
                ContentType.PYTHON: "Python",
                ContentType.JAVASCRIPT: "JavaScript",
                ContentType.MARKDOWN: "Markdown",
                ContentType.JSON: "JSON",
                ContentType.TEXT: "Text",
            }
            self.type_selector.setCurrentText(type_names.get(content_type, "Text"))

        def get_content(self) -> str:
            """Get the current canvas content."""
            return self.editor.toPlainText()

        def get_state(self) -> CanvasState:
            """Get the current canvas state."""
            self.state.content = self.editor.toPlainText()
            self.state.cursor_position = self.editor.textCursor().position()
            return self.state


else:
    # Stub class when PyQt5 is not available
    class AICanvas:
        def __init__(self, *args, **kwargs):
            logger.warning("[Canvas] PyQt5 not available - AICanvas disabled")

        def set_content(self, *args, **kwargs):
            pass

        def get_content(self) -> str:
            return ""


def create_canvas(ai_router=None, parent=None) -> Optional['AICanvas']:
    """Factory function to create an AICanvas instance."""
    if not PYQT_OK:
        logger.warning("[Canvas] Cannot create AICanvas - PyQt5 not available")
        return None
    return AICanvas(ai_router=ai_router, parent=parent)
