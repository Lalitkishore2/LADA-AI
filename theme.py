"""
LADA Unified Theme
==================
Extracted from lada_desktop_app.py -- single source of truth for all
color constants, typography, semantic tokens, and the global QSS stylesheet
applied to every PyQt5 widget in the desktop application.

Import example::

    from theme import (
        BG_MAIN, TEXT, ACCENT, FONT_FAMILY, GLOBAL_QSS,
        header_button_style, get_theme_colors, set_theme_mode,
    )

The palette is designed to match the LADA web app CSS custom properties
(--bg, --surface, --accent, etc.) so both interfaces stay visually
consistent. Supports both dark and light modes.
"""

# ═══════════════════════════════════════════════════════════════════════
# Theme Mode
# ═══════════════════════════════════════════════════════════════════════
_current_theme = "dark"  # "dark" or "light"

# ═══════════════════════════════════════════════════════════════════════
# Dark Mode Colors - LADA Unified Palette (matching web app)
# ═══════════════════════════════════════════════════════════════════════
_DARK = {
    "BG_MAIN": "#0f0f0f",    # Main background - deep dark
    "BG_SIDE": "#0a0a0a",    # Sidebar - deepest dark
    "BG_INPUT": "#1a1a1a",   # Input field background
    "BG_HOVER": "#2a2a2a",   # Hover state
    "BG_CARD": "#1a1a1a",    # Card / bubble / elevated surface
    "BG_SURFACE": "#141414", # Raised surface (panels, overlays)
    "TEXT": "#e8e8e8",       # Primary text - soft white
    "TEXT_DIM": "#9a9a9a",   # Secondary / dimmed text
    "BORDER": "#252525",     # Border color - subtle separator
    "SCROLLBAR_BG": "transparent",
    "SCROLLBAR_HANDLE": "rgba(255,255,255,0.12)",
    "SCROLLBAR_HANDLE_HOVER": "rgba(255,255,255,0.25)",
}

# ═══════════════════════════════════════════════════════════════════════
# Light Mode Colors - Clean, professional light theme
# ═══════════════════════════════════════════════════════════════════════
_LIGHT = {
    "BG_MAIN": "#ffffff",    # Main background - pure white
    "BG_SIDE": "#f5f5f5",    # Sidebar - light gray
    "BG_INPUT": "#f0f0f0",   # Input field background
    "BG_HOVER": "#e8e8e8",   # Hover state
    "BG_CARD": "#f8f8f8",    # Card / bubble / elevated surface
    "BG_SURFACE": "#fafafa", # Raised surface (panels, overlays)
    "TEXT": "#1a1a1a",       # Primary text - dark
    "TEXT_DIM": "#666666",   # Secondary / dimmed text
    "BORDER": "#e0e0e0",     # Border color - subtle separator
    "SCROLLBAR_BG": "transparent",
    "SCROLLBAR_HANDLE": "rgba(0,0,0,0.15)",
    "SCROLLBAR_HANDLE_HOVER": "rgba(0,0,0,0.30)",
}

def get_theme_colors():
    """Get current theme color dictionary."""
    return _DARK if _current_theme == "dark" else _LIGHT

def set_theme_mode(mode: str):
    """Set theme mode ('dark' or 'light')."""
    global _current_theme, BG_MAIN, BG_SIDE, BG_INPUT, BG_HOVER, BG_CARD
    global BG_SURFACE, TEXT, TEXT_DIM, BORDER, GLOBAL_QSS
    _current_theme = mode
    colors = get_theme_colors()
    BG_MAIN = colors["BG_MAIN"]
    BG_SIDE = colors["BG_SIDE"]
    BG_INPUT = colors["BG_INPUT"]
    BG_HOVER = colors["BG_HOVER"]
    BG_CARD = colors["BG_CARD"]
    BG_SURFACE = colors["BG_SURFACE"]
    TEXT = colors["TEXT"]
    TEXT_DIM = colors["TEXT_DIM"]
    BORDER = colors["BORDER"]
    GLOBAL_QSS = _build_qss(colors)
    return GLOBAL_QSS

def get_theme_mode():
    """Get current theme mode."""
    return _current_theme

# Initialize with dark mode defaults
BG_MAIN = _DARK["BG_MAIN"]
BG_SIDE = _DARK["BG_SIDE"]
BG_INPUT = _DARK["BG_INPUT"]
BG_HOVER = _DARK["BG_HOVER"]
BG_CARD = _DARK["BG_CARD"]
BG_SURFACE = _DARK["BG_SURFACE"]
TEXT = _DARK["TEXT"]
TEXT_DIM = _DARK["TEXT_DIM"]
BORDER = _DARK["BORDER"]

# Accent colors (same for both themes)
GREEN = "#10a37f"      # ChatGPT-style green accent
ACCENT = GREEN
ACCENT_GRADIENT_END = "#0f8f70"
ACCENT_DARK = ACCENT_GRADIENT_END
ACCENT_LIGHT = "rgba(16,163,127,0.15)"
BLUE = "#3b82f6"
PURPLE = "#9b59b6"
RED = "#ef4444"
BORDER_FOCUS = "#10a37f"

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
# Global QSS Theme Builder
# ═══════════════════════════════════════════════════════════════════════
def _build_qss(colors: dict = None) -> str:
    """Build the global QSS stylesheet for the given theme colors."""
    if colors is None:
        colors = get_theme_colors()
    
    bg_main = colors["BG_MAIN"]
    bg_side = colors["BG_SIDE"]
    bg_input = colors["BG_INPUT"]
    bg_hover = colors["BG_HOVER"]
    bg_card = colors["BG_CARD"]
    bg_surface = colors["BG_SURFACE"]
    text = colors["TEXT"]
    text_dim = colors["TEXT_DIM"]
    border = colors["BORDER"]
    scrollbar_handle = colors.get("SCROLLBAR_HANDLE", "rgba(255,255,255,0.12)")
    scrollbar_handle_hover = colors.get("SCROLLBAR_HANDLE_HOVER", "rgba(255,255,255,0.25)")
    
    return f"""
/* ═══ Base ═══ */
QMainWindow, QDialog {{
    background: {bg_main}; color: {text};
    font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_MD}px;
}}
QFrame {{ background: transparent; border: none; }}
QLabel {{ color: {text}; background: transparent; }}

/* ═══ Scrollbars ═══ */
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {scrollbar_handle}; border-radius: 3px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {scrollbar_handle_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent; height: 6px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {scrollbar_handle}; border-radius: 3px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {scrollbar_handle_hover}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ═══ Buttons ═══ */
QPushButton {{
    background: {bg_hover}; color: {text};
    border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 13px;
    font-family: {FONT_FAMILY};
}}
QPushButton:hover {{ background: {bg_card}; }}
QPushButton:pressed {{ background: {border}; }}
QPushButton:disabled {{ color: {text_dim}; background: rgba(128,128,128,0.1); }}

/* ═══ Inputs ═══ */
QLineEdit {{
    background: {bg_input}; color: {text};
    border: 1px solid {border}; border-radius: 8px;
    padding: 8px 12px; font-size: 13px;
    font-family: {FONT_FAMILY};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QTextEdit {{
    background: {bg_input}; color: {text};
    border: none;
    selection-background-color: {ACCENT};
    font-family: {FONT_FAMILY};
}}

/* ═══ Combo Boxes ═══ */
QComboBox {{
    background: {bg_input}; color: {text};
    border: 1px solid {border}; border-radius: 8px;
    padding: 6px 12px;
    font-family: {FONT_FAMILY};
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {bg_surface}; color: {text};
    border: 1px solid {border};
    selection-background-color: {bg_hover};
    padding: 4px;
    font-family: {FONT_FAMILY};
}}

/* ═══ Lists ═══ */
QListWidget {{
    background: transparent; border: none; outline: none;
    font-family: {FONT_FAMILY};
}}
QListWidget::item {{
    background: transparent; color: {text_dim};
    padding: 10px 12px; border-radius: 8px; border: none;
}}
QListWidget::item:hover {{ background: {bg_hover}; color: {text}; }}
QListWidget::item:selected {{
    background: {bg_hover}; color: {text};
    border-left: 3px solid {ACCENT};
}}

/* ═══ Checkboxes ═══ */
QCheckBox {{ color: {text}; spacing: 8px; font-family: {FONT_FAMILY}; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 4px;
    border: 2px solid {border}; background: transparent;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ═══ Sliders ═══ */
QSlider::groove:horizontal {{ background: {bg_input}; height: 6px; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 16px; height: 16px;
    margin: -5px 0; border-radius: 8px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}

/* ═══ Tooltips ═══ */
QToolTip {{
    background: {bg_surface}; color: {text};
    border: 1px solid {border}; padding: 6px 10px;
    border-radius: 6px; font-size: 12px;
    font-family: {FONT_FAMILY};
}}

/* ═══ Tab Widgets ═══ */
QTabWidget::pane {{ border: 1px solid {border}; background: {bg_main}; border-radius: 8px; }}
QTabBar::tab {{
    background: {bg_surface}; color: {text_dim};
    padding: 8px 16px; border: none;
    font-family: {FONT_FAMILY};
}}
QTabBar::tab:selected {{ background: {bg_main}; color: {text}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {text}; }}

/* ═══ Group Boxes ═══ */
QGroupBox {{
    background: rgba(128,128,128,0.05);
    border: 1px solid {border}; border-radius: 10px;
    margin-top: 12px; padding-top: 24px;
    font-weight: 600; color: {text};
    font-family: {FONT_FAMILY};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 16px;
    padding: 0 8px; color: {text};
}}

/* ═══ Scroll Areas ═══ */
QScrollArea {{ background: {bg_main}; border: none; }}

/* ═══ Message Boxes / Dialogs ═══ */
QMessageBox {{ background: {bg_surface}; color: {text}; }}
QMessageBox QPushButton {{ min-width: 80px; padding: 8px 20px; }}
QMessageBox QPushButton:default {{ background: {ACCENT}; color: white; }}

/* ═══ Menu ═══ */
QMenu {{
    background: {bg_surface}; color: {text};
    border: 1px solid {border}; border-radius: 10px;
    padding: 6px; font-family: {FONT_FAMILY};
}}
QMenu::item {{ padding: 8px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: {bg_hover}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}

/* ═══ Spin Boxes ═══ */
QSpinBox, QDoubleSpinBox {{
    background: {bg_input}; color: {text};
    border: 1px solid {border}; border-radius: 6px;
    padding: 4px 8px; font-family: {FONT_FAMILY};
}}

/* ═══ Progress Bar ═══ */
QProgressBar {{
    background: {bg_input}; border: none; border-radius: 4px;
    height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
"""

# Build initial QSS with dark theme
GLOBAL_QSS = _build_qss(_DARK)


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
    colors = get_theme_colors()
    text_dim = colors["TEXT_DIM"]
    text = colors["TEXT"]
    bg_hover = colors["BG_HOVER"]
    return f"""
        QPushButton {{
            background: transparent; color: {text_dim};
            border: none; border-radius: 8px;
            padding: 9px 10px; font-size: 13px; text-align: left;
        }}
        QPushButton:hover {{ background: {bg_hover}; color: {text}; }}
    """


def toggle_theme():
    """Toggle between dark and light mode. Returns new QSS."""
    global GLOBAL_QSS
    new_mode = "light" if get_theme_mode() == "dark" else "dark"
    GLOBAL_QSS = set_theme_mode(new_mode)
    return GLOBAL_QSS
