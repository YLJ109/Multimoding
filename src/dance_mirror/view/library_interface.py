"""Card-based dance package library with filtering and asset details."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.storage.motion_library import DancePackage
from dance_mirror.view.design_tokens import palette_for
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
    ProgressBar as QProgressBar,
)
from dance_mirror.view.fluent import (
    PushButton as QPushButton,
)
from dance_mirror.view.fluent import (
    ScrollArea as QScrollArea,
)

VIDEO_FILTER = "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm);;所有文件 (*)"


class _RenameDialog(QDialog):
    def __init__(self, current_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("重命名舞蹈包")
        layout = QVBoxLayout(self)
        self.name_edit = QLineEdit(self)
        self.name_edit.setText(current_name)
        self.name_edit.selectAll()
        layout.addWidget(QLabel("名称", self))
        layout.addWidget(self.name_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def name(self) -> str:
        return self.name_edit.text().strip()


class DancePackageCard(QFrame):
    """One local dance asset with poster, quality, and actions."""

    selected = pyqtSignal(str)
    renameRequested = pyqtSignal(str, str)
    deleteRequested = pyqtSignal(str)
    posterRequested = pyqtSignal(str, str)
    musicRequested = pyqtSignal(str)
    detailsRequested = pyqtSignal(str)
    selectionChanged = pyqtSignal(str, bool)

    def __init__(self, package: DancePackage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.package_id = package.package_id
        self.setObjectName("dance-package-card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(244, 332)
        self._theme_mode = "light"
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 8, 9, 8)
        root.setSpacing(4)
        self.select_check = QCheckBox("选", self)
        # A Fluent CheckBox already reserves room for its indicator + label
        # (sizeHint ~57px); forcing it narrower clips the indicator box.
        self.select_check.setMinimumWidth(self.select_check.sizeHint().width())
        self.select_check.setToolTip("加入批量操作")
        self.select_check.toggled.connect(
            lambda checked: self.selectionChanged.emit(self.package_id, bool(checked))
        )

        self.poster = QLabel(self)
        self.poster.setObjectName("package-poster")
        self.poster.setFixedSize(224, 122)
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_poster(package)
        root.addWidget(self.poster)

        name = QLabel(package.name, self)
        name.setWordWrap(True)
        name.setObjectName("card-title")
        name.setToolTip(package.name)
        name.setFixedHeight(34)
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title_row.addWidget(name, 1)
        title_row.addWidget(self.select_check, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(title_row)

        metadata = QLabel(
            f"{package.duration_s:05.1f} 秒  |  {package.gameplay.bpm:.0f} BPM  |  "
            f"难度 {package.gameplay.difficulty}",
            self,
        )
        metadata.setObjectName("metric-caption")
        metadata.setFixedHeight(18)
        root.addWidget(metadata)

        tags = " · ".join(package.tags[:3]) or package.gameplay.dance_type
        tag_label = QLabel(tags, self)
        tag_label.setObjectName("metric-caption")
        tag_label.setToolTip(tags)
        tag_label.setFixedHeight(18)
        root.addWidget(tag_label)

        status_row = QHBoxLayout()
        quality = QLabel(
            f"{package.quality_label} {package.quality.score_confidence:.0%}",
            self,
        )
        quality.setObjectName("quality-pill")
        quality.setToolTip(
            f"有效帧 {package.quality.valid_frame_ratio:.0%}；"
            f"动作尺度 {package.quality.motion_scale:.0%}"
        )
        status = QLabel(package.status_label, self)
        status.setObjectName("quality-pill")
        status.setToolTip(f"音乐许可：{package.gameplay.music_license}")
        quality.setFixedHeight(22)
        status.setFixedHeight(22)
        status_row.addWidget(quality)
        status_row.addWidget(status)
        status_row.addStretch(1)
        root.addLayout(status_row)

        select_button = PrimaryPushButton("选择并开始准备", self)
        select_button.setFixedHeight(32)
        select_button.clicked.connect(lambda: self.selected.emit(self.package_id))
        root.addWidget(select_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        details_button = QPushButton("详情", self)
        details_button.setFixedHeight(28)
        details_button.clicked.connect(lambda: self.detailsRequested.emit(self.package_id))
        rename_button = QPushButton("改名", self)
        rename_button.setFixedHeight(28)
        rename_button.clicked.connect(
            lambda: self.renameRequested.emit(self.package_id, package.name)
        )
        delete_button = QPushButton("删除", self)
        delete_button.setFixedHeight(28)
        delete_button.setProperty("variant", "danger")
        delete_button.clicked.connect(lambda: self.deleteRequested.emit(self.package_id))
        resource_button = QPushButton("资源", self)
        resource_button.setProperty("variant", "ghost")
        resource_button.setFixedHeight(28)
        resource_button.setToolTip("更换海报或重新提取视频原声")
        resource_menu = QMenu(resource_button)
        resource_menu.addAction("更换海报", self._choose_poster)
        resource_menu.addAction(
            "重新提取原声",
            lambda: self.musicRequested.emit(self.package_id),
        )
        resource_button.setMenu(resource_menu)
        action_row.addWidget(details_button)
        action_row.addWidget(rename_button)
        action_row.addWidget(resource_button)
        action_row.addWidget(delete_button)
        root.addLayout(action_row)


    def set_selected(self, selected: bool) -> None:
        self.select_check.blockSignals(True)
        self.select_check.setChecked(bool(selected))
        self.select_check.blockSignals(False)

    def set_theme_mode(self, theme: str) -> None:
        self._theme_mode = "dark" if str(theme).lower() == "dark" else "light"
        palette = palette_for(self._theme_mode)
        self.poster.setStyleSheet(
            f"background: {palette.camera_background}; color: {palette.camera_placeholder};"
            " border-radius: 5px;"
        )

    def _set_poster(self, package: DancePackage) -> None:
        palette = palette_for(self._theme_mode)
        self.poster.setStyleSheet(
            f"background: {palette.camera_background}; color: {palette.camera_placeholder};"
            " border-radius: 5px;"
        )
        if package.poster_path is not None and package.poster_path.is_file():
            image = QPixmap(str(package.poster_path))
            if not image.isNull():
                self.poster.setPixmap(
                    image.scaled(
                        self.poster.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.poster.setText("暂无海报\n可从详情中更换")

    def _choose_poster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择舞蹈包海报",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)",
        )
        if path:
            self.posterRequested.emit(self.package_id, path)

    def mouseDoubleClickEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        self.selected.emit(self.package_id)


class _PackageDetailsDialog(QDialog):
    """Independent asset drawer with source, license, and quality facts."""

    def __init__(self, package: DancePackage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.package = package
        self.setWindowTitle(f"舞蹈包详情 · {package.name}")
        self.setMinimumSize(680, 500)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(11)

        body = QHBoxLayout()
        poster = QLabel(self)
        poster.setFixedSize(320, 180)
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setObjectName("package-poster")
        if package.poster_path is not None and package.poster_path.is_file():
            image = QPixmap(str(package.poster_path))
            if not image.isNull():
                poster.setPixmap(
                    image.scaled(
                        poster.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        else:
            poster.setText("暂无海报")
        body.addWidget(poster)

        facts = QVBoxLayout()
        title = QLabel(package.name, self)
        title.setObjectName("page-title")
        title.setWordWrap(True)
        facts.addWidget(title)
        details = QLabel(
            "\n".join(
                (
                    f"状态：{package.status_label}",
                    f"动作质量：{package.quality_label} · 置信度 {package.quality.score_confidence:.0%}",
                    f"有效帧比例：{package.quality.valid_frame_ratio:.0%}",
                    f"动作尺度：{package.quality.motion_scale:.0%}",
                    f"时长 / 帧数：{package.duration_s:.1f} 秒 · {package.frame_count} 帧",
                    f"BPM / 难度：{package.gameplay.bpm:.0f} · {package.gameplay.difficulty}",
                    f"类型 / 标签：{package.gameplay.dance_type} / {'、'.join(package.tags) or '无'}",
                    f"音乐：{package.gameplay.music_title or '未配置'}",
                    f"音乐许可：{package.gameplay.music_license}",
                    f"来源：{package.source_video or '本地迁移'}",
                )
            ),
            self,
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        facts.addWidget(details)
        facts.addStretch(1)
        body.addLayout(facts, 1)
        root.addLayout(body, 1)

        reason_text = "；".join(package.quality.reasons) or "未记录额外质量原因。"
        reason = QLabel(f"质量说明：{reason_text}", self)
        reason.setWordWrap(True)
        reason.setObjectName("report-card")
        root.addWidget(reason)

        actions = QHBoxLayout()
        source_button = QPushButton("打开源视频", self)
        source_button.setProperty("variant", "ghost")
        source_button.setEnabled(Path(package.source_video).is_file() if package.source_video else False)
        source_button.clicked.connect(self._open_source)
        music_button = QPushButton("播放音乐", self)
        music_button.setProperty("variant", "ghost")
        music_button.setEnabled(package.has_music)
        music_button.clicked.connect(self._play_music)
        actions.addWidget(source_button)
        actions.addWidget(music_button)
        actions.addStretch(1)
        root.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close | QDialogButtonBox.StandardButton.Ok,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("选择并开始准备")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _open_source(self) -> None:
        if self.package.source_video:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.package.source_video))

    def _play_music(self) -> None:
        if self.package.audio_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.package.audio_path)))


class _TrashDialog(QDialog):
    """Recover or permanently remove packages from the local trash."""

    restoreRequested = pyqtSignal(str)
    purgeRequested = pyqtSignal(str)
    purgeAllRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("舞蹈包回收站")
        self.setMinimumSize(620, 430)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        title = QLabel("可恢复的舞蹈包", self)
        title.setObjectName("page-title")
        root.addWidget(title)
        self.note = QLabel(
            "删除会先移动到本地回收站。恢复不会覆盖同名舞蹈包；永久删除无法撤销。",
            self,
        )
        self.note.setWordWrap(True)
        self.note.setObjectName("page-subtitle")
        root.addWidget(self.note)
        self.list = QListWidget(self)
        self.list.currentRowChanged.connect(self._update_buttons)
        root.addWidget(self.list, 1)
        actions = QHBoxLayout()
        self.restore_button = QPushButton("恢复选中", self)
        self.restore_button.setProperty("variant", "primary")
        self.restore_button.clicked.connect(self._restore)
        self.purge_button = QPushButton("永久删除", self)
        self.purge_button.setProperty("variant", "danger")
        self.purge_button.clicked.connect(self._purge)
        self.purge_all_button = QPushButton("清空回收站", self)
        self.purge_all_button.setProperty("variant", "ghost")
        self.purge_all_button.clicked.connect(self.purgeAllRequested.emit)
        close_button = QPushButton("关闭", self)
        close_button.clicked.connect(self.accept)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.purge_button)
        actions.addWidget(self.purge_all_button)
        actions.addStretch(1)
        actions.addWidget(close_button)
        root.addLayout(actions)
        self._update_buttons()

    def set_entries(self, entries: Sequence[object]) -> None:
        self.list.clear()
        for entry in entries:
            package = getattr(entry, "package", None)
            trash_path = str(getattr(entry, "trash_path", ""))
            name = str(getattr(package, "name", "") or "未知舞蹈包")
            updated = str(getattr(package, "updated_at", "") or "")
            item = QListWidgetItem(f"{name}    ·    {updated}")
            item.setData(Qt.ItemDataRole.UserRole, trash_path)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.purge_all_button.setEnabled(self.list.count() > 0)
        self._update_buttons()

    def _selected_path(self) -> str:
        item = self.list.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _update_buttons(self, _row: int = -1) -> None:
        enabled = bool(self._selected_path())
        self.restore_button.setEnabled(enabled)
        self.purge_button.setEnabled(enabled)

    def _restore(self) -> None:
        path = self._selected_path()
        if path:
            self.restoreRequested.emit(path)

    def _purge(self) -> None:
        path = self._selected_path()
        if path:
            self.purgeRequested.emit(path)


class DancePackageLibraryInterface(QWidget):
    """Responsive, filterable grid of local dance package assets."""

    convertRequested = pyqtSignal(str, str, str)
    selectRequested = pyqtSignal(str)
    renameRequested = pyqtSignal(str, str)
    deleteRequested = pyqtSignal(str)
    posterRequested = pyqtSignal(str, str)
    musicRequested = pyqtSignal(str)
    refreshRequested = pyqtSignal()
    trashRequested = pyqtSignal()
    restoreTrashRequested = pyqtSignal(str)
    purgeTrashRequested = pyqtSignal(str)
    purgeAllTrashRequested = pyqtSignal()
    batchRenameRequested = pyqtSignal(object, str)
    batchDeleteRequested = pyqtSignal(object)
    cancelConversionRequested = pyqtSignal()
    retryConversionRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("package-library-interface")
        self.setAcceptDrops(True)
        self._packages: tuple[DancePackage, ...] = ()
        self._visible_packages: tuple[DancePackage, ...] = ()
        self._columns = 0
        self._selected_ids: set[str] = set()
        self._last_conversion: tuple[str, str, str] | None = None
        self._trash_dialog: _TrashDialog | None = None
        self._theme_mode = "light"
        self._build_ui()
        self.refreshRequested.emit()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("舞蹈包库", self)
        title.setObjectName("page-title")
        subtitle = QLabel(
            "管理舞蹈动作、封面、原声与质量档案。",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("page-subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.add_button = QPushButton("添加舞蹈包", self)
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self._request_conversion)
        self.refresh_button = QPushButton("刷新", self)
        self.refresh_button.setProperty("variant", "ghost")
        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        self.trash_button = QPushButton("回收站", self)
        self.trash_button.setProperty("variant", "ghost")
        self.trash_button.clicked.connect(self.show_trash_dialog)
        self.batch_rename_button = QPushButton("批量改名", self)
        self.batch_rename_button.setProperty("variant", "ghost")
        self.batch_rename_button.clicked.connect(self._batch_rename)
        self.batch_delete_button = QPushButton("批量删除", self)
        self.batch_delete_button.setProperty("variant", "danger")
        self.batch_delete_button.clicked.connect(self._batch_delete)
        header.addWidget(self.add_button)
        header.addWidget(self.refresh_button)
        header.addWidget(self.trash_button)
        header.addWidget(self.batch_rename_button)
        header.addWidget(self.batch_delete_button)
        root.addLayout(header)

        toolbar = QFrame(self)
        toolbar.setObjectName("surface-card")
        toolbar_layout = QGridLayout(toolbar)
        toolbar_layout.setContentsMargins(11, 8, 11, 8)
        toolbar_layout.setHorizontalSpacing(8)
        toolbar_layout.setVerticalSpacing(7)
        self.search_input = QLineEdit(toolbar)
        self.search_input.setPlaceholderText("搜索名称、类型、标签或来源")
        self.difficulty_filter = QComboBox(toolbar)
        self.difficulty_filter.addItem("全部难度", 0)
        for difficulty in range(1, 6):
            self.difficulty_filter.addItem(f"难度 {difficulty}", difficulty)
        self.quality_filter = QComboBox(toolbar)
        self.quality_filter.addItem("全部质量", "")
        self.quality_filter.addItem("已校验 3D", "verified_3d")
        self.quality_filter.addItem("混合 3D", "hybrid_3d")
        self.quality_filter.addItem("相对 3D", "relative_3d")
        self.sort_order = QComboBox(toolbar)
        self.sort_order.addItem("最近更新", "updated_desc")
        self.sort_order.addItem("名称 A-Z", "name_asc")
        self.sort_order.addItem("质量优先", "quality_desc")
        self.sort_order.addItem("难度从低到高", "difficulty_asc")
        self.sort_order.addItem("时长从短到长", "duration_asc")
        self.clear_filters = QPushButton("清除筛选", toolbar)
        self.clear_filters.setProperty("variant", "ghost")
        self.clear_filters.clicked.connect(self._clear_filters)
        toolbar_layout.addWidget(self.search_input, 0, 0, 1, 2)
        toolbar_layout.addWidget(self.difficulty_filter, 0, 2)
        toolbar_layout.addWidget(self.quality_filter, 0, 3)
        toolbar_layout.addWidget(self.sort_order, 0, 4)
        toolbar_layout.addWidget(self.clear_filters, 0, 5)
        toolbar_layout.setColumnStretch(0, 1)
        toolbar_layout.setColumnStretch(1, 1)
        root.addWidget(toolbar)

        self.search_input.textChanged.connect(self._apply_filters)
        self.difficulty_filter.currentIndexChanged.connect(self._apply_filters)
        self.quality_filter.currentIndexChanged.connect(self._apply_filters)
        self.sort_order.currentIndexChanged.connect(self._apply_filters)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.conversion_actions = QHBoxLayout()
        self.cancel_button = QPushButton("取消转换", self)
        self.cancel_button.setProperty("variant", "danger")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancelConversionRequested.emit)
        self.retry_button = QPushButton("重试转换", self)
        self.retry_button.setProperty("variant", "primary")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self.retryConversionRequested.emit)
        self.conversion_actions.addWidget(self.cancel_button)
        self.conversion_actions.addWidget(self.retry_button)
        self.conversion_actions.addStretch(1)
        root.addWidget(self.progress)
        root.addLayout(self.conversion_actions)

        self.status = QLabel("正在扫描本地舞蹈包。", self)
        self.status.setWordWrap(True)
        self.status.setObjectName("page-subtitle")
        root.addWidget(self.status)

        self.scroll = QScrollArea(self)
        if hasattr(self.scroll, "enableTransparentBackground"):
            self.scroll.enableTransparentBackground()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host = QWidget(self.scroll)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.grid.setContentsMargins(0, 4, 0, 12)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        self.empty_label = QLabel(
            "没有匹配的舞蹈包。\n可清除筛选或添加新的动作包。",
            self,
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("page-subtitle")
        self.empty_label.setVisible(False)
        root.addWidget(self.empty_label, 1)

    @property
    def packages(self) -> tuple[DancePackage, ...]:
        return self._packages

    @property
    def last_conversion(self) -> tuple[str, str, str] | None:
        return self._last_conversion

    def set_packages(self, packages: Sequence[DancePackage]) -> None:
        self._packages = tuple(packages)
        valid_ids = {item.package_id for item in self._packages}
        self._selected_ids.intersection_update(valid_ids)
        self._apply_filters(force=True)
        self._update_batch_buttons()

    def set_theme_mode(self, theme: str) -> None:
        self._theme_mode = "dark" if str(theme).lower() == "dark" else "light"
        for card in self.grid_host.findChildren(DancePackageCard):
            card.set_theme_mode(self._theme_mode)

    def set_busy(self, running: bool, message: str = "") -> None:
        self.add_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.batch_rename_button.setEnabled(not running)
        self.batch_delete_button.setEnabled(not running)
        self.progress.setVisible(running)
        self.cancel_button.setVisible(running)
        if running:
            self.retry_button.setVisible(False)
        if not running:
            self.progress.setValue(0)
        if message:
            self.status.setText(message)
        self._update_batch_buttons()

    def set_progress(self, value: int) -> None:
        self.progress.setValue(max(0, min(100, int(value))))

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_conversion_failure(self, message: str) -> None:
        self.status.setText(f"转换失败：{message}")
        self.retry_button.setVisible(self._last_conversion is not None)
        self.cancel_button.setVisible(False)

    def set_trash_entries(self, entries: Sequence[object]) -> None:
        if self._trash_dialog is None:
            return
        self._trash_dialog.set_entries(entries)
        self.status.setText(f"回收站中有 {len(entries)} 个可恢复舞蹈包。")

    def _request_conversion(self, video_path: str = "") -> None:
        video = video_path
        if not video:
            video, _ = QFileDialog.getOpenFileName(
                self,
                "选择真人舞蹈视频",
                "",
                VIDEO_FILTER,
            )
        if not video:
            return
        name = self._ask_new_name(Path(video).stem)
        if not name:
            return
        # Music is always extracted from the original dance video.
        self._last_conversion = (video, name, "")
        self.convertRequested.emit(video, name, "")

    def _ask_new_name(self, suggested: str) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle("新建舞蹈包")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("舞蹈包名称", dialog))
        edit = QLineEdit(dialog)
        edit.setText(suggested)
        edit.setPlaceholderText("例如：宿舍律动基础")
        edit.selectAll()
        layout.addWidget(edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        return edit.text().strip()

    def request_rename(self, current: str) -> tuple[bool, str]:
        dialog = _RenameDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False, current
        return True, dialog.name

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "舞蹈包操作失败", message)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
                self._request_conversion(str(path))
                event.acceptProposedAction()
                return

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        self._rebuild_grid()

    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.difficulty_filter.setCurrentIndex(0)
        self.quality_filter.setCurrentIndex(0)
        self.sort_order.setCurrentIndex(0)

    def _apply_filters(self, _value: object = None, *, force: bool = False) -> None:
        query = " ".join(self.search_input.text().casefold().split())
        difficulty = int(self.difficulty_filter.currentData() or 0)
        quality = str(self.quality_filter.currentData() or "")
        items = []
        for package in self._packages:
            haystack = " ".join(
                (
                    package.name,
                    package.gameplay.dance_type,
                    package.source_video,
                    package.gameplay.music_title,
                    " ".join(package.tags),
                )
            ).casefold()
            if query and query not in haystack:
                continue
            if difficulty and package.gameplay.difficulty != difficulty:
                continue
            if quality and package.quality.level.value != quality:
                continue
            items.append(package)
        order = str(self.sort_order.currentData() or "updated_desc")
        items.sort(key=self._sort_key(order))
        self._visible_packages = tuple(items)
        self._rebuild_grid(force=True)
        if self._packages:
            self.status.setText(
                f"显示 {len(self._visible_packages)} / {len(self._packages)} 个舞蹈包。"
            )
        else:
            self.status.setText("还没有舞蹈包。点击“添加舞蹈包”或拖入真人舞蹈视频。")

    @staticmethod
    def _sort_key(order: str):
        if order == "name_asc":
            return lambda package: package.name.casefold()
        if order == "quality_desc":
            return lambda package: -package.quality.score_confidence
        if order == "difficulty_asc":
            return lambda package: (package.gameplay.difficulty, package.name.casefold())
        if order == "duration_asc":
            return lambda package: (package.duration_s, package.name.casefold())
        return lambda package: package.updated_at

    def _rebuild_grid(self, *, force: bool = False) -> None:
        width = max(1, self.scroll.viewport().width())
        columns = max(1, min(5, (width - 8) // 252))
        if not force and columns == self._columns:
            return
        self._columns = columns
        for column in range(6):
            self.grid.setColumnStretch(column, 0)
        self.grid.setColumnStretch(columns, 1)
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, package in enumerate(self._visible_packages):
            card = DancePackageCard(package, self.grid_host)
            card.set_theme_mode(self._theme_mode)
            card.set_selected(package.package_id in self._selected_ids)
            card.selected.connect(self.selectRequested.emit)
            card.renameRequested.connect(self._rename_card)
            card.deleteRequested.connect(self.deleteRequested.emit)
            card.posterRequested.connect(self.posterRequested.emit)
            card.musicRequested.connect(self.musicRequested.emit)
            card.detailsRequested.connect(self._show_details)
            card.selectionChanged.connect(self._set_selection)
            self.grid.addWidget(
                card,
                index // columns,
                index % columns,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
        self.grid.setRowStretch(
            (len(self._visible_packages) + columns - 1) // columns,
            1,
        )
        has_items = bool(self._visible_packages)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

    def _set_selection(self, package_id: str, selected: bool) -> None:
        if selected:
            self._selected_ids.add(package_id)
        else:
            self._selected_ids.discard(package_id)
        self._update_batch_buttons()

    def _update_batch_buttons(self) -> None:
        busy = self.progress.isVisible()
        selected = bool(self._selected_ids)
        self.batch_rename_button.setEnabled(selected and not busy)
        self.batch_delete_button.setEnabled(selected and not busy)
        self.batch_rename_button.setText(f"批量改名 ({len(self._selected_ids)})")
        self.batch_delete_button.setText(f"批量删除 ({len(self._selected_ids)})")

    def _batch_rename(self) -> None:
        if not self._selected_ids:
            return
        dialog = _RenameDialog("Dance-", self)
        dialog.setWindowTitle("批量添加名称前缀")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        prefix = dialog.name
        if prefix:
            self.batchRenameRequested.emit(tuple(sorted(self._selected_ids)), prefix)

    def _batch_delete(self) -> None:
        count = len(self._selected_ids)
        if not count:
            return
        answer = QMessageBox.question(
            self,
            "批量移动到回收站",
            f"将选中的 {count} 个舞蹈包移动到本地回收站？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self.batchDeleteRequested.emit(tuple(sorted(self._selected_ids)))

    def show_trash_dialog(self) -> None:
        dialog = _TrashDialog(self)
        dialog.restoreRequested.connect(self.restoreTrashRequested.emit)
        dialog.purgeRequested.connect(self.purgeTrashRequested.emit)
        dialog.purgeAllRequested.connect(self.purgeAllTrashRequested.emit)
        dialog.finished.connect(lambda _result: setattr(self, "_trash_dialog", None))
        self._trash_dialog = dialog
        self.trashRequested.emit()
        dialog.exec()

    def _rename_card(self, package_id: str, current: str) -> None:
        accepted, name = self.request_rename(current)
        if accepted and name and name != current:
            self.renameRequested.emit(package_id, name)

    def _show_details(self, package_id: str) -> None:
        package = next(
            (item for item in self._packages if item.package_id == package_id),
            None,
        )
        if package is None:
            return
        dialog = _PackageDetailsDialog(package, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selectRequested.emit(package_id)
