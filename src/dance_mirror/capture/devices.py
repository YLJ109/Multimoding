"""Camera discovery helpers shared by settings and stage dialogs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraDevice:
    """One selectable camera index and its human-readable device name."""

    index: int
    name: str

    @property
    def label(self) -> str:
        clean_name = self.name.strip() or "未命名摄像头"
        return f"{self.index} - {clean_name}"


def list_camera_devices() -> tuple[CameraDevice, ...]:
    """Return cameras exposed by Qt multimedia, with a safe OpenCV fallback."""
    devices: list[CameraDevice] = []
    try:
        from PyQt6.QtMultimedia import QMediaDevices

        for index, device in enumerate(QMediaDevices.videoInputs()):
            name = str(device.description() or "").strip() or f"摄像头 {index}"
            devices.append(CameraDevice(index=index, name=name))
    except (ImportError, RuntimeError):
        devices = []
    if devices:
        return tuple(devices)
    return (CameraDevice(index=0, name="OpenCV 默认摄像头"),)
