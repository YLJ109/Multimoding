"""Robot command center with live imitation and voice command feedback."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.command.intents import CommandResult
from dance_mirror.multimodal.preview import CameraPreviewPacket
from dance_mirror.multimodal.readiness import ReadinessReport
from dance_mirror.view.fluent import (
    CheckBox as QCheckBox,
)
from dance_mirror.view.fluent import (
    ComboBox as QComboBox,
)
from dance_mirror.view.fluent import (
    LineEdit as QLineEdit,
)
from dance_mirror.view.fluent import (
    ListWidget as QListWidget,
)
from dance_mirror.view.fluent import (
    PrimaryPushButton,
)
from dance_mirror.view.fluent import (
    PushButton as QPushButton,
)
from dance_mirror.view.scene_widget import SceneWidget


class CommandCenterInterface(QWidget):
    """Single robot stage plus speech, gestures, and safety controls."""

    imitationRequested = pyqtSignal(bool)
    pauseRequested = pyqtSignal(bool)
    stopRequested = pyqtSignal()
    emergencyStopRequested = pyqtSignal()
    commandSubmitted = pyqtSignal(str)
    scopeChanged = pyqtSignal(str)
    mirrorChanged = pyqtSignal(bool)
    smoothingChanged = pyqtSignal(float)
    resetPoseRequested = pyqtSignal()
    skinChanged = pyqtSignal(str)
    sceneChanged = pyqtSignal(str)
    voiceToggleRequested = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None, *, render_fps: int = 60) -> None:
        super().__init__(parent)
        self.setObjectName("command-center-interface")
        self._running = False
        self._paused = False
        self._build_ui(render_fps)

    def _build_ui(self, render_fps: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        title = QLabel("机器人指挥中心", self)
        title.setObjectName("workspace-title")
        self.status_label = QLabel("待机", self)
        self.status_label.setObjectName("status-pill")
        self.skin = QComboBox(self)
        for label, value in (
            ("默认机器人", "default"),
            ("赛博青", "cyber"),
            ("冠军金", "gold"),
            ("深蓝", "azure"),
            ("警示红", "crimson"),
        ):
            self.skin.addItem(label, value)
        self.skin.currentIndexChanged.connect(
            lambda _index: self.skinChanged.emit(str(self.skin.currentData()))
        )
        self.scene_choice = QComboBox(self)
        for label, value in (
            ("训练舞台", "studio"),
            ("安静宿舍", "dorm"),
            ("霓虹夜场", "neon"),
        ):
            self.scene_choice.addItem(label, value)
        self.scene_choice.currentIndexChanged.connect(
            lambda _index: self.sceneChanged.emit(str(self.scene_choice.currentData()))
        )
        self.emergency_button = QPushButton("紧急停止", self)
        self.emergency_button.setProperty("variant", "danger")
        self.emergency_button.clicked.connect(self.emergencyStopRequested.emit)
        toolbar.addWidget(title)
        toolbar.addWidget(self.status_label)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("皮肤", self))
        toolbar.addWidget(self.skin)
        toolbar.addWidget(QLabel("场景", self))
        toolbar.addWidget(self.scene_choice)
        toolbar.addWidget(self.emergency_button)
        root.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(8)
        self.scene = SceneWidget(self, render_fps=render_fps)
        body.addWidget(self.scene, 1)

        panel = QWidget(self)
        panel.setObjectName("inspector-panel")
        panel.setFixedWidth(310)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(7)

        self.readiness_frame = QFrame(panel)
        self.readiness_frame.setObjectName("status-card")
        readiness_layout = QVBoxLayout(self.readiness_frame)
        self.readiness_title = QLabel("摄像头准备", self.readiness_frame)
        self.readiness_title.setObjectName("section-title")
        self.readiness_detail = QLabel("等待全身进入画面。", self.readiness_frame)
        self.readiness_detail.setWordWrap(True)
        self.readiness_detail.setObjectName("coach-label")
        readiness_layout.addWidget(self.readiness_title)
        readiness_layout.addWidget(self.readiness_detail)
        panel_layout.addWidget(self.readiness_frame)

        queue_title = QLabel("命令队列", panel)
        queue_title.setObjectName("section-title")
        self.queue_list = QListWidget(panel)
        self.queue_list.setMaximumHeight(132)
        panel_layout.addWidget(queue_title)
        panel_layout.addWidget(self.queue_list)

        controls = QFrame(panel)
        controls.setObjectName("surface-card")
        controls_layout = QVBoxLayout(controls)
        row_one = QHBoxLayout()
        self.start_button = PrimaryPushButton("开始模仿", controls)
        self.start_button.clicked.connect(self._handle_action)
        self.pause_button = QPushButton("暂停", controls)
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button = self.start_button
        row_one.addWidget(self.start_button)
        row_one.addWidget(self.pause_button)
        controls_layout.addLayout(row_one)

        self.scope = QComboBox(controls)
        for label, value in (
            ("全身", "full_body"),
            ("上半身", "upper_body"),
            ("下半身", "lower_body"),
            ("手部", "hands"),
            ("头部", "head"),
        ):
            self.scope.addItem(label, value)
        self.scope.currentIndexChanged.connect(
            lambda _index: self.scopeChanged.emit(str(self.scope.currentData()))
        )
        self.mirror = QCheckBox("镜像动作", controls)
        self.mirror.setChecked(True)
        self.mirror.toggled.connect(self.mirrorChanged.emit)
        self.smoothing = QComboBox(controls)
        for label, value in (("灵敏", 0.2), ("标准", 0.45), ("平滑", 0.72), ("强平滑", 0.86)):
            self.smoothing.addItem(label, value)
        self.smoothing.setCurrentIndex(1)
        self.smoothing.currentIndexChanged.connect(
            lambda _index: self.smoothingChanged.emit(float(self.smoothing.currentData()))
        )
        self.reset_button = QPushButton("重置姿势", controls)
        self.reset_button.clicked.connect(self.resetPoseRequested.emit)
        self.camera_reset_button = QPushButton("视角复位", controls)
        self.camera_reset_button.setProperty("variant", "ghost")
        self.camera_reset_button.setToolTip("左键旋转、右键或中键平移、滚轮缩放、双击复位")
        self.camera_reset_button.clicked.connect(self.scene.reset_camera)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("模仿范围", controls))
        scope_row.addWidget(self.scope, 1)
        controls_layout.addLayout(scope_row)
        controls_layout.addWidget(self.mirror)
        smoothing_row = QHBoxLayout()
        smoothing_row.addWidget(QLabel("运动平滑", controls))
        smoothing_row.addWidget(self.smoothing, 1)
        controls_layout.addLayout(smoothing_row)
        controls_layout.addWidget(self.reset_button)
        controls_layout.addWidget(self.camera_reset_button)
        panel_layout.addWidget(controls)

        voice_title = QLabel("实时语音", panel)
        voice_title.setObjectName("section-title")
        self.voice_toggle = QCheckBox("启用云端语音识别", panel)
        self.voice_toggle.toggled.connect(self.voiceToggleRequested.emit)
        self.voice_status = QLabel("语音未启动，可输入文字命令。", panel)
        self.voice_status.setWordWrap(True)
        self.voice_status.setObjectName("metric-caption")
        panel_layout.addWidget(voice_title)
        panel_layout.addWidget(self.voice_toggle)
        panel_layout.addWidget(self.voice_status)

        self.transcript = QLabel("你说：--", panel)
        self.transcript.setWordWrap(True)
        self.transcript.setObjectName("transcript-card")
        self.intent_label = QLabel("意图：--", panel)
        self.intent_label.setWordWrap(True)
        self.intent_label.setObjectName("metric-caption")
        panel_layout.addWidget(self.transcript)
        panel_layout.addWidget(self.intent_label)
        panel_layout.addStretch(1)
        body.addWidget(panel)
        root.addLayout(body, 1)

        command_row = QHBoxLayout()
        self.command_edit = QLineEdit(self)
        self.command_edit.setPlaceholderText("例如：开始模仿我，只模仿上半身，减少抖动，换赛博皮肤")
        self.command_edit.returnPressed.connect(self._submit_command)
        self.command_button = PrimaryPushButton("执行命令", self)
        self.command_button.clicked.connect(self._submit_command)
        command_row.addWidget(self.command_edit, 1)
        command_row.addWidget(self.command_button)
        root.addLayout(command_row)

        self.preview = self.scene.camera_preview

    @property
    def running(self) -> bool:
        return self._running

    def set_camera_packet(self, packet: CameraPreviewPacket) -> None:
        self.scene.set_camera_packet(packet)

    def clear_camera(self) -> None:
        self.scene.clear_camera()

    def set_robot(self, skeleton: object) -> None:
        self.scene.set_robot(skeleton)  # type: ignore[arg-type]

    def set_readiness(self, report: ReadinessReport) -> None:
        self.readiness_title.setText(f"全身就位度 {report.score * 100:.0f}%")
        self.readiness_detail.setText(report.message)

    def set_imitation_running(self, running: bool, paused: bool = False) -> None:
        self._running = running
        self._paused = paused
        self.start_button.setText("停止" if running else "开始模仿")
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(running)
        self.pause_button.setText("继续" if paused else "暂停")
        self.status_label.setText("已暂停" if paused else ("模仿中" if running else "待机"))
        self.scene.set_action_paused(paused)

    def set_scope(self, scope: str) -> None:
        index = self.scope.findData(scope)
        if index >= 0:
            self.scope.setCurrentIndex(index)
        self.scene.set_imitation_scope(scope)

    def set_smoothing(self, value: float) -> None:
        index = self.smoothing.findData(value)
        if index >= 0:
            self.smoothing.setCurrentIndex(index)

    def set_voice_enabled(self, enabled: bool) -> None:
        self.voice_toggle.blockSignals(True)
        self.voice_toggle.setChecked(enabled)
        self.voice_toggle.blockSignals(False)

    def set_voice_status(self, text: str) -> None:
        self.voice_status.setText(text)

    def append_transcript(self, text: str, final: bool = True) -> None:
        prefix = "你说" if final else "识别中"
        self.transcript.setText(f"{prefix}：{text or '--'}")

    def set_command_result(self, result: CommandResult) -> None:
        parameters = ", ".join(f"{key}={value}" for key, value in result.parameters.items())
        detail = result.command.value
        if parameters:
            detail += f" ({parameters})"
        self.intent_label.setText(f"意图：{detail}\n{result.acknowledgement}")

    def set_queue(self, commands: Sequence[CommandResult]) -> None:
        self.queue_list.clear()
        for command in commands[-8:]:
            self.queue_list.addItem(
                f"[{int(command.priority):03d}] {command.command.value}  {command.acknowledgement}"
            )

    def show_status(self, title: str, detail: str) -> None:
        self.status_label.setText(title)
        self.intent_label.setText(detail)

    def set_quality(self, quality: dict[str, object]) -> None:
        fps = float(quality.get("fps", 0.0))
        latency = float(quality.get("inference_ms", 0.0))
        scope = str(quality.get("scope", "full_body"))
        self.status_label.setText(f"模仿中 | {scope} | {fps:.1f} FPS | {latency:.0f} ms")

    def set_safe_hold(self, active: bool) -> None:
        if active:
            self.status_label.setText("安全保持")
            self.readiness_detail.setText("摄像头姿态丢失，机器人保持安全姿势。")
        else:
            self.status_label.setText("模仿中" if self._running else "待机")

    def set_skin(self, name: str) -> None:
        index = self.skin.findData(name)
        if index >= 0:
            self.skin.setCurrentIndex(index)
        self.scene.set_skin(name)

    def set_scene_theme(self, name: str) -> None:
        index = self.scene_choice.findData(name)
        if index >= 0:
            self.scene_choice.setCurrentIndex(index)
        self.scene.set_scene_theme(name)

    def set_low_power(self, enabled: bool) -> None:
        self.scene.set_low_power(enabled)

    def set_model_mode(self, mode: str) -> None:
        self.scene.set_model_mode(mode)

    def play_action(self, name: str) -> None:
        self.scene.play_action(name)

    def stop(self) -> None:
        self.scene.stop()

    def _handle_action(self) -> None:
        if self._running:
            self.stopRequested.emit()
            return
        self.imitationRequested.emit(True)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pauseRequested.emit(self._paused)
        self.set_imitation_running(self._running, self._paused)

    def _submit_command(self) -> None:
        text = self.command_edit.text().strip()
        if not text:
            return
        self.command_edit.clear()
        self.commandSubmitted.emit(text)
