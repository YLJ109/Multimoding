"""Immutable camera preview packet passed from workers to the Qt main thread."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from dance_mirror.domain.types import PoseFrame
from dance_mirror.multimodal.face import FACE_LANDMARK_COUNT, FaceObservation
from dance_mirror.multimodal.gesture import HandGesture


@dataclass(frozen=True, slots=True)
class HandPreview:
    """One hand overlay in preview pixel coordinates."""

    side: str
    name: str
    confidence: float
    landmarks_px: NDArray[np.float64]

    def __post_init__(self) -> None:
        points = np.asarray(self.landmarks_px, dtype=np.float64)
        if points.shape != (21, 3):
            raise ValueError("hand preview landmarks must have shape (21, 3)")
        if self.side not in {"left", "right", "unknown"}:
            raise ValueError("hand preview side is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("hand preview confidence must be in [0, 1]")
        object.__setattr__(self, "landmarks_px", points.copy())
        object.__setattr__(self, "side", str(self.side))
        object.__setattr__(self, "name", str(self.name))


def _empty_face_points() -> NDArray[np.float64]:
    return np.zeros((0, 3), dtype=np.float64)


@dataclass(frozen=True, slots=True)
class CameraPreviewPacket:
    """A downscaled camera image plus overlay coordinates in preview pixels."""

    frame_bgr: NDArray[np.uint8]
    keypoints_px: NDArray[np.float64]
    scores: NDArray[np.float64]
    bbox_xyxy: tuple[float, float, float, float] | None
    person_count: int
    frame_index: int
    timestamp_s: float
    readiness: float
    privacy_masked: bool = False
    hands: tuple[HandPreview, ...] = ()
    face_landmarks_px: NDArray[np.float64] = field(default_factory=_empty_face_points)
    face_bbox_xyxy: tuple[float, float, float, float] | None = None
    face_expression: str = ""
    eye_open: float = 0.0
    mouth_open: float = 0.0

    def __post_init__(self) -> None:
        frame = np.asarray(self.frame_bgr, dtype=np.uint8)
        points = np.asarray(self.keypoints_px, dtype=np.float64)
        scores = np.asarray(self.scores, dtype=np.float64)
        face_points = np.asarray(self.face_landmarks_px, dtype=np.float64)
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("preview frame must have shape (H, W, 3)")
        if points.shape != (17, 3):
            raise ValueError("preview keypoints must have shape (17, 3)")
        if scores.shape != (17,):
            raise ValueError("preview scores must have shape (17,)")
        if face_points.shape not in {(0, 3), (FACE_LANDMARK_COUNT, 3)}:
            raise ValueError(
                "face landmarks must be empty or have shape "
                f"({FACE_LANDMARK_COUNT}, 3)"
            )
        if not 0.0 <= self.readiness <= 1.0:
            raise ValueError("readiness must be in [0, 1]")
        if not 0.0 <= self.eye_open <= 1.0 or not 0.0 <= self.mouth_open <= 1.0:
            raise ValueError("face indicators must be in [0, 1]")
        object.__setattr__(self, "frame_bgr", frame.copy())
        object.__setattr__(self, "keypoints_px", points.copy())
        object.__setattr__(self, "scores", scores.copy())
        object.__setattr__(self, "face_landmarks_px", face_points.copy())
        object.__setattr__(self, "hands", tuple(self.hands))


def _scale_tuple(
    values: tuple[float, float, float, float] | None,
    scale: float,
) -> tuple[float, float, float, float] | None:
    if values is None:
        return None
    return tuple(float(value * scale) for value in values)  # type: ignore[return-value]


def _scale_hands(
    hands: tuple[tuple[str, HandGesture], ...],
    scale: float,
) -> tuple[HandPreview, ...]:
    output: list[HandPreview] = []
    for side, hand in hands:
        points = np.asarray(hand.landmarks, dtype=np.float64).copy()
        points[:, :2] *= scale
        output.append(
            HandPreview(
                side=side,
                name=hand.name,
                confidence=hand.confidence,
                landmarks_px=points,
            )
        )
    return tuple(output)


def _scale_face(
    face: FaceObservation | None,
    scale: float,
    frame_width: int,
    frame_height: int,
) -> tuple[
    NDArray[np.float64],
    tuple[float, float, float, float] | None,
    str,
    float,
    float,
]:
    if face is None:
        return _empty_face_points(), None, "", 0.0, 0.0
    points = np.asarray(face.landmarks, dtype=np.float64).copy()
    points[:, :2] *= scale
    bbox = (
        float(points[:, 0].min() * frame_width),
        float(points[:, 1].min() * frame_height),
        float(points[:, 0].max() * frame_width),
        float(points[:, 1].max() * frame_height),
    )
    return points, bbox, face.expression, face.eye_open, face.mouth_open


def build_camera_preview(
    frame_bgr: NDArray[np.uint8],
    pose: PoseFrame | None,
    *,
    bbox_xyxy: tuple[float, float, float, float] | None = None,
    person_count: int = 0,
    frame_index: int = 0,
    timestamp_s: float = 0.0,
    readiness: float = 0.0,
    preview_width: int = 480,
    privacy_masked: bool = False,
    hands: tuple[HandGesture, ...] = (),
    face: FaceObservation | None = None,
    left_wrist: np.ndarray | None = None,
    right_wrist: np.ndarray | None = None,
    mirror: bool = False,
) -> CameraPreviewPacket:
    """Build a downscaled preview packet without doing any Qt work."""
    frame = np.asarray(frame_bgr, dtype=np.uint8)
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("preview frame must have shape (H, W, 3)")
    if pose is not None and not isinstance(pose, PoseFrame):
        # `estimate()` returns a PoseEstimate wrapper; the overlay needs the
        # inner 2D frame.  Fail loudly instead of raising a cryptic AttributeError.
        raise TypeError(
            "build_camera_preview expects a PoseFrame; pass pose.pose2d when "
            "you hold a PoseEstimate"
        )
    height, width = frame.shape[:2]
    from dance_mirror.motion.hand_features import match_hands_to_wrists

    matched_hands = match_hands_to_wrists(
        hands,
        left_wrist=left_wrist,
        right_wrist=right_wrist,
        image_size=(width, height),
        mirror=mirror,
    )
    target_width = max(240, min(720, int(preview_width)))
    scale = min(1.0, target_width / max(width, 1))
    preview = frame
    if scale < 1.0:
        import cv2

        preview = cv2.resize(
            frame,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    if pose is None:
        points = np.zeros((17, 3), dtype=np.float64)
        scores = np.zeros(17, dtype=np.float64)
    else:
        points = np.asarray(pose.keypoints, dtype=np.float64).copy()
        scores = np.asarray(pose.scores, dtype=np.float64).copy()
        points[:, :2] *= scale
    scaled_bbox = _scale_tuple(bbox_xyxy, scale)
    face_points, face_bbox, expression, eye_open, mouth_open = _scale_face(
        face,
        scale,
        preview.shape[1],
        preview.shape[0],
    )
    return CameraPreviewPacket(
        frame_bgr=preview,
        keypoints_px=points,
        scores=scores,
        bbox_xyxy=scaled_bbox,
        person_count=max(0, int(person_count)),
        frame_index=max(0, int(frame_index)),
        timestamp_s=max(0.0, float(timestamp_s)),
        readiness=max(0.0, min(1.0, float(readiness))),
        privacy_masked=bool(privacy_masked),
        hands=_scale_hands(matched_hands, scale),
        face_landmarks_px=face_points,
        face_bbox_xyxy=face_bbox,
        face_expression=expression,
        eye_open=max(0.0, min(1.0, float(eye_open))),
        mouth_open=max(0.0, min(1.0, float(mouth_open))),
    )


def packet_from_bgr(
    frame: object,
    *,
    keypoints_px: object,
    scores: object,
    bbox_xyxy: tuple[float, float, float, float] | None,
    person_count: int,
    frame_index: int,
    timestamp_s: float,
    readiness: float,
    privacy_masked: bool = False,
    hands: tuple[HandPreview, ...] = (),
    face_landmarks_px: object | None = None,
    face_bbox_xyxy: tuple[float, float, float, float] | None = None,
    face_expression: str = "",
    eye_open: float = 0.0,
    mouth_open: float = 0.0,
    **_: Any,
) -> CameraPreviewPacket:
    """Compatibility helper for workers that already prepared overlay data."""
    return CameraPreviewPacket(
        frame_bgr=np.asarray(frame, dtype=np.uint8),
        keypoints_px=np.asarray(keypoints_px, dtype=np.float64),
        scores=np.asarray(scores, dtype=np.float64),
        bbox_xyxy=bbox_xyxy,
        person_count=int(person_count),
        frame_index=int(frame_index),
        timestamp_s=float(timestamp_s),
        readiness=float(readiness),
        privacy_masked=bool(privacy_masked),
        hands=hands,
        face_landmarks_px=(
            np.asarray(face_landmarks_px, dtype=np.float64)
            if face_landmarks_px is not None
            else _empty_face_points()
        ),
        face_bbox_xyxy=face_bbox_xyxy,
        face_expression=str(face_expression),
        eye_open=float(eye_open),
        mouth_open=float(mouth_open),
    )
