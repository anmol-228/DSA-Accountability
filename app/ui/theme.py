"""Design tokens + QSS generator for the whole application.

Single source of truth for color, typography, spacing, and radius so no
widget hardcodes its own styling. "Mono Light" is the default (matches a
light desktop); "Mono Dark" is available as an alternative. Both are pure
grayscale with restrained, desaturated semantic accents (never bright
orange/green/red) per the visual redesign brief.

This module is presentation-only — it has no knowledge of curriculum,
progression, or any business logic.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str
    surface: str
    surface_alt: str
    hover: str
    active: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    border: str
    divider: str
    btn_dark: str
    btn_dark_hover: str
    btn_dark_text: str
    btn_secondary: str
    btn_secondary_hover: str
    success: str
    warning: str
    error: str
    shadow: str
    scrollbar_thumb: str
    scrollbar_thumb_hover: str


MONO_LIGHT = Palette(
    name="mono_light",
    surface="#FAFAFA",
    surface_alt="#F0F0F0",
    hover="#E9E9E9",
    active="#E2E2E2",
    text_primary="#181818",
    text_secondary="#63636B",
    text_tertiary="#8C8C93",
    border="#DBDBDF",
    divider="#E5E5E8",
    btn_dark="#242424",
    btn_dark_hover="#343434",
    btn_dark_text="#FFFFFF",
    btn_secondary="#ECECEE",
    btn_secondary_hover="#E1E1E4",
    success="#5C8A5B",
    warning="#A9895A",
    error="#B15852",
    shadow="rgba(20, 20, 20, 90)",
    scrollbar_thumb="#C7C7CC",
    scrollbar_thumb_hover="#AFAFB6",
)

MONO_DARK = Palette(
    name="mono_dark",
    surface="#1E1E20",
    surface_alt="#28282B",
    hover="#323235",
    active="#3A3A3E",
    text_primary="#F1F1F3",
    text_secondary="#B4B4BA",
    text_tertiary="#87878E",
    border="#3A3A3E",
    divider="#333336",
    btn_dark="#F1F1F3",
    btn_dark_hover="#FFFFFF",
    btn_dark_text="#181818",
    btn_secondary="#2E2E31",
    btn_secondary_hover="#38383C",
    success="#7CA97A",
    warning="#C4A06B",
    error="#C97871",
    shadow="rgba(0, 0, 0, 160)",
    scrollbar_thumb="#4A4A4E",
    scrollbar_thumb_hover="#5C5C61",
)


class Spacing:
    MICRO = 4
    SMALL = 8
    NORMAL = 12
    MEDIUM = 16
    SECTION = 22
    MAJOR = 30


class Radius:
    TASK_HOVER = 7
    BUTTON = 9
    CARD = 13
    WINDOW = 18


class Font:
    FAMILY = '"Segoe UI Variable", "Segoe UI", sans-serif'
    APP_LABEL = 11
    DAY_INDICATOR = 19
    TOPIC = 14
    SECTION_HEADING = 10.5
    TASK = 12.5
    METADATA = 10.5
    BODY = 12.5


def get_palette(name: str = "mono_light") -> Palette:
    return MONO_DARK if name == "mono_dark" else MONO_LIGHT


def _checkmark_asset_path() -> str:
    """Ensures a small white-checkmark PNG exists on disk and returns its
    path in QSS url() form (forward slashes, required even on Windows).
    Native QCheckBox can't paint a checkmark glyph via QSS colors alone —
    see icons.write_checkbox_check_asset for why this is the one runtime
    file asset in an otherwise asset-free UI."""
    from app import config
    from app.ui import icons

    path = config.DATA_DIR / "checkbox_check.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        icons.write_checkbox_check_asset(path)
    return str(path).replace("\\", "/")


def build_qss(p: Palette) -> str:
    """Global application stylesheet. Widgets opt into variants via the Qt
    dynamic `property` mechanism, e.g. button.setProperty("variant", "primary")
    followed by style().polish(button)."""
    checkmark_url = _checkmark_asset_path()
    return f"""
    * {{
        font-family: {Font.FAMILY};
        outline: none;
    }}

    QWidget {{
        background: {p.surface};
        color: {p.text_primary};
        font-size: {Font.BODY}pt;
    }}

    QDialog {{
        background: {p.surface};
    }}

    QLabel {{
        background: transparent;
    }}

    QLabel[role="app-label"] {{
        color: {p.text_secondary};
        font-size: {Font.APP_LABEL}pt;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    QLabel[role="day-indicator"] {{
        color: {p.text_primary};
        font-size: {Font.DAY_INDICATOR}pt;
        font-weight: 700;
    }}

    QLabel[role="topic"] {{
        color: {p.text_secondary};
        font-size: {Font.TOPIC}pt;
        font-weight: 500;
        font-style: normal;
    }}

    QLabel[role="section-heading"] {{
        color: {p.text_tertiary};
        font-size: {Font.SECTION_HEADING}pt;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}

    QLabel[role="metadata"] {{
        color: {p.text_tertiary};
        font-size: {Font.METADATA}pt;
    }}

    QLabel[role="metadata-strong"] {{
        color: {p.text_secondary};
        font-size: {Font.METADATA}pt;
        font-weight: 600;
    }}

    QLabel[role="body"] {{
        color: {p.text_primary};
        font-size: {Font.BODY}pt;
    }}

    QFrame[role="divider"] {{
        background: {p.divider};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}

    QFrame[role="card"] {{
        background: {p.surface_alt};
        border-radius: {Radius.CARD}px;
    }}

    QPushButton {{
        border: none;
        border-radius: {Radius.BUTTON}px;
        padding: 7px 14px;
        font-size: {Font.BODY}pt;
        font-weight: 600;
        background: {p.btn_secondary};
        color: {p.text_primary};
    }}
    QPushButton:hover {{ background: {p.btn_secondary_hover}; }}
    QPushButton:disabled {{ color: {p.text_tertiary}; }}

    QPushButton[variant="primary"] {{
        background: {p.btn_dark};
        color: {p.btn_dark_text};
    }}
    QPushButton[variant="primary"]:hover {{ background: {p.btn_dark_hover}; }}

    QPushButton[variant="tertiary"] {{
        background: transparent;
        color: {p.text_secondary};
        font-weight: 500;
        padding: 6px 10px;
    }}
    QPushButton[variant="tertiary"]:hover {{
        background: {p.hover};
        color: {p.text_primary};
    }}

    QPushButton[variant="icon"] {{
        background: transparent;
        border-radius: 14px;
        padding: 0px;
    }}
    QPushButton[variant="icon"]:hover {{
        background: {p.hover};
    }}

    QLineEdit, QTextEdit {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: {p.active};
        color: {p.text_primary};
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border: 1px solid {p.text_tertiary};
    }}

    QRadioButton {{
        spacing: 6px;
        color: {p.text_primary};
        font-size: {Font.BODY}pt;
    }}
    QRadioButton::indicator {{
        width: 15px; height: 15px;
        border-radius: 8px;
        border: 1.5px solid {p.border};
        background: {p.surface};
    }}
    QRadioButton::indicator:checked {{
        border: 1.5px solid {p.btn_dark};
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
            stop:0 {p.btn_dark}, stop:0.55 {p.btn_dark}, stop:0.65 {p.surface}, stop:1 {p.surface});
    }}

    QCheckBox {{
        spacing: 8px;
        color: {p.text_primary};
        font-size: {Font.TASK}pt;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 4px;
        border: 1.5px solid {p.text_tertiary};
        background: {p.surface};
    }}
    QCheckBox::indicator:checked {{
        border: 1.5px solid {p.btn_dark};
        background: {p.btn_dark};
        image: url({checkmark_url});
    }}

    QListWidget, QTableWidget {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 10px;
        alternate-background-color: {p.surface_alt};
        gridline-color: {p.divider};
    }}
    QHeaderView::section {{
        background: {p.surface_alt};
        color: {p.text_secondary};
        border: none;
        padding: 4px 6px;
        font-weight: 600;
        font-size: {Font.METADATA}pt;
    }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}

    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 2px 0px 2px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.scrollbar_thumb};
        min-height: 24px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.scrollbar_thumb_hover}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    QScrollBar:horizontal {{ height: 0px; }}

    QLabel[role="chip"] {{
        border-radius: 9px;
        padding: 3px 10px;
        font-size: {Font.METADATA}pt;
        font-weight: 600;
        background: {p.surface_alt};
        color: {p.text_secondary};
    }}
    QLabel[role="chip"][kind="success"] {{ color: {p.success}; }}
    QLabel[role="chip"][kind="warning"] {{ color: {p.warning}; }}
    QLabel[role="chip"][kind="error"] {{ color: {p.error}; }}

    QMenu {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 12px;
        border-radius: 6px;
        color: {p.text_primary};
    }}
    QMenu::item:selected {{ background: {p.hover}; }}
    """
