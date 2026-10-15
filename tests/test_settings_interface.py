"""Qt settings persistence contracts for 3D character controls."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from dance_mirror.view.settings_interface import SettingsInterface


def test_settings_persist_character_and_motion_preset(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    widget = SettingsInterface(character_root=tmp_path)
    captured: list[dict[str, object]] = []
    widget.settingsSaved.connect(captured.append)

    widget.load_values(
        {
            "appearance_theme": "dark",
            "character_id": "humanoid_adult",
            "motion_preset": "smooth",
            "model_mode": "overlay",
        }
    )
    widget._save()  # noqa: SLF001 - test the UI contract directly

    assert captured
    assert captured[-1]["character_id"] == "humanoid_adult"
    assert captured[-1]["motion_preset"] == "smooth"
    assert captured[-1]["appearance_theme"] == "dark"
    widget.deleteLater()
    app.processEvents()


def test_session_api_key_is_masked_and_does_not_dirty_the_form(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    widget = SettingsInterface(character_root=tmp_path)
    widget.load_values({"appearance_theme": "dark"})

    widget.set_session_api_key("session-only-placeholder")

    assert widget.llm_api_key.text() == "session-only-placeholder"
    assert widget.llm_api_key.echoMode().name == "Password"
    assert not widget.has_unsaved_changes()
    widget.deleteLater()
    app.processEvents()
