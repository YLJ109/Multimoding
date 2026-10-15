"""Optional MediaPipe hand gesture recognition with deterministic geometry."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from dance_mirror.runtime import isolate_mediapipe_runtime

LOGGER = logging.getLogger(__name__)

GESTURE_NAMES_ZH: dict[str, str] = {
    "ok": "OK手势",
    "open_palm": "张开手掌",
    "point": "单指指向",
    "fist": "握拳",
    "unknown": "未识别",
}

HAND_SIDE_NAMES_ZH: dict[str, str] = {
    "left": "左手",
    "right": "右手",
    "unknown": "未知手",
}

FACE_EXPRESSION_NAMES_ZH: dict[str, str] = {
    "neutral": "自然",
    "blink": "眨眼",
    "surprised": "惊讶",
    "smile": "微笑",
    "focused": "专注",
}


def gesture_name_zh(name: str) -> str:
    """Return the Chinese display name for a recognized gesture."""
    return GESTURE_NAMES_ZH.get(str(name or "").lower(), str(name or "未知"))


def hand_side_name_zh(side: str) -> str:
    """Return the Chinese display name for a hand side."""
    return HAND_SIDE_NAMES_ZH.get(str(side or "").lower(), "未知手")


def face_expression_name_zh(expression: str) -> str:
    """Return the Chinese display name for a face expression."""
    return FACE_EXPRESSION_NAMES_ZH.get(str(expression or "").lower(), str(expression or "人脸"))


_HAND_CONNECTIONS = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (0, 17),
)


@dataclass(frozen=True, slots=True)
class HandGesture:
    """One recognized hand gesture in normalized image coordinates."""

    name: str
    confidence: float
    landmarks: np.ndarray
    handedness: str = "unknown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "landmarks", np.asarray(self.landmarks, dtype=np.float64).copy())
        if self.landmarks.shape != (21, 3):
            raise ValueError("hand landmarks must have shape (21, 3)")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("gesture confidence must be in [0, 1]")
        if self.handedness not in {"left", "right", "unknown"}:
            raise ValueError("handedness must be left, right, or unknown")


def _distance(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.linalg.norm(first[:2] - second[:2]))


def _extended(
    landmarks: np.ndarray,
    mcp: int,
    pip: int,
    tip: int,
    wrist: np.ndarray,
) -> bool:
    pip_distance = max(1e-6, _distance(landmarks[pip], wrist))
    radial_extension = _distance(landmarks[tip], wrist) / pip_distance
    first = landmarks[pip, :2] - landmarks[mcp, :2]
    second = landmarks[tip, :2] - landmarks[pip, :2]
    denominator = max(
        1e-6,
        float(np.linalg.norm(first) * np.linalg.norm(second)),
    )
    bend_cosine = float(np.dot(first, second)) / denominator
    return radial_extension >= 1.04 and bend_cosine >= -0.2


def classify_hand_landmarks(landmarks: np.ndarray) -> HandGesture:
    """Classify one MediaPipe hand using scale-independent distances.

    The classifier intentionally exposes only a small whitelist. It can be
    replaced by a learned model without changing worker or UI contracts.
    """
    points = np.asarray(landmarks, dtype=np.float64)
    if points.shape != (21, 3):
        raise ValueError("hand landmarks must have shape (21, 3)")
    wrist = points[0]
    palm_scale = max(
        1e-6,
        _distance(points[0], points[9]),
        _distance(points[5], points[17]),
        _distance(points[5], points[9]),
    )
    index_extended = _extended(points, 5, 6, 8, wrist)
    middle_extended = _extended(points, 9, 10, 12, wrist)
    ring_extended = _extended(points, 13, 14, 16, wrist)
    pinky_extended = _extended(points, 17, 18, 20, wrist)
    thumb_index_gap = min(
        _distance(points[4], points[8]),
        _distance(points[4], points[7]),
    ) / palm_scale
    extended_count = sum(
        (index_extended, middle_extended, ring_extended, pinky_extended)
    )
    other_extended = sum((middle_extended, ring_extended, pinky_extended))
    if thumb_index_gap <= 0.50 and other_extended >= 2:
        pinch_quality = max(0.0, min(1.0, 1.0 - thumb_index_gap / 0.50))
        support_quality = other_extended / 3.0
        confidence = min(0.99, 0.56 + 0.27 * pinch_quality + 0.16 * support_quality)
        return HandGesture("ok", confidence, points)
    if extended_count >= 4:
        return HandGesture("open_palm", 0.84, points)
    if index_extended and not middle_extended and not ring_extended and not pinky_extended:
        return HandGesture("point", 0.82, points)
    if extended_count == 0:
        return HandGesture("fist", 0.80, points)
    return HandGesture("unknown", 0.0, points)


def pose_hand_search_roi(
    keypoints: np.ndarray,
    scores: np.ndarray,
    image_size: tuple[int, int],
    *,
    min_confidence: float = 0.25,
) -> tuple[int, int, int, int] | None:
    """Return a square upper-body/arm ROI that makes small hands easier to see."""
    points = np.asarray(keypoints, dtype=np.float64)
    confidence = np.asarray(scores, dtype=np.float64).reshape(-1)
    if points.shape != (17, 3) or confidence.shape != (17,):
        return None
    width, height = (int(image_size[0]), int(image_size[1]))
    if width <= 0 or height <= 0:
        return None
    visible_indices = [
        index
        for index in (5, 6, 7, 8, 9, 10, 11, 12)
        if confidence[index] >= min_confidence and np.all(np.isfinite(points[index, :2]))
    ]
    if not visible_indices:
        visible_indices = [
            index
            for index in (0, 5, 6, 9, 10)
            if confidence[index] >= min_confidence and np.all(np.isfinite(points[index, :2]))
        ]
    if not visible_indices:
        return None
    selected = points[visible_indices, :2]
    left, top = selected.min(axis=0)
    right, bottom = selected.max(axis=0)
    span_x = max(1.0, float(right - left))
    span_y = max(1.0, float(bottom - top))
    padding = max(64.0, 0.32 * max(span_x, span_y), 0.05 * min(width, height))
    x1 = max(0, int(np.floor(left - padding)))
    y1 = max(0, int(np.floor(top - padding)))
    x2 = min(width, int(np.ceil(right + padding)))
    y2 = min(height, int(np.ceil(bottom + padding)))
    if x2 - x1 < 160:
        extra = (160 - (x2 - x1)) / 2.0
        x1 = max(0, int(np.floor(x1 - extra)))
        x2 = min(width, int(np.ceil(x2 + extra)))
    if y2 - y1 < 160:
        extra = (160 - (y2 - y1)) / 2.0
        y1 = max(0, int(np.floor(y1 - extra)))
        y2 = min(height, int(np.ceil(y2 + extra)))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def select_primary_gesture(
    gestures: Sequence[HandGesture],
) -> HandGesture | None:
    """Prefer OK so a start gesture is never masked by the other hand."""
    ordered = tuple(gestures)
    if not ordered:
        return None
    for gesture in ordered:
        if str(gesture.name).strip().lower() == "ok":
            return gesture
    return max(ordered, key=lambda item: item.confidence)


class MediaPipeHandTracker:
    """Thread-confined optional MediaPipe wrapper."""

    def __init__(self, *, max_hands: int = 2, min_detection_confidence: float = 0.40) -> None:
        self.available = False
        self._hands: object | None = None
        try:
            isolate_mediapipe_runtime()
            import mediapipe as mp
        except Exception:
            LOGGER.warning("MediaPipe Hands is unavailable", exc_info=True)
            return
        try:
            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=max(1, min(2, int(max_hands))),
                model_complexity=0,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=0.40,
            )
        except Exception:
            LOGGER.exception("MediaPipe Hands initialization failed")
            return
        self.available = True

    def process(
        self,
        frame_bgr: np.ndarray,
        search_roi: tuple[int, int, int, int] | None = None,
    ) -> tuple[HandGesture, ...]:
        if not self.available or self._hands is None:
            return ()
        try:
            import cv2

            source = np.asarray(frame_bgr, dtype=np.uint8)
            height, width = source.shape[:2]
            crop = self._clamped_roi(search_roi, width, height)
            inference_frame = source
            offset_x = 0
            offset_y = 0
            if crop is not None:
                x1, y1, x2, y2 = crop
                inference_frame = source[y1:y2, x1:x2]
                offset_x = x1
                offset_y = y1
            rgb = cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)
        except Exception:
            LOGGER.exception("MediaPipe hand inference failed")
            return ()
        multi_hand_landmarks = getattr(results, "multi_hand_landmarks", None)
        if not multi_hand_landmarks and crop is not None:
            try:
                rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
                results = self._hands.process(rgb)
            except Exception:
                LOGGER.exception("MediaPipe full-frame hand inference failed")
                return ()
            offset_x = 0
            offset_y = 0
            inference_frame = source
            multi_hand_landmarks = getattr(results, "multi_hand_landmarks", None)
        if not multi_hand_landmarks:
            return ()
        gestures: list[HandGesture] = []
        for hand in multi_hand_landmarks:
            landmarks = np.asarray(
                [
                    (
                        (point.x * inference_frame.shape[1] + offset_x) / max(width, 1),
                        (point.y * inference_frame.shape[0] + offset_y) / max(height, 1),
                        point.z,
                    )
                    for point in hand.landmark
                ],
                dtype=np.float64,
            )
            gestures.append(classify_hand_landmarks(landmarks))
        handedness_results = getattr(results, "multi_handedness", None) or ()
        enriched: list[HandGesture] = []
        for index, gesture in enumerate(gestures):
            side = "unknown"
            if index < len(handedness_results):
                classifications = getattr(handedness_results[index], "classification", ())
                if classifications:
                    label = str(getattr(classifications[0], "label", "unknown")).lower()
                    side = label if label in {"left", "right"} else "unknown"
            enriched.append(
                HandGesture(gesture.name, gesture.confidence, gesture.landmarks, side)
            )
        return tuple(enriched)

    @staticmethod
    def _clamped_roi(
        roi: tuple[int, int, int, int] | None,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int] | None:
        if roi is None:
            return None
        x1, y1, x2, y2 = (int(value) for value in roi)
        x1 = max(0, min(width, x1))
        y1 = max(0, min(height, y1))
        x2 = max(0, min(width, x2))
        y2 = max(0, min(height, y2))
        if x2 - x1 < 96 or y2 - y1 < 96:
            return None
        return x1, y1, x2, y2

    def close(self) -> None:
        hands = self._hands
        self._hands = None
        self.available = False
        if hands is not None and hasattr(hands, "close"):
            hands.close()


def hand_edges() -> tuple[tuple[int, int], ...]:
    """Expose the stable MediaPipe hand topology for preview drawing."""
    return _HAND_CONNECTIONS
