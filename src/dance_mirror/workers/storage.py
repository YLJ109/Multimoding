"""Background persistence workers for training records."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal

from dance_mirror.storage.database import TrainingRecord, TrainingStore
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class SaveTrainingRecordWorker(CancellableWorker):
    """Persist one session record and return the refreshed history."""

    historyReady = pyqtSignal(object)

    def __init__(self, database_path: str, record: TrainingRecord) -> None:
        super().__init__()
        self.database_path = database_path
        self.record = record

    def run(self) -> None:
        try:
            with TrainingStore(self.database_path) as store:
                store.save(self.record)
                records = store.list_recent(20)
            if self._stopped:
                self.cancelled.emit()
                return
            self.historyReady.emit(records)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("failed to persist training record")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class LoadHistoryWorker(CancellableWorker):
    """Load recent records without blocking the Qt event loop."""

    historyReady = pyqtSignal(object)

    def __init__(self, database_path: str, limit: int = 20) -> None:
        super().__init__()
        self.database_path = database_path
        self.limit = limit

    def run(self) -> None:
        try:
            with TrainingStore(self.database_path) as store:
                records = store.list_recent(self.limit)
            if self._stopped:
                self.cancelled.emit()
                return
            self.historyReady.emit(records)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("failed to load training history")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
