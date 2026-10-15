"""Ultralytics YOLO pose adapter with a narrow, replaceable boundary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dance_mirror.domain.types import PoseEstimate, PoseFrame
from dance_mirror.errors import DependencyUnavailableError, PoseEstimationError

LOGGER = logging.getLogger(__name__)


def _as_numpy(value: object) -> np.ndarray:
    """Copy a CPU/CUDA tensor or array-like value into a NumPy array."""
    if hasattr(value, "detach"):
        value = value.detach()  # type: ignore[union-attr]
    if hasattr(value, "cpu"):
        value = value.cpu()  # type: ignore[union-attr]
    if hasattr(value, "numpy"):
        value = value.numpy()  # type: ignore[union-attr]
    return np.asarray(value, dtype=np.float64)


@dataclass(slots=True)
class YoloPoseConfig:
    """Runtime settings for a YOLO pose model.

    The model path is deliberately configurable because Ultralytics model
    names and exported ONNX assets differ by release.  Pin the exact asset in
    ``docs/ENVIRONMENT.md`` before producing a release.
    """

    model_path: str = "yolo11n-pose.pt"
    device: str = "cuda:0"
    image_size: int = 640
    confidence: float = 0.35
    iou: float = 0.5
    max_detections: int = 4


class YoloPoseEstimator:
    """Thread-confined Ultralytics predictor.

    Construct and use this class inside one worker thread.  It is not safe to
    share a live Ultralytics model or CUDA context across threads.
    """

    def __init__(self, config: YoloPoseConfig | None = None) -> None:
        self.config = config or YoloPoseConfig()
        self.last_boxes: np.ndarray | None = None
        self.last_person_count = 0
        self.last_primary_index = 0
        self._last_primary_center: np.ndarray | None = None
        self._model: object | None = None

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DependencyUnavailableError(
                "Ultralytics is required for YOLO pose inference; "
                "install the vision extra in pytorch_cuda_env"
            ) from exc
        model_path = Path(self.config.model_path).expanduser()
        if not model_path.is_file():
            raise PoseEstimationError(
                f"YOLO model file not found: {model_path}; run scripts/install_vision.ps1"
            )
        try:
            self._model = YOLO(str(model_path))
        except Exception as exc:
            raise PoseEstimationError(f"failed to load YOLO model: {model_path}") from exc
        return self._model

    def estimate(
        self,
        frame: np.ndarray,
        *,
        frame_index: int,
        timestamp_s: float,
    ) -> PoseEstimate | None:
        """Run one prediction and return a canonical COCO-17 observation."""
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must have shape (H, W, 3)")
        model = self._load_model()
        try:
            results = model.predict(
                source=frame,
                imgsz=self.config.image_size,
                conf=self.config.confidence,
                iou=self.config.iou,
                max_det=self.config.max_detections,
                device=self.config.device,
                verbose=False,
            )
        except Exception as exc:
            raise PoseEstimationError(
                f"YOLO inference failed at frame {frame_index}"
            ) from exc
        if not results:
            self._clear_people_metadata()
            return None

        result = results[0]
        self._update_people_metadata(result)
        keypoints = getattr(result, "keypoints", None)
        if keypoints is None or keypoints.xy is None:
            return None
        xy = _as_numpy(keypoints.xy)
        if xy.shape[0] == 0:
            return None
        if xy.shape[1:] != (17, 2):
            raise PoseEstimationError(
                f"expected COCO-17 YOLO output, got keypoint shape {xy.shape}"
            )

        confidences = getattr(keypoints, "conf", None)
        if confidences is None:
            scores = np.ones((xy.shape[0], 17), dtype=np.float64)
        else:
            scores = _as_numpy(confidences)
        if scores.shape != (xy.shape[0], 17):
            raise PoseEstimationError(
                f"expected confidence shape {(xy.shape[0], 17)}, got {scores.shape}"
            )
        person_index = self._select_primary_index(scores, frame.shape)
        self.last_primary_index = person_index
        points = np.zeros((17, 3), dtype=np.float64)
        points[:, :2] = xy[person_index]
        frame = PoseFrame(
            keypoints=points,
            scores=scores[person_index],
            timestamp_s=max(0.0, timestamp_s),
            frame_index=frame_index,
            schema="coco17",
        )
        # Expose the same frame in both slots; the real-3D backend differs.
        return PoseEstimate(
            pose3d=frame,
            pose2d=frame,
            is_metric=False,
            person_count=int(scores.shape[0]),
            primary_index=person_index,
            boxes=self.last_boxes,
        )

    def _select_primary_index(
        self,
        scores: np.ndarray,
        frame_shape: tuple[int, ...],
    ) -> int:
        """Keep one person selected across frames when several are visible.

        A plain ``argmax`` on pose confidence can switch back and forth when a
        second person enters the frame. The first observation uses confidence
        to find the dancer; later observations follow the nearest box centre so
        the selected skeleton remains temporally stable.
        """
        person_count = int(scores.shape[0])
        if person_count <= 1:
            index = 0
            centres: np.ndarray | None = None
        else:
            finite_scores = np.where(np.isfinite(scores), scores, 0.0)
            mean_scores = np.mean(finite_scores, axis=1)

            centres = None
            boxes = self.last_boxes
            if (
                boxes is not None
                and boxes.shape[0] >= person_count
                and boxes.shape[1] >= 4
            ):
                centres = (boxes[:person_count, :2] + boxes[:person_count, 2:4]) * 0.5

            if self._last_primary_center is None or centres is None:
                index = int(np.argmax(mean_scores))
            else:
                height, width = (int(frame_shape[0]), int(frame_shape[1]))
                diagonal = max(1.0, float(np.hypot(width, height)))
                distances = np.linalg.norm(centres - self._last_primary_center, axis=1)
                index = min(
                    range(person_count),
                    key=lambda candidate: (
                        float(distances[candidate]) / diagonal,
                        -float(mean_scores[candidate]),
                    ),
                )

        if centres is not None:
            self._last_primary_center = centres[index].copy()
        else:
            self._last_primary_center = None
        return index

    def _update_people_metadata(self, result: object) -> None:
        boxes = getattr(result, "boxes", None)
        box_values = getattr(boxes, "xyxy", None) if boxes is not None else None
        if box_values is None:
            self.last_boxes = None
            self.last_person_count = 0
            self.last_primary_index = 0
            return
        self.last_boxes = _as_numpy(box_values)
        self.last_person_count = int(self.last_boxes.shape[0])
        if self.last_person_count == 0:
            self.last_primary_index = 0
            self._last_primary_center = None

    def _clear_people_metadata(self) -> None:
        self.last_boxes = None
        self.last_person_count = 0
        self.last_primary_index = 0
        self._last_primary_center = None

    def close(self) -> None:
        """Drop model references; CUDA memory is reclaimed by the process."""
        self._model = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            LOGGER.debug("torch is not installed while closing YOLO adapter")
        except Exception:
            LOGGER.exception("failed while releasing YOLO CUDA cache")
