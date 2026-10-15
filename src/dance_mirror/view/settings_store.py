"""Persistent settings snapshot/persist mapping.

Extracted from ``MainWindow`` so the 50+ key dictionary <-> QSettings mapping
lives in one testable, UI-independent place.  The mapping is intentionally flat:
``snapshot`` reads every key from a ``Settings`` facade, ``persist`` writes them
back.  ``MainWindow`` only forwards its ``Settings`` instance, the active session
provider (for default values), and the models directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SettingsStore:
    """Bidirectional bridge between the in-memory settings dict and storage."""

    @staticmethod
    def _as_float(settings: Any, key: str, default: float) -> float:
        try:
            return float(settings.get_str(key, str(default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def pose_model_path(settings: Any, models_dir: Path, default_filename: str = "yolo11n-pose.pt") -> str:
        """Resolve the local pose model path, defaulting inside ``models_dir``."""
        default_path = str(Path(models_dir) / default_filename)
        configured = settings.get_str("vision/model_path", default_path)
        if configured in {"", default_filename}:
            return default_path
        return configured

    @staticmethod
    def snapshot(
        settings: Any,
        *,
        session_provider: Any,
        models_dir: Path,
        root_motion_none_value: str,
    ) -> dict[str, Any]:
        """Read every persisted setting into the in-memory dict representation."""
        s = settings
        return {
            "appearance_theme": s.get_str("appearance/theme", "dark"),
            "fullscreen_on_start": s.get_bool("window/fullscreen_on_start", False),
            "cloud_base_url": s.get_str(
                "cloud/base_url", session_provider.llm_base_url or "https://api.openai.com/v1"
            ),
            "provider_key": s.get_str("cloud/provider", session_provider.key),
            "cloud_model": s.get_str(
                "cloud/model", session_provider.llm_model or "gpt-4o-mini"
            ),
            "cloud_timeout_s": SettingsStore._as_float(s, "cloud/timeout_s", 30.0),
            "asr_base_url": s.get_str(
                "asr/base_url", session_provider.asr_base_url or "https://api.openai.com/v1"
            ),
            "asr_model": s.get_str(
                "asr/model", session_provider.asr_model or "whisper-1"
            ),
            "asr_language": s.get_str("asr/language", "zh"),
            "asr_enabled": s.get_bool("asr/enabled", bool(session_provider.asr_model)),
            "tts_enabled": s.get_bool("tts/enabled", True),
            "tts_backend": s.get_str(
                "tts/backend", "cloud" if session_provider.tts_model else "local"
            ),
            "tts_base_url": s.get_str(
                "tts/base_url", session_provider.tts_base_url or "https://api.openai.com/v1"
            ),
            "tts_model": s.get_str(
                "tts/model", session_provider.tts_model or "gpt-4o-mini-tts"
            ),
            "tts_voice": s.get_str(
                "tts/voice", session_provider.tts_voice or "alloy"
            ),
            "tts_timeout_s": SettingsStore._as_float(s, "tts/timeout_s", 30.0),
            "pose_model_path": SettingsStore.pose_model_path(s, models_dir),
            "device": s.get_str("vision/device", "cuda:0"),
            "target_fps": SettingsStore._as_float(s, "training/target_fps", 15.0),
            "camera_width": s.get_int("camera/width", 1280),
            "camera_index": s.get_int("camera/index", 0),
            "camera_name": s.get_str("camera/name", ""),
            "camera_height": s.get_int("camera/height", 720),
            "overlay_body": s.get_bool("camera/overlay_body", True),
            "overlay_face": s.get_bool("camera/overlay_face", True),
            "overlay_hands": s.get_bool("camera/overlay_hands", True),
            "overlay_bbox": s.get_bool("camera/overlay_bbox", True),
            "overlay_hud": s.get_bool("camera/overlay_hud", True),
            "overlay_labels": s.get_bool("camera/overlay_labels", True),
            "mirror_user": s.get_bool("training/mirror_user", True),
            "record_enabled": s.get_bool("training/record_enabled", False),
            "privacy_shield": s.get_bool("training/privacy_shield", True),
            "model_mode": s.get_str("renderer/model_mode", "overlay"),
            "character_id": s.get_str("robot/character_id", "humanoid_adult"),
            "motion_preset": s.get_str("renderer/motion_preset", "balanced"),
            "robot_model_path": s.get_str("robot/model_path", ""),
            "render_fps": s.get_int("renderer/target_fps", 45),
            "pending_timeout_ms": s.get_int("renderer/pending_timeout_ms", 300),
            "camera_preview_size": s.get_str("camera/preview_size", "medium"),
            "reference_view": s.get_str("camera/reference_view", "front"),
            "user_view": s.get_str("camera/user_view", "front"),
            "user_offset_ms": s.get_int("training/user_offset_ms", 0),
            "latency_alpha": SettingsStore._as_float(s, "training/capture_latency_alpha", 0.2),
            "root_mode": s.get_str("motion/root_mode", root_motion_none_value),
            "low_power": s.get_bool("renderer/low_power", True),
            "skin": s.get_str("robot/skin", "default"),
            "scene_theme": s.get_str("robot/scene_theme", "studio"),
            "imitation_scope": s.get_str("robot/imitation_scope", "full_body"),
            "imitation_smoothing": SettingsStore._as_float(s, "robot/imitation_smoothing", 0.45),
        }

    @staticmethod
    def persist(settings: Any, values: dict[str, Any]) -> None:
        """Write the in-memory settings dict back to persistent storage."""
        pairs = {
            "cloud/base_url": values["cloud_base_url"],
            "cloud/provider": values.get("provider_key", "custom"),
            "cloud/model": values["cloud_model"],
            "cloud/timeout_s": values["cloud_timeout_s"],
            "asr/base_url": values["asr_base_url"],
            "asr/model": values["asr_model"],
            "asr/language": values["asr_language"],
            "asr/enabled": values["asr_enabled"],
            "tts/enabled": values["tts_enabled"],
            "tts/backend": values["tts_backend"],
            "tts/base_url": values["tts_base_url"],
            "tts/model": values["tts_model"],
            "tts/voice": values["tts_voice"],
            "tts/timeout_s": values["tts_timeout_s"],
            "vision/model_path": values["pose_model_path"],
            "vision/device": values["device"],
            "training/target_fps": values["target_fps"],
            "appearance/theme": values["appearance_theme"],
            "window/fullscreen_on_start": values["fullscreen_on_start"],
            "camera/index": values["camera_index"],
            "camera/name": values.get("camera_name", ""),
            "camera/width": values["camera_width"],
            "camera/height": values["camera_height"],
            "camera/overlay_body": values["overlay_body"],
            "camera/overlay_face": values["overlay_face"],
            "camera/overlay_hands": values["overlay_hands"],
            "camera/overlay_bbox": values["overlay_bbox"],
            "camera/overlay_hud": values["overlay_hud"],
            "camera/overlay_labels": values["overlay_labels"],
            "training/mirror_user": values["mirror_user"],
            "training/record_enabled": values["record_enabled"],
            "training/privacy_shield": values["privacy_shield"],
            "renderer/model_mode": values["model_mode"],
            "renderer/motion_preset": values["motion_preset"],
            "robot/character_id": values["character_id"],
            "robot/model_path": values["robot_model_path"],
            "renderer/target_fps": values["render_fps"],
            "renderer/pending_timeout_ms": values["pending_timeout_ms"],
            "camera/preview_size": values["camera_preview_size"],
            "camera/reference_view": values["reference_view"],
            "camera/user_view": values["user_view"],
            "training/user_offset_ms": values["user_offset_ms"],
            "training/capture_latency_alpha": values["latency_alpha"],
            "motion/root_mode": values["root_mode"],
            "renderer/low_power": values["low_power"],
            "robot/skin": values["skin"],
            "robot/scene_theme": values["scene_theme"],
            "robot/imitation_scope": values["imitation_scope"],
            "robot/imitation_smoothing": values["imitation_smoothing"],
        }
        for key, value in pairs.items():
            if isinstance(value, bool):
                settings.set_bool(key, value)
            elif isinstance(value, int):
                settings.set_int(key, value)
            else:
                settings.set_str(key, str(value))
