"""Training history dashboard with trends, filters, and actionable insights."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dance_mirror.services.analytics import (
    filter_records,
    format_duration,
    normalize_records,
    package_options,
    record_change,
    record_package,
    summarize_history,
    top_cue,
    weakest_part,
)
from dance_mirror.services.progression import build_progression
from dance_mirror.services.report import build_history_report_html
from dance_mirror.storage.database import TrainingRecord
from dance_mirror.view.design_tokens import palette_for
from dance_mirror.view.fluent import (
    ComboBox as QComboBox,
)
from dance_mirror.view.fluent import (
    LineEdit as QLineEdit,
)
from dance_mirror.view.fluent import (
    PrimaryPushButton,
)
from dance_mirror.view.fluent import (
    PushButton as QPushButton,
)
from dance_mirror.view.fluent import (
    TableWidget as QTableWidget,
)


class _MetricCard(QFrame):
    """Compact KPI used by the history overview."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metric-card")
        self.setMinimumHeight(82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(2)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("metric-label")
        self.value_label = QLabel("--", self)
        self.value_label.setObjectName("metric-value")
        self.detail_label = QLabel("", self)
        self.detail_label.setObjectName("metric-caption")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str = "") -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)


class _TrendChart(QWidget):
    """Small dependency-free score trend chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._records: tuple[TrainingRecord, ...] = ()
        self._theme_mode = "light"
        self.setMinimumHeight(205)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_records(self, records: tuple[TrainingRecord, ...]) -> None:
        self._records = records
        self.update()

    def set_theme_mode(self, theme: str) -> None:
        self._theme_mode = "dark" if str(theme).lower() == "dark" else "light"
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        palette = palette_for(self._theme_mode)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self.rect()).adjusted(10, 8, -10, -8)
        if area.width() <= 20 or area.height() <= 20:
            return
        if len(self._records) < 2:
            painter.setPen(QColor(palette.muted))
            painter.drawText(
                area,
                Qt.AlignmentFlag.AlignCenter,
                "积累两次训练后显示趋势",
            )
            return

        plot = area.adjusted(34, 10, -12, -28)
        painter.setPen(QPen(QColor(palette.border), 1.0))
        for index in range(5):
            y = plot.bottom() - plot.height() * index / 4.0
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(palette.muted))
            painter.drawText(
                QRectF(area.left(), y - 8, 30, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(index * 25),
            )
            painter.setPen(QPen(QColor(palette.border), 1.0))

        ordered = tuple(reversed(self._records))
        points = []
        for index, record in enumerate(ordered):
            x = plot.left() + plot.width() * index / max(1, len(ordered) - 1)
            y = plot.bottom() - plot.height() * max(0.0, min(100.0, record.overall_score)) / 100.0
            points.append(QPointF(x, y))

        fill_points = QPolygonF([QPointF(plot.left(), plot.bottom()), *points, QPointF(plot.right(), plot.bottom())])
        gradient = QLinearGradient(0.0, plot.top(), 0.0, plot.bottom())
        primary = QColor(palette.primary)
        gradient.setColorAt(0.0, QColor(primary.red(), primary.green(), primary.blue(), 75))
        gradient.setColorAt(1.0, QColor(primary.red(), primary.green(), primary.blue(), 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPolygon(fill_points)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(primary, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPolyline(QPolygonF(points))
        painter.setBrush(primary)
        for point in points:
            painter.drawEllipse(point, 3.0, 3.0)

        painter.setPen(QColor(palette.muted))
        labels = min(3, len(ordered))
        for index in range(labels):
            record_index = round(index * (len(ordered) - 1) / max(1, labels - 1))
            x = plot.left() + plot.width() * record_index / max(1, len(ordered) - 1)
            text = _short_timestamp(ordered[record_index].started_at)
            painter.drawText(
                QRectF(x - 40, plot.bottom() + 7, 80, 18),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )


class _SortableItem(QTableWidgetItem):
    """Table item with numeric sorting for scores and durations."""

    def __init__(self, text: str, sort_value: float | str) -> None:
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return float(left) < float(right)
        return str(left) < str(right)


class HistoryInterface(QWidget):
    """Show trends, weak dimensions, recurring issues, and local records."""

    retrainRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("history-interface")
        self._records: tuple[TrainingRecord, ...] = ()
        self._filtered: tuple[TrainingRecord, ...] = ()
        self._theme_mode = "light"
        self.setMinimumWidth(720)
        self._build_ui()
        self._render()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(11)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("训练历史", self)
        title.setObjectName("page-title")
        subtitle = QLabel(
            "先看趋势和问题排行，再回到具体舞蹈片段的薄弱部位。数据仅保存在本机。",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("page-subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.export_button = QPushButton("导出 CSV", self)
        self.export_button.setProperty("variant", "ghost")
        self.export_button.clicked.connect(self._export_csv)
        self.report_button = PrimaryPushButton("导出 HTML 报告", self)
        self.report_button.clicked.connect(self._export_html_report)
        header.addWidget(self.export_button)
        header.addWidget(self.report_button)
        root.addLayout(header)

        filters = QFrame(self)
        filters.setObjectName("surface-card")
        filter_layout = QGridLayout(filters)
        filter_layout.setContentsMargins(11, 8, 11, 8)
        filter_layout.setHorizontalSpacing(8)
        filter_layout.setVerticalSpacing(7)
        self.search_input = QLineEdit(filters)
        self.search_input.setPlaceholderText("搜索舞蹈包、问题、部位或总结")
        self.package_filter = QComboBox(filters)
        self.package_filter.addItem("全部舞蹈包", "")
        self.time_filter = QComboBox(filters)
        self.time_filter.addItem("全部时间", None)
        self.time_filter.addItem("最近 7 天", 7)
        self.time_filter.addItem("最近 30 天", 30)
        self.time_filter.addItem("最近 90 天", 90)
        self.score_filter = QComboBox(filters)
        self.score_filter.addItem("全部分数", None)
        self.score_filter.addItem("90 分以上", (90.0, None))
        self.score_filter.addItem("80 - 90 分", (80.0, 90.0))
        self.score_filter.addItem("80 分以下", (None, 80.0))
        self.clear_button = QPushButton("清除筛选", filters)
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.clicked.connect(self._clear_filters)
        filter_layout.addWidget(self.search_input, 0, 0, 1, 2)
        filter_layout.addWidget(self.package_filter, 0, 2)
        filter_layout.addWidget(self.time_filter, 0, 3)
        filter_layout.addWidget(self.score_filter, 0, 4)
        filter_layout.addWidget(self.clear_button, 0, 5)
        filter_layout.setColumnStretch(0, 1)
        filter_layout.setColumnStretch(1, 1)
        root.addWidget(filters)

        self.search_input.textChanged.connect(self._apply_filters)
        self.package_filter.currentIndexChanged.connect(self._apply_filters)
        self.time_filter.currentIndexChanged.connect(self._apply_filters)
        self.score_filter.currentIndexChanged.connect(self._apply_filters)

        metric_layout = QGridLayout()
        metric_layout.setHorizontalSpacing(9)
        metric_layout.setVerticalSpacing(9)
        self.session_card = _MetricCard("训练次数", self)
        self.duration_card = _MetricCard("累计时长", self)
        self.average_card = _MetricCard("平均分", self)
        self.change_card = _MetricCard("最近变化", self)
        for column, card in enumerate(
            (self.session_card, self.duration_card, self.average_card, self.change_card)
        ):
            metric_layout.addWidget(card, 0, column)
            metric_layout.setColumnStretch(column, 1)
        root.addLayout(metric_layout)

        chart_frame = QFrame(self)
        chart_frame.setObjectName("surface-card")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(11, 9, 11, 8)
        chart_title = QLabel("总分趋势", chart_frame)
        chart_title.setObjectName("section-title")
        chart_layout.addWidget(chart_title)
        self.trend_chart = _TrendChart(chart_frame)
        chart_layout.addWidget(self.trend_chart, 1)
        root.addWidget(chart_frame, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        self.table = QTableWidget(splitter)
        self.table.setColumnCount(7)
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(
            ["时间", "舞蹈包", "总分", "变化", "时长", "最常见问题", "薄弱部位"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 7):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        splitter.addWidget(self.table)

        insight = QFrame(splitter)
        insight.setObjectName("surface-card")
        insight.setMinimumWidth(246)
        insight_layout = QVBoxLayout(insight)
        insight_layout.setContentsMargins(13, 12, 13, 12)
        insight_layout.setSpacing(7)
        insight_title = QLabel("本次结论", insight)
        insight_title.setObjectName("section-title")
        self.weakest_label = QLabel("首要薄弱部位：--", insight)
        self.weakest_label.setWordWrap(True)
        self.issue_label = QLabel("高频问题：--", insight)
        self.issue_label.setWordWrap(True)
        self.latest_label = QLabel("最近训练：暂无", insight)
        self.latest_label.setWordWrap(True)
        self.latest_label.setObjectName("coach-label")
        self.progress_label = QLabel("舞者进度：训练新星", insight)
        self.progress_label.setWordWrap(True)
        self.progress_label.setObjectName("section-title")
        self.badges_label = QLabel("徽章：暂无", insight)
        self.badges_label.setWordWrap(True)
        self.leaderboard_label = QLabel("本地排行：暂无", insight)
        self.leaderboard_label.setWordWrap(True)
        self.leaderboard_label.setObjectName("metric-caption")
        self.recommendation_label = QLabel("积累一次训练后会生成复训建议。", insight)
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setObjectName("report-card")
        self.retrain_button = PrimaryPushButton("复训所选舞蹈包", insight)
        self.retrain_button.setEnabled(False)
        self.retrain_button.clicked.connect(self._request_retrain)
        insight_layout.addWidget(insight_title)
        insight_layout.addWidget(self.weakest_label)
        insight_layout.addWidget(self.issue_label)
        insight_layout.addWidget(self.latest_label)
        insight_layout.addWidget(self.progress_label)
        insight_layout.addWidget(self.badges_label)
        insight_layout.addWidget(self.leaderboard_label)
        insight_layout.addWidget(self.recommendation_label)
        insight_layout.addStretch(1)
        insight_layout.addWidget(self.retrain_button)
        splitter.addWidget(insight)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([760, 290])
        root.addWidget(splitter, 2)

        self.status_label = QLabel("暂无训练记录。", self)
        self.status_label.setObjectName("page-subtitle")
        root.addWidget(self.status_label)

    def set_records(self, records: list[TrainingRecord] | tuple[TrainingRecord, ...]) -> None:
        self._records = normalize_records(records)
        self._refresh_package_filter()
        self._apply_filters()

    def set_theme_mode(self, theme: str) -> None:
        self._theme_mode = "dark" if str(theme).lower() == "dark" else "light"
        self.trend_chart.set_theme_mode(self._theme_mode)

    def _refresh_package_filter(self) -> None:
        selected = str(self.package_filter.currentData() or "")
        self.package_filter.blockSignals(True)
        self.package_filter.clear()
        self.package_filter.addItem("全部舞蹈包", "")
        for package_id, package_name in package_options(self._records):
            self.package_filter.addItem(package_name, package_id)
        index = self.package_filter.findData(selected)
        self.package_filter.setCurrentIndex(max(0, index))
        self.package_filter.blockSignals(False)

    def _apply_filters(self) -> None:
        score_range = self.score_filter.currentData()
        minimum: float | None = None
        maximum: float | None = None
        if isinstance(score_range, tuple):
            minimum, maximum = score_range
        self._filtered = filter_records(
            self._records,
            query=self.search_input.text(),
            package_id=str(self.package_filter.currentData() or ""),
            days=self.time_filter.currentData(),
            minimum_score=minimum,
            maximum_score=maximum,
        )
        self._render()

    def _render(self) -> None:
        summary = summarize_history(self._filtered)
        self.session_card.set_value(
            str(summary.sessions),
            f"覆盖 {summary.active_days} 个训练日" if summary.sessions else "等待第一次训练",
        )
        self.duration_card.set_value(
            format_duration(summary.total_duration_s),
            "当前筛选范围内",
        )
        self.average_card.set_value(
            f"{summary.average_score:.1f}" if summary.sessions else "--",
            f"最佳 {summary.best_score:.1f}" if summary.sessions else "暂无评分",
        )
        change_text = "--" if not summary.sessions else f"{summary.recent_change:+.1f}"
        self.change_card.set_value(
            change_text,
            f"最近一次 {summary.latest_score:.1f}" if summary.sessions else "暂无评分",
        )
        self.trend_chart.set_records(self._filtered)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for record in self._filtered:
            self._append_record(record)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self.table.setVisible(bool(self._filtered))
        if not self._filtered:
            self.status_label.setText(
                "当前筛选没有训练记录。清除筛选或完成一次训练后再查看。"
            )
        else:
            self.status_label.setText(
                f"显示 {len(self._filtered)} / {len(self._records)} 次训练。"
                "双击记录可回到对应舞蹈包准备复训。"
            )
        self._update_insights(summary)
        self._update_progression()

    def _append_record(self, record: TrainingRecord) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        package_id, package_name = record_package(record)
        change = record_change(self._records, record)
        values: list[QTableWidgetItem] = [
            _SortableItem(_display_timestamp(record.started_at), record.started_at),
            _SortableItem(package_name, package_name),
            _SortableItem(f"{record.overall_score:.1f}", record.overall_score),
            _SortableItem("--" if change is None else f"{change:+.1f}", change if change is not None else 0.0),
            _SortableItem(f"{record.duration_s:.0f} 秒", record.duration_s),
            _SortableItem(top_cue(record), top_cue(record)),
            _SortableItem(weakest_part(record), weakest_part(record)),
        ]
        values[0].setData(Qt.ItemDataRole.UserRole + 1, (record.session_id, package_id))
        for column, item in enumerate(values):
            if column in {2, 3, 4}:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, column, item)

    def _update_insights(self, summary: object) -> None:
        if not self._filtered:
            self.weakest_label.setText("首要薄弱部位：--")
            self.issue_label.setText("高频问题：--")
            self.latest_label.setText("最近训练：暂无")
            self.recommendation_label.setText("积累一次训练后会生成复训建议。")
            self.retrain_button.setEnabled(False)
            return
        latest = self._filtered[0]
        package_id, package_name = record_package(latest)
        self.weakest_label.setText(f"首要薄弱部位：{summary.weakest_part}")
        self.issue_label.setText(f"高频问题：{summary.top_issue}")
        self.latest_label.setText(
            f"最近训练：{package_name} · {latest.overall_score:.1f} 分\n"
            f"{_display_timestamp(latest.started_at)}"
        )
        self.recommendation_label.setText(
            f"下一次优先练：{summary.weakest_part}。"
            f"针对“{summary.top_issue}”做慢速重复，再逐步恢复原速。"
        )
        self.retrain_button.setEnabled(bool(package_id))
        self.retrain_button.setProperty("package_id", package_id)

    def _update_progression(self) -> None:
        progression = build_progression(self._filtered)
        shown_stars = "★" * progression.stars + "☆" * (3 - progression.stars)
        self.progress_label.setText(
            f"{progression.title}  {shown_stars}  最高连击 {progression.max_combo}\n"
            f"{progression.active_days} 个训练日 · {progression.sessions} 次训练"
        )
        badges = " / ".join(item.label for item in progression.badges) or "暂无"
        self.badges_label.setText(f"徽章：{badges}")
        if progression.leaderboard:
            ranking = "\n".join(
                f"{index}. {item.package_name}  {item.best_score:.1f} 分 · {item.sessions} 次"
                for index, item in enumerate(progression.leaderboard[:3], start=1)
            )
        else:
            ranking = "暂无"
        self.leaderboard_label.setText(f"本地排行：\n{ranking}")

    def _request_retrain(self) -> None:
        package_id = str(self.retrain_button.property("package_id") or "")
        if package_id:
            self.retrainRequested.emit(package_id)

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        payload = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(payload, tuple) and len(payload) == 2 and payload[1]:
            self.retrainRequested.emit(str(payload[1]))

    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.package_filter.setCurrentIndex(0)
        self.time_filter.setCurrentIndex(0)
        self.score_filter.setCurrentIndex(0)

    def _export_html_report(self) -> None:
        if not self._filtered:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 DanceMirror 训练报告",
            "DanceMirror_训练报告.html",
            "HTML 文件 (*.html)",
        )
        if not path:
            return
        try:
            Path(path).write_text(
                build_history_report_html(self._filtered),
                encoding="utf-8",
                newline="\n",
            )
        except OSError as exc:
            self.status_label.setText(f"报告导出失败：{exc}")
            return
        self.status_label.setText(f"已导出训练报告：{path}")

    def _export_csv(self) -> None:
        if not self._filtered:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出训练历史",
            "训练历史.csv",
            "CSV 文件 (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "时间",
                        "舞蹈包",
                        "总分",
                        "变化",
                        "时长秒",
                        "最常见问题",
                        "薄弱部位",
                        "总结",
                    ]
                )
                for record in self._filtered:
                    _, package_name = record_package(record)
                    change = record_change(self._records, record)
                    writer.writerow(
                        [
                            record.started_at,
                            package_name,
                            f"{record.overall_score:.2f}",
                            "" if change is None else f"{change:+.2f}",
                            f"{record.duration_s:.2f}",
                            top_cue(record),
                            weakest_part(record),
                            record.summary,
                        ]
                    )
        except OSError as exc:
            self.status_label.setText(f"导出失败：{exc}")
            return
        self.status_label.setText(f"已导出 {len(self._filtered)} 条记录：{path}")


def _short_timestamp(value: str) -> str:
    parsed = _parse_timestamp(value)
    return parsed.strftime("%m-%d") if parsed else "--"


def _display_timestamp(value: str) -> str:
    parsed = _parse_timestamp(value)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else str(value)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
