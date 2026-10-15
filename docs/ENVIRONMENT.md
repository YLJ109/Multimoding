# DanceMirror 环境与运行说明

版本基线：DanceMirror 0.2.0  
目标环境：Conda `pytorch_cuda_env`  
目标设备：RTX 3060 Laptop，6GB 显存  
工作目录：`D:\PythonProjections\MultimodingProject`

## 1. 关键决策

本项目已经按以下边界实施：

1. 参考真人视频通过 YOLO Pose 提取二维关键点，再归一化并注入保守深度，形成可比较、可渲染的动作包。
2. 第一版同时保留 COCO-17 骨架和低多边形人体；界面可在“骨架 / 低模人体 / 叠加”之间切换。
3. 即时语音支持 Windows 本地 SAPI 和云端 OpenAI-compatible TTS，云端配置可在设置页修改。
4. 云端语言模型与 TTS 服务不写死供应商，Base URL、模型、音色、超时均可配置；API Key 只保存在当前进程内。
5. 训练过程默认不上传连续视频。云端只接收结构化分数字段，可生成训练总结。
6. 本地训练录像、隐私遮蔽、SQLite 历史和多次训练对比均已接入。
7. Three.js 已本地化到 `src/dance_mirror/resources/`，包含 `three.module.min.js` 与它依赖的 `three.core.min.js`，避免比赛现场断网导致 3D 白屏。

## 2. 环境隔离

当前 Conda 环境是 Python 3.11。用户级 Python 3.11 `site-packages` 会污染导入路径，项目必须显式禁止用户级包：

```powershell
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
$python = 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe'
```

不要使用 `conda run` 作为日常测试入口。文件锁和临时环境处理可能造成难以诊断的问题。优先直接调用上面这个 Python 解释器。

## 3. 基础依赖

已安装或应安装到目标环境自身 `site-packages` 的包：

```powershell
$env:PYTHONNOUSERSITE = '1'
$python = 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe'

& $python -m pip install `
  numpy opencv-python httpx `
  PyQt6 PyQt6-Fluent-Widgets PyQt6-WebEngine `
  scipy einops
```

如果环境刚重建，先运行：

```powershell
& $python -m pip install --upgrade pip setuptools wheel
```

## 4. CUDA PyTorch

目标是 CUDA wheel，而不是 CPU wheel。当前设备驱动和 CUDA UMD 已满足 CUDA 12.8 wheel 的使用条件。推荐命令：

```powershell
$env:PYTHONNOUSERSITE = '1'
$python = 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe'

& $python -m pip install torch torchvision `
  --index-url https://download.pytorch.org/whl/cu128
```

安装完成后必须核验：

```powershell
$env:PYTHONNOUSERSITE = '1'
& $python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
```

期望结果包含：

- `torch` 版本带 `+cu128`
- `torch.cuda.is_available()` 为 `True`
- GPU 名称包含 NVIDIA GeForce RTX 3060

如果 `torch.cuda.is_available()` 为 `False`，先检查是否误装 CPU wheel，再检查驱动，不要继续做实时姿态调参。

## 5. YOLO 与导出依赖

```powershell
$env:PYTHONNOUSERSITE = '1'
$python = 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe'

& $python -m pip install ultralytics onnxruntime-gpu
```

安装脚本会预下载 `yolo11n-pose.pt`，校验固定 SHA-256，并放入
`%LOCALAPPDATA%\DanceMirror\models`。程序不会在比赛运行时自动下载权重：

```powershell
.\scripts\install_vision.ps1
```

如自定义 `DANCE_MIRROR_HOME`，脚本和程序会使用同一目录。设置页默认指向该
绝对路径；不要改成依赖当前工作目录的相对文件名。

## 6. 运行

推荐使用项目脚本：

```powershell
.\scripts\run.ps1
```

也可以直接运行：

```powershell
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = (Resolve-Path 'src').Path
& 'C:\Users\Administrator\.conda\envs\pytorch_cuda_env\python.exe' -m dance_mirror.app
```

环境自检：

```powershell
.\scripts\doctor.ps1
```

## 7. 云端服务约定

### 7.1 语言模型

使用 OpenAI-compatible Chat Completions：

```text
POST {base_url}/chat/completions
```

请求只包含结构化训练摘要，例如总分、身体部分分数、提示计数和持续时间。不要将连续视频作为请求体发送。

### 7.2 云端 TTS

使用 OpenAI-compatible Speech：

```text
POST {base_url}/audio/speech
```

请求字段：

```json
{
  "model": "gpt-4o-mini-tts",
  "voice": "alloy",
  "input": "左手抬高一点。",
  "response_format": "mp3"
}
```

如果服务商字段名不同，需要在 `src/dance_mirror/coaching/tts.py` 的适配器中增加明确的适配层，不要在 UI 或主窗口中拼接请求。

## 8. 本地录像与隐私

- 默认不保存摄像头录像，必须在设置页主动开启。
- 默认启用其他人物模糊；当前只对本地录像帧进行遮蔽，原始摄像头帧不写入磁盘。
- 主人物选择来自 YOLO Pose 的平均关键点置信度，存在误选风险时应先人工确认机位。
- 录像路径位于 `AppPaths.recordings`，历史数据库位于 `AppPaths.data/training_history.sqlite3`。
- 若室友出现在画面中，演示前仍应主动说明并在设置页确认隐私遮蔽开关已打开。

## 9. 6GB 显存策略

- 参考视频只在准备阶段离线处理一次。
- 实时阶段只保留一个 YOLO Pose 实例，不与参考视频同时推理。
- 默认摄像头 720p，实时目标 15 FPS；设置页可以降低到 10 FPS。
- 渲染优先使用本地 Three.js 低模人体；显存不足时切换到骨架模式。
- 云端 LLM 只做训练结束后的总结，不参与逐帧推理。
- 如果出现 CUDA OOM，按顺序降低摄像头分辨率、实时 FPS、YOLO `imgsz`，最后切换 ONNX/TensorRT 导出。
- 不在此设备上运行本地大语言模型、扩散模型或高精度 SMPL-X。

## 10. 离线比赛检查

比赛前至少完成一次：

1. 断网启动 `.\scripts\run.ps1`。
2. 确认 3D 场景不是白屏，骨架和低模人体都能显示。
3. 用一段 30 至 60 秒固定机位视频完成参考动作解析。
4. 打开摄像头，确认 720p 下可以连续训练 10 分钟。
5. 打开录像和隐私遮蔽，确认室友区域被模糊。
6. 关闭网络后再次训练，确认云端失败不会阻塞本地训练和本地历史记录。
7. 在设置页填入准备好的云端 Key 后，完成一次训练总结请求。
8. 检查 `logs/dance_mirror.log` 没有未处理的异常和线程退出警告。

## 11. 许可提醒

PyQt6、PyQt6-Fluent-Widgets、Ultralytics 和 Three.js 均有各自许可证。比赛或商业发布前必须确认使用方式。参考舞蹈视频、音乐和动作数据也需要自行取得授权。不要把未授权视频或音乐打包进发布程序。
