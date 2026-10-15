"""Optional MediaPipe Face Mesh landmarks and lightweight expression state."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dance_mirror.runtime import isolate_mediapipe_runtime

LOGGER = logging.getLogger(__name__)

FACE_LANDMARK_COUNT = 468

# A compact set of semantically useful landmarks. The complete 468-point mesh
# is still retained in FaceObservation so future renderers can use it directly.
FACE_OUTLINE = (
    10,
    338,
    297,
    332,
    284,
    251,
    389,
    356,
    454,
    323,
    361,
    288,
    397,
    365,
    379,
    378,
    400,
    377,
    152,
    148,
    176,
    149,
    150,
    136,
    172,
    58,
    132,
    93,
    234,
    127,
    162,
    21,
    54,
    103,
    67,
    109,
    10,
)
LEFT_EYE = (33, 160, 158, 133, 153, 144, 33)
RIGHT_EYE = (362, 385, 387, 263, 373, 380, 362)
LEFT_EYEBROW = (70, 63, 105, 66, 107)
RIGHT_EYEBROW = (336, 296, 334, 293, 300)
NOSE = (168, 6, 197, 195, 5, 4, 1, 2, 98, 327)
LIPS = (
    61,
    185,
    40,
    39,
    37,
    0,
    267,
    269,
    270,
    409,
    291,
    308,
    415,
    310,
    311,
    312,
    13,
    82,
    81,
    80,
    191,
    78,
    62,
    76,
    77,
    96,
    146,
    61,
)


@dataclass(frozen=True, slots=True)
class FaceObservation:
    """One detected face in normalized image coordinates."""

    landmarks: NDArray[np.float64]
    expression: str
    eye_open: float
    mouth_open: float
    smile: float
    confidence: float

    def __post_init__(self) -> None:
        points = np.asarray(self.landmarks, dtype=np.float64)
        if points.shape != (FACE_LANDMARK_COUNT, 3):
            raise ValueError(
                f"face landmarks must have shape ({FACE_LANDMARK_COUNT}, 3), got {points.shape}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("face confidence must be in [0, 1]")
        object.__setattr__(self, "landmarks", points.copy())
        object.__setattr__(self, "eye_open", _bounded(self.eye_open))
        object.__setattr__(self, "mouth_open", _bounded(self.mouth_open))
        object.__setattr__(self, "smile", _bounded(self.smile))


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _distance(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.linalg.norm(first[:2] - second[:2]))


def analyze_face_landmarks(
    landmarks: NDArray[np.float64],
    *,
    confidence: float = 1.0,
) -> FaceObservation:
    """Derive deterministic eye, mouth, and smile indicators from Face Mesh."""
    points = np.asarray(landmarks, dtype=np.float64)
    if points.shape != (FACE_LANDMARK_COUNT, 3):
        raise ValueError(
            f"face landmarks must have shape ({FACE_LANDMARK_COUNT}, 3), got {points.shape}"
        )
    face_width = max(1e-6, _distance(points[234], points[454]))
    face_height = max(1e-6, _distance(points[10], points[152]))
    left_eye = (
        _distance(points[159], points[145]) + _distance(points[158], points[153])
    ) / (2.0 * face_height)
    right_eye = (
        _distance(points[386], points[374]) + _distance(points[385], points[380])
    ) / (2.0 * face_height)
    eye_open = max(0.0, min(1.0, ((left_eye + right_eye) / 2.0 - 0.012) / 0.045))
    mouth_open = max(0.0, min(1.0, (_distance(points[13], points[14]) - 0.006) / 0.16))
    mouth_width = _distance(points[61], points[291]) / face_width
    corner_height = (points[61, 1] + points[291, 1]) * 0.5 - points[13, 1]
    smile = max(0.0, min(1.0, (mouth_width - 0.48) / 0.40 + (-corner_height) / face_height * 1.5))
    if eye_open <= 0.18:
        expression = "blink"
    elif mouth_open >= 0.55:
        expression = "surprised"
    elif smile >= 0.58:
        expression = "smile"
    elif eye_open >= 0.55:
        expression = "focused"
    else:
        expression = "neutral"
    return FaceObservation(
        landmarks=points,
        expression=expression,
        eye_open=eye_open,
        mouth_open=mouth_open,
        smile=smile,
        confidence=max(0.0, min(1.0, float(confidence))),
    )


def face_connections() -> tuple[tuple[int, int], ...]:
    """Return a compact, attractive face-wire topology using source indices."""
    connections: list[tuple[int, int]] = []
    for chain in (
        FACE_OUTLINE,
        LEFT_EYE,
        RIGHT_EYE,
        LEFT_EYEBROW,
        RIGHT_EYEBROW,
        NOSE,
        LIPS,
    ):
        connections.extend(zip(chain[:-1], chain[1:], strict=False))
    return tuple(connections)


class MediaPipeFaceTracker:
    """Thread-confined optional MediaPipe Face Mesh wrapper."""

    def __init__(
        self,
        *,
        min_detection_confidence: float = 0.50,
        refine_landmarks: bool = False,
    ) -> None:
        self.available = False
        self._face_mesh: object | None = None
        try:
            isolate_mediapipe_runtime()
            import mediapipe as mp
        except Exception:
            LOGGER.warning("MediaPipe Face Mesh is unavailable", exc_info=True)
            return
        try:
            self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=bool(refine_landmarks),
                min_detection_confidence=max(0.1, min(0.95, min_detection_confidence)),
                min_tracking_confidence=0.50,
            )
        except Exception:
            LOGGER.exception("MediaPipe Face Mesh initialization failed")
            return
        self.available = True

    def process(self, frame_bgr: np.ndarray) -> FaceObservation | None:
        if not self.available or self._face_mesh is None:
            return None
        try:
            import cv2

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self._face_mesh.process(rgb)
        except Exception:
            LOGGER.exception("MediaPipe Face Mesh inference failed")
            return None
        faces = getattr(results, "multi_face_landmarks", None)
        if not faces:
            return None
        face = faces[0]
        landmarks = np.asarray(
            [(point.x, point.y, point.z) for point in face.landmark],
            dtype=np.float64,
        )
        if landmarks.shape[0] < FACE_LANDMARK_COUNT:
            return None
        return analyze_face_landmarks(landmarks[:FACE_LANDMARK_COUNT])

    def close(self) -> None:
        face_mesh = self._face_mesh
        self._face_mesh = None
        self.available = False
        if face_mesh is not None and hasattr(face_mesh, "close"):
            face_mesh.close()
