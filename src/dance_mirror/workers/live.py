"""Real-time camera -> pose -> comparison worker."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import numpy as np
from PyQt6.QtCore import pyqtSignal

from dance_mirror.capture import CameraSource
from dance_mirror.coaching.policy import CoachPolicy
from dance_mirror.domain.quality import MotionQualityProfile, assess_motion_quality
from dance_mirror.domain.types import (
    CoachCue,
    PoseFrame,
    PoseSequence,
    TrainingUpdate,
)
from dance_mirror.motion.comparison import ComparisonConfig, compare_feature_frames
from dance_mirror.motion.comparison_space import (
    CameraProfile,
    CameraView,
    build_comparison_space,
)
from dance_mirror.motion.features import FeatureSequence, extract_feature_sequence, extract_features
from dance_mirror.motion.hand_features import (
    HandFeatureSequence,
    HandPerformanceTracker,
    extract_hand_features,
    face_performance_score,
    hands_by_side,
)
from dance_mirror.motion.normalization import (
    NormalizationError,
    normalize_frame,
    normalize_sequence,
)
from dance_mirror.motion.retarget import retarget_frame
from dance_mirror.motion.sync import SyncController, SyncPolicy
from dance_mirror.multimodal.face import FaceObservation, MediaPipeFaceTracker
from dance_mirror.multimodal.gesture import (
    HandGesture,
    MediaPipeHandTracker,
    pose_hand_search_roi,
    select_primary_gesture,
)
from dance_mirror.multimodal.preview import build_camera_preview
from dance_mirror.pose2d.yolo_pose import YoloPoseConfig, YoloPoseEstimator
from dance_mirror.pose3d.baseline import BaselinePoseLifter
from dance_mirror.pose3d.blaze_pose import BlazePoseConfig, BlazePoseEstimator, PoseEstimate
from dance_mirror.pose3d.registry import make_pose_estimator
from dance_mirror.privacy import PrivacyConfig, blur_other_people
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class LiveTrainingWorker(CancellableWorker):
    """Process camera frames and emit pure comparison/retargeting data."""

    updateReady = pyqtSignal(object)
    poseReady = pyqtSignal(object)
    referencePoseReady = pyqtSignal(object)
    privacyChanged = pyqtSignal(bool)
    recordingChanged = pyqtSignal(bool)
    qualityReady = pyqtSignal(object)
    syncReady = pyqtSignal(object)
    previewReady = pyqtSignal(object)
    gestureReady = pyqtSignal(str, float)

    def __init__(
        self,
        reference: PoseSequence,
        camera_index: int = 0,
        *,
        pose_config: YoloPoseConfig | None = None,
        comparison_config: ComparisonConfig | None = None,
        target_fps: float = 15.0,
        camera_width: int = 1280,
        camera_height: int = 720,
        camera_fps: float = 30.0,
        privacy_shield: bool = True,
        privacy_config: PrivacyConfig | None = None,
        record_path: str | None = None,
        mirror_user: bool = False,
        reference_camera: CameraProfile | None = None,
        user_camera: CameraProfile | None = None,
        pose_backend: str = "blazepose",
        sync_policy: SyncPolicy | None = None,
        enable_hand_gestures: bool = True,
        gesture_interval_frames: int = 3,
        enable_face: bool = True,
        face_interval_frames: int = 3,
    ) -> None:
        super().__init__()
        self.enable_hand_gestures = bool(enable_hand_gestures)
        self.gesture_interval_frames = max(1, int(gesture_interval_frames))
        self.enable_face = bool(enable_face)
        self.face_interval_frames = max(1, int(face_interval_frames))
        self.reference = reference
        self.camera_index = camera_index
        self.pose_config = pose_config or YoloPoseConfig()
        self.comparison_config = comparison_config or ComparisonConfig()
        self.target_fps = max(1.0, float(target_fps))
        self.camera_width = max(320, int(camera_width))
        self.camera_height = max(240, int(camera_height))
        self.camera_fps = max(1.0, float(camera_fps))
        self.privacy_shield = privacy_shield
        self.privacy_config = privacy_config or PrivacyConfig()
        self.record_path = record_path
        self.mirror_user = mirror_user
        self.policy = CoachPolicy()
        self.depth_lifter = BaselinePoseLifter()
        self.reference_camera = reference_camera or self._reference_camera_profile(reference)
        self.user_camera = user_camera or CameraProfile(view=CameraView.FRONT)
        self.pose_backend = str(pose_backend or "blazepose").lower()
        self.sync = SyncController(sync_policy)
        self.quality = self._reference_quality(reference)

    @staticmethod
    def _reference_camera_profile(reference: PoseSequence) -> CameraProfile:
        if isinstance(reference.metadata.get("camera_profile"), dict):
            return CameraProfile.from_metadata(reference.metadata)
        return CameraProfile(view=CameraView.FRONT)

    @staticmethod
    def _reference_quality(reference: PoseSequence) -> MotionQualityProfile:
        explicit = MotionQualityProfile.from_metadata(reference.metadata)
        return explicit or assess_motion_quality(reference)

    def run(self) -> None:
        writer: object | None = None
        privacy_state = False
        estimator: YoloPoseEstimator | BlazePoseEstimator | None = None
        hand_tracker: MediaPipeHandTracker | None = None
        face_tracker: MediaPipeFaceTracker | None = None
        camera: CameraSource | None = None
        last_gesture_name = ""
        last_gesture_at = 0.0
        last_hand_gestures: tuple[HandGesture, ...] = ()
        last_face: FaceObservation | None = None
        try:
            normalized_reference = self._normalized_reference()
            reference_features = extract_feature_sequence(
                normalized_reference,
                min_confidence=self.comparison_config.min_confidence,
            )
            reference_hands = HandFeatureSequence.from_metadata(
                normalized_reference.metadata,
                expected_length=len(normalized_reference),
            )
            hand_performance = HandPerformanceTracker(reference_hands)
            if len(reference_features) == 0:
                self.errorOccurred.emit("参考动作包没有可用帧。")
                return

            space = build_comparison_space(
                self.reference_camera,
                self.user_camera,
                quality=self.quality,
            )
            effective_config = replace(self.comparison_config, feature_space=space)
            self.qualityReady.emit(self.quality)

            estimator = make_pose_estimator(
                self.pose_backend,
                yolo_config=self.pose_config,
                blaze_config=BlazePoseConfig(),
            )
            if self.enable_hand_gestures:
                hand_tracker = MediaPipeHandTracker()
            if self.enable_face:
                face_tracker = MediaPipeFaceTracker()
            camera = CameraSource(
                self.camera_index,
                width=self.camera_width,
                height=self.camera_height,
                fps=self.camera_fps,
            )
            if self.record_path:
                writer = self._open_recording(camera)
                if writer is None:
                    return
                self.recordingChanged.emit(True)

            period = 1.0 / self.target_fps
            session_started = time.perf_counter()
            while not self._stopped:
                cycle_start = time.perf_counter()
                timestamp_s = time.perf_counter() - session_started
                packet = camera.read()
                if packet is None:
                    self.errorOccurred.emit("摄像头读帧失败，请检查设备和权限。")
                    return
                pose_started = time.perf_counter()
                pose = estimator.estimate(
                    packet.image,
                    frame_index=packet.index,
                    timestamp_s=timestamp_s,
                )
                pose_latency_s = time.perf_counter() - pose_started
                gestures = last_hand_gestures
                face = last_face
                if (
                    hand_tracker is not None
                    and hand_tracker.available
                    and packet.index % self.gesture_interval_frames == 0
                ):
                    search_roi = (
                        pose_hand_search_roi(
                            pose.pose2d.keypoints,
                            pose.pose2d.scores,
                            (packet.image.shape[1], packet.image.shape[0]),
                        )
                        if pose is not None
                        else None
                    )
                    gestures = hand_tracker.process(packet.image, search_roi=search_roi)
                    last_hand_gestures = gestures
                    gesture = select_primary_gesture(gestures)
                    if gesture is not None:
                        now = time.perf_counter()
                        if (
                            gesture.name != last_gesture_name
                            or gesture.name == "ok"
                            or now - last_gesture_at >= 0.8
                        ):
                            last_gesture_name = gesture.name
                            last_gesture_at = now
                            self.gestureReady.emit(gesture.name, gesture.confidence)
                if (
                    face_tracker is not None
                    and face_tracker.available
                    and packet.index % self.face_interval_frames == 0
                ):
                    face = face_tracker.process(packet.image)
                    last_face = face
                recording_frame = packet.image
                has_other_people = bool(
                    self.privacy_shield and estimator.last_person_count > 1
                )
                if has_other_people:
                    recording_frame = blur_other_people(
                        recording_frame,
                        estimator.last_boxes,
                        primary_index=estimator.last_primary_index,
                        config=self.privacy_config,
                    )
                if has_other_people != privacy_state:
                    privacy_state = has_other_people
                    self.privacyChanged.emit(privacy_state)
                if writer is not None:
                    writer.write(recording_frame)

                if pose is not None:
                    self._process_user_pose(
                        pose,
                        normalized_reference=normalized_reference,
                        reference_features=reference_features,
                        camera=camera,
                        timestamp_s=timestamp_s,
                        pose_latency_s=pose_latency_s,
                        now_s=time.perf_counter() - session_started,
                        comparison_config=effective_config,
                        hands=gestures,
                        face=face,
                        hand_performance=hand_performance,
                    )

                score_values = pose.pose2d.scores if pose is not None else None
                readiness = (
                    float((score_values >= 0.35).mean())
                    if score_values is not None
                    else 0.0
                )
                self.previewReady.emit(
                    build_camera_preview(
                        packet.image,
                        pose.pose2d if pose is not None else None,
                        bbox_xyxy=self._primary_bbox(estimator),
                        person_count=estimator.last_person_count,
                        frame_index=packet.index,
                        timestamp_s=timestamp_s,
                        readiness=readiness,
                        preview_width=480,
                        privacy_masked=has_other_people,
                        hands=gestures,
                        face=face,
                        left_wrist=(
                            pose.pose2d.keypoints[9, :2]
                            if pose is not None and pose.pose2d.scores[9] >= 0.25
                            else None
                        ),
                        right_wrist=(
                            pose.pose2d.keypoints[10, :2]
                            if pose is not None and pose.pose2d.scores[10] >= 0.25
                            else None
                        ),
                    )
                )

                elapsed = time.perf_counter() - cycle_start
                if elapsed < period:
                    time.sleep(period - elapsed)
        except Exception as exc:
            LOGGER.exception("live training worker failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if writer is not None:
                writer.release()
                self.recordingChanged.emit(False)
            if camera is not None:
                camera.close()
            if estimator is not None:
                estimator.close()
            if hand_tracker is not None:
                hand_tracker.close()
            if face_tracker is not None:
                face_tracker.close()
            self.finished.emit()

    @staticmethod
    def _primary_bbox(
        estimator: YoloPoseEstimator | BlazePoseEstimator,
    ) -> tuple[float, float, float, float] | None:
        boxes = estimator.last_boxes
        if boxes is None or boxes.size == 0:
            return None
        index = min(max(0, estimator.last_primary_index), len(boxes) - 1)
        return tuple(float(value) for value in boxes[index, :4])  # type: ignore[return-value]

    def _normalized_reference(self) -> PoseSequence:
        metadata = self.reference.metadata
        if metadata.get("normalized"):
            return self.reference
        width = int(metadata.get("source_width", 0) or 0)
        height = int(metadata.get("source_height", 0) or 0)
        return normalize_sequence(
            self.reference,
            image_size=(width, height) if width > 0 and height > 0 else None,
            mirror=False,
            min_confidence=self.comparison_config.min_confidence,
        )

    def _process_user_pose(
        self,
        pose: PoseEstimate,
        *,
        normalized_reference: PoseSequence,
        reference_features: FeatureSequence,
        camera: CameraSource,
        timestamp_s: float,
        pose_latency_s: float,
        now_s: float,
        comparison_config: ComparisonConfig,
        hands: tuple[HandGesture, ...],
        face: FaceObservation | None,
        hand_performance: HandPerformanceTracker,
    ) -> None:
        """Score one live pose while treating an unusable frame as a gap."""
        try:
            normalized_user = normalize_frame(
                pose.pose3d,
                image_size=None if pose.is_metric else (camera.width, camera.height),
                mirror=self.mirror_user,
                min_confidence=comparison_config.min_confidence,
            )
        except NormalizationError:
            LOGGER.debug("skipping a pose frame without usable torso joints")
            return

        user_feature = extract_features(
            normalized_user,
            min_confidence=comparison_config.min_confidence,
        )
        sync_snapshot = self.sync.effective_pose_time(
            timestamp_s,
            now_s=now_s,
            capture_to_pose_latency_s=pose_latency_s,
        )
        reference_index = self._nearest_reference_index(
            reference_features,
            sync_snapshot.pose_effective_time_s,
        )
        reference_feature = reference_features.frame(reference_index)
        score = compare_feature_frames(
            reference_feature,
            user_feature,
            config=comparison_config,
        )
        left_wrist = pose.pose2d.keypoints[9, :2] if pose.pose2d.scores[9] >= 0.25 else None
        right_wrist = pose.pose2d.keypoints[10, :2] if pose.pose2d.scores[10] >= 0.25 else None
        user_hands = hands_by_side(
            hands,
            left_wrist=left_wrist,
            right_wrist=right_wrist,
            image_size=(camera.width, camera.height),
            mirror=self.mirror_user,
        )
        hand_feature = extract_hand_features(
            hands,
            mirror=self.mirror_user,
            left_wrist=left_wrist,
            right_wrist=right_wrist,
            image_size=(camera.width, camera.height),
        )
        hand_score = hand_performance.score(
            hand_feature,
            frame_index=reference_index,
            mirror=self.mirror_user,
        )
        face_score = face_performance_score(face)
        hand_weight = 0.16 if hand_score.mode == "reference" else 0.08
        combined_overall = round(
            score.overall * (1.0 - hand_weight) + hand_score.overall * hand_weight,
            2,
        )
        combined_score = replace(
            score,
            overall=combined_overall,
            dimensions={
                "body": round(float(score.overall), 2),
                "hands": round(float(hand_score.overall), 2),
                "face": round(float(face_score), 2),
            },
        )
        cue = self.policy.evaluate(score, sync_snapshot.pose_effective_time_s)
        if cue is None and hand_score.cue and hand_score.mode == "reference":
            cue = CoachCue(
                feature="hands",
                text=hand_score.cue,
                priority=2,
                severity=max(0.25, 1.0 - hand_score.overall / 100.0),
                timestamp_s=sync_snapshot.pose_effective_time_s,
            )
        update = TrainingUpdate(
            reference_time_s=float(reference_features.timestamps_s[reference_index]),
            score=combined_score,
            cue=cue,
        )
        # Real-3D backends already carry metric depth; only the 2D (YOLO)
        # backend needs the synthetic lifter to fill z.
        lifted_user = (
            normalized_user
            if pose.is_metric
            else self.depth_lifter.lift_frame(normalized_user)
        )
        self.syncReady.emit(sync_snapshot)
        self.updateReady.emit(update)
        self.poseReady.emit(retarget_frame(lifted_user, hands=user_hands))
        reference_frame = self._pose_frame(
            normalized_reference,
            min(reference_index, len(normalized_reference) - 1),
        )
        reference_hands = self._reference_hands(normalized_reference, reference_index)
        self.referencePoseReady.emit(retarget_frame(reference_frame, hands=reference_hands))
        self.progressChanged.emit(
            max(0, min(100, int(sync_snapshot.pose_effective_time_s * self.target_fps)))
        )


    @staticmethod
    def _reference_hands(
        sequence: PoseSequence,
        frame_index: int,
    ) -> dict[str, np.ndarray] | None:
        rows = sequence.metadata.get("hand_landmarks")
        if not isinstance(rows, (list, tuple)) or not rows:
            return None
        index = max(0, min(int(frame_index), len(rows) - 1))
        row = rows[index]
        if not isinstance(row, Mapping):
            return None
        output: dict[str, np.ndarray] = {}
        for side in ("left", "right"):
            points = row.get(side)
            if points is None:
                continue
            values = np.asarray(points, dtype=np.float64)
            if values.shape == (21, 3):
                output[side] = values
        return output or None

    def _open_recording(self, camera: CameraSource) -> object | None:
        try:
            import cv2
        except ImportError:
            self.errorOccurred.emit("录像需要 OpenCV。")
            return None
        output_path = Path(self.record_path or "").expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self.target_fps,
            (camera.width, camera.height),
        )
        if not writer.isOpened():
            writer.release()
            self.errorOccurred.emit("无法创建本地录像文件。")
            return None
        return writer

    @staticmethod
    def _pose_frame(sequence: PoseSequence, index: int) -> PoseFrame:
        return PoseFrame(
            keypoints=sequence.keypoints[index],
            scores=sequence.scores[index],
            timestamp_s=float(sequence.timestamps_s[index]),
            frame_index=index,
            schema=sequence.schema,
        )

    @staticmethod
    def _nearest_reference_index(
        reference: FeatureSequence,
        timestamp_s: float,
    ) -> int:
        if len(reference) == 0:
            return 0
        timestamps = reference.timestamps_s
        relative = timestamps - timestamp_s
        return int(abs(relative).argmin())
