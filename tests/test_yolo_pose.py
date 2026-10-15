"""Tests for the YOLO pose adapter's person selection boundary."""

from __future__ import annotations

import numpy as np

from dance_mirror.pose2d.yolo_pose import YoloPoseEstimator, _as_numpy


class _FakeCudaTensor:
    def detach(self) -> _FakeCudaTensor:
        return self

    def cpu(self) -> _FakeCudaTensor:
        return self

    def numpy(self) -> np.ndarray:
        return np.asarray([[1.0, 2.0]], dtype=np.float64)


def test_tensor_like_values_are_copied_to_numpy() -> None:
    assert np.allclose(_as_numpy(_FakeCudaTensor()), [[1.0, 2.0]])


def _mean_scores(*values: float) -> np.ndarray:
    return np.tile(np.asarray(values, dtype=np.float64)[:, None], (1, 17))


def test_first_primary_person_uses_keypoint_confidence() -> None:
    estimator = YoloPoseEstimator()
    estimator.last_boxes = np.asarray(
        [[0.0, 0.0, 10.0, 10.0], [20.0, 20.0, 30.0, 30.0]],
        dtype=np.float64,
    )

    index = estimator._select_primary_index(_mean_scores(0.2, 0.9), (100, 100, 3))

    assert index == 1
    assert np.allclose(estimator._last_primary_center, [25.0, 25.0])


def test_later_primary_person_follows_previous_centre_before_confidence() -> None:
    estimator = YoloPoseEstimator()
    estimator.last_boxes = np.asarray(
        [[0.0, 0.0, 10.0, 10.0], [20.0, 20.0, 30.0, 30.0]],
        dtype=np.float64,
    )
    estimator._last_primary_center = np.asarray([25.0, 25.0], dtype=np.float64)

    index = estimator._select_primary_index(_mean_scores(0.99, 0.2), (100, 100, 3))

    assert index == 1
    assert np.allclose(estimator._last_primary_center, [25.0, 25.0])


def test_clearing_metadata_resets_tracking_anchor() -> None:
    estimator = YoloPoseEstimator()
    estimator.last_boxes = np.asarray([[0.0, 0.0, 10.0, 10.0]], dtype=np.float64)
    estimator.last_person_count = 1
    estimator._last_primary_center = np.asarray([5.0, 5.0], dtype=np.float64)

    estimator._clear_people_metadata()

    assert estimator.last_boxes is None
    assert estimator.last_person_count == 0
    assert estimator._last_primary_center is None
