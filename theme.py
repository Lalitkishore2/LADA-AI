"""
LADA Unified Theme
==================
Extracted from lada_desktop_app.py -- single source of truth for all
color constants, typography, semantic tokens, and the global QSS stylesheet
applied to every PyQt5 widget in the desktop application.

Import example::

    from theme import (
        BG_MAIN, TEXT, ACCENT, FONT_FAMILY, GLOBAL_QSS,
        header_button_style,
    )

The palette is designed to match the LADA web app CSS custom properties
(--bg, --surface, --accent, etc.) so both interfaces stay visually
consistent.
"""

# ═══════════════════════════════════════════════════════════════════════
# Colors - LADA Unified Palette (matching web app)
# ═══════════════════════════════════════════════════════════════════════
BG_MAIN = "#0f0f0f"    # Main background - deep dark (matches web --bg)
BG_SIDE = "#0a0a0a"    # Sidebar - deepest dark (matches web --surface)
BG_INPUT = "#1a1a1a"   # Input field background (matches web --surface2)
BG_HOVER = "#2a2a2a"   # Hover state
BG_CARD = "#1a1a1a"    # Card / bubble / elevated surface
BG_SURFACE = "#141414" # Raised surface (panels, overlays)
TEXT = "#e8e8e8"       # Primary text - soft white
TEXT_DIM = "#9a9a9a"   # Secondary / dimmed text
GREEN = "#10a37f"      # ChatGPT-style green accent (matches refreshed web --accent)
ACCENT = GREEN         # Canonical name for the accent color
ACCENT_GRADIENT_END = "#0f8f70"  # Darker green for gradient end
ACCENT_DARK = ACCENT_GRADIENT_END  # Alias
ACCENT_LIGHT = "rgba(16,163,127,0.15)"  # Light accent for hover states
BLUE = "#3b82f6"       # Blue accent
PURPLE = "#9b59b6"     # Purple accent (legacy)
RED = "#ef4444"        # Error red
BORDER = "#252525"     # Border color - subtle separator
BORDER_FOCUS = "#10a37f"  # Focus ring color - green accent

# ═══════════════════════════════════════════════════════════════════════
# Typography
# ═══════════════════════════════════════════════════════════════════════
FONT_FAMILY = "Manrope, Avenir Next, Nunito Sans, Segoe UI, sans-serif"
FONT_HEADING = "Segoe UI Semibold"
FONT_SIZE_SM = 12
FONT_SIZE_MD = 14
FONT_SIZE_LG = 16
FONT_SIZE_XL = 28

# ═══════════════════════════════════════════════════════════════════════
# Layout Tokens (Desktop)
# ═══════════════════════════════════════════════════════════════════════
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16
SPACING_XL = 24

CONTROL_ICON_SIZE = 32
CONTROL_TOOLBAR_BUTTON_SIZE = 26

APP_COLUMN_MAX_WIDTH = 920
APP_INPUT_MAX_WIDTH = 880
APP_WELCOME_GRID_MAX_WIDTH = 760
APP_SUGGESTION_CARD_MIN_HEIGHT = 72
APP_ASSISTANT_TEXT_MAX_WIDTH = 760
APP_USER_TEXT_MAX_WIDTH = 700

# ═══════════════════════════════════════════════════════════════════════
# Semantic colors
# ═══════════════════════════════════════════════════════════════════════
SUCCESS = "#22c55e"    # Green for success states
WARNING = "#f59e0b"    # Amber for warnings
INFO = BLUE            # Blue for informational

# ═══════════════════════════════════════════════════════════════════════
# Global QSS Theme
# ═══════════════════════════════════════════════════════════════════════
# Applied via app.setStyleSheet(GLOBAL_QSS) -- cascades to ALL child widgets.
# This eliminates most inline setStyleSheet() calls.
GLOBAL_QSS = f"""
/* ═══ Base ═══ */
QMainWindow, QDialog {{
    background: {BG_MAIN}; color: {TEXT};
    font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_MD}px;
}}
QFrame {{ background: transparent; border: none; }}
QLabel {{ color: {TEXT}; background: transparent; }}

/* ═══ Scrollbars ═══ */
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.12); border-radius: 3px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.25); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent; height: 6px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255,255,255,0.12); border-radius: 3px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: rgba(255,255,255,0.25); }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ═══ Buttons ═══ */
QPushButton {{
    background: {BG_HOVER}; color: {TEXT};
    border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 13px;
    font-family: {FONT_FAMILY};
}}
QPushButton:hover {{ background: {BG_CARD}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: rgba(255,255,255,0.03); }}

/* ═══ Inputs ═══ */
QLineEdit {{
    background: {BG_INPUT}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 12px; font-size: 13px;
    font-family: {FONT_FAMILY};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QTextEdit {{
    background: {BG_INPUT}; color: {TEXT};
    border: none;
    selection-background-color: {ACCENT};
    font-family: {FONT_FAMILY};
}}

/* ═══ Combo Boxes ═══ */
QComboBox {{
    background: {BG_INPUT}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 12px;
    font-family: {FONT_FAMILY};
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_SURFACE}; color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {BG_HOVER};
    padding: 4px;
    font-family: {FONT_FAMILY};
}}

/* ═══ Lists ═══ */
QListWidget {{
    background: transparent; border: none; outline: none;
    font-family: {FONT_FAMILY};
}}
QListWidget::item {{
    background: transparent; color: {TEXT_DIM};
    padding: 10px 12px; border-radius: 8px; border: none;
}}
QListWidget::item:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
QListWidget::item:selected {{
    background: {BG_HOVER}; color: {TEXT};
    border-left: 3px solid {ACCENT};
}}

/* ═══ Checkboxes ═══ */
QCheckBox {{ color: {TEXT}; spacing: 8px; font-family: {FONT_FAMILY}; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 4px;
    border: 2px solid {BORDER}; background: transparent;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ═══ Sliders ═══ */
QSlider::groove:horizontal {{ background: {BG_INPUT}; height: 6px; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 16px; height: 16px;
    margin: -5px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}

/* ═══ Tooltips ═══ */
QToolTip {{
    background: {BG_SURFACE}; color: {TEXT};
    border: 1px solid {BORDER}; padding: 6px 10px;
    border-radius: 6px; font-size: 12px;
    font-family: {FONT_FAMILY};
}}

/* ═══ Tab Widgets ═══ */
QTabWidget::pane {{ border: 1px solid {BORDER}; background: {BG_MAIN}; border-radius: 8px; }}
QTabBar::tab {{
    background: {BG_SURFACE}; color: {TEXT_DIM};
    padding: 8px 16px; border: none;
    font-family: {FONT_FAMILY};
}}
QTabBar::tab:selected {{ background: {BG_MAIN}; color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* ═══ Group Boxes ═══ */
QGroupBox {{
    background: rgba(255,255,255,0.02);
    border: 1px solid {BORDER}; border-radius: 10px;
    margin-top: 12px; padding-top: 24px;
    font-weight: 600; color: {TEXT};
    font-family: {FONT_FAMILY};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 16px;
    padding: 0 8px; color: {TEXT};
}}

/* ═══ Scroll Areas ═══ */
QScrollArea {{ background: {BG_MAIN}; border: none; }}

/* ═══ Message Boxes / Dialogs ═══ */
QMessageBox {{ background: {BG_SURFACE}; color: {TEXT}; }}
QMessageBox QPushButton {{ min-width: 80px; padding: 8px 20px; }}
QMessageBox QPushButton:default {{ background: {ACCENT}; color: white; }}

/* ═══ Menu ═══ */
QMenu {{
    background: {BG_SURFACE}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 10px;
    padding: 6px; font-family: {FONT_FAMILY};
}}
QMenu::item {{ padding: 8px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: {BG_HOVER}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

/* ═══ Spin Boxes ═══ */
QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px;
    padding: 4px 8px; font-family: {FONT_FAMILY};
}}

/* ═══ Progress Bar ═══ */
QProgressBar {{
    background: {BG_INPUT}; border: none; border-radius: 4px;
    height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
"""


# ═══════════════════════════════════════════════════════════════════════
# Helper utilities
# ═══════════════════════════════════════════════════════════════════════

def header_button_style() -> str:
    """Return the inline QSS for a compact, borderless, translucent header /
    sidebar button.

    This style is shared by the sidebar bottom-row buttons (Export Chat,
    Settings, Session, Cost) and any other small utility button that should
    blend into the dark chrome.

    Usage::

        btn = QPushButton("  Settings")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(header_button_style())
    """
    return f"""
        QPushButton {{
            background: transparent; color: {TEXT_DIM};
            border: none; border-radius: 8px;
            padding: 9px 10px; font-size: 13px; text-align: left;
        }}
        QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT}; }}
    """
