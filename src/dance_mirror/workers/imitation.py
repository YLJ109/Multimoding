"""Real-time camera-to-robot imitation worker for the command center."""

from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PyQt6.QtCore import pyqtSignal

from dance_mirror.capture import CameraSource
from dance_mirror.motion.hand_features import hands_by_side
from dance_mirror.motion.normalization import NormalizationError, normalize_frame
from dance_mirror.motion.retarget import RetargetedSkeleton, retarget_frame
from dance_mirror.multimodal.face import FaceObservation, MediaPipeFaceTracker
from dance_mirror.multimodal.gesture import (
    HandGesture,
    MediaPipeHandTracker,
    pose_hand_search_roi,
    select_primary_gesture,
)
from dance_mirror.multimodal.preview import CameraPreviewPacket, build_camera_preview
from dance_mirror.multimodal.readiness import assess_readiness
from dance_mirror.pose2d.yolo_pose import YoloPoseConfig, YoloPoseEstimator
from dance_mirror.pose3d.baseline import BaselinePoseLifter
from dance_mirror.pose3d.blaze_pose import BlazePoseConfig, PoseEstimate
from dance_mirror.pose3d.registry import make_pose_estimator
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class RobotImitationWorker(CancellableWorker):
    """Capture one pose stream and emit retarget-ready robot skeletons."""

    poseReady = pyqtSignal(object)
    previewReady = pyqtSignal(object)
    readinessReady = pyqtSignal(object)
    qualityReady = pyqtSignal(object)
    safeHoldChanged = pyqtSignal(bool)
    gestureReady = pyqtSignal(str, float)

    def __init__(
        self,
        camera_index: int = 0,
        *,
        pose_config: YoloPoseConfig | None = None,
        pose_backend: str = "blazepose",
        target_fps: float = 15.0,
        camera_width: int = 1280,
        camera_height: int = 720,
        mirror: bool = True,
        smoothing: float = 0.45,
        preview_width: int = 480,
        safe_hold_timeout_s: float = 1.2,
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
        self.camera_index = max(0, int(camera_index))
        self.pose_config = pose_config or YoloPoseConfig()
        self.pose_backend = str(pose_backend or "blazepose").lower()
        self.target_fps = max(1.0, min(60.0, float(target_fps)))
        self.camera_width = max(320, int(camera_width))
        self.camera_height = max(240, int(camera_height))
        self.preview_width = max(240, min(720, int(preview_width)))
        self.safe_hold_timeout_s = max(0.2, float(safe_hold_timeout_s))
        self._mirror = bool(mirror)
        self._smoothing = max(0.0, min(0.95, float(smoothing)))
        self._scope = "full_body"
        self._paused = False
        self._lock = threading.Lock()
        self._lifter = BaselinePoseLifter()

    def configure(
        self,
        *,
        mirror: bool | None = None,
        smoothing: float | None = None,
        scope: str | None = None,
        paused: bool | None = None,
    ) -> None:
        """Apply UI/voice settings without restarting the worker."""
        with self._lock:
            if mirror is not None:
                self._mirror = bool(mirror)
            if smoothing is not None:
                self._smoothing = max(0.0, min(0.95, float(smoothing)))
            if scope is not None:
                allowed = {"full_body", "upper_body", "lower_body", "hands", "head"}
                if scope not in allowed:
                    raise ValueError(f"unsupported imitation scope: {scope}")
                self._scope = scope
            if paused is not None:
                self._paused = bool(paused)

    def run(self) -> None:
        estimator: YoloPoseEstimator | None = None
        hand_tracker: MediaPipeHandTracker | None = None
        face_tracker: MediaPipeFaceTracker | None = None
        camera: CameraSource | None = None
        previous: RetargetedSkeleton | None = None
        last_hands: tuple[HandGesture, ...] = ()
        last_face: FaceObservation | None = None
        last_gesture_name = ""
        last_gesture_at = 0.0
        last_pose_time = time.monotonic()
        safe_hold = False
        try:
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
                fps=min(30.0, self.target_fps),
            )
            started = time.monotonic()
            period = 1.0 / self.target_fps
            while not self._stopped:
                cycle_start = time.monotonic()
                packet = camera.read()
                if packet is None:
                    self.errorOccurred.emit("摄像头读帧失败，请检查设备和权限。")
                    return
                pose_started = time.monotonic()
                pose = estimator.estimate(
                    packet.image,
                    frame_index=packet.index,
                    timestamp_s=cycle_start - started,
                )
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
                    last_hands = gestures
                    gesture = select_primary_gesture(gestures)
                    if gesture is not None:
                        now = time.monotonic()
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
                    last_face = face_tracker.process(packet.image)
                latency_ms = (time.monotonic() - pose_started) * 1000.0
                with self._lock:
                    mirror = self._mirror
                    smoothing = self._smoothing
                    scope = self._scope
                    paused = self._paused

                report = None
                if pose is not None:
                    report = assess_readiness(
                        pose.pose2d,
                        image_size=(camera.width, camera.height),
                        person_count=estimator.last_person_count,
                    )
                    last_pose_time = time.monotonic()
                    if safe_hold:
                        safe_hold = False
                        self.safeHoldChanged.emit(False)
                    if not paused:
                        skeleton = self._pose_to_skeleton(
                            pose,
                            camera,
                            mirror=mirror,
                            hands=last_hands,
                        )
                        if skeleton is not None:
                            previous = self._smooth(previous, skeleton, smoothing)
                            self.poseReady.emit(previous)
                else:
                    if not safe_hold and time.monotonic() - last_pose_time > self.safe_hold_timeout_s:
                        safe_hold = True
                        self.safeHoldChanged.emit(True)

                self.previewReady.emit(
                    self._build_preview(
                        packet.image,
                        pose,
                        bbox=self._primary_bbox(estimator),
                        person_count=estimator.last_person_count,
                        frame_index=packet.index,
                        timestamp_s=cycle_start - started,
                        readiness=report.score if report is not None else 0.0,
                        hands=last_hands,
                        face=last_face,
                    )
                )
                if report is not None:
                    self.readinessReady.emit(report)
                self.qualityReady.emit(
                    {
                        "fps": round(1.0 / max(time.monotonic() - cycle_start, 1e-6), 2),
                        "inference_ms": round(latency_ms, 2),
                        "person_count": estimator.last_person_count,
                        "scope": scope,
                        "paused": paused,
                        "safe_hold": safe_hold,
                    }
                )
                elapsed = time.monotonic() - cycle_start
                if elapsed < period:
                    time.sleep(period - elapsed)
        except Exception as exc:
            LOGGER.exception("robot imitation worker failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if camera is not None:
                camera.close()
            if estimator is not None:
                estimator.close()
            if hand_tracker is not None:
                hand_tracker.close()
            if face_tracker is not None:
                face_tracker.close()
            self.finished.emit()


    def _pose_to_skeleton(
        self,
        pose: PoseEstimate,
        camera: CameraSource,
        *,
        mirror: bool,
        hands: tuple[HandGesture, ...] = (),
    ) -> RetargetedSkeleton | None:
        try:
            normalized = normalize_frame(
                pose.pose3d,
                image_size=None if pose.is_metric else (camera.width, camera.height),
                mirror=mirror,
                min_confidence=0.25,
            )
        except NormalizationError:
            return None
        # Real-3D backends already carry metric depth; the synthetic lifter only
        # fills z for the 2D (YOLO) backend.
        lifted = normalized if pose.is_metric else self._lifter.lift_frame(normalized)
        left_wrist = pose.pose2d.keypoints[9, :2] if pose.pose2d.scores[9] >= 0.25 else None
        right_wrist = pose.pose2d.keypoints[10, :2] if pose.pose2d.scores[10] >= 0.25 else None
        return retarget_frame(
            lifted,
            hands=hands_by_side(
                hands,
                left_wrist=left_wrist,
                right_wrist=right_wrist,
                image_size=(camera.width, camera.height),
                mirror=mirror,
            ),
        )

    @staticmethod
    def _smooth(
        previous: RetargetedSkeleton | None,
        current: RetargetedSkeleton,
        smoothing: float,
    ) -> RetargetedSkeleton:
        if previous is None or smoothing <= 0.0:
            return current
        alpha = max(0.05, 1.0 - smoothing)
        joints: dict[str, tuple[float, float, float]] = {}
        for name, point in current.joints.items():
            old = previous.joints.get(name, point)
            joints[name] = (
                old[0] + alpha * (point[0] - old[0]),
                old[1] + alpha * (point[1] - old[1]),
                old[2] + alpha * (point[2] - old[2]),
            )
        return RetargetedSkeleton(
            joints=joints,
            scores=dict(current.scores),
            edges=current.edges,
            timestamp_s=current.timestamp_s,
            frame_index=current.frame_index,
            hands=current.hands,
        )

    def _build_preview(
        self,
        frame: np.ndarray,
        pose: PoseEstimate | None,
        *,
        bbox: tuple[float, float, float, float] | None,
        person_count: int,
        frame_index: int,
        timestamp_s: float,
        readiness: float,
        hands: tuple[HandGesture, ...] = (),
        face: FaceObservation | None = None,
    ) -> CameraPreviewPacket:
        return build_camera_preview(
            frame,
            pose.pose2d if pose is not None else None,
            bbox_xyxy=bbox,
            person_count=person_count,
            frame_index=frame_index,
            timestamp_s=timestamp_s,
            readiness=readiness,
            preview_width=self.preview_width,
            hands=hands,
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

    @staticmethod
    def _primary_bbox(
        estimator: YoloPoseEstimator,
    ) -> tuple[float, float, float, float] | None:
        boxes = estimator.last_boxes
        if boxes is None or boxes.size == 0:
            return None
        index = min(max(0, estimator.last_primary_index), len(boxes) - 1)
        values = boxes[index, :4]
        return tuple(float(value) for value in values)  # type: ignore[return-value]
