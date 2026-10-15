"""Temporal smoothing and short-gap repair."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


def fill_short_gaps(
    values: Array,
    scores: Array,
    *,
    min_confidence: float = 0.2,
    max_gap: int = 8,
) -> tuple[Array, Array]:
    """Linearly interpolate short missing runs and mark repaired points as valid."""
    repaired = np.array(values, dtype=np.float64, copy=True)
    repaired_scores = np.array(scores, dtype=np.float64, copy=True)
    valid = repaired_scores >= min_confidence

    for joint in range(repaired.shape[1]):
        valid_indices = np.flatnonzero(valid[:, joint])
        if len(valid_indices) < 2:
            continue
        for left, right in zip(valid_indices[:-1], valid_indices[1:], strict=False):
            gap = int(right - left - 1)
            if gap <= 0 or gap > max_gap:
                continue
            alpha = np.linspace(0.0, 1.0, gap + 2)[1:-1, None]
            start = repaired[left, joint]
            end = repaired[right, joint]
            repaired[left + 1 : right, joint] = start + alpha * (end - start)
            repaired_scores[left + 1 : right, joint] = np.minimum(
                repaired_scores[left, joint], repaired_scores[right, joint]
            )
            valid[left + 1 : right, joint] = True

    return repaired, repaired_scores


def exponential_smooth(
    values: Array,
    scores: Array,
    *,
    alpha: float = 0.35,
    min_confidence: float = 0.2,
) -> Array:
    """Apply a lightweight confidence-aware exponential filter."""
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in the interval (0, 1]")
    output = np.array(values, dtype=np.float64, copy=True)
    smoothed = output[0].copy()
    for index in range(1, len(output)):
        current = output[index]
        valid = scores[index] >= min_confidence
        smoothed[valid] = alpha * current[valid] + (1.0 - alpha) * smoothed[valid]
        output[index, valid] = smoothed[valid]
    return output


def one_euro_smooth(
    values: Array,
    scores: Array,
    *,
    frequency: float,
    min_cutoff: float = 1.0,
    beta: float = 0.05,
    derivative_cutoff: float = 1.0,
    min_confidence: float = 0.2,
) -> Array:
    """Apply the One Euro filter independently to every coordinate."""
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    output = np.array(values, dtype=np.float64, copy=True)
    time_delta = 1.0 / frequency

    def alpha(cutoff: float) -> float:
        tau = 1.0 / (2.0 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / time_delta)

    previous = output[0].copy()
    previous_derivative = np.zeros_like(previous)
    for index in range(1, len(output)):
        current = output[index]
        valid = scores[index] >= min_confidence
        derivative = (current - previous) / time_delta
        derivative_alpha = alpha(derivative_cutoff)
        filtered_derivative = derivative_alpha * derivative + (
            1.0 - derivative_alpha
        ) * previous_derivative
        cutoff = min_cutoff + beta * np.abs(filtered_derivative)
        data_alpha = 1.0 / (1.0 + (1.0 / (2.0 * np.pi * cutoff)) / time_delta)
        filtered = data_alpha * current + (1.0 - data_alpha) * previous
        output[index, valid] = filtered[valid]
        previous[valid] = filtered[valid]
        previous_derivative[valid] = filtered_derivative[valid]
    return output
