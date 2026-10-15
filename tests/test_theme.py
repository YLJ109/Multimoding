"""Theme startup contracts for the desktop shell."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from dance_mirror.view.fluent import FLUENT_AVAILABLE, Theme, isDarkTheme
from dance_mirror.view.theme import apply_app_theme


def test_application_theme_defaults_to_dark_and_accepts_explicit_light() -> None:
    app = QApplication.instance() or QApplication([])

    apply_app_theme(app)
    assert "QComboBox QAbstractItemView" in app.styleSheet()
    if FLUENT_AVAILABLE:
        assert isDarkTheme()

    apply_app_theme(app, "light")
    assert "QComboBox QAbstractItemView" in app.styleSheet()
    if FLUENT_AVAILABLE and Theme is not None:
        assert not isDarkTheme()
