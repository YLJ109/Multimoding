"""Tests for the explicit dance-session lifecycle."""

from __future__ import annotations

import pytest

from dance_mirror.session import (
    DanceSessionState,
    DanceSessionStateMachine,
    InvalidSessionTransition,
)


def test_happy_path_reaches_settled_state() -> None:
    lifecycle = DanceSessionStateMachine()
    for state in (
        DanceSessionState.PREFLIGHT,
        DanceSessionState.CAMERA_WARMUP,
        DanceSessionState.COUNTDOWN,
        DanceSessionState.PLAYING,
        DanceSessionState.FINALIZING,
        DanceSessionState.SETTLED,
    ):
        assert lifecycle.transition(state) is state
    assert lifecycle.terminal
    assert not lifecycle.active
    assert not lifecycle.paused


def test_pause_and_resume_keep_active_flags_consistent() -> None:
    lifecycle = DanceSessionStateMachine()
    lifecycle.transition(DanceSessionState.PREFLIGHT)
    lifecycle.transition(DanceSessionState.CAMERA_WARMUP)
    lifecycle.transition(DanceSessionState.COUNTDOWN)
    lifecycle.transition(DanceSessionState.PLAYING)
    lifecycle.transition(DanceSessionState.PAUSED)
    assert lifecycle.active
    assert lifecycle.paused
    lifecycle.transition(DanceSessionState.PLAYING)
    assert lifecycle.active
    assert not lifecycle.paused


def test_illegal_transition_is_rejected() -> None:
    lifecycle = DanceSessionStateMachine()
    with pytest.raises(InvalidSessionTransition):
        lifecycle.transition(DanceSessionState.PLAYING)
