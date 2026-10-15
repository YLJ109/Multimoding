"""Settings page for model, camera, privacy, and renderer options."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.capture.devices import CameraDevice, list_camera_devices
from dance_mirror.coaching.providers import PROVIDER_PRESETS, provider_preset
from dance_mirror.config import AppPaths
from dance_mirror.renderer.character_catalog import (
    CHARACTER_PRESETS,
    CharacterStore,
    character_preset,
)
from dance_mirror.view.design_tokens import palette_for
from dance_mirror.view.fluent import (
    CheckBox as QCheckBox,
)
from dance_mirror.view.fluent import (
    ComboBox as QComboBox,
)
from dance_mirror.view.fluent import (
    DoubleSpinBox as QDoubleSpinBox,
)
from dance_mirror.view.fluent import (
    EditableComboBox,
    PrimaryPushButton,
)
from dance_mirror.view.fluent import (
    LineEdit as QLineEdit,
)
from dance_mirror.view.fluent import (
    ProgressBar as QProgressBar,
)
from dance_mirror.view.fluent import (
    PushButton as QPushButton,
)
from dance_mirror.view.fluent import (
    ScrollArea as QScrollArea,
)
from dance_mirror.view.fluent import (
    SpinBox as QSpinBox,
)
from dance_mirror.workers.base import WorkerThreadController
from dance_mirror.workers.character import CharacterDownloadWorker


class SettingsInterface(QWidget):
    """Collect runtime settings while keeping secrets in memory only."""

    settingsSaved = pyqtSignal(object)
    themePreviewRequested = pyqtSignal(str)
    fullscreenToggleRequested = pyqtSignal()
    capabilityTestRequested = pyqtSignal(str, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        character_root: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settings-interface")
        self._character_store = CharacterStore(
            self._default_character_root() if character_root is None else character_root
        )
        self._downloaded_character_key: str | None = None
        self._character_controller: WorkerThreadController | None = None
        self._dirty = False
        self._loading = False
        self._groups: list[QGroupBox] = []
        self._group_levels: dict[QGroupBox, str] = {}
        self._connection_labels: dict[str, QLabel] = {}


        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(32, 24, 32, 12)
        header_layout.setSpacing(9)
        title = QLabel("设置", header)
        title.setObjectName("page-title")
        subtitle = QLabel(
            "基础项直接可见；高级项按需展开。API Key 只保留在当前进程内。",
            header,
        )
        subtitle.setObjectName("page-subtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        filter_row = QHBoxLayout()
        self.search_input = QLineEdit(header)
        self.search_input.setPlaceholderText("搜索设置项，例如摄像头、模型、云端、语音")
        self.advanced_toggle = QCheckBox("显示高级设置", header)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.advanced_toggle)
        header_layout.addLayout(filter_row)
        shell.addWidget(header)

        scroll = QScrollArea(self)
        if hasattr(scroll, "enableTransparentBackground"):
            scroll.enableTransparentBackground()
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 8, 32, 22)
        root.setSpacing(14)
        columns = QHBoxLayout()
        columns.setSpacing(14)
        left_column = QVBoxLayout()
        left_column.setSpacing(14)
        right_column = QVBoxLayout()
        right_column.setSpacing(14)
        columns.addLayout(left_column, 1)
        columns.addLayout(right_column, 1)

        cloud_group = self._build_cloud_group(content)
        appearance_group = self._build_appearance_group(content)
        asr_group = self._build_asr_group(content)
        tts_group = self._build_tts_group(content)
        vision_group = self._build_vision_group(content)
        camera_group = self._build_camera_group(content)
        training_group = self._build_training_group(content)
        renderer_group = self._build_renderer_group(content)
        self._groups = [
            appearance_group,
            training_group,
            camera_group,
            cloud_group,
            asr_group,
            tts_group,
            vision_group,
            renderer_group,
        ]
        self._group_levels = {
            cloud_group: "basic",
            appearance_group: "basic",
            asr_group: "advanced",
            tts_group: "advanced",
            vision_group: "advanced",
            camera_group: "basic",
            training_group: "basic",
            renderer_group: "advanced",
        }
        for index, group in enumerate(self._groups):
            target = left_column if index % 2 == 0 else right_column
            target.addWidget(group)
        left_column.addStretch(1)
        right_column.addStretch(1)
        root.addLayout(columns, 1)
        self._refresh_character_presets()
        self._apply_provider_preset()

        note = QLabel(
            "隐私边界：连续摄像头画面不会上传。云端只接收结构化训练摘要，"
            "API Key 不写入 QSettings、日志、数据库或动作包。"
        )
        note.setWordWrap(True)
        note.setObjectName("page-subtitle")
        root.addWidget(note)
        scroll.setWidget(content)
        shell.addWidget(scroll, 1)

        footer = QWidget(self)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(32, 10, 32, 12)
        self.dirty_label = QLabel("设置已同步", footer)
        self.dirty_label.setObjectName("metric-caption")
        self.restore_button = QPushButton("恢复默认", footer)
        self.restore_button.setProperty("variant", "ghost")
        self.restore_button.clicked.connect(self._restore_defaults)
        self.save_button = PrimaryPushButton("保存设置", footer)
        self.save_button.clicked.connect(self._save)
        footer_layout.addWidget(self.dirty_label, 1)
        footer_layout.addWidget(self.restore_button)
        footer_layout.addWidget(self.save_button)
        shell.addWidget(footer)

        self.search_input.textChanged.connect(self._apply_settings_filter)
        self.advanced_toggle.toggled.connect(self._apply_settings_filter)
        self._connect_dirty_tracking()
        self._apply_settings_filter()

    def _build_appearance_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("外观与窗口", parent)
        form = QFormLayout(group)
        self.appearance_theme = QComboBox()
        self.appearance_theme.addItem("深色科技风", "dark")
        self.appearance_theme.addItem("浅色科技风", "light")
        self.appearance_theme.currentIndexChanged.connect(
            lambda _index: self.themePreviewRequested.emit(self._combo_data(self.appearance_theme))
        )
        self.fullscreen_on_start = QCheckBox("保存设置后立即切换为全屏模式")
        self.fullscreen_on_start.setToolTip("下次启动 DanceMirror 时自动进入全屏")
        self.fullscreen_toggle_button = QPushButton("立即切换全屏 / 窗口化")
        self.fullscreen_toggle_button.setProperty("variant", "ghost")
        self.fullscreen_toggle_button.setToolTip("与 F11 快捷键效果相同")
        self.fullscreen_toggle_button.clicked.connect(self.fullscreenToggleRequested.emit)
        form.addRow("界面主题", self.appearance_theme)
        form.addRow("全屏模式", self.fullscreen_on_start)
        form.addRow("", self.fullscreen_toggle_button)
        return group

    def _build_cloud_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("云端语言模型", parent)
        form = QFormLayout(group)
        self.provider = QComboBox()
        for preset in PROVIDER_PRESETS:
            self.provider.addItem(preset.name, preset.key)
        self.provider_capabilities = QLabel()
        self.provider_capabilities.setWordWrap(True)
        self.provider_capabilities.setObjectName("metric-caption")
        self.llm_base_url = QLineEdit()
        self.llm_base_url.setText("https://api.openai.com/v1")
        self.llm_model = QLineEdit()
        self.llm_model.setText("gpt-4o-mini")
        self.llm_api_key = QLineEdit()
        self.llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_api_key.setPlaceholderText("仅当前进程使用，不写入磁盘")
        self.llm_timeout = QDoubleSpinBox()
        self.llm_timeout.setRange(3.0, 120.0)
        self.llm_timeout.setValue(30.0)
        self.llm_timeout.setSuffix(" 秒")
        form.addRow("服务预设", self.provider)
        form.addRow("已声明能力", self.provider_capabilities)
        form.addRow("Base URL", self.llm_base_url)
        form.addRow("模型", self.llm_model)
        form.addRow("API Key", self.llm_api_key)
        form.addRow("超时", self.llm_timeout)
        self.provider.currentIndexChanged.connect(self._apply_provider_preset)
        self.llm_test_button = QPushButton("测试语言模型连接", group)
        self.llm_test_button.setProperty("variant", "ghost")
        self.llm_test_button.clicked.connect(lambda: self._request_capability_test("llm"))
        self.llm_connection = QLabel("尚未测试。", group)
        self.llm_connection.setWordWrap(True)
        self.llm_connection.setObjectName("metric-caption")
        self._connection_labels["llm"] = self.llm_connection
        form.addRow("", self.llm_test_button)
        form.addRow("连接状态", self.llm_connection)
        return group

    def _apply_provider_preset(self, _index: int = 0) -> None:
        preset = provider_preset(str(self.provider.currentData() or "custom"))
        self.provider_capabilities.setText(f"{preset.capabilities}。{preset.note}")
        if preset.key == "custom":
            return
        if preset.llm_base_url:
            self.llm_base_url.setText(preset.llm_base_url)
        if preset.llm_model:
            self.llm_model.setText(preset.llm_model)
        if preset.asr_base_url and preset.asr_model:
            self.asr_base_url.setText(preset.asr_base_url)
            self.asr_model.setText(preset.asr_model)
            self.asr_enabled.setChecked(True)
        else:
            self.asr_enabled.setChecked(False)
        if preset.tts_base_url and preset.tts_model:
            self.tts_backend.setCurrentIndex(self.tts_backend.findData("cloud"))
            self.tts_base_url.setText(preset.tts_base_url)
            self.tts_model.setText(preset.tts_model)
            if preset.tts_voice:
                self.tts_voice.setText(preset.tts_voice)
        else:
            self.tts_backend.setCurrentIndex(self.tts_backend.findData("local"))

    def _build_asr_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("云端语音识别", parent)
        form = QFormLayout(group)
        self.asr_enabled = QCheckBox("启用实时语音指令")
        self.asr_base_url = QLineEdit()
        self.asr_base_url.setText("https://api.openai.com/v1")
        self.asr_model = QLineEdit()
        self.asr_model.setText("whisper-1")
        self.asr_language = QLineEdit()
        self.asr_language.setText("zh")
        self.asr_api_key = QLineEdit()
        self.asr_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.asr_api_key.setPlaceholderText("留空时复用语言模型 API Key")
        form.addRow("", self.asr_enabled)
        form.addRow("Base URL", self.asr_base_url)
        form.addRow("模型", self.asr_model)
        form.addRow("语言", self.asr_language)
        form.addRow("API Key", self.asr_api_key)
        self.asr_test_button = QPushButton("测试语音识别连接", group)
        self.asr_test_button.setProperty("variant", "ghost")
        self.asr_test_button.clicked.connect(lambda: self._request_capability_test("asr"))
        self.asr_connection = QLabel("尚未测试。", group)
        self.asr_connection.setWordWrap(True)
        self.asr_connection.setObjectName("metric-caption")
        self._connection_labels["asr"] = self.asr_connection
        form.addRow("", self.asr_test_button)
        form.addRow("连接状态", self.asr_connection)
        return group

    def _build_tts_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("语音提醒", parent)
        form = QFormLayout(group)
        self.tts_enabled = QCheckBox("启用即时语音纠错")
        self.tts_enabled.setChecked(True)
        self.tts_backend = QComboBox()
        self.tts_backend.addItem("Windows 本地语音", "local")
        self.tts_backend.addItem("云端 TTS", "cloud")
        self.tts_base_url = QLineEdit()
        self.tts_base_url.setText("https://api.openai.com/v1")
        self.tts_model = QLineEdit()
        self.tts_model.setText("gpt-4o-mini-tts")
        self.tts_voice = QLineEdit()
        self.tts_voice.setText("alloy")
        self.tts_api_key = QLineEdit()
        self.tts_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.tts_api_key.setPlaceholderText("留空时复用云端语言模型 API Key")
        self.tts_timeout = QDoubleSpinBox()
        self.tts_timeout.setRange(3.0, 120.0)
        self.tts_timeout.setValue(30.0)
        self.tts_timeout.setSuffix(" 秒")
        form.addRow("", self.tts_enabled)
        form.addRow("后端", self.tts_backend)
        form.addRow("Base URL", self.tts_base_url)
        form.addRow("模型", self.tts_model)
        form.addRow("音色", self.tts_voice)
        form.addRow("API Key", self.tts_api_key)
        form.addRow("超时", self.tts_timeout)
        self.tts_test_button = QPushButton("测试语音合成连接", group)
        self.tts_test_button.setProperty("variant", "ghost")
        self.tts_test_button.clicked.connect(lambda: self._request_capability_test("tts"))
        self.tts_connection = QLabel("尚未测试。", group)
        self.tts_connection.setWordWrap(True)
        self.tts_connection.setObjectName("metric-caption")
        self._connection_labels["tts"] = self.tts_connection
        form.addRow("", self.tts_test_button)
        form.addRow("连接状态", self.tts_connection)
        return group

    def _build_vision_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("姿态模型", parent)
        form = QFormLayout(group)
        self.pose_model_path = QLineEdit()
        self.pose_model_path.setText("yolo11n-pose.pt")
        self.pose_model_path.setPlaceholderText("本地权重路径或 Ultralytics 模型名")
        self.device = EditableComboBox()
        for value in ("cuda:0", "cpu"):
            self.device.addItem(value)
        self.target_fps = QDoubleSpinBox()
        self.target_fps.setRange(1.0, 60.0)
        self.target_fps.setValue(15.0)
        self.target_fps.setDecimals(1)
        self.target_fps.setSuffix(" FPS")
        form.addRow("模型文件", self.pose_model_path)
        form.addRow("推理设备", self.device)
        form.addRow("实时目标帧率", self.target_fps)
        return group

    def _build_camera_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("摄像头", parent)
        form = QFormLayout(group)
        self.camera_device = QComboBox()
        camera_row = QHBoxLayout()
        camera_row.addWidget(self.camera_device, 1)
        self.camera_refresh_button = QPushButton("刷新")
        self.camera_refresh_button.setProperty("variant", "ghost")
        self.camera_refresh_button.clicked.connect(self._refresh_camera_devices)
        camera_row.addWidget(self.camera_refresh_button)
        form.addRow("摄像头（编号 - 名称）", camera_row)
        self.camera_diagnose_button = QPushButton("检测当前摄像头", group)
        self.camera_diagnose_button.setProperty("variant", "ghost")
        self.camera_diagnose_button.clicked.connect(self._diagnose_camera)
        self.camera_diagnostic = QLabel("尚未检测。", group)
        self.camera_diagnostic.setWordWrap(True)
        self.camera_diagnostic.setObjectName("metric-caption")
        form.addRow("", self.camera_diagnose_button)
        form.addRow("诊断结果", self.camera_diagnostic)
        self.camera_width = QSpinBox()
        self.camera_width.setRange(320, 3840)
        self.camera_width.setValue(1280)
        self.camera_height = QSpinBox()
        self.camera_height.setRange(240, 2160)
        self.camera_height.setValue(720)
        self.reference_view = QComboBox()
        for label, value in (
            ("正面", "front"),
            ("背面", "back"),
            ("左侧", "left_profile"),
            ("右侧", "right_profile"),
            ("三分之四", "three_quarter"),
            ("未知", "unknown"),
        ):
            self.reference_view.addItem(label, value)
        self.user_view = QComboBox()
        for label, value in (
            ("正面", "front"),
            ("背面", "back"),
            ("左侧", "left_profile"),
            ("右侧", "right_profile"),
            ("三分之四", "three_quarter"),
            ("未知", "unknown"),
        ):
            self.user_view.addItem(label, value)
        self.camera_preview_size = QComboBox()
        for label, value in (
            ("小", "small"),
            ("中", "medium"),
            ("大", "large"),
            ("收起", "collapsed"),
        ):
            self.camera_preview_size.addItem(label, value)
        self.camera_preview_size.setCurrentIndex(1)
        self.overlay_body = QCheckBox("人体骨架")
        self.overlay_face = QCheckBox("人脸网格与表情")
        self.overlay_hands = QCheckBox("双手 21 点骨架")
        self.overlay_bbox = QCheckBox("人体与人脸框")
        self.overlay_hud = QCheckBox("识别状态 HUD")
        self.overlay_labels = QCheckBox("手势与表情标签")
        overlay_layout = QVBoxLayout()
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(5)
        for checkbox in (
            self.overlay_body,
            self.overlay_face,
            self.overlay_hands,
            self.overlay_bbox,
            self.overlay_hud,
            self.overlay_labels,
        ):
            checkbox.setChecked(True)
            overlay_layout.addWidget(checkbox)
        form.addRow("识别叠加显示", overlay_layout)
        form.addRow("宽度", self.camera_width)
        form.addRow("高度", self.camera_height)
        form.addRow("参考视频机位", self.reference_view)
        form.addRow("用户摄像头机位", self.user_view)
        form.addRow("左上角小窗", self.camera_preview_size)
        return group

    def _build_training_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("训练与隐私", parent)
        form = QFormLayout(group)
        self.mirror_user = QCheckBox("镜像显示用户动作")
        self.mirror_user.setChecked(True)
        self.record_enabled = QCheckBox("保存本地训练录像")
        self.privacy_shield = QCheckBox("自动模糊画面中的其他人物")
        self.privacy_shield.setChecked(True)
        self.user_offset_ms = QSpinBox()
        self.user_offset_ms.setRange(0, 300)
        self.user_offset_ms.setValue(0)
        self.user_offset_ms.setSuffix(" ms")
        self.latency_alpha = QDoubleSpinBox()
        self.latency_alpha.setRange(0.05, 0.8)
        self.latency_alpha.setSingleStep(0.05)
        self.latency_alpha.setValue(0.2)
        form.addRow("", self.mirror_user)
        form.addRow("", self.record_enabled)
        form.addRow("", self.privacy_shield)
        form.addRow("音画补偿", self.user_offset_ms)
        form.addRow("延迟平滑", self.latency_alpha)
        return group

    def _build_renderer_group(self, parent: QWidget) -> QGroupBox:
        group = QGroupBox("3D 显示", parent)
        form = QFormLayout(group)
        self.robot_model_path = QLineEdit()
        self.robot_model_path.setPlaceholderText("留空使用内置 CC0 机器人；仅加载有授权的本地 GLB")
        model_row = QHBoxLayout()
        model_row.addWidget(self.robot_model_path, 1)
        model_button = QPushButton("选择 GLB", group)
        model_button.setProperty("variant", "ghost")
        model_button.clicked.connect(self._choose_robot_model)
        model_row.addWidget(model_button)
        clear_model_button = QPushButton("清除")
        clear_model_button.setProperty("variant", "ghost")
        clear_model_button.clicked.connect(self.robot_model_path.clear)
        model_row.addWidget(clear_model_button)
        self.model_mode = QComboBox()
        self.model_mode.addItem("骨架", "skeleton")
        self.model_mode.addItem("低模人体", "body")
        self.model_mode.addItem("骨架 + 人体", "overlay")
        self.model_mode.setCurrentIndex(2)
        self.character_preset = QComboBox()
        self.character_preset.currentIndexChanged.connect(self._update_character_details)
        self.character_info = QLabel()
        self.character_info.setWordWrap(True)
        self.character_info.setObjectName("metric-caption")
        self.character_download_button = PrimaryPushButton("下载并应用")
        self.character_download_button.clicked.connect(self._download_character)
        self.character_progress = QProgressBar()
        self.character_progress.setRange(0, 100)
        self.character_progress.setValue(0)
        self.character_progress.setVisible(False)
        character_row = QHBoxLayout()
        character_row.addWidget(self.character_preset, 1)
        character_row.addWidget(self.character_download_button)
        character_box = QVBoxLayout()
        character_box.setContentsMargins(0, 0, 0, 0)
        character_box.setSpacing(5)
        character_box.addLayout(character_row)
        character_box.addWidget(self.character_info)
        character_box.addWidget(self.character_progress)
        form.addRow("在线角色", character_box)
        self.motion_preset = QComboBox()
        self.motion_preset.addItem("低延迟", "low_latency")
        self.motion_preset.addItem("平衡（推荐）", "balanced")
        self.motion_preset.addItem("平滑优先", "smooth")
        self.motion_preset.setCurrentIndex(1)
        form.addRow("动作流畅度", self.motion_preset)
        self.render_fps = QSpinBox()
        self.render_fps.setRange(30, 60)
        self.render_fps.setValue(60)
        self.render_fps.setSuffix(" FPS")
        self.pending_timeout_ms = QSpinBox()
        self.pending_timeout_ms.setRange(100, 1000)
        self.pending_timeout_ms.setValue(300)
        self.pending_timeout_ms.setSuffix(" ms")
        self.low_power = QCheckBox("低功耗模式（6GB 显存优先）")
        self.root_mode = QComboBox()
        self.root_mode.addItem("不移动根节点", "none")
        self.root_mode.addItem("小幅摆动", "sway")
        self.root_mode.addItem("平面移动（需高可信 3D）", "planar")
        self.skin = QComboBox()
        for label, value in (
            ("默认机器人", "default"),
            ("赛博青", "cyber"),
            ("冠军金", "gold"),
            ("深蓝", "azure"),
            ("警示红", "crimson"),
        ):
            self.skin.addItem(label, value)
        self.scene_theme = QComboBox()
        for label, value in (
            ("训练舞台", "studio"),
            ("安静宿舍", "dorm"),
            ("霓虹夜场", "neon"),
        ):
            self.scene_theme.addItem(label, value)
        form.addRow("显示模式", self.model_mode)
        form.addRow("角色模型", model_row)
        form.addRow("渲染刷新", self.render_fps)
        form.addRow("待发送超时", self.pending_timeout_ms)
        form.addRow("", self.low_power)
        form.addRow("根运动", self.root_mode)
        form.addRow("机器人皮肤", self.skin)
        form.addRow("默认场景", self.scene_theme)
        return group

    def _connect_dirty_tracking(self) -> None:
        for group in self._groups:
            for line_edit in group.findChildren(QLineEdit):
                line_edit.textChanged.connect(self._mark_dirty)
            for combo in group.findChildren(QComboBox):
                combo.currentIndexChanged.connect(self._mark_dirty)
            for spin in group.findChildren(QSpinBox):
                spin.valueChanged.connect(self._mark_dirty)
            for spin in group.findChildren(QDoubleSpinBox):
                spin.valueChanged.connect(self._mark_dirty)
            for checkbox in group.findChildren(QCheckBox):
                checkbox.toggled.connect(self._mark_dirty)

    def _mark_dirty(self, *_args: object) -> None:
        if self._loading:
            return
        self._dirty = True
        self.dirty_label.setText("有未保存修改")
        self.save_button.setEnabled(True)

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def mark_saved(self) -> None:
        self._dirty = False
        self.dirty_label.setText("设置已同步")

    def set_save_error(self, message: str) -> None:
        self.dirty_label.setText(f"未应用：{message}")
        self.save_button.setEnabled(True)

    def _apply_settings_filter(self, *_args: object) -> None:
        query = " ".join(self.search_input.text().casefold().split())
        show_advanced = self.advanced_toggle.isChecked()
        for group in self._groups:
            level_visible = self._group_levels.get(group, "basic") == "basic" or show_advanced
            texts = [group.title()] + [label.text() for label in group.findChildren(QLabel)]
            texts.extend(combo.currentText() for combo in group.findChildren(QComboBox))
            haystack = " ".join(texts).casefold()
            group.setVisible(level_visible and (not query or query in haystack))

    def _restore_defaults(self) -> None:
        self._loading = True
        self._set_combo_data(self.appearance_theme, "dark")
        self.fullscreen_on_start.setChecked(False)
        self._set_combo_data(self.provider, "custom")
        self.llm_base_url.setText("https://api.openai.com/v1")
        self.llm_model.setText("gpt-4o-mini")
        self.llm_timeout.setValue(30.0)
        self.asr_enabled.setChecked(False)
        self.tts_enabled.setChecked(True)
        self._set_combo_data(self.tts_backend, "local")
        self.pose_model_path.setText("yolo11n-pose.pt")
        self._set_combo_text(self.device, "cuda:0")
        self.target_fps.setValue(15.0)
        self.camera_width.setValue(1280)
        self.camera_height.setValue(720)
        self.mirror_user.setChecked(True)
        self.record_enabled.setChecked(False)
        self.privacy_shield.setChecked(True)
        self.render_fps.setValue(45)
        self.low_power.setChecked(True)
        self._set_combo_data(self.model_mode, "overlay")
        self._loading = False
        self._mark_dirty()

    def _request_capability_test(self, capability: str) -> None:
        if capability == "llm":
            payload = {
                "base_url": self.llm_base_url.text().strip(),
                "model": self.llm_model.text().strip(),
                "api_key": self.llm_api_key.text().strip(),
                "timeout_s": self.llm_timeout.value(),
            }
        elif capability == "asr":
            payload = {
                "base_url": self.asr_base_url.text().strip(),
                "model": self.asr_model.text().strip(),
                "api_key": (self.asr_api_key.text().strip() or self.llm_api_key.text().strip()),
                "timeout_s": self.llm_timeout.value(),
            }
        else:
            payload = {
                "base_url": self.tts_base_url.text().strip(),
                "model": self.tts_model.text().strip(),
                "voice": self.tts_voice.text().strip(),
                "api_key": (self.tts_api_key.text().strip() or self.llm_api_key.text().strip()),
                "timeout_s": self.tts_timeout.value(),
            }
        self.set_connection_result(capability, "正在测试连接...", None)
        self.capabilityTestRequested.emit(capability, payload)

    def set_connection_result(
        self,
        capability: str,
        message: str,
        ok: bool | None,
    ) -> None:
        label = self._connection_labels.get(capability)
        if label is None:
            return
        label.setText(message)
        palette = palette_for(str(self._combo_data(self.appearance_theme) or "dark"))
        if ok is None:
            label.setStyleSheet("")
        elif ok:
            label.setStyleSheet(f"color: {palette.success};")
        else:
            label.setStyleSheet(f"color: {palette.danger};")

    def _diagnose_camera(self) -> None:
        index = int(self.camera_device.currentData() or 0)
        try:
            import cv2
        except ImportError:
            self.camera_diagnostic.setText("OpenCV 不可用，无法检测摄像头。")
            return
        capture = cv2.VideoCapture(index)
        try:
            if not capture.isOpened():
                self.camera_diagnostic.setText(
                    f"摄像头 {index} 无法打开，可能被其他程序占用。"
                )
                return
            ok = False
            for _ in range(3):
                ok, _frame = capture.read()
                if ok:
                    break
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            state = "画面读取正常" if ok else "已占用但暂未读到画面"
            self.camera_diagnostic.setText(
                f"{state}。编号 {index}；分辨率 {width}x{height}；报告 FPS {fps:.1f}。"
            )
        finally:
            capture.release()

    def _refresh_camera_devices(
        self,
        _checked: bool = False,
        *,
        preferred_index: int | None = None,
        preferred_name: str = "",
    ) -> None:
        current = self.camera_device.currentData() if self.camera_device.count() else None
        index = int(current) if current is not None else 0
        if preferred_index is not None:
            index = max(0, int(preferred_index))
        devices = list(list_camera_devices())
        if preferred_name and all(device.index != index for device in devices):
            devices.append(CameraDevice(index=index, name=preferred_name))
        self.camera_device.blockSignals(True)
        self.camera_device.clear()
        for device in devices:
            self.camera_device.addItem(device.label, device.index)
        selected = self.camera_device.findData(index)
        if selected < 0 and self.camera_device.count():
            selected = 0
        if selected >= 0:
            self.camera_device.setCurrentIndex(selected)
        self.camera_device.blockSignals(False)

    def _choose_robot_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择授权的本地机器人模型",
            "",
            "GLB 模型 (*.glb);;所有文件 (*)",
        )
        if path:
            self.robot_model_path.setText(path)

    def _default_character_root(self) -> Path:
        return AppPaths.discover().characters

    def _refresh_character_presets(self) -> None:
        current = self._combo_data(self.character_preset) if self.character_preset.count() else ""
        self.character_preset.blockSignals(True)
        self.character_preset.clear()
        for preset in CHARACTER_PRESETS:
            installed = self._character_store.installed_path(preset.key) is not None
            suffix = "内置" if preset.is_bundled else ("已缓存" if installed else "可下载")
            self.character_preset.addItem(f"{preset.name} · {suffix}", preset.key)
        self.character_preset.blockSignals(False)
        index = self.character_preset.findData(current)
        if index >= 0:
            self.character_preset.setCurrentIndex(index)
        self._update_character_details()

    def _update_character_details(self, _index: int = -1) -> None:
        preset = character_preset(self._combo_data(self.character_preset))
        installed = self._character_store.installed_path(preset.key) is not None
        if preset.is_bundled:
            state = "已内置，可直接使用" if installed else "内置资源缺失"
        elif installed:
            state = "已下载并缓存，可直接使用"
        else:
            state = "尚未下载"
        self.character_info.setText(
            f"{state}。{preset.summary}\n"
            f"作者：{preset.author or '未标注'}；许可：{preset.license_name}"
        )
        self.character_download_button.setEnabled(not installed or preset.is_bundled)
        if preset.is_bundled:
            self.character_download_button.setText("使用内置角色")
        elif installed:
            self.character_download_button.setText("已下载")
        else:
            self.character_download_button.setText("下载并应用")

    def _download_character(self) -> None:
        if self._character_controller is not None:
            return
        preset = character_preset(self._combo_data(self.character_preset))
        if preset.is_bundled:
            self._save()
            return
        worker = CharacterDownloadWorker(self._character_store, preset.key)
        controller = WorkerThreadController(worker, self)
        self._character_controller = controller
        self.character_progress.setValue(0)
        self.character_progress.setVisible(True)
        self.character_download_button.setEnabled(False)
        controller.progressChanged.connect(self.character_progress.setValue)
        worker.completed.connect(self._on_character_downloaded)
        controller.errorOccurred.connect(self._on_character_download_error)
        controller.finished.connect(self._on_character_download_finished)
        controller.start()

    def _on_character_downloaded(self, key: str, _path: str) -> None:
        self._downloaded_character_key = key
        self.character_info.setText(
            f"角色下载完成：{character_preset(key).name}。正在自动应用到 3D 舞台。"
        )

    def _on_character_download_error(self, message: str) -> None:
        self.character_info.setText(f"角色下载失败：{message}")

    def _on_character_download_finished(self) -> None:
        self._character_controller = None
        self.character_progress.setVisible(False)
        downloaded_key = self._downloaded_character_key
        self._downloaded_character_key = None
        self._refresh_character_presets()
        if downloaded_key:
            index = self.character_preset.findData(downloaded_key)
            if index >= 0:
                self.character_preset.setCurrentIndex(index)
            QTimer.singleShot(0, self._save)

    def load_values(self, values: Mapping[str, Any]) -> None:
        """Apply a configuration snapshot without persisting secrets here."""
        self._loading = True
        self._set_combo_data(
            self.appearance_theme,
            str(values.get("appearance_theme", "dark")),
        )
        self.fullscreen_on_start.setChecked(
            bool(values.get("fullscreen_on_start", False))
        )
        provider_index = self.provider.findData(str(values.get("provider_key", "custom")))
        if provider_index >= 0:
            self.provider.blockSignals(True)
            self.provider.setCurrentIndex(provider_index)
            self.provider.blockSignals(False)
            self._apply_provider_preset()
        self.llm_base_url.setText(str(values.get("cloud_base_url", self.llm_base_url.text())))
        self.llm_model.setText(str(values.get("cloud_model", self.llm_model.text())))
        self.llm_timeout.setValue(float(values.get("cloud_timeout_s", self.llm_timeout.value())))

        self.asr_enabled.setChecked(bool(values.get("asr_enabled", self.asr_enabled.isChecked())))
        self.asr_base_url.setText(str(values.get("asr_base_url", self.asr_base_url.text())))
        self.asr_model.setText(str(values.get("asr_model", self.asr_model.text())))
        self.asr_language.setText(str(values.get("asr_language", self.asr_language.text())))

        self.tts_enabled.setChecked(bool(values.get("tts_enabled", self.tts_enabled.isChecked())))
        self._set_combo_data(
            self.tts_backend, str(values.get("tts_backend", self._combo_data(self.tts_backend)))
        )
        self.tts_base_url.setText(str(values.get("tts_base_url", self.tts_base_url.text())))
        self.tts_model.setText(str(values.get("tts_model", self.tts_model.text())))
        self.tts_voice.setText(str(values.get("tts_voice", self.tts_voice.text())))
        self.tts_timeout.setValue(float(values.get("tts_timeout_s", self.tts_timeout.value())))

        self.pose_model_path.setText(str(values.get("pose_model_path", self.pose_model_path.text())))
        self._set_combo_text(self.device, str(values.get("device", self.device.currentText())))
        self.target_fps.setValue(float(values.get("target_fps", self.target_fps.value())))

        self.camera_width.setValue(int(values.get("camera_width", self.camera_width.value())))
        self._refresh_camera_devices(
            preferred_index=int(values.get("camera_index", 0)),
            preferred_name=str(values.get("camera_name", "")),
        )
        for checkbox, key in (
            (self.overlay_body, "overlay_body"),
            (self.overlay_face, "overlay_face"),
            (self.overlay_hands, "overlay_hands"),
            (self.overlay_bbox, "overlay_bbox"),
            (self.overlay_hud, "overlay_hud"),
            (self.overlay_labels, "overlay_labels"),
        ):
            checkbox.setChecked(bool(values.get(key, checkbox.isChecked())))
        self.camera_height.setValue(int(values.get("camera_height", self.camera_height.value())))
        self._set_combo_data(
            self.reference_view,
            str(values.get("reference_view", self._combo_data(self.reference_view))),
        )
        self._set_combo_data(
            self.user_view,
            str(values.get("user_view", self._combo_data(self.user_view))),
        )
        self._set_combo_data(
            self.camera_preview_size,
            str(values.get("camera_preview_size", self._combo_data(self.camera_preview_size))),
        )

        self.mirror_user.setChecked(bool(values.get("mirror_user", self.mirror_user.isChecked())))
        self.record_enabled.setChecked(
            bool(values.get("record_enabled", self.record_enabled.isChecked()))
        )
        self.privacy_shield.setChecked(
            bool(values.get("privacy_shield", self.privacy_shield.isChecked()))
        )
        self.user_offset_ms.setValue(int(values.get("user_offset_ms", self.user_offset_ms.value())))
        self.latency_alpha.setValue(float(values.get("latency_alpha", self.latency_alpha.value())))

        self._set_combo_data(
            self.model_mode, str(values.get("model_mode", self._combo_data(self.model_mode)))
        )
        self._set_combo_data(
            self.character_preset,
            str(values.get("character_id", self._combo_data(self.character_preset))),
        )
        self._set_combo_data(
            self.motion_preset,
            str(values.get("motion_preset", self._combo_data(self.motion_preset))),
        )
        self.robot_model_path.setText(str(values.get("robot_model_path", "")))
        self.render_fps.setValue(int(values.get("render_fps", self.render_fps.value())))
        self.pending_timeout_ms.setValue(
            int(values.get("pending_timeout_ms", self.pending_timeout_ms.value()))
        )
        self.low_power.setChecked(bool(values.get("low_power", self.low_power.isChecked())))
        self._set_combo_data(self.root_mode, str(values.get("root_mode", "none")))
        self._set_combo_data(self.skin, str(values.get("skin", "default")))
        self._set_combo_data(
            self.scene_theme,
            str(values.get("scene_theme", "studio")),
        )
        self._loading = False
        self._dirty = False
        self.dirty_label.setText("设置已同步")

    def set_session_api_key(self, value: str) -> None:
        """Show a process-only key in the form without persisting or dirtying it."""
        secret = str(value).strip()
        if not secret:
            return
        previous_loading = self._loading
        self._loading = True
        self.llm_api_key.setText(secret)
        self._loading = previous_loading

    def _save(self) -> None:
        self.dirty_label.setText("正在校验并应用...")
        self.settingsSaved.emit(
            {
                "appearance_theme": self._combo_data(self.appearance_theme),
                "fullscreen_on_start": self.fullscreen_on_start.isChecked(),
                "cloud_base_url": self.llm_base_url.text().strip(),
                "provider_key": str(self.provider.currentData() or "custom"),
                "cloud_model": self.llm_model.text().strip(),
                "cloud_api_key": self.llm_api_key.text().strip(),
                "cloud_timeout_s": self.llm_timeout.value(),
                "asr_enabled": self.asr_enabled.isChecked(),
                "asr_base_url": self.asr_base_url.text().strip(),
                "asr_model": self.asr_model.text().strip(),
                "asr_language": self.asr_language.text().strip(),
                "asr_api_key": self.asr_api_key.text().strip(),
                "tts_enabled": self.tts_enabled.isChecked(),
                "tts_backend": self._combo_data(self.tts_backend),
                "tts_base_url": self.tts_base_url.text().strip(),
                "tts_model": self.tts_model.text().strip(),
                "tts_voice": self.tts_voice.text().strip(),
                "tts_api_key": self.tts_api_key.text().strip(),
                "tts_timeout_s": self.tts_timeout.value(),
                "pose_model_path": self.pose_model_path.text().strip(),
                "device": self.device.currentText().strip(),
                "target_fps": self.target_fps.value(),
                "camera_index": int(self.camera_device.currentData() or 0),
                "camera_name": str(self.camera_device.currentText()).split(" - ", 1)[-1],
                "camera_width": self.camera_width.value(),
                "overlay_body": self.overlay_body.isChecked(),
                "overlay_face": self.overlay_face.isChecked(),
                "overlay_hands": self.overlay_hands.isChecked(),
                "overlay_bbox": self.overlay_bbox.isChecked(),
                "overlay_hud": self.overlay_hud.isChecked(),
                "overlay_labels": self.overlay_labels.isChecked(),
                "camera_height": self.camera_height.value(),
                "reference_view": self._combo_data(self.reference_view),
                "user_view": self._combo_data(self.user_view),
                "camera_preview_size": self._combo_data(self.camera_preview_size),
                "mirror_user": self.mirror_user.isChecked(),
                "record_enabled": self.record_enabled.isChecked(),
                "privacy_shield": self.privacy_shield.isChecked(),
                "user_offset_ms": self.user_offset_ms.value(),
                "latency_alpha": self.latency_alpha.value(),
                "model_mode": self._combo_data(self.model_mode),
                "character_id": self._combo_data(self.character_preset),
                "motion_preset": self._combo_data(self.motion_preset),
                "robot_model_path": self.robot_model_path.text().strip(),
                "render_fps": self.render_fps.value(),
                "pending_timeout_ms": self.pending_timeout_ms.value(),
                "low_power": self.low_power.isChecked(),
                "root_mode": self._combo_data(self.root_mode),
                "skin": self._combo_data(self.skin),
                "scene_theme": self._combo_data(self.scene_theme),
            }
        )

    @staticmethod
    def _combo_data(combo: QComboBox) -> str:
        value = combo.currentData()
        return str(value if value is not None else combo.currentText())

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        if not value:
            return
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif hasattr(combo, "setCurrentText"):
            combo.setCurrentText(value)
