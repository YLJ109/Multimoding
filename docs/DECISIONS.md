# DanceMirror 已确认决策

本文件记录进入编码前由用户确认、并已落实到实现中的决策。规格文档中尚未展开的部分，以本文件为准。

| 编号 | 主题 | 确认结果 | 实现落点 |
|---:|---|---|---|
| 1 | 输入类型 | 真人视频检测骨架后转换为 3D 动作 | `services/reference.py`、`pose2d/yolo_pose.py`、`pose3d/baseline.py` |
| 2 | 参考来源 | 使用真人舞蹈视频作为标准动作 | `ReferenceAnalysisWorker` 与 `*.dmotion.json` |
| 3 | 模型形态 | 同时保留骨架和低多边形整人体模型 | `renderer/three_scene.py` 的 skeleton/body/overlay |
| 4 | 语音方式 | 即时纠错可以使用云端 TTS | `coaching/tts.py`、设置页 TTS 配置 |
| 5 | 云服务 | 云端 LLM/TTS 都可配置，设置页可修改 | `view/settings_interface.py`、`config.py` |
| 6 | 项目目标 | 比赛型项目，优先稳定演示与隐私可信 | `docs/ENVIRONMENT.md` 的比赛检查清单 |
| 7 | 环境策略 | 接受 `pytorch_cuda_env`，缺少依赖直接安装 | `scripts/install_vision.ps1` |
| 8 | 训练录像 | 需要保存用户训练过程 | `workers/live.py`、`AppPaths.recordings` |
| 9 | 历史对比 | 需要保存并对比历史记录 | `storage/database.py`、`view/history_interface.py` |
| 10 | 隐私遮蔽 | 室友出现在画面时自动遮蔽 | `privacy/__init__.py`、`LiveTrainingWorker` |
| 11 | 离线要求 | 比赛现场不能依赖 CDN | `resources/three.module.min.js` 本地资源 |
| 12 | 实时边界 | 逐帧比较留在本地；云端只做结构化总结和复杂语言规划，返回内容再次经过本地白名单校验 | `workers/cloud.py`、`coaching/cloud.py`、`command/parser.py` |
| 13 | 人物表示 | 大画面只允许一个 3D 机器人，用户始终保持二维骨架，不创建用户 3D/SMPL | `domain/representation.py`、`view/scene_widget.py` |
| 14 | 角色资产 | 默认使用 CC0 机器人；用户可导入有授权的本地 GLB，不打包受保护 IP 角色 | `view/settings_interface.py`、`renderer/three_scene.py` |

## 第一版可实现边界

- 单人、固定机位、全身可见的 30 至 60 秒参考视频。
- 正面或轻微斜侧面优先，快速旋转、严重遮挡、地板动作不作为验收项。
- 低模人体是用于动作观察和比较的体感角色，不等同于高精度 SMPL-X 真人重建。
- 云端服务失败不影响本地训练、评分、录像和历史保存。
- 任何训练录像默认不保存，必须由用户主动开启。
