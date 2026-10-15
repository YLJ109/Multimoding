"""Application paths and local settings.

QSettings is used instead of custom JSON files so Windows registry/INI storage
is atomic and already integrated with Qt.  The UI-specific QConfig layer can be
added on top without changing feature code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSettings


@dataclass(frozen=True, slots=True)
class AppPaths:
    """All writable locations used by the desktop application."""

    root: Path
    logs: Path
    data: Path
    motion_packages: Path
    recordings: Path
    models: Path
    characters: Path

    @classmethod
    def discover(cls) -> AppPaths:
        override = os.environ.get("DANCE_MIRROR_HOME")
        if override:
            root = Path(override).expanduser().resolve()
        else:
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".dance_mirror"))
            root = (base / "DanceMirror").resolve()
        return cls(
            root=root,
            logs=root / "logs",
            data=root / "data",
            motion_packages=root / "motion_packages",
            recordings=root / "recordings",
            models=root / "models",
            characters=root / "characters",
        )

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.logs,
            self.data,
            self.motion_packages,
            self.recordings,
            self.models,
            self.characters,
        ):
            directory.mkdir(parents=True, exist_ok=True)


class Settings:
    """Small typed facade over Qt's native persistent settings."""

    def __init__(self, organization: str = "DanceMirror") -> None:
        self._settings = QSettings(organization, "DanceMirror")

    def get_str(self, key: str, default: str = "") -> str:
        return str(self._settings.value(key, default))

    def set_str(self, key: str, value: str) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()

    def get_int(self, key: str, default: int) -> int:
        value = self._settings.value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def set_int(self, key: str, value: int) -> None:
        self._settings.setValue(key, int(value))
        self._settings.sync()

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def set_bool(self, key: str, value: bool) -> None:
        self._settings.setValue(key, bool(value))
        self._settings.sync()
