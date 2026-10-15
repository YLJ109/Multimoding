"""Closed-loop render performance guard for low-VRAM devices."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceAction:
    """One deterministic quality step applied by the UI."""

    level: int
    low_power: bool
    render_fps: int
    message: str


_LEVELS = (
    PerformanceAction(0, False, 60, "高质量"),
    PerformanceAction(1, False, 48, "平衡模式"),
    PerformanceAction(2, True, 40, "低功耗模式"),
    PerformanceAction(3, True, 30, "安全模式"),
)


class PerformanceGuard:
    """Degrade after sustained low FPS and avoid rapid oscillation."""

    def __init__(
        self,
        *,
        target_fps: float = 45.0,
        degrade_ratio: float = 0.68,
        samples_required: int = 4,
        cooldown_samples: int = 12,
    ) -> None:
        self.target_fps = max(1.0, float(target_fps))
        self.degrade_ratio = min(max(float(degrade_ratio), 0.1), 1.0)
        self.samples_required = max(1, int(samples_required))
        self.cooldown_samples = max(0, int(cooldown_samples))
        self._level = 0
        self._low_samples = 0
        self._cooldown = 0

    @property
    def level(self) -> int:
        return self._level

    @property
    def current(self) -> PerformanceAction:
        return _LEVELS[self._level]

    def reset(self, *, level: int = 0) -> None:
        self._level = max(0, min(len(_LEVELS) - 1, int(level)))
        self._low_samples = 0
        self._cooldown = 0

    def observe(self, measured_fps: float) -> PerformanceAction | None:
        """Return a new action only when a degradation threshold is crossed."""
        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if self._level >= len(_LEVELS) - 1:
            return None
        if float(measured_fps) < self.target_fps * self.degrade_ratio:
            self._low_samples += 1
        else:
            self._low_samples = 0
            return None
        if self._low_samples < self.samples_required:
            return None
        self._level += 1
        self._low_samples = 0
        self._cooldown = self.cooldown_samples
        return self.current
