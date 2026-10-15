"""Tests for versioned motion packages and SQLite session persistence."""

from __future__ import annotations

import numpy as np

from dance_mirror.domain.types import PoseSequence
from dance_mirror.storage.database import TrainingRecord, TrainingStore
from dance_mirror.storage.motion_package import load_motion_package, save_motion_package


def _sequence() -> PoseSequence:
    points = np.zeros((3, 17, 3), dtype=np.float64)
    points[:, :, 0] = 0.1
    points[:, :, 1] = 0.2
    return PoseSequence(
        keypoints=points,
        scores=np.ones((3, 17), dtype=np.float64),
        timestamps_s=np.asarray([0.0, 1 / 30, 2 / 30], dtype=np.float64),
        fps=30.0,
        metadata={"source": "unit-test"},
    )


def test_motion_package_round_trip(tmp_path) -> None:
    path = tmp_path / "motion.json"
    save_motion_package(_sequence(), path)
    restored = load_motion_package(path)
    assert restored.fps == 30.0
    assert restored.keypoints.shape == (3, 17, 3)
    assert restored.metadata["source"] == "unit-test"


def test_training_store_round_trip(tmp_path) -> None:
    path = tmp_path / "training.db"
    record = TrainingRecord(
        session_id="session-1",
        started_at="2026-09-21T00:00:00+00:00",
        duration_s=42.0,
        overall_score=88.5,
        body_part_scores={"upper_body": 90.0},
        cue_counts={"left_wrist_height": 2},
        summary="test",
    )
    with TrainingStore(path) as store:
        store.save(record)
        records = store.list_recent()
    assert len(records) == 1
    assert records[0].session_id == "session-1"
    assert records[0].cue_counts["left_wrist_height"] == 2
