"""Tests for view-aware comparison and left/right semantic alignment."""

from __future__ import annotations

import math

from dance_mirror.domain.types import FeatureVector
from dance_mirror.motion.comparison import ComparisonConfig, compare_feature_frames
from dance_mirror.motion.comparison_space import (
    CameraProfile,
    CameraView,
    SemanticAlignment,
    build_comparison_space,
)
from dance_mirror.motion.features import FEATURE_NAMES


def _vector(
    overrides: dict[str, float] | None = None,
    *,
    confidence: float = 1.0,
) -> FeatureVector:
    values = {name: 0.0 for name in FEATURE_NAMES}
    if overrides:
        values.update(overrides)
    return FeatureVector(
        values=values,
        confidence={name: confidence for name in FEATURE_NAMES},
    )


def test_front_to_side_does_not_penalize_lateral_projection() -> None:
    reference = _vector()
    actual = _vector(
        {
            "left_wrist_side": 1.0,
            "right_wrist_side": -1.0,
            "body_lean": 0.8,
            "hip_shift": -0.6,
        }
    )
    space = build_comparison_space(
        CameraProfile(view=CameraView.FRONT),
        CameraProfile(view=CameraView.LEFT_PROFILE),
    )
    score = compare_feature_frames(
        reference,
        actual,
        config=ComparisonConfig(feature_space=space),
    )
    assert score.overall > 85.0
    assert space.weight("left_wrist_side") < 0.2
    assert space.weight("left_elbow_angle") == 1.0


def test_mirrored_semantics_are_applied_before_comparison() -> None:
    reference = _vector({"left_elbow_angle": 1.0, "right_elbow_angle": 1.0})
    actual = _vector({"left_elbow_angle": 2.0, "right_elbow_angle": 1.0})
    space = build_comparison_space(
        CameraProfile(view=CameraView.FRONT),
        CameraProfile(
            view=CameraView.FRONT,
            semantic_alignment=SemanticAlignment.MIRRORED,
        ),
    )
    aligned = space.align_actual(actual)
    assert aligned.values["left_elbow_angle"] == 1.0
    assert aligned.values["right_elbow_angle"] == 2.0
    score = compare_feature_frames(
        reference,
        actual,
        config=ComparisonConfig(feature_space=space),
    )
    # The mirror map exchanges source values before the deviation comparison.
    assert score.by_feature["left_elbow_angle"] == 100.0
    assert score.by_feature["right_elbow_angle"] < 100.0


def test_unknown_camera_reduces_evidence_instead_of_inventing_certainty() -> None:
    space = build_comparison_space(CameraProfile(), CameraProfile())
    assert space.evidence_scale < 0.8
    assert "camera_view_unknown" in space.reasons
    assert not math.isclose(space.weight("left_wrist_side"), 1.0)
