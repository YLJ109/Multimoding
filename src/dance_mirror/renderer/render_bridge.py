"""Coalescing bridge between real-time producers and a browser renderer."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderBridgeStats:
    """Observable counters for diagnosing renderer backpressure."""

    submitted: int = 0
    coalesced: int = 0
    dropped: int = 0
    batches: int = 0
    dispatched: int = 0
    failures: int = 0


@dataclass(slots=True)
class _PendingCommand:
    channel: str
    script: str
    submitted_at_s: float
    sequence: int


class LatestFrameRenderBridge:
    """Keep only the latest command per channel and dispatch merged batches.

    The bridge is intentionally Qt-free so it can be tested without a display.
    A Qt owner can call :meth:`flush` from a timer and pass ``runJavaScript`` as
    the dispatch function.
    """

    def __init__(
        self,
        dispatch: Callable[[str], None],
        *,
        min_interval_s: float = 1.0 / 60.0,
        max_pending_age_s: float = 0.300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_interval_s < 0.0:
            raise ValueError("min_interval_s cannot be negative")
        if max_pending_age_s <= 0.0:
            raise ValueError("max_pending_age_s must be positive")
        self._dispatch = dispatch
        self._min_interval_s = float(min_interval_s)
        self._max_pending_age_s = float(max_pending_age_s)
        self._clock = clock
        self._pending: dict[str, _PendingCommand] = {}
        self._next_flush_at_s = 0.0
        self._sequence = 0
        self._stats = RenderBridgeStats()

    @property
    def stats(self) -> RenderBridgeStats:
        return self._stats

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def submit(self, channel: str, script: str, *, now_s: float | None = None) -> bool:
        """Store the latest script for a channel, replacing any older value."""
        channel = channel.strip()
        if not channel or not script:
            return False
        now = self._clock() if now_s is None else float(now_s)
        if channel in self._pending:
            self._stats = RenderBridgeStats(
                submitted=self._stats.submitted + 1,
                coalesced=self._stats.coalesced + 1,
                dropped=self._stats.dropped,
                batches=self._stats.batches,
                dispatched=self._stats.dispatched,
                failures=self._stats.failures,
            )
        else:
            self._stats = RenderBridgeStats(
                submitted=self._stats.submitted + 1,
                coalesced=self._stats.coalesced,
                dropped=self._stats.dropped,
                batches=self._stats.batches,
                dispatched=self._stats.dispatched,
                failures=self._stats.failures,
            )
        self._sequence += 1
        self._pending[channel] = _PendingCommand(
            channel=channel,
            script=script,
            submitted_at_s=now,
            sequence=self._sequence,
        )
        return True

    def flush(self, *, force: bool = False, now_s: float | None = None) -> int:
        """Dispatch one merged batch if the rate limit allows it.

        A failed browser call is counted and the batch is dropped. Renderer
        failures must never propagate into the camera or scoring loop.
        """
        now = self._clock() if now_s is None else float(now_s)
        if not self._pending:
            return 0
        if not force and now < self._next_flush_at_s:
            return 0

        expired = [
            channel
            for channel, command in self._pending.items()
            if now - command.submitted_at_s > self._max_pending_age_s
        ]
        for channel in expired:
            del self._pending[channel]
        if expired:
            self._stats = RenderBridgeStats(
                submitted=self._stats.submitted,
                coalesced=self._stats.coalesced,
                dropped=self._stats.dropped + len(expired),
                batches=self._stats.batches,
                dispatched=self._stats.dispatched,
                failures=self._stats.failures,
            )
        if not self._pending:
            return 0

        commands = sorted(self._pending.values(), key=lambda item: item.sequence)
        self._pending.clear()
        script = "\n".join(command.script for command in commands)
        try:
            self._dispatch(script)
        except Exception:
            self._stats = RenderBridgeStats(
                submitted=self._stats.submitted,
                coalesced=self._stats.coalesced,
                dropped=self._stats.dropped + len(commands),
                batches=self._stats.batches,
                dispatched=self._stats.dispatched,
                failures=self._stats.failures + 1,
            )
            self._next_flush_at_s = now + self._min_interval_s
            return 0

        self._stats = RenderBridgeStats(
            submitted=self._stats.submitted,
            coalesced=self._stats.coalesced,
            dropped=self._stats.dropped,
            batches=self._stats.batches + 1,
            dispatched=self._stats.dispatched + len(commands),
            failures=self._stats.failures,
        )
        self._next_flush_at_s = now + self._min_interval_s
        return len(commands)

    def clear(self) -> None:
        self._pending.clear()
