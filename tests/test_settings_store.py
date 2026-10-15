"""Unit tests for the UI-independent settings snapshot/persist mapping.

``SettingsStore`` only depends on a ``Settings``-like facade (get_str/get_int/
get_bool/set_*), so these tests run headless with a dict-backed mock and never
touch ``QSettings`` or ``QApplication``.
"""

from __future__ import annotations

from pathlib import Path

from dance_mirror.view.settings_store import SettingsStore


class _MockSettings:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def get_str(self, key: str, default: str = "") -> str:
        return str(self.data.get(key, default))

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self.data.get(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        return bool(self.data.get(key, default))

    def set_str(self, key: str, value: object) -> None:
        self.data[key] = str(value)

    def set_int(self, key: str, value: object) -> None:
        self.data[key] = int(value)

    def set_bool(self, key: str, value: object) -> None:
        self.data[key] = bool(value)


class _MockSession:
    llm_base_url = "https://api.example.com/v1"
    key = "sess-key"
    llm_model = "gpt-test"
    asr_base_url = "https://asr.example.com/v1"
    asr_model = "whisper-test"
    tts_model = "tts-test"
    tts_base_url = "https://tts.example.com/v1"
    tts_voice = "nova"


def _snapshot(settings: _MockSettings) -> dict:
    return SettingsStore.snapshot(
        settings,
        session_provider=_MockSession(),
        models_dir=Path("/models"),
        root_motion_none_value="none",
    )


def test_snapshot_reads_sensible_defaults_from_empty_storage() -> None:
    snap = _snapshot(_MockSettings())

    assert snap["appearance_theme"] == "dark"
    assert snap["target_fps"] == 15.0
    assert snap["latency_alpha"] == 0.2
    assert snap["imitation_smoothing"] == 0.45
    assert snap["cloud_base_url"] == "https://api.example.com/v1"
    assert snap["cloud_model"] == "gpt-test"
    assert snap["pose_model_path"] == str(Path("/models") / "yolo11n-pose.pt")


def test_roundtrip_is_stable() -> None:
    settings = _MockSettings()
    snap1 = _snapshot(settings)
    SettingsStore.persist(settings, snap1)
    snap2 = _snapshot(settings)

    for key in snap1:
        assert snap1[key] == snap2[key], key


def test_persist_writes_every_mapped_key() -> None:
    settings = _MockSettings()
    snap = _snapshot(settings)
    SettingsStore.persist(settings, snap)

    expected_keys = {
        "cloud/base_url", "cloud/provider", "cloud/model", "cloud/timeout_s",
        "asr/base_url", "asr/model", "asr/language", "asr/enabled",
        "tts/enabled", "tts/backend", "tts/base_url", "tts/model", "tts/voice",
        "tts/timeout_s", "vision/model_path", "vision/device",
        "training/target_fps", "appearance/theme", "window/fullscreen_on_start",
        "camera/index", "camera/name", "camera/width", "camera/height",
        "camera/overlay_body", "camera/overlay_face", "camera/overlay_hands",
        "camera/overlay_bbox", "camera/overlay_hud", "camera/overlay_labels",
        "training/mirror_user", "training/record_enabled", "training/privacy_shield",
        "renderer/model_mode", "renderer/motion_preset", "robot/character_id",
        "robot/model_path", "renderer/target_fps", "renderer/pending_timeout_ms",
        "camera/preview_size", "camera/reference_view", "camera/user_view",
        "training/user_offset_ms", "training/capture_latency_alpha",
        "motion/root_mode", "renderer/low_power", "robot/skin", "robot/scene_theme",
        "robot/imitation_scope", "robot/imitation_smoothing",
    }
    assert expected_keys <= set(settings.data.keys())


def test_as_float_falls_back_on_garbage() -> None:
    settings = _MockSettings()
    settings.set_str("cloud/timeout_s", "not-a-number")
    snap = _snapshot(settings)
    # Garbage is coerced to the default 30.0 rather than raising
    assert snap["cloud_timeout_s"] == 30.0


def test_pose_model_path_uses_default_when_unconfigured() -> None:
    settings = _MockSettings()
    assert SettingsStore.pose_model_path(settings, Path("/m")) == str(
        Path("/m") / "yolo11n-pose.pt"
    )


def test_pose_model_path_returns_explicit_configured_path() -> None:
    settings = _MockSettings()
    settings.set_str("vision/model_path", "/custom/model.pt")
    assert SettingsStore.pose_model_path(settings, Path("/m")) == "/custom/model.pt"


def test_pose_model_path_uses_default_for_bare_filename() -> None:
    settings = _MockSettings()
    settings.set_str("vision/model_path", "yolo11n-pose.pt")
    assert SettingsStore.pose_model_path(settings, Path("/m")) == str(
        Path("/m") / "yolo11n-pose.pt"
    )
