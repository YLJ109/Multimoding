"""Background download worker for curated 3D characters."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal

from dance_mirror.renderer.character_catalog import CharacterStore, character_preset
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class CharacterDownloadWorker(CancellableWorker):
    """Download one character without blocking the Qt event loop."""

    completed = pyqtSignal(str, str)

    def __init__(self, store: CharacterStore, key: str) -> None:
        super().__init__()
        self.store = store
        self.key = character_preset(key).key

    def run(self) -> None:
        try:
            path = self.store.download(
                self.key,
                progress=self.progressChanged.emit,
                should_stop=lambda: self.is_stopped,
            )
            if self.is_stopped:
                self.cancelled.emit()
                return
            self.completed.emit(self.key, str(path))
            self.finished.emit()
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            LOGGER.exception("character download failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
