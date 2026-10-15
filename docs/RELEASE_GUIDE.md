# DanceMirror 发布与比赛交付指南

本文档面向比赛提交、演示机和内部验收，不把源码目录直接当作发布包。发布流程必须先通过自动检查和目标机器实测，任何云端能力都不能成为本地训练链路的硬依赖。

## 1. 发布边界

发布包只包含以下内容：

- `src/dance_mirror/` 应用代码。
- 本地 Three.js、GLTFLoader 和经确认可再分发的机器人资源。
- Python 依赖清单、环境说明、第三方许可和发布检查脚本。
- 用户需要自行确认授权的视频、音乐、VRM 或 GLB 不随安装包分发。

发布包不得包含：

- API Key、访问令牌、Cookie、浏览器凭据或 QSettings 密码字段。
- 用户训练录像、截图、SQLite 历史数据库和日志。
- 未取得授权的参考视频、视频原声、明星肖像、蜘蛛侠、奥特曼或其他受保护 IP 模型。
- 没有通过许可审计的模型权重和测试数据集。

## 2. 发布前依赖检查

目标环境固定为：

```text
C:\Users\Administrator\.conda\envs\pytorch_cuda_env
```

运行：

```powershell
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe' -m dance_mirror.cli doctor
```

至少确认：

- Python 解释器和虚拟环境路径正确。
- `torch.cuda.is_available()` 为 `True`。
- GPU 为 NVIDIA GeForce RTX 3060 Laptop，显存约为 6GB。
- YOLO Pose、PyQt6、WebEngine、MediaPipe 和音频输入依赖均来自目标环境。
- `yolo11n-pose.pt` 存在且 SHA-256 与安装脚本记录一致。

## 3. 自动发布门禁

从项目根目录运行：

```powershell
.\scripts\release_check.ps1
.\scripts\verify.ps1
```

`release_check.ps1` 会检查必需文件、扫描明显密钥泄漏并运行环境诊断。`verify.ps1` 还会执行编译、Ruff、pytest 和 WebEngine 3D 冒烟测试。

发布门禁必须满足：

- 自动测试全部通过。
- 静态检查通过。
- WebEngine 场景可加载，机器人模型、骨架、手掌和深色主题状态正确。
- 3D 状态中只有一个画布、一个角色和一个机器人根节点。
- 连续低帧率时性能自动降级，不阻塞 UI 线程。

## 4. 目标机器手工验收

自动测试通过后，仍须在真实比赛机器上完成：

1. 断网启动，确认主界面和 3D 舞台不依赖 CDN。
2. 使用授权舞蹈视频完成一次视频转舞蹈包。
3. 检查舞蹈包卡片、海报、原声、搜索、筛选、重命名和删除。
4. 打开独立训练窗口，确认关闭窗口后摄像头、音乐、计时器和 Worker 全部释放。
5. 确认大画面只有一个 3D 机器人，左上角只显示二维骨架、人脸和手掌。
6. 在 720p 下连续训练 10 分钟，记录 GPU 显存、推理 FPS 和渲染 FPS。
7. 关闭网络后测试 LLM、ASR 和 TTS 失败，确认本地评分、音乐、TTS 回退和历史记录不受影响。
8. 检查 F11、全屏启动、摄像头下拉框、深色主题和浅色主题。
9. 检查日志中没有 API Key、原始音频、连续视频帧或个人信息。
10. 在另一台同规格机器上复现启动和依赖安装流程。

## 5. 资源与许可证清单

发布前逐项确认：

| 类别 | 需要记录 | 当前处理 |
|---|---|---|
| Python 依赖 | 名称、版本、许可证、分发方式 | 见 `ASSET_LICENSES.md` 与 `pyproject.toml` |
| Three.js | 版本、MIT、来源 | 已本地化并记录 |
| 默认角色 | 作者、来源、CC0 1.0、校验值 | 已随项目提供 `dance_robot_cyber.glb` |
| 下载角色 | 来源、CC BY、用户按需缓存 | 不直接随包分发 |
| 参考视频 | 用户授权、公开演示范围 | 不随包分发 |
| 视频原声 | 音乐授权、是否允许再分发 | 只保存在用户本地舞蹈包 |
| 用户导入 GLB | 用户授权、本地使用范围 | 仅本地应用，不再分发 |
| YOLO/Ultralytics | 版本、AGPL/商业许可策略 | 发布前必须单独审计 |

Ultralytics、PyQt6、PyQt6-Fluent-Widgets、MediaPipe、FFmpeg 和其他依赖都有各自的许可证要求。比赛或商业发布前不能只检查代码，还要检查实际分发的二进制、权重和媒体资源。

## 6. 云端密钥策略

- 用户在设置页输入的 API Key 只保存在当前进程内存。
- 不把密钥写入 `QSettings`、SQLite、舞蹈包、日志、崩溃报告或 HTML 报告。
- 不在比赛演示视频、截图、屏幕录制和提交材料中展示密钥。
- 摄像头画面不发送给云端；云端只接收结构化评分、部位统计和用户主动输入的文本。
- 任何云服务失败都必须回退本地评分、本地提示和本地历史保存。

## 7. 打包建议

本项目当前以 Conda 环境和 PowerShell 脚本作为可复现交付基线。需要生成 Windows 安装包时，建议在干净的 `pytorch_cuda_env` 副本上执行，不要直接把开发目录压缩成安装包。

打包前应：

- 固定 Python、PyTorch、Ultralytics、PyQt6 和 WebEngine 版本。
- 将 Three.js、GLTFLoader、默认机器人和许可文件列入 PyInstaller `datas`。
- 排除 `__pycache__`、测试缓存、日志、训练录像和用户数据。
- 单独决定是否分发 YOLO 权重；若分发，先完成 Ultralytics 许可审计。
- 安装包首次启动后在用户数据目录创建数据库、动作包目录和日志目录，而不是尝试写入只读安装目录。

本项目尚未把 PyInstaller 安装包作为默认发布产物；在完成目标机器打包复现前，应使用源码环境加启动脚本交付。

## 8. 失败处理

发布检查失败时按以下顺序处理：

1. 缺失文件：从源码仓库补齐，不能用手工复制的同名空文件绕过。
2. 密钥命中：移除文件内容，轮换密钥，并检查日志和提交历史。
3. 环境缺失：在目标 Conda 环境安装依赖，不使用用户级 site-packages。
4. GPU 不可用：停止性能验收，先修复 CUDA/PyTorch 环境。
5. 3D 冒烟失败：检查本地 Three.js 资源、WebEngine 进程和 OpenGL 状态。
6. 测试失败：修复代码或更新测试，不允许通过跳过测试发布。

## 9. 交付记录模板

```text
版本：
构建时间：
目标机器：
Python：
PyTorch/CUDA：
GPU/显存：
release_check：通过 / 失败
verify：通过 / 失败
WebEngine 冒烟：通过 / 失败
连续 10 分钟训练：通过 / 失败
断网演练：通过 / 失败
密钥扫描：通过 / 失败
许可证审计：通过 / 待确认
已知限制：
```
