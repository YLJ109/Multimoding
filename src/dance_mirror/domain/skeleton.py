"""COCO-17 skeleton metadata shared by all motion components."""

from __future__ import annotations

from enum import IntEnum


class CocoJoint(IntEnum):
    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 3
    RIGHT_EAR = 4
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    LEFT_KNEE = 13
    RIGHT_KNEE = 14
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16


JOINT_NAMES: tuple[str, ...] = tuple(joint.name.lower() for joint in CocoJoint)

EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)

LEFT_RIGHT_SWAP: tuple[int, ...] = (
    0,
    2,
    1,
    4,
    3,
    6,
    5,
    8,
    7,
    10,
    9,
    12,
    11,
    14,
    13,
    16,
    15,
)

JOINT_WEIGHTS: dict[str, float] = {
    "left_wrist_height": 1.2,
    "right_wrist_height": 1.2,
    "left_wrist_side": 0.8,
    "right_wrist_side": 0.8,
    "left_elbow_angle": 1.0,
    "right_elbow_angle": 1.0,
    "left_knee_angle": 1.1,
    "right_knee_angle": 1.1,
    "left_foot_height": 0.8,
    "right_foot_height": 0.8,
    "body_lean": 1.0,
    "hip_shift": 0.8,
}
