"""Priority command queue with expiry and bounded capacity."""

from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass, field

from dance_mirror.command.intents import CommandResult, RobotCommand, SafetyClass


@dataclass(order=True, slots=True)
class _Entry:
    sort_key: tuple[int, float, int]
    sequence: int
    result: CommandResult = field(compare=False)
    expires_at_s: float = field(compare=False)


class CommandQueue:
    """A small heap queue that keeps safety commands ahead of appearance."""

    def __init__(self, *, max_size: int = 32, default_ttl_s: float = 4.0) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self.default_ttl_s = max(0.1, float(default_ttl_s))
        self._heap: list[_Entry] = []
        self._counter = itertools.count()
        self._discarded = 0

    @property
    def size(self) -> int:
        self._purge_expired()
        return len(self._heap)

    @property
    def discarded(self) -> int:
        return self._discarded

    def push(self, result: CommandResult, *, ttl_s: float | None = None) -> bool:
        if result.command is RobotCommand.UNKNOWN:
            self._discarded += 1
            return False
        self._purge_expired()
        ttl = self.default_ttl_s if ttl_s is None else max(0.05, float(ttl_s))
        if result.safety_class is SafetyClass.SAFE_FAST:
            ttl = max(ttl, 1.0)
        priority = int(result.priority)
        sort_key = (-priority, time.monotonic(), next(self._counter))
        entry = _Entry(
            sort_key=sort_key,
            sequence=sort_key[2],
            result=result,
            expires_at_s=time.monotonic() + ttl,
        )
        if len(self._heap) >= self.max_size:
            self._heap.sort()
            worst = self._heap.pop()
            if worst.result.priority > result.priority:
                self._heap.append(worst)
                self._discarded += 1
                return False
            self._discarded += 1
        heapq.heappush(self._heap, entry)
        return True

    def pop(self) -> CommandResult | None:
        self._purge_expired()
        while self._heap:
            entry = heapq.heappop(self._heap)
            if entry.expires_at_s >= time.monotonic():
                return entry.result
        return None

    def clear(self) -> None:
        self._heap.clear()

    def _purge_expired(self) -> None:
        now = time.monotonic()
        if not self._heap:
            return
        active = [entry for entry in self._heap if entry.expires_at_s >= now]
        self._discarded += len(self._heap) - len(active)
        if len(active) != len(self._heap):
            heapq.heapify(active)
            self._heap = active
