"""Gamified dance-learning workspace built around one robot stage."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.domain.types import TrainingUpdate
from dance_mirror.multimodal.preview import CameraPreviewPacket
from dance_mirror.storage.motion_library import DancePackage
from dance_mirror.view.fluent import (
    ComboBox as QComboBox,
)
from dance_mirror.view.fluent import (
    PrimaryPushButton,
)
from dance_mirror.view.fluent import (
    ProgressBar as QProgressBar,
)
from dance_mirror.view.fluent import (
    PushButton as QPushButton,
)
from dance_mirror.view.fluent import (
    Slider as QSlider,
)
from dance_mirror.view.scene_widget import SceneWidget


class _MetricCard(QFrame):
    def __init__(self, title: str, value: str = "--", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metric-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        label = QLabel(title, self)
        label.setObjectName("metric-label")
        self.value_label = QLabel(value, self)
        self.value_label.setObjectName("metric-value")
        layout.addWidget(label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class DanceWorkspaceInterface(QWidget):
    """Music-master-clock training page with countdown and score HUD."""

    startRequested = pyqtSignal()
    pauseRequested = pyqtSignal(bool)
    stopRequested = pyqtSignal()
    speedChanged = pyqtSignal(float)
    replayWeakSegmentRequested = pyqtSignal(float, float)
    backToLibraryRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, render_fps: int = 60) -> None:
        super().__init__(parent)
        self.setObjectName("dance-workspace-interface")
        self._package: DancePackage | None = None
        self._playing = False
        self._armed = False
        self._duration_s = 0.0
        self._build_ui(render_fps)

    def _build_ui(self, render_fps: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(9)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.back_button = QPushButton("返回舞蹈包库", self)
        self.back_button.setProperty("variant", "ghost")
        self.back_button.setText("完成并关闭")
        self.back_button.setToolTip("结算完成后关闭训练窗口并返回舞蹈包库")
        self.back_button.setVisible(False)
        self.back_button.clicked.connect(self.backToLibraryRequested.emit)
        self.title = QLabel("未选择舞蹈包", self)
        self.title.setObjectName("workspace-title")
        self.clock = QLabel("00:00 / 00:00", self)
        self.clock.setObjectName("mono-muted")
        self.bpm_label = QLabel("-- BPM", self)
        self.bpm_label.setObjectName("metric-caption")
        self.speed = QComboBox(self)
        for label, value in (
            ("0.5x", 0.5),
            ("0.75x", 0.75),
            ("1.0x", 1.0),
            ("1.25x", 1.25),
            ("1.5x", 1.5),
            ("2.0x", 2.0),
        ):
            self.speed.addItem(label, value)
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(
            lambda _index: self.speedChanged.emit(float(self.speed.currentData()))
        )
        self.start_button = PrimaryPushButton("开始", self)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._handle_action)
        self.pause_button = QPushButton("暂停", self)
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button = self.start_button
        self.camera_reset_button = QPushButton("视角复位", self)
        self.camera_reset_button.setProperty("variant", "ghost")
        self.camera_reset_button.setToolTip("左键旋转、右键或中键平移、滚轮缩放、双击复位")
        self.view_mode = QComboBox(self)
        self.view_mode.addItem("骨架 + 人体", "overlay")
        self.view_mode.addItem("仅骨架", "skeleton")
        self.view_mode.addItem("仅人体", "body")
        self.camera_toggle_button = QPushButton("收起摄像头", self)
        self.camera_toggle_button.setProperty("variant", "ghost")
        self.camera_toggle_button.setToolTip("收起或恢复左上角二维摄像头叠加")
        header.addWidget(self.title, 1)
        header.addWidget(self.clock)
        header.addWidget(self.bpm_label)
        header.addWidget(self.back_button)
        controls.addWidget(QLabel("节奏", self))
        controls.addWidget(self.speed)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addSpacing(10)
        controls.addWidget(self.view_mode)
        controls.addWidget(self.camera_reset_button)
        controls.addWidget(self.camera_toggle_button)
        controls.addStretch(1)
        root.addLayout(header)
        root.addLayout(controls)

        body = QHBoxLayout()
        body.setSpacing(8)
        self.scene = SceneWidget(self, render_fps=render_fps)
        self.camera_reset_button.clicked.connect(self.scene.reset_camera)
        self.view_mode.currentIndexChanged.connect(
            lambda _index: self.scene.set_model_mode(str(self.view_mode.currentData()))
        )
        self.camera_toggle_button.clicked.connect(self._toggle_camera_overlay)
        body.addWidget(self.scene, 1)

        hud = QWidget(self)
        hud.setObjectName("hud-panel")
        hud.setFixedWidth(304)
        hud_layout = QVBoxLayout(hud)
        hud_layout.setContentsMargins(0, 0, 0, 0)
        hud_layout.setSpacing(7)

        status_frame = QFrame(hud)
        status_frame.setObjectName("status-card")
        status_layout = QVBoxLayout(status_frame)
        self.phase_label = QLabel("等待开始", status_frame)
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_label.setObjectName("phase-label")
        self.countdown_label = QLabel("准备", status_frame)
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setObjectName("countdown-label")
        self.coach_label = QLabel("选择舞蹈包后开始准备。", status_frame)
        self.coach_label.setWordWrap(True)
        self.coach_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.coach_label.setObjectName("coach-label")
        status_layout.addWidget(self.phase_label)
        status_layout.addWidget(self.countdown_label)
        status_layout.addWidget(self.coach_label)
        hud_layout.addWidget(status_frame)

        metrics = QGridLayout()
        metrics.setSpacing(7)
        self.score_card = _MetricCard("总分", "--", hud)
        self.combo_card = _MetricCard("连击", "0", hud)
        self.accuracy_card = _MetricCard("准确度", "--", hud)
        self.coverage_card = _MetricCard("覆盖率", "--", hud)
        metrics.addWidget(self.score_card, 0, 0)
        metrics.addWidget(self.combo_card, 0, 1)
        metrics.addWidget(self.accuracy_card, 1, 0)
        metrics.addWidget(self.coverage_card, 1, 1)
        hud_layout.addLayout(metrics)

        body_parts = QFrame(hud)
        body_parts.setObjectName("surface-card")
        parts_layout = QVBoxLayout(body_parts)
        parts_title = QLabel("分部位得分", body_parts)
        parts_title.setObjectName("section-title")
        parts_layout.addWidget(parts_title)
        self.part_labels: dict[str, QLabel] = {}
        for key, display in (
            ("left_arm", "左臂"),
            ("right_arm", "右臂"),
            ("left_leg", "左腿"),
            ("right_leg", "右腿"),
            ("torso", "躯干"),
            ("head", "头部"),
        ):
            row = QHBoxLayout()
            name = QLabel(display, body_parts)
            name.setFixedWidth(48)
            bar = QProgressBar(body_parts)
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            value = QLabel("--", body_parts)
            value.setFixedWidth(40)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(value)
            parts_layout.addLayout(row)
            self.part_labels[key] = value
        hud_layout.addWidget(body_parts)

        self.beat_label = QLabel("节拍：--", hud)
        self.beat_label.setObjectName("metric-caption")
        self.sync_label = QLabel("延迟：-- ms", hud)
        self.sync_label.setObjectName("metric-caption")
        hud_layout.addWidget(self.beat_label)
        hud_layout.addWidget(self.sync_label)
        hud_layout.addStretch(1)
        body.addWidget(hud)
        root.addLayout(body, 1)

        timeline_row = QHBoxLayout()
        self.timeline = QSlider(self)
        self.timeline.setOrientation(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 1000)
        self.timeline.setEnabled(False)
        self.timeline.sliderMoved.connect(self._seek)
        self.weak_button = QPushButton("回练薄弱片段", self)
        self.weak_button.setEnabled(False)
        self.weak_button.clicked.connect(lambda: self.replayWeakSegmentRequested.emit(0.0, 0.0))
        timeline_row.addWidget(self.timeline, 1)
        timeline_row.addWidget(self.weak_button)
        root.addLayout(timeline_row)

        self.report_label = QLabel("", self)
        self.report_label.setWordWrap(True)
        self.report_label.setObjectName("report-card")
        root.addWidget(self.report_label)

        self.preview = self.scene.camera_preview

    @property
    def package(self) -> DancePackage | None:
        return self._package

    @property
    def playing(self) -> bool:
        return self._playing

    def set_package(self, package: DancePackage) -> None:
        self._package = package
        self._duration_s = max(0.0, package.duration_s)
        self.title.setText(package.name)
        self.bpm_label.setText(f"{package.gameplay.bpm:.0f} BPM")
        self.speed.setCurrentIndex(2)
        self.start_button.setEnabled(True)
        self._set_action_state(armed=False, playing=False)
        self.back_button.setVisible(False)
        self.timeline.setEnabled(True)
        self.clock.setText(f"00:00 / {self._format_time(self._duration_s)}")
        self.phase_label.setText("准备")
        self.countdown_label.setText("就位")
        self.coach_label.setText("全身进入左上角画面，确认后开始 3、2、1 倒计时。")
        self.report_label.setText("")

    def set_camera_packet(self, packet: CameraPreviewPacket) -> None:
        self.scene.set_camera_packet(packet)
        if packet.person_count <= 1:
            self.coach_label.setText(
                f"全身就位度 {packet.readiness * 100:.0f}%。保持头顶和双脚可见。"
            )

    def clear_camera(self) -> None:
        self.scene.clear_camera()

    def set_playing(self, playing: bool, paused: bool = False) -> None:
        self._playing = playing
        self._armed = bool(playing)
        self.pause_button.setEnabled(playing)
        self._set_action_state(armed=playing, playing=playing)
        self.pause_button.setText("继续" if paused else "暂停")
        if playing:
            self.phase_label.setText("暂停" if paused else "跟舞中")
            self.scene.set_action_paused(paused)

    def set_armed(self, armed: bool) -> None:
        """Reflect the preflight gate on the shared start/stop action."""
        self._armed = bool(armed)
        self._set_action_state(armed=self._armed, playing=self._playing)

    def _set_action_state(self, *, armed: bool, playing: bool) -> None:
        active = bool(armed or playing)
        self.start_button.setText("停止" if active else "开始")
        self.start_button.setEnabled(active or self._package is not None)
        self.start_button.setToolTip(
            "停止当前准备或训练" if active else "开始全身就位与 OK 手势确认"
        )

    def show_countdown(self, value: int | str) -> None:
        text = str(value)
        self.countdown_label.setText(text)
        self.phase_label.setText("准备开始")
        self.scene.set_status(f"倒计时 {text}" if text.isdigit() else text)

    def set_progress_seconds(self, value_s: float) -> None:
        if self._duration_s <= 0:
            self.timeline.setValue(0)
            self.clock.setText("00:00 / 00:00")
            return
        bounded = max(0.0, min(self._duration_s, float(value_s)))
        if not self.timeline.isSliderDown():
            self.timeline.setValue(round(bounded / self._duration_s * 1000))
        self.clock.setText(
            f"{self._format_time(bounded)} / {self._format_time(self._duration_s)}"
        )

    def apply_update(self, update: TrainingUpdate) -> None:
        self.score_card.set_value(f"{update.score.overall:.1f}")
        cue = update.cue
        if cue is not None:
            self.coach_label.setText(cue.text)
            self.scene.set_status(cue.text)
        deviations = update.score.deviations
        self.accuracy_card.set_value(f"{update.score.overall:.0f}%")
        visible = [item for item in deviations if item.confidence >= 0.25]
        coverage = len(visible) / max(1, len(deviations))
        self.coverage_card.set_value(f"{coverage * 100:.0f}%")
        if update.score.overall >= 75.0:
            current = int(self.combo_card.value_label.text() or "0")
            self.combo_card.set_value(str(current + 1))
        else:
            self.combo_card.set_value("0")
        part_scores = self._body_part_scores(deviations)
        for key, label in self.part_labels.items():
            score = part_scores.get(key)
            label.setText("--" if score is None else f"{score:.0f}")

    def set_sync_status(self, snapshot: object) -> None:
        delay = 0.0
        confidence = 0.0
        if hasattr(snapshot, "applied_delay_s"):
            delay = float(snapshot.applied_delay_s) * 1000.0
        if hasattr(snapshot, "confidence"):
            confidence = float(snapshot.confidence)
        self.sync_label.setText(f"延迟：{delay:.0f} ms  同步 {confidence:.0%}")

    def set_beat(self, text: str) -> None:
        self.beat_label.setText(f"节拍：{text}")

    def set_quality(self, text: str) -> None:
        self.coach_label.setText(text)

    def set_live_coach(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.coach_label.setText(clean)
            self.scene.set_status(clean)

    def set_report(self, text: str) -> None:
        self.report_label.setText(text)
        has_report = bool(str(text).strip())
        self.back_button.setVisible(has_report)
        self.back_button.setEnabled(has_report)

    def set_low_power(self, enabled: bool) -> None:
        self.scene.set_low_power(enabled)

    def set_root_motion(self, mode: str) -> None:
        self.scene.set_root_motion(mode)

    def set_model_mode(self, mode: str) -> None:
        self.scene.set_model_mode(mode)

    def set_skin(self, name: str) -> None:
        self.scene.set_skin(name)

    def set_scene_theme(self, name: str) -> None:
        self.scene.set_scene_theme(name)

    def _toggle_camera_overlay(self) -> None:
        collapsed = self.scene.camera_preview.size_mode == "collapsed"
        mode = "medium" if collapsed else "collapsed"
        self.scene.set_camera_size_mode(mode)
        self.camera_toggle_button.setText("显示摄像头" if collapsed else "收起摄像头")

    def set_reference(self, skeleton: object) -> None:
        self.scene.set_robot(skeleton)  # type: ignore[arg-type]

    def set_action(self, name: str) -> None:
        self.scene.play_action(name)

    def stop(self) -> None:
        self.scene.stop()

    def _handle_action(self) -> None:
        if self._armed or self._playing:
            self.stopRequested.emit()
            return
        self.startRequested.emit()

    def _toggle_pause(self) -> None:
        paused = self.pause_button.text() == "暂停"
        self.pauseRequested.emit(paused)

    def _seek(self, value: int) -> None:
        if self._duration_s > 0:
            self.set_progress_seconds(value / 1000.0 * self._duration_s)

    @staticmethod
    def _format_time(seconds: float) -> str:
        value = max(0, round(seconds))
        return f"{value // 60:02d}:{value % 60:02d}"

    @staticmethod
    def _body_part_scores(deviations: list[object]) -> dict[str, float]:
        groups = {
            "left_arm": ("left_elbow", "left_wrist"),
            "right_arm": ("right_elbow", "right_wrist"),
            "left_leg": ("left_knee", "left_ankle"),
            "right_leg": ("right_knee", "right_ankle"),
            "torso": ("shoulder", "hip", "torso"),
            "head": ("head", "nose", "neck"),
        }
        output: dict[str, float] = {}
        for key, fragments in groups.items():
            values = [
                float(getattr(item, "score", 0.0))
                for item in deviations
                if any(fragment in str(getattr(item, "feature", "")) for fragment in fragments)
            ]
            if values:
                output[key] = sum(values) / len(values)
        return output
