"""Explicit lifecycle states for one dance-training session."""

from __future__ import annotations

from enum import StrEnum


class DanceSessionState(StrEnum):
    """All legal states for a dance-learning session."""

    IDLE = "idle"
    PREFLIGHT = "preflight"
    CAMERA_WARMUP = "camera_warmup"
    COUNTDOWN = "countdown"
    PLAYING = "playing"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    SETTLED = "settled"
    CLOSED = "closed"


_TRANSITIONS: dict[DanceSessionState, frozenset[DanceSessionState]] = {
    DanceSessionState.IDLE: frozenset(
        {
            DanceSessionState.PREFLIGHT,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.PREFLIGHT: frozenset(
        {
            DanceSessionState.CAMERA_WARMUP,
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.CAMERA_WARMUP: frozenset(
        {
            DanceSessionState.COUNTDOWN,
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.COUNTDOWN: frozenset(
        {
            DanceSessionState.PLAYING,
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.PLAYING: frozenset(
        {
            DanceSessionState.PAUSED,
            DanceSessionState.FINALIZING,
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.PAUSED: frozenset(
        {
            DanceSessionState.PLAYING,
            DanceSessionState.FINALIZING,
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.FINALIZING: frozenset(
        {
            DanceSessionState.SETTLED,
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.SETTLED: frozenset(
        {
            DanceSessionState.IDLE,
            DanceSessionState.CLOSED,
        }
    ),
    DanceSessionState.CLOSED: frozenset(),
}


class InvalidSessionTransition(RuntimeError):
    """Raised when a caller attempts an illegal session transition."""

    def __init__(
        self,
        current: DanceSessionState,
        requested: DanceSessionState,
    ) -> None:
        super().__init__(
            f"cannot transition dance session from {current.value} to {requested.value}"
        )
        self.current = current
        self.requested = requested


class DanceSessionStateMachine:
    """Track and validate one dance session without touching Qt."""

    def __init__(self) -> None:
        self._state = DanceSessionState.IDLE

    @property
    def state(self) -> DanceSessionState:
        return self._state

    @property
    def active(self) -> bool:
        return self._state in {
            DanceSessionState.PLAYING,
            DanceSessionState.PAUSED,
        }

    @property
    def paused(self) -> bool:
        return self._state is DanceSessionState.PAUSED

    @property
    def countdown(self) -> bool:
        return self._state is DanceSessionState.COUNTDOWN

    @property
    def terminal(self) -> bool:
        return self._state in {
            DanceSessionState.SETTLED,
            DanceSessionState.CLOSED,
        }

    def can_transition(self, requested: DanceSessionState) -> bool:
        return requested in _TRANSITIONS[self._state]

    def transition(self, requested: DanceSessionState) -> DanceSessionState:
        """Move to one legal state or reject the transition."""
        if requested is self._state:
            return self._state
        if not self.can_transition(requested):
            raise InvalidSessionTransition(self._state, requested)
        self._state = requested
        return self._state

    def reset(self) -> DanceSessionState:
        """Return to idle without creating a hidden cross-session transition."""
        if self._state is DanceSessionState.CLOSED:
            raise InvalidSessionTransition(self._state, DanceSessionState.IDLE)
        self._state = DanceSessionState.IDLE
        return self._state
