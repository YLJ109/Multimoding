"""Tests for curated 3D character download and validation."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from dance_mirror.renderer.character_catalog import (
    CHARACTER_PRESETS,
    CharacterStore,
    character_preset,
    validate_glb,
)


def _minimal_glb() -> bytes:
    return b"glTF" + struct.pack("<II", 2, 20) + b"\x00" * 8


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_character_download_uses_glb_temp_file_and_applies(monkeypatch, tmp_path: Path) -> None:
    payload = _minimal_glb()
    monkeypatch.setattr(
        "dance_mirror.renderer.character_catalog.urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(payload),
    )
    store = CharacterStore(tmp_path)
    progress: list[int] = []

    path = store.download("rigged_figure", progress=progress.append)

    assert path == tmp_path / "rigged_figure.glb"
    assert path.read_bytes() == payload
    assert store.installed_path("rigged_figure") == path
    assert progress[-1] == 100
    assert not (tmp_path / ".rigged_figure.part.glb").exists()


def test_character_store_rejects_invalid_custom_glb(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.glb"
    invalid.write_bytes(b"not-a-valid-glb")
    store = CharacterStore(tmp_path / "cache")

    assert store.resolve("robot_expressive", str(invalid)) is None


def test_default_character_is_bundled_adult_humanoid() -> None:
    expected = CHARACTER_PRESETS[0]

    assert expected.key == "humanoid_adult"
    assert expected.bundled_path is not None
    for key in ("", "robot_expressive", "cesium_man", "unknown-character"):
        assert character_preset(key) is expected

    resolved = validate_glb(expected.bundled_path)
    assert resolved.name == "dance_robot_cyber.glb"
    assert resolved.read_bytes()[:4] == b"glTF"


def test_character_store_falls_back_to_bundled_character() -> None:
    store = CharacterStore(Path(".runtime-smoke") / "character-tests")

    resolved = store.resolve("unknown-character", "")

    assert resolved is not None
    assert resolved.suffix.lower() == ".glb"


def test_download_rejects_oversized_remote_asset(monkeypatch, tmp_path: Path) -> None:
    payload = b"glTF" + b"x" * (2 * 1024 * 1024)
    monkeypatch.setattr(
        "dance_mirror.renderer.character_catalog.urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(payload),
    )
    store = CharacterStore(tmp_path, max_bytes=1024 * 1024)

    with pytest.raises(ValueError, match="size limit"):
        store.download("rigged_figure")
