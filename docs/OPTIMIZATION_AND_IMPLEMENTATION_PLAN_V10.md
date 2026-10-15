# DanceMirror 跨视角评分、音画同步与企业级实施契约 V10

状态：实施基线，包含纵向切片与验收门槛  
日期：2026-09-21  
目标设备：RTX 3060 Laptop 6GB，兼容更低端 Windows 设备  
目标环境：Conda `pytorch_cuda_env`  
最终交互基线：`docs/ULTIMATE_3D_INTERACTION_PLAN_V9.md`

---

## 0. 结论先行

V2 到 V9 已解决“项目要做成什么”，V10 解决“先做什么、按什么契约做、如何证明没有踩雷”。

V10 不推翻 V9，只收紧五条底层契约：

1. 参考视频和用户摄像头可以来自不同机位，评分不能直接比较原始二维坐标。
2. 视频转换出的动作包必须标明 3D 质量等级，低质量动作可以驱动角色，但必须降低评分证据权重。
3. WebEngine 渲染不能每帧直接调用 `runJavaScript()`，必须只保留最新帧、合并命令、超时丢帧。
4. 音乐是训练页主时钟；姿态评分、骨架颜色、语音提示必须使用同一修正后的动作时间。
5. 宿舍和低端设备默认关闭根运动，避免二维深度噪声导致机器人漂移、转身或冲出舞台。

这五条先以纯逻辑、可测试模块落地，再接入现有 UI，避免把高风险功能一次性塞进主窗口。

---

## 1. 当前风险复盘

| 风险 | 当前实现 | 后果 | V10 处理 |
|---|---|---|---|
| 跨视角误判 | 直接比较身体局部二维特征 | 侧面视频和正面摄像头会产生虚假低分 | `CameraProfile` + `ComparisonFeatureSpace` |
| 3D 质量不可见 | 基线深度和真实 3D 都只表现成同一骨架 | 用户误以为动作包是精确 3D | `MotionQualityLevel` |
| WebEngine 命令堆积 | 每帧直接 `page().runJavaScript()` | 渲染慢时主线程排队、界面卡顿 | `LatestFrameRenderBridge` |
| 音画时基不一致 | 摄像头时间直接匹配参考视频时间 | TTS、评分和画面错拍 | `SyncController` |
| 根运动噪声 | 骨架原点固定，后续可能直接采用深度位移 | 角色漂移、转身、出画 | `RootMotionMode.NONE` 默认策略 |
| 用户 3D 回流 | 旧文档仍提到用户角色和双舞台 | 可能重新引入 6GB 显存无法承受的路径 | `RepresentationPolicy` 硬约束 |
| 低置信度乱扣分 | 部分特征缺失时可能拉低总分 | 用户站位和遮挡被误认为舞蹈错误 | 证据缩放 + 最低覆盖率 |

---

## 2. P0-1：跨视角评分契约

### 2.1 核心思想

不同机位看到的是同一个动作在不同投影空间中的表现。以下量通常可以跨视角比较：

- 关节夹角：肘角、膝角。
- 骨骼比例和左右语义。
- 手腕、脚踝相对身体的高度变化。
- 动作速度、节拍相位、躯干稳定度。

以下量强依赖机位：

- 手腕横向偏移。
- 髋部横向偏移。
- 躯干在图像 x 轴上的倾斜。
- 二维深度变化。
- 左右方向在正面与背面之间的视觉解释。

因此不能只有一套固定容差，必须根据两端机位生成特征空间。

### 2.2 `CameraProfile`

```text
CameraProfile
  view: FRONT | BACK | LEFT_PROFILE | RIGHT_PROFILE | THREE_QUARTER | UNKNOWN
  semantic_alignment: ALIGNED | MIRRORED | UNKNOWN
  upright: bool
  perspective_confidence: 0.0..1.0
```

规则：

- `ALIGNED`：参考和用户的左右关节语义一致。
- `MIRRORED`：比较前交换实际动作的左右特征，不能只交换显示。
- `UNKNOWN`：降低左右相关特征权重，并在动作包中标记“方向语义未确认”。
- `upright=False`：手腕高度和脚高度的权重显著下降。
- `perspective_confidence` 同时影响横向特征和证据强度。

### 2.3 `ComparisonFeatureSpace`

输出内容：

```text
ComparisonFeatureSpace
  weights: feature -> multiplier
  actual_feature_map: compare_feature -> actual_feature
  evidence_scale: 0.0..1.0
  reasons: string[]
```

建议初始权重：

| 特征组 | 同机位 | 正面与三分之四 | 正面与侧面 | 左右侧面相反 | 未知机位 |
|---|---:|---:|---:|---:|---:|
| 肘角、膝角 | 1.00 | 1.00 | 1.00 | 1.00 | 0.85 |
| 手腕/脚高度 | 1.00 | 0.95 | 0.90 | 0.85 | 0.80 |
| 手腕横向 | 1.00 | 0.55 | 0.12 | 0.15 | 0.45 |
| 髋部横向 | 1.00 | 0.50 | 0.10 | 0.12 | 0.40 |
| 躯干倾斜 | 1.00 | 0.55 | 0.12 | 0.15 | 0.45 |

`evidence_scale` 建议：

- 双方机位明确且兼容：`1.00`
- 一端未知：`0.85`
- 双方未知：`0.72`
- 动作包质量低于 `HYBRID_3D`：再乘以动作包质量系数

### 2.4 评分公式

对每个可用特征：

```text
effective_confidence =
    min(reference_confidence, actual_confidence)
    * evidence_scale

error_ratio = abs(actual - reference) / tolerance
feature_score = 100 * exp(-0.5 * min(error_ratio, 3)^2)

weighted_score =
    sum(feature_score * base_weight * space_weight * effective_confidence)
    / sum(base_weight * space_weight * effective_confidence)
```

当没有足够证据时不扣分，返回 `overall=0` 并在 UI 标记“证据不足”，而不是显示“动作错误”。

---

## 3. P0-2：视频转 3D 质量等级

### 3.1 等级定义

| 等级 | 含义 | 评分证据系数 | 动作幅度上限 | 典型来源 |
|---|---|---:|---:|---|
| `RELATIVE_3D` | 相对 2.5D，深度只用于可读性 | 0.65 | 0.80 | 单目视频 + 基线提升 |
| `HYBRID_3D` | 有实际 3D 提升器输出，仍无标定 | 0.85 | 0.95 | VideoPose3D、MMPose、GVHMR 等 |
| `VERIFIED_3D` | 有标定、多视角或动捕校验 | 1.00 | 1.00 | 多机位标定、专业动捕、已校验数据 |

### 3.2 动作包元数据

```json
{
  "quality": {
    "level": "HYBRID_3D",
    "score_confidence": 0.85,
    "motion_scale": 0.95,
    "valid_frame_ratio": 0.93,
    "depth_activity": 0.071,
    "reasons": ["learned_lifter", "depth_activity_sufficient"]
  },
  "camera_profile": {
    "view": "FRONT",
    "semantic_alignment": "ALIGNED",
    "upright": true,
    "perspective_confidence": 0.8
  }
}
```

### 3.3 使用规则

- `RELATIVE_3D` 仍可驱动机器人，保证项目可用。
- 评分权重不能与 `VERIFIED_3D` 相同。
- 大动作需要限制幅度时，先缩放机器人动作，不改用户评分尺度。
- UI 必须显示等级，例如“动作包：相对 3D（可训练，评分置信度 65%）”。
- 不得把基线深度伪称为“精确 3D 重建”。

---

## 4. P0-3：WebEngine 渲染桥

### 4.1 问题

`QWebEngineView` 的 `runJavaScript()` 不是免费操作。如果 YOLO、摄像头、UI 和 WebEngine 同时高负载，逐帧调用会让主线程堆积命令，表现为界面卡顿、骨架延迟和退出时崩溃。

### 4.2 `LatestFrameRenderBridge`

职责：

- 每个命令通道只保留最新值。
- 参考动作、用户动作、状态文本可以合并成一个脚本批次。
- 默认最多 60 次刷新/秒，低端模式可降到 30 次/秒。
- 待发送命令超过最大寿命后直接丢弃。
- WebEngine 尚未加载完成时保存最后状态，加载完成后只发送最新状态。
- 发生异常时记录统计并丢弃当前批次，不阻塞摄像头线程。

```text
LatestFrameRenderBridge
  submit(channel, script) -> accepted
  flush(force=False) -> dispatched_count
  stats -> submitted/coalesced/dropped/batches
```

### 4.3 合并策略

| 通道 | 保留策略 |
|---|---|
| `reference` | 只保留最新参考姿态 |
| `user` | 只保留最新用户姿态或 `clearUser` |
| `mode` | 只保留最新显示模式 |
| `status` | 只保留最新状态文本 |
| `command` | 只保留最新短命令 |

### 4.4 回退

如果 WebEngine 不可用：

- 继续使用原生骨架预览。
- 不允许因渲染桥失败阻断训练、评分和 TTS。
- 摄像头左上角叠加层必须经过 Windows WebEngine 层级测试；失败时回退为独立停靠面板。

---

## 5. P0-4：音画同步控制器

### 5.1 主时钟原则

训练页以音乐时间为主时钟。动作、评分、骨架高亮、语音提示、下一拍轨迹都从同一个音乐时间派生。

```text
pose_effective_time =
    music_time_now
    - max(0, now - capture_timestamp)
    - capture_to_pose_latency
    - user_offset

delay = clamp(
    max(0, now - capture_timestamp) + capture_to_pose_latency + user_offset,
    0,
    0.3s
)
```

在音乐尚未启动时，使用会话捕获时间作为后备时间轴。

### 5.2 平滑与钳制

- 延迟限制在 `0..300 ms`。
- 捕获到姿态延迟使用指数移动平均，默认 `alpha=0.2`。
- 用户手动偏移限制在 `-300..300 ms`；实际延迟仍不低于 0。
- 单帧异常延迟超过 1 秒时视为掉帧，不进入平滑窗口。
- 同步丢失时不使用错误时间戳评分，直接标记该帧无效。

### 5.3 输出

```text
SyncSnapshot
  pose_effective_time_s
  applied_delay_s
  raw_latency_s
  smoothed_latency_s
  confidence
```

UI 只显示经过钳制后的延迟，不显示内部原始值。

---

## 6. P0-5：根运动策略

### 6.1 模式

| 模式 | 行为 | 默认场景 |
|---|---|---|
| `NONE` | 根节点固定在舞台原点，只保留身体局部动作 | 宿舍、低端设备、比赛演示 |
| `SWAY` | 只允许小幅度横向摆动，不允许位移 | 中端设备、轻量舞台效果 |
| `PLANAR` | 允许 x/y 平移，仍需边界钳制 | 有可信 3D 根轨迹时 |

### 6.2 安全规则

- 默认必须是 `NONE`。
- 单目基线深度不得自动升级为 `PLANAR`。
- `PLANAR` 必须同时满足：质量等级至少 `HYBRID_3D`、根轨迹置信度足够、位移边界有效。
- 切换动作包、切角色、暂停恢复时必须重置根运动状态。
- 根运动不得改变评分使用的身体局部坐标。

---

## 7. P0-6：人物表示硬约束

`RepresentationPolicy` 必须在代码层拒绝以下请求：

- 学习舞蹈页创建用户 3D 角色。
- 机器人指挥中心创建用户 3D 角色。
- 用 SMPL、人体网格或用户 3D 舞台替代摄像头二维骨架。
- 同时创建两个大画面 3D 角色。

最终表示：

```text
学习舞蹈页
  大画面 -> 视频动作包驱动的 3D 机器人
  左上角 -> 用户 2D 骨架
  评分 -> 用户 2D 特征 + 视频动作包特征

机器人指挥中心
  大画面 -> 实时重定向的 3D 机器人
  左上角 -> 用户 2D 骨架
  控制 -> 语言、手势、动作状态机
```

---

## 8. 纵向实施切片

### Slice 1：纯逻辑契约

交付：

- `CameraProfile`
- `ComparisonFeatureSpace`
- `MotionQualityLevel`
- `SyncController`
- `LatestFrameRenderBridge`
- `RepresentationPolicy`
- `RootMotionMode`
- 对应 pytest

不交付：

- 全量页面重写。
- GLB/VRM 下载器。
- 语音大模型接入。
- 异步 MP4 编码。

验收：

- 跨视角横向差异不会导致虚假低分。
- 低置信度证据不足不扣分。
- 延迟钳制和平滑边界正确。
- 渲染桥只保留最新帧并合并命令。
- 表示策略拒绝用户 3D。
- 根运动默认 `NONE`。

### Slice 2：现有页面接入

交付：

- `SceneWidget` 接入渲染桥。
- 动作包显示质量等级。
- 实时训练接入同步控制器和相机配置。
- 设置页增加相机视角、用户偏移和根运动模式。
- V9 公共工作区外壳草图。

验收：

- 现有训练流程不回归。
- WebEngine 冒烟测试通过。
- 主线程不再逐帧堆积 JavaScript。
- 用户可在配置中修改视角和延迟。

### Slice 3：单机器人舞台

交付：

- 米制舞台。
- 机器人 GLB/VRM 运行时。
- Humanoid 骨骼映射。
- 机器人骨架层始终可见。
- 左上限位摄像头二维骨架。

### Slice 4：学习舞蹈游戏化

交付：

- 动作包卡片页。
- 海报、重命名、删除、选择。
- 3、2、1 倒计时和 OK 手势启动。
- 音乐、速度、暂停、完成度、评分。
- 下一拍关键部位轨迹提示。

### Slice 5：机器人指挥中心

交付：

- 语言命令解析。
- 手势和动作状态机。
- 实时模仿。
- 皮肤切换。
- 安全保持和紧急停止。

---

## 9. 模块落点

```text
src/dance_mirror/domain/
  quality.py                 # 3D 质量等级与动作包评估
  representation.py          # 表示策略、根运动模式、角色能力矩阵

src/dance_mirror/motion/
  comparison_space.py        # 机位、左右语义、跨视角特征空间
  comparison.py              # 接入 feature space，保持旧接口兼容
  sync.py                    # 音乐主时钟与姿态有效时间

src/dance_mirror/renderer/
  render_bridge.py           # 最新帧渲染桥

src/dance_mirror/view/
  scene_widget.py            # 桥接 QTimer 与 QWebEngineView
  settings_interface.py      # 相机视角、用户偏移、根运动配置

tests/
  test_comparison_space.py
  test_quality.py
  test_sync.py
  test_render_bridge.py
  test_representation.py
```

---

## 10. 配置键

| 键 | 默认值 | 范围 | 说明 |
|---|---:|---:|---|
| `camera/reference_view` | `front` | 枚举 | 参考视频机位 |
| `camera/user_view` | `front` | 枚举 | 用户摄像头机位 |
| `training/user_offset_ms` | `0` | `0..300` | 用户动作手动补偿 |
| `training/capture_latency_alpha` | `0.2` | `0.05..0.8` | 延迟平滑系数 |
| `renderer/target_fps` | `60` | `30..60` | 渲染桥刷新上限 |
| `renderer/pending_timeout_ms` | `300` | `100..1000` | 命令最大寿命 |
| `motion/root_mode` | `none` | 枚举 | 根运动策略 |

配置层只保存非敏感项；API Key 仍仅保存在内存。

---

## 11. 测试门槛

### 11.1 跨视角

- 正面参考与侧面用户的肘角、膝角相同，横向特征差异大时，分数仍高于 85。
- 左右语义镜像时，比较层交换实际特征，而不是交换显示。
- 低置信度帧的覆盖率不足时返回证据不足，不返回 0 分错误提示。

### 11.2 质量等级

- 基线深度序列默认是 `RELATIVE_3D`。
- 明确标定且证据充分时可升级到 `VERIFIED_3D`。
- 低质量动作包不能被 UI 或评分层宣称精确 3D。

### 11.3 同步

- 延迟钳制在 `0..300 ms`。
- 平滑后延迟不会因单帧尖峰剧烈跳动。
- 掉帧帧不进入平滑。
- 音乐时间减去处理延迟后用于最近参考帧选择。

### 11.4 渲染桥

- 同通道连续提交只保留最新脚本。
- 多通道在同一刷新窗口只产生一个批次。
- 超时命令被丢弃。
- 调度异常不向主循环抛出未处理异常。

### 11.5 表示与根运动

- 学习舞蹈和指挥中心都拒绝用户 3D。
- 默认根运动模式为 `NONE`。
- `NONE` 不改变身体局部动作。
- `SWAY` 只产生受限横向位移。
- `PLANAR` 在质量不足时被拒绝。

---

## 12. 性能预算

| 项目 | 目标 |
|---|---:|
| YOLO Pose | 12 到 18 FPS |
| 3D 渲染 | 30 到 60 FPS |
| 渲染桥刷新 | 30 到 60 次/秒 |
| 捕获到姿态 | 小于 150 ms，P95 小于 220 ms |
| 姿态到评分 | 小于 40 ms |
| 音画偏移 | 小于 120 ms |
| VRAM 峰值 | 小于 5.2 GB |
| VRAM 安全余量 | 大于 0.8 GB |
| 主线程阻塞 | 单次小于 16 ms |

---

## 13. 线程与状态规则

- 摄像头、YOLO、评分、TTS、网络和文件哈希不在主线程运行。
- 子线程只发送纯数据对象，不创建或修改 `QWidget`、`QPixmap`、`QWebEngineView`。
- `SceneWidget` 只接收桥接命令，不直接持有 Worker。
- 同步控制器由实时 Worker 拥有，UI 只显示快照。
- 动作包切换、工作区切换和停止时必须清空渲染桥、同步状态和根运动状态。
- 同一时间只允许一个工作区占用摄像头、YOLO 和主 WebGL 场景。

---

## 14. 降级顺序

1. 降低渲染桥刷新到 30 FPS。
2. 关闭轨迹提示和残影。
3. 降低材质和阴影。
4. 降低摄像头小窗分辨率。
5. 降低 YOLO 频率。
6. 关闭 3D 身体，只保留机器人骨架和用户二维骨架。
7. 暂停评分但保留动作回放。
8. 进入安全保持。

骨架显示优先于模型细节保留。

---

## 15. 实施状态

- [x] V10 实施契约
- [x] 跨视角特征空间
- [x] 动作包质量等级
- [x] 音乐主时钟同步控制器
- [x] 最新帧渲染桥
- [x] 人物表示策略
- [x] 根运动默认关闭
- [x] 纯逻辑测试
- [x] SceneWidget 接入与 WebEngine 冒烟回归
- [x] 实时 Worker 接入视角、同步和质量降级
- [x] 设置页相机视角、延迟、根运动和模型配置
- [x] 单机器人 3D 舞台与始终可见骨架
- [x] 学习舞蹈游戏化页面与卡片包库
- [x] 机器人指挥中心、实时模仿和本地优先语言控制
- [x] 授权本地 GLB 导入与低功耗降级
- [x] 云端结构化命令规划与本地白名单二次校验

---

## 16. 最终原则

```text
先契约，后界面。
先证据，后评分。
先同步，后反馈。
先骨架，后材质。
先单机器人，后生态。
先稳定运行，后增加效果。
```

V10 的成功标准不是“功能列表更长”，而是：项目能在 6GB 显存设备上稳定运行，评分对机位差异有解释力，音画不漂移，渲染不堵塞，并且不会重新引入用户 3D 重建这一高风险路径。
