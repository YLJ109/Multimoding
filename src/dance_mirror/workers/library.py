"""Workers for dance-package disk operations."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal

from dance_mirror.domain.types import PoseSequence
from dance_mirror.storage.motion_library import (
    DancePackage,
    GameplayMetadata,
    MotionPackageLibrary,
)
from dance_mirror.workers.base import CancellableWorker

LOGGER = logging.getLogger(__name__)


class LibraryScanWorker(CancellableWorker):
    packagesReady = pyqtSignal(object)

    def __init__(self, library_root: str) -> None:
        super().__init__()
        self.library_root = library_root

    def run(self) -> None:
        try:
            packages = MotionPackageLibrary(self.library_root).scan()
            if not self._stopped:
                self.packagesReady.emit(packages)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("dance package scan failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class CreateDancePackageWorker(CancellableWorker):
    packageReady = pyqtSignal(object)

    def __init__(
        self,
        sequence: PoseSequence,
        library_root: str,
        *,
        name: str,
        source_video: str,
        audio_source: str = "",
        bpm: float = 120.0,
        difficulty: int = 3,
        dance_type: str = "其他",
    ) -> None:
        super().__init__()
        self.sequence = sequence
        self.library_root = library_root
        self.name = name
        self.source_video = source_video
        self.audio_source = audio_source
        self.bpm = float(bpm)
        self.difficulty = int(difficulty)
        self.dance_type = dance_type

    def run(self) -> None:
        try:
            library = MotionPackageLibrary(self.library_root)
            package = library.create_from_sequence(
                self.sequence,
                name=self.name,
                source_video=self.source_video,
                poster_source=None,
                audio_source=self.audio_source or None,
                gameplay=GameplayMetadata(
                    bpm=self.bpm,
                    difficulty=self.difficulty,
                    dance_type=self.dance_type,
                    tags=("video", "dance"),
                ),
            )
            if not self._stopped:
                self.packageReady.emit(package)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("dance package creation failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class LoadDancePackageWorker(CancellableWorker):
    packageReady = pyqtSignal(object)
    sequenceReady = pyqtSignal(object)
    beatmapReady = pyqtSignal(object)

    def __init__(self, library_root: str, package_id: str) -> None:
        super().__init__()
        self.library_root = library_root
        self.package_id = package_id

    def run(self) -> None:
        try:
            library = MotionPackageLibrary(self.library_root)
            package: DancePackage = library.load(self.package_id)
            sequence = library.load_motion(package)
            beatmap = library.load_beatmap(package)
            if self._stopped:
                return
            self.packageReady.emit(package)
            self.sequenceReady.emit(sequence)
            self.beatmapReady.emit(beatmap)
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("dance package loading failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class RenameDancePackageWorker(CancellableWorker):
    packageReady = pyqtSignal(object)

    def __init__(self, library_root: str, package_id: str, name: str) -> None:
        super().__init__()
        self.library_root = library_root
        self.package_id = package_id
        self.name = name

    def run(self) -> None:
        try:
            package = MotionPackageLibrary(self.library_root).rename(
                self.package_id,
                self.name,
            )
            self.packageReady.emit(package)
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class DeleteDancePackageWorker(CancellableWorker):
    deleted = pyqtSignal(str)

    def __init__(self, library_root: str, package_id: str) -> None:
        super().__init__()
        self.library_root = library_root
        self.package_id = package_id

    def run(self) -> None:
        try:
            MotionPackageLibrary(self.library_root).delete(self.package_id)
            self.deleted.emit(self.package_id)
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class AssetUpdateWorker(CancellableWorker):
    packageReady = pyqtSignal(object)

    def __init__(
        self,
        library_root: str,
        package_id: str,
        *,
        poster_source: str = "",
        audio_source: str = "",
        extract_audio: bool = False,
    ) -> None:
        super().__init__()
        self.library_root = library_root
        self.package_id = package_id
        self.poster_source = poster_source
        self.audio_source = audio_source
        self.extract_audio = extract_audio

    def run(self) -> None:
        try:
            library = MotionPackageLibrary(self.library_root)
            if self.poster_source:
                library.set_poster(self.package_id, self.poster_source)
            if self.audio_source:
                library.set_audio(self.package_id, self.audio_source)
            if self.extract_audio:
                library.extract_audio_from_video(self.package_id)
            self.packageReady.emit(library.load(self.package_id))
            self.finished.emit()
        except Exception as exc:
            LOGGER.exception("dance package asset update failed")
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class TrashScanWorker(CancellableWorker):
    entriesReady = pyqtSignal(object)

    def __init__(self, library_root: str) -> None:
        super().__init__()
        self.library_root = library_root

    def run(self) -> None:
        try:
            entries = MotionPackageLibrary(self.library_root).list_trash()
            if not self._stopped:
                self.entriesReady.emit(entries)
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class RestoreDancePackageWorker(CancellableWorker):
    restored = pyqtSignal(object)

    def __init__(self, library_root: str, trash_path: str) -> None:
        super().__init__()
        self.library_root = library_root
        self.trash_path = trash_path

    def run(self) -> None:
        try:
            package = MotionPackageLibrary(self.library_root).restore(self.trash_path)
            self.restored.emit(package)
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class PurgeTrashWorker(CancellableWorker):
    purged = pyqtSignal(int)

    def __init__(self, library_root: str, trash_path: str = "") -> None:
        super().__init__()
        self.library_root = library_root
        self.trash_path = trash_path

    def run(self) -> None:
        try:
            library = MotionPackageLibrary(self.library_root)
            if self.trash_path:
                library.purge(self.trash_path)
                count = 1
            else:
                count = library.purge_all()
            self.purged.emit(int(count))
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class BatchRenameDancePackagesWorker(CancellableWorker):
    packagesReady = pyqtSignal(object)

    def __init__(
        self,
        library_root: str,
        package_ids: tuple[str, ...],
        prefix: str,
    ) -> None:
        super().__init__()
        self.library_root = library_root
        self.package_ids = tuple(package_ids)
        self.prefix = str(prefix).strip()

    def run(self) -> None:
        try:
            library = MotionPackageLibrary(self.library_root)
            updated: list[DancePackage] = []
            for package_id in self.package_ids:
                if self._stopped:
                    self.cancelled.emit()
                    return
                package = library.load(package_id)
                updated.append(library.rename(package, f"{self.prefix}{package.name}"))
            self.packagesReady.emit(updated)
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")


class BatchDeleteDancePackagesWorker(CancellableWorker):
    deleted = pyqtSignal(int)

    def __init__(self, library_root: str, package_ids: tuple[str, ...]) -> None:
        super().__init__()
        self.library_root = library_root
        self.package_ids = tuple(package_ids)

    def run(self) -> None:
        try:
            library = MotionPackageLibrary(self.library_root)
            deleted = 0
            for package_id in self.package_ids:
                if self._stopped:
                    self.cancelled.emit()
                    return
                library.delete(package_id)
                deleted += 1
            self.deleted.emit(deleted)
            self.finished.emit()
        except Exception as exc:
            self.errorOccurred.emit(f"{type(exc).__name__}: {exc}")
