"""DanceMirror desktop application entry point."""

from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from dance_mirror.config import AppPaths
from dance_mirror.logging_setup import configure_logging
from dance_mirror.runtime import isolate_mediapipe_runtime
from dance_mirror.view.branding import application_icon
from dance_mirror.view.main_window import MainWindow
from dance_mirror.view.theme import apply_app_theme


def _install_exception_hook() -> None:
    def handle(exc_type: type[BaseException], value: BaseException, tb: object) -> None:
        logging.critical(
            "uncaught exception",
            exc_info=(exc_type, value, tb),  # type: ignore[arg-type]
        )
        sys.__excepthook__(exc_type, value, tb)  # type: ignore[arg-type]

    sys.excepthook = handle


def run() -> int:
    """Create the Qt application and enter its event loop."""
    paths = AppPaths.discover()
    paths.ensure()
    configure_logging(paths.logs)
    isolate_mediapipe_runtime()
    _install_exception_hook()
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--enable-unsafe-swiftshader",
    )

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("DanceMirror")
    app.setOrganizationName("DanceMirror")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    icon = application_icon()
    app.setWindowIcon(icon)
    apply_app_theme(app, "dark")
    window = MainWindow(paths=paths)
    window.setWindowIcon(icon)
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(run())
