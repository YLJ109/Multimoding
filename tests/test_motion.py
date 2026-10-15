"""Focused tests for the dependency-light motion core."""

from __future__ import annotations

import numpy as np

from dance_mirror.coaching.policy import CoachPolicy
from dance_mirror.domain.skeleton import LEFT_RIGHT_SWAP
from dance_mirror.domain.types import FeatureVector, JointDeviation, PoseFrame, TrainingScore
from dance_mirror.motion.alignment import dtw_align
from dance_mirror.motion.comparison import compare_feature_frames
from dance_mirror.motion.features import FEATURE_NAMES, FeatureSequence, extract_features
from dance_mirror.motion.normalization import mirror_keypoints, normalize_frame


def _raw_pose() -> PoseFrame:
    keypoints = np.zeros((17, 3), dtype=np.float64)
    keypoints[0] = (320, 80, 0)
    keypoints[5] = (300, 100, 0)
    keypoints[6] = (340, 100, 0)
    keypoints[7] = (280, 160, 0)
    keypoints[8] = (360, 160, 0)
    keypoints[9] = (260, 220, 0)
    keypoints[10] = (380, 220, 0)
    keypoints[11] = (305, 300, 0)
    keypoints[12] = (335, 300, 0)
    keypoints[13] = (300, 380, 0)
    keypoints[14] = (340, 380, 0)
    keypoints[15] = (295, 460, 0)
    keypoints[16] = (345, 460, 0)
    return PoseFrame(
        keypoints=keypoints,
        scores=np.ones(17, dtype=np.float64),
        timestamp_s=0.0,
        frame_index=0,
    )


def test_normalization_moves_hips_to_origin_and_scales_torso() -> None:
    normalized = normalize_frame(_raw_pose(), image_size=(640, 480))
    hip_center = (normalized.keypoints[11] + normalized.keypoints[12]) / 2.0
    shoulder_center = (normalized.keypoints[5] + normalized.keypoints[6]) / 2.0
    assert np.allclose(hip_center, (0.0, 0.0, 0.0), atol=1e-9)
    assert np.linalg.norm(shoulder_center) == 1.0
    assert normalized.keypoints[0, 1] > normalized.keypoints[11, 1]


def test_mirror_swaps_left_and_right_semantics() -> None:
    points, scores = mirror_keypoints(_raw_pose().keypoints, scores=_raw_pose().scores)
    assert np.array_equal(points[5], _raw_pose().keypoints[6])
    assert np.array_equal(points[9], _raw_pose().keypoints[10])
    assert np.array_equal(scores[5], _raw_pose().scores[6])


def test_normalize_frame_mirror_is_a_true_reflection() -> None:
    """D1 regression: mirroring must reflect x, not merely relabel joints.

    A relabel-only mirror leaves x untouched, so the robot's limbs end up on the
    wrong side and cross the body.  The fix negates x about the body centre.
    """
    raw = _raw_pose()
    plain = normalize_frame(raw, image_size=(640, 480), mirror=False)
    mirror = normalize_frame(raw, image_size=(640, 480), mirror=True)
    swap = np.asarray(LEFT_RIGHT_SWAP, dtype=np.int64)

    # exact reflection: x flips, y and z carry over unchanged
    assert np.allclose(mirror.keypoints[:, 0], -plain.keypoints[swap, 0], atol=1e-12)
    assert np.allclose(mirror.keypoints[:, 1:], plain.keypoints[swap, 1:], atol=1e-12)
    # ...and it is explicitly NOT the old relabel-only behaviour
    assert not np.allclose(mirror.keypoints[:, 0], plain.keypoints[swap, 0], atol=1e-12)


def test_normalization_accepts_one_visible_shoulder_and_hip() -> None:
    frame = _raw_pose()
    frame.scores = np.zeros(17, dtype=np.float64)
    frame.scores[5] = 0.15
    frame.scores[11] = 0.15

    normalized = normalize_frame(frame, image_size=(640, 480), min_confidence=0.25)

    assert np.all(np.isfinite(normalized.keypoints))
    assert normalized.keypoints[5, 1] > 0.5
    assert normalized.scores[5] == 0.15
    assert normalized.scores[11] == 0.15


def _feature_pose() -> PoseFrame:
    points = np.zeros((17, 3), dtype=np.float64)
    points[5] = (-0.25, 1.0, 0.0)
    points[6] = (0.25, 1.0, 0.0)
    points[7] = (-0.55, 0.85, 0.0)
    points[8] = (0.55, 0.85, 0.0)
    points[9] = (-0.85, 0.70, 0.0)
    points[10] = (0.85, 0.70, 0.0)
    points[11] = (-0.15, 0.0, 0.0)
    points[12] = (0.15, 0.0, 0.0)
    points[13] = (-0.2, -0.8, 0.0)
    points[14] = (0.2, -0.8, 0.0)
    points[15] = (-0.25, -1.55, 0.0)
    points[16] = (0.25, -1.55, 0.0)
    return PoseFrame(
        keypoints=points,
        scores=np.ones(17, dtype=np.float64),
        timestamp_s=0.0,
        frame_index=0,
    )


def test_feature_extraction_and_identical_score() -> None:
    feature = extract_features(_feature_pose())
    assert all(name in feature.values for name in FEATURE_NAMES)
    score = compare_feature_frames(feature, feature)
    assert score.overall == 100.0
    assert len(score.deviations) >= 8


def test_dtw_path_is_monotonic() -> None:
    reference = FeatureSequence(
        timestamps_s=np.arange(5, dtype=np.float64) / 10,
        values=np.arange(10, dtype=np.float64).reshape(5, 2),
        confidence=np.ones((5, 2), dtype=np.float64),
        names=("first", "second"),
    )
    user = FeatureSequence(
        timestamps_s=np.arange(5, dtype=np.float64) / 10,
        values=np.arange(10, dtype=np.float64).reshape(5, 2),
        confidence=np.ones((5, 2), dtype=np.float64),
        names=("first", "second"),
    )
    result = dtw_align(reference, user)
    assert result.path
    assert all(
        right[0] >= left[0] and right[1] >= left[1]
        for left, right in zip(result.path[:-1], result.path[1:], strict=False)
    )


def test_policy_requires_persistence_and_cooldown() -> None:
    deviation = JointDeviation(
        feature="left_wrist_height",
        reference=0.0,
        actual=1.0,
        delta=1.0,
        error_ratio=3.0,
        confidence=0.9,
    )
    score = TrainingScore(overall=20.0, by_feature={"left_wrist_height": 20.0}, deviations=[deviation])
    policy = CoachPolicy()
    assert policy.evaluate(score, 0.0) is None
    cue = policy.evaluate(score, 0.8)
    assert cue is not None
    assert cue.feature == "left_wrist_height"
    assert policy.evaluate(score, 1.0) is None


def test_feature_vector_confidence_is_preserved() -> None:
    vector = FeatureVector(values={"left_wrist_height": 1.0}, confidence={"left_wrist_height": 0.8})
    assert vector.confidence["left_wrist_height"] == 0.8
