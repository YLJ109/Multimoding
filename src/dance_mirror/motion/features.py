"""Interpretable motion features extracted from normalized poses.

Each feature is designed to be useful for both scoring and a human-readable
coaching cue.  Missing or low-confidence landmarks produce ``nan`` and are
reported as low confidence instead of being silently treated as zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dance_mirror.domain.skeleton import JOINT_WEIGHTS
from dance_mirror.domain.types import FeatureVector, PoseFrame, PoseSequence

FloatArray = NDArray[np.float64]

FEATURE_NAMES: tuple[str, ...] = (
    "left_wrist_height",
    "right_wrist_height",
    "left_wrist_side",
    "right_wrist_side",
    "left_elbow_angle",
    "right_elbow_angle",
    "left_knee_angle",
    "right_knee_angle",
    "left_foot_height",
    "right_foot_height",
    "body_lean",
    "hip_shift",
)

LEFT_FEATURES = frozenset(
    {
        "left_wrist_height",
        "left_wrist_side",
        "left_elbow_angle",
        "left_knee_angle",
        "left_foot_height",
    }
)
RIGHT_FEATURES = frozenset(
    {
        "right_wrist_height",
        "right_wrist_side",
        "right_elbow_angle",
        "right_knee_angle",
        "right_foot_height",
    }
)


@dataclass(slots=True)
class FeatureSequence:
    """Frame-aligned feature vectors stored as a dense matrix."""

    timestamps_s: FloatArray
    values: FloatArray
    confidence: FloatArray
    names: tuple[str, ...] = FEATURE_NAMES

    def __post_init__(self) -> None:
        self.timestamps_s = np.asarray(self.timestamps_s, dtype=np.float64)
        self.values = np.asarray(self.values, dtype=np.float64)
        self.confidence = np.asarray(self.confidence, dtype=np.float64)
        expected = (len(self.timestamps_s), len(self.names))
        if self.values.shape != expected:
            raise ValueError(f"values must have shape {expected}, got {self.values.shape}")
        if self.confidence.shape != expected:
            raise ValueError(
                f"confidence must have shape {expected}, got {self.confidence.shape}"
            )

    def __len__(self) -> int:
        return len(self.timestamps_s)

    def frame(self, index: int) -> FeatureVector:
        values = {
            name: float(self.values[index, column])
            for column, name in enumerate(self.names)
        }
        confidence = {
            name: float(self.confidence[index, column])
            for column, name in enumerate(self.names)
        }
        return FeatureVector(values=values, confidence=confidence)


def _point(
    frame: PoseFrame,
    index: int,
    *,
    min_confidence: float,
) -> tuple[FloatArray, float] | None:
    if frame.scores[index] < min_confidence:
        return None
    point = np.asarray(frame.keypoints[index], dtype=np.float64)
    if not np.all(np.isfinite(point)):
        return None
    return point, float(frame.scores[index])


def _angle(
    first: tuple[FloatArray, float] | None,
    center: tuple[FloatArray, float] | None,
    second: tuple[FloatArray, float] | None,
) -> tuple[float, float]:
    if first is None or center is None or second is None:
        return math.nan, 0.0
    first_vector = first[0] - center[0]
    second_vector = second[0] - center[0]
    denominator = float(np.linalg.norm(first_vector) * np.linalg.norm(second_vector))
    if denominator <= 1e-8:
        return math.nan, 0.0
    cosine = float(np.dot(first_vector, second_vector) / denominator)
    angle = math.acos(float(np.clip(cosine, -1.0, 1.0)))
    confidence = min(first[1], center[1], second[1])
    return angle, confidence


def extract_features(
    frame: PoseFrame,
    *,
    min_confidence: float = 0.2,
) -> FeatureVector:
    """Extract normalized, interpretable features from one body-local pose."""
    left_shoulder = _point(
        frame, 5, min_confidence=min_confidence
    )
    right_shoulder = _point(
        frame, 6, min_confidence=min_confidence
    )
    left_elbow = _point(frame, 7, min_confidence=min_confidence)
    right_elbow = _point(frame, 8, min_confidence=min_confidence)
    left_wrist = _point(frame, 9, min_confidence=min_confidence)
    right_wrist = _point(frame, 10, min_confidence=min_confidence)
    left_hip = _point(frame, 11, min_confidence=min_confidence)
    right_hip = _point(frame, 12, min_confidence=min_confidence)
    left_knee = _point(frame, 13, min_confidence=min_confidence)
    right_knee = _point(frame, 14, min_confidence=min_confidence)
    left_ankle = _point(frame, 15, min_confidence=min_confidence)
    right_ankle = _point(frame, 16, min_confidence=min_confidence)

    values: dict[str, float] = {name: math.nan for name in FEATURE_NAMES}
    confidence: dict[str, float] = {name: 0.0 for name in FEATURE_NAMES}

    if left_wrist is not None and left_shoulder is not None:
        values["left_wrist_height"] = float(left_wrist[0][1] - left_shoulder[0][1])
        confidence["left_wrist_height"] = min(
            left_wrist[1], left_shoulder[1]
        )
        values["left_wrist_side"] = float(left_wrist[0][0] - left_shoulder[0][0])
        confidence["left_wrist_side"] = confidence["left_wrist_height"]
    if right_wrist is not None and right_shoulder is not None:
        values["right_wrist_height"] = float(
            right_wrist[0][1] - right_shoulder[0][1]
        )
        confidence["right_wrist_height"] = min(
            right_wrist[1], right_shoulder[1]
        )
        values["right_wrist_side"] = float(
            right_wrist[0][0] - right_shoulder[0][0]
        )
        confidence["right_wrist_side"] = confidence["right_wrist_height"]

    angle, angle_confidence = _angle(left_shoulder, left_elbow, left_wrist)
    values["left_elbow_angle"], confidence["left_elbow_angle"] = (
        angle,
        angle_confidence,
    )
    angle, angle_confidence = _angle(right_shoulder, right_elbow, right_wrist)
    values["right_elbow_angle"], confidence["right_elbow_angle"] = (
        angle,
        angle_confidence,
    )
    angle, angle_confidence = _angle(left_hip, left_knee, left_ankle)
    values["left_knee_angle"], confidence["left_knee_angle"] = (
        angle,
        angle_confidence,
    )
    angle, angle_confidence = _angle(right_hip, right_knee, right_ankle)
    values["right_knee_angle"], confidence["right_knee_angle"] = (
        angle,
        angle_confidence,
    )

    if left_ankle is not None and right_ankle is not None:
        lowest = min(float(left_ankle[0][1]), float(right_ankle[0][1]))
        values["left_foot_height"] = float(left_ankle[0][1] - lowest)
        values["right_foot_height"] = float(right_ankle[0][1] - lowest)
        confidence["left_foot_height"] = left_ankle[1]
        confidence["right_foot_height"] = right_ankle[1]

    shoulder_center = _center(left_shoulder, right_shoulder)
    hip_center = _center(left_hip, right_hip)
    ankle_center = _center(left_ankle, right_ankle)
    if shoulder_center is not None and hip_center is not None:
        values["body_lean"] = float(shoulder_center[0][0] - hip_center[0][0])
        confidence["body_lean"] = min(shoulder_center[1], hip_center[1])
    if hip_center is not None and ankle_center is not None:
        values["hip_shift"] = float(hip_center[0][0] - ankle_center[0][0])
        confidence["hip_shift"] = min(hip_center[1], ankle_center[1])

    return FeatureVector(values=values, confidence=confidence)


def _center(
    first: tuple[FloatArray, float] | None,
    second: tuple[FloatArray, float] | None,
) -> tuple[FloatArray, float] | None:
    if first is None or second is None:
        return None
    return (first[0] + second[0]) / 2.0, min(first[1], second[1])


def extract_feature_sequence(
    sequence: PoseSequence,
    *,
    min_confidence: float = 0.2,
) -> FeatureSequence:
    """Extract a dense feature sequence with one row per pose frame."""
    values = np.full((len(sequence), len(FEATURE_NAMES)), np.nan, dtype=np.float64)
    confidence = np.zeros_like(values)
    for index in range(len(sequence)):
        frame = PoseFrame(
            keypoints=sequence.keypoints[index],
            scores=sequence.scores[index],
            timestamp_s=float(sequence.timestamps_s[index]),
            frame_index=index,
            schema=sequence.schema,
        )
        feature = extract_features(frame, min_confidence=min_confidence)
        for column, name in enumerate(FEATURE_NAMES):
            values[index, column] = feature.values[name]
            confidence[index, column] = feature.confidence[name]
    return FeatureSequence(
        timestamps_s=sequence.timestamps_s,
        values=values,
        confidence=confidence,
    )


def feature_weight(name: str) -> float:
    """Return the configured comparison weight for a feature."""
    return float(JOINT_WEIGHTS.get(name, 1.0))
