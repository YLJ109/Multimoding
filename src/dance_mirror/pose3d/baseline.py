"""A dependency-light 3D pose baseline.

This is not a claim of monocular 3D accuracy.  It creates a stable, skeletally
plausible depth component so the renderer, retargeting layer, and temporal
pipeline can be developed and tested before a learned lifter is plugged in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dance_mirror.domain.types import PoseFrame, PoseSequence

FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class BaselineLifterConfig:
    """Controls the conservative depth approximation."""

    depth_scale: float = 0.08
    smoothing: float = 0.75


class BaselinePoseLifter:
    """Attach a low-amplitude depth estimate to normalized 2D poses."""

    def __init__(self, config: BaselineLifterConfig | None = None) -> None:
        self.config = config or BaselineLifterConfig()
        self._last_depth: FloatArray | None = None

    def reset(self) -> None:
        self._last_depth = None

    def lift_frame(self, frame: PoseFrame) -> PoseFrame:
        """Lift one normalized frame while keeping state for a live stream."""
        points = np.asarray(frame.keypoints, dtype=np.float64).copy()
        raw_depth = self.config.depth_scale * np.tanh(points[:, 1])
        alpha = float(np.clip(self.config.smoothing, 0.0, 1.0))
        if self._last_depth is None:
            depth = raw_depth
        else:
            depth = alpha * raw_depth + (1.0 - alpha) * self._last_depth
        self._last_depth = depth.copy()
        points[:, 2] = depth
        return PoseFrame(
            keypoints=points,
            scores=np.asarray(frame.scores, dtype=np.float64).copy(),
            timestamp_s=frame.timestamp_s,
            frame_index=frame.frame_index,
            schema=frame.schema,
        )

    def lift(self, sequence: PoseSequence) -> PoseSequence:
        if len(sequence) == 0:
            return PoseSequence(
                keypoints=sequence.keypoints.copy(),
                scores=sequence.scores.copy(),
                timestamps_s=sequence.timestamps_s.copy(),
                fps=sequence.fps,
                schema=sequence.schema,
                metadata={**dict(sequence.metadata), "lifter": "baseline"},
            )
        points = np.asarray(sequence.keypoints, dtype=np.float64).copy()
        # The baseline treats image-plane y as a weak depth proxy for joints
        # whose depth is otherwise unobservable.  It is intentionally small so
        # it cannot dominate the real x/y motion.
        raw_depth = self.config.depth_scale * np.tanh(points[:, :, 1])
        depth = np.empty_like(raw_depth)
        depth[0] = raw_depth[0]
        alpha = float(np.clip(self.config.smoothing, 0.0, 1.0))
        for index in range(1, len(points)):
            depth[index] = alpha * raw_depth[index] + (1.0 - alpha) * depth[index - 1]
        points[:, :, 2] = depth
        return PoseSequence(
            keypoints=points,
            scores=sequence.scores.copy(),
            timestamps_s=sequence.timestamps_s.copy(),
            fps=sequence.fps,
            schema=sequence.schema,
            metadata={**dict(sequence.metadata), "lifter": "baseline", "is_3d": True},
        )
