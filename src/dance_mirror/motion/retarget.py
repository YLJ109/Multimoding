"""Convert canonical normalized poses into renderer-ready skeletons."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from dance_mirror.domain.skeleton import EDGES, CocoJoint
from dance_mirror.domain.types import PoseFrame, PoseSequence


@dataclass(slots=True)
class RetargetedSkeleton:
    """A renderer-friendly skeleton with named joints and stable edges."""

    joints: dict[str, tuple[float, float, float]]
    scores: dict[str, float]
    edges: tuple[tuple[str, str], ...]
    timestamp_s: float
    frame_index: int
    hands: dict[str, tuple[tuple[float, float, float], ...]] | None = None


JOINT_KEYS: tuple[str, ...] = tuple(joint.name.lower() for joint in CocoJoint)
RENDER_EDGES: tuple[tuple[str, str], ...] = tuple(
    (JOINT_KEYS[first], JOINT_KEYS[second]) for first, second in EDGES
)


def _normalize_hands(
    hands: Mapping[str, np.ndarray] | None,
) -> dict[str, tuple[tuple[float, float, float], ...]] | None:
    if not hands:
        return None
    output: dict[str, tuple[tuple[float, float, float], ...]] = {}
    for side, raw_points in hands.items():
        if side not in {"left", "right", "unknown"}:
            continue
        points = np.asarray(raw_points, dtype=np.float64)
        if points.shape != (21, 3):
            raise ValueError("retargeted hands must have shape (21, 3)")
        output[side] = tuple(
            (float(point[0]), float(point[1]), float(point[2]))
            for point in points
        )
    return output or None


def retarget_frame(
    frame: PoseFrame,
    *,
    hands: Mapping[str, np.ndarray] | None = None,
) -> RetargetedSkeleton:
    """Map one normalized pose frame to a serializable skeleton."""
    points = np.asarray(frame.keypoints, dtype=np.float64)
    if points.shape != (17, 3):
        raise ValueError(f"expected (17, 3) pose, got {points.shape}")
    hand_payload = _normalize_hands(hands)
    joints = {
        JOINT_KEYS[index]: (
            float(points[index, 0]),
            float(points[index, 1]),
            float(points[index, 2]),
        )
        for index in range(17)
    }
    scores = {
        JOINT_KEYS[index]: float(frame.scores[index]) for index in range(17)
    }
    return RetargetedSkeleton(
        joints=joints,
        scores=scores,
        edges=RENDER_EDGES,
        timestamp_s=frame.timestamp_s,
        frame_index=frame.frame_index,
        hands=hand_payload,
    )


def retarget_sequence(sequence: PoseSequence) -> list[RetargetedSkeleton]:
    """Map a pose sequence into frames accepted by the 3D bridge."""
    output: list[RetargetedSkeleton] = []
    for index in range(len(sequence)):
        output.append(
            retarget_frame(
                PoseFrame(
                    keypoints=sequence.keypoints[index],
                    scores=sequence.scores[index],
                    timestamp_s=float(sequence.timestamps_s[index]),
                    frame_index=index,
                    schema=sequence.schema,
                )
            )
        )
    return output
