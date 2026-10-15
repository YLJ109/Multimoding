"""Persistent-error detection and cue selection for spoken coaching."""

from __future__ import annotations

from dataclasses import dataclass, field

from dance_mirror.domain.skeleton import JOINT_WEIGHTS
from dance_mirror.domain.types import CoachCue, TrainingScore

PRIORITY: dict[str, int] = {
    "left_knee_angle": 5,
    "right_knee_angle": 5,
    "hip_shift": 5,
    "body_lean": 4,
    "left_wrist_height": 4,
    "right_wrist_height": 4,
    "left_wrist_side": 3,
    "right_wrist_side": 3,
    "left_elbow_angle": 3,
    "right_elbow_angle": 3,
    "left_foot_height": 3,
    "right_foot_height": 3,
}

CUE_TEXT: dict[str, tuple[str, str]] = {
    "left_wrist_height": ("左手抬高一点。", "左手放低一点。"),
    "right_wrist_height": ("右手抬高一点。", "右手放低一点。"),
    "left_wrist_side": ("左手再向外一点。", "左手向身体收回一点。"),
    "right_wrist_side": ("右手再向外一点。", "右手向身体收回一点。"),
    "left_elbow_angle": ("左肘伸直一点。", "左肘再弯曲一点。"),
    "right_elbow_angle": ("右肘伸直一点。", "右肘再弯曲一点。"),
    "left_knee_angle": ("左膝伸直一点。", "左膝再弯曲一点。"),
    "right_knee_angle": ("右膝伸直一点。", "右膝再弯曲一点。"),
    "left_foot_height": ("左脚抬高一点。", "左脚放低一点。"),
    "right_foot_height": ("右脚抬高一点。", "右脚放低一点。"),
    "body_lean": ("身体向右回正一点。", "身体向左回正一点。"),
    "hip_shift": ("重心向右移一点。", "重心向左移一点。"),
}


@dataclass(slots=True)
class CoachPolicyConfig:
    """Timing and threshold settings for non-intrusive live coaching."""

    min_confidence: float = 0.35
    trigger_error_ratio: float = 0.45
    min_persistence_s: float = 0.6
    cooldown_s: float = 3.0
    fallback_cooldown_s: float = 6.0
    min_priority: int = 1
    feature_weights: dict[str, float] = field(
        default_factory=lambda: dict(JOINT_WEIGHTS)
    )


@dataclass(slots=True)
class _ActiveError:
    first_seen_s: float
    last_seen_s: float
    last_value: float


class CoachPolicy:
    """Select at most one persistent, high-value error for a voice cue."""

    def __init__(self, config: CoachPolicyConfig | None = None) -> None:
        self.config = config or CoachPolicyConfig()
        self._active: dict[str, _ActiveError] = {}
        self._last_spoken: dict[str, float] = {}
        self._last_fallback_s = float("-inf")

    def reset(self) -> None:
        self._active.clear()
        self._last_spoken.clear()
        self._last_fallback_s = float("-inf")

    def evaluate(self, score: TrainingScore, timestamp_s: float) -> CoachCue | None:
        """Return a cue only after an error has remained visible and cooled down."""
        candidates: list[tuple[float, str, float, float]] = []
        for deviation in score.deviations:
            if deviation.confidence < self.config.min_confidence:
                continue
            if deviation.error_ratio < self.config.trigger_error_ratio:
                continue
            priority = PRIORITY.get(deviation.feature, self.config.min_priority)
            if priority < self.config.min_priority:
                continue
            weight = self.config.feature_weights.get(deviation.feature, 1.0)
            severity = deviation.error_ratio * max(weight, 0.1) * deviation.confidence
            candidates.append(
                (severity, deviation.feature, deviation.delta, deviation.confidence)
            )

        current_features = {item[1] for item in candidates}
        for feature in list(self._active):
            if feature not in current_features:
                del self._active[feature]

        for _, feature, delta, _ in candidates:
            active = self._active.get(feature)
            if active is None:
                self._active[feature] = _ActiveError(timestamp_s, timestamp_s, delta)
            else:
                active.last_seen_s = timestamp_s
                active.last_value = delta

        ready: list[tuple[float, str, float, float]] = []
        for severity, feature, _delta, confidence in candidates:
            active = self._active.get(feature)
            if active is None:
                continue
            persistence = active.last_seen_s - active.first_seen_s
            if persistence < self.config.min_persistence_s:
                continue
            last_spoken = self._last_spoken.get(feature, float("-inf"))
            if timestamp_s - last_spoken < self.config.cooldown_s:
                continue
            ready.append((severity, feature, active.last_value, confidence))

        if not candidates:
            if timestamp_s - self._last_fallback_s < self.config.fallback_cooldown_s:
                return None
            self._last_fallback_s = timestamp_s
            return CoachCue(
                feature="posture",
                text="请调整站位，让全身和主要关节保持在画面中。",
                priority=10,
                severity=1.0,
                timestamp_s=timestamp_s,
            )

        if ready:
            _, feature, delta, _ = max(
                ready,
                key=lambda item: (PRIORITY.get(item[1], 0), item[0]),
            )
            self._last_spoken[feature] = timestamp_s
            return CoachCue(
                feature=feature,
                text=build_cue_text(feature, delta),
                priority=PRIORITY.get(feature, 1),
                severity=abs(delta),
                timestamp_s=timestamp_s,
            )

        if candidates or timestamp_s - self._last_fallback_s < self.config.fallback_cooldown_s:
            return None
        self._last_fallback_s = timestamp_s
        return CoachCue(
            feature="posture",
            text="请调整站位，让全身和主要关节保持在画面中。",
            priority=10,
            severity=1.0,
            timestamp_s=timestamp_s,
        )


def build_cue_text(feature: str, delta: float) -> str:
    """Convert a signed feature delta into a concise Chinese instruction."""
    low_text, high_text = CUE_TEXT.get(feature, ("请调整动作。", "请调整动作。"))
    return high_text if delta > 0 else low_text
