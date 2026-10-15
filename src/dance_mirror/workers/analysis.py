"""Reference-video analysis worker."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal

from dance_mirror.pose2d.yolo_pose import YoloPoseConfig
from dance_mirror.services.reference import analyze_reference_video
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class ReferenceAnalysisWorker(CancellableWorker):
    """Decode a reference video and extract canonical pose frames."""

    sequenceReady = pyqtSignal(object)

    def __init__(self, video_path: str, config: YoloPoseConfig) -> None:
        super().__init__()
        self.video_path = video_path
        self.config = config

    def run(self) -> None:
        try:
            result = analyze_reference_video(
                self.video_path,
                pose_config=self.config,
                progress=self.progressChanged.emit,
                should_cancel=lambda: self._stopped,
            )
            if self._stopped:
                self.cancelled.emit()
                return
            self.sequenceReady.emit(result.sequence)
            self.finished.emit()
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            LOGGER.exception("reference video analysis failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
