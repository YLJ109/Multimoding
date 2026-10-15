"""Tests for the latest-frame render bridge."""

from __future__ import annotations

from dance_mirror.renderer.render_bridge import LatestFrameRenderBridge


def test_bridge_keeps_only_latest_command_per_channel() -> None:
    now = [0.0]
    batches: list[str] = []
    bridge = LatestFrameRenderBridge(
        batches.append,
        min_interval_s=0.1,
        max_pending_age_s=1.0,
        clock=lambda: now[0],
    )

    assert bridge.submit("user", "user-old", now_s=0.0)
    assert bridge.submit("reference", "reference", now_s=0.0)
    assert bridge.submit("user", "user-new", now_s=0.0)
    assert bridge.flush(force=True, now_s=0.0) == 2

    assert len(batches) == 1
    assert "user-old" not in batches[0]
    assert "user-new" in batches[0]
    assert "reference" in batches[0]
    assert bridge.stats.coalesced == 1


def test_bridge_rate_limits_and_drops_expired_commands() -> None:
    now = [0.0]
    batches: list[str] = []
    bridge = LatestFrameRenderBridge(
        batches.append,
        min_interval_s=0.1,
        max_pending_age_s=0.3,
        clock=lambda: now[0],
    )

    bridge.submit("user", "first", now_s=0.0)
    assert bridge.flush(now_s=0.0) == 1
    bridge.submit("user", "rate-limited", now_s=0.05)
    assert bridge.flush(now_s=0.05) == 0
    assert bridge.flush(now_s=0.1) == 1

    bridge.submit("user", "stale", now_s=0.1)
    now[0] = 0.5
    assert bridge.flush(force=True, now_s=0.5) == 0
    assert bridge.stats.dropped == 1
    assert "stale" not in batches


def test_dispatch_failure_is_counted_not_raised() -> None:
    def fail(_script: str) -> None:
        raise RuntimeError("renderer unavailable")

    bridge = LatestFrameRenderBridge(fail, min_interval_s=0.1)
    bridge.submit("user", "frame", now_s=0.0)
    assert bridge.flush(force=True, now_s=0.0) == 0
    assert bridge.stats.failures == 1
    assert bridge.stats.dropped == 1
