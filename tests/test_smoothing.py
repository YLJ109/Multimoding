"""Unit tests for the dependency-light temporal smoothing core.

These run headless (numpy only) and lock in the contract that ``values`` is
``(frames, joints[, 2])`` and ``scores`` is ``(frames, joints)`` — the same
shapes produced by the reference pipeline in ``services/reference.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from dance_mirror.motion.smoothing import (
    exponential_smooth,
    fill_short_gaps,
    one_euro_smooth,
)


# --------------------------------------------------------------------------- #
# fill_short_gaps
# --------------------------------------------------------------------------- #
def test_fill_short_gaps_interpolates_short_runs_linearly() -> None:
    values = np.zeros((5, 1, 2), dtype=np.float64)
    scores = np.zeros((5, 1), dtype=np.float64)
    values[0, 0, :] = [0.0, 0.0]
    values[4, 0, :] = [4.0, 8.0]
    scores[0, 0] = 1.0
    scores[4, 0] = 1.0

    repaired, repaired_scores = fill_short_gaps(values, scores, max_gap=8)

    np.testing.assert_allclose(repaired[1, 0, :], [1.0, 2.0])
    np.testing.assert_allclose(repaired[2, 0, :], [2.0, 4.0])
    np.testing.assert_allclose(repaired[3, 0, :], [3.0, 6.0])
    # repaired points are flagged valid with the weaker neighbour confidence
    assert repaired_scores[1:4, 0].min() == 1.0


def test_fill_short_gaps_skips_runs_longer_than_max_gap() -> None:
    values = np.zeros((20, 1, 1), dtype=np.float64)
    scores = np.zeros((20, 1), dtype=np.float64)
    values[0, 0, 0] = 1.0
    values[19, 0, 0] = 3.0
    scores[0, 0] = 1.0
    scores[19, 0] = 1.0

    repaired, _ = fill_short_gaps(values, scores, max_gap=8)

    # 18-frame gap far exceeds max_gap -> nothing interpolated
    assert np.all(repaired[1:19, 0, 0] == 0.0)


def test_fill_short_gaps_leaves_anchors_untouched() -> None:
    values = np.zeros((5, 1, 1), dtype=np.float64)
    scores = np.zeros((5, 1), dtype=np.float64)
    values[0, 0, 0] = 1.0
    values[4, 0, 0] = 3.0
    scores[0, 0] = 1.0
    scores[4, 0] = 1.0

    repaired, _ = fill_short_gaps(values, scores)

    assert repaired[0, 0, 0] == 1.0
    assert repaired[4, 0, 0] == 3.0


def test_fill_short_gaps_handles_no_valid_points() -> None:
    values = np.zeros((4, 2, 1), dtype=np.float64)
    scores = np.zeros((4, 2), dtype=np.float64)  # nothing valid

    repaired, repaired_scores = fill_short_gaps(values, scores)

    assert np.all(repaired == 0.0)
    assert np.all(repaired_scores == 0.0)


# --------------------------------------------------------------------------- #
# exponential_smooth
# --------------------------------------------------------------------------- #
def test_exponential_smooth_interpolates_valid_frames() -> None:
    values = np.array([[[0.0]], [[10.0]], [[10.0]]], dtype=np.float64)
    scores = np.ones((3, 1), dtype=np.float64)

    out = exponential_smooth(values, scores, alpha=0.5)

    np.testing.assert_allclose(out[:, 0, 0], [0.0, 5.0, 7.5])


def test_exponential_smooth_keeps_low_confidence_frames() -> None:
    values = np.array([[[0.0]], [[10.0]], [[10.0]]], dtype=np.float64)
    scores = np.array([[1.0], [0.0], [1.0]], dtype=np.float64)  # middle invalid

    out = exponential_smooth(values, scores, alpha=0.5)

    # middle frame passes through untouched; tail still smoothed from prev valid
    np.testing.assert_allclose(out[:, 0, 0], [0.0, 10.0, 5.0])


def test_exponential_smooth_rejects_invalid_alpha() -> None:
    values = np.zeros((3, 1, 1), dtype=np.float64)
    scores = np.ones((3, 1), dtype=np.float64)
    with pytest.raises(ValueError):
        exponential_smooth(values, scores, alpha=1.5)
    with pytest.raises(ValueError):
        exponential_smooth(values, scores, alpha=0.0)


def test_exponential_smooth_preserves_shape() -> None:
    values = np.random.default_rng(0).normal(size=(30, 5, 2))
    scores = np.ones((30, 5), dtype=np.float64)
    assert exponential_smooth(values, scores).shape == values.shape


# --------------------------------------------------------------------------- #
# one_euro_smooth
# --------------------------------------------------------------------------- #
def test_one_euro_smooth_rejects_non_positive_frequency() -> None:
    values = np.zeros((3, 1, 1), dtype=np.float64)
    scores = np.ones((3, 1), dtype=np.float64)
    with pytest.raises(ValueError):
        one_euro_smooth(values, scores, frequency=0.0)
    with pytest.raises(ValueError):
        one_euro_smooth(values, scores, frequency=-5.0)


def test_one_euro_smooth_is_deterministic_and_shaped() -> None:
    values = np.random.default_rng(7).normal(size=(40, 6, 2))
    scores = np.ones((40, 6), dtype=np.float64)

    a = one_euro_smooth(values, scores, frequency=30.0)
    b = one_euro_smooth(values, scores, frequency=30.0)

    assert a.shape == values.shape
    np.testing.assert_array_equal(a, b)


def test_one_euro_smooth_respects_confidence_mask() -> None:
    values = np.array([[[0.0]], [[9.0]], [[9.0]]], dtype=np.float64)
    scores = np.array([[1.0], [0.0], [1.0]], dtype=np.float64)

    out = one_euro_smooth(values, scores, frequency=30.0)

    # first confidence-gated frame carries the raw value, not a filtered blend
    assert out[0, 0, 0] == 0.0
    assert out[1, 0, 0] == 9.0  # invalid frame passes through unchanged
