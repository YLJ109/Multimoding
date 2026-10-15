"""Small worker lifecycle primitives for PyQt6 applications."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QThread, pyqtSignal

LOGGER = logging.getLogger(__name__)


class CancellableWorker(QObject):
    """Base class for long-running work moved to a QThread."""

    progressChanged = pyqtSignal(int)
    finished = pyqtSignal()
    errorOccurred = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    def run(self) -> None:
        raise NotImplementedError


class WorkerThreadController(QObject):
    """Own a worker and its QThread for the full widget lifetime.

    The controller is the only place where worker cleanup is wired, so screens
    cannot accidentally create an unreferenced thread or forget ``wait()``.
    """

    started = pyqtSignal()
    finished = pyqtSignal()
    errorOccurred = pyqtSignal(str)

    def __init__(self, worker: CancellableWorker, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.worker = worker
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.started.emit)
        self.thread.started.connect(self.worker.run)
        self.worker.progressChanged.connect(self.progressChanged.emit)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.errorOccurred.connect(self._on_worker_error)
        self.worker.cancelled.connect(self._on_worker_cancelled)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finished.emit)

    progressChanged = pyqtSignal(int)

    def _on_worker_finished(self) -> None:
        self.thread.quit()

    def _on_worker_error(self, message: str) -> None:
        self.errorOccurred.emit(message)
        self.thread.quit()

    def _on_worker_cancelled(self) -> None:
        self.thread.quit()

    def start(self) -> None:
        if not self.thread.isRunning():
            self.thread.start()

    def stop(self, wait_ms: int = 3000) -> None:
        self.worker.stop()
        if self.thread.isRunning():
            self.thread.quit()
            if wait_ms > 0 and not self.thread.wait(wait_ms):
                LOGGER.error("worker thread did not stop within %d ms", wait_ms)
