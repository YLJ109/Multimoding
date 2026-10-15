"""Keep one Qt application alive for the whole test session."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])
