# Skill: PyQt-Fluent-Widgets 组件规范

## 触发条件
使用 qfluentwidgets 任何组件时。

## 规则
1. import 名是 qfluentwidgets，pip 包名必须与 Qt 绑定配对(PyQt6↔PyQt6-Fluent-Widgets)，禁止混装 PySide 版。
2. addSubInterface 的界面必须先 setObjectName("xxx-interface")，且唯一。
3. 禁止全局 setStyleSheet —— 会覆盖 Fluent 内部样式。自定义样式用精确选择器 + isDarkTheme() 分支。
4. ScrollArea 必须：enableTransparentBackground() + setWidgetResizable(True) + setWidget(w)。
5. 通知用 InfoBar(parent 必填)，耗时任务状态用 StateToolTip(setState(True) 结束)。
6. 对话框：确认类继承 MessageBoxBase，逻辑写在重写的 accept() 中。
7. 配置持久化用 QConfig 子类 + 单例，禁止手写 json 读写。
8. 组件不能在 Designer 拖拽，只能代码创建；不确定的 API 先查 examples/gallery 源码再写。

## 打包关联
涉及 PyInstaller 时自动附加：--collect-all qfluentwidgets --hidden-import PyQt6.QtSvg
（漏 QtSvg = 图标全空白，最高频打包事故）
