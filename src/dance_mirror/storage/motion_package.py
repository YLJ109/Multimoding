"""Versioned JSON movement packages for reference-video results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from dance_mirror.domain.types import PoseSequence
from dance_mirror.errors import MotionFormatError

FORMAT_VERSION = 1


def save_motion_package(sequence: PoseSequence, path: str | Path) -> Path:
    """Write a pose sequence and its metadata to a UTF-8 JSON file."""
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "dance-mirror-motion",
        "version": FORMAT_VERSION,
        "schema": sequence.schema,
        "fps": sequence.fps,
        "timestamps_s": sequence.timestamps_s.tolist(),
        "keypoints": sequence.keypoints.tolist(),
        "scores": sequence.scores.tolist(),
        "metadata": dict(sequence.metadata),
    }
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return destination


def load_motion_package(path: str | Path) -> PoseSequence:
    """Load a versioned JSON movement package with strict validation."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise MotionFormatError(f"motion package does not exist: {source}")
    try:
        with source.open("r", encoding="utf-8") as handle:
            payload: dict[str, Any] = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MotionFormatError(f"cannot read motion package: {source}") from exc
    if payload.get("format") != "dance-mirror-motion":
        raise MotionFormatError("unrecognized motion package format")
    if int(payload.get("version", 0)) != FORMAT_VERSION:
        raise MotionFormatError(
            f"unsupported motion package version: {payload.get('version')}"
        )
    try:
        return PoseSequence(
            keypoints=np.asarray(payload["keypoints"], dtype=np.float64),
            scores=np.asarray(payload["scores"], dtype=np.float64),
            timestamps_s=np.asarray(payload["timestamps_s"], dtype=np.float64),
            fps=float(payload["fps"]),
            schema=str(payload.get("schema", "coco17")),
            metadata=dict(payload.get("metadata", {})),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MotionFormatError("motion package contains invalid pose arrays") from exc
