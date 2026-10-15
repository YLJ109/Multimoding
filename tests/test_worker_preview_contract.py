"""Regression tests for the worker -> preview contract.

``estimate()`` returns a ``PoseEstimate`` wrapper (``pose3d`` + ``pose2d``),
while ``build_camera_preview`` needs a plain ``PoseFrame``.  Passing the wrapper
straight through crashed the realtime imitation worker at runtime, so these
tests pin the corrected call path.
"""

from __future__ import annotations

import numpy as np
import pytest

from dance_mirror.domain.types import PoseEstimate, PoseFrame
from dance_mirror.multimodal.preview import build_camera_preview
from dance_mirror.workers.imitation import RobotImitationWorker


def _pose_frame() -> PoseFrame:
    points = np.zeros((17, 3), dtype=np.float64)
    points[:, 0] = np.linspace(-0.3, 0.3, 17)
    points[:, 1] = np.linspace(1.0, -1.0, 17)
    return PoseFrame(
        keypoints=points,
        scores=np.ones(17, dtype=np.float64),
        timestamp_s=0.0,
        frame_index=0,
    )


def _estimate() -> PoseEstimate:
    frame = _pose_frame()
    return PoseEstimate(pose3d=frame, pose2d=frame, is_metric=True)


def test_imitation_build_preview_accepts_a_pose_estimate() -> None:
    worker = RobotImitationWorker()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    packet = worker._build_preview(
        frame,
        _estimate(),
        bbox=(10.0, 20.0, 100.0, 200.0),
        person_count=1,
        frame_index=3,
        timestamp_s=0.1,
        readiness=0.7,
    )

    assert packet.keypoints_px.shape == (17, 3)
    assert packet.scores.shape == (17,)
    assert packet.person_count == 1
    assert packet.frame_index == 3


def test_imitation_build_preview_tolerates_a_missing_pose() -> None:
    worker = RobotImitationWorker()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    packet = worker._build_preview(
        frame,
        None,
        bbox=None,
        person_count=0,
        frame_index=0,
        timestamp_s=0.0,
        readiness=0.0,
    )

    assert packet.keypoints_px.shape == (17, 3)
    assert packet.scores.shape == (17,)


def test_preview_rejects_a_pose_estimate_with_an_actionable_error() -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    with pytest.raises(TypeError, match="pose.pose2d"):
        build_camera_preview(frame, _estimate())


def test_preview_accepts_a_plain_pose_frame() -> None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    packet = build_camera_preview(frame, _pose_frame())
    assert packet.keypoints_px.shape == (17, 3)
