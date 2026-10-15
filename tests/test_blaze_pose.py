"""Regression tests for the BlazePose real-3D estimator contract.

The MediaPipe model itself is replaced by a fake so the mapping from world
landmarks to the canonical COCO-17 layout can be asserted without a camera or
the native graph.
"""

from __future__ import annotations

import numpy as np

from dance_mirror.domain.types import PoseEstimate
from dance_mirror.pose3d.blaze_pose import (
    MP_TO_COCO,
    BlazePoseConfig,
    BlazePoseEstimator,
)


class _Landmark:
    def __init__(self, x: float, y: float, z: float, visibility: float = 1.0) -> None:
        self.x, self.y, self.z, self.visibility = x, y, z, visibility


class _Landmarks:
    def __init__(self, points: list[_Landmark]) -> None:
        self.landmark = points


class _Results:
    def __init__(self, image_points: list[_Landmark], world_points: list[_Landmark]) -> None:
        self.pose_landmarks = _Landmarks(image_points)
        self.pose_world_landmarks = _Landmarks(world_points)


class _FakeModel:
    def __init__(self, results: _Results) -> None:
        self._results = results

    def process(self, _rgb: object) -> _Results:
        return self._results

    def close(self) -> None:
        pass


def _blank_landmarks() -> list[_Landmark]:
    return [_Landmark(0.5, 0.5, 0.0) for _ in range(33)]


def _estimate_with(image_points: list[_Landmark], world_points: list[_Landmark]) -> PoseEstimate:
    estimator = BlazePoseEstimator(BlazePoseConfig())
    estimator._model = _FakeModel(_Results(image_points, world_points))  # type: ignore[assignment]
    estimate = estimator.estimate(
        np.zeros((480, 640, 3), dtype=np.uint8),
        frame_index=0,
        timestamp_s=0.1,
    )
    assert estimate is not None
    return estimate


def test_world_landmarks_become_metric_coco17_with_y_up() -> None:
    image_points = _blank_landmarks()
    world_points = _blank_landmarks()
    # MediaPipe index 11 is the person's left shoulder; world y is y-down.
    world_points[11] = _Landmark(0.30, 0.30, 0.10)
    image_points[11] = _Landmark(0.30, 0.30, 0.0)

    estimate = _estimate_with(image_points, world_points)

    assert estimate.is_metric is True
    shoulder = estimate.pose3d.keypoints[MP_TO_COCO[11]]
    assert np.allclose(shoulder[:3], (0.30, -0.30, 0.10))  # y negated to y-up
    pixels = estimate.pose2d.keypoints[MP_TO_COCO[11]]
    assert np.allclose(pixels[:2], (0.30 * 640, 0.30 * 480))  # image pixels for overlays
    assert estimate.boxes is not None
    assert estimate.boxes.shape == (1, 4)


def test_pose2d_and_pose3d_share_scores_and_frame_metadata() -> None:
    image_points = _blank_landmarks()
    world_points = _blank_landmarks()
    image_points[15] = _Landmark(0.42, 0.71, 0.0, visibility=0.8)

    estimate = _estimate_with(image_points, world_points)

    index = MP_TO_COCO[15]
    assert np.isclose(estimate.pose3d.scores[index], 0.8)
    assert np.isclose(estimate.pose2d.scores[index], 0.8)
    assert estimate.pose3d.frame_index == estimate.pose2d.frame_index == 0
    assert estimate.pose3d.timestamp_s == estimate.pose2d.timestamp_s == 0.1
