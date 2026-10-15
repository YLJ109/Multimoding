"""View-aware feature alignment for comparing poses captured from different cameras."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from dance_mirror.domain.quality import MotionQualityProfile
from dance_mirror.domain.skeleton import JOINT_WEIGHTS
from dance_mirror.domain.types import FeatureVector
from dance_mirror.motion.features import FEATURE_NAMES


class CameraView(StrEnum):
    """Expected camera placement relative to the dancer."""

    FRONT = "front"
    BACK = "back"
    LEFT_PROFILE = "left_profile"
    RIGHT_PROFILE = "right_profile"
    THREE_QUARTER = "three_quarter"
    UNKNOWN = "unknown"


class SemanticAlignment(StrEnum):
    """Whether left/right joint labels are aligned between the two inputs."""

    ALIGNED = "aligned"
    MIRRORED = "mirrored"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CameraProfile:
    """Camera metadata used to decide which features are comparable."""

    view: CameraView = CameraView.UNKNOWN
    semantic_alignment: SemanticAlignment = SemanticAlignment.ALIGNED
    upright: bool = True
    perspective_confidence: float = 0.8

    def __post_init__(self) -> None:
        if not 0.0 <= self.perspective_confidence <= 1.0:
            raise ValueError("perspective_confidence must be in [0, 1]")

    def as_metadata(self) -> dict[str, object]:
        return {
            "view": self.view.value,
            "semantic_alignment": self.semantic_alignment.value,
            "upright": self.upright,
            "perspective_confidence": self.perspective_confidence,
        }

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, object]) -> CameraProfile:
        raw = metadata.get("camera_profile")
        source: Mapping[str, object] = raw if isinstance(raw, Mapping) else metadata
        try:
            view = CameraView(str(source.get("view", source.get("camera_view", "unknown"))))
        except (TypeError, ValueError):
            view = CameraView.UNKNOWN
        try:
            alignment = SemanticAlignment(
                str(source.get("semantic_alignment", source.get("alignment", "aligned")))
            )
        except (TypeError, ValueError):
            alignment = SemanticAlignment.UNKNOWN
        try:
            confidence = float(source.get("perspective_confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        return cls(
            view=view,
            semantic_alignment=alignment,
            upright=bool(source.get("upright", True)),
            perspective_confidence=confidence,
        )


_ANGLE_FEATURES = frozenset(
    {
        "left_elbow_angle",
        "right_elbow_angle",
        "left_knee_angle",
        "right_knee_angle",
    }
)
_HEIGHT_FEATURES = frozenset(
    {
        "left_wrist_height",
        "right_wrist_height",
        "left_foot_height",
        "right_foot_height",
    }
)
_LATERAL_FEATURES = frozenset(
    {
        "left_wrist_side",
        "right_wrist_side",
        "body_lean",
        "hip_shift",
    }
)
_MIRROR_MAP = {
    "left_wrist_height": "right_wrist_height",
    "right_wrist_height": "left_wrist_height",
    "left_wrist_side": "right_wrist_side",
    "right_wrist_side": "left_wrist_side",
    "left_elbow_angle": "right_elbow_angle",
    "right_elbow_angle": "left_elbow_angle",
    "left_knee_angle": "right_knee_angle",
    "right_knee_angle": "left_knee_angle",
    "left_foot_height": "right_foot_height",
    "right_foot_height": "left_foot_height",
}


@dataclass(frozen=True, slots=True)
class ComparisonFeatureSpace:
    """Per-feature weights and semantic mapping for one comparison pair."""

    weights: Mapping[str, float] = field(default_factory=dict)
    actual_feature_map: Mapping[str, str] = field(default_factory=dict)
    evidence_scale: float = 1.0
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.evidence_scale <= 1.0:
            raise ValueError("evidence_scale must be in [0, 1]")
        for name, weight in self.weights.items():
            if name not in FEATURE_NAMES:
                raise ValueError(f"unknown feature in feature space: {name}")
            if weight < 0.0:
                raise ValueError(f"feature weight cannot be negative: {name}")
        for source in self.actual_feature_map.values():
            if source not in FEATURE_NAMES:
                raise ValueError(f"unknown mapped feature: {source}")

    def weight(self, feature: str) -> float:
        return float(self.weights.get(feature, 1.0))

    @property
    def applicable_features(self) -> tuple[str, ...]:
        return tuple(name for name in FEATURE_NAMES if self.weight(name) > 0.0)

    def align_actual(self, actual: FeatureVector) -> FeatureVector:
        """Apply left/right remapping without mutating the caller's vector."""
        values: dict[str, float] = {}
        confidence: dict[str, float] = {}
        for target in FEATURE_NAMES:
            source = self.actual_feature_map.get(target, target)
            values[target] = float(actual.values.get(source, float("nan")))
            confidence[target] = float(actual.confidence.get(source, 0.0))
        return FeatureVector(values=values, confidence=confidence)


def _same_family(first: CameraView, second: CameraView) -> bool:
    front_group = {CameraView.FRONT, CameraView.THREE_QUARTER}
    back_group = {CameraView.BACK}
    side_group = {CameraView.LEFT_PROFILE, CameraView.RIGHT_PROFILE}
    if first == second:
        return True
    return any(first in group and second in group for group in (front_group, back_group, side_group))


def _lateral_factor(first: CameraView, second: CameraView) -> float:
    if first == CameraView.UNKNOWN or second == CameraView.UNKNOWN:
        return 0.45
    if first == second:
        return 1.0
    if first in {CameraView.FRONT, CameraView.BACK, CameraView.THREE_QUARTER} and second in {
        CameraView.FRONT,
        CameraView.BACK,
        CameraView.THREE_QUARTER,
    }:
        # A front and a back camera see mirrored screen-space x. Keep a small
        # amount of evidence only when the views are genuinely compatible.
        if {first, second} == {CameraView.BACK, CameraView.FRONT}:
            return 0.20
        return 0.55
    if first in {CameraView.LEFT_PROFILE, CameraView.RIGHT_PROFILE} and second in {
        CameraView.LEFT_PROFILE,
        CameraView.RIGHT_PROFILE,
    }:
        return 0.80 if first == second else 0.15
    return 0.10


def _alignment_map(alignment: SemanticAlignment) -> dict[str, str]:
    if alignment is SemanticAlignment.MIRRORED:
        return {name: _MIRROR_MAP.get(name, name) for name in FEATURE_NAMES}
    return {}


def build_comparison_space(
    reference: CameraProfile,
    user: CameraProfile,
    *,
    quality: MotionQualityProfile | None = None,
) -> ComparisonFeatureSpace:
    """Build conservative feature weights for a reference/user camera pair."""
    reasons: list[str] = []
    reference_known = reference.view is not CameraView.UNKNOWN
    user_known = user.view is not CameraView.UNKNOWN
    if not reference_known or not user_known:
        quality_scale = quality.score_confidence if quality is not None else 1.0
        evidence = 0.72 if not reference_known and not user_known else 0.85
        evidence *= quality_scale
        weights = {
            name: 0.85 if name in _ANGLE_FEATURES else 0.45 if name in _LATERAL_FEATURES else 0.80
            for name in FEATURE_NAMES
        }
        reasons.append("camera_view_unknown")
        return ComparisonFeatureSpace(
            weights=weights,
            actual_feature_map=_alignment_map(user.semantic_alignment),
            evidence_scale=evidence,
            reasons=tuple(reasons),
        )

    lateral = _lateral_factor(reference.view, user.view) * min(
        reference.perspective_confidence,
        user.perspective_confidence,
    )
    upright_factor = 1.0 if reference.upright and user.upright else 0.45
    weights = {}
    for name in FEATURE_NAMES:
        if name in _ANGLE_FEATURES:
            weights[name] = 1.0
        elif name in _HEIGHT_FEATURES:
            weights[name] = upright_factor
        elif name in _LATERAL_FEATURES:
            weights[name] = lateral
        else:
            weights[name] = 1.0

    if not _same_family(reference.view, user.view):
        reasons.append("different_camera_families")
    if lateral < 0.3:
        reasons.append("lateral_features_downweighted")
    if not (reference.upright and user.upright):
        reasons.append("camera_not_upright")

    evidence = 1.0
    if user.semantic_alignment is SemanticAlignment.UNKNOWN:
        evidence *= 0.90
        reasons.append("semantic_alignment_unknown")
    if quality is not None:
        evidence *= quality.score_confidence
        reasons.append(f"quality_{quality.level.value}")
    return ComparisonFeatureSpace(
        weights=weights,
        actual_feature_map=_alignment_map(user.semantic_alignment),
        evidence_scale=evidence,
        reasons=tuple(reasons),
    )


def base_feature_weights() -> dict[str, float]:
    """Return a copy of the canonical weights for callers that need to tune them."""
    return {name: float(JOINT_WEIGHTS.get(name, 1.0)) for name in FEATURE_NAMES}
