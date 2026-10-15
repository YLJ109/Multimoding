"""Home page for selecting the reference video and starting a session."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class HomeInterface(QWidget):
    """Non-blocking control surface; all heavy work is delegated upward."""

    analyzeRequested = pyqtSignal(str)
    startTrainingRequested = pyqtSignal(int)
    stopRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("home-interface")
        self._video_path = ""
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)

        title = QLabel("舞镜 DanceMirror")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        subtitle = QLabel(
            "参考视频离线提取一次动作，摄像头实时驱动用户骨架；"
            "本地负责评分和语音辅导，云端只做训练总结。"
        )
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        reference_box = QGroupBox("标准舞蹈视频")
        reference_layout = QFormLayout(reference_box)
        self.video_edit = QLineEdit()
        self.video_edit.setReadOnly(True)
        self.video_edit.setPlaceholderText("选择固定机位、单人、全身可见的视频")
        browse = QPushButton("选择视频")
        browse.setProperty("variant", "ghost")
        browse.clicked.connect(self._choose_video)
        video_row = QHBoxLayout()
        video_row.addWidget(self.video_edit, 1)
        video_row.addWidget(browse)
        reference_layout.addRow("文件", video_row)
        self.analyze_button = QPushButton("解析为 3D 动作包")
        self.analyze_button.setProperty("variant", "primary")
        self.analyze_button.clicked.connect(self._request_analysis)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        reference_layout.addRow("", self.analyze_button)
        reference_layout.addRow("进度", self.progress)
        root.addWidget(reference_box)

        training_box = QGroupBox("实时训练")
        training_layout = QFormLayout(training_box)
        self.camera_index = QSpinBox()
        self.camera_index.setRange(0, 9)
        self.camera_index.setValue(0)
        training_layout.addRow("摄像头编号", self.camera_index)
        self.start_button = QPushButton("开始训练")
        self.start_button.setProperty("variant", "primary")
        self.start_button.clicked.connect(
            lambda: self.startTrainingRequested.emit(self.camera_index.value())
        )
        self.stop_button = QPushButton("停止")
        self.stop_button.setProperty("variant", "danger")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        button_row = QHBoxLayout()
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        training_layout.addRow("", button_row)
        root.addWidget(training_box)
        root.addStretch(1)

        self.status = QLabel("尚未解析参考视频。")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    @property
    def video_path(self) -> str:
        return self._video_path

    def _choose_video(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择标准舞蹈视频",
            str(Path.home()),
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm);;所有文件 (*)",
        )
        if selected:
            self._video_path = selected
            self.video_edit.setText(selected)
            self.status.setText("已选择视频，可以开始离线解析。")

    def _request_analysis(self) -> None:
        if not self._video_path:
            self.status.setText("请先选择标准舞蹈视频。")
            return
        self.analyzeRequested.emit(self._video_path)

    def set_analysis_running(self, running: bool) -> None:
        self.analyze_button.setEnabled(not running)
        self.progress.setValue(0 if running else self.progress.value())
        if running:
            self.status.setText("正在离线解析参考视频，首次运行会加载 YOLO 模型。")

    def set_training_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.camera_index.setEnabled(not running)
        if running:
            self.status.setText("训练进行中。请保证全身和主要关节在画面内。")

    def set_progress(self, value: int) -> None:
        self.progress.setValue(max(0, min(100, value)))

    def set_status(self, text: str) -> None:
        self.status.setText(text)
