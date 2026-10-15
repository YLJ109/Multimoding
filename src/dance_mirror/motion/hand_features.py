"""Hand feature extraction and explainable hand-performance scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from dance_mirror.domain.types import FeatureVector
from dance_mirror.multimodal.face import FaceObservation
from dance_mirror.multimodal.gesture import HandGesture

FloatArray = NDArray[np.float64]

HAND_FEATURE_NAMES: tuple[str, ...] = (
    "left_hand_openness",
    "right_hand_openness",
    "left_hand_pinch",
    "right_hand_pinch",
    "left_hand_spread",
    "right_hand_spread",
    "left_hand_rotation",
    "right_hand_rotation",
)

_HAND_SIDES = ("left", "right")
_HAND_TOLERANCES = {
    "openness": 0.24,
    "pinch": 0.26,
    "spread": 0.30,
    "rotation": 0.45,
}
_HAND_WEIGHTS = {
    "openness": 1.25,
    "pinch": 1.15,
    "spread": 0.90,
    "rotation": 0.85,
}


@dataclass(frozen=True, slots=True)
class HandPerformance:
    """One frame of hand scoring with its evidence level exposed."""

    overall: float
    posture: float
    movement: float
    mode: str
    detected_sides: tuple[str, ...]
    cue: str | None = None


@dataclass(slots=True)
class HandFeatureSequence:
    """Reference hand features aligned one-to-one with body pose frames."""

    values: FloatArray
    confidence: FloatArray
    names: tuple[str, ...] = HAND_FEATURE_NAMES

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values, dtype=np.float64)
        self.confidence = np.asarray(self.confidence, dtype=np.float64)
        if self.values.ndim != 2 or self.values.shape[1] != len(self.names):
            raise ValueError(f"hand values must have shape (T, {len(self.names)})")
        if self.confidence.shape != self.values.shape:
            raise ValueError("hand confidence must match hand values")

    def __len__(self) -> int:
        return len(self.values)

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

    @classmethod
    def from_metadata(
        cls,
        metadata: Mapping[str, Any],
        *,
        expected_length: int,
    ) -> HandFeatureSequence | None:
        names_raw = metadata.get("hand_feature_names")
        values_raw = metadata.get("hand_features")
        confidence_raw = metadata.get("hand_confidence")
        if not isinstance(names_raw, Sequence) or not isinstance(values_raw, Sequence):
            return None
        names = tuple(str(item) for item in names_raw)
        if names != HAND_FEATURE_NAMES:
            return None
        rows = list(values_raw)
        if len(rows) != expected_length:
            return None
        values = np.full((expected_length, len(names)), np.nan, dtype=np.float64)
        confidence = np.zeros_like(values)
        confidence_rows = list(confidence_raw) if isinstance(confidence_raw, Sequence) else []
        for row_index, row in enumerate(rows):
            if not isinstance(row, Sequence) or len(row) != len(names):
                continue
            for column, value in enumerate(row):
                if value is None:
                    continue
                try:
                    values[row_index, column] = float(value)
                except (TypeError, ValueError):
                    continue
                if row_index < len(confidence_rows):
                    confidence_row = confidence_rows[row_index]
                    if isinstance(confidence_row, Sequence) and column < len(confidence_row):
                        with suppress(TypeError, ValueError):
                            confidence[row_index, column] = max(
                                0.0, min(1.0, float(confidence_row[column]))
                            )
                elif np.isfinite(values[row_index, column]):
                    confidence[row_index, column] = 1.0
        return cls(values=values, confidence=confidence, names=names)


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _distance(first: np.ndarray, second: np.ndarray) -> float:
    common = min(first.shape[0], second.shape[0], 3)
    return float(np.linalg.norm(first[:common] - second[:common]))


def _rotation(points: np.ndarray) -> float:
    wrist = points[0]
    middle = points[9]
    return math.atan2(float(middle[1] - wrist[1]), float(middle[0] - wrist[0])) / math.pi


def hand_geometry(points: np.ndarray) -> dict[str, float]:
    """Return scale-independent geometric descriptors for one hand."""
    landmarks = np.asarray(points, dtype=np.float64)
    if landmarks.shape != (21, 3):
        raise ValueError("hand landmarks must have shape (21, 3)")
    palm_scale = max(1e-6, _distance(landmarks[0], landmarks[9]))
    extensions = []
    for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
        del mcp
        pip_distance = max(1e-6, _distance(landmarks[pip], landmarks[0]))
        tip_distance = _distance(landmarks[tip], landmarks[0])
        extensions.append(_bounded((tip_distance / pip_distance - 0.96) / 0.52))
    tip_indices = (4, 8, 12, 16, 20)
    gaps = [
        _distance(landmarks[first], landmarks[second]) / palm_scale
        for index, first in enumerate(tip_indices)
        for second in tip_indices[index + 1 :]
    ]
    spread = _bounded((float(np.mean(gaps)) - 0.42) / 1.05)
    pinch_gap = _distance(landmarks[4], landmarks[8]) / palm_scale
    return {
        "openness": float(np.mean(extensions)),
        "pinch": 1.0 - _bounded((pinch_gap - 0.18) / 0.88),
        "spread": spread,
        "rotation": _rotation(landmarks),
        "pinch_gap": pinch_gap,
    }


def _wrist_point(hand: HandGesture, image_size: tuple[int, int] | None) -> np.ndarray:
    """Return the hand wrist in the same coordinate space as the pose anchors."""
    point = np.asarray(hand.landmarks[0], dtype=np.float64).copy()
    if image_size is not None and len(image_size) == 2:
        width, height = image_size
        if width > 0 and height > 0:
            point[0] *= float(width)
            point[1] *= float(height)
    return point


def _valid_anchor(anchor: np.ndarray | None) -> bool:
    if anchor is None:
        return False
    point = np.asarray(anchor, dtype=np.float64)
    return point.size >= 2 and np.all(np.isfinite(point[:2]))


def _fallback_hand_side(hand: HandGesture, *, mirror: bool) -> str:
    side = hand.handedness
    if side not in _HAND_SIDES:
        side = "left" if float(hand.landmarks[9, 0]) < 0.5 else "right"
    if mirror:
        side = "right" if side == "left" else "left"
    return side


def match_hands_to_wrists(
    hands: Sequence[HandGesture],
    *,
    left_wrist: np.ndarray | None = None,
    right_wrist: np.ndarray | None = None,
    image_size: tuple[int, int] | None = None,
    mirror: bool = False,
) -> tuple[tuple[str, HandGesture], ...]:
    """Bind each detected hand to the nearest COCO wrist anchor.

    This avoids the MediaPipe handedness label (which can flip for mirrored
    front-camera input) and makes the robot hands follow the body skeleton.
    """
    anchors: list[tuple[str, np.ndarray]] = []
    if _valid_anchor(left_wrist):
        anchors.append(("left", np.asarray(left_wrist, dtype=np.float64)[:2]))
    if _valid_anchor(right_wrist):
        anchors.append(("right", np.asarray(right_wrist, dtype=np.float64)[:2]))
    if not anchors:
        return tuple((_fallback_hand_side(hand, mirror=mirror), hand) for hand in hands)

    ordered = sorted(hands, key=lambda item: item.confidence, reverse=True)
    used: set[str] = set()
    output: list[tuple[str, HandGesture]] = []
    for hand in ordered:
        wrist = _wrist_point(hand, image_size)
        available = [(side, point) for side, point in anchors if side not in used]
        if available:
            side = min(available, key=lambda item: _distance(wrist, item[1]))[0]
        else:
            fallback = _fallback_hand_side(hand, mirror=False)
            side = fallback if fallback in {name for name, _point in anchors} else min(
                anchors, key=lambda item: _distance(wrist, item[1])
            )[0]
        used.add(side)
        if mirror:
            side = "right" if side == "left" else "left"
        output.append((side, hand))
    return tuple(output)


def hands_by_side(
    hands: Sequence[HandGesture],
    *,
    left_wrist: np.ndarray | None = None,
    right_wrist: np.ndarray | None = None,
    image_size: tuple[int, int] | None = None,
    mirror: bool = False,
) -> dict[str, np.ndarray]:
    """Return one landmark array per canonical hand side."""
    selected: dict[str, np.ndarray] = {}
    for side, hand in match_hands_to_wrists(
        hands,
        left_wrist=left_wrist,
        right_wrist=right_wrist,
        image_size=image_size,
        mirror=mirror,
    ):
        if side in {"left", "right"}:
            selected[side] = np.asarray(hand.landmarks, dtype=np.float64)
    return selected
def extract_hand_features(
    gestures: Sequence[HandGesture],
    *,
    mirror: bool = False,
    left_wrist: np.ndarray | None = None,
    right_wrist: np.ndarray | None = None,
    image_size: tuple[int, int] | None = None,
) -> FeatureVector:
    """Map hands into the stable eight-column scoring contract."""
    values = {name: math.nan for name in HAND_FEATURE_NAMES}
    confidence = {name: 0.0 for name in HAND_FEATURE_NAMES}
    for side, gesture in match_hands_to_wrists(
        gestures,
        left_wrist=left_wrist,
        right_wrist=right_wrist,
        image_size=image_size,
        mirror=mirror,
    ):
        if side not in _HAND_SIDES:
            continue
        geometry = hand_geometry(gesture.landmarks)
        for metric in ("openness", "pinch", "spread", "rotation"):
            name = f"{side}_hand_{metric}"
            values[name] = geometry[metric]
            confidence[name] = max(gesture.confidence, 0.35)
    return FeatureVector(values=values, confidence=confidence)


def hand_feature_rows(
    feature: FeatureVector,
) -> tuple[list[float | None], list[float]]:
    """Serialize one feature vector for compact storage in pose metadata."""
    values = [
        float(feature.values[name]) if math.isfinite(feature.values[name]) else None
        for name in HAND_FEATURE_NAMES
    ]
    confidence = [float(feature.confidence[name]) for name in HAND_FEATURE_NAMES]
    return values, confidence


def _circular_delta(first: float, second: float) -> float:
    return (second - first + 1.0) % 2.0 - 1.0


def _side_feature(metric: str, side: str) -> str:
    return f"{side}_hand_{metric}"


def _strict_hand_score(
    reference: FeatureVector,
    actual: FeatureVector,
) -> tuple[float, float, str | None, tuple[str, ...]]:
    weighted = 0.0
    total_weight = 0.0
    side_scores: dict[str, list[float]] = {"left": [], "right": []}
    detected: list[str] = []
    for side in _HAND_SIDES:
        expected_names = [_side_feature(metric, side) for metric in _HAND_TOLERANCES]
        expected = any(reference.confidence.get(name, 0.0) >= 0.25 for name in expected_names)
        visible = any(actual.confidence.get(name, 0.0) >= 0.25 for name in expected_names)
        if visible:
            detected.append(side)
        if expected and not visible:
            side_scores[side].extend(0.0 for _name in expected_names)
            total_weight += sum(_HAND_WEIGHTS.values())
            continue
        for metric, tolerance in _HAND_TOLERANCES.items():
            name = _side_feature(metric, side)
            reference_value = float(reference.values.get(name, math.nan))
            actual_value = float(actual.values.get(name, math.nan))
            confidence = min(
                float(reference.confidence.get(name, 0.0)),
                float(actual.confidence.get(name, 0.0)),
            )
            if confidence < 0.25 or not (
                math.isfinite(reference_value) and math.isfinite(actual_value)
            ):
                continue
            delta = (
                _circular_delta(reference_value, actual_value)
                if metric == "rotation"
                else actual_value - reference_value
            )
            item_score = 100.0 * math.exp(-0.5 * min(abs(delta) / tolerance, 3.0) ** 2)
            weight = _HAND_WEIGHTS[metric] * confidence
            weighted += item_score * weight
            total_weight += weight
            side_scores[side].append(item_score)
    score = weighted / total_weight if total_weight > 1e-9 else 0.0
    cue = _hand_cue(side_scores, strict=True)
    return round(score, 2), score, cue, tuple(detected)


def _dynamic_hand_score(
    previous: FeatureVector | None,
    actual: FeatureVector,
) -> tuple[float, float, str | None, tuple[str, ...]]:
    visible_sides = []
    for side in _HAND_SIDES:
        names = [_side_feature(metric, side) for metric in _HAND_TOLERANCES]
        if any(actual.confidence.get(name, 0.0) >= 0.25 for name in names):
            visible_sides.append(side)
    presence = 0.0 if not visible_sides else (100.0 if len(visible_sides) == 2 else 78.0)
    movement = 0.0
    if previous is not None and visible_sides:
        deltas: list[float] = []
        for side in visible_sides:
            for metric in ("openness", "pinch", "spread"):
                name = _side_feature(metric, side)
                first = float(previous.values.get(name, math.nan))
                second = float(actual.values.get(name, math.nan))
                if math.isfinite(first) and math.isfinite(second):
                    deltas.append(abs(second - first))
        if deltas:
            movement = 100.0 * _bounded(float(np.mean(deltas)) / 0.11)
    score = 0.74 * presence + 0.26 * movement if visible_sides else 0.0
    cue = None if visible_sides else "双手再多进入画面一些，手部表现分会更准确。"
    return round(score, 2), movement, cue, tuple(visible_sides)


def _hand_cue(
    side_scores: Mapping[str, list[float]],
    *,
    strict: bool,
) -> str | None:
    available = {
        side: sum(values) / len(values)
        for side, values in side_scores.items()
        if values
    }
    if not available:
        return None
    side = min(available, key=available.get)
    if not strict or available[side] >= 58.0:
        return None
    side_name = "左手" if side == "left" else "右手"
    return f"{side_name}的手掌方向再跟紧一点，手指动作保持清楚。"


class HandPerformanceTracker:
    """Stateful hand scorer that never invents reference-video certainty."""

    def __init__(self, reference: HandFeatureSequence | None = None) -> None:
        self.reference = reference
        self._previous: FeatureVector | None = None

    def score(
        self,
        actual: FeatureVector,
        *,
        frame_index: int,
        mirror: bool = False,
    ) -> HandPerformance:
        reference_feature: FeatureVector | None = None
        if self.reference is not None and len(self.reference):
            index = max(0, min(int(frame_index), len(self.reference) - 1))
            reference_feature = self.reference.frame(index)
        if mirror and reference_feature is not None:
            reference_feature = _mirror_hand_vector(reference_feature)
        if reference_feature is not None and any(
            value >= 0.25 for value in reference_feature.confidence.values()
        ):
            overall, posture, cue, detected = _strict_hand_score(reference_feature, actual)
            mode = "reference"
            movement = 0.0
        else:
            overall, movement, cue, detected = _dynamic_hand_score(self._previous, actual)
            posture = overall
            mode = "performance"
        self._previous = actual
        return HandPerformance(
            overall=overall,
            posture=round(posture, 2),
            movement=round(movement, 2),
            mode=mode,
            detected_sides=detected,
            cue=cue,
        )


def _mirror_hand_vector(vector: FeatureVector) -> FeatureVector:
    values: dict[str, float] = {}
    confidence: dict[str, float] = {}
    for side in _HAND_SIDES:
        other = "right" if side == "left" else "left"
        for metric in _HAND_TOLERANCES:
            source = _side_feature(metric, other)
            target = _side_feature(metric, side)
            values[target] = float(vector.values.get(source, math.nan))
            confidence[target] = float(vector.confidence.get(source, 0.0))
    return FeatureVector(values=values, confidence=confidence)


def face_performance_score(face: FaceObservation | None) -> float:
    """Return a conservative visibility-focused face performance indicator."""
    if face is None:
        return 0.0
    expression_bonus = 8.0 if face.expression not in {"neutral", "blink"} else 2.0
    return round(min(100.0, face.confidence * 92.0 + expression_bonus), 2)
