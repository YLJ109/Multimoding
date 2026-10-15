"""Coordinate normalization for canonical COCO-17 poses.

The comparison layer works in body-local coordinates instead of raw image
pixels.  The conventions are intentionally small and explicit:

* ``x`` grows to the right of the image;
* ``y`` grows upward after conversion from image coordinates;
* ``z`` keeps the source depth convention and is scaled by torso length;
* the origin is the hip midpoint;
* distances are measured in torso-length units.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from dance_mirror.domain.skeleton import LEFT_RIGHT_SWAP, CocoJoint
from dance_mirror.domain.types import PoseFrame, PoseSequence

FloatArray = NDArray[np.float64]


class NormalizationError(ValueError):
    """Raised when a pose cannot be normalized safely."""



def mirror_keypoints(
    keypoints: FloatArray,
    *,
    scores: FloatArray | None = None,
) -> tuple[FloatArray, FloatArray | None]:
    """Swap left/right joints while preserving the canonical array layout."""
    points = np.asarray(keypoints, dtype=np.float64)
    if points.shape != (17, 3):
        raise NormalizationError(f"expected keypoints shape (17, 3), got {points.shape}")
    mirrored = points[np.asarray(LEFT_RIGHT_SWAP, dtype=np.int64)].copy()
    if scores is None:
        return mirrored, None
    score_values = np.asarray(scores, dtype=np.float64)
    if score_values.shape != (17,):
        raise NormalizationError(f"expected scores shape (17,), got {score_values.shape}")
    return mirrored, score_values[np.asarray(LEFT_RIGHT_SWAP, dtype=np.int64)].copy()


def _joint(
    keypoints: FloatArray,
    scores: FloatArray,
    joint: CocoJoint,
    *,
    min_confidence: float,
) -> FloatArray | None:
    index = int(joint)
    if scores[index] < min_confidence:
        return None
    point = keypoints[index]
    if not np.all(np.isfinite(point)):
        return None
    return point


def _midpoint(
    first: FloatArray | None,
    second: FloatArray | None,
) -> FloatArray | None:
    if first is None or second is None:
        return None
    return (first + second) / 2.0


def _centre_or_single(
    first: FloatArray | None,
    second: FloatArray | None,
) -> FloatArray | None:
    """Use a true centre when possible and one visible joint as fallback."""
    centre = _midpoint(first, second)
    if centre is not None:
        return centre
    return first if first is not None else second


def normalize_frame(
    frame: PoseFrame,
    *,
    image_size: tuple[int, int] | None = None,
    mirror: bool = False,
    min_confidence: float = 0.2,
    torso_floor: float = 0.03,
) -> PoseFrame:
    """Convert one pose into a scale- and translation-normalized frame.

    ``image_size`` is ``(width, height)``.  Supply it when keypoints are
    expressed in pixels.  If omitted, keypoints are assumed to be already
    normalized to the image plane.
    """
    keypoints = np.asarray(frame.keypoints, dtype=np.float64).copy()
    scores = np.asarray(frame.scores, dtype=np.float64).copy()
    if mirror:
        keypoints, scores = mirror_keypoints(keypoints, scores=scores)
        # A true horizontal mirror swaps left/right labels AND reflects x about
        # the body centre.  Skipping the x flip only relabels the joints and
        # drives the robot's limbs across the body.  `mirror_keypoints` already
        # swapped the array indices, so negating x here completes the reflection.
        keypoints[:, 0] = -keypoints[:, 0]

    if image_size is not None:
        width, height = image_size
        if width <= 0 or height <= 0:
            raise NormalizationError("image_size values must be positive")
        keypoints[:, 0] /= float(width)
        keypoints[:, 1] /= float(height)
        keypoints[:, 2] /= float(width)
        keypoints[:, 1] = 1.0 - keypoints[:, 1]

    # Essential joints occasionally receive low confidence in a side view or
    # during a fast turn. Use a lower threshold for normalisation only so one
    # weak frame does not abort an otherwise usable reference clip.
    essential_confidence = min(min_confidence, 0.10)
    left_hip = _joint(
        keypoints, scores, CocoJoint.LEFT_HIP, min_confidence=essential_confidence
    )
    right_hip = _joint(
        keypoints, scores, CocoJoint.RIGHT_HIP, min_confidence=essential_confidence
    )
    left_shoulder = _joint(
        keypoints, scores, CocoJoint.LEFT_SHOULDER, min_confidence=essential_confidence
    )
    right_shoulder = _joint(
        keypoints, scores, CocoJoint.RIGHT_SHOULDER, min_confidence=essential_confidence
    )
    hip_center = _centre_or_single(left_hip, right_hip)
    shoulder_center = _centre_or_single(left_shoulder, right_shoulder)
    default_torso = 0.25

    if hip_center is None and shoulder_center is not None:
        hip_center = shoulder_center - np.asarray([0.0, default_torso, 0.0])
    if shoulder_center is None and hip_center is not None:
        shoulder_center = hip_center + np.asarray([0.0, default_torso, 0.0])
    if hip_center is None or shoulder_center is None:
        raise NormalizationError(
            "at least one hip or shoulder joint is required for normalization"
        )

    torso = shoulder_center - hip_center
    torso_length = float(np.linalg.norm(torso))
    if not np.isfinite(torso_length) or torso_length < torso_floor:
        span_candidates: list[float] = []
        if left_shoulder is not None and right_shoulder is not None:
            span_candidates.append(
                float(np.linalg.norm(left_shoulder - right_shoulder))
            )
        if left_hip is not None and right_hip is not None:
            span_candidates.append(float(np.linalg.norm(left_hip - right_hip)))
        torso_length = max(span_candidates, default=default_torso)
    if not np.isfinite(torso_length) or torso_length < torso_floor:
        torso_length = default_torso

    keypoints = (keypoints - hip_center) / torso_length
    # A small z component keeps the output useful for a depth-aware renderer.
    keypoints[:, 2] = np.nan_to_num(keypoints[:, 2], nan=0.0)
    unknown = scores < min_confidence
    for joint in (
        CocoJoint.LEFT_SHOULDER,
        CocoJoint.RIGHT_SHOULDER,
        CocoJoint.LEFT_HIP,
        CocoJoint.RIGHT_HIP,
    ):
        index = int(joint)
        if scores[index] >= essential_confidence and np.all(np.isfinite(keypoints[index])):
            unknown[index] = False
    keypoints[unknown] = 0.0
    return PoseFrame(
        keypoints=keypoints,
        scores=scores,
        timestamp_s=frame.timestamp_s,
        frame_index=frame.frame_index,
        schema=frame.schema,
    )


def normalize_sequence(
    sequence: PoseSequence,
    *,
    image_size: tuple[int, int] | None = None,
    mirror: bool = False,
    min_confidence: float = 0.2,
    torso_floor: float = 0.03,
) -> PoseSequence:
    """Normalize every frame without changing its timestamp or frame index."""
    normalized: list[PoseFrame] = []
    for index in range(len(sequence)):
        frame = PoseFrame(
            keypoints=sequence.keypoints[index],
            scores=sequence.scores[index],
            timestamp_s=float(sequence.timestamps_s[index]),
            frame_index=index,
            schema=sequence.schema,
        )
        try:
            normalized.append(
                normalize_frame(
                    frame,
                    image_size=image_size,
                    mirror=mirror,
                    min_confidence=min_confidence,
                    torso_floor=torso_floor,
                )
            )
        except NormalizationError:
            # A missing person in a reference video should not abort the full
            # clip.  The frame is kept as invalid and filtered by confidence.
            points = np.zeros((17, 3), dtype=np.float64)
            points[:, 2] = 0.0
            normalized.append(
                PoseFrame(
                    keypoints=points,
                    scores=np.zeros(17, dtype=np.float64),
                    timestamp_s=frame.timestamp_s,
                    frame_index=frame.frame_index,
                    schema=frame.schema,
                )
            )

    if not normalized:
        return PoseSequence(
            keypoints=np.zeros((0, 17, 3), dtype=np.float64),
            scores=np.zeros((0, 17), dtype=np.float64),
            timestamps_s=np.zeros(0, dtype=np.float64),
            fps=sequence.fps,
            schema=sequence.schema,
            metadata=dict(sequence.metadata),
        )

    return PoseSequence(
        keypoints=np.stack([item.keypoints for item in normalized], axis=0),
        scores=np.stack([item.scores for item in normalized], axis=0),
        timestamps_s=np.asarray(
            [item.timestamp_s for item in normalized], dtype=np.float64
        ),
        fps=sequence.fps,
        schema=sequence.schema,
        metadata={
            **dict(sequence.metadata),
            "normalized": True,
            "mirrored": mirror,
        },
    )


def orientation_safe_mirror(sequence: PoseSequence) -> PoseSequence:
    """Return a mirrored copy with matching metadata."""
    points, scores = mirror_keypoints(
        sequence.keypoints[0] if len(sequence) else np.zeros((17, 3)),
        scores=sequence.scores[0] if len(sequence) else np.zeros(17),
    )
    del points, scores
    mirrored_points = sequence.keypoints[:, np.asarray(LEFT_RIGHT_SWAP, dtype=np.int64)]
    mirrored_scores = sequence.scores[:, np.asarray(LEFT_RIGHT_SWAP, dtype=np.int64)]
    return PoseSequence(
        keypoints=mirrored_points.copy(),
        scores=mirrored_scores.copy(),
        timestamps_s=sequence.timestamps_s.copy(),
        fps=sequence.fps,
        schema=sequence.schema,
        metadata={**dict(sequence.metadata), "mirrored": True},
    )
