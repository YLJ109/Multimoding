"""Deterministic hand-gesture classifier tests."""

from __future__ import annotations

import numpy as np

from dance_mirror.motion.hand_features import hands_by_side, match_hands_to_wrists
from dance_mirror.multimodal.gesture import (
    HandGesture,
    classify_hand_landmarks,
    pose_hand_search_roi,
    select_primary_gesture,
)


def _base_landmarks() -> np.ndarray:
    points = np.zeros((21, 3), dtype=np.float64)
    points[0] = (0.0, 0.0, 0.0)
    points[9] = (0.0, 0.5, 0.0)
    return points


def test_open_palm_is_classified_without_mediapipe_runtime() -> None:
    points = _base_landmarks()
    points[4] = (-0.25, -0.05, 0.0)
    for mcp, pip, tip, x in (
        (5, 6, 8, 0.10),
        (9, 10, 12, 0.00),
        (13, 14, 16, -0.10),
        (17, 18, 20, -0.20),
    ):
        points[mcp] = (x, 0.20, 0.0)
        points[pip] = (x, 0.42, 0.0)
        points[tip] = (x, 0.70, 0.0)
    gesture = classify_hand_landmarks(points)
    assert gesture.name == "open_palm"
    assert gesture.confidence >= 0.8


def test_closed_fist_is_classified() -> None:
    points = _base_landmarks()
    points[4] = (0.02, 0.10, 0.0)
    for mcp, pip, tip, x in (
        (5, 6, 8, 0.10),
        (9, 10, 12, 0.00),
        (13, 14, 16, -0.10),
        (17, 18, 20, -0.20),
    ):
        points[mcp] = (x, 0.20, 0.0)
        points[pip] = (x, 0.34, 0.0)
        points[tip] = (x, 0.28, 0.0)
    gesture = classify_hand_landmarks(points)
    assert gesture.name == "fist"
    assert gesture.confidence >= 0.8


def _hand_at(x: float, *, handedness: str = "unknown") -> HandGesture:
    points = _base_landmarks()
    points[0, 0] = x
    return HandGesture("open_palm", 0.9, points, handedness)


def test_hand_side_follows_nearest_wrist_instead_of_mediapipe_label() -> None:
    # MediaPipe deliberately returns the wrong sides here to prove the
    # matching layer is authoritative.
    hands = (_hand_at(0.78, handedness="left"), _hand_at(0.22, handedness="right"))
    matched = match_hands_to_wrists(
        hands,
        left_wrist=(120.0, 200.0),
        right_wrist=(520.0, 200.0),
        image_size=(640, 480),
    )
    sides = {side for side, _ in matched}
    assert sides == {"left", "right"}
    assert {side for side, hand in matched if hand is hands[0]} == {"right"}
    assert {side for side, hand in matched if hand is hands[1]} == {"left"}


def test_mirrored_hand_side_matches_mirrored_body_skeleton() -> None:
    hands = (_hand_at(0.78), _hand_at(0.22))
    mapped = hands_by_side(
        hands,
        left_wrist=(120.0, 200.0),
        right_wrist=(520.0, 200.0),
        image_size=(640, 480),
        mirror=True,
    )
    assert set(mapped) == {"left", "right"}
    assert np.isclose(mapped["left"][0, 0], 0.78)
    assert np.isclose(mapped["right"][0, 0], 0.22)


def test_ok_gesture_accepts_two_extended_support_fingers() -> None:
    points = _base_landmarks()
    points[4] = (0.10, 0.30, 0.0)
    points[8] = (0.08, 0.32, 0.0)
    for mcp, pip, tip, x in (
        (9, 10, 12, 0.00),
        (13, 14, 16, -0.10),
        (17, 18, 20, -0.20),
    ):
        points[mcp] = (x, 0.20, 0.0)
        points[pip] = (x, 0.42, 0.0)
        points[tip] = (x, 0.70, 0.0)
    gesture = classify_hand_landmarks(points)
    assert gesture.name == "ok"
    assert gesture.confidence >= 0.55


def test_ok_gesture_is_preferred_over_higher_confidence_palm() -> None:
    ok = HandGesture("ok", 0.55, _base_landmarks(), "left")
    palm = HandGesture("open_palm", 0.92, _base_landmarks(), "right")
    assert select_primary_gesture((palm, ok)) is ok


def test_ok_gesture_tolerates_loose_thumb_index_contact() -> None:
    points = _base_landmarks()
    points[4] = (0.20, 0.28, 0.0)
    points[7] = (0.08, 0.30, 0.0)
    points[8] = (0.07, 0.46, 0.0)
    for mcp, pip, tip, x in (
        (9, 10, 12, 0.0),
        (13, 14, 16, -0.1),
        (17, 18, 20, -0.2),
    ):
        points[mcp] = (x, 0.2, 0.0)
        points[pip] = (x, 0.42, 0.0)
        points[tip] = (x, 0.7, 0.0)
    gesture = classify_hand_landmarks(points)
    assert gesture.name == "ok"
    assert gesture.confidence >= 0.55


def test_pose_roi_contains_visible_arms_and_torso() -> None:
    points = np.zeros((17, 3), dtype=np.float64)
    scores = np.zeros(17, dtype=np.float64)
    for index, point in {
        5: (100.0, 110.0, 0.0),
        6: (300.0, 110.0, 0.0),
        7: (80.0, 170.0, 0.0),
        8: (330.0, 175.0, 0.0),
        9: (70.0, 210.0, 0.0),
        10: (350.0, 215.0, 0.0),
        11: (160.0, 300.0, 0.0),
        12: (260.0, 300.0, 0.0),
    }.items():
        points[index] = point
        scores[index] = 0.9
    roi = pose_hand_search_roi(points, scores, (640, 480))
    assert roi is not None
    x1, y1, x2, y2 = roi
    assert x1 <= 70 and y1 <= 110
    assert x2 >= 350 and y2 >= 300
