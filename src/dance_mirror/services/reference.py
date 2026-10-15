"""Reference-video analysis service used by both CLI and Qt workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from dance_mirror.capture import VideoSource
from dance_mirror.domain.quality import assess_motion_quality
from dance_mirror.domain.types import PoseSequence
from dance_mirror.motion.hand_features import (
    HAND_FEATURE_NAMES,
    extract_hand_features,
    hand_feature_rows,
    match_hands_to_wrists,
)
from dance_mirror.motion.normalization import normalize_sequence
from dance_mirror.motion.smoothing import fill_short_gaps
from dance_mirror.multimodal.gesture import MediaPipeHandTracker
from dance_mirror.pose2d.yolo_pose import YoloPoseConfig, YoloPoseEstimator
from dance_mirror.pose3d.baseline import BaselinePoseLifter


@dataclass(slots=True)
class ReferenceAnalysisResult:
    """Pose sequence and source coverage statistics."""

    sequence: PoseSequence
    total_frames: int
    detected_frames: int


ProgressCallback = Callable[[int], None]
CancelCheck = Callable[[], bool]


def analyze_reference_video(
    video_path: str,
    *,
    pose_config: YoloPoseConfig | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: CancelCheck | None = None,
) -> ReferenceAnalysisResult:
    """Process one reference video exactly once and return a lifted sequence."""
    estimator = YoloPoseEstimator(pose_config)
    hand_tracker = MediaPipeHandTracker(max_hands=2)
    frames: list[np.ndarray] = []
    scores: list[np.ndarray] = []
    timestamps: list[float] = []
    hand_values: list[list[float | None]] = []
    hand_confidence: list[list[float]] = []
    hand_landmarks: list[dict[str, list[list[float]]]] = []
    total_frames = 0
    source_width = 0
    source_height = 0
    source_fps = 30.0
    try:
        with VideoSource(video_path) as source:
            total_frames = source.frame_count
            source_width = int(source.width)
            source_height = int(source.height)
            source_fps = float(source.fps)
            expected_total = max(total_frames, 1)
            for packet in source.frames():
                if should_cancel is not None and should_cancel():
                    raise InterruptedError("reference analysis cancelled")
                pose = estimator.estimate(
                    packet.image,
                    frame_index=packet.index,
                    timestamp_s=packet.timestamp_s,
                )
                if pose is not None:
                    frames.append(pose.pose3d.keypoints)
                    scores.append(pose.pose3d.scores)
                    timestamps.append(pose.pose3d.timestamp_s)
                    gestures = hand_tracker.process(packet.image)
                    hand_feature = extract_hand_features(
                        gestures,
                        left_wrist=pose.pose2d.keypoints[9, :2],
                        right_wrist=pose.pose2d.keypoints[10, :2],
                        image_size=(source_width, source_height),
                    )
                    values, confidence = hand_feature_rows(hand_feature)
                    hand_values.append(values)
                    hand_confidence.append(confidence)
                    hand_landmarks.append(
                        {
                            side: gesture.landmarks.tolist()
                            for side, gesture in match_hands_to_wrists(
                                gestures,
                                left_wrist=pose.pose2d.keypoints[9, :2],
                                right_wrist=pose.pose2d.keypoints[10, :2],
                                image_size=(source_width, source_height),
                            )
                            if side in {"left", "right"}
                        }
                    )
                if progress is not None:
                    progress(min(99, int((packet.index + 1) * 100 / expected_total)))
    finally:
        estimator.close()
        hand_tracker.close()

    if not frames:
        raise ValueError("no usable pose was detected in the reference video")
    if progress is not None:
        progress(100)

    raw_sequence = PoseSequence(
        keypoints=np.stack(frames, axis=0),
        scores=np.stack(scores, axis=0),
        timestamps_s=np.asarray(timestamps, dtype=np.float64),
        fps=source_fps,
        metadata={
            "source": video_path,
            "kind": "reference",
            "source_width": source_width,
            "source_height": source_height,
            "source_fps": source_fps,
        },
    )
    image_size = (
        source_width if source_width > 0 else None,
        source_height if source_height > 0 else None,
    )
    repaired_points, repaired_scores = fill_short_gaps(
        raw_sequence.keypoints,
        raw_sequence.scores,
        min_confidence=0.25,
        max_gap=8,
    )
    prepared_sequence = PoseSequence(
        keypoints=repaired_points,
        scores=repaired_scores,
        timestamps_s=raw_sequence.timestamps_s.copy(),
        fps=raw_sequence.fps,
        schema=raw_sequence.schema,
        metadata=dict(raw_sequence.metadata),
    )
    normalized = normalize_sequence(
        prepared_sequence,
        image_size=image_size if all(image_size) else None,
        min_confidence=0.25,
    )
    sequence = BaselinePoseLifter().lift(normalized)
    quality = assess_motion_quality(sequence)
    sequence.metadata = {
        **dict(sequence.metadata),
        "source": video_path,
        "kind": "reference",
        "source_width": source_width,
        "source_height": source_height,
        "source_fps": source_fps,
        "quality": quality.as_metadata(),
        "quality_level": quality.level.value,
        "hand_feature_names": list(HAND_FEATURE_NAMES),
        "hand_features": hand_values,
        "hand_confidence": hand_confidence,
        "hand_landmarks": hand_landmarks,
    }
    return ReferenceAnalysisResult(
        sequence=sequence,
        total_frames=total_frames,
        detected_frames=len(frames),
    )
