"""Fluent widget imports with a conservative Qt fallback for diagnostics."""

from __future__ import annotations

try:
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        CardWidget,
        CheckBox,
        DoubleSpinBox,
        FluentIcon,
        FluentWindow,
        HeaderCardWidget,
        ImageLabel,
        InfoBar,
        InfoBarPosition,
        LineEdit,
        ListWidget,
        NavigationItemPosition,
        PrimaryPushButton,
        ProgressBar,
        PushButton,
        ScrollArea,
        SearchLineEdit,
        SimpleCardWidget,
        Slider,
        SmoothScrollArea,
        SpinBox,
        StrongBodyLabel,
        SubtitleLabel,
        SwitchButton,
        TableWidget,
        Theme,
        TitleLabel,
        ToolButton,
        TransparentToolButton,
        isDarkTheme,
        setTheme,
        setThemeColor,
    )
    from qfluentwidgets import (
        ComboBox as _ComboBoxBackend,
    )
    from qfluentwidgets import (
        EditableComboBox as _EditableComboBoxBackend,
    )

    FLUENT_AVAILABLE = True
except ImportError:  # pragma: no cover - qfluentwidgets is a declared dependency
    from PyQt6.QtWidgets import (
        QCheckBox as CheckBox,
    )
    from PyQt6.QtWidgets import QComboBox as _ComboBoxBackend
    from PyQt6.QtWidgets import QComboBox as _EditableComboBoxBackend
    from PyQt6.QtWidgets import (
        QDoubleSpinBox as DoubleSpinBox,
    )
    from PyQt6.QtWidgets import (
        QFrame as CardWidget,
    )
    from PyQt6.QtWidgets import (
        QFrame as HeaderCardWidget,
    )
    from PyQt6.QtWidgets import (
        QFrame as SimpleCardWidget,
    )
    from PyQt6.QtWidgets import (
        QLabel as BodyLabel,
    )
    from PyQt6.QtWidgets import (
        QLabel as CaptionLabel,
    )
    from PyQt6.QtWidgets import (
        QLabel as ImageLabel,
    )
    from PyQt6.QtWidgets import (
        QLabel as StrongBodyLabel,
    )
    from PyQt6.QtWidgets import (
        QLabel as SubtitleLabel,
    )
    from PyQt6.QtWidgets import (
        QLabel as TitleLabel,
    )
    from PyQt6.QtWidgets import (
        QLineEdit as LineEdit,
    )
    from PyQt6.QtWidgets import (
        QLineEdit as SearchLineEdit,
    )
    from PyQt6.QtWidgets import (
        QListWidget as ListWidget,
    )
    from PyQt6.QtWidgets import (
        QProgressBar as ProgressBar,
    )
    from PyQt6.QtWidgets import (
        QPushButton as PrimaryPushButton,
    )
    from PyQt6.QtWidgets import (
        QPushButton as PushButton,
    )
    from PyQt6.QtWidgets import (
        QScrollArea as ScrollArea,
    )
    from PyQt6.QtWidgets import (
        QScrollArea as SmoothScrollArea,
    )
    from PyQt6.QtWidgets import (
        QSlider as Slider,
    )
    from PyQt6.QtWidgets import (
        QSpinBox as SpinBox,
    )
    from PyQt6.QtWidgets import (
        QTableWidget as TableWidget,
    )

    FluentIcon = None
    FluentWindow = None
    InfoBar = None
    InfoBarPosition = None
    NavigationItemPosition = None
    SwitchButton = CheckBox
    Theme = None
    ToolButton = PushButton
    TransparentToolButton = PushButton
    FLUENT_AVAILABLE = False

    def isDarkTheme() -> bool:  # noqa: N802 - qfluentwidgets API
        return False

    def setTheme(_theme: object) -> None:
        return None

    def setThemeColor(_color: object) -> None:
        return None


class ComboBox(_ComboBoxBackend):  # type: ignore[misc, valid-type]
    """Compatibility adapter for Qt's addItem(text, data) call contract."""

    def addItem(  # noqa: N802 - Qt API
        self,
        text: str,
        userData: object = None,
        icon: object | None = None,
    ) -> None:
        super().addItem(text, icon, userData)


class EditableComboBox(_EditableComboBoxBackend):  # type: ignore[misc, valid-type]
    """Editable Fluent combo box with Qt-compatible item data."""

    def addItem(  # noqa: N802 - Qt API
        self,
        text: str,
        userData: object = None,
        icon: object | None = None,
    ) -> None:
        super().addItem(text, icon, userData)


__all__ = [
    "BodyLabel",
    "CaptionLabel",
    "CardWidget",
    "CheckBox",
    "ComboBox",
    "EditableComboBox",
    "DoubleSpinBox",
    "FLUENT_AVAILABLE",
    "FluentIcon",
    "FluentWindow",
    "HeaderCardWidget",
    "ImageLabel",
    "InfoBar",
    "InfoBarPosition",
    "LineEdit",
    "ListWidget",
    "NavigationItemPosition",
    "PrimaryPushButton",
    "ProgressBar",
    "PushButton",
    "ScrollArea",
    "SearchLineEdit",
    "SimpleCardWidget",
    "Slider",
    "SmoothScrollArea",
    "SpinBox",
    "StrongBodyLabel",
    "SubtitleLabel",
    "SwitchButton",
    "TableWidget",
    "Theme",
    "TitleLabel",
    "ToolButton",
    "TransparentToolButton",
    "isDarkTheme",
    "setTheme",
    "setThemeColor",
]
