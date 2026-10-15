"""Validation and normalization for runtime settings snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class SettingsValidationIssue:
    """One user-visible settings problem."""

    field: str
    message: str
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class SettingsValidationResult:
    """Normalized settings plus all detected problems."""

    values: dict[str, Any]
    issues: tuple[SettingsValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def _bounded_int(
    values: dict[str, Any],
    key: str,
    *,
    minimum: int,
    maximum: int,
    fallback: int,
) -> None:
    try:
        value = int(values.get(key, fallback))
    except (TypeError, ValueError):
        value = fallback
    values[key] = max(minimum, min(maximum, value))


def _bounded_float(
    values: dict[str, Any],
    key: str,
    *,
    minimum: float,
    maximum: float,
    fallback: float,
) -> None:
    try:
        value = float(values.get(key, fallback))
    except (TypeError, ValueError):
        value = fallback
    values[key] = max(minimum, min(maximum, value))


def _valid_http_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_settings(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    allowed_model_modes: frozenset[str] = frozenset({"skeleton", "body", "overlay"}),
    allowed_root_modes: frozenset[str] = frozenset({"none", "sway", "planar"}),
) -> SettingsValidationResult:
    """Merge and normalize a settings update without applying side effects."""
    values = dict(current)
    for key in current:
        if key in incoming:
            values[key] = incoming[key]

    issues: list[SettingsValidationIssue] = []

    values["model_mode"] = str(values.get("model_mode", "overlay")).lower()
    if values["model_mode"] not in allowed_model_modes:
        issues.append(
            SettingsValidationIssue("model_mode", "3D 显示模式无效，已回退到叠加模式。")
        )
        values["model_mode"] = "overlay"

    values["root_mode"] = str(values.get("root_mode", "none")).lower()
    if values["root_mode"] not in allowed_root_modes:
        issues.append(
            SettingsValidationIssue("root_mode", "根运动模式无效，已回退到不移动。")
        )
        values["root_mode"] = "none"

    for key in ("cloud_base_url", "asr_base_url", "tts_base_url"):
        if key in values and str(values.get(key, "")).strip() and not _valid_http_url(
            values[key]
        ):
            issues.append(
                SettingsValidationIssue(key, "云端地址必须是 http 或 https 地址。")
            )

    for key, label in (
        ("target_fps", "目标帧率"),
        ("cloud_timeout_s", "语言模型超时"),
        ("tts_timeout_s", "语音合成超时"),
    ):
        if key in values:
            try:
                number = float(values[key])
            except (TypeError, ValueError):
                issues.append(SettingsValidationIssue(key, f"{label}必须是数字。"))
            else:
                if number <= 0:
                    issues.append(SettingsValidationIssue(key, f"{label}必须大于零。"))

    model_path = str(values.get("robot_model_path", "")).strip()
    if model_path:
        path = Path(model_path).expanduser()
        if not path.is_file():
            issues.append(
                SettingsValidationIssue("robot_model_path", "选择的本地 GLB 文件不存在。")
            )
            values["robot_model_path"] = ""
        elif path.suffix.lower() != ".glb":
            issues.append(
                SettingsValidationIssue("robot_model_path", "角色模型必须是 GLB 文件。")
            )
            values["robot_model_path"] = ""
        elif path.stat().st_size > 50 * 1024 * 1024:
            issues.append(
                SettingsValidationIssue("robot_model_path", "角色模型不能超过 50 MB。")
            )
            values["robot_model_path"] = ""

    _bounded_float(values, "target_fps", minimum=1.0, maximum=60.0, fallback=15.0)
    _bounded_int(values, "render_fps", minimum=30, maximum=60, fallback=45)
    _bounded_int(
        values,
        "pending_timeout_ms",
        minimum=100,
        maximum=1000,
        fallback=300,
    )
    _bounded_int(values, "camera_index", minimum=0, maximum=32, fallback=0)
    _bounded_int(values, "camera_width", minimum=320, maximum=3840, fallback=1280)
    _bounded_int(values, "camera_height", minimum=240, maximum=2160, fallback=720)
    _bounded_int(values, "user_offset_ms", minimum=0, maximum=300, fallback=0)
    _bounded_float(
        values,
        "latency_alpha",
        minimum=0.05,
        maximum=0.8,
        fallback=0.2,
    )
    _bounded_float(
        values,
        "imitation_smoothing",
        minimum=0.0,
        maximum=0.95,
        fallback=0.45,
    )
    _bounded_float(
        values,
        "cloud_timeout_s",
        minimum=3.0,
        maximum=120.0,
        fallback=30.0,
    )
    _bounded_float(
        values,
        "tts_timeout_s",
        minimum=3.0,
        maximum=120.0,
        fallback=30.0,
    )
    return SettingsValidationResult(values=values, issues=tuple(issues))
