"""Ports implemented by infrastructure adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from dance_mirror.domain.types import PoseEstimate, PoseSequence


@runtime_checkable
class PoseEstimator(Protocol):
    """Extract a canonical COCO-17 pose from a BGR image frame."""

    def estimate(
        self,
        frame: np.ndarray,
        *,
        frame_index: int,
        timestamp_s: float,
    ) -> PoseEstimate | None: ...

    def close(self) -> None: ...


@runtime_checkable
class PoseLifter(Protocol):
    """Estimate a 3D pose sequence from canonical 2D observations."""

    def lift(self, sequence: PoseSequence) -> PoseSequence: ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """Speak coaching text without blocking the caller indefinitely."""

    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...
