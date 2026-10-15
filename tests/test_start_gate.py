"""Behavioral contracts for the dance start readiness gate."""

from __future__ import annotations

from dance_mirror.view.start_gate import DanceStartGate


def test_start_requires_stable_placement_and_sustained_ok() -> None:
    gate = DanceStartGate()
    gate.arm(0.0)
    gate.observe_hands(True)

    assert not gate.observe_readiness(
        score=0.92,
        single_person=True,
        full_body=True,
        now_s=0.0,
    )
    assert not gate.observe_gesture("ok", 0.91, 0.0)
    assert not gate.observe_gesture("ok", 0.91, 0.6)
    assert gate.observe_gesture("ok", 0.91, 0.85)
    assert not gate.armed


def test_start_rejects_weak_placement_and_low_confidence_ok() -> None:
    gate = DanceStartGate()
    gate.arm(0.0)
    gate.observe_hands(True)

    assert not gate.observe_readiness(
        score=0.77,
        single_person=True,
        full_body=True,
        now_s=0.0,
    )
    assert not gate.observe_readiness(
        score=0.95,
        single_person=False,
        full_body=True,
        now_s=1.0,
    )
    assert not gate.observe_gesture("ok", 0.64, 1.0)
    assert not gate.observe_gesture("ok", 0.95, 2.0)
    assert gate.armed


def test_hand_loss_clears_previous_ok_hold() -> None:
    gate = DanceStartGate()
    gate.arm(0.0)
    gate.observe_hands(True)
    gate.observe_readiness(
        score=0.90,
        single_person=True,
        full_body=True,
        now_s=0.0,
    )
    gate.observe_gesture("ok", 0.90, 0.0)
    gate.observe_hands(False)
    gate.observe_hands(True)

    assert not gate.observe_gesture("ok", 0.90, 0.8)
    assert gate.observe_gesture("ok", 0.90, 1.71)
