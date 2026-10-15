"""Shared start/stop controls stay stateful and singular."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from dance_mirror.view.command_center_interface import CommandCenterInterface
from dance_mirror.view.dance_workspace_interface import DanceWorkspaceInterface


def test_dance_workspace_uses_one_start_stop_action() -> None:
    app = QApplication.instance() or QApplication([])
    workspace = DanceWorkspaceInterface()
    events: list[str] = []
    workspace.startRequested.connect(lambda: events.append("start"))
    workspace.stopRequested.connect(lambda: events.append("stop"))

    assert workspace.stop_button is workspace.start_button
    workspace._handle_action()  # noqa: SLF001
    workspace.set_armed(True)
    workspace._handle_action()  # noqa: SLF001

    assert events == ["start", "stop"]
    assert workspace.start_button.text() == "停止"
    workspace.set_playing(False)
    assert workspace.start_button.text() == "开始"
    workspace.deleteLater()
    app.processEvents()


def test_command_center_uses_one_start_stop_action() -> None:
    app = QApplication.instance() or QApplication([])
    workspace = CommandCenterInterface()
    events: list[str] = []
    workspace.imitationRequested.connect(lambda _enabled: events.append("start"))
    workspace.stopRequested.connect(lambda: events.append("stop"))

    assert workspace.stop_button is workspace.start_button
    workspace._handle_action()  # noqa: SLF001
    workspace.set_imitation_running(True)
    workspace._handle_action()  # noqa: SLF001

    assert events == ["start", "stop"]
    assert workspace.start_button.text() == "停止"
    workspace.set_imitation_running(False)
    assert workspace.start_button.text() == "开始模仿"
    workspace.deleteLater()
    app.processEvents()
