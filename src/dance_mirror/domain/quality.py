"""Video-to-3D quality levels and motion-package assessment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

from dance_mirror.domain.types import PoseSequence


class MotionQualityLevel(StrEnum):
    """How much trust the scoring layer may place in a motion package."""

    RELATIVE_3D = "relative_3d"
    HYBRID_3D = "hybrid_3d"
    VERIFIED_3D = "verified_3d"

    @property
    def display_name(self) -> str:
        return {
            MotionQualityLevel.RELATIVE_3D: "相对 3D",
            MotionQualityLevel.HYBRID_3D: "混合 3D",
            MotionQualityLevel.VERIFIED_3D: "已校验 3D",
        }[self]


_LEVEL_DEFAULTS: dict[MotionQualityLevel, tuple[float, float]] = {
    MotionQualityLevel.RELATIVE_3D: (0.65, 0.80),
    MotionQualityLevel.HYBRID_3D: (0.85, 0.95),
    MotionQualityLevel.VERIFIED_3D: (1.00, 1.00),
}


@dataclass(frozen=True, slots=True)
class MotionQualityProfile:
    """Quality metadata attached to a reference motion package."""

    level: MotionQualityLevel
    score_confidence: float
    motion_scale: float
    valid_frame_ratio: float
    depth_activity: float
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("score_confidence", self.score_confidence),
            ("motion_scale", self.motion_scale),
            ("valid_frame_ratio", self.valid_frame_ratio),
            ("depth_activity", self.depth_activity),
        ):
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.score_confidence > 1.0 or self.motion_scale > 1.0:
            raise ValueError("quality scales cannot exceed 1.0")
        if self.valid_frame_ratio > 1.0:
            raise ValueError("valid_frame_ratio cannot exceed 1.0")

    @classmethod
    def for_level(
        cls,
        level: MotionQualityLevel,
        *,
        valid_frame_ratio: float = 0.0,
        depth_activity: float = 0.0,
        reasons: tuple[str, ...] = (),
    ) -> MotionQualityProfile:
        score_confidence, motion_scale = _LEVEL_DEFAULTS[level]
        return cls(
            level=level,
            score_confidence=score_confidence,
            motion_scale=motion_scale,
            valid_frame_ratio=valid_frame_ratio,
            depth_activity=depth_activity,
            reasons=reasons,
        )

    @classmethod
    def from_metadata(
        cls,
        metadata: Mapping[str, Any],
        *,
        valid_frame_ratio: float = 0.0,
        depth_activity: float = 0.0,
    ) -> MotionQualityProfile | None:
        """Read an explicit quality block without trusting free-form strings."""
        raw = metadata.get("quality")
        if not isinstance(raw, Mapping):
            return None
        raw_level = raw.get("level", metadata.get("quality_level"))
        try:
            level = MotionQualityLevel(str(raw_level))
        except (TypeError, ValueError):
            return None
        default_confidence, default_scale = _LEVEL_DEFAULTS[level]
        try:
            score_confidence = float(raw.get("score_confidence", default_confidence))
            motion_scale = float(raw.get("motion_scale", default_scale))
            valid = float(raw.get("valid_frame_ratio", valid_frame_ratio))
            depth = float(raw.get("depth_activity", depth_activity))
        except (TypeError, ValueError):
            return None
        raw_reasons = raw.get("reasons", ())
        reasons = tuple(str(item) for item in raw_reasons) if isinstance(raw_reasons, list) else ()
        return cls(
            level=level,
            score_confidence=score_confidence,
            motion_scale=motion_scale,
            valid_frame_ratio=valid,
            depth_activity=depth,
            reasons=reasons,
        )

    def as_metadata(self) -> dict[str, object]:
        return {
            "level": self.level.value,
            "score_confidence": self.score_confidence,
            "motion_scale": self.motion_scale,
            "valid_frame_ratio": self.valid_frame_ratio,
            "depth_activity": self.depth_activity,
            "reasons": list(self.reasons),
        }


def _valid_frame_ratio(sequence: PoseSequence) -> float:
    if len(sequence) == 0:
        return 0.0
    scores = np.asarray(sequence.scores, dtype=np.float64)
    points = np.asarray(sequence.keypoints, dtype=np.float64)
    finite = np.all(np.isfinite(points), axis=2)
    usable = (scores >= 0.25) & finite
    return float(np.mean(np.sum(usable, axis=1) >= 6))


def _depth_activity(sequence: PoseSequence) -> float:
    if len(sequence) == 0:
        return 0.0
    points = np.asarray(sequence.keypoints, dtype=np.float64)
    depth = points[:, :, 2]
    if not np.any(np.isfinite(depth)):
        return 0.0
    depth_span = float(np.nanstd(depth))
    hip = (points[:, 11, :2] + points[:, 12, :2]) / 2.0
    shoulder = (points[:, 5, :2] + points[:, 6, :2]) / 2.0
    torso = np.linalg.norm(shoulder - hip, axis=1)
    scale = float(np.nanmean(torso)) if np.any(np.isfinite(torso)) else 0.0
    if not np.isfinite(scale) or scale < 1e-6:
        return 0.0
    return float(depth_span / scale)


def _has_calibrated_source(metadata: Mapping[str, Any]) -> bool:
    return any(
        (
            bool(metadata.get("quality_verified", False)),
            bool(metadata.get("calibration_id", "")),
            bool(metadata.get("multi_view", False)),
            str(metadata.get("source_type", "")).lower() in {"mocap", "motion_capture"},
        )
    )


def _has_learned_lifter(metadata: Mapping[str, Any]) -> bool:
    lifter = str(metadata.get("lifter", "")).strip().lower()
    return bool(metadata.get("learned_lifter", False)) or lifter not in {"", "baseline", "none"}


def assess_motion_quality(sequence: PoseSequence) -> MotionQualityProfile:
    """Classify a sequence conservatively and return explainable metadata."""
    valid_ratio = _valid_frame_ratio(sequence)
    depth_activity = _depth_activity(sequence)
    explicit = MotionQualityProfile.from_metadata(
        sequence.metadata,
        valid_frame_ratio=valid_ratio,
        depth_activity=depth_activity,
    )
    if explicit is not None:
        return explicit

    reasons: list[str] = []
    if valid_ratio < 0.85:
        reasons.append("valid_frames_low")
    if depth_activity < 0.02:
        reasons.append("depth_activity_low")

    if (
        _has_calibrated_source(sequence.metadata)
        and valid_ratio >= 0.85
        and depth_activity >= 0.02
    ):
        reasons.append("calibrated_source")
        return MotionQualityProfile.for_level(
            MotionQualityLevel.VERIFIED_3D,
            valid_frame_ratio=valid_ratio,
            depth_activity=depth_activity,
            reasons=tuple(reasons),
        )

    if (
        _has_learned_lifter(sequence.metadata)
        and valid_ratio >= 0.75
        and depth_activity >= 0.02
    ):
        reasons.append("learned_lifter")
        return MotionQualityProfile.for_level(
            MotionQualityLevel.HYBRID_3D,
            valid_frame_ratio=valid_ratio,
            depth_activity=depth_activity,
            reasons=tuple(reasons),
        )

    reasons.append("baseline_relative_depth")
    return MotionQualityProfile.for_level(
        MotionQualityLevel.RELATIVE_3D,
        valid_frame_ratio=valid_ratio,
        depth_activity=depth_activity,
        reasons=tuple(reasons),
    )
