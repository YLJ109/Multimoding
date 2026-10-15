from __future__ import annotations

from dance_mirror.services.analytics import (
    filter_records,
    format_duration,
    normalize_records,
    package_options,
    record_change,
    summarize_history,
    top_cue,
    weakest_part,
)
from dance_mirror.storage.database import TrainingRecord


def record(
    session_id: str,
    started_at: str,
    score: float,
    *,
    duration: float = 30.0,
    parts: dict[str, float] | None = None,
    cues: dict[str, int] | None = None,
    package_id: str = "dance-a",
    package_name: str = "基础律动",
) -> TrainingRecord:
    return TrainingRecord(
        session_id=session_id,
        started_at=started_at,
        duration_s=duration,
        overall_score=score,
        body_part_scores=parts or {"upper_body": score, "lower_body": score - 5.0, "torso": score + 2.0},
        cue_counts=cues or {},
        metadata={"package_id": package_id, "package_name": package_name},
    )


def test_normalize_and_summarize_history() -> None:
    older = record(
        "old",
        "2026-09-20T10:00:00+00:00",
        72.0,
        duration=40.0,
        cues={"left_wrist_height": 4},
    )
    newer = record(
        "new",
        "2026-09-22T10:00:00+00:00",
        82.0,
        duration=50.0,
        cues={"right_knee_angle": 2},
    )

    ordered = normalize_records([older, newer])
    summary = summarize_history(ordered)

    assert [item.session_id for item in ordered] == ["new", "old"]
    assert summary.sessions == 2
    assert summary.average_score == 77.0
    assert summary.latest_score == 82.0
    assert summary.best_score == 82.0
    assert summary.recent_change == 10.0
    assert summary.total_duration_s == 90.0
    assert summary.active_days == 2
    assert summary.weakest_part == "下肢"
    assert summary.top_issue == "左手高度"
    assert record_change(ordered, newer) == 10.0
    assert record_change(ordered, older) is None


def test_filter_records_by_text_package_time_and_score() -> None:
    first = record("a", "2026-09-22T10:00:00+00:00", 92.0)
    second = record(
        "b",
        "2026-09-22T11:00:00+00:00",
        74.0,
        package_id="dance-b",
        package_name="宿舍律动",
        cues={"body_lean": 3},
    )

    assert [item.session_id for item in filter_records([first, second], query="宿舍")] == ["b"]
    assert [item.session_id for item in filter_records([first, second], package_id="dance-a")] == ["a"]
    assert [
        item.session_id
        for item in filter_records([first, second], minimum_score=80.0)
    ] == ["a"]
    assert [
        item.session_id
        for item in filter_records([first, second], maximum_score=80.0)
    ] == ["b"]


def test_display_helpers_and_package_options() -> None:
    item = record(
        "a",
        "2026-09-22T10:00:00+00:00",
        80.0,
        cues={"body_lean": 2, "left_knee_angle": 4},
    )
    assert weakest_part(item) == "下肢"
    assert top_cue(item) == "左膝角度"
    assert format_duration(3665.0) == "1 小时 1 分"
    assert package_options([item]) == (("dance-a", "基础律动"),)
