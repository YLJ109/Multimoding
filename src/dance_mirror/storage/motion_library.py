"""Versioned dance-package library and legacy motion migration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from dance_mirror.domain.quality import (
    MotionQualityLevel,
    MotionQualityProfile,
    assess_motion_quality,
)
from dance_mirror.domain.types import PoseSequence
from dance_mirror.errors import MotionFormatError
from dance_mirror.motion.comparison_space import CameraProfile, CameraView
from dance_mirror.storage.database import utc_timestamp
from dance_mirror.storage.motion_package import load_motion_package, save_motion_package

PACKAGE_FORMAT = "dance-mirror-dance-package"
PACKAGE_VERSION = 2
MANIFEST_NAME = "manifest.json"
MOTION_NAME = "motion.json"
GAMEPLAY_NAME = "gameplay.json"
BEATMAP_NAME = "beatmap.json"
QUALITY_NAME = "quality.json"
POSTER_NAME = "cover.jpg"
AUDIO_NAME = "music"
EXTRACTED_AUDIO_SUFFIX = ".mp3"

_SAFE_ID = re.compile(r"[^a-zA-Z0-9_-]+")


class DancePackageError(MotionFormatError):
    """Raised when a V2 dance package is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class GameplayMetadata:
    """Non-pose gameplay parameters persisted with a dance package."""

    bpm: float = 120.0
    difficulty: int = 3
    dance_type: str = "其他"
    tags: tuple[str, ...] = ()
    default_speed: float = 1.0
    music_title: str = ""
    music_license: str = "用户本地使用"
    notes: str = ""

    def __post_init__(self) -> None:
        if not np.isfinite(self.bpm) or not 30.0 <= self.bpm <= 300.0:
            raise ValueError("bpm must be between 30 and 300")
        if not 1 <= int(self.difficulty) <= 5:
            raise ValueError("difficulty must be between 1 and 5")
        if not np.isfinite(self.default_speed) or not 0.5 <= self.default_speed <= 2.0:
            raise ValueError("default_speed must be between 0.5 and 2.0")

    def as_dict(self) -> dict[str, object]:
        return {
            "bpm": float(self.bpm),
            "difficulty": int(self.difficulty),
            "dance_type": self.dance_type,
            "tags": list(self.tags),
            "default_speed": float(self.default_speed),
            "music_title": self.music_title,
            "music_license": self.music_license,
            "notes": self.notes,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> GameplayMetadata:
        data = raw or {}
        tags = data.get("tags", ())
        return cls(
            bpm=float(data.get("bpm", 120.0)),
            difficulty=int(data.get("difficulty", 3)),
            dance_type=str(data.get("dance_type", "其他")),
            tags=tuple(str(item) for item in tags) if isinstance(tags, list) else (),
            default_speed=float(data.get("default_speed", 1.0)),
            music_title=str(data.get("music_title", "")),
            music_license=str(data.get("music_license", "用户本地使用")),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True, slots=True)
class DancePackage:
    """One card-ready dance asset stored in the local library."""

    package_id: str
    name: str
    root: Path
    motion_path: Path
    poster_path: Path | None
    audio_path: Path | None
    duration_s: float
    fps: float
    frame_count: int
    quality: MotionQualityProfile
    gameplay: GameplayMetadata
    camera: CameraProfile
    source_video: str
    created_at: str
    updated_at: str
    tags: tuple[str, ...] = ()

    @property
    def quality_label(self) -> str:
        return self.quality.level.display_name

    @property
    def ready(self) -> bool:
        return self.frame_count > 0 and self.motion_path.is_file()

    @property
    def has_music(self) -> bool:
        return self.audio_path is not None and self.audio_path.is_file()

    @property
    def status_label(self) -> str:
        if not self.ready:
            return "损坏"
        if not self.has_music:
            return "草稿：缺少音乐"
        return "可开始"


@dataclass(frozen=True, slots=True)
class TrashEntry:
    """One recoverable package currently stored in the local trash."""

    package: DancePackage
    trash_path: Path


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DancePackageError(f"cannot read package file: {path.name}") from exc
    if not isinstance(value, dict):
        raise DancePackageError(f"package file must contain an object: {path.name}")
    return value


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return "未命名舞蹈"
    return cleaned[:80]


def _safe_relative_file(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise DancePackageError("package asset path escapes its package directory")
    return candidate if candidate.is_file() else None


def _quality_from_manifest(raw: Mapping[str, Any]) -> MotionQualityProfile:
    quality = MotionQualityProfile.from_metadata({"quality": dict(raw)})
    return quality or MotionQualityProfile.for_level(MotionQualityLevel.RELATIVE_3D)


def _camera_from_manifest(raw: Mapping[str, Any] | None) -> CameraProfile:
    if not raw:
        return CameraProfile(view=CameraView.UNKNOWN)
    try:
        return CameraProfile.from_metadata({"camera_profile": dict(raw)})
    except (TypeError, ValueError):
        return CameraProfile(view=CameraView.UNKNOWN)


def select_video_poster(video_path: str | Path, output_path: str | Path) -> Path | None:
    """Choose the sharpest sampled frame and save a card cover.

    The operation is deliberately small and synchronous. Callers should run it
    in the video-analysis worker, never on the Qt main thread.
    """
    source = Path(video_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if not source.is_file():
        return None
    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        return None
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count <= 0:
            return None
        indices = np.linspace(0, max(0, frame_count - 1), num=7, dtype=np.int64)
        best_frame = None
        best_score = float("-inf")
        for index in np.unique(indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            brightness = float(np.mean(gray))
            balance = 1.0 - min(abs(brightness - 128.0) / 128.0, 1.0)
            score = sharpness + balance * 250.0
            if score > best_score:
                best_score = score
                best_frame = frame
        if best_frame is None:
            return None
        height, width = best_frame.shape[:2]
        if width > 960:
            scale = 960.0 / width
            best_frame = cv2.resize(
                best_frame,
                (960, max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), best_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88]):
            return None
        return destination
    finally:
        capture.release()


def _ffmpeg_executable() -> str | None:
    configured = os.environ.get("DANCE_MIRROR_FFMPEG", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
    return shutil.which("ffmpeg")


def extract_video_audio(
    video_path: str | Path,
    output_path: str | Path,
    *,
    ffmpeg_path: str | Path | None = None,
) -> bool:
    """Extract the first audio stream from a video into a compact MP3 file."""
    source = Path(video_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if not source.is_file():
        raise DancePackageError(f"video file does not exist: {source}")
    executable = (
        str(Path(ffmpeg_path).expanduser().resolve())
        if ffmpeg_path
        else _ffmpeg_executable()
    )
    if not executable:
        raise DancePackageError(
            "FFmpeg was not found; set DANCE_MIRROR_FFMPEG or add ffmpeg to PATH"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    command = [
        executable,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-map",
        "0:a:0",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(destination),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size <= 0:
        destination.unlink(missing_ok=True)
        return False
    return True


def build_beatmap(
    *,
    duration_s: float,
    fps: float,
    bpm: float,
    default_speed: float = 1.0,
    difficulty: int = 3,
) -> dict[str, object]:
    """Create a deterministic beat grid until offline audio analysis is added."""
    safe_duration = max(0.0, float(duration_s))
    beat_s = 60.0 / float(bpm)
    count = max(1, int(np.floor(safe_duration / beat_s)) + 1)
    beats = np.arange(count, dtype=np.float64) * beat_s
    beats = beats[beats <= safe_duration + 1e-6]
    accent_every = 4
    beat_items = [
        {
            "time_s": round(float(value), 6),
            "frame": min(max(0, int(round(value * fps))), max(0, int(safe_duration * fps))),
            "accent": bool(index % accent_every == 0),
            "section": int(index // 16) + 1,
        }
        for index, value in enumerate(beats)
    ]
    cues: list[dict[str, object]] = []
    for index in range(0, len(beat_items), 8):
        beat = beat_items[index]
        cues.append(
            {
                "time_s": beat["time_s"],
                "frame": beat["frame"],
                "text": "注意下一组动作",
                "priority": 2,
            }
        )
    return {
        "format": "dance-mirror-beatmap",
        "version": 1,
        "bpm": float(bpm),
        "offset_s": 0.0,
        "speed": float(default_speed),
        "difficulty": int(difficulty),
        "beats": beat_items,
        "cues": cues,
    }


class MotionPackageLibrary:
    """Scan, create, load, rename and delete local V2 dance packages."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.trash = self.root / ".trash"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.trash.mkdir(parents=True, exist_ok=True)

    def create_from_sequence(
        self,
        sequence: PoseSequence,
        *,
        name: str,
        source_video: str = "",
        poster_source: str | Path | None = None,
        audio_source: str | Path | None = None,
        gameplay: GameplayMetadata | None = None,
        camera: CameraProfile | None = None,
        package_id: str | None = None,
    ) -> DancePackage:
        """Persist one analyzed sequence into an atomic package directory."""
        self.ensure()
        identifier = _SAFE_ID.sub("-", package_id or uuid4().hex).strip("-") or uuid4().hex
        final_root = self.root / identifier
        if final_root.exists():
            raise DancePackageError(f"dance package id already exists: {identifier}")

        temporary_root = Path(
            tempfile.mkdtemp(prefix=f".{identifier}.", dir=str(self.root))
        )
        timestamp = utc_timestamp()
        try:
            motion_path = temporary_root / MOTION_NAME
            save_motion_package(sequence, motion_path)
            quality = assess_motion_quality(sequence)
            gameplay_data = gameplay or GameplayMetadata()
            camera_data = camera or self._camera_from_sequence(sequence)
            audio_name: str | None = None
            if audio_source:
                source_audio = Path(audio_source).expanduser().resolve()
                if not source_audio.is_file():
                    raise DancePackageError(f"audio file does not exist: {source_audio}")
                audio_name = f"{AUDIO_NAME}{source_audio.suffix.lower() or '.bin'}"
                shutil.copy2(source_audio, temporary_root / audio_name)
                if not gameplay_data.music_title:
                    gameplay_data = replace(gameplay_data, music_title=source_audio.stem)
            elif source_video and Path(source_video).expanduser().is_file():
                extracted_name = f"{AUDIO_NAME}{EXTRACTED_AUDIO_SUFFIX}"
                if extract_video_audio(source_video, temporary_root / extracted_name):
                    audio_name = extracted_name
                    if not gameplay_data.music_title:
                        gameplay_data = replace(
                            gameplay_data,
                            music_title=Path(source_video).expanduser().stem,
                            music_license="歌舞蹈视频原声，用户本地使用",
                        )

            beatmap = build_beatmap(
                duration_s=sequence.duration_s,
                fps=sequence.fps,
                bpm=gameplay_data.bpm,
                default_speed=gameplay_data.default_speed,
                difficulty=gameplay_data.difficulty,
            )
            _atomic_json_write(temporary_root / GAMEPLAY_NAME, gameplay_data.as_dict())
            _atomic_json_write(temporary_root / BEATMAP_NAME, beatmap)
            _atomic_json_write(temporary_root / QUALITY_NAME, quality.as_metadata())

            poster_name: str | None = None
            if poster_source:
                source = Path(poster_source).expanduser().resolve()
                if source.is_file():
                    poster_name = POSTER_NAME
                    shutil.copy2(source, temporary_root / poster_name)
                elif Path(source_video).is_file() and select_video_poster(
                    source_video, temporary_root / POSTER_NAME
                ):
                    poster_name = POSTER_NAME
            elif source_video and select_video_poster(
                source_video, temporary_root / POSTER_NAME
            ):
                poster_name = POSTER_NAME


            manifest = {
                "format": PACKAGE_FORMAT,
                "version": PACKAGE_VERSION,
                "id": identifier,
                "name": _safe_name(name),
                "subtitle": "",
                "created_at": timestamp,
                "updated_at": timestamp,
                "source_video": source_video,
                "schema": sequence.schema,
                "fps": float(sequence.fps),
                "frame_count": len(sequence),
                "duration_s": float(sequence.duration_s),
                "motion_file": MOTION_NAME,
                "poster_file": poster_name,
                "audio_file": audio_name,
                "quality_file": QUALITY_NAME,
                "gameplay_file": GAMEPLAY_NAME,
                "beatmap_file": BEATMAP_NAME,
                "quality": quality.as_metadata(),
                "camera_profile": camera_data.as_metadata(),
                "license": {
                    "code": "local-user-content",
                    "motion": "user-provided",
                    "music": gameplay_data.music_license,
                },
            }
            _atomic_json_write(temporary_root / MANIFEST_NAME, manifest)
            os.replace(temporary_root, final_root)
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        return self._load_directory(final_root)

    def scan(self) -> list[DancePackage]:
        """Return valid packages and isolate damaged directories from the UI."""
        self.ensure()
        packages: list[DancePackage] = []
        for child in self.root.iterdir():
            if child.name.startswith(".") or not child.is_dir():
                continue
            try:
                packages.append(self._load_directory(child))
            except DancePackageError:
                continue
        packages.sort(key=lambda item: item.updated_at, reverse=True)
        return packages

    def load(self, package_id: str) -> DancePackage:
        identifier = _SAFE_ID.sub("-", package_id).strip("-")
        if identifier != package_id:
            raise DancePackageError("invalid dance package identifier")
        package = self._load_directory(self.root / identifier)
        if not package.ready:
            raise DancePackageError(f"dance package is incomplete: {package.name}")
        return package

    def load_motion(self, package: DancePackage | str) -> PoseSequence:
        item = self.load(package) if isinstance(package, str) else package
        sequence = load_motion_package(item.motion_path)
        sequence.metadata = {
            **dict(sequence.metadata),
            "package_id": item.package_id,
            "package_name": item.name,
            "quality": item.quality.as_metadata(),
            "quality_level": item.quality.level.value,
            "camera_profile": item.camera.as_metadata(),
        }
        return sequence

    def load_beatmap(self, package: DancePackage | str) -> dict[str, Any]:
        item = self.load(package) if isinstance(package, str) else package
        return _read_json(item.root / BEATMAP_NAME)

    def rename(self, package: DancePackage | str, name: str) -> DancePackage:
        item = self.load(package.root.name) if isinstance(package, DancePackage) else self.load(package)
        manifest_path = item.root / MANIFEST_NAME
        manifest = _read_json(manifest_path)
        manifest["name"] = _safe_name(name)
        manifest["updated_at"] = utc_timestamp()
        _atomic_json_write(manifest_path, manifest)
        return self._load_directory(item.root)

    def set_audio(
        self,
        package: DancePackage | str,
        audio_source: str | Path,
        *,
        music_title: str = "",
        music_license: str = "用户本地使用",
    ) -> DancePackage:
        item = self.load(package.root.name) if isinstance(package, DancePackage) else self.load(package)
        source = Path(audio_source).expanduser().resolve()
        if not source.is_file():
            raise DancePackageError(f"audio file does not exist: {source}")
        manifest_path = item.root / MANIFEST_NAME
        manifest = _read_json(manifest_path)
        old_name = str(manifest.get("audio_file", "") or "")
        filename = f"{AUDIO_NAME}{source.suffix.lower() or '.bin'}"
        destination = item.root / filename
        shutil.copy2(source, destination)
        if old_name and old_name != filename:
            (item.root / old_name).unlink(missing_ok=True)
        manifest["audio_file"] = filename
        manifest["updated_at"] = utc_timestamp()
        _atomic_json_write(manifest_path, manifest)

        gameplay_path = item.root / GAMEPLAY_NAME
        gameplay = _read_json(gameplay_path)
        gameplay["music_title"] = music_title or source.stem
        gameplay["music_license"] = music_license
        _atomic_json_write(gameplay_path, gameplay)
        return self._load_directory(item.root)

    def extract_audio_from_video(self, package: DancePackage | str) -> DancePackage:
        """Replace the package soundtrack with audio from its source video."""
        item = (
            self.load(package.root.name)
            if isinstance(package, DancePackage)
            else self.load(package)
        )
        source = Path(item.source_video).expanduser().resolve()
        if not source.is_file():
            raise DancePackageError("源视频文件不存在，无法重新提取音乐")
        temporary_audio = item.root / f".{AUDIO_NAME}-{uuid4().hex}{EXTRACTED_AUDIO_SUFFIX}"
        try:
            if not extract_video_audio(source, temporary_audio):
                raise DancePackageError("源视频没有可提取的音轨")
            return self.set_audio(
                item,
                temporary_audio,
                music_title=source.stem,
                music_license="舞蹈视频原声，用户本地使用",
            )
        finally:
            temporary_audio.unlink(missing_ok=True)

    def set_poster(self, package: DancePackage | str, poster_source: str | Path) -> DancePackage:
        item = self.load(package.root.name) if isinstance(package, DancePackage) else self.load(package)
        source = Path(poster_source).expanduser().resolve()
        if not source.is_file():
            raise DancePackageError(f"poster file does not exist: {source}")
        shutil.copy2(source, item.root / POSTER_NAME)
        manifest_path = item.root / MANIFEST_NAME
        manifest = _read_json(manifest_path)
        manifest["poster_file"] = POSTER_NAME
        manifest["updated_at"] = utc_timestamp()
        _atomic_json_write(manifest_path, manifest)
        return self._load_directory(item.root)

    def delete(self, package: DancePackage | str) -> Path:
        """Move a package to the local trash and return its trash path."""
        self.ensure()
        item = self.load(package.root.name) if isinstance(package, DancePackage) else self.load(package)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = self.trash / f"{item.package_id}-{stamp}"
        if destination.exists():
            destination = self.trash / f"{item.package_id}-{stamp}-{uuid4().hex[:6]}"
        os.replace(item.root, destination)
        return destination

    def restore(self, trash_path: str | Path) -> DancePackage:
        self.ensure()
        source = Path(trash_path).expanduser().resolve()
        if not source.is_relative_to(self.trash.resolve()) or not source.is_dir():
            raise DancePackageError("trash path is invalid")
        manifest = _read_json(source / MANIFEST_NAME)
        identifier = str(manifest.get("id", "")).strip()
        if not identifier or _SAFE_ID.sub("-", identifier).strip("-") != identifier:
            raise DancePackageError("trash package id is invalid")
        destination = self.root / identifier
        if destination.exists():
            raise DancePackageError("a package with the same id already exists")
        os.replace(source, destination)
        return self._load_directory(destination)

    def list_trash(self) -> list[TrashEntry]:
        """Return valid recoverable packages newest first."""
        self.ensure()
        entries: list[TrashEntry] = []
        for child in self.trash.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                package = self._load_directory(child)
            except DancePackageError:
                continue
            entries.append(TrashEntry(package=package, trash_path=child.resolve()))
        entries.sort(key=lambda item: item.package.updated_at, reverse=True)
        return entries

    def purge(self, trash_path: str | Path) -> None:
        """Permanently remove one validated trash directory."""
        source = self._validate_trash_path(trash_path)
        shutil.rmtree(source)

    def purge_all(self) -> int:
        """Permanently remove all valid trash entries and return the count."""
        removed = 0
        for entry in self.list_trash():
            self.purge(entry.trash_path)
            removed += 1
        return removed


    def migrate_legacy_json(
        self,
        source_path: str | Path,
        *,
        name: str | None = None,
        audio_source: str | Path | None = None,
    ) -> DancePackage:
        source = Path(source_path).expanduser().resolve()
        sequence = load_motion_package(source)
        return self.create_from_sequence(
            sequence,
            name=name or source.stem,
            source_video=str(sequence.metadata.get("source", "")),
            audio_source=audio_source,
            gameplay=GameplayMetadata(
                bpm=120.0,
                dance_type="迁移包",
                tags=("legacy",),
            ),
        )

    def _load_directory(self, root: Path) -> DancePackage:
        root = root.expanduser().resolve()
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise DancePackageError(f"manifest is missing: {root}")
        manifest = _read_json(manifest_path)
        if manifest.get("format") != PACKAGE_FORMAT:
            raise DancePackageError("unrecognized dance package format")
        if int(manifest.get("version", 0)) != PACKAGE_VERSION:
            raise DancePackageError(f"unsupported dance package version: {manifest.get('version')}")
        package_id = str(manifest.get("id", "")).strip()
        if not package_id or _SAFE_ID.sub("-", package_id).strip("-") != package_id:
            raise DancePackageError("dance package id is invalid")
        motion = _safe_relative_file(root, str(manifest.get("motion_file", MOTION_NAME)))
        if motion is None:
            raise DancePackageError("motion file is missing")
        poster = _safe_relative_file(root, str(manifest.get("poster_file") or ""))
        audio = _safe_relative_file(root, str(manifest.get("audio_file") or ""))
        gameplay_raw = _read_json(root / str(manifest.get("gameplay_file", GAMEPLAY_NAME)))
        quality_raw = _read_json(root / str(manifest.get("quality_file", QUALITY_NAME)))
        try:
            gameplay = GameplayMetadata.from_mapping(gameplay_raw)
            quality = _quality_from_manifest(quality_raw)
            camera = _camera_from_manifest(manifest.get("camera_profile"))
        except (TypeError, ValueError) as exc:
            raise DancePackageError("dance package metadata is invalid") from exc
        return DancePackage(
            package_id=package_id,
            name=_safe_name(str(manifest.get("name", "未命名舞蹈"))),
            root=root,
            motion_path=motion,
            poster_path=poster,
            audio_path=audio,
            duration_s=max(0.0, float(manifest.get("duration_s", 0.0))),
            fps=max(1.0, float(manifest.get("fps", 30.0))),
            frame_count=max(0, int(manifest.get("frame_count", 0))),
            quality=quality,
            gameplay=gameplay,
            camera=camera,
            source_video=str(manifest.get("source_video", "")),
            created_at=str(manifest.get("created_at", "")),
            updated_at=str(manifest.get("updated_at", "")),
            tags=tuple(gameplay.tags),
        )

    def _validate_trash_path(self, path: str | Path) -> Path:
        self.ensure()
        source = Path(path).expanduser().resolve()
        trash_root = self.trash.resolve()
        if source == trash_root or not source.is_relative_to(trash_root):
            raise DancePackageError("trash path is invalid")
        if not source.is_dir() or source.parent != trash_root:
            raise DancePackageError("trash path is invalid")
        return source

    @staticmethod
    def _camera_from_sequence(sequence: PoseSequence) -> CameraProfile:
        raw = sequence.metadata.get("camera_profile")
        if isinstance(raw, Mapping):
            try:
                return CameraProfile.from_metadata({"camera_profile": dict(raw)})
            except (TypeError, ValueError):
                pass
        return CameraProfile(view=CameraView.UNKNOWN)


def package_with_updates(package: DancePackage, **changes: Any) -> DancePackage:
    """Test-friendly immutable update helper for package metadata."""
    return replace(package, **changes)
