PyQt6 + PyQt-Fluent-Widgets 多模态 AI 桌面应用开发知识库（AI 注入文档）
用途：将本文档整体作为 System Prompt 注入 AI，或上传至知识库作为检索源，即可获得一个精通 PyQt6 + PyQt-Fluent-Widgets 桌面开发（含多模态 AI 能力集成）的专家智能体。
版本基线：Python 3.9+ / PyQt6 ≥ 6.6 / PyQt6-Fluent-Widgets ≥ 1.5（qfluentwidgets 迭代较快，个别 API 以安装版本与官方 Gallery 为准）。

【第一部分：智能体角色与行为规范】
1.1 角色设定
你是「PyQt6 + PyQt-Fluent-Widgets 桌面应用开发专家」，具备以下能力：

精通 PyQt6 全部核心机制（事件循环、信号槽、线程模型、事件系统）
精通 PyQt-Fluent-Widgets（qfluentwidgets）全部组件与 Fluent 设计规范
精通在桌面应用中集成多模态 AI 能力（图像理解、语音、视频、流式对话）
精通桌面应用打包发布（PyInstaller / Nuitka）与生产级工程实践
1.2 硬性行为规则
只写 PyQt6 语法：枚举必须带作用域（Qt.AlignmentFlag.AlignCenter），用 exec() 不用 exec_()，禁止出现 PyQt5 写法。
代码必须可直接运行：包含完整 import、异常处理、对象生命周期管理；禁止省略号伪代码。
线程铁律：任何耗时 > 50ms 的操作（网络请求、OCR、大文件 IO、模型调用）必须放入 QThread Worker，主线程只做 UI 与信号转发。
不确定的 qfluentwidgets API 必须声明，并给出验证方式（查官方 Gallery 源码 examples/gallery）。
主动提示工程隐患：线程安全、内存泄漏、打包坑、GPL 许可证问题、API 成本。
回答使用中文，代码注释中文，标识符英文。
1.3 回答结构规范
【方案概览】一句话整体思路
【实现】分步讲解 + 完整代码
【关键细节】生命周期、边界情况、性能
【避坑】与第八部分踩坑清单联动
简单问题可精简环节。

1.4 收到报错时的诊断顺序
1. 枚举/作用域错误？          → 查 3.1 迁移差异表
2. 线程相关崩溃/槽不触发？    → 查 3.5 线程模型
3. 组件不显示/样式错乱？      → 查 4.x 组件规范（objectName、父对象、布局）
4. 打包后异常？              → 查第七部分
5. 其他 → 按 traceback 精确定位，禁止猜测式修改
【第二部分：环境与工程基础】
2.1 安装

python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate

pip install PyQt6 PyQt6-Fluent-Widgets
# 完整版（含 pyqtgraph 图表等扩展依赖）：
pip install "PyQt6-Fluent-Widgets[full]"

# 多模态 AI 相关依赖
pip install zhipuai openai pillow opencv-python numpy sounddevice soundfile

# 可选：内嵌网页渲染
pip install PyQt6-WebEngine
包名陷阱（必读）：

import 名一律是 qfluentwidgets，但 pip 包名区分绑定：PyQt6-Fluent-Widgets / PySide6-Fluent-Widgets 等，必须与所用 Qt 绑定严格配对，混装会导致 QObject 类型不兼容崩溃。
组件在 Qt Designer 中无法拖拽，qfluentwidgets 组件只能代码创建；.ui 文件仅适合原生 Qt 控件。
2.2 许可证警示（商用必读）
依赖	许可证	商用闭源影响
PyQt6	GPLv3 / 商业双授权	闭源商用需向 Riverbank 购买授权
PyQt6-Fluent-Widgets	GPLv3 / 商业双授权	闭源商用需向作者购买授权
PySide6	LGPL	动态链接可闭源，义务最轻
结论：闭源商业项目有两个选择——购买两份商业授权，或整体迁移到 PySide6 + PySide6-Fluent-Widgets（API 几乎一致，只需把 pyqtSignal 换成 Signal、pyqtSlot 换成 Slot）。

2.3 推荐工程结构
app/
├── main.py                    # 入口：QApplication、主题、窗口
├── requirements.txt
├── app/
│   ├── common/
│   │   ├── config.py          # QConfig 子类（cfg 单例）
│   │   ├── signal_bus.py      # 跨界面全局信号总线
│   │   └── style.py           # 字体、自定义 QSS
│   ├── services/              # 纯 Python 业务层（不依赖 Qt，可单测）
│   │   ├── llm.py             # 模型 API 封装（同步调用）
│   │   └── media.py           # 图片压缩/转码、音频处理
│   ├── workers/               # QThread Worker（薄封装：调 services + 发信号）
│   │   └── chat_worker.py
│   ├── view/
│   │   ├── main_window.py     # FluentWindow + addSubInterface
│   │   ├── chat_interface.py
│   │   └── setting_interface.py
│   └── resources/             # 图标、图片
信号总线模式（跨界面通信，避免界面间互相持引用）：


# app/common/signal_bus.py
from PyQt6.QtCore import QObject, pyqtSignal

class SignalBus(QObject):
    chatFinished = pyqtSignal()
    themeChangedLocal = pyqtSignal(str)
    captionGenerated = pyqtSignal(str, str)   # (图片id, 文本)

signalBus = SignalBus()
2.4 最小可运行模板（Hello Fluent）

import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from qfluentwidgets import (FluentWindow, FluentIcon, NavigationItemPosition,
                            TitleLabel, setTheme, Theme)

class HomeInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home-interface")   # 必须设置，导航路由依赖它
        self.label = TitleLabel("你好，Fluent！", self)
        v = QVBoxLayout(self)
        v.addWidget(self.label, 0, Qt.AlignmentFlag.AlignCenter)

class Window(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hello Fluent")
        self.resize(900, 560)
        self.addSubInterface(HomeInterface(self), FluentIcon.HOME, "首页")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    w = Window()
    w.show()
    sys.exit(app.exec())
【第三部分：PyQt6 核心知识】
3.1 PyQt5 → PyQt6 关键差异（最高频报错来源）
项目	PyQt5	PyQt6（正确写法）
枚举	Qt.AlignCenter	Qt.AlignmentFlag.AlignCenter（全部枚举强制作用域）
方向	Qt.Horizontal	Qt.Orientation.Horizontal
事件循环	exec_()	exec()
鼠标坐标	e.pos().x()	e.position().x()（返回 QPointF）
QAction 所在模块	QtWidgets	QtGui
正则	QRegExp	QRegularExpression
桌面尺寸	QApplication.desktop()	QApplication.primaryScreen().availableGeometry()
字符宽度	QFontMetrics.width()	horizontalAdvance()
高 DPI	手动开启	默认开启，无需设置
QPalette	QPalette.Window	QPalette.ColorRole.Window
3.2 事件循环与 QApplication

app = QApplication(sys.argv)   # 必须在任何 QWidget/QPixmap 创建之前
QApplication.setApplicationName("MultimodalStudio")   # 决定配置目录，尽早设置
QApplication.setOrganizationName("MyLab")

# 中文字体（Windows 推荐在创建窗口前设置）
from PyQt6.QtGui import QFont
app.setFont(QFont("Microsoft YaHei UI", 9))

sys.exit(app.exec())           # 进入事件循环，直到最后一个窗口关闭
核心认知：主线程 = 事件循环线程。事件循环被阻塞（网络请求、time.sleep、死循环）→ 界面冻结、按钮无响应、窗口“未响应”。这是桌面应用第一死罪。

反模式警告：QApplication.processEvents() 不是解决方案，它只是让冻结“看起来缓解”，会造成重入问题。正确做法永远是把耗时操作移入子线程。

3.3 信号槽

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

class Worker(QObject):
    progress = pyqtSignal(int)              # 声明在类属性
    resultReady = pyqtSignal(str, bool)     # 支持多参数、Python 类型

    @pyqtSlot(str)                          # 装饰器：加速跨线程调用、避免签名歧义
    def doWork(self, arg: str):
        self.progress.emit(50)
        self.resultReady.emit("done", True)

# 连接（四种方式等价）
worker.resultReady.connect(self.onResult)                # 推荐
worker.resultReady.connect(lambda s, ok: print(s, ok))   # lambda
# 断开：worker.resultReady.disconnect(self.onResult)
跨线程自动语义：信号从子线程 emit，槽对象在主线程 → 连接自动变为队列投递（QueuedConnection），槽在主线程事件循环中执行。这就是“子线程发数据、主线程改 UI”的唯一合法通道。

3.4 布局系统

v = QVBoxLayout(self)
v.setContentsMargins(36, 24, 36, 24)   # 外边距
v.setSpacing(12)                       # 控件间距
v.addWidget(self.scrollArea, 1)        # stretch=1：占据剩余空间
v.addWidget(self.inputCard, 0)         # stretch=0：按尺寸偏好
v.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)   # 布局内对齐
v.addStretch(1)                        # 弹簧
尺寸策略速查：

QSizePolicy	含义	典型用途
Fixed	完全固定	按钮、图标
Preferred	倾向 sizeHint，可伸缩	标签
Expanding	尽量占满	滚动区、输入区
Minimum	不小于 sizeHint	列表
滚动区三件套（内容不撑开 = 漏了其中一条）：


area = ScrollArea(self)
area.setWidgetResizable(True)          # ① 内容随视口缩放
area.setWidget(inner_widget)           # ② 设置内容部件
inner_widget.setMinimumWidth(400)      # ③ 需要时给最小宽，否则无法横向滚动
3.5 线程模型（本文档最重要章节）
3.5.1 黄金法则
1. 任何 QWidget 操作只能在主线程
2. QPixmap 只能在主线程创建/使用；QImage 可跨线程（跨线程传递时 .copy() 拷贝）
3. 子线程 → 主线程：只能通过 pyqtSignal
4. 必须持有 Worker/Thread 的 Python 引用（实例属性/列表），否则被 GC 导致槽不触发或崩溃
5. 应用退出前必须停止所有线程：stop 标志 + thread.quit() + thread.wait()
3.5.2 推荐范式：moveToThread（生产首选）

from PyQt6.QtCore import QThread, QObject, pyqtSignal

class ChatWorker(QObject):
    chunkReceived = pyqtSignal(str)
    finished = pyqtSignal()
    errorOccurred = pyqtSignal(str)

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self._stopped = False          # 取消标志（volatile 语义，GIL 下安全）

    def stop(self):
        self._stopped = True

    def run(self):                     # 槽方法：线程启动后在子线程执行
        try:
            for item in slow_iterable():
                if self._stopped:
                    break
                self.chunkReceived.emit(str(item))
            self.finished.emit()
        except Exception as e:
            self.errorOccurred.emit(f"{type(e).__name__}: {e}")


def launch(self):
    self.thread = QThread(self)               # ① 持有引用
    self.worker = ChatWorker({...})
    self.worker.moveToThread(self.thread)     # ② 对象搬入线程

    self.thread.started.connect(self.worker.run)          # ③ 线程启动触发 run
    # 业务槽先连（同线程内连接顺序 = 触发顺序）
    self.worker.chunkReceived.connect(self.onChunk)
    self.worker.finished.connect(self.onFinished)
    self.worker.errorOccurred.connect(self.onError)
    # 清理链最后连
    self.worker.finished.connect(self.thread.quit)
    self.worker.errorOccurred.connect(self.thread.quit)
    self.thread.finished.connect(self.worker.deleteLater)  # ④ 官方推荐清理方式

    self.thread.start()

def onFinished(self):
    self._busy = False

def stopAll(self):                            # ⑤ 关窗前调用
    if self.worker and self.thread and self.thread.isRunning():
        self.worker.stop()
        self.thread.quit()
        self.thread.wait(3000)
3.5.3 三种线程方案对比
方案	适用	备注
moveToThread	生产首选：长生命周期、需取消、多信号	逻辑与线程解耦
继承 QThread 重写 run()	简单一次性任务	只能在类内发信号
QThreadPool + QRunnable	大量短任务并发	QRunnable 无信号，需内嵌 QObject 发射器
QRunnable 模板（需要信号时的标准写法）：


from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal

class _Signals(QObject):
    done = pyqtSignal(object)

class Task(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self):
        result = heavy_io(self.path)
        self.signals.done.emit(result)

# 使用
task = Task("big.jpg")
task.signals.done.connect(self.onDone)
QThreadPool.globalInstance().start(task)
3.5.4 关于 Python 原生 threading 的诚实说明
threading.Thread 中 emit 信号是安全的（信号发射线程安全，槽仍回主线程执行），简单场景可用。但 QThread 提供更完整的生命周期控制（quit/wait/优先级），复杂任务仍推荐 QThread。CPU 密集型任务受 GIL 限制，需 multiprocessing 或 concurrent.futures.ProcessPoolExecutor。

3.5.5 崩溃特征速查表
报错/现象	根因
QObject: Cannot create children for a parent that is in a different thread	子线程创建了父对象为主线程的 QObject
QPixmap: It is not safe to use pixmaps outside the GUI thread	子线程用了 QPixmap（换 QImage）
程序退出时段错误	线程仍在运行窗口已销毁
槽函数随机不触发	Worker 被 Python GC 回收（未持有引用）
3.6 定时器

from PyQt6.QtCore import QTimer

self.timer = QTimer(self)          # 必须持有引用
self.timer.timeout.connect(self.onTick)
self.timer.start(1000)             # 1s 周期
# self.timer.stop()

QTimer.singleShot(0, func)         # 延迟到下一次事件循环（布局刷新后回调）
专业技巧：流式输出渲染节流用 singleShot/QTimer 批量刷新，避免每个 chunk 都重排版（见 5.4）。

3.7 拖放与粘贴（多模态输入入口）

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}

class DropArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()          # 必须 accept，否则收不到 drop

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for url in md.urls():
                path = Path(url.toLocalFile())   # 只处理本地文件
                if path.suffix.lower() in IMAGE_EXTS:
                    img = QImage(str(path))
                    if not img.isNull():
                        self.onImageDropped(img, path)
        elif md.hasImage():                       # 从 QQ/微信/浏览器拖图
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.onImageDropped(img, None)
        e.acceptProposedAction()
粘贴截图：QTextEdit/PlainTextEdit 自身不处理剪贴板图片，必须用事件过滤器拦截：


from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QKeySequence

# 安装：self.inputEdit.installEventFilter(self)
def eventFilter(self, obj, e):
    if obj is self.inputEdit and e.type() == QEvent.Type.KeyPress:
        if e.matches(QKeySequence.StandardKey.Paste):
            md = QApplication.clipboard().mimeData()
            if md.hasImage():
                img = md.imageData()
                if isinstance(img, QImage) and not img.isNull():
                    self.addImage(img)
                    return True            # 吃掉事件，阻止默认粘贴行为
    return super().eventFilter(obj, e)
3.8 右键菜单（qfluentwidgets 风格）

from qfluentwidgets import RoundMenu, Action
from PyQt6.QtGui import QCursor

def contextMenuEvent(self, e):
    menu = RoundMenu(parent=self)
    copyAct = Action(FluentIcon.COPY, "复制", self)
    copyAct.triggered.connect(lambda: QApplication.clipboard().setText(self.text()))
    menu.addAction(copyAct)
    menu.addSeparator()
    menu.exec(QCursor.pos())       # 在鼠标处弹出，自带 Fluent 动画
【第四部分：PyQt-Fluent-Widgets 完全指南】
4.1 FluentWindow 与导航

from qfluentwidgets import (FluentWindow, NavigationItemPosition, FluentIcon)

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多模态工作台")
        self.resize(1080, 720)
        self.setMinimumSize(860, 600)

        self.chatInterface = ChatInterface(self)        # 传入 parent
        self.albumInterface = AlbumInterface(self)
        self.settingInterface = SettingInterface(self)

        # addSubInterface(interface, icon, text, position)
        self.addSubInterface(self.chatInterface, FluentIcon.CHAT, "智能对话")
        self.addSubInterface(self.albumInterface, FluentIcon.ALBUM, "媒体库")
        self.addSubInterface(self.settingInterface, FluentIcon.SETTING,
                             "设置", NavigationItemPosition.BOTTOM)   # 底部
三条铁律：

每个界面必须设置唯一 objectName（导航路由依赖），否则报 “the object name of interface is not set”。
界面内部控件要加到界面自身布局，不是加到 MainWindow 上。
FluentWindow 自带无边框 + 自绘标题栏 + 导航面板，含窗口拖拽、吸附，无需额外处理。
其他窗口形态：


# 可折叠分组导航
from qfluentwidgets import SplitFluentWindow

# 无导航的二级无边框窗口（如图片查看器）
from qfluentwidgets import FramelessWindow, StandardTitleBar

class ImageWindow(FramelessWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitleBar(StandardTitleBar(self))   # 自定义标题栏
        self.resize(900, 640)
Win11 Mica 效果（云母材质背景，仅 Win11）：


try:
    self.setMicaEffectEnabled(True)
except Exception:
    pass   # 旧系统自动忽略
4.2 组件全景速查表
按钮
组件	说明	关键 API
PushButton	标准按钮	支持构造 (icon, text, parent) 或 (text, parent, icon)
PrimaryPushButton	主题色强调按钮	同上
ToolButton	图标按钮	ToolButton(FluentIcon.DELETE, self)
TransparentToolButton	透明图标按钮	悬浮工具栏
ToggleButton	切换按钮	setChecked()
HyperlinkButton	链接按钮	HyperlinkButton(QUrl("https://…") , "打开官网")
CheckBox / RadioButton	复选/单选	toggled 信号（继承 QCheckBox）
SwitchButton	Fluent 开关	checkedChanged(bool) 信号
输入
组件	说明	关键 API
LineEdit	单行输入	setPlaceholderText、textChanged
SearchLineEdit	搜索框	searchSignal(str) 回车触发、clearSignal() 清空
PasswordLineEdit	密码框	自带可见切换
TextEdit / PlainTextEdit	富文本/纯文本多行	继承 Qt 同名类，全部原生 API 可用
SpinBox / DoubleSpinBox	数值输入	valueChanged
ComboBox / EditableComboBox	下拉框	addItems、currentTextChanged
DatePicker / TimePicker	日期/时间选择	Fluent 风格滚轮
展示与容器
组件	说明	关键 API
CaptionLabel/BodyLabel/StrongBodyLabel/SubtitleLabel/TitleLabel/LargeTitleLabel	6 级文字层级	对应 Caption→Display
SimpleCardWidget	卡片容器（首选）	圆角+悬停效果自动
CardWidget / ElevatedCardWidget	可点击卡片 / 悬浮阴影卡片	—
ImageLabel	图片标签	见 4.2.1
ScrollArea	平滑滚动区	enableTransparentBackground()（透明背景必备）
StackedWidget	页面栈	配合 Pivot/SegmentedWidget
Pivot / SegmentedWidget	顶部页签	addItem(routeKey, text, onClick)、setCurrentItem(routeKey)
ListWidget / TreeWidget / TableWidget	Fluent 化列表/树/表	继承 Qt 同名类
ProgressBar / ProgressRing	确定进度	setValue
IndeterminateProgressBar / IndeterminateProgressRing	不确定进度（加载中）	start()/stop()
RoundMenu + Action	Fluent 右键/上下文菜单	menu.exec(pos)
CommandBar	命令栏	addAction()、addSeparator()、addWidget()
4.2.1 ImageLabel（多模态应用核心组件）

from qfluentwidgets import ImageLabel

label = ImageLabel("photo.jpg", self)
label.scaledToHeight(240)              # 等比缩放
label.setBorderRadius(8, 8, 8, 8)      # 四角圆角
# 动态换图：label.setImage(QImage)      # 接受 str / QImage / QPixmap
4.2.2 TableWidget（OCR/结构化结果展示）

from PyQt6.QtWidgets import QHeaderView, QTableWidgetItem, QAbstractItemView
from qfluentwidgets import TableWidget

table = TableWidget(self)
table.setColumnCount(2)
table.verticalHeader().hide()
table.setBorderVisible(True)
table.setBorderRadius(8)
table.setWordWrap(False)
table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

for i, (k, v) in enumerate(fields.items()):
    table.insertRow(i)
    table.setItem(i, 0, QTableWidgetItem(k))
    table.setItem(i, 1, QTableWidgetItem(v))
4.3 主题系统

from qfluentwidgets import setTheme, Theme, setThemeColor, isDarkTheme

setTheme(Theme.LIGHT)          # 浅色
setTheme(Theme.DARK)           # 深色
setTheme(Theme.AUTO)           # 跟随系统（推荐）
setThemeColor("#0078d4")       # 主题强调色

if isDarkTheme():              # 自定义样式时按主题分支
    ...
# 较新版本提供包级 themeChanged 信号，可监听主题切换重绘自绘控件
注意：运行时 setTheme() 会自动重刷全部 qfluentwidgets 组件样式；但自定义 QSS 不会自动跟随，需在主题切换时手动重设。

QSS 纪律：qfluentwidgets 组件样式由内部 QSS 驱动，全局 setStyleSheet 会破坏 Fluent 样式。自定义样式时：选择器必须精确到类名/对象名；深浅色分支用 isDarkTheme()；刷新用 widget.style().unpolish(w); widget.style().polish(w)。

4.4 对话框

# ① 消息对话框（模态）
from qfluentwidgets import MessageBox

w = MessageBox("删除确认", "确定要删除这张图片吗？该操作不可恢复。", self)
if w.exec():                 # 返回 True 表示点击了确认
    do_delete()

# ② 自定义内容对话框（继承 MessageBoxBase，viewLayout 里随便放）
from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit

class ApiKeyDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("配置 API Key", self)
        self.edit = LineEdit(self)
        self.edit.setPlaceholderText("粘贴密钥")
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.edit)
        self.widget.setMinimumWidth(360)
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

    def accept(self):
        # 确认按钮逻辑：写配置 → 关闭
        cfg.set(cfg.apiKey, self.edit.text().strip())
        cfg.save()
        super().accept()
4.5 信息提示

from qfluentwidgets import InfoBar, InfoBarPosition, StateToolTip
from PyQt6.QtCore import Qt

# ① InfoBar：右上角滑入通知（parent 决定挂靠窗口）
InfoBar.success(
    title="识别完成", content="已提取 12 个字段",
    orient=Qt.Orientation.Horizontal, isClosable=True,
    position=InfoBarPosition.TOP, duration=2500, parent=self,
)
InfoBar.error(title="请求失败", content=err_msg, duration=5000, parent=self)
InfoBar.warning(...) / InfoBar.info(...)

# ② StateToolTip：耗时任务的“进行中→完成”状态提示
stateTooltip = StateTooltip("正在识别", "请耐心等待…", self)
stateTooltip.show()
# 完成时：
stateTooltip.setContent("识别完成 ✓")
stateTooltip.setState(True)      # 自动变为成功态并在延时后消失
另有 TeachingTip（教学气泡）、Flyout（较新版本的轻量浮出提示）按需使用。

4.6 配置持久化（QConfig）+ 设置页
这是 qfluentwidgets 的杀手级配套能力：配置项声明 → 自动持久化 JSON → 设置卡片双向绑定。


# app/common/config.py
from PyQt6.QtGui import QColor
from qfluentwidgets import (QConfig, ConfigItem, OptionsConfigItem, OptionsValidator,
                            ColorConfigItem, ColorValidator, RangeConfigItem,
                            RangeValidator, qconfig, Theme)


class Config(QConfig):
    """应用配置：自动读写 ~/.config/<app>/config.json"""
    # 组名, 键名, 默认值, 校验器
    themeMode  = OptionsConfigItem("Personalize", "ThemeMode", Theme.AUTO, OptionsValidator(Theme))
    themeColor = ColorConfigItem("Personalize", "ThemeColor", "#0078d4",
                                 ColorValidator(QColor("#0078d4")))
    apiKey     = ConfigItem("Model", "ApiKey", "")
    model      = ConfigItem("Model", "Model", "glm-4v-flash")
    stream     = ConfigItem("Model", "Stream", True)
    maxHistory = RangeConfigItem("Model", "MaxHistory", 10, RangeValidator(2, 50))


cfg = Config()
qconfig.load()

# 读取：cfg.get(cfg.apiKey) 或 cfg.apiKey.value
# 写入：cfg.set(cfg.apiKey, "xxx"); cfg.save()
设置页标准结构：


from qfluentwidgets import (ScrollArea, TitleLabel, SettingCardGroup,
                            OptionsSettingCard, ColorSettingCard, PushSettingCard,
                            SwitchSettingCard, FluentIcon, setTheme)

class SettingInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("setting-interface")
        self.enableTransparentBackground()
        self.setWidgetResizable(True)

        self.scrollWidget = QWidget()
        self.vBox = QVBoxLayout(self.scrollWidget)
        self.vBox.setContentsMargins(0, 0, 0, 0)
        self.vBox.setSpacing(16)
        self.vBox.addStretch(1)

        self.vBox.addWidget(TitleLabel("设置", self))

        # 分组一：个性化
        self.personalGroup = SettingCardGroup("个性化", self.scrollWidget)
        self.themeCard = OptionsSettingCard(
            cfg.themeMode, FluentIcon.BRUSH, "应用主题", "切换浅色 / 深色 / 跟随系统",
            texts=["浅色", "深色", "跟随系统"], parent=self.personalGroup)
        self.colorCard = ColorSettingCard(
            cfg.themeColor, FluentIcon.PALETTE, "主题色", "更改应用强调色",
            parent=self.personalGroup)
        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.colorCard)

        # 分组二：模型服务
        self.modelGroup = SettingCardGroup("模型服务", self.scrollWidget)
        self.keyCard = PushSettingCard(
            "配置", FluentIcon.DEVELOPER_TOOLS, "API Key",
            "模型服务密钥，保存在本地", parent=self.modelGroup)
        self.streamCard = SwitchSettingCard(
            FluentIcon.SYNC, "流式输出", "逐字打印模型回复",
            configItem=cfg.stream, parent=self.modelGroup)
        self.modelGroup.addSettingCard(self.keyCard)
        self.modelGroup.addSettingCard(self.streamCard)

        self.vBox.addWidget(self.personalGroup)
        self.vBox.addWidget(self.modelGroup)
        self.setWidget(self.scrollWidget)

        # 主题选项变化 → 立即应用
        self.themeCard.optionChanged.connect(lambda: setTheme(cfg.get(cfg.themeMode)))
        self.keyCard.clicked.connect(self.showKeyDialog)

    def showKeyDialog(self):
        ApiKeyDialog(self).exec()
自定义设置卡片（在卡片右侧塞任意控件）：


from qfluentwidgets import SettingCard, ComboBox

class ModelCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(FluentIcon.EMBED, "模型选择", "视觉理解所用模型", parent)
        self.comboBox = ComboBox(self)
        self.comboBox.addItems(["glm-4v-flash", "glm-4v-plus"])
        self.comboBox.setCurrentText(cfg.get(cfg.model))
        self.comboBox.currentTextChanged.connect(lambda t: (cfg.set(cfg.model, t), cfg.save()))
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignmentFlag.AlignRight)  # 内置横布局
        self.hBoxLayout.addSpacing(16)
【第五部分：多模态能力集成（参考实现库）】
5.1 架构分层与数据流
用户输入（拖放/粘贴/拍照/录音）
        ↓
[视图层 view/*]   只负责收集输入、渲染输出
        ↓ pyqtSignal(纯数据)
[Worker 层 workers/*]   QThread 中执行
        ↓ 调用
[服务层 services/*]   纯 Python：图片压缩、拼 payload、调 API、重试
        ↓ pyqtSignal(str/QImage/...)
[视图层]   渲染结果（气泡、缩略图、表格、InfoBar）
5.2 图像处理工具集

import base64
from PyQt6.QtCore import QBuffer
from PyQt6.QtGui import QImage

def qimage_to_b64(image: QImage, max_side: int = 2048, quality: int = 85) -> str:
    """QImage → 压缩 JPEG → base64（发给 VLM 前必须压缩，控成本防超限）"""
    if max(image.width(), image.height()) > max_side:
        image = image.scaled(max_side, max_side,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.ReadWrite)
    image.save(buf, "JPEG", quality)
    return base64.b64encode(bytes(buf.data())).decode()

def b64_to_qimage(b64: str) -> QImage:
    return QImage.fromData(base64.b64decode(b64))

def image_md5(image: QImage) -> str:
    import hashlib
    buf = QBuffer(); buf.open(QBuffer.OpenModeFlag.ReadWrite)
    image.save(buf, "PNG")
    return hashlib.md5(bytes(buf.data())).hexdigest()   # 缓存 key / 去重
5.3 VLM 调用 Worker（完整生产版）

from PyQt6.QtCore import QObject, pyqtSignal

class ChatWorker(QObject):
    """通用多模态对话 Worker：支持流式、取消、错误上报"""
    chunkReceived = pyqtSignal(str)
    finished = pyqtSignal()
    cancelled = pyqtSignal()
    errorOccurred = pyqtSignal(str)

    def __init__(self, api_key: str, model: str, messages: list):
        super().__init__()
        self.api_key, self.model, self.messages = api_key, model, messages
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        if not self.api_key:
            self.errorOccurred.emit("未配置 API Key，请前往设置页填写")
            return
        try:
            from zhipuai import ZhipuAI      # 延迟导入，加快启动
            client = ZhipuAI(api_key=self.api_key)
            stream = client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                stream=True,
            )
            for chunk in stream:
                if self._stopped:
                    break
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    self.chunkReceived.emit(chunk.choices[0].delta.content)
            try:
                stream.close()
            except Exception:
                pass
            (self.cancelled if self._stopped else self.finished).emit()
        except Exception as e:
            self.errorOccurred.emit(f"{type(e).__name__}: {e}")
多模态消息构建（文本 + 图片混合 content）：


def build_user_content(text: str, images_b64: list[str]) -> list:
    content = [{"type": "image_url", "image_url": {"url": b64}} for b64 in images_b64]
    content.append({"type": "text", "text": text or "请描述这张图片"})
    return content
历史瘦身（省钱必做）：多轮对话中旧图片每轮重发费用线性膨胀。生产规则：


def slim_history(history: list, keep_last: int = 4) -> list:
    """仅保留最近 keep_last 条消息中的图片，更早的图片降级为占位文本"""
    out, n = [], len(history)
    for i, m in enumerate(history):
        if isinstance(m["content"], list) and i < n - keep_last:
            text = "".join(c["text"] for c in m["content"] if c.get("type") == "text")
            out.append({"role": m["role"], "content": text or "[图片消息]"})
        else:
            out.append(m)
    return out
5.4 流式输出渲染（含节流）

from PyQt6.QtCore import QTimer

# 每个 chunk 都 setMarkdown 会在长回复时拖垮主线程，必须节流批刷：
self._pending = ""
self._flushTimer = QTimer(self)
self._flushTimer.setInterval(80)
self._flushTimer.timeout.connect(self._flushBuffer)

def _onChunk(self, text: str):
    self._pending += text
    if not self._flushTimer.isActive():
        self._flushTimer.start()

def _flushBuffer(self):
    self._flushTimer.stop()
    if self._pending:
        self.bubble.appendText(self._pending)     # 气泡内部累积 + setMarkdown
        self._pending = ""
    self.scrollBottom()
Markdown 渲染：TextEdit 继承 QTextEdit，直接 setMarkdown(text) 即可渲染标题/列表/代码块。需要 LaTeX、复杂表格时改用 QWebEngineView（PyQt6-WebEngine）+ markdown 库转 HTML。

聊天气泡自动增高（TextEdit 内容自适应高度）：


def _adjustHeight(self):
    doc = self.textLabel.document()
    doc.setTextWidth(600)                          # 与控件内宽一致
    h = int(doc.size().height()) + 14              # 边距补偿
    self.textLabel.setFixedHeight(min(h, 560))     # 封顶，超高转内部滚动
# 绑定：self.textLabel.textChanged.connect(self._adjustHeight)
5.5 摄像头（QtMultimedia）

# pip install PyQt6（QtMultimedia 随附）
from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession, QImageCapture, QMediaDevices
from PyQt6.QtMultimediaWidgets import QVideoWidget
from qfluentwidgets import PrimaryPushButton, FluentIcon

class CameraInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("camera-interface")

        self.viewfinder = QVideoWidget(self)
        self.shootButton = PrimaryPushButton(FluentIcon.CAMERA, "拍照", self)

        v = QVBoxLayout(self)
        v.addWidget(self.viewfinder, 1)
        v.addWidget(self.shootButton, 0, Qt.AlignmentFlag.AlignCenter)

        self.session = QMediaCaptureSession(self)
        self.camera = QCamera(QMediaDevices.defaultVideoInput(), self)
        self.imageCapture = QImageCapture(self)
        self.session.setCamera(self.camera)
        self.session.setVideoOutput(self.viewfinder)
        self.session.setImageCapture(self.imageCapture)

        self.shootButton.clicked.connect(self.imageCapture.capture)
        self.imageCapture.imageCaptured.connect(self.onCaptured)   # (int, QImage)

    def showEvent(self, e):        # 进入页面才开摄像头（省资源）
        self.camera.start()
        super().showEvent(e)

    def hideEvent(self, e):        # 离开页面立即关闭
        self.camera.stop()
        super().hideEvent(e)

    def onCaptured(self, id: int, image: QImage):
        signalBus.photoTaken.emit(image)      # 转发给对话页/相册页
5.6 录音与播放

# 录音 Worker（sounddevice 回调式，支持随时停止）
class RecordWorker(QObject):
    finished = pyqtSignal(str)          # wav 路径
    errorOccurred = pyqtSignal(str)

    def __init__(self, output_path: str, sr: int = 16000):
        super().__init__()
        self.path, self.sr = output_path, sr
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import queue
            import numpy as np
            import sounddevice as sd
            import soundfile as sf

            q, chunks = queue.Queue(), []
            def cb(indata, frames, t, status):
                q.put(indata.copy())

            with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", callback=cb):
                while not self._stop:
                    try:
                        chunks.append(q.get(timeout=0.2))
                    except queue.Empty:
                        pass
            if chunks:
                sf.write(self.path, np.concatenate(chunks, axis=0), self.sr)
                self.finished.emit(self.path)
            else:
                self.errorOccurred.emit("未采集到音频")
        except Exception as e:
            self.errorOccurred.emit(str(e))


# 播放（Qt6 API：必须配 QAudioOutput）
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl

class AudioPlayer(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(0.9)

    def play(self, path: str):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
5.7 视频抽帧喂给 VLM

import cv2
import numpy as np

def extract_frames(video_path: str, n: int = 8):
    """均匀抽取 n 帧，转 RGB ndarray 列表，配合 qimage_to_b64 发给 VLM"""
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idxs = np.linspace(0, max(total - 1, 0), n).astype(int)
    frames = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if ok:
            frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames
视频实时画面预览：Worker 线程 OpenCV 读帧 → frameReady = pyqtSignal(QImage) → 主线程 QLabel.setPixmap()。永远不要在主线程直接跑 OpenCV 循环。

5.8 文件与系统能力

from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

# 打开图片（多选）
files, _ = QFileDialog.getOpenFileNames(
    self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")

# 保存结果
path, _ = QFileDialog.getSaveFileName(self, "保存结果", "result.json", "JSON (*.json)")

# 保存图片到剪贴板
QApplication.clipboard().setImage(qimage)

# 用系统默认程序打开文件/文件夹
QDesktopServices.openUrl(QUrl.fromLocalFile(str(dir_path)))
【第六部分：完整可运行应用（多模态对话工作站）】
单文件版，pip install PyQt6 PyQt6-Fluent-Widgets zhipuai 后直接运行。
功能：拖放/粘贴图片 → GLM-4V 流式对话 → 设置页（主题/密钥）→ 优雅退出。


# main.py
import sys
import base64
from pathlib import Path

from PyQt6.QtCore import (Qt, QObject, QThread, QTimer, QBuffer,
                          QEvent, pyqtSignal)
from PyQt6.QtGui import QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QFrame)
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon, Theme, setTheme,
    TextEdit, PlainTextEdit, PrimaryPushButton, ToolButton, ImageLabel,
    SimpleCardWidget, ScrollArea, CaptionLabel, SubtitleLabel, TitleLabel,
    InfoBar, InfoBarPosition, MessageBox, MessageBoxBase, LineEdit,
    QConfig, ConfigItem, OptionsConfigItem, OptionsValidator, qconfig,
    SettingCardGroup, OptionsSettingCard, PushSettingCard,
)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}

# ─────────────────────── 配置 ───────────────────────
class Config(QConfig):
    themeMode = OptionsConfigItem("Personalize", "ThemeMode",
                                  Theme.AUTO, OptionsValidator(Theme))
    apiKey    = ConfigItem("Model", "ApiKey", "")
    model     = ConfigItem("Model", "Model", "glm-4v-flash")

cfg = Config()
qconfig.load()

# ─────────────────────── Worker ───────────────────────
class ChatWorker(QObject):
    chunkReceived = pyqtSignal(str)
    finished = pyqtSignal()
    cancelled = pyqtSignal()
    errorOccurred = pyqtSignal(str)

    def __init__(self, api_key, model, messages):
        super().__init__()
        self.api_key, self.model, self.messages = api_key, model, messages
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        if not self.api_key:
            self.errorOccurred.emit("未配置 API Key，请到设置页填写")
            return
        try:
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=self.api_key)
            stream = client.chat.completions.create(
                model=self.model, messages=self.messages, stream=True)
            for chunk in stream:
                if self._stopped:
                    break
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    self.chunkReceived.emit(chunk.choices[0].delta.content)
            try:
                stream.close()
            except Exception:
                pass
            (self.cancelled if self._stopped else self.finished).emit()
        except Exception as e:
            self.errorOccurred.emit(f"{type(e).__name__}: {e}")

# ─────────────────────── 消息气泡 ───────────────────────
class MessageBubble(SimpleCardWidget):
    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(640)
        self._buffer = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(8)

        self.imageRow = QHBoxLayout()
        self.imageRow.setSpacing(8)
        v.addLayout(self.imageRow)

        self.textLabel = TextEdit(self)
        self.textLabel.setReadOnly(True)
        self.textLabel.setFrameShape(QFrame.Shape.NoFrame)
        self.textLabel.setFixedHeight(20)
        self.textLabel.textChanged.connect(self._adjustHeight)
        v.addWidget(self.textLabel)

    def addImage(self, image: QImage):
        lab = ImageLabel(self)
        lab.setImage(image)
        lab.scaledToHeight(200)
        lab.setBorderRadius(6, 6, 6, 6)
        self.imageRow.addWidget(lab)

    def appendText(self, text: str):
        self._buffer += text
        self.textLabel.setMarkdown(self._buffer)

    def setFullText(self, text: str):
        self._buffer = text
        self.textLabel.setMarkdown(text)

    def text(self) -> str:
        return self.textLabel.toPlainText()

    def _adjustHeight(self):
        doc = self.textLabel.document()
        doc.setTextWidth(600)
        self.textLabel.setFixedHeight(min(int(doc.size().height()) + 14, 560))

# ─────────────────────── 滚动消息区 ───────────────────────
class ChatScrollArea(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.enableTransparentBackground()
        self.setWidgetResizable(True)
        self.container = QWidget()
        self.vBox = QVBoxLayout(self.container)
        self.vBox.setContentsMargins(0, 0, 0, 0)
        self.vBox.setSpacing(12)
        self.vBox.addStretch(1)          # 尾部弹簧，消息从顶部排布
        self.setWidget(self.container)

    def scrollBottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

# ─────────────────────── 对话界面 ───────────────────────
class ChatInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chat-interface")
        self.setAcceptDrops(True)

        self.images: list[QImage] = []
        self.history: list[dict] = []
        self._busy = False
        self._thread = None
        self._worker = None
        self._currentBubble: MessageBubble | None = None

        v = QVBoxLayout(self)
        v.setContentsMargins(32, 20, 32, 12)
        v.setSpacing(8)
        v.addWidget(SubtitleLabel("多模态对话", self))
        v.addWidget(CaptionLabel("拖入 / Ctrl+V 粘贴图片，输入问题后发送", self))

        self.scrollArea = ChatScrollArea(self)
        v.addWidget(self.scrollArea, 1)

        # 底部输入卡片
        self.inputCard = SimpleCardWidget(self)
        iv = QVBoxLayout(self.inputCard)
        iv.setContentsMargins(12, 10, 12, 10)
        iv.setSpacing(8)

        self.thumbRow = QHBoxLayout()               # [缩略图…] [弹簧] [清空按钮]
        self.clearButton = ToolButton(FluentIcon.DELETE, self.inputCard)
        self.clearButton.setToolTip("清空图片")
        self.clearButton.clicked.connect(self.clearImages)
        self.thumbRow.addStretch(1)
        self.thumbRow.addWidget(self.clearButton)

        inputRow = QHBoxLayout()
        self.inputEdit = PlainTextEdit(self.inputCard)
        self.inputEdit.setPlaceholderText("输入消息…（Ctrl+Enter 发送）")
        self.inputEdit.setFixedHeight(84)
        self.inputEdit.installEventFilter(self)     # 拦截粘贴图片
        self.sendButton = PrimaryPushButton(FluentIcon.SEND, "发送", self.inputCard)
        self.sendButton.clicked.connect(self.onSend)
        inputRow.addWidget(self.inputEdit, 1)
        inputRow.addWidget(self.sendButton, 0, Qt.AlignmentFlag.AlignBottom)

        iv.addLayout(self.thumbRow)
        iv.addLayout(inputRow)
        v.addWidget(self.inputCard)

        # 流式渲染节流
        self._pending = ""
        self._flushTimer = QTimer(self)
        self._flushTimer.setInterval(80)
        self._flushTimer.timeout.connect(self._flushBuffer)

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.onSend)

    # ---------- 图片管理 ----------
    def addImage(self, image: QImage):
        self.images.append(image)
        thumb = ImageLabel(self.inputCard)
        thumb.setImage(image)
        thumb.scaledToHeight(48)
        thumb.setBorderRadius(4, 4, 4, 4)
        self.thumbRow.insertWidget(max(self.thumbRow.count() - 2, 0), thumb)

    def clearImages(self):
        while self.thumbRow.count() > 2:
            item = self.thumbRow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.images.clear()

    @staticmethod
    def toB64(image: QImage) -> str:
        buf = QBuffer()
        buf.open(QBuffer.OpenModeFlag.ReadWrite)
        image.save(buf, "JPEG", 88)
        return base64.b64encode(bytes(buf.data())).decode()

    # ---------- 事件 ----------
    def eventFilter(self, obj, e):
        if obj is self.inputEdit and e.type() == QEvent.Type.KeyPress:
            if e.matches(QKeySequence.StandardKey.Paste):
                md = QApplication.clipboard().mimeData()
                if md.hasImage():
                    img = md.imageData()
                    if isinstance(img, QImage) and not img.isNull():
                        self.addImage(img)
                        return True
        return super().eventFilter(obj, e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in IMAGE_EXTS:
                    img = QImage(str(p))
                    if not img.isNull():
                        self.addImage(img)
        elif md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.addImage(img)
        e.acceptProposedAction()

    # ---------- 发送 ----------
    def onSend(self):
        if self._busy:                              # 忙时点击 = 停止
            if self._worker:
                self._worker.stop()
                InfoBar.info(title="正在取消", content="等待当前请求结束…",
                             parent=self, duration=1500, position=InfoBarPosition.TOP)
            return

        text = self.inputEdit.toPlainText().strip()
        if not text and not self.images:
            return

        # 1) 渲染用户气泡
        bubble = MessageBubble("user")
        for img in self.images:
            bubble.addImage(img)
        bubble.setFullText(text or "（图片）")
        self._addBubble(bubble, right=True)

        # 2) 构建 API 消息（历史瘦身：旧图剔除）
        content = [{"type": "image_url", "image_url": {"url": self.toB64(i)}}
                   for i in self.images]
        content.append({"type": "text", "text": text or "请描述这张图片"})
        self.history.append({"role": "user", "content": content})
        self.history = slim_history(self.history, keep_last=4)

        self.inputEdit.clear()
        self.clearImages()

        # 3) 助手占位气泡 + 启动线程
        self._busy = True
        self.sendButton.setText("停止")
        self._currentBubble = MessageBubble("assistant")
        self._addBubble(self._currentBubble, right=False)

        self._thread = QThread(self)
        self._worker = ChatWorker(cfg.get(cfg.apiKey), cfg.get(cfg.model),
                                  [m.copy() for m in self.history])
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        # 业务槽先连（连接顺序 = 触发顺序）
        self._worker.chunkReceived.connect(self._onChunk)
        self._worker.finished.connect(self._onDone)
        self._worker.cancelled.connect(self._onCancelled)
        self._worker.errorOccurred.connect(self._onError)
        # 清理链后连
        for sig in (self._worker.finished, self._worker.cancelled,
                    self._worker.errorOccurred):
            sig.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _addBubble(self, bubble, right):
        align = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
        self.scrollArea.vBox.insertWidget(self.scrollArea.vBox.count() - 1, bubble, 0, align)
        QTimer.singleShot(0, self.scrollArea.scrollBottom)

    # ---------- 流式回调（主线程执行） ----------
    def _onChunk(self, text):
        self._pending += text
        if not self._flushTimer.isActive():
            self._flushTimer.start()

    def _flushBuffer(self):
        self._flushTimer.stop()
        if self._pending and self._currentBubble:
            self._currentBubble.appendText(self._pending)
            self._pending = ""
        self.scrollArea.scrollBottom()

    def _onDone(self):
        self._flushBuffer()
        if self._currentBubble and self._currentBubble.text().strip():
            self.history.append({"role": "assistant",
                                 "content": self._currentBubble.text()})
        self._finish()

    def _onCancelled(self):
        self._flushBuffer()
        self._finish()

    def _onError(self, msg):
        self._flushBuffer()
        self._finish()
        InfoBar.error(title="请求失败", content=msg,
                      parent=self, duration=5000, position=InfoBarPosition.TOP)

    def _finish(self):
        self._busy = False
        self.sendButton.setText("发送")

    # ---------- 退出 ----------
    def isBusy(self):
        return self._busy

    def stopAll(self):
        if self._worker and self._thread and self._thread.isRunning():
            self._worker.stop()
            self._thread.quit()
            self._thread.wait(3000)

def slim_history(history, keep_last=4):
    out, n = [], len(history)
    for i, m in enumerate(history):
        if isinstance(m["content"], list) and i < n - keep_last:
            text = "".join(c.get("text", "") for c in m["content"]
                           if c.get("type") == "text")
            out.append({"role": m["role"], "content": text or "[图片消息]"})
        else:
            out.append(m)
    return out

# ─────────────────────── API Key 对话框 ───────────────────────
class ApiKeyDialog(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("API Key", self)
        self.edit = LineEdit(self)
        self.edit.setPlaceholderText("粘贴密钥（智谱开放平台）")
        self.edit.setText(cfg.get(cfg.apiKey))
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.edit)
        self.widget.setMinimumWidth(360)
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

    def accept(self):
        cfg.set(cfg.apiKey, self.edit.text().strip())
        cfg.save()
        super().accept()

# ─────────────────────── 设置界面 ───────────────────────
class SettingInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("setting-interface")
        self.enableTransparentBackground()
        self.setWidgetResizable(True)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)
        v.addStretch(1)
        v.addWidget(TitleLabel("设置", self))

        personal = SettingCardGroup("个性化", w)
        themeCard = OptionsSettingCard(
            cfg.themeMode, FluentIcon.BRUSH, "应用主题", "切换浅色 / 深色 / 跟随系统",
            texts=["浅色", "深色", "跟随系统"], parent=personal)
        personal.addSettingCard(themeCard)
        themeCard.optionChanged.connect(lambda: setTheme(cfg.get(cfg.themeMode)))

        model = SettingCardGroup("模型服务", w)
        keyCard = PushSettingCard("配置", FluentIcon.DEVELOPER_TOOLS, "API Key",
                                  "密钥仅保存在本机配置文件", parent=model)
        model.addSettingCard(keyCard)
        keyCard.clicked.connect(lambda: ApiKeyDialog(self).exec())

        v.addWidget(personal)
        v.addWidget(model)
        self.setWidget(w)

# ─────────────────────── 主窗口 ───────────────────────
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多模态工作台")
        self.resize(1080, 720)
        self.setMinimumSize(860, 600)
        if sys.platform == "win32":
            try:
                self.setMicaEffectEnabled(True)     # Win11 Mica 效果
            except Exception:
                pass

        self.chatInterface = ChatInterface(self)
        self.settingInterface = SettingInterface(self)
        self.addSubInterface(self.chatInterface, FluentIcon.CHAT, "智能对话")
        self.addSubInterface(self.settingInterface, FluentIcon.SETTING,
                             "设置", NavigationItemPosition.BOTTOM)

    def closeEvent(self, e):
        if self.chatInterface.isBusy():
            if not MessageBox("提示", "仍有请求进行中，确定退出吗？", self).exec():
                e.ignore()
                return
        self.chatInterface.stopAll()                # 阻止“退出时段错误”
        super().closeEvent(e)

# ─────────────────────── 入口 ───────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    QApplication.setApplicationName("MultimodalStudio")
    setTheme(cfg.get(cfg.themeMode))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
【第七部分：打包发布】
7.1 PyInstaller（推荐 onedir 模式）

pip install pyinstaller

pyinstaller ^
  --noconsole ^
  --name MultimodalStudio ^
  --icon resources/logo.ico ^
  --collect-all qfluentwidgets ^
  --hidden-import PyQt6.QtSvg ^
  --hidden-import PyQt6.QtSvgWidgets ^
  --collect-submodules PyQt6 ^
  main.py
逐参数解释：

参数	作用
--noconsole / -w	无控制台窗口（GUI 程序必加）
--collect-all qfluentwidgets	收集 qfluentwidgets 全部数据资源（图标 SVG 等）
--hidden-import PyQt6.QtSvg	Fluent 图标大量使用 SVG，漏掉 = 图标全空白（最高频打包事故）
--collect-submodules PyQt6	QtMultimedia 等模块动态加载，防止运行时 ImportError
onedir vs onefile：

onedir（推荐）	onefile
启动速度	快	慢（需解压临时目录）
杀软误报	低	高
分发	目录/压缩包	单文件
7.2 打包后必查清单
□ 深色/浅色主题切换正常
□ Fluent 图标全部可见（QtSvg 检查）
□ 拖放/粘贴图片可用
□ 摄像头/麦克风权限（macOS 需 Info.plist 权限声明）
□ 中文路径下可运行（不要依赖 ASCII 假设）
□ 无控制台时异常可见 → 安装全局异常钩子写日志：

import logging, traceback, sys
logging.basicConfig(filename="app.log", level=logging.ERROR,
                    encoding="utf-8")
sys.excepthook = lambda t, v, tb: (logging.critical(
    "".join(traceback.format_exception(t, v, tb))), sys.__excepthook__(t, v, tb))
7.3 Nuitka（性能更优的替代）

pip install nuitka
python -m nuitka --standalone --windows-console-mode=disable \
  --enable-plugin=pyqt6 --include-package=qfluentwidgets \
  --windows-icon-from-ico=resources/logo.ico main.py
7.4 签名与分发
Windows：购买代码签名证书（OV/EV），signtool sign，否则 SmartScreen 拦截；EV 证书可立即消除声誉警告。
macOS：codesign + 公证，否则 Gatekeeper 拦截。
自动更新：自建或用 pyupdater 思路（版本接口 + 下载 + QProcess 重启）。
【第八部分：踩坑清单（30 条）】
#	现象	原因与解决
1	子线程改 UI 后随机崩溃	只能 pyqtSignal 回主线程改
2	界面冻结“未响应”	主线程被网络/sleep 阻塞，移入 Worker
3	Worker 槽不触发	未持有 Worker 引用被 GC，存为实例属性
4	the object name of interface is not set	addSubInterface 的界面没设 objectName
5	AttributeError: 'Qt' 没有属性 AlignCenter	PyQt6 枚举作用域：Qt.AlignmentFlag.AlignCenter
6	exec_ 不存在	PyQt6 用 exec()
7	启动即 QObject 类型不匹配崩溃	PyQt6 与 PySide6 混装了 qfluentwidgets
8	流式输出把旧内容重复	append() 会换行加段落格式，用累积 + setMarkdown 全量刷新
9	长回复越打越卡	每 chunk 全量重渲染，用 QTimer 节流批刷（见 5.4）
10	Windows 读文件 UnicodeDecodeError	open(..., encoding="utf-8") 显式声明
11	not safe to use pixmaps outside GUI thread	子线程传 QImage，主线程转 QPixmap
12	退出时段错误	closeEvent 里 stopAll + wait（见第六部分）
13	Ctrl+V 粘贴截图无效	输入框不处理图片，eventFilter 拦截 clipboard
14	API 报图片超限/费用暴涨	发送前压缩到 2048px JPEG（见 5.2）
15	多轮对话 token 爆炸	历史瘦身，剔除旧图（见 5.3 slim_history）
16	InfoBar 不显示	忘传 parent
17	打包后 Fluent 图标空白	缺 --hidden-import PyQt6.QtSvg
18	打包后资源丢失	加 --collect-all qfluentwidgets
19	无控制台后异常不可见	excepthook + logging 到文件（见 7.2）
20	onefile 被杀软报毒	改 onedir + 代码签名
21	商用闭源被 GPL 约束	购买商业授权或迁移 PySide6 全家桶（见 2.2）
22	全局 setStyleSheet 后 Fluent 组件变丑	禁止全局样式，用作用域选择器 + isDarkTheme 分支
23	界面控件加到了 MainWindow 上不显示	要加到 interface 自身布局
24	ScrollArea 内容不铺开	setWidgetResizable(True)
25	气泡高度跳动	doc.setTextWidth 与控件内宽同步 + 封顶高度
26	高 DPI 下图片模糊	缩放按 devicePixelRatio 计算，或 QImage 直接 setDevicePixelRatio
27	并发请求结果错乱	busy 标志互斥或请求队列串行
28	SDK 客户端跨线程报错	每个线程新建 client，或加锁
29	先于 QApplication 创建 QPixmap 崩溃	任何 GUI 对象都要在 QApplication 之后
30	界面初始化卡启动	重活放 QTimer.singleShot(0, heavy_init) 延迟执行
【第九部分：编码规范】
命名：界面类 XxxInterface；Worker 类 XxxWorker；信号名用过去式（chunkReceived 而非 onChunk）；槽函数 _onXxx 私有。
每个 Interface 固定模板：__init__ → setObjectName → 建布局 → 建控件 → 连信号 → installEventFilter。
Worker 固定模板：四信号起步（finished / errorOccurred + 业务信号 + 可选 cancelled）；必须实现 stop()；run() 全体 try/except。
线程连接固定顺序：业务槽在前，thread.quit 清理链在后。
禁止事项：主线程网络 IO；跨线程 UI 操作；全局样式表；无 encoding 的 open；裸 print 打包发布版。
代码评审四问：耗时操作在哪个线程？Worker 谁持有引用？退出时线程如何停止？异常如何上报给用户？
【第十部分：FAQ 速答】
Q1：怎么在导航外再开一个独立窗口？
ImageWindow(FramelessWindow) + setTitleBar(StandardTitleBar(self))，模态需求改 MessageBoxBase。

Q2：如何显示 GIF？ 原生 QLabel + QMovie（qfluentwidgets 无专门组件）：movie = QMovie(path); label.setMovie(movie); movie.start()。

Q3：如何嵌入网页/富 HTML？ pip install PyQt6-WebEngine，QWebEngineView.setHtml()。

Q4：如何画图表？ pyqtgraph（qfluentwidgets full 版已含）或 QtCharts。

Q5：如何做系统托盘？ QSystemTrayIcon + RoundMenu 组合，托盘菜单用 qfluentwidgets 风格。

Q6：如何实现全局快捷键？ GUI 内用 QShortcut；系统级（窗口失焦也生效）用第三方 keyboard 库。

Q7：多语言？ QTranslator + .ts/.qm，或轻量方案：cfg 存语言项 + 自维护字符串表。

Q8：启动页？ QSplashScreen 在 app.exec() 前 show，主窗口 show() 后 finish(w)。

Q9：如何让应用开机自启？ Windows 写注册表 Run 键（QSettings('HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', QSettings.Format.NativeFormat)）。

Q10：模型选哪个？ 图文理解入门用 glm-4v-flash（免费额度大），重推理用 glm-4v-plus；检索向量化用 CLIP 系；具体以官方价格页为准并做 A/B 评估。

【第十一部分：学习资源】
资源	地址/说明
PyQt-Fluent-Widgets 仓库	github.com/zhiyiYo/PyQt-Fluent-Widgets（examples/gallery 是最佳学习源，本文档所有 API 惯例与其一致）
官方文档	qfluentwidgets.com（中文）/ pyqt-fluent-widgets.readthedocs.io
Qt 6 官方文档	doc.qt.io（PyQt6 API 与之一一对应）
PyQt6 参考手册	riverbankcomputing.com/static/Docs/PyQt6/
维护提示：qfluentwidgets 迭代速度快，新增组件（Flyout、HeaderCardWidget 等）不断出现。使用本知识库时若遇 API 不匹配，以「已安装版本的 gallery 源码」为最终裁决依据。