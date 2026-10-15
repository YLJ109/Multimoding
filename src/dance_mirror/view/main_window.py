"""Main window orchestration for DanceMirror V9/V10."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from dance_mirror.coaching.cloud import CloudConfig
from dance_mirror.coaching.providers import default_provider_for_session
from dance_mirror.coaching.tts import CloudTTSConfig
from dance_mirror.command.intents import CommandResult, RobotCommand, SafetyClass
from dance_mirror.command.parser import LocalCommandParser, ValidatedCommandPlan
from dance_mirror.command.queue import CommandQueue
from dance_mirror.config import AppPaths, Settings
from dance_mirror.domain.representation import RootMotionMode, RootMotionPolicy
from dance_mirror.domain.types import PoseFrame, PoseSequence, TrainingUpdate
from dance_mirror.motion.comparison_space import CameraProfile, CameraView
from dance_mirror.motion.normalization import NormalizationError, normalize_frame
from dance_mirror.motion.retarget import retarget_frame
from dance_mirror.motion.sync import SyncPolicy
from dance_mirror.multimodal.gesture import gesture_name_zh
from dance_mirror.pose2d.yolo_pose import YoloPoseConfig
from dance_mirror.renderer.character_catalog import CharacterStore, character_preset
from dance_mirror.renderer.three_scene import ROBOT_MODEL_LOCAL_FILE
from dance_mirror.services.performance import PerformanceGuard
from dance_mirror.session import (
    DanceSessionState,
    DanceSessionStateMachine,
    InvalidSessionTransition,
)
from dance_mirror.storage.database import TrainingRecord, utc_timestamp
from dance_mirror.storage.motion_library import DancePackage, MotionPackageLibrary
from dance_mirror.view.app_shell import AppShellWindow
from dance_mirror.view.command_center_interface import CommandCenterInterface
from dance_mirror.view.dance_session_window import DanceSessionWindow
from dance_mirror.view.dance_workspace_interface import DanceWorkspaceInterface
from dance_mirror.view.design_tokens import palette_for
from dance_mirror.view.fluent import (
    FLUENT_AVAILABLE,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
)
from dance_mirror.view.history_interface import HistoryInterface
from dance_mirror.view.library_interface import DancePackageLibraryInterface
from dance_mirror.view.settings_interface import SettingsInterface
from dance_mirror.view.settings_store import SettingsStore
from dance_mirror.view.settings_validation import validate_settings
from dance_mirror.view.start_gate import DanceStartGate
from dance_mirror.view.theme import apply_app_theme, resolve_theme
from dance_mirror.workers.analysis import ReferenceAnalysisWorker
from dance_mirror.workers.base import WorkerThreadController
from dance_mirror.workers.cloud import (
    CloudCapabilityWorker,
    CloudCommandWorker,
    CloudSummaryWorker,
)
from dance_mirror.workers.imitation import RobotImitationWorker
from dance_mirror.workers.library import (
    AssetUpdateWorker,
    BatchDeleteDancePackagesWorker,
    BatchRenameDancePackagesWorker,
    CreateDancePackageWorker,
    DeleteDancePackageWorker,
    LibraryScanWorker,
    LoadDancePackageWorker,
    PurgeTrashWorker,
    RenameDancePackageWorker,
    RestoreDancePackageWorker,
    TrashScanWorker,
)
from dance_mirror.workers.live import LiveTrainingWorker
from dance_mirror.workers.registry import WorkerRegistry
from dance_mirror.workers.speech import SpeechWorker
from dance_mirror.workers.storage import LoadHistoryWorker, SaveTrainingRecordWorker
from dance_mirror.workers.voice import CloudSpeechRecognitionConfig, VoiceCommandWorker

LOGGER = logging.getLogger(__name__)

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:
    QAudioOutput = None
    QMediaPlayer = None



class MainWindow(AppShellWindow):
    """Own threads, renderer state, package assets, and workflow routing."""

    def __init__(self, paths: AppPaths | None = None, settings: Settings | None = None) -> None:
        super().__init__()
        self.paths = paths or AppPaths.discover()
        self.paths.ensure()
        self.settings = settings or Settings()
        self.library = MotionPackageLibrary(self.paths.motion_packages)
        self.character_store = CharacterStore(self.paths.characters)

        self._settings_values = self._load_settings_snapshot()
        self._camera_index = int(self._settings_values["camera_index"])
        self._api_key = self._session_secret("DASHSCOPE_API_KEY")
        self._tts_api_key = ""
        self._asr_api_key = ""
        self._dance_session_window: DanceSessionWindow | None = None
        self._packages: tuple[DancePackage, ...] = ()
        self._selected_package: DancePackage | None = None
        self._reference_sequence: PoseSequence | None = None
        self._beatmap: dict[str, Any] = {}
        self._pending_conversion: tuple[str, str, str] | None = None

        self._analysis_controller: WorkerThreadController | None = None
        self._create_package_controller: WorkerThreadController | None = None
        self._load_package_controller: WorkerThreadController | None = None
        self._command_load_controller: WorkerThreadController | None = None
        self._library_controller: WorkerThreadController | None = None
        self._asset_controller: WorkerThreadController | None = None
        self._live_controller: WorkerThreadController | None = None
        self._preview_controller: WorkerThreadController | None = None
        self._imitation_controller: WorkerThreadController | None = None
        self._voice_controller: WorkerThreadController | None = None
        self._cloud_controller: WorkerThreadController | None = None
        self._live_coach_controller: WorkerThreadController | None = None
        self._cloud_test_controller: WorkerThreadController | None = None
        self._last_live_coach_at = 0.0
        self._live_coach_low_streak = 0
        self._cloud_command_controller: WorkerThreadController | None = None
        self._speech_controller: WorkerThreadController | None = None
        self._history_controller: WorkerThreadController | None = None
        self._record_controller: WorkerThreadController | None = None
        self._trash_controller: WorkerThreadController | None = None
        self._batch_controller: WorkerThreadController | None = None
        self._retiring_controllers: list[WorkerThreadController] = []
        self._worker_registry = WorkerRegistry()

        self._session_started_at: str | None = None
        self._session_start_monotonic = 0.0
        self._session_clock_base_s = 0.0
        self._session_speed = 1.0
        self._session_active = False
        self._session_paused = False
        self._session_countdown = 0
        self._session_start_pending = False
        self._dance_start_gate = DanceStartGate()
        self._session_start_generation = 0
        self._session_waiting_for_worker = False
        self._session_state = DanceSessionStateMachine()
        self._session_cues: dict[str, int] = {}
        self._latest_update: TrainingUpdate | None = None
        self._latest_body_scores: dict[str, float] = {}
        self._current_record: TrainingRecord | None = None
        self._performance_guard = PerformanceGuard(
            target_fps=45.0,
            samples_required=4,
            cooldown_samples=12,
        )
        self._performance_level = 0
        self._performance_request_pending = False

        self._command_parser = LocalCommandParser()
        self._command_queue = CommandQueue()
        self._pending_command_results: list[CommandResult] = []
        self._command_sequence: PoseSequence | None = None
        self._command_package: DancePackage | None = None
        self._command_clock_base_s = 0.0
        self._command_clock_started = 0.0
        self._last_command_text = ""
        self._last_command_at = 0.0

        self._media_player: object | None = None
        self._audio_output: object | None = None
        self._clock_timer = QTimer(self)
        self._clock_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._clock_timer.setInterval(33)
        self._clock_timer.timeout.connect(self._tick_dance_clock)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._session_start_guard_timer = QTimer(self)
        self._session_start_guard_timer.setSingleShot(True)
        self._session_start_guard_timer.setInterval(15000)
        self._session_start_guard_timer.timeout.connect(self._on_session_start_timeout)
        self._command_poll_timer = QTimer(self)
        self._command_poll_timer.setInterval(80)
        self._command_poll_timer.timeout.connect(self._drain_command_queue)
        self._performance_timer = QTimer(self)
        self._performance_timer.setInterval(1200)
        self._performance_timer.timeout.connect(self._sample_render_performance)

        self.setWindowTitle("舞镜 DanceMirror")
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        target_width = min(1440, max(960, available.width() - 48)) if available else 1440
        target_height = min(900, max(620, available.height() - 48)) if available else 900
        self.resize(target_width, target_height)
        self.setMinimumSize(min(1100, target_width), min(700, target_height))
        self._fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self._fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        self._configure_window_theme()
        self._build_interfaces()
        self._create_media_player()
        self._start_speech_worker()
        self._load_history()
        self._start_library_scan()
        self._performance_timer.start()
        if bool(self._settings_values.get("fullscreen_on_start", False)):
            QTimer.singleShot(0, self.showFullScreen)

    def _configure_window_theme(self) -> None:
        theme_name = resolve_theme(str(self._settings_values.get("appearance_theme", "dark")))
        app = QApplication.instance()
        if app is not None:
            apply_app_theme(app, theme_name)
        if hasattr(self, "setMicaEffectEnabled"):
            try:
                self.setMicaEffectEnabled(False)
            except Exception:
                LOGGER.debug("Mica is unavailable on this Windows build")
        if hasattr(self, "setCustomBackgroundColor"):
            try:
                palette = palette_for(theme_name)
                self.setCustomBackgroundColor(palette.background, palette.background)
            except Exception:
                LOGGER.debug("custom window background is unavailable")
        if hasattr(self, "dance_workspace"):
            self.dance_workspace.scene.set_theme_mode(theme_name)
        if hasattr(self, "command_center"):
            self.command_center.scene.set_theme_mode(theme_name)
        if hasattr(self, "history_interface"):
            self.history_interface.set_theme_mode(theme_name)
        if hasattr(self, "library_interface"):
            self.library_interface.set_theme_mode(theme_name)

    def _load_settings_snapshot(self) -> dict[str, Any]:
        def as_float(key: str, default: float) -> float:
            try:
                return float(self.settings.get_str(key, str(default)))
            except (TypeError, ValueError):
                return default

        session_provider = default_provider_for_session(os.environ)
        return {
            "appearance_theme": self.settings.get_str("appearance/theme", "dark"),
            "fullscreen_on_start": self.settings.get_bool("window/fullscreen_on_start", False),
            "cloud_base_url": self.settings.get_str(
                "cloud/base_url", session_provider.llm_base_url or "https://api.openai.com/v1"
            ),
            "provider_key": self.settings.get_str("cloud/provider", session_provider.key),
            "cloud_model": self.settings.get_str(
                "cloud/model", session_provider.llm_model or "gpt-4o-mini"
            ),
            "cloud_timeout_s": as_float("cloud/timeout_s", 30.0),
            "asr_base_url": self.settings.get_str(
                "asr/base_url", session_provider.asr_base_url or "https://api.openai.com/v1"
            ),
            "asr_model": self.settings.get_str(
                "asr/model", session_provider.asr_model or "whisper-1"
            ),
            "asr_language": self.settings.get_str("asr/language", "zh"),
            "asr_enabled": self.settings.get_bool(
                "asr/enabled", bool(session_provider.asr_model)
            ),
            "tts_enabled": self.settings.get_bool("tts/enabled", True),
            "tts_backend": self.settings.get_str(
                "tts/backend", "cloud" if session_provider.tts_model else "local"
            ),
            "tts_base_url": self.settings.get_str(
                "tts/base_url", session_provider.tts_base_url or "https://api.openai.com/v1"
            ),
            "tts_model": self.settings.get_str(
                "tts/model", session_provider.tts_model or "gpt-4o-mini-tts"
            ),
            "tts_voice": self.settings.get_str(
                "tts/voice", session_provider.tts_voice or "alloy"
            ),
            "tts_timeout_s": as_float("tts/timeout_s", 30.0),
            "pose_model_path": self._pose_model_path(),
            "device": self.settings.get_str("vision/device", "cuda:0"),
            "target_fps": as_float("training/target_fps", 15.0),
            "camera_width": self.settings.get_int("camera/width", 1280),
            "camera_index": self.settings.get_int("camera/index", 0),
            "camera_name": self.settings.get_str("camera/name", ""),
            "camera_height": self.settings.get_int("camera/height", 720),
            "overlay_body": self.settings.get_bool("camera/overlay_body", True),
            "overlay_face": self.settings.get_bool("camera/overlay_face", True),
            "overlay_hands": self.settings.get_bool("camera/overlay_hands", True),
            "overlay_bbox": self.settings.get_bool("camera/overlay_bbox", True),
            "overlay_hud": self.settings.get_bool("camera/overlay_hud", True),
            "overlay_labels": self.settings.get_bool("camera/overlay_labels", True),
            "mirror_user": self.settings.get_bool("training/mirror_user", True),
            "record_enabled": self.settings.get_bool("training/record_enabled", False),
            "privacy_shield": self.settings.get_bool("training/privacy_shield", True),
            "model_mode": self.settings.get_str("renderer/model_mode", "overlay"),
            "character_id": self.settings.get_str(
                "robot/character_id", "humanoid_adult"
            ),
            "motion_preset": self.settings.get_str(
                "renderer/motion_preset", "balanced"
            ),
            "robot_model_path": self.settings.get_str("robot/model_path", ""),
            "render_fps": self.settings.get_int("renderer/target_fps", 45),
            "pending_timeout_ms": self.settings.get_int("renderer/pending_timeout_ms", 300),
            "camera_preview_size": self.settings.get_str("camera/preview_size", "medium"),
            "reference_view": self.settings.get_str("camera/reference_view", "front"),
            "user_view": self.settings.get_str("camera/user_view", "front"),
            "user_offset_ms": self.settings.get_int("training/user_offset_ms", 0),
            "latency_alpha": as_float("training/capture_latency_alpha", 0.2),
            "root_mode": self.settings.get_str("motion/root_mode", RootMotionMode.NONE.value),
            "low_power": self.settings.get_bool("renderer/low_power", True),
            "skin": self.settings.get_str("robot/skin", "default"),
            "scene_theme": self.settings.get_str("robot/scene_theme", "studio"),
            "imitation_scope": self.settings.get_str("robot/imitation_scope", "full_body"),
            "imitation_smoothing": as_float("robot/imitation_smoothing", 0.45),
        }

    def _pose_model_path(self) -> str:
        return SettingsStore.pose_model_path(self.settings, self.paths.models)

    @staticmethod
    def _session_secret(name: str) -> str:
        return str(os.environ.get(name, "")).strip()

    def _robot_model_url(self) -> str:
        path = self.character_store.resolve(
            str(self._settings_values.get("character_id", "humanoid_adult")),
            str(self._settings_values.get("robot_model_path", "")),
        )
        if path is None and ROBOT_MODEL_LOCAL_FILE.is_file():
            path = ROBOT_MODEL_LOCAL_FILE.resolve()
        if path is None:
            return ""
        return QUrl.fromLocalFile(str(path)).toString()

    def _build_interfaces(self) -> None:
        self.library_interface = DancePackageLibraryInterface(self)
        self.dance_workspace = DanceWorkspaceInterface(
            self,
            render_fps=int(self._settings_values["render_fps"]),
        )
        self.command_center = CommandCenterInterface(
            self,
            render_fps=int(self._settings_values["render_fps"]),
        )
        self.history_interface = HistoryInterface(self)
        self.settings_interface = SettingsInterface(
            self,
            character_root=self.paths.characters,
        )
        self.settings_interface.load_values(self._settings_values)
        self.settings_interface.set_session_api_key(self._api_key)
        self.dance_workspace.scene.sceneStateReady.connect(self._on_scene_state_ready)
        self.command_center.scene.sceneStateReady.connect(self._on_scene_state_ready)
        self._apply_renderer_settings()
        self._configure_window_theme()

        self.library_interface.convertRequested.connect(self.start_package_conversion)
        self.library_interface.selectRequested.connect(self.load_dance_package)
        self.library_interface.renameRequested.connect(self.rename_dance_package)
        self.library_interface.deleteRequested.connect(self.delete_dance_package)
        self.library_interface.posterRequested.connect(self.update_package_poster)
        self.library_interface.musicRequested.connect(self.update_package_music)
        self.library_interface.refreshRequested.connect(self._start_library_scan)
        self.library_interface.trashRequested.connect(self._start_trash_scan)
        self.library_interface.restoreTrashRequested.connect(self._restore_trash_entry)
        self.library_interface.purgeTrashRequested.connect(self._purge_trash_entry)
        self.library_interface.purgeAllTrashRequested.connect(self._purge_all_trash)
        self.library_interface.batchRenameRequested.connect(self._batch_rename_packages)
        self.library_interface.batchDeleteRequested.connect(self._batch_delete_packages)
        self.library_interface.cancelConversionRequested.connect(self._cancel_package_conversion)
        self.library_interface.retryConversionRequested.connect(self._retry_package_conversion)
        self.history_interface.retrainRequested.connect(self.load_dance_package)

        self.dance_workspace.startRequested.connect(self._arm_dance_session)
        self.dance_workspace.pauseRequested.connect(self.pause_dance_session)
        self.dance_workspace.stopRequested.connect(self.stop_dance_session)
        self.dance_workspace.speedChanged.connect(self.set_session_speed)
        self.dance_workspace.backToLibraryRequested.connect(self._return_from_dance_session)

        self.command_center.imitationRequested.connect(self.start_robot_imitation)
        self.command_center.pauseRequested.connect(self.pause_robot_imitation)
        self.command_center.stopRequested.connect(self.stop_robot_imitation)
        self.command_center.emergencyStopRequested.connect(self.emergency_stop)
        self.command_center.commandSubmitted.connect(self.submit_robot_command)
        self.command_center.scopeChanged.connect(self.set_imitation_scope)
        self.command_center.mirrorChanged.connect(self.set_imitation_mirror)
        self.command_center.smoothingChanged.connect(self.set_imitation_smoothing)
        self.command_center.resetPoseRequested.connect(self.reset_robot_pose)
        self.command_center.skinChanged.connect(self.set_robot_skin)
        self.command_center.sceneChanged.connect(self.set_robot_scene)
        self.command_center.voiceToggleRequested.connect(self.toggle_voice_commands)

        self.settings_interface.settingsSaved.connect(self._save_settings)
        self.settings_interface.themePreviewRequested.connect(self._set_theme)
        self.settings_interface.fullscreenToggleRequested.connect(self.toggle_fullscreen)
        self.settings_interface.capabilityTestRequested.connect(self._test_cloud_capability)

        home_icon = getattr(FluentIcon, "HOME", None) if FluentIcon is not None else None
        robot_icon = getattr(FluentIcon, "ROBOT", None) if FluentIcon is not None else None
        history_icon = getattr(FluentIcon, "HISTORY", None) if FluentIcon is not None else None
        settings_icon = getattr(FluentIcon, "SETTING", None) if FluentIcon is not None else None
        self.addSubInterface(self.library_interface, home_icon, "舞蹈包库")
        self.addSubInterface(self.command_center, robot_icon, "机器人指挥中心")
        self.addSubInterface(self.history_interface, history_icon, "训练历史")
        bottom_position = (
            NavigationItemPosition.BOTTOM
            if NavigationItemPosition is not None
            else "bottom"
        )
        self.addSubInterface(
            self.settings_interface,
            settings_icon,
            "设置",
            bottom_position,
        )
        self.switchTo(self.library_interface)

    def _apply_renderer_settings(self) -> None:
        self._performance_guard.reset()
        self._performance_request_pending = False
        model_url = self._robot_model_url()
        for scene_owner in (self.dance_workspace, self.command_center):
            scene_owner.set_model_mode(str(self._settings_values["model_mode"]))
            scene_owner.scene.set_model_url(model_url)
            scene_owner.set_low_power(bool(self._settings_values["low_power"]))
            scene_owner.scene.set_render_fps(int(self._settings_values["render_fps"]))
            scene_owner.scene.set_camera_size_mode(str(self._settings_values["camera_preview_size"]))
            scene_owner.scene.set_root_motion(str(self._settings_values["root_mode"]))
            scene_owner.scene.set_motion_preset(str(self._settings_values["motion_preset"]))
            scene_owner.scene.camera_preview.set_overlay_options(
                body=bool(self._settings_values["overlay_body"]),
                face=bool(self._settings_values["overlay_face"]),
                hands=bool(self._settings_values["overlay_hands"]),
                bbox=bool(self._settings_values["overlay_bbox"]),
                hud=bool(self._settings_values["overlay_hud"]),
                labels=bool(self._settings_values["overlay_labels"]),
            )
            scene_owner.scene.camera_preview.set_mirror(
                bool(self._settings_values["mirror_user"])
            )
        self.command_center.set_skin(str(self._settings_values["skin"]))
        self.command_center.set_scene_theme(str(self._settings_values["scene_theme"]))
        self.command_center.set_scope(str(self._settings_values["imitation_scope"]))
        self.command_center.set_smoothing(float(self._settings_values["imitation_smoothing"]))

    def _sample_render_performance(self) -> None:
        if self._performance_request_pending:
            return
        if self._session_active and self.dance_workspace.isVisible():
            scene = self.dance_workspace.scene
        elif self.command_center.running and self.command_center.isVisible():
            scene = self.command_center.scene
        else:
            return
        self._performance_request_pending = True
        scene.request_scene_state()

    def _on_scene_state_ready(self, state: object) -> None:
        self._performance_request_pending = False
        if not isinstance(state, Mapping):
            return
        measured = float(state.get("measuredFps", 0.0) or 0.0)
        if measured <= 0.0:
            return
        action = self._performance_guard.observe(measured)
        if action is None:
            return
        self._apply_performance_action(action)

    def _apply_performance_action(self, action: object) -> None:
        low_power = bool(getattr(action, "low_power", False))
        render_fps = int(getattr(action, "render_fps", 45))
        message = str(getattr(action, "message", "性能优化"))
        for scene_owner in (self.dance_workspace, self.command_center):
            scene_owner.scene.set_low_power(low_power)
            scene_owner.scene.set_render_fps(render_fps)
        self.dance_workspace.set_quality(f"已自动切换到{message}，优先保持动作流畅。")
        self.command_center.show_status("性能优化", message)

    # ------------------------------------------------------------------
    # Worker lifecycle and notifications
    # ------------------------------------------------------------------
    def _track_controller(
        self,
        name: str,
        controller: WorkerThreadController,
        *,
        timeout_ms: int = 3000,
        critical: bool = False,
    ) -> WorkerThreadController:
        """Register one controller so shutdown never depends on page state."""
        self._worker_registry.register(
            name,
            controller,
            timeout_ms=timeout_ms,
            critical=critical,
        )
        return controller

    def _set_session_state(
        self,
        requested: DanceSessionState,
        *,
        quiet: bool = False,
    ) -> bool:
        """Apply a legal lifecycle transition and keep legacy flags in sync."""
        try:
            self._session_state.transition(requested)
        except InvalidSessionTransition:
            if not quiet:
                LOGGER.warning(
                    "rejected dance session transition: %s -> %s",
                    self._session_state.state.value,
                    requested.value,
                )
            return False
        state = self._session_state.state
        self._session_active = state in {
            DanceSessionState.PLAYING,
            DanceSessionState.PAUSED,
        }
        self._session_paused = state is DanceSessionState.PAUSED
        return True

    def _reset_session_state(self) -> None:
        """Start a new logical session after the previous one has settled."""
        self._dance_start_gate.reset()
        if self._session_state.state is DanceSessionState.CLOSED:
            return
        self._session_state.reset()
        self._session_active = False
        self._live_coach_low_streak = 0
        self._session_paused = False

    def _start_speech_worker(self) -> None:
        worker = SpeechWorker(
            enabled=bool(self._settings_values["tts_enabled"]),
            cloud_config=self._build_tts_config(),
        )
        controller = WorkerThreadController(worker, self)
        controller.errorOccurred.connect(
            lambda message: LOGGER.warning("speech worker error: %s", message)
        )
        self._speech_controller = controller
        self._track_controller("speech", controller)
        controller.start()

    def _restart_speech_worker(self) -> None:
        if self._speech_controller is not None:
            self._speech_controller.stop()
            self._worker_registry.unregister("speech")
        self._speech_controller = None
        self._start_speech_worker()

    def _stop_controller_async(
        self,
        controller: WorkerThreadController,
        callback: object | None = None,
    ) -> None:
        """Request a worker stop without blocking the Qt event loop.

        Camera/model initialization can take several seconds on a cold start.
        The callback runs only after the worker thread has fully released
        its OpenCV and MediaPipe resources.
        """
        called = False
        self._retiring_controllers.append(controller)

        def finish() -> None:
            nonlocal called
            if called:
                return
            called = True
            if controller in self._retiring_controllers:
                self._retiring_controllers.remove(controller)
            if callable(callback):
                callback()
        controller.finished.connect(finish)
        controller.stop(wait_ms=0)
        if not controller.thread.isRunning():
            QTimer.singleShot(0, finish)

    def _load_history(self) -> None:
        worker = LoadHistoryWorker(str(self.history_path), limit=50)
        controller = WorkerThreadController(worker, self)
        worker.historyReady.connect(self._on_history_ready)
        controller.errorOccurred.connect(
            lambda message: LOGGER.warning("history load failed: %s", message)
        )
        self._history_controller = controller
        self._track_controller("history", controller)
        controller.start()

    def _on_history_ready(self, records: object) -> None:
        if isinstance(records, list):
            self.history_interface.set_records(records)

    @property
    def history_path(self) -> Path:
        return self.paths.data / "training_history.sqlite3"

    # ------------------------------------------------------------------
    # Dance package library
    # ------------------------------------------------------------------
    def _start_library_scan(self) -> None:
        if self._library_controller is not None:
            return
        worker = LibraryScanWorker(str(self.paths.motion_packages))
        controller = WorkerThreadController(worker, self)
        worker.packagesReady.connect(self._on_library_ready)
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(self._clear_library_controller)
        self._library_controller = controller
        self._track_controller("library-scan", controller)
        controller.start()

    def _clear_library_controller(self) -> None:
        self._library_controller = None
        self._worker_registry.unregister("library-scan")

    def _on_library_ready(self, packages: object) -> None:
        if not isinstance(packages, list):
            return
        self._packages = tuple(item for item in packages if isinstance(item, DancePackage))
        self.library_interface.set_packages(self._packages)
        self._command_parser.set_packages(self._packages)

    def _on_library_error(self, message: str) -> None:
        LOGGER.error("library scan failed: %s", message)
        self.library_interface.set_status(f"舞蹈包库读取失败：{message}")

    def start_package_conversion(self, video_path: str, name: str, audio_path: str = "") -> None:
        if self._analysis_controller is not None or self._create_package_controller is not None:
            self._notify("正在转换", "请等待当前视频转换完成。")
            return
        self._pending_conversion = (video_path, name, audio_path)
        self.library_interface.set_busy(True, "正在从真人舞蹈视频提取动作，不会生成用户 3D 人物。")
        worker = ReferenceAnalysisWorker(
            video_path,
            YoloPoseConfig(
                model_path=str(self._settings_values["pose_model_path"]),
                device=str(self._settings_values["device"]),
            ),
        )
        controller = WorkerThreadController(worker, self)
        worker.sequenceReady.connect(self._on_reference_analyzed)
        controller.progressChanged.connect(self.library_interface.set_progress)
        controller.errorOccurred.connect(self._on_package_conversion_error)
        controller.finished.connect(self._clear_analysis_controller)
        self._analysis_controller = controller
        self._track_controller("reference-analysis", controller, timeout_ms=15000, critical=True)
        controller.start()

    def _clear_analysis_controller(self) -> None:
        self._analysis_controller = None
        self._worker_registry.unregister("reference-analysis")

    def _on_reference_analyzed(self, sequence: PoseSequence) -> None:
        pending = self._pending_conversion
        if pending is None:
            return
        video_path, name, audio_path = pending
        worker = CreateDancePackageWorker(
            sequence,
            str(self.paths.motion_packages),
            name=name,
            source_video=video_path,
            audio_source=audio_path,
            bpm=120.0,
            difficulty=3,
        )
        controller = WorkerThreadController(worker, self)
        worker.packageReady.connect(self._on_package_created)
        controller.errorOccurred.connect(self._on_package_conversion_error)
        controller.finished.connect(self._clear_create_package_controller)
        self._create_package_controller = controller
        self._track_controller(
            "create-dance-package",
            controller,
            timeout_ms=15000,
            critical=True,
        )
        self.library_interface.set_status("动作提取完成，正在生成海报、节拍图和舞蹈包。")
        controller.start()

    def _clear_create_package_controller(self) -> None:
        self._create_package_controller = None
        self._worker_registry.unregister("create-dance-package")

    def _on_package_created(self, package: object) -> None:
        if not isinstance(package, DancePackage):
            return
        self._pending_conversion = None
        self.library_interface.set_busy(False, f"已创建并保存：{package.name}")
        self._start_library_scan()
        self.load_dance_package(package.package_id)

    def _on_package_conversion_error(self, message: str) -> None:
        self._pending_conversion = None
        self.library_interface.set_busy(False, f"转换失败：{message}")
        self.library_interface.set_conversion_failure(message)
        self.library_interface.show_error(message)

    def _cancel_package_conversion(self) -> None:
        controllers = (self._analysis_controller, self._create_package_controller)
        for controller in controllers:
            if controller is not None:
                controller.stop(wait_ms=0)
        self._pending_conversion = None
        self.library_interface.set_busy(False, "已取消当前转换。")

    def _retry_package_conversion(self) -> None:
        pending = self.library_interface.last_conversion
        if pending is None:
            return
        video_path, name, audio_path = pending
        self.start_package_conversion(video_path, name, audio_path)

    def load_dance_package(self, package_id: str) -> None:
        if self._load_package_controller is not None:
            return
        worker = LoadDancePackageWorker(str(self.paths.motion_packages), package_id)
        controller = WorkerThreadController(worker, self)
        worker.packageReady.connect(self._on_package_metadata_loaded)
        worker.sequenceReady.connect(self._on_reference_sequence_loaded)
        worker.beatmapReady.connect(self._on_beatmap_loaded)
        controller.errorOccurred.connect(self._on_package_conversion_error)
        controller.finished.connect(self._clear_load_package_controller)
        self._load_package_controller = controller
        self._track_controller("load-dance-package", controller, timeout_ms=10000)
        self.library_interface.set_status(f"正在加载舞蹈包：{package_id}")
        controller.start()

    def _clear_load_package_controller(self) -> None:
        self._load_package_controller = None
        self._worker_registry.unregister("load-dance-package")

    def _on_package_metadata_loaded(self, package: object) -> None:
        if isinstance(package, DancePackage):
            self._selected_package = package
            self.dance_workspace.set_package(package)

    def _on_reference_sequence_loaded(self, sequence: object) -> None:
        if not isinstance(sequence, PoseSequence):
            return
        self._reference_sequence = sequence
        self._open_dance_session_window()
        if sequence:
            self._show_reference_seconds(0.0)
        self.library_interface.set_status("舞蹈包已加载，可以进入准备阶段。")
        self._start_dance_preview_worker()
        self._arm_dance_session()

    def _open_dance_session_window(self) -> None:
        """Show one independent dance window without changing main navigation."""
        window = self._dance_session_window
        if window is None:
            window = DanceSessionWindow(self.dance_workspace, parent=self)
            window.closed.connect(self._on_dance_session_closed)
            window.returnRequested.connect(self._close_dance_session_window)
            self._dance_session_window = window
        package = self._selected_package
        if package is not None:
            window.set_session_title(package.name)
        window.show_session(fullscreen=self.isFullScreen())

    def _on_dance_session_closed(self) -> None:
        self._close_dance_session_window()

    def _return_from_dance_session(self) -> None:
        self._close_dance_session_window()

    def _close_dance_session_window(self) -> None:
        """Stop camera workers, music, and timers before hiding the session."""
        window = self._dance_session_window
        if window is None:
            return
        self._dance_session_window = None
        self._stop_dance_session_silently()
        self.dance_workspace.clear_camera()
        self._reset_session_state()
        workspace = getattr(self, "dance_workspace", None)
        if workspace is not None and not sip.isdeleted(workspace):
            workspace.setParent(self)
        if window.isFullScreen():
            window.showNormal()
        window.close()
        window.deleteLater()
        self._switch_to_library()
        self.raise_()
        self.activateWindow()

    def _on_beatmap_loaded(self, beatmap: object) -> None:
        self._beatmap = dict(beatmap) if isinstance(beatmap, Mapping) else {}

    def rename_dance_package(self, package_id: str, name: str) -> None:
        worker = RenameDancePackageWorker(str(self.paths.motion_packages), package_id, name)
        controller = WorkerThreadController(worker, self)
        worker.packageReady.connect(lambda package: self._start_library_scan())
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(controller.deleteLater)
        self._track_controller("rename-dance-package", controller)
        controller.start()

    def delete_dance_package(self, package_id: str) -> None:
        package = self._find_package(package_id)
        if package is None:
            return
        answer = QMessageBox.question(
            self,
            "删除舞蹈包",
            f"将《{package.name}》移动到本地回收站？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        worker = DeleteDancePackageWorker(str(self.paths.motion_packages), package_id)
        controller = WorkerThreadController(worker, self)
        worker.deleted.connect(self._on_package_deleted)
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(controller.deleteLater)
        self._track_controller("delete-dance-package", controller)
        controller.start()

    def _on_package_deleted(self, package_id: str) -> None:
        if self._selected_package and self._selected_package.package_id == package_id:
            self._close_dance_session_window()
            self._selected_package = None
            self._reference_sequence = None
        self._start_library_scan()

    def _start_trash_scan(self) -> None:
        if self._trash_controller is not None:
            return
        worker = TrashScanWorker(str(self.paths.motion_packages))
        controller = WorkerThreadController(worker, self)
        worker.entriesReady.connect(self.library_interface.set_trash_entries)
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(self._clear_trash_controller)
        self._trash_controller = controller
        self._track_controller("trash-scan", controller)
        controller.start()

    def _clear_trash_controller(self) -> None:
        self._trash_controller = None
        self._worker_registry.unregister("trash-scan")

    def _restore_trash_entry(self, trash_path: str) -> None:
        worker = RestoreDancePackageWorker(
            str(self.paths.motion_packages),
            trash_path,
        )
        controller = WorkerThreadController(worker, self)
        worker.restored.connect(lambda _package: self._after_trash_change())
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(controller.deleteLater)
        self._track_controller("trash-restore", controller)
        controller.start()

    def _purge_trash_entry(self, trash_path: str) -> None:
        answer = QMessageBox.question(
            self,
            "永久删除",
            "该操作无法撤销，确认永久删除这个舞蹈包？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        self._start_purge_worker(trash_path)

    def _purge_all_trash(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空回收站",
            "将永久删除回收站中的全部舞蹈包，确认继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._start_purge_worker("")

    def _start_purge_worker(self, trash_path: str) -> None:
        worker = PurgeTrashWorker(str(self.paths.motion_packages), trash_path)
        controller = WorkerThreadController(worker, self)
        worker.purged.connect(lambda _count: self._after_trash_change())
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(controller.deleteLater)
        self._track_controller("trash-purge", controller)
        controller.start()

    def _after_trash_change(self) -> None:
        self._start_library_scan()
        self._start_trash_scan()

    def _batch_rename_packages(self, package_ids: object, prefix: str) -> None:
        ids = tuple(str(item) for item in package_ids) if isinstance(package_ids, (list, tuple)) else ()
        if not ids or self._batch_controller is not None:
            return
        worker = BatchRenameDancePackagesWorker(
            str(self.paths.motion_packages),
            ids,
            prefix,
        )
        controller = WorkerThreadController(worker, self)
        worker.packagesReady.connect(lambda _items: self._start_library_scan())
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(self._clear_batch_controller)
        self._batch_controller = controller
        self._track_controller("library-batch", controller)
        controller.start()

    def _batch_delete_packages(self, package_ids: object) -> None:
        ids = tuple(str(item) for item in package_ids) if isinstance(package_ids, (list, tuple)) else ()
        if not ids or self._batch_controller is not None:
            return
        worker = BatchDeleteDancePackagesWorker(
            str(self.paths.motion_packages),
            ids,
        )
        controller = WorkerThreadController(worker, self)
        worker.deleted.connect(lambda _count: self._start_library_scan())
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(self._clear_batch_controller)
        self._batch_controller = controller
        self._track_controller("library-batch", controller)
        controller.start()

    def _clear_batch_controller(self) -> None:
        self._batch_controller = None
        self._worker_registry.unregister("library-batch")

    def update_package_poster(self, package_id: str, poster_path: str) -> None:
        self._start_asset_update(package_id, poster_source=poster_path)

    def update_package_music(self, package_id: str) -> None:
        self._start_asset_update(package_id, extract_audio=True)

    def _start_asset_update(
        self,
        package_id: str,
        *,
        poster_source: str = "",
        audio_source: str = "",
        extract_audio: bool = False,
    ) -> None:
        if self._asset_controller is not None:
            return
        worker = AssetUpdateWorker(
            str(self.paths.motion_packages),
            package_id,
            poster_source=poster_source,
            audio_source=audio_source,
            extract_audio=extract_audio,
        )
        controller = WorkerThreadController(worker, self)
        worker.packageReady.connect(lambda _package: self._start_library_scan())
        controller.errorOccurred.connect(self._on_library_error)
        controller.finished.connect(self._clear_asset_controller)
        self._asset_controller = controller
        self._track_controller("asset-update", controller, timeout_ms=10000)
        controller.start()

    def _clear_asset_controller(self) -> None:
        self._asset_controller = None
        self._worker_registry.unregister("asset-update")

    def _find_package(self, package_id: str) -> DancePackage | None:
        return next(
            (item for item in self._packages if item.package_id == package_id),
            None,
        )

    def _start_dance_preview_worker(self) -> None:
        if self._preview_controller is not None or self._live_controller is not None:
            return
        worker = RobotImitationWorker(
            self._camera_index,
            pose_config=YoloPoseConfig(
                model_path=str(self._settings_values["pose_model_path"]),
                device=str(self._settings_values["device"]),
            ),
            target_fps=float(self._settings_values["target_fps"]),
            camera_width=int(self._settings_values["camera_width"]),
            camera_height=int(self._settings_values["camera_height"]),
            mirror=bool(self._settings_values["mirror_user"]),
            smoothing=float(self._settings_values["imitation_smoothing"]),
            enable_hand_gestures=True,
        )
        worker.configure(paused=True)
        controller = WorkerThreadController(worker, self)
        worker.previewReady.connect(self._on_dance_preview)
        worker.readinessReady.connect(self._on_dance_readiness)
        worker.gestureReady.connect(self._on_dance_gesture)
        controller.errorOccurred.connect(
            lambda message: LOGGER.warning("dance preview worker: %s", message)
        )
        controller.finished.connect(self._clear_preview_controller)
        self._preview_controller = controller
        self._track_controller(
            "dance-preview",
            controller,
            timeout_ms=15000,
            critical=True,
        )
        controller.start()

    def _clear_preview_controller(self) -> None:
        self._preview_controller = None
        self._worker_registry.unregister("dance-preview")

    def _arm_dance_session(self) -> None:
        """Arm the preview gate; the session starts only after readiness and OK."""
        if self._reference_sequence is None or self._selected_package is None:
            self._notify("缺少舞蹈包", "请先从舞蹈包库选择一个动作包。")
            return
        if self._session_active or self._session_countdown > 0:
            return
        if self._live_controller is not None:
            return
        self._start_dance_preview_worker()
        self._dance_start_gate.arm(time.monotonic())
        self.dance_workspace.set_playing(False)
        self.dance_workspace.set_armed(True)
        self.dance_workspace.set_quality(self._dance_start_gate.reason)

    def _on_dance_readiness(self, report: object) -> None:
        if self._session_active or self._session_countdown > 0 or self._live_controller is not None:
            return
        message = str(getattr(report, "message", ""))
        score = float(getattr(report, "score", 0.0))
        single_person = bool(getattr(report, "single_person", False))
        full_body = bool(getattr(report, "full_body", False))
        if message:
            self.dance_workspace.set_quality(f"{message} 就位度 {score * 100:.0f}%。")
        if self._dance_start_gate.observe_readiness(
            score=score,
            single_person=single_person,
            full_body=full_body,
            now_s=time.monotonic(),
        ):
            self.start_dance_session()

    def _on_dance_gesture(self, name: str, confidence: float) -> None:
        if self._session_active or self._session_countdown > 0 or self._live_controller is not None:
            return
        if name != "unknown" or float(confidence) > 0.0:
            self._dance_start_gate.observe_hands(True)
            self.dance_workspace.set_quality(f"手势：{gesture_name_zh(name)} {confidence:.0%}")
        if self._dance_start_gate.observe_gesture(name, confidence, time.monotonic()):
            self.start_dance_session()
        elif self._dance_start_gate.armed:
            self.dance_workspace.set_quality(self._dance_start_gate.reason)

    # ------------------------------------------------------------------
    # Dance learning session
    # ------------------------------------------------------------------
    def start_dance_session(self) -> None:
        if self._reference_sequence is None or self._selected_package is None:
            self._notify("缺少舞蹈包", "请先从舞蹈包库选择一个动作包。")
            return
        if self._live_controller is not None:
            return
        self._stop_command_dance()
        self._reset_session_state()
        self._set_session_state(DanceSessionState.PREFLIGHT)
        self._session_active = False
        self._session_paused = False
        self._session_clock_base_s = 0.0
        self._session_speed = 1.0
        self._session_cues.clear()
        self._latest_update = None
        self._latest_body_scores.clear()
        self._current_record = None
        self._session_start_generation += 1
        token = self._session_start_generation
        self._session_start_pending = True
        self._session_waiting_for_worker = False
        self.dance_workspace.clear_camera()
        self.dance_workspace.set_playing(False)
        self.dance_workspace.set_package(self._selected_package)
        self.dance_workspace.set_armed(True)
        self.dance_workspace.show_countdown("连接")
        self.dance_workspace.set_quality("正在释放预览摄像头，随后连接正式训练通道。")

        preview = self._preview_controller
        if preview is None:
            QTimer.singleShot(0, lambda: self._begin_dance_session(token))
            return
        self._preview_controller = None
        self._stop_controller_async(
            preview,
            lambda: self._begin_dance_session(token),
        )

    def _begin_dance_session(self, token: int) -> None:
        if token != self._session_start_generation or not self._session_start_pending:
            return
        self._session_start_pending = False
        if self._reference_sequence is None or self._selected_package is None:
            return
        if self._live_controller is not None:
            return
        self._session_waiting_for_worker = True
        self._set_session_state(DanceSessionState.CAMERA_WARMUP, quiet=True)
        self.dance_workspace.show_countdown("连接")
        self.dance_workspace.set_quality("正在初始化姿态、双手和人脸模型，请保持全身进入画面。")
        self._start_live_training_worker()
        self._session_start_guard_timer.start()

    def _on_session_start_timeout(self) -> None:
        if not self._session_waiting_for_worker:
            return
        self._session_waiting_for_worker = False
        self._notify("训练通道未就绪", "15 秒内没有收到摄像头姿态数据，请检查摄像头占用和摆位。")
        self.stop_dance_session()

    def _start_live_training_worker(self) -> None:
        if self._reference_sequence is None:
            return
        package = self._selected_package
        if package is None:
            return
        root_mode = RootMotionMode(str(self._settings_values["root_mode"]))
        root_policy = RootMotionPolicy(mode=root_mode)
        root_downgraded = False
        try:
            root_policy.validate_quality(package.quality)
        except ValueError:
            root_policy = RootMotionPolicy(mode=RootMotionMode.NONE)
            root_downgraded = True
        reference_camera = CameraProfile(
            view=CameraView(str(self._settings_values["reference_view"]))
        )
        user_camera = CameraProfile(view=CameraView(str(self._settings_values["user_view"])))
        sync_policy = SyncPolicy(
            user_offset_s=max(0, int(self._settings_values["user_offset_ms"])) / 1000.0,
            smoothing_alpha=float(self._settings_values["latency_alpha"]),
        )
        record_path = (
            self._new_recording_path()
            if bool(self._settings_values["record_enabled"])
            else None
        )
        worker = LiveTrainingWorker(
            self._reference_sequence,
            camera_index=self._camera_index,
            pose_config=YoloPoseConfig(
                model_path=str(self._settings_values["pose_model_path"]),
                device=str(self._settings_values["device"]),
            ),
            target_fps=float(self._settings_values["target_fps"]),
            camera_width=int(self._settings_values["camera_width"]),
            camera_height=int(self._settings_values["camera_height"]),
            camera_fps=float(self._settings_values["target_fps"]),
            privacy_shield=bool(self._settings_values["privacy_shield"]),
            record_path=str(record_path) if record_path is not None else None,
            mirror_user=bool(self._settings_values["mirror_user"]),
            reference_camera=reference_camera,
            user_camera=user_camera,
            sync_policy=sync_policy,
        )
        controller = WorkerThreadController(worker, self)
        self.dance_workspace.set_root_motion(root_policy.mode.value)
        if root_downgraded:
            self.dance_workspace.set_quality(
                "当前动作包未达到已校验 3D，根运动已自动降级为固定舞台。"
            )
        worker.updateReady.connect(self._on_training_update)
        worker.previewReady.connect(self._on_dance_preview)
        worker.gestureReady.connect(self._on_live_gesture)
        worker.privacyChanged.connect(lambda masked: self.dance_workspace.set_quality(
            "隐私遮罩已开启。" if masked else "摄像头隐私状态正常。"
        ))
        worker.qualityReady.connect(lambda quality: self.dance_workspace.set_quality(
            f"动作包质量：{quality.level.display_name}，评分置信度 {quality.score_confidence:.0%}"
        ))
        worker.syncReady.connect(self.dance_workspace.set_sync_status)
        controller.errorOccurred.connect(self._on_worker_error)
        controller.finished.connect(self._on_live_finished)
        self._live_controller = controller
        self._track_controller(
            "live-training",
            controller,
            timeout_ms=15000,
            critical=True,
        )
        controller.start()

    def _tick_countdown(self) -> None:
        self._session_countdown -= 1
        if self._session_countdown > 0:
            self.dance_workspace.show_countdown(self._session_countdown)
            return
        self._countdown_timer.stop()
        self._activate_dance_session()

    def _activate_dance_session(self) -> None:
        self._set_session_state(DanceSessionState.PLAYING, quiet=True)
        self._session_active = True
        self._session_paused = False
        self._session_start_monotonic = time.monotonic()
        self._session_clock_base_s = 0.0
        self._session_started_at = utc_timestamp()
        self.dance_workspace.show_countdown("开始")
        self.dance_workspace.set_playing(True, paused=False)
        self.dance_workspace.set_action("dance")
        self._play_music(0.0)
        self._clock_timer.start()

    def _session_clock(self) -> float:
        if self._session_paused:
            return self._session_clock_base_s
        package = self._selected_package
        if (
            package is not None
            and package.has_music
            and self._media_player is not None
            and hasattr(self._media_player, "position")
        ):
            position = float(self._media_player.position()) / 1000.0
            if position > 0.0 or self._session_clock_base_s <= 0.0:
                return position
        return self._session_clock_base_s + (
            time.monotonic() - self._session_start_monotonic
        ) * self._session_speed

    def pause_dance_session(self, paused: bool) -> None:
        if not self._session_active:
            return
        requested = (
            DanceSessionState.PAUSED if paused else DanceSessionState.PLAYING
        )
        if not self._set_session_state(requested, quiet=True):
            return
        self._session_paused = paused
        if paused:
            self._session_clock_base_s = self._session_clock()
            if self._media_player is not None and hasattr(self._media_player, "pause"):
                self._media_player.pause()
        else:
            self._session_start_monotonic = time.monotonic()
            if self._media_player is not None and hasattr(self._media_player, "play"):
                self._media_player.play()
        self.dance_workspace.set_playing(True, paused=paused)

    def set_session_speed(self, speed: float) -> None:
        self._session_speed = max(0.5, min(2.0, float(speed)))
        if self._media_player is not None and hasattr(self._media_player, "setPlaybackRate"):
            self._media_player.setPlaybackRate(self._session_speed)

    def stop_dance_session(self, *, completed: bool = False) -> None:
        self._countdown_timer.stop()
        self._clock_timer.stop()
        self._session_start_guard_timer.stop()
        self._session_start_generation += 1
        self._session_start_pending = False
        self._session_waiting_for_worker = False
        self._set_session_state(DanceSessionState.FINALIZING, quiet=True)
        was_active = self._session_active
        self._session_active = False
        self._session_paused = False
        self._stop_music()
        if self._live_controller is not None:
            controller = self._live_controller
            self._live_controller = None
            self._worker_registry.unregister("live-training")
            self._stop_controller_async(controller)
        self.dance_workspace.set_playing(False)
        self.dance_workspace.set_action("idle")
        if completed:
            self.dance_workspace.show_countdown("完成")
            self._finalize_session()
        elif was_active:
            self.dance_workspace.show_countdown("已停止")
            self._finalize_session()
        else:
            self.dance_workspace.show_countdown("准备")

        self._reset_session_state()

    def _on_dance_preview(self, packet: object) -> None:
        if hasattr(packet, "readiness"):
            self.dance_workspace.set_camera_packet(packet)  # type: ignore[arg-type]
        if self._session_waiting_for_worker and self._live_controller is not None:
            self._session_waiting_for_worker = False
            self._set_session_state(DanceSessionState.COUNTDOWN, quiet=True)
            self._session_start_guard_timer.stop()
            self._session_countdown = 3
            self.dance_workspace.show_countdown(self._session_countdown)
            self.dance_workspace.set_quality("训练通道已就绪，请保持全身可见，3 秒后开始。")
            self._countdown_timer.start()
            return
        if self._preview_controller is None or not self._dance_start_gate.armed:
            return
        hands = tuple(getattr(packet, "hands", ()) or ())
        self._dance_start_gate.observe_hands(bool(hands))
        person_count = int(getattr(packet, "person_count", 0) or 0)
        if person_count > 1:
            self._dance_start_gate.observe_readiness(
                score=0.0,
                single_person=False,
                full_body=False,
                now_s=time.monotonic(),
            )
        self.dance_workspace.set_quality(self._dance_start_gate.reason)

    def _on_live_gesture(self, name: str, confidence: float) -> None:
        if name != "unknown":
            self.dance_workspace.set_quality(f"实时手势：{gesture_name_zh(name)} {confidence:.0%}")

    def _on_training_update(self, update: TrainingUpdate) -> None:
        if self._session_countdown > 0:
            return
        if self._session_paused:
            return
        self._latest_update = update
        from dance_mirror.motion.comparison import body_part_scores

        self._latest_body_scores = body_part_scores(update.score)
        self.dance_workspace.apply_update(update)
        if update.cue is not None:
            self._session_cues[update.cue.feature] = (
                self._session_cues.get(update.cue.feature, 0) + 1
            )
            self._enqueue_tts(update.cue.text)

        score = float(update.score.overall)
        if score < 65.0 and self._session_active:
            self._live_coach_low_streak += 1
            if self._live_coach_low_streak >= 5:
                self._start_live_cloud_coach()
        else:
            self._live_coach_low_streak = 0

    def _start_live_cloud_coach(self) -> None:
        if not self._api_key or self._live_coach_controller is not None:
            return
        now = time.monotonic()
        if now - self._last_live_coach_at < 12.0:
            return
        update = self._latest_update
        if update is None:
            return
        self._last_live_coach_at = now
        self._live_coach_low_streak = 0
        summary = {
            "mode": "live_coach",
            "package": self._selected_package.name if self._selected_package else "",
            "elapsed_s": round(self._session_clock(), 1),
            "overall_score": round(float(update.score.overall), 1),
            "body_part_scores": dict(self._latest_body_scores),
            "cue_counts": dict(self._session_cues),
            "request": "只给出一条当前最优先、可立即执行的中文动作提醒，30字以内。",
        }
        worker = CloudSummaryWorker(
            summary,
            CloudConfig(
                base_url=str(self._settings_values["cloud_base_url"]),
                model=str(self._settings_values["cloud_model"]),
                api_key=self._api_key,
                timeout_s=float(self._settings_values["cloud_timeout_s"]),
                max_tokens=80,
                temperature=0.1,
            ),
        )
        controller = WorkerThreadController(worker, self)
        worker.summaryReady.connect(self._on_live_coach_ready)
        controller.errorOccurred.connect(self._on_live_coach_error)
        controller.finished.connect(self._clear_live_coach_controller)
        self._live_coach_controller = controller
        self._track_controller("live-cloud-coach", controller, timeout_ms=10000)
        controller.start()

    def _on_live_coach_ready(self, text: str) -> None:
        if self._session_active and text.strip():
            self.dance_workspace.set_live_coach(text.strip())

    def _on_live_coach_error(self, message: str) -> None:
        LOGGER.warning("live cloud coach failed: %s", message)
        if self._session_active:
            self.dance_workspace.set_live_coach(
                "云端教练暂不可用，继续按本地节拍与姿态提示练习。"
            )

    def _clear_live_coach_controller(self) -> None:
        self._live_coach_controller = None
        self._worker_registry.unregister("live-cloud-coach")

    def _on_live_finished(self) -> None:
        self._live_controller = None
        self._worker_registry.unregister("live-training")
        self._session_start_guard_timer.stop()
        self._session_waiting_for_worker = False
        self.dance_workspace.set_action("idle")
        self._set_session_state(DanceSessionState.FINALIZING, quiet=True)
        if self._session_active:
            self._finalize_session()
        self._session_active = False
        self._session_paused = False
        self._clock_timer.stop()
        self._countdown_timer.stop()
        self._stop_music()
        self.dance_workspace.set_playing(False)
        self._reset_session_state()

    def _finalize_session(self) -> None:
        if self._session_started_at is None:
            return
        started_at = self._session_started_at
        duration_s = self._session_clock()
        self._session_started_at = None
        if self._latest_update is None:
            self.dance_workspace.set_report("本次没有收到有效姿态，未生成评分记录。")
            return
        record = TrainingRecord(
            session_id=f"dance-{time.time_ns()}",
            started_at=started_at,
            duration_s=max(0.0, duration_s),
            overall_score=round(float(self._latest_update.score.overall), 2),
            body_part_scores=dict(self._latest_body_scores),
            cue_counts=dict(self._session_cues),
            summary="本地训练记录已保存。",
            metadata={
                "package_id": self._selected_package.package_id
                if self._selected_package
                else "",
                "package_name": self._selected_package.name
                if self._selected_package
                else "",
                "quality_level": self._selected_package.quality.level.value
                if self._selected_package
                else "",
                "reference_frames": len(self._reference_sequence)
                if self._reference_sequence
                else 0,
            },
        )
        self._current_record = record
        self._persist_record(record)
        self._start_cloud_summary(record)
        summary = self._local_session_summary(record)
        self.dance_workspace.set_report(summary)
        self._set_session_state(DanceSessionState.SETTLED, quiet=True)

    @staticmethod
    def _local_session_summary(record: TrainingRecord) -> str:
        if record.body_part_scores:
            weakest = min(record.body_part_scores, key=record.body_part_scores.get)
            names = {
                "left_arm": "左臂",
                "right_arm": "右臂",
                "left_leg": "左腿",
                "right_leg": "右腿",
                "torso": "躯干",
                "head": "头部",
            }
            weak_name = names.get(weakest, weakest)
            return f"总分 {record.overall_score:.1f}。本局最需要回练：{weak_name}。"
        return f"总分 {record.overall_score:.1f}。继续积累数据后会给分部位建议。"

    def _persist_record(self, record: TrainingRecord) -> None:
        worker = SaveTrainingRecordWorker(str(self.history_path), record)
        controller = WorkerThreadController(worker, self)
        worker.historyReady.connect(self._on_history_ready)
        controller.errorOccurred.connect(
            lambda message: LOGGER.warning("training record save failed: %s", message)
        )
        controller.finished.connect(controller.deleteLater)
        self._record_controller = controller
        self._track_controller("save-training-record", controller, timeout_ms=10000)
        controller.start()

    def _start_cloud_summary(self, record: TrainingRecord) -> None:
        if not self._api_key:
            return
        summary = {
            "package": record.metadata.get("package_name", "") if record.metadata else "",
            "started_at": record.started_at,
            "duration_s": record.duration_s,
            "overall_score": record.overall_score,
            "body_part_scores": record.body_part_scores,
            "cue_counts": record.cue_counts,
            "quality_level": record.metadata.get("quality_level", "")
            if record.metadata
            else "",
        }
        worker = CloudSummaryWorker(
            summary,
            CloudConfig(
                base_url=str(self._settings_values["cloud_base_url"]),
                model=str(self._settings_values["cloud_model"]),
                api_key=self._api_key,
                timeout_s=float(self._settings_values["cloud_timeout_s"]),
            ),
        )
        controller = WorkerThreadController(worker, self)
        worker.summaryReady.connect(self._on_cloud_summary_ready)
        controller.errorOccurred.connect(self._on_cloud_error)
        controller.finished.connect(self._clear_cloud_controller)
        self._cloud_controller = controller
        self._track_controller("cloud-summary", controller, timeout_ms=10000)
        controller.start()

    def _on_cloud_summary_ready(self, text: str) -> None:
        self.dance_workspace.set_report(text)
        if self._current_record is not None:
            self._current_record.summary = text
            self._persist_record(self._current_record)

    def _on_cloud_error(self, message: str) -> None:
        LOGGER.warning("cloud summary unavailable: %s", message)

    def _clear_cloud_controller(self) -> None:
        self._cloud_controller = None
        self._worker_registry.unregister("cloud-summary")

    def _test_cloud_capability(self, capability: str, config: object) -> None:
        if not isinstance(config, Mapping):
            return
        if self._cloud_test_controller is not None:
            controller = self._cloud_test_controller
            self._cloud_test_controller = None
            self._stop_controller_async(controller)
        worker = CloudCapabilityWorker(str(capability), config)
        controller = WorkerThreadController(worker, self)
        worker.resultReady.connect(
            lambda message, ok, _elapsed: self.settings_interface.set_connection_result(
                str(capability), str(message), bool(ok)
            )
        )
        controller.finished.connect(self._clear_cloud_test_controller)
        self._cloud_test_controller = controller
        self._track_controller(
            "cloud-capability-test",
            controller,
            timeout_ms=45000,
        )
        controller.start()

    def _clear_cloud_test_controller(self) -> None:
        self._cloud_test_controller = None
        self._worker_registry.unregister("cloud-capability-test")

    def _show_reference_seconds(self, seconds: float) -> None:
        sequence = self._reference_sequence
        if sequence is None or len(sequence) == 0:
            return
        index = max(0, min(len(sequence) - 1, round(seconds * sequence.fps)))
        try:
            skeleton = retarget_frame(self._reference_frame_at(sequence, index))
        except (TypeError, ValueError, NormalizationError):
            return
        self.dance_workspace.set_reference(skeleton)

    @staticmethod
    def _reference_frame_at(sequence: PoseSequence, index: int) -> PoseFrame:
        frame = PoseFrame(
            keypoints=sequence.keypoints[index],
            scores=sequence.scores[index],
            timestamp_s=float(sequence.timestamps_s[index]),
            frame_index=index,
            schema=sequence.schema,
        )
        if sequence.metadata.get("normalized"):
            return frame
        width = int(sequence.metadata.get("source_width", 0) or 0)
        height = int(sequence.metadata.get("source_height", 0) or 0)
        return normalize_frame(
            frame,
            image_size=(width, height) if width > 0 and height > 0 else None,
        )

    def _new_recording_path(self) -> Path:
        stamp = utc_timestamp().replace(":", "").replace("+00:00", "Z")
        return self.paths.recordings / f"dance-{stamp}.mp4"

    # ------------------------------------------------------------------
    # Robot command center
    # ------------------------------------------------------------------
    def start_robot_imitation(self, _enabled: bool = True) -> None:
        if self._imitation_controller is not None:
            return
        self._stop_dance_session_silently()
        worker = RobotImitationWorker(
            self._camera_index,
            pose_config=YoloPoseConfig(
                model_path=str(self._settings_values["pose_model_path"]),
                device=str(self._settings_values["device"]),
            ),
            target_fps=float(self._settings_values["target_fps"]),
            camera_width=int(self._settings_values["camera_width"]),
            camera_height=int(self._settings_values["camera_height"]),
            mirror=bool(self._settings_values["mirror_user"]),
            smoothing=float(self._settings_values["imitation_smoothing"]),
        )
        worker.configure(scope=str(self._settings_values["imitation_scope"]))
        controller = WorkerThreadController(worker, self)
        worker.poseReady.connect(self.command_center.set_robot)
        worker.previewReady.connect(self.command_center.set_camera_packet)
        worker.readinessReady.connect(self.command_center.set_readiness)
        worker.qualityReady.connect(self.command_center.set_quality)
        worker.safeHoldChanged.connect(self.command_center.set_safe_hold)
        controller.errorOccurred.connect(self._on_worker_error)
        controller.finished.connect(self._on_imitation_finished)
        self._imitation_controller = controller
        self._track_controller(
            "robot-imitation",
            controller,
            timeout_ms=15000,
            critical=True,
        )
        self.command_center.set_imitation_running(True)
        self.command_center.play_action("dance")
        controller.start()
        self._command_poll_timer.start()

    def _on_imitation_finished(self) -> None:
        self._imitation_controller = None
        self._worker_registry.unregister("robot-imitation")
        self.command_center.set_imitation_running(False)

    def pause_robot_imitation(self, paused: bool) -> None:
        controller = self._imitation_controller
        if controller is None:
            return
        worker = controller.worker
        if isinstance(worker, RobotImitationWorker):
            worker.configure(paused=paused)
        self.command_center.set_imitation_running(True, paused)

    def stop_robot_imitation(self) -> None:
        if self._imitation_controller is not None:
            controller = self._imitation_controller
            self._imitation_controller = None
            self._stop_controller_async(controller)
        self._command_poll_timer.stop()
        self._performance_timer.stop()
        self.command_center.set_imitation_running(False)
        self.command_center.play_action("idle")

    def emergency_stop(self) -> None:
        self._command_queue.push(
            CommandResult(
                command=RobotCommand.EMERGENCY_STOP,
                acknowledgement="已执行紧急停止。",
                priority=100,
                raw_text="紧急停止",
            )
        )
        self._drain_command_queue()

    def set_imitation_scope(self, scope: str) -> None:
        self._settings_values["imitation_scope"] = scope
        controller = self._imitation_controller
        if controller is not None and isinstance(controller.worker, RobotImitationWorker):
            controller.worker.configure(scope=scope)
        self.command_center.scene.set_imitation_scope(scope)

    def set_imitation_mirror(self, enabled: bool) -> None:
        controller = self._imitation_controller
        if controller is not None and isinstance(controller.worker, RobotImitationWorker):
            controller.worker.configure(mirror=enabled)
        self.command_center.preview.set_mirror(enabled)

    def set_imitation_smoothing(self, value: float) -> None:
        self._settings_values["imitation_smoothing"] = value
        controller = self._imitation_controller
        if controller is not None and isinstance(controller.worker, RobotImitationWorker):
            controller.worker.configure(smoothing=value)

    def reset_robot_pose(self) -> None:
        self.stop_robot_imitation()
        self.command_center.scene.clear_robot()
        self.command_center.play_action("idle")
        self.command_center.show_status("机器人已回到待机", "复位完成。")

    def set_robot_skin(self, name: str) -> None:
        self._settings_values["skin"] = name
        self.command_center.set_skin(name)

    def set_robot_scene(self, name: str) -> None:
        self._settings_values["scene_theme"] = name
        self.command_center.set_scene_theme(name)

    def toggle_voice_commands(self, enabled: bool) -> None:
        self._settings_values["asr_enabled"] = bool(enabled)
        if self._voice_controller is not None:
            self._voice_controller.stop()
            self._voice_controller = None
        if not enabled:
            self.command_center.set_voice_status("语音已关闭。")
            return
        config = CloudSpeechRecognitionConfig(
            base_url=str(self._settings_values["asr_base_url"]),
            model=str(self._settings_values["asr_model"]),
            language=str(self._settings_values["asr_language"]),
            api_key=self._asr_api_key or self._api_key,
        )
        worker = VoiceCommandWorker(config)
        controller = WorkerThreadController(worker, self)
        worker.transcriptReady.connect(self._on_voice_transcript)
        worker.statusChanged.connect(self.command_center.set_voice_status)
        controller.errorOccurred.connect(
            lambda message: self.command_center.set_voice_status(f"语音识别失败：{message}")
        )
        controller.finished.connect(self._clear_voice_controller)
        self._voice_controller = controller
        self._track_controller("voice-command", controller, timeout_ms=5000)
        controller.start()

    def _clear_voice_controller(self) -> None:
        self._voice_controller = None
        self._worker_registry.unregister("voice-command")

    def _on_voice_transcript(self, text: str, final: bool) -> None:
        self.command_center.append_transcript(text, final)
        if final and text.strip():
            self.submit_robot_command(text)

    def submit_robot_command(self, text: str, *, source: str = "voice") -> None:
        cleaned = " ".join(str(text).strip().split())
        if not cleaned:
            return
        now = time.monotonic()
        duplicate = (
            cleaned == self._last_command_text and now - self._last_command_at < 0.8
        )
        self._last_command_text = cleaned
        self._last_command_at = now

        result = self._command_parser.parse(cleaned, source=source)
        self.command_center.set_command_result(result)
        if result.command is RobotCommand.UNKNOWN:
            if duplicate:
                return
            self._start_cloud_command(cleaned)
            return

        if result.safety_class is SafetyClass.SAFE_FAST:
            self._execute_robot_command(result)
            return
        self._command_queue.push(result)
        self._pending_command_results.append(result)
        self.command_center.set_queue(self._pending_command_results)
        self._drain_command_queue()

    def _start_cloud_command(self, text: str) -> None:
        if not self._api_key:
            acknowledgement = "云端语言模型未配置 API Key，请换用本地命令。"
            self.command_center.show_status("未配置云模型", acknowledgement)
            self._enqueue_tts(acknowledgement)
            return
        if self._cloud_command_controller is not None:
            self.command_center.show_status("正在规划", "上一条复杂指令仍在处理。")
            return
        self.command_center.show_status("AI 规划", "正在把自然语言转换为白名单动作计划。")
        worker = CloudCommandWorker(
            text,
            CloudConfig(
                base_url=str(self._settings_values["cloud_base_url"]),
                model=str(self._settings_values["cloud_model"]),
                api_key=self._api_key,
                timeout_s=float(self._settings_values["cloud_timeout_s"]),
            ),
            self._packages,
        )
        controller = WorkerThreadController(worker, self)
        worker.planReady.connect(self._on_cloud_plan_ready)
        controller.errorOccurred.connect(self._on_cloud_command_error)
        controller.finished.connect(self._clear_cloud_command_controller)
        self._cloud_command_controller = controller
        self._track_controller("cloud-command", controller, timeout_ms=10000)
        controller.start()

    def _on_cloud_plan_ready(self, plan: object) -> None:
        if not isinstance(plan, ValidatedCommandPlan):
            self._on_cloud_command_error("云端返回了无法识别的计划对象。")
            return
        if not plan.commands:
            reply = plan.reply_text or "没有识别到可安全执行的命令。"
            self.command_center.show_status("需要确认", reply)
            self._enqueue_tts(reply)
            return
        self._pending_command_results.extend(plan.commands)
        self.command_center.set_queue(self._pending_command_results)
        for result in plan.commands:
            self._execute_robot_command(result)
        if plan.reply_text:
            self.command_center.show_status("AI 已执行", plan.reply_text)
            self._enqueue_tts(plan.reply_text)

    def _on_cloud_command_error(self, message: str) -> None:
        LOGGER.warning("cloud command planner unavailable: %s", message)
        acknowledgement = "云端规划不可用，请换用本地短命令。"
        self.command_center.show_status("AI 规划失败", acknowledgement)
        self._enqueue_tts(acknowledgement)

    def _clear_cloud_command_controller(self) -> None:
        self._cloud_command_controller = None
        self._worker_registry.unregister("cloud-command")

    def _drain_command_queue(self) -> None:
        while True:
            result = self._command_queue.pop()
            if result is None:
                break
            self._execute_robot_command(result)

    def _execute_robot_command(self, result: CommandResult) -> None:
        command = result.command
        parameters = result.parameters
        if result.acknowledgement:
            self._enqueue_tts(result.acknowledgement)
        if command is RobotCommand.EMERGENCY_STOP:
            self._stop_command_dance()
            self.stop_robot_imitation()
            self.command_center.play_action("idle")
            self.command_center.show_status("紧急停止", result.acknowledgement)
            return
        if command is RobotCommand.START_IMITATION:
            self.start_robot_imitation(True)
        elif command is RobotCommand.STOP_IMITATION:
            self.stop_robot_imitation()
        elif command in {RobotCommand.PAUSE_IMITATION, RobotCommand.PAUSE_DANCE}:
            if command is RobotCommand.PAUSE_DANCE:
                self._pause_command_dance(True)
            else:
                self.pause_robot_imitation(True)
        elif command in {RobotCommand.RESUME_IMITATION, RobotCommand.RESUME_DANCE}:
            if command is RobotCommand.RESUME_DANCE:
                self._pause_command_dance(False)
            else:
                self.pause_robot_imitation(False)
        elif command is RobotCommand.SET_IMITATION_SCOPE:
            scope = str(parameters.get("scope", "full_body"))
            self.command_center.set_scope(scope)
            self.set_imitation_scope(scope)
        elif command is RobotCommand.SET_MIRROR:
            enabled = bool(parameters.get("enabled", True))
            self.command_center.mirror.setChecked(enabled)
            self.set_imitation_mirror(enabled)
        elif command is RobotCommand.SET_SMOOTHING:
            value = float(parameters.get("smoothing", 0.45))
            self.command_center.set_smoothing(value)
            self.set_imitation_smoothing(value)
        elif command is RobotCommand.RESET_POSE:
            self.reset_robot_pose()
        elif command is RobotCommand.PLAY_DANCE:
            package_id = str(parameters.get("package_id", ""))
            if package_id:
                self._load_command_dance(package_id)
        elif command in {
            RobotCommand.MOVE,
            RobotCommand.RUN,
            RobotCommand.TURN,
            RobotCommand.JUMP,
            RobotCommand.WAVE,
        }:
            self._run_builtin_action(command.value)
        elif command is RobotCommand.CHANGE_SKIN:
            skin = str(parameters.get("skin", "default"))
            self._settings_values["skin"] = skin
            self.command_center.set_skin(skin)
        elif command is RobotCommand.CHANGE_SCENE:
            scene = str(parameters.get("scene", "studio"))
            self._settings_values["scene_theme"] = scene
            self.command_center.set_scene_theme(scene)
        elif command is RobotCommand.SET_CAMERA:
            if "view" in parameters:
                self._settings_values["user_view"] = str(parameters["view"])
            if "preview_size" in parameters:
                self._settings_values["camera_preview_size"] = str(parameters["preview_size"])
            self._apply_renderer_settings()
            self.command_center.show_status("摄像头", "画面配置已更新。")
        elif command is RobotCommand.SET_PLAYBACK_SPEED:
            speed = max(0.5, min(2.0, float(parameters.get("speed", 1.0))))
            if self._command_sequence is not None:
                self._command_clock_base_s = self._command_clock()
                self._command_clock_started = time.monotonic()
                self._session_speed = speed
            self.command_center.show_status("速度", f"播放速度 {speed:.2f}x")
        self._pending_command_results = [
            item for item in self._pending_command_results if item.trace_id != result.trace_id
        ]
        self.command_center.set_queue(self._pending_command_results)

    def _run_builtin_action(self, action: str) -> None:
        mapped = "walk" if action == "move" else action
        self.command_center.play_action(mapped)
        self.command_center.show_status("动作", f"正在执行：{action}")

    def _load_command_dance(self, package_id: str) -> None:
        if self._command_load_controller is not None:
            return
        worker = LoadDancePackageWorker(str(self.paths.motion_packages), package_id)
        controller = WorkerThreadController(worker, self)
        worker.packageReady.connect(self._on_command_package_ready)
        worker.sequenceReady.connect(self._on_command_sequence_ready)
        controller.errorOccurred.connect(self._on_worker_error)
        controller.finished.connect(self._clear_command_load_controller)
        self._command_load_controller = controller
        self._track_controller("command-dance-load", controller, timeout_ms=10000)
        controller.start()

    def _clear_command_load_controller(self) -> None:
        self._command_load_controller = None
        self._worker_registry.unregister("command-dance-load")

    def _on_command_package_ready(self, package: object) -> None:
        if isinstance(package, DancePackage):
            self._command_package = package

    def _on_command_sequence_ready(self, sequence: object) -> None:
        if not isinstance(sequence, PoseSequence):
            return
        self._command_sequence = sequence
        self._command_clock_base_s = 0.0
        self._command_clock_started = time.monotonic()
        self.command_center.play_action("dance")
        self.command_center.show_status(
            "舞蹈",
            f"正在播放《{self._command_package.name if self._command_package else '舞蹈包'}》",
        )
        if not self._clock_timer.isActive():
            self._clock_timer.start()

    def _tick_dance_clock(self) -> None:
        if self._session_active:
            seconds = self._session_clock()
            self.dance_workspace.set_progress_seconds(seconds)
            self._show_reference_seconds(seconds)
            if (
                self._selected_package is not None
                and seconds >= self._selected_package.duration_s
            ):
                self.stop_dance_session(completed=True)
            return
        sequence = self._command_sequence
        if sequence is None:
            self._clock_timer.stop()
            return
        seconds = self._command_clock()
        if seconds >= sequence.duration_s:
            self._stop_command_dance()
            self.command_center.play_action("idle")
            return
        index = max(0, min(len(sequence) - 1, round(seconds * sequence.fps)))
        try:
            self.command_center.set_robot(
                retarget_frame(self._reference_frame_at(sequence, index))
            )
        except (TypeError, ValueError, NormalizationError):
            return

    def _command_clock(self) -> float:
        if not self._command_sequence:
            return 0.0
        if self._session_paused:
            return self._command_clock_base_s
        return self._command_clock_base_s + (
            time.monotonic() - self._command_clock_started
        ) * self._session_speed

    def _pause_command_dance(self, paused: bool) -> None:
        if self._command_sequence is None:
            return
        if paused and not self._session_paused:
            self._command_clock_base_s = self._command_clock()
        elif not paused and self._session_paused:
            self._command_clock_started = time.monotonic()
        self._session_paused = paused
        self.command_center.scene.set_action_paused(paused)

    def _stop_command_dance(self) -> None:
        self._command_sequence = None
        self._command_package = None
        self._command_clock_base_s = 0.0
        self._session_paused = False

    def _stop_dance_session_silently(self) -> None:
        self._countdown_timer.stop()
        self._clock_timer.stop()
        self._session_start_guard_timer.stop()
        self._session_start_generation += 1
        self._session_start_pending = False
        self._session_waiting_for_worker = False
        self._session_active = False
        self._session_paused = False
        self._stop_music()
        if self._live_controller is not None:
            controller = self._live_controller
            self._live_controller = None
            self._worker_registry.unregister("live-training")
            self._stop_controller_async(controller)
        if self._preview_controller is not None:
            controller = self._preview_controller
            self._preview_controller = None
            self._worker_registry.unregister("dance-preview")
            self._stop_controller_async(controller)
        workspace = getattr(self, "dance_workspace", None)
        if workspace is not None and not sip.isdeleted(workspace):
            workspace.set_playing(False)
            workspace.set_action("idle")
        self._reset_session_state()

    # ------------------------------------------------------------------
    # Multimedia, speech, settings, and shutdown
    # ------------------------------------------------------------------
    def _create_media_player(self) -> None:
        if QMediaPlayer is None or QAudioOutput is None:
            return
        player = QMediaPlayer(self)
        audio_output = QAudioOutput(self)
        audio_output.setVolume(1.0)
        player.setAudioOutput(audio_output)
        self._media_player = player
        self._audio_output = audio_output

    def _play_music(self, start_s: float) -> None:
        package = self._selected_package
        if package is None or package.audio_path is None or self._media_player is None:
            return
        player = self._media_player
        if hasattr(player, "setSource"):
            player.setSource(QUrl.fromLocalFile(str(package.audio_path)))
        if hasattr(player, "setPlaybackRate"):
            player.setPlaybackRate(self._session_speed)
        if hasattr(player, "setPosition"):
            player.setPosition(round(max(0.0, start_s) * 1000.0))
        if hasattr(player, "play"):
            player.play()

    def _stop_music(self) -> None:
        player = self._media_player
        if player is not None and hasattr(player, "stop"):
            player.stop()

    def _enqueue_tts(self, text: str) -> None:
        controller = self._speech_controller
        if controller is None or not text:
            return
        worker = controller.worker
        if isinstance(worker, SpeechWorker):
            worker.enqueue(text)

    def _save_settings(self, config: object) -> None:
        if not isinstance(config, Mapping):
            return
        validation = validate_settings(self._settings_values, config)
        if not validation.valid:
            details = "\n".join(issue.message for issue in validation.issues)
            LOGGER.warning("settings validation rejected update: %s", details)
            self.settings_interface.set_save_error(details or "请检查设置内容后重试。")
            self._notify("设置未应用", details or "请检查设置内容后重试。")
            return
        config = validation.values
        previous_camera_index = self._camera_index
        training_running = self._live_controller is not None
        preview_running = self._preview_controller is not None
        imitation_running = self._imitation_controller is not None
        current = dict(self._settings_values)
        for key in current:
            if key in config:
                current[key] = config[key]
        current["model_mode"] = str(current["model_mode"]).lower()
        if current["model_mode"] not in {"skeleton", "body", "overlay"}:
            current["model_mode"] = "overlay"
        current["character_id"] = character_preset(
            str(current.get("character_id", "humanoid_adult"))
        ).key
        current["appearance_theme"] = resolve_theme(str(current["appearance_theme"]))
        raw_model_path = str(current.get("robot_model_path", "")).strip()
        if raw_model_path:
            model_path = Path(raw_model_path).expanduser()
            if (
                not model_path.is_file()
                or model_path.suffix.lower() != ".glb"
                or model_path.stat().st_size > 50 * 1024 * 1024
            ):
                current["robot_model_path"] = ""
                self._notify("模型未应用", "请选择 50 MB 以内的本地 GLB 文件。")
        else:
            current["robot_model_path"] = ""
        current["target_fps"] = max(1.0, min(60.0, float(current["target_fps"])))
        current["render_fps"] = max(30, min(60, int(current["render_fps"])))
        current["pending_timeout_ms"] = max(
            100, min(1000, int(current["pending_timeout_ms"]))
        )
        current["camera_index"] = max(0, int(current["camera_index"]))
        current["camera_width"] = max(320, min(3840, int(current["camera_width"])))
        current["camera_height"] = max(240, min(2160, int(current["camera_height"])))
        current["user_offset_ms"] = max(0, min(300, int(current["user_offset_ms"])))
        current["root_mode"] = str(current["root_mode"]).lower()
        if current["root_mode"] not in {"none", "sway", "planar"}:
            current["root_mode"] = "none"
        self._settings_values = current
        self._camera_index = int(current["camera_index"])
        for secret_key, attribute in (
            ("cloud_api_key", "_api_key"),
            ("tts_api_key", "_tts_api_key"),
            ("asr_api_key", "_asr_api_key"),
        ):
            value = str(config.get(secret_key, "")).strip()
            if value:
                setattr(self, attribute, value)
        self._persist_settings()
        self._apply_renderer_settings()
        self._configure_window_theme()
        self._restart_speech_worker()
        if self._camera_index != previous_camera_index:
            self._restart_streams_after_camera_change(
                training_running=training_running,
                preview_running=preview_running,
                imitation_running=imitation_running,
            )
        self._notify("设置已保存", "云端、摄像头和机器人舞台设置已应用到当前进程。")
        self.settings_interface.mark_saved()

    def _set_theme(self, theme: str) -> None:
        """Preview and retain a theme choice without forcing settings persistence."""
        self._settings_values["appearance_theme"] = resolve_theme(theme)
        self._configure_window_theme()

    def toggle_fullscreen(self) -> None:
        """Toggle the main shell between windowed and full-screen modes."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _restart_streams_after_camera_change(
        self,
        *,
        training_running: bool,
        preview_running: bool,
        imitation_running: bool,
    ) -> None:
        """Restart live camera work only after the old OpenCV handle is closed."""
        if training_running:
            self.stop_dance_session()
            self._notify("摄像头已切换", "本次训练已停止，请确认新画面后重新开始。")
        elif preview_running and self._reference_sequence is not None:
            controller = self._preview_controller
            self._preview_controller = None
            if controller is not None:
                self._stop_controller_async(
                    controller,
                    self._start_dance_preview_worker,
                )
        if imitation_running:
            controller = self._imitation_controller
            self._imitation_controller = None
            self.command_center.set_imitation_running(False)
            self.command_center.play_action("idle")
            if controller is not None:
                self._stop_controller_async(
                    controller,
                    lambda: self.start_robot_imitation(True),
                )

    def _persist_settings(self) -> None:
        SettingsStore.persist(self.settings, self._settings_values)

    def _build_tts_config(self) -> CloudTTSConfig | None:
        if str(self._settings_values["tts_backend"]).lower() != "cloud":
            return None
        return CloudTTSConfig(
            base_url=str(self._settings_values["tts_base_url"]),
            model=str(self._settings_values["tts_model"]),
            voice=str(self._settings_values["tts_voice"]),
            api_key=self._tts_api_key or self._api_key,
            timeout_s=float(self._settings_values["tts_timeout_s"]),
        )

    def _on_worker_error(self, message: str) -> None:
        LOGGER.error("worker error: %s", message)
        self._notify("任务失败", message)
        if self._analysis_controller is not None:
            self._analysis_controller = None
        if self._load_package_controller is not None:
            self._load_package_controller = None
        if self._create_package_controller is not None:
            self._create_package_controller = None
        if self._live_controller is not None:
            self._on_live_finished()
        if self._imitation_controller is not None:
            self._imitation_controller = None
            self.command_center.set_imitation_running(False)

    def _switch_to(self, widget: QWidget) -> None:
        self.switchTo(widget)

    def _switch_to_library(self) -> None:
        self._switch_to(self.library_interface)

    def _notify(self, title: str, content: str) -> None:
        if FLUENT_AVAILABLE and InfoBar is not None and InfoBarPosition is not None:
            InfoBar.info(
                title=title,
                content=content,
                parent=self,
                duration=3500,
                position=InfoBarPosition.TOP,
            )
            return
        QMessageBox.information(self, title, content)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._close_dance_session_window()
        self.stop_all()
        super().closeEvent(event)

    def stop_all(self) -> None:
        registered_ids = {
            id(controller)
            for name in self._worker_registry.names()
            if (controller := self._worker_registry.get(name)) is not None
        }
        wait_failures = self._worker_registry.stop_all()
        if wait_failures:
            LOGGER.error("workers missed shutdown deadline: %s", ", ".join(wait_failures))
        self._countdown_timer.stop()
        self._session_start_guard_timer.stop()
        self._clock_timer.stop()
        self._command_poll_timer.stop()
        self._dance_start_gate.reset()
        self._set_session_state(DanceSessionState.CLOSED, quiet=True)
        self._stop_music()
        camera_controllers = (
            self._preview_controller,
            self._live_controller,
            self._imitation_controller,
        )
        other_controllers = (
            self._analysis_controller,
            self._create_package_controller,
            self._load_package_controller,
            self._command_load_controller,
            self._library_controller,
            self._asset_controller,
            self._voice_controller,
            self._cloud_controller,
            self._live_coach_controller,
            self._cloud_command_controller,
            self._speech_controller,
            self._history_controller,
            self._trash_controller,
            self._batch_controller,
            self._record_controller,
        )
        seen: set[int] = set()
        for controller in (*camera_controllers, *self._retiring_controllers):
            if controller is None or id(controller) in seen or id(controller) in registered_ids:
                continue
            seen.add(id(controller))
            controller.stop(wait_ms=15000)
        for controller in other_controllers:
            if controller is None or id(controller) in seen or id(controller) in registered_ids:
                continue
            seen.add(id(controller))
            controller.stop()
        self.dance_workspace.stop()
        self.command_center.stop()
        QTimer.singleShot(0, self._clear_worker_refs)

    def _clear_worker_refs(self) -> None:
        self._analysis_controller = None
        self._create_package_controller = None
        self._load_package_controller = None
        self._command_load_controller = None
        self._library_controller = None
        self._asset_controller = None
        self._preview_controller = None
        self._live_controller = None
        self._imitation_controller = None
        self._voice_controller = None
        self._cloud_controller = None
        self._live_coach_controller = None
        self._cloud_command_controller = None
        self._speech_controller = None
        self._history_controller = None
        self._trash_controller = None
        self._batch_controller = None
        self._record_controller = None
        self._retiring_controllers.clear()
        self._worker_registry.clear_callbacks()
