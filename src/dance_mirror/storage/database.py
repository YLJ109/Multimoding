"""SQLite persistence for training sessions and report summaries."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TrainingRecord:
    """Serializable result of one training session."""

    session_id: str
    started_at: str
    duration_s: float
    overall_score: float
    body_part_scores: dict[str, float]
    cue_counts: dict[str, int]
    summary: str = ""
    metadata: dict[str, Any] | None = None


class TrainingStore:
    """A small, explicit SQLite repository.

    Database operations are local and synchronous.  Callers should use them
    from a worker thread when the database is on a slow disk.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None

    def open(self) -> None:
        if self._connection is not None:
            return
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS training_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                duration_s REAL NOT NULL,
                overall_score REAL NOT NULL,
                body_part_scores TEXT NOT NULL,
                cue_counts TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._connection.commit()

    def save(self, record: TrainingRecord) -> None:
        self.open()
        assert self._connection is not None
        self._connection.execute(
            """
            INSERT OR REPLACE INTO training_sessions (
                session_id, started_at, duration_s, overall_score,
                body_part_scores, cue_counts, summary, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.session_id,
                record.started_at,
                record.duration_s,
                record.overall_score,
                json.dumps(record.body_part_scores, ensure_ascii=False),
                json.dumps(record.cue_counts, ensure_ascii=False),
                record.summary,
                json.dumps(record.metadata or {}, ensure_ascii=False),
            ),
        )
        self._connection.commit()

    def list_recent(self, limit: int = 20) -> list[TrainingRecord]:
        if limit <= 0:
            return []
        self.open()
        assert self._connection is not None
        rows = self._connection.execute(
            """
            SELECT * FROM training_sessions
            ORDER BY started_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> TrainingRecord:
        return TrainingRecord(
            session_id=str(row["session_id"]),
            started_at=str(row["started_at"]),
            duration_s=float(row["duration_s"]),
            overall_score=float(row["overall_score"]),
            body_part_scores=dict(json.loads(row["body_part_scores"])),
            cue_counts=dict(json.loads(row["cue_counts"])),
            summary=str(row["summary"]),
            metadata=dict(json.loads(row["metadata"])),
        )

    def __enter__(self) -> TrainingStore:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def utc_timestamp() -> str:
    """Return a stable ISO timestamp for session records."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def aggregate_cue_counts(cues: Iterable[str]) -> dict[str, int]:
    """Count cue features without storing natural-language text."""
    counts: dict[str, int] = {}
    for feature in cues:
        counts[feature] = counts.get(feature, 0) + 1
    return counts
