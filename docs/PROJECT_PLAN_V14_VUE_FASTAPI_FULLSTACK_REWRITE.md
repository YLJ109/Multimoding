# 舞镜 DanceMirror 2.0 — 全栈重构技术方案

> **一句话定义**：把手机里的真人舞蹈视频，一键变成可在浏览器里"照着跳"的 3D 机器人示范，并通过**手势门控 → 实时跟练 → 表现力结算 → 差异驱动的复训**形成闭环；同时提供"真人做啥机器人做啥"的**实时镜像 + 机器人控制中心**。
>
> **技术栈**：Vue 3 + Vite + TypeScript + Three.js（前端） / FastAPI + SQLAlchemy 2.0 + SQLite（后端） / Python 算法内核以包形式复用。
>
> **文档版本**：V14 · 2026-09-29 · 目标：毕业设计答辩 + 应用类竞赛（互联网+/挑战杯/服务外包），并为算法类赛道预留方法层。

---

## 0. 重构判据：为什么是这次、为什么这样切

### 0.1 旧系统的真实死因（不是"技术垃圾"）

| 现象 | 真实根因 | 换栈能否解决 |
|---|---|---|
| 3D 舞台永远空白 | **desktop 宿主 QWebEngine 在本环境连 `<h1>` 都加载失败**（已实测 `loadFinished=False`） | ✅ 换浏览器前端直接绕过 |
| 改一处崩一处 | 管线在 view 层与 worker 层各写一遍，接缝无契约 | ✅ 契约唯一真源 + 代码生成 |
| 单机、不可分享 | PyQt6 桌面应用，答辩只能本机演示 | ✅ B/S 化，一个链接打开 |
| 无用户/无数据沉淀 | 无持久层，历史靠本地文件 | ✅ SQLite + 服务端权威记录 |
| 机器人模仿不到位 | 纯几何对齐，无接触/平衡约束 | ⚠️ 需算法层升级（本方案的创新点 1） |

**结论**：换栈解决的是 1–4；第 5 条必须靠算法层方法升级解决，否则"换壳不涨创新点"。

### 0.2 重构边界（重要，直接决定工期与风险）

| 层 | 处置 | 理由 |
|---|---|---|
| `view/`（PyQt6 界面全部） | **全部丢弃** | 换栈后被 Vue 取代，无一保留 |
| `workers/`（QThread 封装） | **全部丢弃** | 被 FastAPI 异步任务 + 浏览器主循环取代 |
| `renderer/three_scene.py` 的 HTML 模板 | **重写** | 迁移为 Vue 组件 + 独立 three.js 模块 |
| `pose3d/` `pose2d/` `motion/` `domain/` `multimodal/` `coaching/` `storage/` `services/` | **以"内核包"形式复用并补测** | 这是已验证的数学与教训，重写=白扔 2–3 周且引入回归 |
| `storage/database.py` | **重写** | 从裸 sqlite3 升级到 SQLAlchemy 2.0 + Alembic 迁移 |

> **一句话**：旧代码里约 95% 的价值是**算法与踩坑记录**，约 100% 的技术债在**UI 与控制层**。所以是"应用全新 + 内核迁移"，不是"逐行重写"。

---

## 1. 产品定位与目标用户

| 维度 | 内容 |
|---|---|
| **场景** | 家庭客厅 / 宿舍 / 教室，一台笔记本 + 一个摄像头 |
| **主用户** | 想学舞但请不起老师、又不敢在镜子前跳的普通学生 |
| **次用户** | 体育/美育教师（布置跟练作业并看班级报告）、机器人科普展台讲解员 |
| **核心价值** | ① 把"任意舞蹈视频"变成"可跟练的 3D 示范"；② 把"跳得怎么样"从模糊感受变成**可解释的四维分数**；③ 把"真人动作"实时搬到 3D 机器人上，做具身智能的直观演示 |
| **差异化** | 同类产品（Kalidoface 3D、VTube Studio、各类舞蹈 App）要么只做实时驱动、要么只做视频跟练评分；**本系统把"视频→资产→跟练→评分→复训"与"实时具身映射"合并在一个闭环里，并给出物理可信的重定向** |

---

## 2. 两条主线场景（详细用户旅程）

### 场景 A：视频 → 3D 模板 → 跟练 → 结算

```
① 上传视频           ② 转 3D 模板           ③ 选模板 + 站位校准
  手机拍的跳舞片段  →  服务端抽帧/估姿/    →  "请后退半步让全身入镜"
  (≤200MB, ≤5min)     平滑/分级/入库          实时红黄绿提示
        │                    │                       │
        ▼                    ▼                       ▼
   进度条 + SSE         动作包卡片               ④ 手势门控
   阶段化提示           (BPM/难度/风格/          👌 OK 手势保持 0.6s
   可离开页面            质量等级/预览)          → 3-2-1 节拍倒计时
                                                       │
        ┌──────────────────────────────────────────────┘
        ▼
⑤ 跟练中（主舞台）
   · 左：3D 机器人示范（可换皮肤/角色）  右：我的摄像头画面（2D 骨架叠加）
   · 底部：节拍时间轴 + 当前分数 + 四维实时条
   · 实时纠错：偏差超阈值时高亮"应该动的那个关节"（黄→红）
   · 随时：空格暂停 / 急停 / 镜像开关 / 慢放 0.5×–1.0×
        │
        ▼
⑥ 结算画面
   总分 + 星级 + 四维雷达 + 时间轴热力图 + 最佳/最差 3 段回放（左右对照）
   + 教练点评 3 条（LLM，短 JSON，本地校验）+ XP/等级 + 成就解锁
   + [保存报告] [生成分享卡 PNG] [只练弱项] [再来一次] [换动作]
        │
        ▼
⑦ 复训闭环
   "只练弱项" 自动裁出最差的 3 个节拍片段组成 mini 包 → 重跳 → 曲线对比
```

**关键设计**：第 ③④ 步是**转化率生死线**。门控必须"严进宽出"——识别严格（防误触发），但永远提供**手动开始**兜底（按钮 / 空格 / 无摄像头模式），绝不因识别失败卡死演示。

### 场景 B：实时镜像 + 机器人控制中心

```
┌─ 实时镜像页（单人）────────────────────────────────────┐
│  浏览器摄像头 → 浏览器内 BlazePose（WASM/WebGL）        │
│      ↓ 17 点 COCO 归一化 3D 坐标                        │
│  ① 本地重定向（接触感知，含脚锁定/平衡约束）→ 我的 3D 机器人 │
│  ② 同时以 30Hz 二进制特征帧上行 → 服务端权威评分/记录      │
│  端到端延迟目标 ≤ 120ms                                 │
└──────────────────────────────────────────────────────┘
                    ↓ 可选：下发到真实/仿真机器人
┌─ 控制中心（多机监控台）─────────────────────────────────┐
│  机器人列表：在线状态 · 心跳 · 温度/负载 · 当前动作包        │
│  批量命令：播放 / 暂停 / 继续 / 停止 / 急停 / 回原点        │
│  分发模式：① 全体同步镜像同一人  ② 每人一机（课堂分组）      │
│  安全：默认「演练模式」仅驱动 3D 仿真；    指令白名单 +      │
│        参数范围本地二次校验；急停永远本地优先，不等网络       │
│  事件流：每条指令写审计日志 + 可回放指令时间线              │
└──────────────────────────────────────────────────────┘
```

> **隐私红线（本方案的核心优势）**：实时链路中**视频帧永不出浏览器**。浏览器完成姿态估计后只上行"特征帧"（约 6–21 KB/s，纯数值、不可还原画面）。这条设计同时解决了带宽、延迟、隐私、合规四个问题，也是答辩时的强叙事点。

---

## 3. 总体架构

```
┌─────────────────────────── 浏览器（Vue 3 + Vite + TS）───────────────────────────┐
│  View 层        Pages / Components / 设计令牌(CSS 变量 + TS token 单一真源)       │
│  State 层       Pinia stores（session / robot / library / auth）+ 会话状态机      │
│  Realtime 层    WebSocket 二进制帧编解码 · 背压 · 重连 · 本地快速通道(暂停/急停)   │
│  Motion 层      @dm/motion-js：BlazePose(WASM) · 手势识别 · 特征提取 · 本地重定向  │
│  Render 层      three.js 舞台（本地 vendored，离线可用）· 皮肤/角色 · 后处理       │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                          HTTPS / REST (JSON)  +  WSS (binary + JSON)
┌──────────────────────────────────▼───────────────────────────────────────────────┐
│                        FastAPI（apps/api）                                        │
│  Routers    auth · packages · jobs · sessions · reports · robots · ws             │
│  Services   动作包流水线 · 权威评分引擎 · 教练编排 · 控制中心 · 进度与成就           │
│  Tasks      asyncio 任务队列 + 进程池（视频重任务）+ 进度经 SSE 下发                │
│  Drivers    RobotDriver: sim | ws_bridge | modbus | efort   （统一接口，可插拔）    │
│  Persist    SQLAlchemy 2.0 + Alembic + SQLite(WAL, FTS5)                          │
└──────────────────────────────────┬───────────────────────────────────────────────┘
┌──────────────────────────────────▼───────────────────────────────────────────────┐
│              packages/core —— 纯 Python 算法内核（无 IO / 无框架 / 可单测）         │
│  pose（BlazePose/YOLO 封装）· retarget（接触感知）· features · comparison(DTW)     │
│  gesture（手势判定）· scoring（四维）· package（dmotion v2 序列化）· smoothing     │
└──────────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────────────────┐
│  packages/contracts —— Pydantic v2 单一真源  ──自动生成──▶  packages/contracts/ts  │
│  （REST 模型 / WS 消息 / 动作包 schema / 枚举；CI 校验产物无漂移）                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 为什么"客户端估姿 + 服务端权威评分"

| 方案 | 延迟 | 带宽 | 隐私 | 评分一致性 | 结论 |
|---|---|---|---|---|---|
| 视频全部上行，服务端估姿 | 高（编码+上行+排队） | 高（Mbps） | 差（画面出机器） | 天然一致 | ❌ |
| 全部在浏览器（含评分） | 最低 | 0 | 最好 | **两套实现，必然漂移** | ❌ |
| **本方案：客户端估姿 + 特征上行 + 服务端权威评分** | 低（估姿本地，评分不影响画面） | 极低 | 好 | ✅ 唯一真源 | ✅ |

- 实时**渲染**只依赖本地结果 → 延迟与网络无关，画面永远跟手；
- **评分/排名/成就**由服务端算 → 防篡改、可审计、可复算（换算法的版本号一起存）；
- 跨语言一致性由 **一致性测试夹具** 锁定（见 §16.3）。

---

## 4. 技术栈清单（版本锁定）

| 层 | 选型 | 版本 | 说明 |
|---|---|---|---|
| 前端框架 | Vue | 3.5.x | `<script setup>` + TS |
| 构建 | Vite | 6.x | 开发期 HMR，生产 rollup |
| 语言 | TypeScript | 5.6+ | `strict: true` |
| 状态 | Pinia | 2.x | 按领域分 store，禁止单 store 上帝对象 |
| 路由 | Vue Router | 4.x | 懒加载路由级分包 |
| 样式 | Tailwind CSS | 4.x + CSS 变量 | 颜色**只**来自设计令牌 |
| 组件库 | Element Plus | 2.x | **仅**用于表格/表单/日期等复杂控件，不用于主舞台 |
| 3D | three.js | 0.180（本地 vendored） | `three.module.min.js` + `three.core.min.js` 已在仓库 |
| 姿态 | MediaPipe Tasks Vision | 0.10.x | WASM + WebGL delegate，浏览器端 |
| 图表 | ECharts | 5.x | 雷达图/时间轴热力/曲线 |
| 后端框架 | FastAPI | 0.115+ | 全异步 + Pydantic v2 |
| ASGI | uvicorn | 0.32+ | `--workers 4` |
| ORM | SQLAlchemy | 2.0（async） | `AsyncSession` + `aiosqlite` |
| 迁移 | Alembic | 1.13+ | 每次 schema 变更必带迁移 |
| DB | SQLite | 3.45+ | WAL + `foreign_keys=ON` + FTS5(trigram) |
| 校验 | Pydantic | 2.x | 契约唯一真源 |
| 认证 | PyJWT + argon2-cffi | — | access 15min / refresh 14d 轮换 |
| 视频 | ffmpeg / ffprobe | 系统 | 探测真实容器，抽帧 |
| 内核 | mediapipe / opencv / numpy / scipy | 沿用现有环境 | 与旧项目同环境（`pytorch_cuda_env`） |
| 测试 | pytest / pytest-asyncio / vitest / Playwright | — | 见 §16 |

---

## 5. 仓库目录结构

```
dance-mirror/
├─ apps/
│  ├─ web/                          # Vue 3 前端
│  │  ├─ src/
│  │  │  ├─ pages/                  # Home / Library / Studio / Mirror / Console / Report
│  │  │  ├─ components/             # StageView CameraDock MetricsPanel GestureGate ...
│  │  │  ├─ stores/                 # session.ts robot.ts library.ts auth.ts
│  │  │  ├─ realtime/               # ws.ts frameCodec.ts backpressure.ts
│  │  │  ├─ design/                 # tokens.ts tokens.css themes.ts
│  │  │  └─ api/                    # 由 contracts 生成的类型 + 手写 fetcher
│  │  └─ public/                    # three.module.min.js three.core.min.js wasm
│  └─ api/                          # FastAPI 后端
│     ├─ app/
│     │  ├─ main.py
│     │  ├─ routers/               # auth packages jobs sessions reports robots ws
│     │  ├─ services/              # pipeline scoring coach control progress
│     │  ├─ drivers/               # sim.py ws_bridge.py modbus.py efort.py
│     │  ├─ db/                    # models.py session.py deps.py seed.py
│     │  ├─ tasks/                 # queue.py worker.py
│     │  └─ security/              # jwt.py hashing.py limits.py
│     └─ alembic/
├─ packages/
│  ├─ core/                         # 纯算法内核（从旧 src/dance_mirror 迁移）
│  │  └─ dm_core/{pose,retarget,features,comparison,gesture,scoring,package,smoothing}/
│  ├─ contracts/                    # Pydantic 模型 + 生成的 TS 类型
│  └─ motion-js/                    # 浏览器端姿态/手势/特征（TS，与 core 对齐）
├─ assets/
│  ├─ builtin_packages/             # 6–8 个官方预设动作包（dmotion v2）
│  ├─ characters/                   # GLB 角色/皮肤
│  └─ fonts/
├─ data/                            # 运行期（git-ignored）
│  ├─ dance_mirror.db
│  ├─ uploads/                      # 原始视频
│  ├─ packages/                     # 动作包 payload
│  └─ previews/
├─ scripts/
│  ├─ dev.ps1  start.ps1  verify.ps1
│  ├─ gen_ts_types.py               # contracts → TS
│  └─ seed_builtin.py
├─ tests/
│  ├─ api/  conformance/  e2e/  perf/
├─ docs/
└─ .workbuddy/memory/
```

---

## 6. 数据模型（SQLite DDL）

> 约定：所有时间戳为 `INTEGER`（毫秒 Unix）；所有 ID 为 `TEXT`（UUIDv7，可排序）；连接开启 `PRAGMA foreign_keys=ON; journal_mode=WAL; synchronous=NORMAL`。
> **大对象不入库**：视频/动作包 payload 落盘，DB 只存 `path` + `bytes` + `sha256`。

```sql
-- ============ 用户与认证 ============
CREATE TABLE users (
  id             TEXT PRIMARY KEY,
  username       TEXT NOT NULL UNIQUE,
  display_name   TEXT NOT NULL,
  avatar_url     TEXT,
  password_hash  TEXT NOT NULL,              -- argon2id
  role           TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','guest','admin')),
  created_at     INTEGER NOT NULL,
  last_login_at  INTEGER
);

CREATE TABLE auth_sessions (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_hash TEXT NOT NULL,                -- 只存哈希
  device_label TEXT,
  user_agent   TEXT,
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  revoked_at   INTEGER
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);

-- ============ 素材与动作包 ============
CREATE TABLE assets (
  id           TEXT PRIMARY KEY,
  owner_id     TEXT REFERENCES users(id) ON DELETE SET NULL,
  kind         TEXT NOT NULL CHECK (kind IN ('source_video','motion_payload','preview_clip','thumbnail','share_card')),
  path         TEXT NOT NULL,                -- 相对 data/ 的路径
  bytes        INTEGER NOT NULL,
  sha256       TEXT NOT NULL,
  duration_ms  INTEGER,
  fps          REAL,
  width        INTEGER,
  height       INTEGER,
  created_at   INTEGER NOT NULL
);
CREATE INDEX idx_assets_owner_kind ON assets(owner_id, kind);

CREATE TABLE motion_packages (
  id                 TEXT PRIMARY KEY,
  owner_id           TEXT REFERENCES users(id) ON DELETE SET NULL,   -- NULL = 官方预设
  title              TEXT NOT NULL,
  description        TEXT NOT NULL DEFAULT '',
  source_kind        TEXT NOT NULL CHECK (source_kind IN ('upload','builtin','recorded_live','imported')),
  source_asset_id    TEXT REFERENCES assets(id) ON DELETE SET NULL,
  schema_version     TEXT NOT NULL,          -- 'dmotion/2'
  duration_ms        INTEGER NOT NULL,
  frame_count        INTEGER NOT NULL,
  fps                REAL NOT NULL,
  bpm                REAL,
  difficulty         INTEGER NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
  style              TEXT NOT NULL DEFAULT 'other',
  scope              TEXT NOT NULL DEFAULT 'full_body' CHECK (scope IN ('full_body','upper_body','hands_only')),
  mirror_safe        INTEGER NOT NULL DEFAULT 1,
  quality_confidence REAL NOT NULL DEFAULT 0,        -- 0..1
  quality_grade      TEXT NOT NULL DEFAULT 'B' CHECK (quality_grade IN ('S','A','B','C','rejected')),
  visibility         TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private','unlisted','public')),
  payload_asset_id   TEXT NOT NULL REFERENCES assets(id),
  thumb_asset_id     TEXT REFERENCES assets(id),
  preview_asset_id   TEXT REFERENCES assets(id),
  play_count         INTEGER NOT NULL DEFAULT 0,
  created_at         INTEGER NOT NULL,
  updated_at         INTEGER NOT NULL
);
CREATE INDEX idx_pkg_owner      ON motion_packages(owner_id, created_at DESC);
CREATE INDEX idx_pkg_discovery  ON motion_packages(visibility, difficulty, style);
CREATE INDEX idx_pkg_scope_bpm  ON motion_packages(scope, bpm);

-- 按节拍切分，用于"只练弱项"与动态难度
CREATE TABLE motion_segments (
  id           TEXT PRIMARY KEY,
  package_id   TEXT NOT NULL REFERENCES motion_packages(id) ON DELETE CASCADE,
  idx          INTEGER NOT NULL,
  start_ms     INTEGER NOT NULL,
  end_ms       INTEGER NOT NULL,
  beat_count   INTEGER NOT NULL DEFAULT 4,
  difficulty   INTEGER NOT NULL DEFAULT 3,
  label        TEXT,                          -- 'wave','spin','step_touch'...
  key_angles   TEXT,                          -- JSON：该段代表性关节角（用于差异高亮）
  UNIQUE (package_id, idx)
);

CREATE TABLE tags (
  id   TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'style'          -- style | body_part | mood
);
CREATE TABLE package_tags (
  package_id TEXT NOT NULL REFERENCES motion_packages(id) ON DELETE CASCADE,
  tag_id     TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (package_id, tag_id)
);

-- 中文检索必须用 trigram 分词器（SQLite >= 3.34）
CREATE VIRTUAL TABLE motion_packages_fts USING fts5(
  title, description, tags,
  content='', tokenize='trigram'
);

-- ============ 训练会话 ============
CREATE TABLE dance_sessions (
  id                TEXT PRIMARY KEY,
  user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  package_id        TEXT REFERENCES motion_packages(id) ON DELETE SET NULL,
  mode              TEXT NOT NULL CHECK (mode IN ('follow_template','live_mirror','control_center')),
  status            TEXT NOT NULL CHECK (status IN ('created','gesture_wait','armed','running','paused','settled','aborted')),
  engine_side       TEXT NOT NULL DEFAULT 'client' CHECK (engine_side IN ('client','server')),
  started_at        INTEGER NOT NULL,
  ended_at          INTEGER,
  active_ms         INTEGER NOT NULL DEFAULT 0,      -- 扣掉暂停
  mirror            INTEGER NOT NULL DEFAULT 0,
  scope             TEXT NOT NULL DEFAULT 'full_body',
  slowdown          REAL NOT NULL DEFAULT 1.0,
  score_total       REAL,
  score_pose        REAL,
  score_rhythm      REAL,
  score_dynamics    REAL,
  score_fluency     REAL,
  stars             INTEGER,
  xp_gained         INTEGER NOT NULL DEFAULT 0,
  abort_reason      TEXT,
  scoring_version   TEXT NOT NULL DEFAULT 'score/1',
  created_at        INTEGER NOT NULL
);
CREATE INDEX idx_session_user ON dance_sessions(user_id, created_at DESC);
CREATE INDEX idx_session_pkg  ON dance_sessions(package_id);

-- 抽稀到 5Hz 的逐帧分数（全量 30–60Hz 只留在本地/临时文件，避免库膨胀）
CREATE TABLE session_frames (
  session_id   TEXT NOT NULL REFERENCES dance_sessions(id) ON DELETE CASCADE,
  t_ms         INTEGER NOT NULL,
  score_total  REAL NOT NULL,
  score_pose   REAL, score_rhythm REAL, score_dynamics REAL, score_fluency REAL,
  com_offset_m REAL,
  contact_l    INTEGER, contact_r INTEGER,
  deviation    TEXT,                                  -- JSON：偏差最大的 top-3 关节
  PRIMARY KEY (session_id, t_ms)
) WITHOUT ROWID;

CREATE TABLE session_events (
  id          TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL REFERENCES dance_sessions(id) ON DELETE CASCADE,
  t_ms        INTEGER NOT NULL,
  kind        TEXT NOT NULL,        -- gesture_ok / armed / start / pause / resume / estop / low_fps / reconnect / abort
  payload     TEXT,
  created_at  INTEGER NOT NULL
);
CREATE INDEX idx_event_session ON session_events(session_id, t_ms);

-- ============ 报告与教练 ============
CREATE TABLE reports (
  id                 TEXT PRIMARY KEY,
  session_id         TEXT NOT NULL UNIQUE REFERENCES dance_sessions(id) ON DELETE CASCADE,
  user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  summary_md         TEXT NOT NULL,
  highlights         TEXT NOT NULL,     -- JSON：最佳 3 段
  weakest_segments   TEXT NOT NULL,     -- JSON：最差 3 段（用于"只练弱项"）
  next_actions       TEXT NOT NULL,     -- JSON：3 条可执行建议
  llm_provider       TEXT,
  llm_model          TEXT,
  prompt_tokens      INTEGER,
  completion_tokens  INTEGER,
  fallback_used      INTEGER NOT NULL DEFAULT 0,
  created_at         INTEGER NOT NULL
);

CREATE TABLE coach_messages (
  id         TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES dance_sessions(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('user','coach')),
  content    TEXT NOT NULL,
  validated  INTEGER NOT NULL DEFAULT 1,   -- 是否通过本地白名单校验
  created_at INTEGER NOT NULL
);

-- ============ 进度与激励 ============
CREATE TABLE user_progress (
  user_id            TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  xp                 INTEGER NOT NULL DEFAULT 0,
  level              INTEGER NOT NULL DEFAULT 1,
  streak_days        INTEGER NOT NULL DEFAULT 0,
  last_practice_date TEXT,
  total_sessions     INTEGER NOT NULL DEFAULT 0,
  total_active_ms    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE achievements (
  id          TEXT PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,        -- 'first_dance','rhythm_master','week_streak'
  name        TEXT NOT NULL,
  description TEXT NOT NULL,
  rule        TEXT NOT NULL,               -- JSON 规则，服务端求值
  icon        TEXT NOT NULL DEFAULT 'star'
);

CREATE TABLE user_achievements (
  user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  achievement_id TEXT NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
  unlocked_at    INTEGER NOT NULL,
  PRIMARY KEY (user_id, achievement_id)
);

-- 排行榜用视图，避免冗余表
CREATE VIEW v_leaderboard AS
SELECT s.user_id,
       u.display_name,
       p.id   AS package_id,
       p.title AS package_title,
       MAX(s.score_total) AS best_score,
       COUNT(*)           AS attempts
FROM dance_sessions s
JOIN users u            ON u.id = s.user_id
LEFT JOIN motion_packages p ON p.id = s.package_id
WHERE s.status = 'settled'
GROUP BY s.user_id, p.id;

-- ============ 控制中心 ============
CREATE TABLE robots (
  id              TEXT PRIMARY KEY,
  owner_id        TEXT REFERENCES users(id) ON DELETE SET NULL,
  name            TEXT NOT NULL,
  driver          TEXT NOT NULL CHECK (driver IN ('sim','ws_bridge','modbus','efort')),
  endpoint        TEXT,                       -- ws://ip:port 或 host:502
  model_variant   TEXT NOT NULL DEFAULT 'dance_robot_cyber',
  status          TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('offline','idle','busy','error')),
  mode            TEXT NOT NULL DEFAULT 'drill' CHECK (mode IN ('drill','live','readonly')),  -- drill=仅驱动仿真
  capabilities    TEXT NOT NULL DEFAULT '{}',  -- JSON：支持的命令集合
  last_heartbeat  INTEGER,
  created_at      INTEGER NOT NULL
);

CREATE TABLE robot_commands (
  id         TEXT PRIMARY KEY,
  robot_id   TEXT NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
  issued_by  TEXT REFERENCES users(id) ON DELETE SET NULL,
  session_id TEXT REFERENCES dance_sessions(id) ON DELETE SET NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('play','pause','resume','stop','estop','home','set_pose')),
  payload    TEXT NOT NULL DEFAULT '{}',
  state      TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','sent','acked','failed')),
  issued_at  INTEGER NOT NULL,
  acked_at   INTEGER,
  error      TEXT
);
CREATE INDEX idx_robot_cmd ON robot_commands(robot_id, issued_at DESC);

CREATE TABLE robot_telemetry (
  robot_id   TEXT NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
  t_ms       INTEGER NOT NULL,
  joints     TEXT,                       -- JSON：6 轴角度
  load_pct   REAL,
  temp_c     REAL,
  fps        REAL,
  PRIMARY KEY (robot_id, t_ms)
) WITHOUT ROWID;

-- ============ 异步任务与审计 ============
CREATE TABLE jobs (
  id           TEXT PRIMARY KEY,
  user_id      TEXT REFERENCES users(id) ON DELETE SET NULL,
  kind         TEXT NOT NULL,            -- 'ingest_video' | 'rebuild_preview' | 'export_report'
  state        TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed','canceled')),
  priority     INTEGER NOT NULL DEFAULT 100,
  progress     REAL NOT NULL DEFAULT 0,
  stage        TEXT,                     -- 'probe' | 'extract' | 'smooth' | 'package' | 'grade'
  payload      TEXT NOT NULL DEFAULT '{}',
  result       TEXT,
  error        TEXT,
  attempts     INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL,
  started_at   INTEGER,
  finished_at  INTEGER
);
CREATE INDEX idx_jobs_state ON jobs(state, priority, created_at);

CREATE TABLE audit_log (
  id         TEXT PRIMARY KEY,
  actor_id   TEXT,
  action     TEXT NOT NULL,
  target     TEXT,
  detail     TEXT,
  ip         TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);

CREATE TABLE settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

---

## 7. API 契约

### 7.1 REST（前缀 `/api/v1`）

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/auth/register` | 注册（用户名+密码，可访客） | 公开 |
| POST | `/auth/login` | 登录，返回 access+refresh | 公开 |
| POST | `/auth/refresh` | 刷新（refresh 轮换，旧的立即失效） | 公开 |
| POST | `/auth/logout` | 撤销当前 refresh | 登录 |
| GET | `/me` | 当前用户 + 进度摘要 | 登录 |
| GET | `/packages` | **检索**：`q,difficulty,scope,style,bpm_min,bpm_max,duration_max,sort,page,page_size` | 登录 |
| POST | `/packages/upload` | 上传视频建包（multipart）→ 返回 `job_id` | 登录 |
| GET | `/packages/{id}` | 动作包详情（含分段与元数据） | owner 或 public |
| PATCH | `/packages/{id}` | 改标题/描述/难度/可见性 | **owner 校验** |
| DELETE | `/packages/{id}` | 删除（级联 assets 清理） | **owner 校验** |
| GET | `/packages/{id}/motion` | 取 `dmotion.json`（gzip + ETag + Range） | owner 或 public |
| GET | `/packages/{id}/segments` | 分段列表 | owner 或 public |
| POST | `/packages/{id}/publish` | 公开到动作库 | **owner 校验** |
| GET | `/jobs/{id}` | 任务状态（轮询兜底） | **owner 校验** |
| GET | `/jobs/{id}/events` | **SSE** 阶段化进度（推荐主通道） | **owner 校验** |
| POST | `/jobs/{id}/cancel` | 取消任务 | **owner 校验** |
| POST | `/sessions` | 创建会话（选包/模式/镜像/慢放） | 登录 |
| GET | `/sessions` | 历史列表 | **owner 校验** |
| GET | `/sessions/{id}` | 会话详情 | **owner 校验** |
| POST | `/sessions/{id}/abort` | 中止（带 reason） | **owner 校验** |
| POST | `/sessions/{id}/settle` | 结算：写分数/星级/XP/成就，生成报告 | **owner 校验** |
| GET | `/sessions/{id}/report` | 报告（含教练文案） | **owner 校验** |
| POST | `/sessions/{id}/report/regenerate` | 重新生成教练点评 | **owner 校验** |
| GET | `/progress` `/achievements` `/leaderboard` | 进度 / 成就 / 榜 | 登录 |
| GET | `/robots` | 机器人列表 + 状态 | 登录 |
| POST | `/robots/{id}/commands` | 下发命令（白名单 + 范围校验） | 登录 + 审计 |
| GET | `/robots/{id}/telemetry?since=` | 遥测回放 | 登录 |
| GET | `/health` `/version` | 健康检查（部署与答辩前自检） | 公开 |

**统一错误体**：
```json
{"error": {"code": "PACKAGE_NOT_FOUND", "message": "动作包不存在", "detail": {}, "trace_id": "..."}}
```

### 7.2 WebSocket

| 端点 | 用途 | 载荷 |
|---|---|---|
| `WSS /api/v1/ws/live/{session_id}` | 实时跟练/镜像 | **上行二进制特征帧**；下行 JSON（评分 10Hz / 状态 / 教练 / 急停确认） |
| `WSS /api/v1/ws/console` | 控制中心 | 双向 JSON：机器人状态广播、命令回执、遥测 |
| `WSS /api/v1/ws/watch/{session_id}` | 大屏/观众只读 | 下行 JSON（与 live 同构，去掉评分以外的隐私字段） |

**鉴权**：连接后 3 秒内必须发送首帧 `{"type":"auth","token":"<access>"}`，否则 4401 关闭。
**心跳**：客户端每 5s `{"type":"ping"}` → 服务端 `{"type":"pong","server_t":...}`，用于估算单向延迟。

### 7.3 二进制特征帧协议（`dmf/1`，little-endian）

```
Byte  0      : uint8   version = 1
Byte  1      : uint8   flags   bit0 mirror / bit1 pose_valid / bit2 has_left_hand / bit3 has_right_hand
Byte  2..3   : uint16  seq（回绕计数，用于丢包统计）
Byte  4..7   : uint32  t_ms（会话时钟）
Byte  8..9   : uint16  n_joints（=17，COCO17）
Byte 10..11  : uint16  reserved（对齐）
--- 之后为变长体 ---
[17 × 3] float32 : 归一化 3D 关节坐标（米；以髋中点为原点，y 向上，+z 朝相机）
[1]      float32 : 姿态置信度 0..1
[1]      float32 : 重心相对支撑多边形的偏移（米，正=偏右）
[2]      uint8   : 接触标志 left/right（0/1）
[2]      float32 : 接触置信度 left/right
若 has_left_hand  : [21 × 3] float32 左手关键点（归一化到手部包围盒）
若 has_right_hand : [21 × 3] float32 右手关键点
```

**尺寸预算**：`12 + 204 + 8 + 4 + 8 = 236 B`（无手）/ `236 + 504 = 740 B`（双手）。
30 fps → **7.1 / 22.2 KB/s**，一节课 10 分钟约 **4–13 MB**。完全可接受。

**丢包/乱序**：`seq` 单调，服务端丢弃 `seq` 回退的帧；允许丢帧但**不允许丢事件**（事件走 JSON 通道）。
**背压**：客户端 `WebSocket.bufferedAmount > 256KB` 时降采样至 15Hz 并上报 `flags` 中的降级位。

**下行消息（JSON）**：
```json
{"type":"score","t":12345,"total":86.4,"pose":91.2,"rhythm":80.5,"dynamics":88.0,"fluency":85.9,
 "deviations":[{"joint":"leftElbow","delta_deg":22.5},{"joint":"rightWrist","delta_deg":18.1}]}
{"type":"state","state":"running","segment_idx":7,"beat":3}
{"type":"cue","kind":"highlight","joints":["leftElbow"],"ttl_ms":1200}
{"type":"coach","text":"第 3 段手臂抬高不够，再高 15 度","severity":"warn"}
{"type":"estop_ack","t":12360}
```

> **铁律保留**：`暂停 / 停止 / 急停` **永远由客户端本地立即执行**（不等待服务端往返），服务端只做记录与广播。网络断了，舞也能停。

---

## 8. 核心引擎设计

### 8.1 姿态估计（双实现，一套语义）

| 场景 | 实现 | 位置 | 取舍 |
|---|---|---|---|
| **实时镜像/跟练** | MediaPipe Tasks Vision（`PoseLandmarker`，`numPoses=1`，`outputWorldLandmarks=true`） | 浏览器 WASM + WebGL | 延迟优先，隐私优先 |
| **视频批量建包** | `dm_core.pose.BlazePoseEstimator`（旧 `pose3d/blaze_pose.py`） | 服务端 Python（可 GPU） | 质量优先，可重试 |

**统一坐标约定（沿用旧项目已验证的映射，切勿改动）**：
`x = world.x`，`y = -world.y`（MediaPipe 的 y 轴向下），`z = world.z`（+z 朝相机，机器人面朝 +Z 直接可用）。
**统一骨架**：内部一律用 **COCO17**（`nose, left/rightEye, left/rightEar, left/rightShoulder, left/rightElbow, left/rightWrist, left/rightHip, left/rightKnee, left/rightAnkle`）；MediaPipe 33 点 → COCO17 的映射表已存在于旧内核。

**契约铁律（旧项目踩过的坑，必须在新架构中以类型强制）**：
> 任何接受"一帧位姿"的函数**只能**接收 `Pose2D | Pose3D`（关键点数组），**禁止**接收整个 `PoseEstimate` 对象。旧系统正是因为在 `_build_preview` 里把 `PoseEstimate` 当位置参数传入，导致 worker 崩溃、摄像头卡死。
> **新架构做法**：`PoseEstimate` 拆成 `PoseFrame`（`pose2d` + `pose3d` + `confidence` + `boxes`）与消费端签名分离，并用 TS 的 `Pose2D`/`Pose3D` 品牌类型（branded type）+ Python 的 `NewType` 双端锁死；回归测试 `tests/conformance/test_pose_contract.py`。

### 8.2 重定向：从"纯几何"到"物理可信"（创新点 1）

```
输入：COCO17 世界坐标（米）
  ↓ ① 基线对齐（复用旧 motion/retarget.py 的 setFromUnitVectors 逐骨对齐）
  ↓ ② 镜像不变量  —— mirror=true 时必须同时【换左右标签】且【x = -x 绕身体中线反射】
  ↓ ③ 接触检测：踝关节高度 < ε 且竖直速度 ≈ 0 → 判定脚掌接触
  ↓ ④ 脚锁定：接触脚的世界位置一帧内锁死（抑制滑步），非接触脚自由
  ↓ ⑤ 重心约束：COM 投影必须落在支撑多边形内，否则用 IK 微调髋/膝，权重可调
  ↓ ⑥ 关节限位：每关节硬软限位（软限位用惩罚项，硬限位直接裁剪）
  ↓ 输出：RetargetedSkeleton（可直接喂 three.js 骨骼）
```

> **② 是旧项目 D1 缺陷的修复点，绝不可回退**：只换左右标签而不翻转 x，会把机器人肢体驱动到身体另一侧造成穿模。已有测试 `test_normalize_frame_mirror_is_a_true_reflection` 锁定，迁移时一并带走。

**量化指标**（对比"纯几何基线"）：

| 指标 | 定义 | 目标 |
|---|---|---|
| 脚滑量 | 接触脚相邻帧水平位移累计（m/秒） | 相对基线 ↓ ≥ 90% |
| 穿地深度 | 踝/趾低于地面平面的最大深度（m） | 相对基线 ↓ ≥ 90% |
| 重心越界率 | COM 投影在多边形外的时间占比 | 相对基线 ↓ ≥ 90% |
| 关节超限次数 | 超出软限位的帧×关节数 | 相对基线 ↓ ≥ 80% |
| 视觉可信度 | 5 人盲评（1–5 分） | 显著优于基线（p<0.05） |

> **现状可复现**：`demo.html` 已经跑出基线对照 **脚滑 1.01→0.00、穿地 0.97→0.00、重心越界 31.7%→0.0%（三项 100% 降幅）**。新系统把同一算法搬到真实数据上，并补齐关节限位维度。

### 8.3 手势门控（OK 手势启动）

```
状态机：IDLE → READINESS → GESTURE_WAIT → ARMED → RUNNING → SETTLED
```

| 状态 | 进入条件 | 退出条件 | UI |
|---|---|---|---|
| `IDLE` | 进入页面 | 点击"开始" | 待机插图 + 引导文案 |
| `READINESS` | 摄像头就绪 | 全身入镜 + 亮度达标 + 焦段合适 | 实时红黄绿提示（复用旧 `multimodal/readiness.py`：`assess_readiness`） |
| `GESTURE_WAIT` | 站位通过 | **OK 手势稳定 N 帧** 或 手动开始 | 手部骨架高亮 + 进度环（提示"保持 0.6 秒"） |
| `ARMED` | 手势确认 | 4 拍倒计时结束 | 节拍器 3-2-1-GO，同时锁定首帧参考姿态 |
| `RUNNING` | 倒计时结束 | 动作包播完 / 用户停止 | 主舞台 |
| `SETTLED` | 播完或停止 | — | 结算页 |

**OK 手势判定（尺度/旋转/光照不变）**：
采用 MediaPipe Hands 21 点，判据四条件同时成立：
1. **拇指-食指指尖距离** < `0.22 × 手掌对角线`（构成圆环）；
2. **圆环闭合度**：拇指尖到食指尖连线中点，与掌心距离 < `0.3 × 掌心-食指尖距离`；
3. **其余三指伸展**：中指/无名指/小指各自"指根-指尖距离 / 掌长" > 1.35；
4. **掌心朝向相机**：以食指-小指指根与掌心的法向判定（减小侧向误判）。
配 **迟滞（hysteresis）**：连续 `N=12` 帧（≈0.4s）达标才触发，触发后 `cooldown = 2000ms`；要求**任一只手**达标即可。

**防误触的工程兜底（必须实现）**：
- 误触发率监控：把每次触发与"触发前 2s 内是否有其它手势"一起写 `session_events`，用于离线调参；
- **手动开始永远可用**：页面上的「直接开始」按钮 + 空格键，**无障碍与答辩保命**；
- 无摄像头模式：`scope=upper_body` 时允许纯手动开始。

### 8.4 四维表现力评分（创新点 2）

| 维度 | 权重 | 计算要点 | 为什么需要 |
|---|---|---|---|
| **姿态相似度** pose | 0.40 | DTW 对齐后的关节角距离（对时间弯曲鲁棒），分部位加权（手 > 臂 > 躯干 > 腿） | 回答"像不像" |
| **节奏相位** rhythm | 0.25 | 以包 BPM 建立节拍网格，计算运动能量峰与节拍点的相位差与抖动 | 回答"有没有踩点"（旧系统完全缺失） |
| **动力学** dynamics | 0.20 | 末端速度/加速度峰值比（力度）与关节活动幅度（延伸度），归一化到包元数据分布 | 回答"有没有劲/延伸" |
| **流畅度** fluency | 0.15 | 加速度抖动（jerk）倒数 + 停顿检测 | 回答"顺不顺" |

- 总分 = 加权和，映射到 0–100 与 1–5 星（星级阈值 60/72/82/90）；
- **可解释性**：每维输出"最该改的 3 个关节 + 偏差度数"，直接驱动 UI 高亮（`cue.highlight`）；
- **`scoring_version` 入库**：换算法后可复算历史（答辩被问"你改了什么"时能直接对比）。
- **验证方法**：邀请 ≥15 人录制，5 名人类评委盲评（1–5 分）→ 计算 **Spearman 秩相关**，目标 ρ > 0.7；同时做**分维消融**（去掉某维后相关性下降多少）。

### 8.5 动作包 `dmotion/2`（数据资产化）

```json
{
  "schema": "dmotion/2",
  "meta": {
    "id": "01924f...", "title": "三十秒甜酷舞", "source_kind": "upload",
    "duration_ms": 31200, "fps": 30, "frame_count": 936,
    "bpm": 128.0, "difficulty": 3, "style": "kpop",
    "scope": "full_body", "mirror_safe": true
  },
  "skeleton": { "format": "coco17", "unit": "meter", "up_axis": "y", "facing": "+z" },
  "quality": { "confidence": 0.91, "grade": "A",
               "gaps": [{"start_ms": 8200, "end_ms": 8460, "kind": "occlusion"}],
               "note": "第 8.2s 存在 0.26s 遮挡，已插值" },
  "segments": [
    { "idx": 0, "start_ms": 0, "end_ms": 3750, "beat_count": 8, "label": "intro",
      "key_angles": { "leftElbow": 92.1, "rightElbow": 88.4 } }
  ],
  "frames": [
    { "t_ms": 0,    "conf": 0.96, "k": [[0,1.72,0], [0.18,1.66,0.02], "..."],
      "contact": [1,1], "com": [0.01, 0.004] },
    { "t_ms": 33,   "conf": 0.95, "k": ["..."] }
  ]
}
```

**`quality.confidence` 的来源**（可解释的质量分级，替代"看起来还行"）：
`0.35×平均姿态置信度 + 0.25×(1−遮挡帧比例) + 0.20×(1−抖动能量) + 0.20×时间连续性`，等级阈值 `S≥0.92 / A≥0.82 / B≥0.70 / C≥0.55 / else rejected`。低于 `C` 的动作包**拒绝入库但保留可人工修复**（提示"请在光线充足、全身入镜的条件下重拍"）。

**体积控制**：30s/30fps/17 点 float32 ≈ **1.9 MB** 原始 → 量化（角度用 int16、位置用 float16）+ gzip 后 ≈ **150–250 KB**，可直接随 API 下发。

---

## 9. 场景 A 详细设计：视频 → 3D 模板 → 跟练 → 结算

### 9.1 上传与建包流水线（异步、可离开页面）

```
POST /packages/upload (multipart)
  ↓ 同步：大小/扩展名初筛 → 落盘 data/uploads/{uuid}.mp4 → 建 job → 立即返回 job_id
GET  /jobs/{id}/events (SSE)  ← 阶段化进度（前端画步骤条，不画假进度）
  ↓ [1] probe      ffprobe 探测真实容器/时长/分辨率/fps/音轨 → 校验（拒绝伪装文件）
  ↓ [2] decode     ffmpeg 抽帧（按 fps 上限 30，最长边 ≤ 960）
  ↓ [3] estimate   BlazePose world landmarks（GPU 可批处理）
  ↓ [4] repair     缺帧插值 + 遮挡段外推 + 低置信度帧剔除
  ↓ [5] smooth     单向指数平滑 + 关节限位感知（复用 motion/smoothing.py）
  ↓ [6] retarget   接触感知重定向（§8.2）→ RetargetedSkeleton 序列
  ↓ [7] segment    以 BPM 建立节拍网格 → 按 8 拍切段 → 生成 key_angles
  ↓ [8] grade      质量分级（§8.5）→ 低质直接失败并给出可执行建议
  ↓ [9] package    序列化 dmotion/2（量化 + gzip）→ assets
  ↓ [10] preview   渲染 6s 预览循环（three.js headless 截图序列 → mp4/gif）
  ↓ [11] persist   motion_packages + motion_segments + FTS 索引
  ↓ 完成：推送 job 结果（含 package_id 与质量报告）
```

**时间预算**：30s / 1080p 视频，GPU 环境 **≤ 90 秒**（目标 60 秒）；CPU 环境 ≤ 4 分钟。
**幂等**：以 `sha256` 去重——同一视频重复上传直接返回已有包（提示"已存在同源动作包"）。
**失败可恢复**：job 记录 `stage`，失败后可从该阶段重试（不必从抽帧重来）。

### 9.2 动作库与检索

- 卡片信息：缩略图（循环预览）、标题、时长、BPM、难度星级、风格标签、质量等级徽章、**我的最佳分 / 跳过的次数**；
- 多维筛选：难度、部位（全身/上半身/仅手部）、风格、时长、BPM 区间、**只显示我上传的 / 官方预设 / 公开**；
- 搜索：SQLite FTS5（`trigram` 分词，中文可用）+ 结构化过滤混合；排序：热门 / 最新 / 我跳得最好的 / 难度递增；
- **智能推荐（简单但有效）**：按"最近 5 次会话的平均分"给每个包算 `掌握度`，优先推"难度 +0.5 且掌握度 < 0.6"的包 —— 就是**最近发展区**。

### 9.3 跟练舞台（Studio）

```
┌───────────────────────────────────────────────────────────────┐
│ 顶部：动作包标题 · 节拍 128 BPM · 进度 00:12/00:31 · 暂停 急停   │
├──────────────────────────────┬────────────────────────────────┤
│ 3D 机器人示范（主视图）        │ 我的摄像头（2D 骨架叠加）         │
│ · 可换角色/皮肤（6 种）        │ · 镜像开关                       │
│ · 关节偏差实时高亮（黄→红）     │ · 站位/亮度提示                  │
│ · 地面接触环（绿=接触）        │ · 遮罩（隐私模式，只留骨架）       │
├──────────────────────────────┴────────────────────────────────┤
│ 节拍时间轴：每格 1 拍，已完成段着色（绿/黄/红），可拖动跳转        │
├───────────────────────────────────────────────────────────────┤
│ 实时四维条：姿态 91 · 节奏 80 · 动力 88 · 流畅 86 · 综合 86.4     │
└───────────────────────────────────────────────────────────────┘
```

**交互细节**：
- 慢放 `0.5× / 0.75× / 1.0×`（**改变节拍网格**而非简单插值，否则节奏分会失真）；
- 暂停后出现"逐帧"按钮（每次前进 1 拍，方便学分解动作）；
- 单段循环：在时间轴上框选一段 → 🔁 循环（**这就是"只练弱项"的入口**）；
- 键盘：`空格` 暂停/继续、`R` 重开、`M` 镜像、`Esc` 急停；
- 演示保底：无摄像头也能"跟机器人跳"（不评分，只示范），答辩不断场。

### 9.4 结算画面（Settlement）

| 区块 | 内容 |
|---|---|
| **主数字** | 总分（大号等宽数字，0–100）+ 星级（1–5，带节奏感动画）+ "刷新个人最佳"角标 |
| **四维雷达** | ECharts 雷达：姿态/节奏/动力学/流畅度；叠加"上次同包成绩"对比环 |
| **时间轴热力图** | 每秒一格，红→绿；点击任意格 → 跳到该段回放（左右对照） |
| **最佳/最差 3 段** | 左右对照回放：左=我的 2D 骨架重演，右=机器人示范；标注偏差最大的关节 |
| **教练点评** | 3 条（LLM，短 JSON，本地白名单校验；失败则用模板文案兜底） |
| **激励** | +XP、等级进度条、解锁成就弹窗、连续打卡天数 |
| **动作** | [保存报告 PNG] [生成分享卡] [只练弱项] [再来一次] [换个动作] |

**教练点评的数据契约（严格约束 LLM 输出）**：
```json
{ "summary": "整体完成度不错，节奏是短板。",
  "tips": [
    {"severity":"warn","title":"第 3 段手臂抬高不足","action":"左肘再抬高约 20°","segment_idx":2},
    {"severity":"info","title":"落点偏快","action":"第 5–6 段提前半拍准备","segment_idx":4},
    {"severity":"good","title":"躯干控制稳定","action":"保持这个核心张力","segment_idx":0}
  ] }
```
服务端收到后**逐字段校验**：`severity` 必须在枚举内、`segment_idx` 必须 < 段数、`action` 长度 ≤ 40 字且不含命令式危险词；任何不合法 → 丢弃该条并降级为模板文案。**LLM 永远不参与评分、不产生数值。**

---

## 10. 场景 B 详细设计：实时镜像 + 机器人控制中心

### 10.1 实时镜像（单人）

```
摄像头 (getUserMedia, 640×480@30 或 1280×720@30)
   ↓ requestAnimationFrame
[浏览器] PoseLandmarker.detectForVideo  (~8–14ms, WebGL delegate)
   ↓ COCO17 世界坐标（米）
[浏览器] 本地重定向（接触感知）→ three.js 骨骼 → 渲染（目标 60fps）
   ↓ 同时：特征提取 → dmf/1 二进制帧 → WSS 上行 30Hz
[服务端] 权威评分（10Hz 下行）+ 事件落库 + 状态机
   ↓ 可选：RobotDriver 下发（sim / ws_bridge / modbus / efort）
[机器人] 仿真或实体
```

**延迟预算（端到端 ≤ 120ms）**：

| 环节 | 预算 |
|---|---|
| 采集 + 姿态估计 | 40 ms |
| 特征提取 + 上行（同城） | 15 ms |
| 重定向 + 平滑缓冲 | 30 ms |
| three.js 渲染 + 合成 | 20 ms |
| 显示（60Hz） | ≤ 16 ms |
| **合计** | **≤ 121 ms** |

> 关键取舍：**渲染不等服务端**。评分是旁路（10Hz 下行），所以网络抖动只影响分数刷新，不影响机器人动作跟手。
> 平滑缓冲用"延迟补偿 + 单帧预测"（速度外推 1 帧）抵消相机与网络抖动；缓冲过小会抖，过大会拖。

**降级阶梯（每一级都必须能继续跳舞）**：
`60fps 全量 → 30fps → 720p→480p → 仅上半身（手/臂/躯干） → 仅 2D 骨架 + 评分（不出 3D） → 无摄像头（示范回放 + 手动开始）`。

### 10.2 机器人控制中心（Console）

| 模块 | 功能 |
|---|---|
| **机队总览** | 卡片式机器人列表：名称、驱动类型、在线状态（心跳超时 10s 判离线）、当前动作包、温度/负载、FPS、最近一次指令 |
| **单机详情** | 6 轴关节实时值（等宽数字 + 条形）、遥测曲线（温度/负载/延迟）、指令历史时间线 |
| **命令面板** | 播放（选包/选段/循环/慢放）、暂停、继续、停止、**急停**、回原点、（`readonly` 模式下禁用一切运动指令） |
| **分发模式** | ① **全体镜像**：一人跳，N 台机器人同步（展会/课堂教学）② **分组镜像**：每人一机（`session_id` 与 `robot_id` 绑定） |
| **安全** | 默认 `mode='drill'`（只驱动 3D 仿真，不碰实体）；`live` 需二次确认 + 责任人记录；指令白名单 + 参数范围**本地二次校验**（服务端校验 + 驱动层再校验）；急停本地优先；每条指令写 `audit_log` |
| **审计与回放** | 指令时间线可按时间回放；异常指令（越界/超时/未回执）自动标记 |

**`RobotDriver` 统一接口（可插拔，对应旧项目 EFORT/Modbus 经验）**：

```python
class RobotDriver(Protocol):
    async def connect(self, endpoint: str) -> None: ...
    async def disconnect(self) -> None: ...
    async def send_pose(self, joints: list[float], t_ms: int) -> None: ...
    async def play_package(self, payload: bytes, *, speed: float = 1.0) -> None: ...
    async def stop(self, *, estop: bool = False) -> None: ...
    async def home(self) -> None: ...
    async def telemetry(self) -> AsyncIterator[Telemetry]: ...
    @property
    def capabilities(self) -> frozenset[str]: ...
```

| 实现 | 用途 | 说明 |
|---|---|---|
| `sim` | 默认、答辩演示 | 只推 three.js 场景，零硬件风险 |
| `ws_bridge` | 真机（网关中转） | 上位机侧桥接进程，协议自定义 |
| `modbus` | 真机（直连） | TCP 502，FLOAT CDAB，`slave=1`，关节寄存器块（沿用既有经验） |
| `efort` | 埃夫特控制器 | 复用 EFORT 侧既有服务程序与 RPL 生成经验 |

> **安全红线**：`capabilities` 决定命令面板显示哪些按钮——**不支持的绝不下发**；`mode='readonly'` 时 `play/pause/stop/home/set_pose` 全部禁用，只保留遥测。这是"只读，绝不移动机器人"的工程化落地。

---

## 11. 前端设计系统

### 11.1 设计令牌（唯一真源，禁止硬编码颜色）

```ts
// apps/web/src/design/tokens.ts —— 与 tokens.css 的 CSS 变量一一对应
export const tokens = {
  color: {
    bg:      { light: '#F7F8FA', dark: '#0D0F11' },
    surface: { light: '#FFFFFF', dark: '#16191C' },
    surface2:{ light: '#F1F3F5', dark: '#1D2126' },
    border:  { light: 'rgba(16,24,40,.08)', dark: 'rgba(255,255,255,.08)' },
    text:    { light: '#101828', dark: '#E9ECEF' },
    muted:   { light: '#667085', dark: '#98A0A6' },
    accent:  { light: '#0F9D6E', dark: '#34D399' },   // 主强调（对/成功）
    warn:    { light: '#B45309', dark: '#F5A524' },   // 警告（偏差）
    danger:  { light: '#B42318', dark: '#F97362' },   // 错误/急停
    info:    { light: '#175CD3', dark: '#6EA8FE' },
  },
  radius: { sm: 8, md: 10, lg: 14, pill: 999 },
  space:  [0, 4, 8, 12, 16, 24, 32, 48, 64],           // 8pt 网格
  motion: { fast: 160, base: 200, slow: 240 },          // ms，ease-out
  font:   { cjk: '"PingFang SC","Microsoft YaHei",system-ui', mono: '"JetBrains Mono",Consolas,monospace' },
} as const;
```

- **双主题**（深色为默认，答辩投屏/教室亮环境可切浅色）；切换只改 `data-theme`，组件零改动；
- 数字一律用**等宽字体**（分数、BPM、关节角、计时），避免跳动；
- 动效只做**位移/透明度/进度**（160–240ms ease-out）；**禁止**旋转翻转等花活（用户明确反感）。

### 11.2 组件清单（关键）

`StageView`（three.js 舞台容器 + 生命周期）· `CameraDock`（摄像头 + 2D 骨架 canvas）· `MetricsPanel`（四维条）· `ScoreRadar` · `BeatTimeline`（可拖动 + 段落着色）· `GestureGateOverlay`（手部骨架 + 进度环）· `CountdownOverlay`（节拍器）· `SettlementCard` · `PackageCard` · `JobProgressSteps`（SSE 阶段条）· `RobotTile` · `CommandPanel` · `JointReadout` · `Toaster`。

### 11.3 页面路由

| 路由 | 页面 | 权限 |
|---|---|---|
| `/` | 首页（价值主张 + 两个入口 + 我的最近训练） | 公开 |
| `/login` | 登录/注册 | 公开 |
| `/library` | 动作库（检索/筛选/上传） | 登录 |
| `/library/:id` | 动作包详情（预览 + 分段 + 我的最佳） | 登录 |
| `/studio/:sessionId` | 跟练舞台（含门控与倒计时） | 登录 |
| `/mirror` | 实时镜像 | 登录 |
| `/console` | 机器人控制中心 | 登录（管理类） |
| `/report/:sessionId` | 结算/报告 | **owner** |
| `/profile` | 我的（进度/成就/历史/设置） | 登录 |

---

## 12. 异步任务与作业队列

- **模型**：DB 表 `jobs` 做持久队列（重启不丢），内存 `asyncio.Queue` 做调度触发；
- **两档并发**：
  - `io_slots = 4`（ffprobe/ffmpeg 抽帧、预览渲染，IO 密集）；
  - `gpu_slots = 1`（姿态估计，`mp.ProcessPoolExecutor`，避免 GIL 与显存争抢）；
- **优先级**：交互型（`rebuild_preview`）> 上传建包 > 批量导出；
- **进度上报**：每阶段写 `jobs.stage/progress` → SSE 推送（前端步骤条不是假动画）；
- **取消**：协作式——每个阶段入口检查 `jobs.state == 'canceled'`；ffmpeg 子进程支持终止；
- **重试**：最多 2 次，指数退避；`stage` 粒度重试（从失败阶段继续，不从头抽帧）；
- **清理**：`rejected`/`failed` 的视频按 24h TTL 清理；孤儿 asset 每日巡检。

---

## 13. 安全、隐私与合规

| 项 | 措施 |
|---|---|
| 认证 | JWT access 15min + refresh 14d **轮换**（旧的立即失效）；密码 argon2id |
| **越权（IDOR）** | **统一依赖 `require_owner(resource, user)`，所有 `{id}` 接口强制走 owner 校验**；导出"越权测试用例清单"（读写删 × 他人资源）作为 CI 必过项 —— 这是同类项目最常见的翻车点 |
| 上传安全 | ffprobe 校验真实容器类型、时长/分辨率/大小上限、拒绝可执行与伪装文件、文件名一律服务端重命名 |
| 注入 | 全量 SQLAlchemy 参数化；FTS 查询单独转义 |
| 限流 | 登录 5 次/分钟/IP；上传 10 次/小时/用户；WS 连接数/用户上限 |
| CORS/CSP | 白名单来源；`default-src 'self'`，`script-src 'self'`（three.js 本地化，无需 CDN 白名单） |
| **隐私（核心优势）** | 实时链路**视频帧不出浏览器**，只上行数值特征；提供"遮罩模式"（只保留骨架，不显示画面）；一键清空我的全部会话与视频 |
| 数据最小化 | 全量逐帧数据默认只留本地/临时（`session_frames` 抽稀 5Hz 入库）；原始视频可配置保留期（默认 7 天自动清理） |
| LLM | 只上传**结构化统计**（不传视频、不传人脸图像）；输出强制 JSON + 本地校验；Key 只从环境变量读取，不落库不落日志 |
| 审计 | 机器人指令、动作包公开/删除、登录异常全部写 `audit_log` |

---

## 14. 可观测性与测试策略

### 14.1 观测
- 结构化日志（`structlog`）：`trace_id` 贯穿 REST/SSE/WS；
- 指标：API p50/p95 延迟、WS 帧率/丢帧率、姿态估计耗时、重定向耗时、渲染帧率、任务阶段耗时；
- 前端埋点（自建轻量）：门控触发成功率、误触发、卡顿（`longtask`）、降级档位分布。

### 14.2 测试金字塔

| 层 | 工具 | 覆盖 |
|---|---|---|
| 内核单测 | pytest | 重定向不变量（镜像反射、脚锁定、限位）、平滑、特征、DTW、动作包序列化往返 |
| 契约测试 | pytest + Pydantic | 所有 schema 快照；生成 TS 产物与仓库一致（CI `git diff --exit-code`） |
| **跨语言一致性** | pytest + vitest **共用夹具** | `tests/conformance/fixtures/*.json`：同一输入（关键点序列）在 Python 与 TS 两侧算出特征/手势/评分，断言误差 < 1e-4 |
| API 集成 | pytest + `httpx.ASGITransport` | 全路由 + **越权矩阵** + 限流 + 错误体一致性 |
| 端到端 | Playwright | 上传→建包→门控→跟练→结算；用 `--use-fake-device-for-media-stream` 注入合成视频跑通实时链路 |
| 性能回归 | 自建脚本 | 帧预算（估姿/重定向/渲染）、上传流水线总时长、WS 带宽 |

---

## 15. 部署与"答辩保底"

| 模式 | 说明 | 用途 |
|---|---|---|
| **离线一键启动** ⭐ | `start.ps1`：拉起 uvicorn + 托管构建好的前端静态文件（同源，无 CORS）→ 打开 `http://127.0.0.1:8000`，**全程无外网依赖**（three.js/字体/WASM/模型全部本地） | **答辩现场保底，断网也能演** |
| 开发模式 | Vite dev server + uvicorn `--reload`，Vite 代理 `/api` 与 `/ws` | 日常开发 |
| 容器化 | 多阶段 Dockerfile（node 构建 → python 运行），SQLite 挂卷 | 可选，加分项 |
| 公网演示 | 单机部署 + 反向代理（WSS 必须）；如需 HTTPS 摄像头权限 | 线上演示 |

**健康自检**：`/health` + 前端启动自检页（检查：后端可达、DB 可写、媒体目录可写、WASM 资源可用、WebGL 可用、摄像头可用），**答辩前一条命令出全绿报告**。

---

## 16. 里程碑与排期（10 周，可压缩至 7 周）

| 里程碑 | 周期 | 交付物（可验收） | 完成判据 |
|---|---|---|---|
| **M0 地基** | 1w | monorepo、contracts→TS 代码生成、SQLite+Alembic 首迁、认证、设计令牌、CI | `verify.ps1` 全绿；登录后能拿到 `/me` |
| **M1 动作包流水线** | 1.5w | 上传→SSE 进度→dmotion/2→质量分级→库检索→预览 | 上传 30s 视频 ≤ 90s 出包；FTS 中文可搜 |
| **M2 3D 舞台与跟练** | 1.5w | three.js 舞台、骨骼驱动、节拍时间轴、慢放/循环/镜像 | 本地预设包可完整跟练；镜像不变量测试通过 |
| **M3 门控与结算** | 1w | OK 手势门控状态机、倒计时、实时评分下行、结算页（雷达/热力/回放） | 门控成功率 >95%、误触发 <1 次/5min；结算页四区块全通 |
| **M4 实时镜像与控制中心** | 1.5w | 浏览器端估姿、dmf/1 上行、权威评分、控制中心、`sim` 驱动 | 端到端 ≤ 120ms；两档降级可演示 |
| **M5 教练与闭环** | 1w | 四维评分、LLM 短 JSON + 校验、报告、只练弱项、错题本 | 评分与人工 ρ>0.7；弱项复训分数提升可复现 |
| **M6 实验与打磨** | 1w | 消融实验、性能回归、无障碍、移动端布局、护眼色温 | 指标图表齐备；移动端可用 |
| **M7 交付** | 1w | 离线一键启动、部署脚本、论文素材、演示彩排 | 断网一键启动成功；彩排 3 次无事故 |

**关键顺序**（不要跳步）：**M0 → M1（先出数据）→ M2（再出画面）→ M3（再出门控与结算）→ M4（最后上实时）**。
理由：M1 的动作包是后面一切的地基（也是论文里最重要的"数据资产"），先做能立刻验证流水线；M4 的实时链路风险最高（估姿性能/浏览器兼容），放到架构稳定后再攻。

---

## 17. 验收标准（量化）

| 类别 | 指标 | 目标 |
|---|---|---|
| 建包 | 30s/1080p → 动作包 | ≤ 90s（GPU） |
| 实时 | 端到端延迟（动作→3D 机器人动） | ≤ 120ms |
| 实时 | 渲染帧率 | ≥ 55fps @ 95 分位（目标 60fps） |
| 实时 | 上行带宽 | ≤ 25 KB/s |
| 门控 | OK 手势成功率 / 误触发 | > 95% / < 1 次每 5 分钟 |
| 评分 | 与人工盲评 Spearman ρ | > 0.70 |
| 重定向 | 脚滑/穿地/重心越界 相对纯几何基线 | ↓ ≥ 90%（现有 demo 已达 100%） |
| 重定向 | 关节超限次数 | ↓ ≥ 80% |
| API | p95 延迟（不含重任务） | ≤ 120ms |
| 安全 | 越权测试用例 | 100% 拦截 |
| 质量 | 测试覆盖（core/contracts） | 语句覆盖 ≥ 85% |

---

## 18. 创新点与叙事（毕设 / 竞赛双用）

| # | 创新点 | 层级 | 痛点 | 你的方法 | 可量化 |
|---|---|---|---|---|---|
| **1** ★ | **接触感知的物理可信重定向** | 方法 | 纯几何对齐 → 脚滑/穿地/悬空/穿模 | 接触检测 → 脚锁定 → 重心约束 → 关节限位 | 脚滑/穿地/越界 ↓≥90%，盲评显著提升 |
| **2** ★ | **四维表现力评估** | 方法 | 只说"像不像"，说不出"为何没感觉" | 姿态 + 节奏相位 + 动力学 + 流畅度 | 与人工 ρ>0.7 + 分维消融 |
| **3** ★ | **手势门控的沉浸式启动** | 场景 | 点击开始 → 割裂感强 | 站位就绪校验 + OK 手势 + 节拍倒计时，多重防误触 | 成功率/误触发率 + 启动耗时 |
| **4** ★ | **端云协同的隐私实时引擎** | 架构 | 视频上云 → 带宽/延迟/隐私三重问题 | 客户端估姿 + 特征帧上行 + 服务端权威评分 | 带宽 ↓ 百倍、延迟 ≤120ms、视频零出机 |
| **5** | **差异驱动的自动示范与复训闭环** | 场景 | 只告诉你错，不教你改 | 分段慢放 + 高亮差异关节 + LLM 讲解 + 弱项自动组卷 | 复训前后分数提升曲线 |

**一句话答辩稿**：
> 我们做的不是"读个视频播一下"，而是**把任意真人舞蹈视频变成物理可信、可跟练、可评分、可复训的 3D 动作资产**；核心贡献是**接触感知重定向**与**四维表现力评估**两个方法，以及一条**视频永不出本机**的端云协同实时链路。

---

## 19. 风险登记册

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 浏览器端估姿性能不足（低端机 <20fps） | 中 | 高 | 降分辨率/降帧 + 服务端估姿兜底开关；降级阶梯 6 档 |
| 摄像头手部精度不足导致门控失败 | 中 | 高 | 手势门槛双档（宽/严）+ **手动开始永远可用**；提示走近 |
| 重写范围失控 | 中 | 高 | 内核复用不重写；契约先行；**每周必须有一个可运行增量** |
| SQLite 并发写瓶颈 | 低 | 中 | WAL + 写操作串行化（单写队列）；SQLAlchemy 抽象保留迁 Postgres 能力 |
| LLM 输出不稳定/延迟高 | 中 | 中 | 短 JSON + 本地校验 + 模板兜底；异步生成不阻塞结算页首屏 |
| 真实机器人安全 | 低 | 极高 | 默认 `drill` 只驱动仿真；指令白名单 + 双层校验；急停本地优先 + 硬件回路 |
| 数据合规（视频/人脸） | 低 | 高 | 视频本地处理、最小化留存、可一键清除、不上传图像给 LLM |
| 答辩现场网络故障 | 中 | 高 | 离线一键启动 + 本地资源全量内嵌 + 彩排 3 次 |

---

## 20. 附录 A：旧 → 新 迁移映射表

| 旧模块（`src/dance_mirror/`） | 新归属 | 处置 |
|---|---|---|
| `pose3d/blaze_pose.py` `pose3d/registry.py` | `packages/core/dm_core/pose/` | 迁移 + 补测 |
| `pose2d/yolo_pose.py` | `packages/core/dm_core/pose/yolo.py` | 迁移动备用后端 |
| `motion/retarget.py` `normalization.py` | `dm_core/retarget/` | 迁移，**新增接触/平衡/限位** |
| `motion/smoothing.py` `sync.py` `alignment.py` | `dm_core/filters/` | 迁移 |
| `motion/features.py` `hand_features.py` `comparison.py` `comparison_space.py` | `dm_core/features/` | 迁移 + 新增节奏相位/动力学 |
| `multimodal/gesture.py` | `dm_core/gesture/` + `packages/motion-js/gesture.ts` | 迁移并双实现（一致性夹具锁定） |
| `multimodal/readiness.py` `preview.py` `face.py` | `dm_core/readiness/` `dm_core/preview/` | 迁移（face 仅用于"是否有人"，不做身份识别） |
| `storage/motion_package.py` `motion_library.py` | `dm_core/package/`（`dmotion/2`） | **Schema 升级 + 量化压缩** |
| `storage/database.py` | `apps/api/app/db/` | 重写（SQLAlchemy 2.0 + Alembic） |
| `services/analytics.py` `progression.py` `performance.py` `report.py` `reference.py` | `apps/api/app/services/` | 重构为服务层 |
| `coaching/*` | `apps/api/app/services/coach.py` | 重构：短 JSON + 本地校验 + 模板兜底 |
| `command/*` | `apps/api/app/services/`（意图解析）+ 前端快捷键 | 重构 |
| `renderer/three_scene.py` `render_bridge.py` `character_catalog.py` | `apps/web/src/render/` + `assets/characters/` | 重写为 TS 渲染层 |
| `renderer/resources/*.js` `dance_robot_cyber.glb` | `apps/web/public/` `assets/characters/` | 直接复用（已验证本地化可离线） |
| `view/**`（全部 PyQt6 界面） | — | **丢弃** |
| `workers/**`（QThread 封装） | — | **丢弃**（改用 API 异步任务 + 前端帧循环） |
| `config.py` `logging_setup.py` `errors.py` | `apps/api/app/settings.py` | 重构（Pydantic Settings + 环境变量） |
| `demo.html`（物理可信对照演示） | `apps/web/src/pages/_lab/` | **保留为"实验对照页"**——答辩时用来展示基线 vs 接触感知的指标对比，是创新点 1 的现成证据 |

## 21. 附录 B：`dmotion/2` 与旧格式差异

| 项 | `dmotion/1`（旧） | `dmotion/2`（新） |
|---|---|---|
| 元数据 | 基础（时长/BPM/难度） | **+ style / scope / mirror_safe / quality.grade** |
| 分段 | 无 | **按节拍切段 + 代表性关节角（驱动弱项复训与高亮）** |
| 质量 | 单一 `score_confidence` | **可解释四因子 + 缺口标注 + 等级阈值** |
| 数值 | float32 原样 | **量化（int16 角 + float16 位置）+ gzip**，体积 ↓ ~90% |
| 接触信息 | 无 | **每帧 `contact[2]` + `com[2]`**（接触感知重定向的产物，也是评分依据） |
| 版本 | 无显式 | **`schema` 字段 + 迁移脚本**（老包可自动升级） |

---

## 附：本方案的取舍一览（写在最前面，也放在最后）

| 决策 | 选择 | 一句话理由 |
|---|---|---|
| 前端栈 | Vue 3 + Vite + TS | 换掉 QWebEngine 这个死路，且 B/S 可分享 |
| 后端 | FastAPI + SQLAlchemy 2.0 | 异步、类型契约天然、与算法内核同语言 |
| DB | SQLite(WAL) | 单机零运维，答辩友好；抽象保留升级空间 |
| 估姿位置 | 实时在浏览器、建包在服务端 | 延迟与隐私 vs 质量与吞吐，各取所需 |
| 评分位置 | **服务端权威** | 防篡改、可复算、避免两套实现漂移 |
| 算法内核 | **复用不重写** | 已验证的数学重写=白扔 2–3 周 + 引入回归 |
| 旧 UI/Worker | **全部丢弃** | 换栈后零价值，是技术债本体 |
| 演示保底 | 离线一键启动 + 手动开始 + 降级 6 档 | 答辩不能赌网络和摄像头 |
