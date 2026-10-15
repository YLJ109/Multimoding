"""Music-master-clock synchronization for live pose feedback."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SyncPolicy:
    """Bounds and smoothing parameters for one live training session."""

    max_delay_s: float = 0.300
    user_offset_s: float = 0.0
    smoothing_alpha: float = 0.20
    max_plausible_latency_s: float = 1.0

    def __post_init__(self) -> None:
        if self.max_delay_s <= 0.0:
            raise ValueError("max_delay_s must be positive")
        if not 0.0 < self.smoothing_alpha <= 1.0:
            raise ValueError("smoothing_alpha must be in (0, 1]")
        if self.max_plausible_latency_s <= 0.0:
            raise ValueError("max_plausible_latency_s must be positive")


@dataclass(frozen=True, slots=True)
class SyncSnapshot:
    """One clamped and smoothed synchronization result."""

    pose_effective_time_s: float
    applied_delay_s: float
    raw_latency_s: float
    smoothed_latency_s: float
    confidence: float


class SyncController:
    """Map capture timestamps into the reference/music timeline.

    A music player is the master clock. When music time is available, a pose
    captured at ``capture_timestamp_s`` is mapped to the music position that
    was actually being played when the pose happened. Before music starts, the
    capture timestamp is used as a fallback timeline.
    """

    def __init__(
        self,
        policy: SyncPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or SyncPolicy()
        self._clock = clock
        self._music_time_s: float | None = None
        self._music_observed_at_s: float | None = None
        self._smoothed_latency_s: float | None = None
        self._last_snapshot: SyncSnapshot | None = None

    def set_music_time(self, music_time_s: float, *, now_s: float | None = None) -> None:
        if not np.isfinite(music_time_s):
            raise ValueError("music_time_s must be finite")
        self._music_time_s = max(0.0, float(music_time_s))
        self._music_observed_at_s = self._now(now_s)

    def clear_music_time(self) -> None:
        self._music_time_s = None
        self._music_observed_at_s = None

    def reset(self) -> None:
        self.clear_music_time()
        self._smoothed_latency_s = None
        self._last_snapshot = None

    def _now(self, now_s: float | None) -> float:
        return self._clock() if now_s is None else float(now_s)

    def _music_time_at(self, now_s: float) -> float | None:
        if self._music_time_s is None or self._music_observed_at_s is None:
            return None
        return self._music_time_s + max(0.0, now_s - self._music_observed_at_s)

    def _smooth_latency(self, raw_latency_s: float) -> tuple[float, bool]:
        if not np.isfinite(raw_latency_s) or raw_latency_s < 0.0:
            return self._smoothed_latency_s or 0.0, False
        if raw_latency_s > self.policy.max_plausible_latency_s:
            return self._smoothed_latency_s or 0.0, False
        if self._smoothed_latency_s is None:
            self._smoothed_latency_s = raw_latency_s
        else:
            alpha = self.policy.smoothing_alpha
            self._smoothed_latency_s = (
                alpha * raw_latency_s + (1.0 - alpha) * self._smoothed_latency_s
            )
        return self._smoothed_latency_s, True

    def effective_pose_time(
        self,
        capture_timestamp_s: float,
        *,
        now_s: float | None = None,
        capture_to_pose_latency_s: float = 0.0,
    ) -> SyncSnapshot:
        """Return the reference time that should be scored for a pose."""
        if not np.isfinite(capture_timestamp_s):
            raise ValueError("capture_timestamp_s must be finite")
        now = self._now(now_s)
        elapsed_s = max(0.0, now - float(capture_timestamp_s))
        raw_latency_s = max(0.0, float(capture_to_pose_latency_s))
        smoothed_latency_s, valid_latency = self._smooth_latency(raw_latency_s)
        if not valid_latency:
            elapsed_s = 0.0
        applied_delay_s = float(
            np.clip(
                elapsed_s + smoothed_latency_s + self.policy.user_offset_s,
                0.0,
                self.policy.max_delay_s,
            )
        )
        music_time = self._music_time_at(now)
        if music_time is None:
            effective_time = capture_timestamp_s - smoothed_latency_s - self.policy.user_offset_s
        else:
            effective_time = music_time - applied_delay_s
        snapshot = SyncSnapshot(
            pose_effective_time_s=max(0.0, float(effective_time)),
            applied_delay_s=applied_delay_s,
            raw_latency_s=raw_latency_s,
            smoothed_latency_s=smoothed_latency_s,
            confidence=1.0 if valid_latency else 0.25,
        )
        self._last_snapshot = snapshot
        return snapshot

    @property
    def last_snapshot(self) -> SyncSnapshot | None:
        return self._last_snapshot
