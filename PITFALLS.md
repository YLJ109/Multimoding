# DanceMirror 踩坑账本

| 日期 | 现象 | 根因 | 修复 | 关键词 |
|---|---|---|---|---|
| 2026-09-21 | `pytorch_cuda_env` 看似已安装大量包，但读不到 torch | 包装在 Python 3.13 用户级 `site-packages`，目标环境是 Python 3.11 | 项目依赖必须安装到目标环境自身 `site-packages`，并禁止依赖用户级包 | conda, torch, user-site, python-version |
| 2026-09-21 | 导入到错误的 PyQt6、OpenCV 或旧 TensorFlow | 默认 Python 会加载用户级 `site-packages`，与 Conda 环境包混用 | 所有安装、测试、启动均设置 `PYTHONNOUSERSITE=1` | user-site, PyQt6, TensorFlow, DLL |
| 2026-09-21 | `conda run` 偶发临时文件锁失败 | Conda 运行包装器与 Windows 文件锁交互 | 直接调用目标环境 Python，脚本中固定绝对路径 | conda-run, windows, lock |
| 2026-09-21 | 比赛现场 3D 场景白屏 | Three.js 从 CDN 加载，断网后模块请求失败 | 将 `three.module.min.js` 固定到项目 `resources`，并保留原生骨架回退 | three.js, cdn, offline |
| 2026-09-21 | 摄像头帧持续低置信度但界面仍在评分 | 低置信度帧被当作正常动作进入比较 | 评分前检查特征置信度和覆盖率，低置信度只提示站位 | confidence, pose, scoring |
| 2026-09-21 | 云端 TTS 或 LLM 失败拖慢训练 | 网络请求被错误地放进实时循环 | 云端只在训练结束后总结；TTS 使用有界队列和独立 Worker | cloud, tts, queue, worker |
| 2026-09-21 | CUDA 模式 YOLO 推理时报 “can't convert cuda:0 device type tensor to numpy” | Ultralytics 的 boxes/keypoints 输出仍在 GPU 上 | 统一先 `detach().cpu().numpy()` 再进入 NumPy 业务边界 | YOLO, CUDA, tensor, numpy |
| 2026-09-21 | PyQt6 WebEngine 总是回退到原生骨架，或直接崩溃 | QtWebEngineWidgets 必须在 QApplication 前完成共享 OpenGL 上下文配置 | 启动前设置 `AA_ShareOpenGLContexts`，并开启 SwiftShader 渲染兜底 | PyQt6, WebEngine, OpenGL, SwiftShader |
| 2026-09-21 | 比赛电脑无法从 GitHub 下载 YOLO 权重 | 下载源不稳定或现场断网 | 安装阶段固定 `yolo11n-pose.pt` 与 SHA-256，运行时只接受本地权重 | YOLO, weights, offline, checksum |
| 2026-09-21 | 15 FPS 训练录像播放速度异常、参考动作不同步 | 摄像头实际输出 30 FPS，但采样循环按 15 FPS 写入 | 实时时间轴使用 monotonic 时钟，录像帧率固定为实际采样目标帧率 | camera, fps, recording, timestamp |
