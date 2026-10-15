"""OpenCV-backed camera and video-file sources."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

from dance_mirror.capture.types import FramePacket
from dance_mirror.errors import DependencyUnavailableError, VideoSourceError


def _cv2() -> object:
    try:
        import cv2
    except ImportError as exc:
        raise DependencyUnavailableError(
            "OpenCV is required; install opencv-python in pytorch_cuda_env"
        ) from exc
    return cv2


class VideoSource:
    """A replayable video file source.

    The object is intentionally synchronous.  Callers must run it in a worker
    thread when used from a PyQt application.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._capture: object | None = None
        self._frame_index = 0
        self.fps = 0.0
        self.width = 0
        self.height = 0
        self.frame_count = 0

    def open(self) -> None:
        if self._capture is not None:
            return
        if not self.path.is_file():
            raise VideoSourceError(f"video file does not exist: {self.path}")
        cap = _cv2().VideoCapture(str(self.path))
        if not cap.isOpened():
            cap.release()
            raise VideoSourceError(f"cannot open video file: {self.path}")
        self._capture = cap
        self.fps = float(cap.get(_cv2().CAP_PROP_FPS) or 0.0)
        self.width = int(cap.get(_cv2().CAP_PROP_FRAME_WIDTH) or 0)
        self.height = int(cap.get(_cv2().CAP_PROP_FRAME_HEIGHT) or 0)
        self.frame_count = int(cap.get(_cv2().CAP_PROP_FRAME_COUNT) or 0)
        if self.fps <= 0 or self.fps != self.fps:
            self.fps = 30.0

    def read(self) -> FramePacket | None:
        if self._capture is None:
            self.open()
        ok, image = self._capture.read()
        if not ok or image is None:
            return None
        frame = FramePacket(
            image=image,
            index=self._frame_index,
            timestamp_s=self._frame_index / self.fps,
            source_fps=self.fps,
        )
        self._frame_index += 1
        return frame

    def frames(self) -> Iterator[FramePacket]:
        self.open()
        while True:
            frame = self.read()
            if frame is None:
                break
            yield frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> VideoSource:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class CameraSource:
    """A camera source whose capture object is released reliably."""

    def __init__(
        self,
        index: int = 0,
        *,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
    ) -> None:
        if index < 0:
            raise ValueError("camera index must be non-negative")
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("camera dimensions and fps must be positive")
        self.index = index
        self.requested_width = width
        self.requested_height = height
        self.requested_fps = fps
        self.width = width
        self.height = height
        self.fps = fps
        self._capture: object | None = None
        self._frame_index = 0

    def open(self) -> None:
        if self._capture is not None:
            return
        cap = _cv2().VideoCapture(self.index, _cv2().CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = _cv2().VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            raise VideoSourceError(f"cannot open camera index {self.index}")
        cap.set(_cv2().CAP_PROP_FRAME_WIDTH, self.requested_width)
        cap.set(_cv2().CAP_PROP_FRAME_HEIGHT, self.requested_height)
        cap.set(_cv2().CAP_PROP_FPS, self.requested_fps)
        self._capture = cap
        self.width = int(cap.get(_cv2().CAP_PROP_FRAME_WIDTH) or self.requested_width)
        self.height = int(cap.get(_cv2().CAP_PROP_FRAME_HEIGHT) or self.requested_height)
        actual_fps = float(cap.get(_cv2().CAP_PROP_FPS) or 0.0)
        self.fps = actual_fps if actual_fps > 0 else self.requested_fps

    def read(self) -> FramePacket | None:
        if self._capture is None:
            self.open()
        ok, image = self._capture.read()
        if not ok or image is None:
            return None
        frame = FramePacket(
            image=np.ascontiguousarray(image),
            index=self._frame_index,
            timestamp_s=self._frame_index / self.fps,
            source_fps=self.fps,
        )
        self._frame_index += 1
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> CameraSource:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
