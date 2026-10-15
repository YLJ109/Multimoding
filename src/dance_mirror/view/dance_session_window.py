"""Dedicated top-level window for one dance-learning session."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget

from dance_mirror.view.dance_workspace_interface import DanceWorkspaceInterface


class DanceSessionWindow(QDialog):
    """Host the dance workspace outside the main navigation window."""

    closed = pyqtSignal()
    returnRequested = pyqtSignal()

    def __init__(
        self,
        workspace: DanceWorkspaceInterface,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dance-session-window")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setModal(False)
        self.setWindowTitle("DanceMirror - 舞蹈训练")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 660)
        self.workspace = workspace
        if workspace.parent() is not self:
            workspace.setParent(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(workspace)
        self._fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self._fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        workspace.backToLibraryRequested.connect(self.returnRequested.emit)

    def set_session_title(self, package_name: str) -> None:
        clean_name = str(package_name or "").strip() or "未命名舞蹈"
        self.setWindowTitle(f"DanceMirror - {clean_name}")

    def show_session(self, *, fullscreen: bool = False) -> None:
        if fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
            self._center_on_parent()
            self.raise_()
            self.activateWindow()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        center = parent.frameGeometry().center()
        screen = QApplication.screenAt(center) or self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        geometry = self.frameGeometry()
        geometry.moveCenter(center)
        geometry.moveLeft(max(available.left(), geometry.left()))
        geometry.moveTop(max(available.top(), geometry.top()))
        if geometry.right() > available.right():
            geometry.moveRight(available.right())
        if geometry.bottom() > available.bottom():
            geometry.moveBottom(available.bottom())
        self.move(geometry.topLeft())

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self.closed.emit()
        super().closeEvent(event)
