# Skill: PyQt6 严格语法校验

## 触发条件
生成任何 PyQt6 代码后，输出前自检。

## 强制写法对照
| 错误(PyQt5) | 正确(PyQt6) |
|---|---|
| Qt.AlignCenter | Qt.AlignmentFlag.AlignCenter |
| Qt.Horizontal | Qt.Orientation.Horizontal |
| exec_() | exec() |
| e.pos().x() | e.position().x() |
| from QtWidgets import QAction | from QtGui import QAction |
| QApplication.desktop() | QApplication.primaryScreen().availableGeometry() |
| QFontMetrics.width() | horizontalAdvance() |

## 附加规则
- 高 DPI 默认开启，删除任何 AA_EnableHighDpiScaling 设置代码
- open() 必须显式 encoding="utf-8"
