"""Filesystem contracts for the versioned dance-package library."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from dance_mirror.domain.types import PoseSequence
from dance_mirror.storage.motion_library import DancePackageError, MotionPackageLibrary


def _sequence() -> PoseSequence:
    frames = 24
    points = np.zeros((frames, 17, 3), dtype=np.float64)
    points[:, :, 0] = np.linspace(-0.2, 0.2, 17)
    points[:, :, 1] = np.linspace(-1.0, 1.0, 17)
    scores = np.ones((frames, 17), dtype=np.float64)
    return PoseSequence(
        keypoints=points,
        scores=scores,
        timestamps_s=np.arange(frames, dtype=np.float64) / 12.0,
        fps=12.0,
    )


def _write_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        12.0,
        (160, 96),
    )
    assert writer.isOpened()
    for index in range(12):
        frame = np.zeros((96, 160, 3), dtype=np.uint8)
        frame[:, :, 0] = (index * 21) % 255
        frame[20:76, 30:130] = (40, 190, 240)
        writer.write(frame)
    writer.release()


def test_library_create_rename_delete_and_poster_extraction(tmp_path: Path) -> None:
    library = MotionPackageLibrary(tmp_path / "packages")
    video = tmp_path / "dance.avi"
    _write_video(video)
    package = library.create_from_sequence(
        _sequence(),
        name="宿舍测试舞",
        source_video=str(video),
    )

    assert package.ready
    assert package.poster_path is not None and package.poster_path.is_file()
    assert package.name == "宿舍测试舞"

    renamed = library.rename(package, "测试新名称")
    assert renamed.name == "测试新名称"
    assert library.load(package.package_id).name == "测试新名称"

    trash_path = library.delete(renamed)
    assert trash_path.is_dir()
    with pytest.raises(DancePackageError):
        library.load(package.package_id)
