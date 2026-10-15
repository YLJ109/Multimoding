"""Live training page with the shared 3D scene and cue panel."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.domain.types import TrainingUpdate
from dance_mirror.motion.retarget import RetargetedSkeleton
from dance_mirror.view.scene_widget import SceneWidget


class TrainingInterface(QWidget):
    """Display the synchronized reference/user skeleton and current score."""

    stopRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("training-interface")
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("实时双影训练")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.score_label = QLabel("总分 --")
        self.score_label.setObjectName("metric-value")
        self.score_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.quality_label = QLabel("动作包 --")
        self.quality_label.setObjectName("metric-caption")
        self.quality_label.setStyleSheet("font-size: 13px;")
        self.stop_button = QPushButton("停止训练")
        self.stop_button.setProperty("variant", "danger")
        self.stop_button.clicked.connect(self.stopRequested.emit)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.quality_label)
        header.addWidget(self.score_label)
        header.addWidget(self.stop_button)
        root.addLayout(header)

        self.scene = SceneWidget(self)
        root.addWidget(self.scene, 1)

        status_row = QHBoxLayout()
        self.playback_label = QLabel("参考动作 3D 回放：未开始")
        self.privacy_label = QLabel("隐私遮蔽：待机")
        self.recording_label = QLabel("录像：关闭")
        status_row.addWidget(self.playback_label)
        status_row.addWidget(self.privacy_label)
        status_row.addWidget(self.recording_label)
        status_row.addStretch(1)
        root.addLayout(status_row)

        footer = QHBoxLayout()
        self.cue_label = QLabel("等待训练开始。")
        self.cue_label.setWordWrap(True)
        self.cue_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cue_label.setStyleSheet("font-size: 16px; padding: 8px;")
        footer.addWidget(self.cue_label, 1)
        root.addLayout(footer)

        self.report_label = QLabel("")
        self.report_label.setWordWrap(True)
        self.report_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.report_label.setObjectName("report-card")
        self.report_label.setStyleSheet("font-size: 13px; padding: 6px;")
        root.addWidget(self.report_label)

    def apply_update(self, update: TrainingUpdate) -> None:
        if update.score.quality_label:
            self.quality_label.setText(f"动作包 {update.score.quality_label}")
        self.score_label.setText(f"总分 {update.score.overall:.1f}")
        if update.cue is None:
            self.cue_label.setText("动作已捕捉，继续跟上节拍。")
        else:
            self.cue_label.setText(update.cue.text)
            self.scene.set_status(update.cue.text)

    def set_reference(self, skeleton: RetargetedSkeleton) -> None:
        self.scene.set_reference(skeleton)

    def set_user(self, skeleton: RetargetedSkeleton) -> None:
        self.scene.set_user(skeleton)

    def clear_user(self) -> None:
        self.scene.clear_user()

    def set_reference_playback_status(self, text: str) -> None:
        self.playback_label.setText(text)
        self.scene.set_status(text)

    def set_message(self, text: str) -> None:
        self.cue_label.setText(text)
        self.scene.set_status(text)

    def set_report(self, text: str) -> None:
        self.report_label.setText(text)

    def set_privacy_status(self, masked: bool) -> None:
        self.privacy_label.setText("隐私遮蔽：已遮蔽其他人物" if masked else "隐私遮蔽：未发现其他人物")

    def set_recording_status(self, recording: bool) -> None:
        self.recording_label.setText("录像：保存中" if recording else "录像：关闭")

    def set_model_mode(self, mode: str) -> None:
        self.scene.set_model_mode(mode)

    def set_training_enabled(self, enabled: bool) -> None:
        self.stop_button.setEnabled(enabled)
        if not enabled:
            self.score_label.setText("总分 --")

    def stop(self) -> None:
        self.scene.stop()
