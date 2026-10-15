"""Contracts for progression, performance degradation, and HTML reports."""

from __future__ import annotations

from dance_mirror.services.performance import PerformanceGuard
from dance_mirror.services.progression import build_progression, stars_for_score
from dance_mirror.services.report import build_history_report_html
from dance_mirror.storage.database import TrainingRecord


def _record(
    session_id: str,
    started_at: str,
    score: float,
    *,
    combo: int = 0,
    package_id: str = "dance-a",
    package_name: str = "基础律动",
) -> TrainingRecord:
    return TrainingRecord(
        session_id=session_id,
        started_at=started_at,
        duration_s=45.0,
        overall_score=score,
        body_part_scores={"hands": score, "torso": score - 5.0},
        cue_counts={"left_wrist_height": 2},
        metadata={
            "package_id": package_id,
            "package_name": package_name,
            "max_combo": combo,
        },
    )


def test_progression_rewards_badges_stars_and_local_leaderboard() -> None:
    records = (
        _record("a", "2026-09-20T10:00:00+00:00", 92.0, combo=12),
        _record("b", "2026-09-21T10:00:00+00:00", 86.0, combo=8),
        _record(
            "c",
            "2026-09-22T10:00:00+00:00",
            88.0,
            combo=10,
            package_id="dance-b",
            package_name="宿舍律动",
        ),
    )

    snapshot = build_progression(records)

    assert stars_for_score(88.0) == 2
    assert stars_for_score(91.0) == 3
    assert snapshot.sessions == 3
    assert snapshot.active_days == 3
    assert snapshot.max_combo == 12
    assert snapshot.title == "金牌舞者"
    assert snapshot.leaderboard[0].package_name == "基础律动"
    assert {badge.key for badge in snapshot.badges} >= {
        "first_dance",
        "steady_week",
        "sharp_eye",
        "stage_master",
        "combo_10",
        "hand_master",
    }
    assert "gold" in snapshot.unlocked_skins
    assert "crimson" in snapshot.unlocked_skins


def test_performance_guard_degrades_after_sustained_low_fps() -> None:
    guard = PerformanceGuard(target_fps=45.0, samples_required=3, cooldown_samples=2)

    assert guard.observe(20.0) is None
    assert guard.observe(20.0) is None
    action = guard.observe(20.0)
    assert action is not None
    assert action.level == 1
    assert guard.observe(20.0) is None
    assert guard.observe(20.0) is None
    assert guard.observe(20.0) is None
    assert guard.observe(20.0) is None
    action = guard.observe(20.0)
    assert action is not None
    assert action.level == 2
    assert action.low_power is True


def test_html_report_is_self_contained_and_contains_progress() -> None:
    report = build_history_report_html(
        [_record("a", "2026-09-22T10:00:00+00:00", 91.0, combo=12)]
    )

    assert report.startswith("<!doctype html>")
    assert "DanceMirror 训练报告" in report
    assert "舞台掌控" in report
    assert "基础律动" in report
    assert "http://" not in report
    assert "https://" not in report
