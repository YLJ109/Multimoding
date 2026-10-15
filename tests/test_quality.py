"""Tests for conservative motion-package quality classification."""

from __future__ import annotations

import numpy as np

from dance_mirror.domain.quality import MotionQualityLevel, assess_motion_quality
from dance_mirror.domain.types import PoseSequence


def _sequence(metadata: dict[str, object] | None = None) -> PoseSequence:
    frames = 20
    keypoints = np.zeros((frames, 17, 3), dtype=np.float64)
    keypoints[:, 5] = (-0.25, 1.0, 0.0)
    keypoints[:, 6] = (0.25, 1.0, 0.0)
    keypoints[:, 11] = (-0.12, 0.0, 0.0)
    keypoints[:, 12] = (0.12, 0.0, 0.0)
    keypoints[:, 9, 2] = np.linspace(-0.1, 0.1, frames)
    keypoints[:, 10, 2] = np.linspace(0.1, -0.1, frames)
    return PoseSequence(
        keypoints=keypoints,
        scores=np.ones((frames, 17), dtype=np.float64),
        timestamps_s=np.arange(frames, dtype=np.float64) / 30.0,
        fps=30.0,
        metadata=metadata or {},
    )


def test_baseline_depth_is_relative_3d() -> None:
    quality = assess_motion_quality(_sequence({"lifter": "baseline", "is_3d": True}))
    assert quality.level is MotionQualityLevel.RELATIVE_3D
    assert quality.score_confidence == 0.65
    assert quality.motion_scale == 0.80


def test_explicit_calibration_can_be_verified() -> None:
    quality = assess_motion_quality(
        _sequence({"quality_verified": True, "calibration_id": "lab-01"})
    )
    assert quality.level is MotionQualityLevel.VERIFIED_3D
    assert quality.score_confidence == 1.0


def test_learned_lifter_is_hybrid_not_verified() -> None:
    quality = assess_motion_quality(_sequence({"learned_lifter": True}))
    assert quality.level is MotionQualityLevel.HYBRID_3D
    assert quality.score_confidence < 1.0
