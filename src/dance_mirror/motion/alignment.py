"""Dynamic time warping for offline and bounded real-time alignment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dance_mirror.motion.features import FeatureSequence

FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class AlignmentResult:
    """A monotonic mapping from user frames to reference frames."""

    path: list[tuple[int, int]]
    cost: float
    normalized_cost: float
    reference_indices: NDArray[np.int64]
    user_indices: NDArray[np.int64]


def _distance(first: FloatArray, second: FloatArray) -> float:
    valid = np.isfinite(first) & np.isfinite(second)
    if not np.any(valid):
        return 1.0
    difference = np.abs(first[valid] - second[valid])
    return float(np.mean(np.minimum(difference, 3.0)))


def dtw_align(
    reference: FeatureSequence,
    user: FeatureSequence,
    *,
    max_cost: float = 3.0,
    band: int | None = None,
) -> AlignmentResult:
    """Align two feature sequences with a Sakoe-Chiba band when requested.

    The returned path contains ``(reference_index, user_index)`` pairs and is
    strictly monotonic.  ``band=None`` performs full DTW; a positive band is
    useful for the bounded live-training window.
    """
    reference_values = np.asarray(reference.values, dtype=np.float64)
    user_values = np.asarray(user.values, dtype=np.float64)
    reference_count = len(reference_values)
    user_count = len(user_values)
    if reference_count == 0 or user_count == 0:
        return AlignmentResult(
            path=[],
            cost=0.0,
            normalized_cost=0.0,
            reference_indices=np.zeros(0, dtype=np.int64),
            user_indices=np.zeros(0, dtype=np.int64),
        )
    if reference_values.shape[1] != user_values.shape[1]:
        raise ValueError("reference and user feature widths must match")
    if band is not None and band < 0:
        raise ValueError("band must be non-negative or None")

    costs = np.full((reference_count + 1, user_count + 1), np.inf, dtype=np.float64)
    costs[0, 0] = 0.0
    for i in range(1, reference_count + 1):
        lower = 1 if band is None else max(1, i - band)
        upper = user_count if band is None else min(user_count, i + band)
        for j in range(lower, upper + 1):
            local = min(
                _distance(reference_values[i - 1], user_values[j - 1]),
                max_cost,
            )
            costs[i, j] = local + min(
                costs[i - 1, j],
                costs[i, j - 1],
                costs[i - 1, j - 1],
            )

    i, j = reference_count, user_count
    if not np.isfinite(costs[i, j]):
        # A narrow band can exclude the corner for inputs with very different
        # lengths.  Retry once without a band instead of returning a false map.
        if band is not None:
            return dtw_align(reference, user, max_cost=max_cost, band=None)
        return AlignmentResult(
            path=[],
            cost=float("inf"),
            normalized_cost=float("inf"),
            reference_indices=np.zeros(0, dtype=np.int64),
            user_indices=np.zeros(0, dtype=np.int64),
        )

    path: list[tuple[int, int]] = []
    while i > 0 or j > 0:
        path.append((i - 1, j - 1))
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            previous = min(
                costs[i - 1, j],
                costs[i, j - 1],
                costs[i - 1, j - 1],
            )
            if previous == costs[i - 1, j - 1]:
                i -= 1
                j -= 1
            elif previous == costs[i - 1, j]:
                i -= 1
            else:
                j -= 1
    path.reverse()
    reference_indices = np.asarray([item[0] for item in path], dtype=np.int64)
    user_indices = np.asarray([item[1] for item in path], dtype=np.int64)
    total_cost = float(costs[reference_count, user_count])
    return AlignmentResult(
        path=path,
        cost=total_cost,
        normalized_cost=total_cost / max(len(path), 1),
        reference_indices=reference_indices,
        user_indices=user_indices,
    )


def best_reference_index(
    alignment: AlignmentResult,
    user_index: int,
    *,
    max_distance: int = 2,
) -> int | None:
    """Return the reference frame aligned to a user frame when available."""
    if not alignment.path:
        return None
    differences = np.abs(alignment.user_indices - user_index)
    candidate = int(np.argmin(differences))
    if int(differences[candidate]) > max_distance:
        return None
    return int(alignment.reference_indices[candidate])
