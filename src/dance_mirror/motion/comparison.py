"""Confidence-aware comparison between normalized motion features."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from dance_mirror.domain.skeleton import JOINT_WEIGHTS
from dance_mirror.domain.types import FeatureVector, JointDeviation, TrainingScore
from dance_mirror.motion.comparison_space import ComparisonFeatureSpace
from dance_mirror.motion.features import FEATURE_NAMES

DEFAULT_TOLERANCES: dict[str, float] = {
    "left_wrist_height": 0.22,
    "right_wrist_height": 0.22,
    "left_wrist_side": 0.22,
    "right_wrist_side": 0.22,
    "left_elbow_angle": 0.30,
    "right_elbow_angle": 0.30,
    "left_knee_angle": 0.28,
    "right_knee_angle": 0.28,
    "left_foot_height": 0.12,
    "right_foot_height": 0.12,
    "body_lean": 0.16,
    "hip_shift": 0.18,
}

_QUALITY_REASON_LABELS = {
    "quality_relative_3d": "相对 3D",
    "quality_hybrid_3d": "混合 3D",
    "quality_verified_3d": "已校验 3D",
}


def _quality_label(space: ComparisonFeatureSpace) -> str | None:
    for reason in space.reasons:
        if reason in _QUALITY_REASON_LABELS:
            return _QUALITY_REASON_LABELS[reason]
    return None


@dataclass(slots=True)
class ComparisonConfig:
    """Thresholds and coverage requirements for one comparison."""

    min_confidence: float = 0.25
    min_feature_coverage: float = 0.25
    tolerances: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TOLERANCES)
    )
    weights: dict[str, float] = field(
        default_factory=lambda: dict(JOINT_WEIGHTS)
    )
    feature_space: ComparisonFeatureSpace = field(default_factory=ComparisonFeatureSpace)

    def tolerance(self, feature: str) -> float:
        value = self.tolerances.get(feature, 0.2)
        if value <= 0:
            raise ValueError(f"tolerance must be positive for {feature}")
        return value

    def weight(self, feature: str) -> float:
        return max(float(self.weights.get(feature, 1.0)), 0.0)

    def space_weight(self, feature: str) -> float:
        return self.feature_space.weight(feature)

    @property
    def applicable_feature_count(self) -> int:
        return len(self.feature_space.applicable_features)


def _finite(value: float) -> bool:
    return math.isfinite(value)


def compare_feature_vectors(
    reference: FeatureVector,
    actual: FeatureVector,
    *,
    config: ComparisonConfig | None = None,
) -> list[JointDeviation]:
    """Return deviations for every feature observed with enough confidence."""
    settings = config or ComparisonConfig()
    actual = settings.feature_space.align_actual(actual)
    deviations: list[JointDeviation] = []
    for feature in FEATURE_NAMES:
        if settings.space_weight(feature) <= 0.0:
            continue
        reference_value = float(reference.values.get(feature, math.nan))
        actual_value = float(actual.values.get(feature, math.nan))
        reference_confidence = float(reference.confidence.get(feature, 0.0))
        actual_confidence = float(actual.confidence.get(feature, 0.0))
        confidence = min(reference_confidence, actual_confidence)
        confidence *= settings.feature_space.evidence_scale
        if confidence < settings.min_confidence:
            continue
        if not (_finite(reference_value) and _finite(actual_value)):
            continue
        delta = actual_value - reference_value
        error_ratio = abs(delta) / settings.tolerance(feature)
        deviations.append(
            JointDeviation(
                feature=feature,
                reference=reference_value,
                actual=actual_value,
                delta=delta,
                error_ratio=error_ratio,
                confidence=confidence,
            )
        )
    return deviations


def score_deviations(
    deviations: list[JointDeviation],
    *,
    config: ComparisonConfig | None = None,
    feature_count: int | None = None,
) -> TrainingScore:
    """Aggregate deviations into a bounded score and per-feature details."""
    settings = config or ComparisonConfig()
    total_weight = 0.0
    total_score = 0.0
    by_feature: dict[str, float] = {}
    for item in deviations:
        weight = (
            settings.weight(item.feature)
            * settings.space_weight(item.feature)
            * item.confidence
        )
        total_weight += weight
        total_score += item.score * weight
        by_feature[item.feature] = item.score

    denominator = feature_count or settings.applicable_feature_count or len(FEATURE_NAMES)
    coverage = len(deviations) / max(denominator, 1)
    if total_weight <= 1e-9 or coverage < settings.min_feature_coverage:
        return TrainingScore(
            overall=0.0,
            by_feature=by_feature,
            deviations=deviations,
            quality_label=_quality_label(settings.feature_space),
        )

    overall = total_score / total_weight
    return TrainingScore(
        overall=round(float(overall), 2),
        by_feature=by_feature,
        deviations=deviations,
        quality_label=_quality_label(settings.feature_space),
    )


def compare_feature_frames(
    reference: FeatureVector,
    actual: FeatureVector,
    *,
    config: ComparisonConfig | None = None,
) -> TrainingScore:
    """Compare one synchronized pair of feature vectors."""
    settings = config or ComparisonConfig()
    deviations = compare_feature_vectors(reference, actual, config=settings)
    return score_deviations(
        deviations,
        config=settings,
        feature_count=settings.applicable_feature_count,
    )


def body_part_scores(score: TrainingScore) -> dict[str, float]:
    """Aggregate feature scores into the dimensions shown in the report."""
    groups = {
        "upper_body": (
            "left_wrist_height",
            "right_wrist_height",
            "left_wrist_side",
            "right_wrist_side",
            "left_elbow_angle",
            "right_elbow_angle",
        ),
        "lower_body": (
            "left_knee_angle",
            "right_knee_angle",
            "left_foot_height",
            "right_foot_height",
        ),
        "torso": ("body_lean", "hip_shift"),
    }
    result: dict[str, float] = {}
    for name, features in groups.items():
        values = [score.by_feature[item] for item in features if item in score.by_feature]
        result[name] = round(sum(values) / len(values), 2) if values else 0.0
    return result
