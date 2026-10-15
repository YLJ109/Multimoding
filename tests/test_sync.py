"""Tests for music-master-clock synchronization."""

from __future__ import annotations

import pytest

from dance_mirror.motion.sync import SyncController, SyncPolicy


def test_delay_is_clamped_and_music_time_is_applied() -> None:
    now = [100.0]
    controller = SyncController(
        SyncPolicy(max_delay_s=0.3, user_offset_s=0.1),
        clock=lambda: now[0],
    )
    controller.set_music_time(10.0, now_s=100.0)

    snapshot = controller.effective_pose_time(
        99.8,
        now_s=100.0,
        capture_to_pose_latency_s=0.05,
    )

    assert snapshot.applied_delay_s == pytest.approx(0.3)
    assert snapshot.pose_effective_time_s == pytest.approx(9.7)


def test_latency_is_smoothed() -> None:
    controller = SyncController(SyncPolicy(smoothing_alpha=0.2))
    first = controller.effective_pose_time(0.0, now_s=0.0, capture_to_pose_latency_s=0.4)
    second = controller.effective_pose_time(
        0.01,
        now_s=0.01,
        capture_to_pose_latency_s=0.1,
    )

    assert first.smoothed_latency_s == pytest.approx(0.4)
    assert second.smoothed_latency_s == pytest.approx(0.34)
    assert second.confidence == 1.0


def test_implausible_latency_spike_is_not_smoothed_into_state() -> None:
    controller = SyncController(SyncPolicy(max_plausible_latency_s=1.0))
    first = controller.effective_pose_time(0.0, now_s=0.0, capture_to_pose_latency_s=0.1)
    spike = controller.effective_pose_time(0.1, now_s=0.1, capture_to_pose_latency_s=1.2)

    assert first.smoothed_latency_s == pytest.approx(0.1)
    assert spike.smoothed_latency_s == pytest.approx(0.1)
    assert spike.raw_latency_s == pytest.approx(1.2)
    assert spike.confidence == 0.25
