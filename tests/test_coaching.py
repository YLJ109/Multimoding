"""Tests for privacy masking, depth lifting, and cloud service contracts."""

from __future__ import annotations

import numpy as np

from dance_mirror.coaching.providers import default_provider_for_session
from dance_mirror.coaching.tts import CloudTTSConfig
from dance_mirror.domain.types import PoseFrame
from dance_mirror.pose3d.baseline import BaselinePoseLifter
from dance_mirror.privacy import blur_other_people


def _normalized_pose() -> PoseFrame:
    points = np.zeros((17, 3), dtype=np.float64)
    points[:, 1] = np.linspace(-1.0, 1.0, 17)
    return PoseFrame(
        keypoints=points,
        scores=np.ones(17, dtype=np.float64),
        timestamp_s=0.0,
        frame_index=3,
    )


def test_baseline_lifter_adds_bounded_depth() -> None:
    lifter = BaselinePoseLifter()
    lifted = lifter.lift_frame(_normalized_pose())
    assert lifted.frame_index == 3
    assert np.all(np.isfinite(lifted.keypoints[:, 2]))
    assert np.max(np.abs(lifted.keypoints[:, 2])) <= 0.08 + 1e-9


def test_privacy_blurs_only_non_primary_regions() -> None:
    frame = np.zeros((80, 160, 3), dtype=np.uint8)
    checker = np.indices((80, 80)).sum(axis=0) % 2
    frame[:, 80:, 0] = checker.astype(np.uint8) * 255
    boxes = np.asarray([[0, 0, 70, 80], [80, 0, 160, 80]], dtype=np.float64)
    masked = blur_other_people(frame, boxes, primary_index=0)
    assert np.array_equal(masked[:, :80], frame[:, :80])
    assert not np.array_equal(masked[:, 80:], frame[:, 80:])


def test_cloud_tts_endpoint_is_openai_compatible() -> None:
    config = CloudTTSConfig(base_url="https://example.com/v1/")
    assert config.endpoint() == "https://example.com/v1/audio/speech"


def test_dashscope_environment_selects_qwen_session_defaults() -> None:
    preset = default_provider_for_session({"DASHSCOPE_API_KEY": "session-only"})
    assert preset.key == "qwen"
    assert preset.llm_base_url.endswith("/compatible-mode/v1")
    assert preset.asr_model == "qwen3-asr-flash"
    assert preset.tts_model == "qwen-tts"
