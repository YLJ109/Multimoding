"""Tests for settings validation and normalization."""

from __future__ import annotations

from pathlib import Path

from dance_mirror.view.settings_validation import validate_settings


def _base() -> dict[str, object]:
    return {
        "target_fps": 15.0,
        "render_fps": 45,
        "cloud_base_url": "https://api.example.com/v1",
        "cloud_timeout_s": 30.0,
        "camera_width": 1280,
        "camera_height": 720,
        "robot_model_path": "",
    }


def test_invalid_cloud_url_blocks_settings_application() -> None:
    result = validate_settings(_base(), {"cloud_base_url": "not-a-url"})
    assert not result.valid
    assert any(issue.field == "cloud_base_url" for issue in result.issues)


def test_numeric_values_are_bounded() -> None:
    result = validate_settings(
        _base(),
        {"target_fps": 120.0, "camera_width": 99999, "camera_height": 1},
    )
    assert result.valid
    assert result.values["target_fps"] == 60.0
    assert result.values["camera_width"] == 3840
    assert result.values["camera_height"] == 240


def test_missing_glb_is_rejected_and_cleared(tmp_path: Path) -> None:
    missing = tmp_path / "missing.glb"
    result = validate_settings(_base(), {"robot_model_path": str(missing)})
    assert not result.valid
    assert result.values["robot_model_path"] == ""
