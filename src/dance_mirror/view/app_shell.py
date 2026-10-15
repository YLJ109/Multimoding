"""Fluent application shell with stable navigation and page routing."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEvent, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.view.fluent import (
    FLUENT_AVAILABLE,
    FluentIcon,
    FluentWindow,
    NavigationItemPosition,
)
from dance_mirror.view.native_window import apply_native_window_corners

_FluentBase = FluentWindow if FLUENT_AVAILABLE and FluentWindow is not None else QMainWindow


class AppShellWindow(_FluentBase):
    """Own the Fluent navigation panel and the shared interface stack."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("app-shell-window")
        self._shortcuts: list[QShortcut] = []
        if FLUENT_AVAILABLE:
            self._stack = self.stackedWidget
            self._nav_buttons: dict[QWidget, object] = {}
            navigation = self.navigationInterface
            navigation.setExpandWidth(224)
            navigation.setCollapsible(False)
            navigation.setReturnButtonVisible(False)
            panel = getattr(navigation, "panel", None)
            if panel is not None and hasattr(panel, "setMenuButtonVisible"):
                panel.setMenuButtonVisible(False)
            if panel is not None:
                # The Fluent title bar spans the top edge; reserve its height so
                # the first navigation item cannot render underneath the title.
                panel.vBoxLayout.setContentsMargins(0, 50, 0, 5)
            navigation.expand(False)
            self.setMicaEffectEnabled(False)
        else:  # pragma: no cover - the declared dependency is installed in production
            self._stack = QStackedWidget(self)
            self._nav_group = QButtonGroup(self)
            self._nav_group.setExclusive(True)
            self._nav_buttons: dict[QWidget, QPushButton] = {}
            self._build_fallback_shell()

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)  # type: ignore[misc]
        QTimer.singleShot(0, self._refresh_native_window_chrome)

    def changeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)  # type: ignore[misc]
        event_type = getattr(event, "type", lambda: None)()
        if event_type == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._refresh_native_window_chrome)

    def _refresh_native_window_chrome(self) -> None:
        rounded = not (self.isFullScreen() or self.isMaximized())
        apply_native_window_corners(self, rounded=rounded)

    def _build_fallback_shell(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        rail = QWidget(central)
        rail.setFixedWidth(224)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(16, 20, 16, 18)
        rail_layout.setSpacing(8)
        self._fallback_main = QVBoxLayout()
        self._fallback_bottom = QVBoxLayout()
        rail_layout.addLayout(self._fallback_main)
        rail_layout.addStretch(1)
        rail_layout.addLayout(self._fallback_bottom)
        root.addWidget(rail)
        root.addWidget(self._stack, 1)
        self.setCentralWidget(central)

    def addSubInterface(  # noqa: N802 - qfluentwidgets API
        self,
        widget: QWidget,
        icon: object | None = None,
        text: str = "",
        position: object | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> object:
        """Add a page while preserving the shell contract used by MainWindow."""
        if FLUENT_AVAILABLE:
            target = (
                NavigationItemPosition.BOTTOM
                if str(getattr(position, "name", position or "")).upper().endswith("BOTTOM")
                else NavigationItemPosition.TOP
            )
            item = super().addSubInterface(
                widget,
                icon or FluentIcon.APPLICATION,
                str(text),
                target,
            )
            self._nav_buttons[widget] = item
            self._register_shortcuts(widget)
            return item

        if widget not in self._nav_buttons:
            self._stack.addWidget(widget)
            button = QPushButton(str(text), self)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, page=widget: self.switchTo(page))
            self._nav_group.addButton(button)
            self._nav_buttons[widget] = button
            target = (
                self._fallback_bottom
                if str(getattr(position, "name", position or "")).upper().endswith("BOTTOM")
                else self._fallback_main
            )
            target.addWidget(button)
            self._register_shortcuts(widget)
        return self._nav_buttons[widget]

    def _register_shortcuts(self, widget: QWidget) -> None:
        index = len(self._shortcuts) + 1
        if index > 4:
            return
        shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
        shortcut.activated.connect(lambda page=widget: self.switchTo(page))
        self._shortcuts.append(shortcut)

    def switchTo(self, widget: QWidget) -> None:  # noqa: N802 - qfluentwidgets API
        """Select one page and keep the navigation state synchronized."""
        if FLUENT_AVAILABLE:
            super().switchTo(widget)
            return
        if widget not in self._nav_buttons:
            return
        self._stack.setCurrentWidget(widget)
        self._nav_buttons[widget].setChecked(True)

    def current_page(self) -> QWidget | None:
        return self._stack.currentWidget()
