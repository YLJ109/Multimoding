"""Curated replaceable 3D characters with explicit licensing metadata."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dance_mirror.renderer.three_scene import ROBOT_MODEL_LOCAL_FILE

MAX_GLB_BYTES = 50 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True)
class CharacterPreset:
    """One curated character that can be downloaded and cached locally."""

    key: str
    name: str
    summary: str
    license_name: str
    license_url: str
    source_url: str
    model_url: str = ""
    preview_url: str = ""
    author: str = ""
    bundled_path: Path | None = None

    @property
    def is_bundled(self) -> bool:
        return self.bundled_path is not None

    @property
    def is_downloadable(self) -> bool:
        return bool(self.model_url)

    @property
    def filename(self) -> str:
        return f"{self.key}.glb"


CHARACTER_PRESETS: tuple[CharacterPreset, ...] = (
    CharacterPreset(
        key="humanoid_adult",
        name="星轨赛博人形",
        summary="内置成人比例赛博机甲，全身骨骼与 Idle、Walk、Run、Wave 等动画；手掌 21 点实时叠加。",
        license_name="CC0 1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        source_url=(
            "https://quaternius.com/packs/animatedcyberpunk.html"
        ),
        author="Quaternius",
        bundled_path=ROBOT_MODEL_LOCAL_FILE,
    ),
    CharacterPreset(
        key="rigged_figure",
        name="Rigged Figure",
        summary="轻量标准类人骨架，骨骼少、显存占用低，适合 3060 6GB。",
        license_name="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        source_url=(
            "https://github.com/KhronosGroup/glTF-Sample-Assets/"
            "tree/main/Models/RiggedFigure"
        ),
        model_url=(
            "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/"
            "main/Models/RiggedFigure/glTF-Binary/RiggedFigure.glb"
        ),
        preview_url=(
            "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/"
            "main/Models/RiggedFigure/screenshot/screenshot.gif"
        ),
        author="Cesium",
    ),
)


def character_preset(key: str) -> CharacterPreset:
    """Return one preset, falling back to the bundled character."""
    normalized = str(key or "").strip().lower()
    if normalized in {"", "robot_expressive", "cesium_man"}:
        return CHARACTER_PRESETS[0]
    for preset in CHARACTER_PRESETS:
        if preset.key == normalized:
            return preset
    return CHARACTER_PRESETS[0]


def validate_glb(path: Path, *, max_bytes: int = MAX_GLB_BYTES) -> Path:
    """Validate a GLB file without parsing untrusted scene content."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"GLB file does not exist: {resolved}")
    if resolved.suffix.lower() != ".glb":
        raise ValueError("only .glb character files are supported")
    size = resolved.stat().st_size
    if size < 20:
        raise ValueError("GLB file is empty or truncated")
    if size > max_bytes:
        raise ValueError(f"GLB file exceeds {max_bytes // (1024 * 1024)} MB")
    with resolved.open("rb") as handle:
        if handle.read(4) != b"glTF":
            raise ValueError("file is not a valid binary glTF asset")
    return resolved


class CharacterStore:
    """Resolve bundled/custom characters and cache curated downloads."""

    def __init__(self, root: Path, *, max_bytes: int = MAX_GLB_BYTES) -> None:
        self.root = Path(root).expanduser().resolve()
        self.max_bytes = max(1024 * 1024, int(max_bytes))

    def installed_path(self, key: str) -> Path | None:
        preset = character_preset(key)
        if preset.is_bundled:
            bundled = preset.bundled_path
            if bundled is not None and bundled.is_file():
                return bundled.resolve()
            return None
        candidate = self.root / preset.filename
        if candidate.is_file():
            try:
                return validate_glb(candidate, max_bytes=self.max_bytes)
            except (OSError, ValueError):
                return None
        return None

    def resolve(self, key: str, custom_path: str = "") -> Path | None:
        """Resolve a custom path first, then the selected curated character."""
        raw_custom = str(custom_path or "").strip()
        if raw_custom:
            try:
                return validate_glb(Path(raw_custom), max_bytes=self.max_bytes)
            except (OSError, ValueError):
                return None
        return self.installed_path(key)

    def download(
        self,
        key: str,
        *,
        progress: Callable[[int], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Path:
        """Download one curated GLB atomically and return its cached path."""
        preset = character_preset(key)
        if preset.is_bundled:
            if preset.bundled_path is None or not preset.bundled_path.is_file():
                raise FileNotFoundError("bundled character is unavailable")
            return preset.bundled_path.resolve()
        if not preset.model_url:
            raise ValueError("selected character has no download source")

        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / preset.filename
        if destination.is_file():
            return validate_glb(destination, max_bytes=self.max_bytes)

        temporary = destination.with_name(f".{destination.stem}.part.glb")
        temporary.unlink(missing_ok=True)
        request = urllib.request.Request(
            preset.model_url,
            headers={"User-Agent": "DanceMirror/0.2 character-downloader"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                declared_size = int(response.headers.get("Content-Length", "0") or "0")
                if declared_size > self.max_bytes:
                    raise ValueError("remote GLB exceeds the configured size limit")
                total = 0
                with temporary.open("wb") as handle:
                    while True:
                        if should_stop is not None and should_stop():
                            raise InterruptedError("character download cancelled")
                        chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise ValueError("remote GLB exceeds the configured size limit")
                        handle.write(chunk)
                        if progress is not None and declared_size > 0:
                            progress(min(99, round(total * 100 / declared_size)))
            validate_glb(temporary, max_bytes=self.max_bytes)
            os.replace(temporary, destination)
            if progress is not None:
                progress(100)
            return destination.resolve()
        except (OSError, urllib.error.URLError, ValueError, InterruptedError):
            temporary.unlink(missing_ok=True)
            raise
