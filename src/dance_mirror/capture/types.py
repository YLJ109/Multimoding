"""Capture data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class FramePacket:
    """A single BGR frame with its source timeline metadata."""

    image: NDArray[np.uint8]
    index: int
    timestamp_s: float
    source_fps: float

    def __post_init__(self) -> None:
        self.image = np.asarray(self.image, dtype=np.uint8)
        if self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError("image must be a BGR frame with shape (H, W, 3)")
        if self.index < 0:
            raise ValueError("index must be non-negative")
        if self.timestamp_s < 0:
            raise ValueError("timestamp_s must be non-negative")
        if self.source_fps <= 0:
            raise ValueError("source_fps must be positive")
