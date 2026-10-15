"""BlazePose (MediaPipe) real-3D pose estimator.

This replaces the synthetic ``BaselinePoseLifter`` depth with genuine metric
world landmarks from ``mediapipe.solutions.pose``.  The same approach powers
Kalidoface 3D / VTube-style avatars: MediaPipe returns 33 landmarks, the
``pose_world_landmarks`` are expressed in metres with the origin at the hip
centre (x right, y down, z toward the camera).

We map the 33-point topology onto the project's canonical COCO-17 layout so the
rest of the pipeline (normalization, retarget, JS redirection) is unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from dance_mirror.domain.types import PoseEstimate, PoseFrame

LOGGER = logging.getLogger(__name__)

# MediaPipe PoseLandmark index -> canonical COCO-17 index (see probe output).
MP_TO_COCO: dict[int, int] = {
    0: 0,   # nose
    2: 1,   # left_eye
    5: 2,   # right_eye
    7: 3,   # left_ear
    8: 4,   # right_ear
    11: 5,  # left_shoulder
    12: 6,  # right_shoulder
    13: 7,  # left_elbow
    14: 8,  # right_elbow
    15: 9,  # left_wrist
    16: 10,  # right_wrist
    23: 11,  # left_hip
    24: 12,  # right_hip
    25: 13,  # left_knee
    26: 14,  # right_knee
    27: 15,  # left_ankle
    28: 16,  # right_ankle
}

COCO_JOINT_COUNT = 17


@dataclass(slots=True)
class BlazePoseConfig:
    """Runtime settings for the MediaPipe BlazePose estimator."""

    model_complexity: int = 1
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    # World landmarks arrive y-down; negate for the y-up convention the renderer
    # expects.  Disabled only if a future MediaPipe build changes its axis.
    flip_y: bool = True
    # World z is positive toward the camera.  The robot faces +Z, so a lean
    # toward the camera should map to +Z.  Keep 1.0; flip to -1.0 if depth
    # ever appears inverted at runtime.
    z_sign: float = 1.0
    smooth_landmarks: bool = True


class BlazePoseEstimator:
    """Thread-confined MediaPipe BlazePose predictor.

    Build and use inside one worker thread.  It returns a :class:`PoseEstimate`
    whose ``pose3d`` carries real metric depth (origin at the hip centre) and
    whose ``pose2d`` carries image-pixel coordinates for overlays and hand ROI.
    """

    def __init__(self, config: BlazePoseConfig | None = None) -> None:
        self.config = config or BlazePoseConfig()
        self.last_boxes: np.ndarray | None = None
        self.last_person_count = 0
        self.last_primary_index = 0
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        import mediapipe as mp

        self._model = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=int(self.config.model_complexity),
            enable_segmentation=False,
            smooth_landmarks=bool(self.config.smooth_landmarks),
            min_detection_confidence=float(self.config.min_detection_confidence),
            min_tracking_confidence=float(self.config.min_tracking_confidence),
        )
        return self._model

    def estimate(
        self,
        frame: np.ndarray,
        *,
        frame_index: int,
        timestamp_s: float,
    ) -> PoseEstimate | None:
        """Run one prediction and return COCO-17 observations, or ``None``."""
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must have shape (H, W, 3)")
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        try:
            results = self._ensure_model().process(rgb)
        except Exception as exc:  # pragma: no cover - depends on runtime model
            LOGGER.warning("BlazePose inference failed: %s", exc)
            self.last_person_count = 0
            self.last_boxes = None
            return None

        if results is None or results.pose_landmarks is None:
            self.last_person_count = 0
            self.last_boxes = None
            self.last_primary_index = 0
            return None

        world = results.pose_world_landmarks
        image_lm = results.pose_landmarks.landmark

        xyz3d = np.zeros((COCO_JOINT_COUNT, 3), dtype=np.float64)
        xyz2d = np.zeros((COCO_JOINT_COUNT, 3), dtype=np.float64)
        scores = np.zeros(COCO_JOINT_COUNT, dtype=np.float64)
        if world is not None:
            world_lm = world.landmark
            for mp_index, coco_index in MP_TO_COCO.items():
                src = world_lm[mp_index]
                y = -float(src.y) if self.config.flip_y else float(src.y)
                xyz3d[coco_index, 0] = float(src.x)
                xyz3d[coco_index, 1] = y
                xyz3d[coco_index, 2] = float(src.z) * float(self.config.z_sign)
                image_src = image_lm[mp_index]
                xyz2d[coco_index, 0] = float(image_src.x) * width
                xyz2d[coco_index, 1] = float(image_src.y) * height
                xyz2d[coco_index, 2] = 0.0
                scores[coco_index] = float(getattr(image_src, "visibility", 1.0))
        else:
            # World landmarks unavailable: degrade to a centred 2D-only pose.
            for mp_index, coco_index in MP_TO_COCO.items():
                image_src = image_lm[mp_index]
                xyz3d[coco_index, 0] = float(image_src.x) - 0.5
                xyz3d[coco_index, 1] = 0.5 - float(image_src.y)
                xyz3d[coco_index, 2] = 0.0
                xyz2d[coco_index, 0] = float(image_src.x) * width
                xyz2d[coco_index, 1] = float(image_src.y) * height
                scores[coco_index] = float(getattr(image_src, "visibility", 1.0))

        self.last_person_count = 1
        self.last_primary_index = 0
        self.last_boxes = self._bbox_from_2d(xyz2d, scores, width, height)

        pose3d = PoseFrame(
            keypoints=xyz3d,
            scores=scores.copy(),
            timestamp_s=max(0.0, timestamp_s),
            frame_index=int(frame_index),
            schema="coco17",
        )
        pose2d = PoseFrame(
            keypoints=xyz2d,
            scores=scores.copy(),
            timestamp_s=max(0.0, timestamp_s),
            frame_index=int(frame_index),
            schema="coco17",
        )
        return PoseEstimate(
            pose3d=pose3d,
            pose2d=pose2d,
            is_metric=True,
            person_count=1,
            primary_index=0,
            boxes=self.last_boxes,
        )

    @staticmethod
    def _bbox_from_2d(
        xyz2d: np.ndarray,
        scores: np.ndarray,
        width: int,
        height: int,
    ) -> np.ndarray:
        visible = scores >= 0.25
        if not np.any(visible):
            return None
        xs = xyz2d[visible, 0]
        ys = xyz2d[visible, 1]
        x1 = float(np.clip(xs.min() - 0.10 * width, 0, width))
        y1 = float(np.clip(ys.min() - 0.10 * height, 0, height))
        x2 = float(np.clip(xs.max() + 0.10 * width, 0, width))
        y2 = float(np.clip(ys.max() + 0.10 * height, 0, height))
        return np.array([[x1, y1, x2, y2]], dtype=np.float64)

    def close(self) -> None:
        if self._model is not None:
            try:
                self._model.close()
            except Exception:  # pragma: no cover - best effort
                LOGGER.debug("BlazePose model close failed", exc_info=True)
        self._model = None
