"""Motion, comparison, scoring, and coaching domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class PoseFrame:
    """A single pose observation in canonical COCO-17 layout."""

    keypoints: FloatArray
    scores: FloatArray
    timestamp_s: float
    frame_index: int
    schema: str = "coco17"

    def __post_init__(self) -> None:
        self.keypoints = np.asarray(self.keypoints, dtype=np.float64)
        self.scores = np.asarray(self.scores, dtype=np.float64)
        if self.keypoints.shape != (17, 3):
            raise ValueError(f"keypoints must have shape (17, 3), got {self.keypoints.shape}")
        if self.scores.shape != (17,):
            raise ValueError(f"scores must have shape (17,), got {self.scores.shape}")
        if self.schema != "coco17":
            raise ValueError(f"unsupported pose schema: {self.schema}")


@dataclass(slots=True)
class PoseEstimate:
    """One camera observation in both retarget-ready and preview-ready forms.

    Every pose backend (2D YOLO or real-3D BlazePose) returns this single
    contract so downstream workers stay backend-agnostic.
    """

    pose3d: PoseFrame
    pose2d: PoseFrame
    is_metric: bool = False
    person_count: int = 1
    primary_index: int = 0
    boxes: FloatArray | None = None


@dataclass(slots=True)
class PoseSequence:
    """A time-aligned pose sequence."""

    keypoints: FloatArray
    scores: FloatArray
    timestamps_s: FloatArray
    fps: float
    schema: str = "coco17"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.keypoints = np.asarray(self.keypoints, dtype=np.float64)
        self.scores = np.asarray(self.scores, dtype=np.float64)
        self.timestamps_s = np.asarray(self.timestamps_s, dtype=np.float64)
        if self.keypoints.ndim != 3 or self.keypoints.shape[1:] != (17, 3):
            raise ValueError(
                f"keypoints must have shape (T, 17, 3), got {self.keypoints.shape}"
            )
        if self.scores.shape != self.keypoints.shape[:2]:
            raise ValueError(
                f"scores must have shape {self.keypoints.shape[:2]}, got {self.scores.shape}"
            )
        if self.timestamps_s.shape != (len(self.keypoints),):
            raise ValueError("timestamps_s must contain one value per frame")
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        if self.schema != "coco17":
            raise ValueError(f"unsupported pose schema: {self.schema}")

    def __len__(self) -> int:
        return len(self.keypoints)

    @property
    def duration_s(self) -> float:
        if not len(self):
            return 0.0
        return float(self.timestamps_s[-1] - self.timestamps_s[0])


@dataclass(slots=True)
class FeatureVector:
    """Normalized motion features used for comparison."""

    values: dict[str, float]
    confidence: dict[str, float]


@dataclass(slots=True)
class JointDeviation:
    """A single feature deviation between reference and user motion."""

    feature: str
    reference: float
    actual: float
    delta: float
    error_ratio: float
    confidence: float

    @property
    def score(self) -> float:
        """Map an error ratio into a bounded 0-100 score."""
        bounded = min(max(self.error_ratio, 0.0), 3.0)
        return round(100.0 * np.exp(-0.5 * bounded**2), 2)


@dataclass(slots=True)
class TrainingScore:
    """Weighted score and per-feature details."""

    overall: float
    by_feature: dict[str, float]
    deviations: list[JointDeviation]
    quality_label: str | None = None
    dimensions: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class CoachCue:
    """A spoken coaching instruction."""

    feature: str
    text: str
    priority: int
    severity: float
    timestamp_s: float


@dataclass(slots=True)
class TrainingUpdate:
    """Result of processing one live user pose."""

    reference_time_s: float
    score: TrainingScore
    cue: CoachCue | None
