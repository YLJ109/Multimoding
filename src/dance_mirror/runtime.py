"""Process-level runtime isolation helpers."""

from __future__ import annotations

import os
import site
import sys
import threading
from pathlib import Path

_IMPORT_LOCK = threading.RLock()
_STALE_MODULE_PREFIXES = ("mediapipe", "tensorflow")


def _same_path(first: str, second: str) -> bool:
    try:
        return Path(first).resolve() == Path(second).resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def isolate_mediapipe_runtime() -> tuple[str, ...]:
    """Keep user-site TensorFlow from contaminating the conda MediaPipe runtime.

    Some Windows Python installations expose a global user-site TensorFlow that
    was built for NumPy 1.x. MediaPipe imports TensorFlow only as an optional
    documentation helper, so the contaminated package can otherwise break the
    entire camera worker with errors such as ``audio_classifier is not defined``.
    """
    with _IMPORT_LOCK:
        os.environ["PYTHONNOUSERSITE"] = "1"
        user_sites = {
            value
            for value in (site.getusersitepackages(),)
            if isinstance(value, str) and value
        }
        removed: list[str] = []
        for entry in tuple(sys.path):
            if not entry:
                continue
            if any(_same_path(entry, user_site) for user_site in user_sites):
                if entry in sys.path:
                    sys.path.remove(entry)
                removed.append(entry)

        mediapipe_module = sys.modules.get("mediapipe")
        mediapipe_ready = bool(getattr(mediapipe_module, "solutions", None))
        for module_name in tuple(sys.modules):
            is_stale_target = any(
                module_name == prefix or module_name.startswith(f"{prefix}.")
                for prefix in _STALE_MODULE_PREFIXES
            )
            if not is_stale_target:
                continue
            if mediapipe_ready and (
                module_name == "mediapipe" or module_name.startswith("mediapipe.")
            ):
                continue
            sys.modules.pop(module_name, None)
        return tuple(removed)
