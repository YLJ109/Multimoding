"""Local, deterministic dance progression and reward rules."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from dance_mirror.services.analytics import normalize_records
from dance_mirror.storage.database import TrainingRecord


@dataclass(frozen=True, slots=True)
class Badge:
    """One explainable local achievement."""

    key: str
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    """One package in the local personal leaderboard."""

    package_id: str
    package_name: str
    best_score: float
    sessions: int


@dataclass(frozen=True, slots=True)
class ProgressionSnapshot:
    """Aggregated achievements for all records or one package."""

    sessions: int
    active_days: int
    total_duration_s: float
    average_score: float
    best_score: float
    latest_score: float
    max_combo: int
    stars: int
    title: str
    badges: tuple[Badge, ...]
    unlocked_skins: tuple[str, ...]
    leaderboard: tuple[LeaderboardEntry, ...]


BADGES: dict[str, Badge] = {
    "first_dance": Badge("first_dance", "初次登台", "完成第一次有效训练"),
    "steady_week": Badge("steady_week", "坚持舞者", "在 3 个不同日期完成训练"),
    "sharp_eye": Badge("sharp_eye", "精准控制", "单次训练达到 80 分"),
    "stage_master": Badge("stage_master", "舞台掌控", "单次训练达到 90 分"),
    "combo_10": Badge("combo_10", "连击核心", "单次训练最高连击达到 10"),
    "hand_master": Badge("hand_master", "手势专家", "手部平均得分达到 82"),
}


def stars_for_score(score: float) -> int:
    """Map a score to a three-star rating."""
    value = float(score)
    if value >= 90.0:
        return 3
    if value >= 75.0:
        return 2
    if value >= 60.0:
        return 1
    return 0


def build_progression(
    records: Iterable[TrainingRecord],
    *,
    package_id: str = "",
) -> ProgressionSnapshot:
    """Build local achievements without network access or hidden scoring."""
    normalized = normalize_records(records)
    if package_id:
        normalized = tuple(
            record
            for record in normalized
            if str((record.metadata or {}).get("package_id", "")) == package_id
        )

    dates: set[date] = set()
    scores: list[float] = []
    total_duration = 0.0
    max_combo = 0
    hand_scores: list[float] = []
    by_package: dict[str, list[TrainingRecord]] = defaultdict(list)
    for record in normalized:
        parsed = _parse_date(record.started_at)
        if parsed is not None:
            dates.add(parsed)
        score = float(record.overall_score)
        scores.append(score)
        total_duration += max(0.0, float(record.duration_s))
        metadata = record.metadata or {}
        max_combo = max(max_combo, _safe_int(metadata.get("max_combo", 0)))
        hand_score = record.body_part_scores.get("hands")
        if hand_score is None:
            hand_score = record.body_part_scores.get("upper_body")
        if hand_score is not None:
            hand_scores.append(float(hand_score))
        identifier = str(metadata.get("package_id", "")).strip()
        if identifier:
            by_package[identifier].append(record)

    best_score = max(scores, default=0.0)
    latest_score = scores[0] if scores else 0.0
    average_score = sum(scores) / len(scores) if scores else 0.0
    earned: list[Badge] = []
    if normalized:
        earned.append(BADGES["first_dance"])
    if len(dates) >= 3:
        earned.append(BADGES["steady_week"])
    if best_score >= 80.0:
        earned.append(BADGES["sharp_eye"])
    if best_score >= 90.0:
        earned.append(BADGES["stage_master"])
    if max_combo >= 10:
        earned.append(BADGES["combo_10"])
    if hand_scores and sum(hand_scores) / len(hand_scores) >= 82.0:
        earned.append(BADGES["hand_master"])

    unlocked = ["default", "cyber"]
    if len(normalized) >= 3 or best_score >= 70.0:
        unlocked.append("azure")
    if best_score >= 85.0:
        unlocked.append("gold")
    if best_score >= 92.0 and len(dates) >= 3:
        unlocked.append("crimson")

    leaderboard: list[LeaderboardEntry] = []
    for identifier, package_records in by_package.items():
        package_scores = [float(item.overall_score) for item in package_records]
        name = str((package_records[0].metadata or {}).get("package_name", "")).strip()
        leaderboard.append(
            LeaderboardEntry(
                package_id=identifier,
                package_name=name or identifier,
                best_score=max(package_scores),
                sessions=len(package_records),
            )
        )
    leaderboard.sort(key=lambda item: (-item.best_score, item.package_name.casefold()))

    return ProgressionSnapshot(
        sessions=len(normalized),
        active_days=len(dates),
        total_duration_s=total_duration,
        average_score=average_score,
        best_score=best_score,
        latest_score=latest_score,
        max_combo=max_combo,
        stars=stars_for_score(best_score),
        title=_title_for(best_score, len(normalized), len(dates)),
        badges=tuple(earned),
        unlocked_skins=tuple(unlocked),
        leaderboard=tuple(leaderboard[:5]),
    )


def _title_for(best_score: float, sessions: int, active_days: int) -> str:
    if best_score >= 95.0:
        return "舞台掌控者"
    if best_score >= 90.0:
        return "金牌舞者"
    if best_score >= 80.0:
        return "节奏核心"
    if best_score >= 65.0 or active_days >= 3:
        return "稳定舞者"
    if sessions >= 3:
        return "进阶舞者"
    return "训练新星"


def _parse_date(value: str) -> date | None:
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed.date()


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
