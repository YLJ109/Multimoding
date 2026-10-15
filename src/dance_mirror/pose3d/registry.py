"""Unified pose-estimator factory used by the real-time workers."""

from __future__ import annotations

from dance_mirror.pose2d.yolo_pose import YoloPoseConfig, YoloPoseEstimator
from dance_mirror.pose3d.blaze_pose import BlazePoseConfig, BlazePoseEstimator

VALID_BACKENDS = ("blazepose", "blaze", "mediapipe", "yolo")


def make_pose_estimator(
    backend: str = "blazepose",
    *,
    yolo_config: YoloPoseConfig | None = None,
    blaze_config: BlazePoseConfig | None = None,
) -> YoloPoseEstimator | BlazePoseEstimator:
    """Construct the requested pose backend in a thread-confined manner."""
    key = (backend or "blazepose").lower()
    if key in ("yolo",):
        return YoloPoseEstimator(yolo_config or YoloPoseConfig())
    if key in ("blazepose", "blaze", "mediapipe"):
        return BlazePoseEstimator(blaze_config or BlazePoseConfig())
    raise ValueError(f"unknown pose backend: {backend!r} (choose from {VALID_BACKENDS})")
