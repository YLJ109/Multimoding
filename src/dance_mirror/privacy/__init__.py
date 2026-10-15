"""Privacy helpers for multi-person camera scenes.

The primary dancer is kept visible; other detected people are blurred before a
frame can be written to an optional local recording.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class PrivacyConfig:
    """Controls local-only masking for additional people."""

    blur_kernel_divisor: int = 12
    min_blur_kernel: int = 15
    max_blur_kernel: int = 151


def _clip_box(box: FloatArray, width: int, height: int) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(float(box[0])))))
    y1 = max(0, min(height - 1, int(round(float(box[1])))))
    x2 = max(x1 + 1, min(width, int(round(float(box[2])))))
    y2 = max(y1 + 1, min(height, int(round(float(box[3])))))
    return x1, y1, x2, y2


def blur_other_people(
    frame: NDArray[np.uint8],
    boxes: FloatArray | None,
    *,
    primary_index: int,
    config: PrivacyConfig | None = None,
) -> NDArray[np.uint8]:
    """Return a copy with every non-primary person region blurred."""
    settings = config or PrivacyConfig()
    output = np.ascontiguousarray(frame).copy()
    if boxes is None or len(boxes) <= 1:
        return output
    try:
        import cv2
    except ImportError:
        return output

    height, width = output.shape[:2]
    for index, box in enumerate(np.asarray(boxes, dtype=np.float64)):
        if index == primary_index:
            continue
        x1, y1, x2, y2 = _clip_box(box, width, height)
        width_px = x2 - x1
        height_px = y2 - y1
        if width_px < 8 or height_px < 8:
            continue
        kernel = int(max(width_px, height_px) / settings.blur_kernel_divisor)
        kernel = max(settings.min_blur_kernel, min(settings.max_blur_kernel, kernel))
        if kernel % 2 == 0:
            kernel += 1
        region = output[y1:y2, x1:x2]
        output[y1:y2, x1:x2] = cv2.GaussianBlur(
            region,
            (kernel, kernel),
            sigmaX=0,
        )
    return output
