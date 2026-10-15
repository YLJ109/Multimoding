"""Deterministic analytics helpers for local training history."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from dance_mirror.storage.database import TrainingRecord

PART_LABELS = {
    "upper_body": "上肢",
    "lower_body": "下肢",
    "torso": "躯干",
    "head": "头部",
    "left_arm": "左臂",
    "right_arm": "右臂",
    "left_leg": "左腿",
    "right_leg": "右腿",
    "hands": "手部",
}

CUE_LABELS = {
    "left_wrist_height": "左手高度",
    "right_wrist_height": "右手高度",
    "left_wrist_side": "左手位置",
    "right_wrist_side": "右手位置",
    "left_elbow_angle": "左肘角度",
    "right_elbow_angle": "右肘角度",
    "left_knee_angle": "左膝角度",
    "right_knee_angle": "右膝角度",
    "left_foot_height": "左脚高度",
    "right_foot_height": "右脚高度",
    "body_lean": "身体倾斜",
    "hip_shift": "胯部偏移",
}


@dataclass(frozen=True, slots=True)
class HistorySummary:
    """Small immutable summary displayed by the history dashboard."""

    sessions: int
    total_duration_s: float
    average_score: float
    latest_score: float
    best_score: float
    recent_change: float
    active_days: int
    weakest_part: str
    top_issue: str


def normalize_records(records: Iterable[TrainingRecord]) -> tuple[TrainingRecord, ...]:
    """Return records newest first, including legacy unsorted input."""
    return tuple(sorted(records, key=lambda item: _parse_timestamp(item.started_at), reverse=True))


def filter_records(
    records: Iterable[TrainingRecord],
    *,
    query: str = "",
    package_id: str = "",
    days: int | None = None,
    minimum_score: float | None = None,
    maximum_score: float | None = None,
) -> tuple[TrainingRecord, ...]:
    """Apply the same local filters used by the history toolbar."""
    normalized = normalize_records(records)
    search = " ".join(str(query).split()).casefold()
    cutoff = datetime.now(UTC) - timedelta(days=days) if days and days > 0 else None
    result: list[TrainingRecord] = []
    for record in normalized:
        metadata = record.metadata or {}
        package_name = str(metadata.get("package_name", ""))
        identifier = str(metadata.get("package_id", ""))
        if package_id and identifier != package_id:
            continue
        if cutoff is not None and _parse_timestamp(record.started_at) < cutoff:
            continue
        if minimum_score is not None and record.overall_score < minimum_score:
            continue
        if maximum_score is not None and record.overall_score >= maximum_score:
            continue
        haystack = " ".join(
            (
                package_name,
                identifier,
                record.summary,
                " ".join(record.cue_counts),
                " ".join(record.body_part_scores),
            )
        ).casefold()
        if search and search not in haystack:
            continue
        result.append(record)
    return tuple(result)


def summarize_history(records: Iterable[TrainingRecord]) -> HistorySummary:
    """Calculate stable dashboard metrics from newest-first records."""
    items = normalize_records(records)
    if not items:
        return HistorySummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, "待评估", "暂无")

    scores = [float(item.overall_score) for item in items]
    latest = scores[0]
    recent_change = latest - scores[1] if len(scores) > 1 else 0.0
    part_totals: dict[str, list[float]] = {}
    cue_counts: Counter[str] = Counter()
    for record in items:
        for name, value in record.body_part_scores.items():
            part_totals.setdefault(name, []).append(float(value))
        cue_counts.update(record.cue_counts)
    weakest_key = min(
        part_totals,
        key=lambda name: sum(part_totals[name]) / len(part_totals[name]),
        default="",
    )
    active_days = len(
        {
            _parse_timestamp(item.started_at).astimezone(UTC).date()
            for item in items
        }
    )
    top_issue = CUE_LABELS.get(cue_counts.most_common(1)[0][0], "暂无") if cue_counts else "暂无"
    return HistorySummary(
        sessions=len(items),
        total_duration_s=sum(max(0.0, float(item.duration_s)) for item in items),
        average_score=sum(scores) / len(scores),
        latest_score=latest,
        best_score=max(scores),
        recent_change=recent_change,
        active_days=active_days,
        weakest_part=PART_LABELS.get(weakest_key, weakest_key or "待评估"),
        top_issue=top_issue,
    )


def record_change(
    records: Iterable[TrainingRecord],
    record: TrainingRecord,
) -> float | None:
    """Return the score difference from the previous older session."""
    items = normalize_records(records)
    for index, candidate in enumerate(items):
        if candidate.session_id != record.session_id:
            continue
        if index + 1 >= len(items):
            return None
        return float(candidate.overall_score) - float(items[index + 1].overall_score)
    return None


def package_options(records: Iterable[TrainingRecord]) -> tuple[tuple[str, str], ...]:
    """Return sorted ``(package_id, package_name)`` filter options."""
    options: dict[str, str] = {}
    for record in records:
        metadata = record.metadata or {}
        identifier = str(metadata.get("package_id", "")).strip()
        if identifier:
            options.setdefault(identifier, str(metadata.get("package_name", "")).strip() or identifier)
    return tuple(sorted(options.items(), key=lambda item: item[1].casefold()))


def weakest_part(record: TrainingRecord) -> str:
    """Return a human-readable weakest-part label for one record."""
    if not record.body_part_scores:
        return "待评估"
    name = min(record.body_part_scores, key=record.body_part_scores.get)
    return PART_LABELS.get(name, name)


def top_cue(record: TrainingRecord) -> str:
    """Return the most frequent cue label for one record."""
    if not record.cue_counts:
        return "无明显问题"
    name = max(record.cue_counts, key=record.cue_counts.get)
    return CUE_LABELS.get(name, name)


def format_duration(seconds: float) -> str:
    """Format a duration for compact dashboard cards."""
    total_seconds = max(0, round(float(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {secs} 秒"
    return f"{secs} 秒"


def record_package(record: TrainingRecord) -> tuple[str, str]:
    """Return ``(package_id, package_name)`` from a training record."""
    metadata: dict[str, Any] = record.metadata or {}
    identifier = str(metadata.get("package_id", "")).strip()
    name = str(metadata.get("package_name", "")).strip() or "未关联舞蹈包"
    return identifier, name


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
