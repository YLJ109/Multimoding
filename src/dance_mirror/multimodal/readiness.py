"""Explainable full-body readiness checks for dormitory camera setups."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dance_mirror.domain.types import PoseFrame

_EXPECTED = {
    "head": (0,),
    "shoulders": (5, 6),
    "wrists": (9, 10),
    "hips": (11, 12),
    "knees": (13, 14),
    "ankles": (15, 16),
}


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Readiness score and actionable reasons for the camera preview."""

    score: float
    coverage: float
    confidence: float
    centered: bool
    full_body: bool
    single_person: bool
    reasons: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        return self.score >= 0.78 and self.single_person

    @property
    def message(self) -> str:
        if not self.single_person:
            return "请只保留主要人物在画面中。"
        if self.full_body:
            if self.score >= 0.78:
                return "全身就位，可以做 OK 手势开始。"
            return "位置可用，请保持稳定。"
        return "请后退，让头顶和双脚都进入画面。"


def assess_readiness(
    frame: PoseFrame,
    *,
    image_size: tuple[int, int],
    person_count: int = 1,
    min_confidence: float = 0.35,
) -> ReadinessReport:
    """Assess one pixel-space COCO-17 pose without allocating UI objects."""
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image_size values must be positive")
    points = np.asarray(frame.keypoints, dtype=np.float64)
    scores = np.asarray(frame.scores, dtype=np.float64)
    if points.shape != (17, 3) or scores.shape != (17,):
        raise ValueError("readiness requires a COCO-17 pose")

    visible_groups = 0
    for indices in _EXPECTED.values():
        if any(scores[index] >= min_confidence for index in indices):
            visible_groups += 1
    coverage = visible_groups / len(_EXPECTED)
    visible_scores = scores[scores >= min_confidence]
    confidence = float(np.mean(visible_scores)) if visible_scores.size else 0.0

    ankle_visible = bool(np.max(scores[[15, 16]]) >= min_confidence)
    head_visible = bool(scores[0] >= min_confidence)
    full_body = ankle_visible and head_visible and coverage >= 0.75

    x_values = points[scores >= min_confidence, 0]
    y_values = points[scores >= min_confidence, 1]
    centered = False
    if x_values.size and y_values.size:
        centre_x = float(np.mean(x_values)) / width
        vertical_margin = min(
            float(np.min(y_values)) / height,
            1.0 - float(np.max(y_values)) / height,
        )
        centered = 0.16 <= centre_x <= 0.84 and vertical_margin >= 0.02

    reasons: list[str] = []
    if person_count > 1:
        reasons.append("multiple_people")
    if not head_visible:
        reasons.append("head_missing")
    if not ankle_visible:
        reasons.append("feet_missing")
    if coverage < 0.75:
        reasons.append("joints_missing")
    if confidence < 0.50:
        reasons.append("low_confidence")
    if not centered:
        reasons.append("centre_adjustment_needed")

    centre_score = 1.0 if centered else 0.45
    single_person = person_count <= 1
    score = (
        0.45 * coverage
        + 0.25 * confidence
        + 0.20 * (1.0 if full_body else 0.0)
        + 0.10 * centre_score
    )
    if not single_person:
        score *= 0.45
    return ReadinessReport(
        score=round(max(0.0, min(1.0, score)), 4),
        coverage=round(coverage, 4),
        confidence=round(confidence, 4),
        centered=centered,
        full_body=full_body,
        single_person=single_person,
        reasons=tuple(reasons),
    )
