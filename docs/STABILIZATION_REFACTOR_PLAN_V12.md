# DanceMirror 稳定性与重构方案 V12

> 触发背景：一次「接入 BlazePose 真 3D」的契约改动，在 30 分钟内连续引爆 3 个运行时故障（摄像头卡死 / JS 每帧抛异常 / 控件被裁）。
> 106 个单测全绿，应用却是坏的。本文件回答两件事：**为什么会这样**，以及**怎么一次性解决**。

---

## 一、结论（TL;DR）

项目不是"越写越烂"，而是**架构上缺少三类护栏**，导致任何一处改动都可能以运行时崩溃的形式暴露：

1. **没有接缝测试** —— 106 个测试只覆盖纯函数；`worker → Qt → JS` 这条真实数据链**零覆盖**。
2. **同一套管线写了两遍**（`workers/imitation.py` 与 `workers/live.py`）—— 改一处必漏一处，本轮就是铁证。
3. **跨语言契约靠"双方心里有数"** —— Python 序列化 dict ↔ JS 读取，无 schema、无版本、无双向校验。

修法不是"重写"，而是**补护栏 + 消除重复**，分 6 个阶段增量落地，每阶段都有验收门禁。

---

## 二、本轮故障复盘（证据链）

| # | 现象 | 直接原因 | 为什么测试没拦住 | 系统性根因 |
|---|---|---|---|---|
| 1 | 启动摄像头卡死 | `imitation._build_preview` 把 `PoseEstimate` 当 `PoseFrame` 传进 `build_camera_preview`（第 2 个**位置参数**漏改） | 无 worker 级测试 | 契约变更靠人工核对；`live.py` 同款代码改对了、`imitation.py` 漏了 |
| 2 | JS 每帧 `source.slice is not a function` | Python `skeleton_payload` 把 hands 序列化成**索引对象**，JS 期望**数组** | 无 Python↔JS 契约测试 | 跨语言契约隐式、无 schema |
| 3 | 卡片复选框显示不全 | `setFixedWidth(38)` 硬压 Fluent CheckBox（自然宽 57px） | 无布局体检测试 | UI 用魔法数字而非 sizeHint |
| 4 | `QFont::setPointSize -1` 警告 | 主题 QSS 用 `font-size: 34px` → Qt 字体 `pointSize()==-1` | ——（警告） | px/pt 混用 |

> 故障 1 与 2 的共同点：**都不是逻辑错误，而是"接缝"错误**。逻辑单测永远抓不到接缝。

---

## 三、重构方案（分阶段 · 可增量 · 每阶段独立验收）

### P0 · 接缝止血（0.5 天）— 最先做
| 动作 | 说明 |
|---|---|
| 固化单帧链路测试 | 把本轮临时验证脚本升级为正式测试 `tests/test_worker_frame_pipeline.py`：**无摄像头**跑完整一帧 `readiness → normalize → retarget → smooth → hand-ROI → preview`，并断言 mirror 几何卫生（`left_shoulder.x > 0`） |
| payload 双向契约测试 | Python 断言 hands 是 21 长度数组（已加 `tests/test_three_scene.py`）；Node 用同一份 JSON 断言 `Array.isArray` + `.slice` 可用（本轮已验证的模式） |
| JS 入口防御 | `mapHandPoints` 已改为"数组/旧对象"双兼容；`updateRobot` 增加顶层 try/catch，单帧异常不得中断渲染循环 |
| 把 `mypy` 纳入 `scripts/verify.ps1` | `pyproject.toml` 已配 `strict`；让"漏改位置参数"这类错误在提交期暴露，而不是运行期 |

**验收**：故意回退任一修复 → 新测试必须变红。

### P1 · 消除双份管线（1–2 天）— 收益最大
现状：`imitation.py` 与 `live.py` 各自实现了一遍
`normalize_frame → retarget_frame → build_camera_preview → hands_by_side`。

抽取：
```
motion/frame_pipeline.py
    @dataclass FrameResult: skeleton, preview, readiness, hands, ...
    class LiveFramePipeline:
        def process(frame_bgr, *, mirror, person_count, hands_interval) -> FrameResult
```
- `live.py` 只保留差异：评分 / 同步 / 参考帧。
- `imitation.py` 只保留差异：safe-hold / scope / smoothing。

**验收**：两个 worker 中不再直接出现 `normalize_frame` / `retarget_frame` / `build_camera_preview`；行为等价（106 测试 + P0 新测试）。

### P2 · payload schema 单一真源（1–2 天）
```
renderer/payload.py
    @dataclass RobotFramePayload:  # 唯一真源，含 payload_version
        joints, scores, edges, hands, timestamp_s, frame_index
        def to_browser(self) -> dict
```
- JS `updateRobot` 首行校验 `payload_version`：不匹配 → 打日志 + 降级，**不崩**。
- 同一份 golden JSON 同时驱动 Python 与 Node 断言。

**验收**：任何 schema 改动都会**同时**让两侧测试失败。

### P3 · 拆 `main_window.py` 上帝对象（2–3 天）
现状 ≈ 2200 行 / 130+ 方法，同时管：界面装配、会话状态机、Worker 生命周期、音乐、设置、云端。

拆分：
- `session_controller.py`：`PREFLIGHT → CAMERA_WARMUP → COUNTDOWN → PLAYING → FINALIZING` 状态机（纯逻辑，可单测）。
- `worker_manager.py`：收敛 `_track_controller` / `_stop_controller_async` / registry。
- `settings_controller.py`：与 `SettingsStore` 对接。
- `main_window.py` 只做"装配 + 信号转发"。

**验收**：`main_window.py` ≤ 800 行；会话状态机有独立纯单测（不依赖 UI）。

### P4 · UI 令牌与布局稳健化（1 天）
- QSS 字号 `px → pt`：消除 `pointSize=-1` 警告，且 HiDPI 下更正确（96 DPI 下视觉尺寸几乎不变）。
- 移除 Fluent 控件上的 `setFixedWidth/Height` 魔法数字 → `setMinimumWidth(sizeHint)` / 布局策略。**（复选框已按此修）**
- 新增"布局体检"测试：构造关键卡片，断言 `widget.width() >= widget.minimumSizeHint().width()`。
- 用 `qInstallMessageHandler` 断言关键流程 **0 条 Qt 警告**。

**验收**：截图对比无回归；字体警告归零。

### P5 · 测试金字塔补齐（持续）
- 接缝测试：`worker→Qt→JS` 每类至少 1 条。
- UI 冒烟：关键路径 `QTest` 点击（已有无头启动冒烟作基础）。
- 覆盖率门禁：`pytest-cov` 已在环境中，纳入 `verify.ps1`。

**验收**：覆盖率不再只统计纯函数层；UI/worker 层有非零覆盖。

---

## 四、建议执行顺序与取舍

| 优先级 | 阶段 | 理由 |
|---|---|---|
| 立刻 | P0 | 成本最低、直接防止"改 A 崩 B"再次发生 |
| 其次 | P1 | 消除本轮"改一处漏一处"的**结构性质因** |
| 然后 | P2 | 让跨语言契约可被机器校验 |
| 可排期 | P3 | 上帝对象不改也能跑，但会持续放大维护成本 |
| 顺手 | P4 | 纯 UI 稳健化，无功能风险 |
| 长期 | P5 | 与 P1/P3 同步推进 |

**明确不做**（避免过度工程）：
- 不推倒重写（现架构分层是对的：`domain → motion/pose → workers → view`）。
- 不为凑覆盖率写无意义测试。
- 不在无真实显示器的机器上盲改 3D JS 的骨骼驱动（D4 根节点转向 / D5 脚掌锁骨）——风险大于收益。

---

## 五、本轮已落地的修复（对照）

| 修复 | 文件 | 验证 |
|---|---|---|
| D1 镜像是真反射（换标签 **+ 翻 x**） | `motion/normalization.py` | 数值断言 + 回归测试 |
| D2 模仿路径保留手部数据 | `workers/imitation.py` | 回归测试 |
| D3 BlazePose 真 3D（真实米制深度） | `pose3d/blaze_pose.py`（新）| 探针 + 21.4ms 实测 |
| 崩溃：`PoseEstimate` 位置参数漏改 | `workers/imitation.py` | 单帧链路仿真 |
| hands 序列化对象→数组 + JS 双兼容 | `renderer/three_scene.py` | Node 断言 `slice` 不再抛 |
| 复选框被裁（38px→57px） | `view/library_interface.py` | 布局探针 `clipped_by=0` |
| 窗口图标缺失 | `view/branding.py`（新）+ `app.py` | 7 档尺寸校验 |
| 回归测试补强 | `tests/{test_blaze_pose,test_worker_preview_contract,test_three_scene,test_motion}.py` | 106 用例全绿 |

---

## 六、待确认项

1. **"窗口闪一下"**：现有日志最后一条即为 `23:42:26` 的 worker 崩溃，其后**无新运行记录** → 极可能就是你看到的那次。请用已修版本重启验证；若仍闪，请把新日志给我。
2. **`QFont::setPointSize -1`**：无害警告，根因是 QSS 用 `px` 字号。建议按 P4 改 `pt`（视觉尺寸基本不变）。
3. **3D 保真**：D4（根节点转向跟随）与 D5（脚掌/锁骨驱动）需要真实显示器边看边调，暂缓。
