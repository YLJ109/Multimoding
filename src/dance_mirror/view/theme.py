"""Fluent theme integration for the DanceMirror desktop application."""

from __future__ import annotations

import logging

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from dance_mirror.view.design_tokens import DARK_PALETTE, LIGHT_PALETTE, UiPalette
from dance_mirror.view.fluent import (
    FLUENT_AVAILABLE,
    Theme,
    setTheme,
    setThemeColor,
)

LOGGER = logging.getLogger(__name__)


def resolve_theme(theme: str) -> str:
    """Resolve one persisted theme name to a supported Fluent theme."""
    return "dark" if str(theme).strip().lower() == "dark" else "light"


def build_theme_stylesheet(colors: UiPalette) -> str:
    """Return a narrow Qt stylesheet that keeps native popups theme-aware."""
    return f"""
QComboBox QAbstractItemView {{
    background-color: {colors.surface_raised};
    color: {colors.text};
    border: 1px solid {colors.border};
    selection-background-color: {colors.primary_soft};
    selection-color: {colors.text};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {colors.primary_soft};
}}
QMenu {{
    background-color: {colors.surface_raised};
    color: {colors.text};
    border: 1px solid {colors.border};
}}
QMenu::item {{
    padding: 6px 18px;
}}
QMenu::item:selected {{
    background-color: {colors.primary_soft};
}}
QToolTip {{
    background-color: {colors.hud_background};
    color: {colors.hud_text};
    border: 1px solid {colors.border};
}}
QFrame#dance-package-card,
QFrame#status-card,
QFrame#surface-card,
QFrame#metric-card,
QFrame#report-card,
QFrame#transcript-card {{
    background-color: {colors.surface_raised};
    border: 1px solid {colors.border};
    border-radius: 8px;
}}
QFrame#dance-package-card:hover {{
    border-color: {colors.focus};
    background-color: {colors.surface_alt};
}}
QWidget#inspector-panel,
QWidget#hud-panel {{
    background-color: transparent;
    border: none;
}}
QLabel#section-title {{
    color: {colors.text_soft};
    font-weight: 600;
    font-size: 13px;
}}
QLabel#workspace-title {{
    color: {colors.text};
    font-weight: 700;
    font-size: 20px;
}}
QLabel#metric-label {{
    color: {colors.muted};
    font-size: 11px;
}}
QLabel#metric-value {{
    color: {colors.text};
    font-weight: 700;
    font-size: 18px;
}}
QLabel#metric-caption,
QLabel#mono-muted {{
    color: {colors.muted};
    font-size: 12px;
}}
QLabel#coach-label {{
    color: {colors.text_soft};
    font-size: 13px;
}}
QLabel#countdown-label {{
    color: {colors.focus};
    font-weight: 700;
    font-size: 34px;
}}
QLabel#status-pill,
QLabel#quality-pill {{
    background-color: {colors.primary_soft};
    color: {colors.text};
    border-radius: 10px;
    padding: 2px 9px;
}}
QLineEdit {{
    background-color: {colors.surface};
    color: {colors.text};
    border: 1px solid {colors.border};
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: {colors.primary_soft};
}}
QLineEdit:focus {{
    border-color: {colors.focus};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {colors.border_strong};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {colors.primary};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {colors.border_strong};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {colors.primary};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {colors.border};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {colors.primary};
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QProgressBar {{
    background-color: {colors.surface};
    color: {colors.text};
    border: 1px solid {colors.border};
    border-radius: 5px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {colors.primary};
    border-radius: 4px;
}}
"""


def _build_palette(colors: UiPalette) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors.background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors.surface))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors.surface_alt))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors.surface_raised))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors.text_soft))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.primary))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors.hud_text))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors.hud_background))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors.hud_text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors.muted))
    palette.setColor(QPalette.ColorRole.Mid, QColor(colors.border))
    palette.setColor(QPalette.ColorRole.Dark, QColor(colors.border_strong))
    return palette


def apply_app_theme(app: QApplication, theme: str = "dark") -> None:
    """Apply Fluent's component theme without installing a global stylesheet."""
    resolved = resolve_theme(theme)
    colors = DARK_PALETTE if resolved == "dark" else LIGHT_PALETTE
    app.setPalette(_build_palette(colors))
    app.setStyleSheet(build_theme_stylesheet(colors))
    if not FLUENT_AVAILABLE or Theme is None:
        return
    try:
        setTheme(Theme.DARK if resolved == "dark" else Theme.LIGHT)
        setThemeColor(colors.primary)
    except RuntimeError:
        # qfluentwidgets' QObject singleton can be torn down between test apps.
        LOGGER.debug("Fluent theme singleton is unavailable", exc_info=True)
