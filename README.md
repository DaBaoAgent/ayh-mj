# ayh-mj — 轻便侠 · AI 视频工厂（vNext）

**电动轮椅软广短视频全自动生产**：「单条多镜」one-take 工艺 —— 一次 H3 调用生成整条 15 秒（含全部镜头切换 + 双音色对口型），后期烧字幕 / BGM / 音效，出抖音成片。

> **唯一执行入口是 Orchestrator**：`python tools/orchestrate.py`。
> 任何"绕过编排器、手工跑某个脚本出片"的用法都是人工应急通道，不是产线。
> 旧入口 `tools/run_all.py` 已声明废弃（运行会打印 `[deprecated]`）。

> **唯一事实源**：
> - 任务与状态 → SQLite `state/pipeline.db`（JobStore）
> - 配置 → `config/default.yaml`（环境变量 `AYHMJ_<SECTION>__<KEY>` 覆盖）
> - 产品事实/卖点 → `assets/products/claims.yaml`（Claims Registry）
> - 台词规范 → `docs/执行标准-20260925.md`

---

## 一分钟看懂

| 维度 | 现行方案 |
|---|---|
| 编排 | `tools/orchestrate.py`（Plan → Preflight → Generate → QA → Compose → Package） |
| 规划 | `lib/creative/planner.py` 自主补齐 `daily_target`，不依赖人工预放 queue spec |
| 工艺 | one-take：一次 H3 生成整条 15 秒（4 镜 + 对口型） |
| 组合 | 四池智能组合：角色组 100 人 × 卖点 20 × 角度 50 × 片型 10，保新优先 |
| 提示词 | 官方 Ref2VA 六段式，编译进 StorySpec 后存 job artifact |
| 合规 | 出片前 Claims Gate（数值/认证/疗效/绝对化必须映射到可用 claim） |
| 验片 | QA 识别错嘴 / 产品形变 / ASR 漏词 / 字幕失败 → RepairEngine 定点修复 |
| 字幕 | 新青年体 · 不加粗 · 无标点 · 关键词黄字高亮 + 弹跳 |
| BGM/音效 | AudioDirector（确定性选曲，可解释 rationale）+ SFX policy |
| 发布 | Packaging artifact + 发布 Gate（配额 / 时段 / auth / AI 声明 / claims） |
| 成本 | ≈ ¥1.0 / 条（H3 ¥0.9 + 校验/杂项） |

---

## 1. 安装（fresh clone 三步）

```bash
git clone <repo> ayh-mj && cd ayh-mj

# ① 建 venv 并装依赖（uv 为推荐，pip 等价）
uv venv .venv
uv pip install -r requirements.txt          # 或：pip install -e ".[dev]"

# ② 配置密钥（二选一，二者都不进仓库）
cp .env.example .env                        # 填 AUTODL_API_KEY / DEEPSEEK_API_KEY ...
#   或把 key 放进系统凭据库 keyring

# ③ 一键体检（顺带补齐 venv/依赖）
python tools/bootstrap.py
```

可选依赖按需装：`pip install -e ".[asr]"`（本地转写 faster-whisper）、`.[metrics]`、`.[learn]`。
**缺可选依赖不会让仓库起不来**，只会让 health check 报 DEGRADED。

## 2. Health check：先看能不能跑

```bash
python tools/health_check.py          # 人类可读
python tools/bootstrap.py --json      # 机器可读（CI/Hermes 用）
```

退出码：`READY=0`，`DEGRADED=0`（能跑但能力有缺），`BLOCKED=1`。

| 状态 | 含义 | 处置 |
|---|---|---|
| `READY` | 必需项与可选项全部就绪 | 直接生产 |
| `DEGRADED` | 必需项齐、可选项缺（如未装 whisper / 未登录抖音 / 缺 PostFlow） | 可生产，但相关能力会跳过或转人工；报告里每项都带 `修复：` 提示 |
| `BLOCKED` | 必需项缺（python / ffmpeg / db 写不了） | 先按提示修复，任何 stage 都不会硬闯 |

典型输出（本机）：

```text
🏥 ayh-mj 能力体检 ｜ 总状态 △ DEGRADED
  ✓ python    [必需] 3.12.9
  ✓ ffmpeg    [必需] .../ffmpeg.exe
  △ whisper   [可选] faster_whisper 未安装：转写/字级字幕不可用
      ↳ 修复：uv pip install faster-whisper（或 pip install -e '.[asr]'）
  △ douyin_profile [可选] 登录态目录不存在或为空
      ↳ 修复：python s1_trend/browser.py --login 扫码
DEGRADED｜阻塞 0 项 / 降级 3 项
```

## 3. 启动

### CLI（生产主链）

```bash
python tools/orchestrate.py start                      # 按 daily_target 创建并执行（阻塞）
python tools/orchestrate.py start --count 5            # 覆盖 daily_target
python tools/orchestrate.py start --goal "国庆出游场景"  # 指定选题
python tools/orchestrate.py start --dry                # 演练：不出片、不花钱、不发布
python tools/orchestrate.py status                     # 编排器 + 任务概览
python tools/orchestrate.py status --uid J20260930xxxx # 单条详情
```

### WebUI（控制台）

```bash
python -m uvicorn webui.server:app --host 127.0.0.1 --port 8899
# 浏览器打开 http://127.0.0.1:8899
```

控制台的"目标条数 / 并发 / 演练 / 真实发布 / 真实互动 / 发布平台"写进 `state/console.json`，
**与 CLI、Hermes 共用同一份用户意图** —— 三个入口读到的运行时配置结构完全一致。

> ⛔ 不要 `taskkill` 杀 `server.py`（会自断 Hermes 命令通道）。重启用 `POST /api/restart`。

## 4. 创建目标

- **自动补齐**：`daily_target`（WebUI 设置；默认 1）减去"今日已存在/已完成"就是本轮要新规划的数量。
  队列为空时 Planner 会自主生成，不需要人工预放 spec。
- **指定选题**：`--goal "<一句话>"`。
- **指定 spec**：`--spec state/queue_15s/<uid>.json`（只跑这一条，用于复现/调试）。
- **绕过门禁**：`--force`（跳过门禁自检，仅用于排障，别用在产线）。

## 5. 观察与恢复

| 场景 | 命令 |
|---|---|
| 看整体 | `python tools/orchestrate.py status` |
| 看单条 | `python tools/orchestrate.py status --uid <uid>` |
| 进程崩溃/断电后收敛 | `python tools/orchestrate.py recover`（把遗留"运行中"收敛为 `PAUSED`） |
| 从断点继续 | `python tools/orchestrate.py resume --uid <uid>` |
| 重试失败/受阻 | `python tools/orchestrate.py retry --uid <uid>` |
| 协作式取消 | `python tools/orchestrate.py cancel --uid <uid>`（或 `--all`） |

**幂等保证**：每个 stage 产物已存在就跳过；供应商提交前先落 `provider_tasks`（fingerprint 唯一），
崩溃重启后按 fingerprint 只 **query** 原 task，**绝不重复 create_task**（不重复扣费）。
`recover` 不创造新任务，只把状态收敛到可解释的静止态。

## 6. 人工阻断（哪些情况会停下来等人）

编排器**不会硬闯**，会停在明确的状态并给出原因：

| 状态 | 触发 | 人工动作 |
|---|---|---|
| `BLOCKED` | Claims Gate 不通过 / 修复次数达上限 / 预算超限 | 看 `status` 的 `error_code` 与事件流，改文案或调预算后 `retry` |
| `PAUSED` | 进程重启时任务正在跑（`recover` 收敛） | `resume` |
| `FAILED` | 不可恢复错误（如 PROVIDER_REJECTED） | 修因后 `retry` |
| `REQUIRE_HUMAN`（事件） | 平台验证码 / 账号风控 / 自动评论命中价格·医疗·投诉红线 | 人工在 WebUI 处理，**不做绕过** |
| `DEGRADED`（环境） | 缺字体 / 缺 ffmpeg / 缺 Upload-Post key | 按 health check 提示补齐 |

`CANCELLED` 是协作式取消：先置取消标记，再按**进程树**安全终止子进程，**不留孤儿进程**。

## 7. 发布安全（默认永真发）

```yaml
# config/default.yaml
publish:
  ai_generated: true
  ai_disclosure_confirmable: {}   # 默认"每个平台都没确认" → 只能传草稿；无草稿通道的平台转人工
```

- `real_publish=false`（默认）时，**任何路径都不会真发**社媒。
- `real_publish=true` 也必须依次通过：**quota（日限/最小间隔） → time window（发布窗口/夜间静默） → auth →
  AI disclosure → claims → artifact 完整性**。
- 平台 auth 异常触发**熔断**，不会循环登录或连续发布。
- 同一 `post.external_id` 幂等：同一 job 重试不重复发帖。
- 自动评论命中价格/医疗/投诉红线 → 转人工。

## 8. 测试方法

```bash
python tools/ci.py                 # 一条命令跑完所有非 live / 非 paid 检查
python tools/ci.py --skip-frontend  # 无浏览器环境
python tools/ci.py --list           # 只列步骤
```

| 顺序 | 步骤 | 内容 |
|---|---|---|
| 1 | `lint` | `ruff check lib tests tools webui s6_publish s7_learn` |
| 2 | `typecheck` | `compileall`（能用"能不能编译"当语法闸门） |
| 3 | `unit` | 纯逻辑单测 + marker 纪律检查（每条 `tests/unit` 用例必须带 `unit` marker） |
| 4 | `contract` | 第三方响应契约 fixture（DeepSeek / AutoDL / Upload-Post / PostFlow） |
| 5 | `integration` | fake provider 驱动的多模块流程（含 Planner 到 READY 的主链） |
| 6 | `frontend` | Playwright WebUI 冒烟（可 `--skip-frontend`） |
| 7 | `migration` | 数据库迁移测试 |

分层单跑：

```bash
python -m pytest tests/unit -q          # unit
python -m pytest tests/contract -q      # contract
python -m pytest tests/integration -q   # integration
python -m pytest tests/frontend -q      # frontend
python -m pytest -m "not live and not paid" -q   # 全量（排除真花钱/真联网）
```

**硬约束**：

- `live`（要真实网络或账号）与 `paid`（真花钱）**默认永不执行**，必须显式
  `AYHMJ_RUN_LIVE=1` / `AYHMJ_RUN_PAID=1`；`tools/ci.py` 与 CI 会强制清空这两个变量。
- 自动测试对 AutoDL 的付费提交有硬约束：任何一次真实提交都会直接 `AssertionError`（FakeEnv 计数为 1 的显式断言除外）。
- 契约 fixture 在 `tests/fixtures/contracts/`（`ok/` 是真实形状，`broken/` 是反例）；被改坏会**点名到字段**。
- Golden 样本在 `tests/golden/creative/`：只冻结输入（稳定 StorySpec / CreativeDNA），断言关键结构与 hard constraints。
- 废弃事实源回归在 `tests/unit/test_legacy_fact_sources.py`：`pipeline.yaml` 不得再被当路径读、音频选曲不得回到 `random`、
  `_deprecated_*` 不得被 import。

CI 配置见 `.github/workflows/ci.yml`，PR 未全绿禁止合并。

## 9. 目录结构

```text
ayh-mj/
├── config/default.yaml      # ★ 唯一权威非敏感配置（Phase 14 起无兜底文件）
├── lib/                     # 领域逻辑
│   ├── jobstore.py          #   ★ JobStore：唯一事实源（状态机 + 事件 + artifact）
│   ├── migrations.py        #   schema 版本化迁移（当前 v4）
│   ├── orchestrator/        #   ★ 编排内核（service / stages / policies / recovery）
│   ├── creative/            #   CreativeDNA / StorySpec / Planner / Compiler / Router / Prescreen
│   ├── qa/                  #   验片与缺陷分类
│   ├── post/                #   AudioDirector / SFX / Loudness / canonical transcript
│   ├── packaging/           #   标题 / 描述 / claim ids / AI disclosure
│   ├── safety/              #   发布 Gate / 互动风控 / 熔断
│   ├── claims.py            #   Claims Registry（唯一产品事实来源）
│   └── settings.py          #   配置装载（default.yaml + 环境变量）
├── s1_trend/ … s7_learn/    # 七个产线模块（被编排器调用）
├── tools/                   # 入口与工具（清单见 tools/README.md）
├── webui/                   # FastAPI 控制台（默认 127.0.0.1:8899）
├── assets/                  # cast / products / bgm_trending / sfx / templates
├── state/                   # 运行状态（不进 git）：pipeline.db / queue_15s / console.json
├── out/                     # 成片输出（不进 git）：out/approved/ 为已验收
├── tests/                   # unit / contract / integration / frontend + fixtures + golden
├── docs/                    # 规范、验收证据、架构与运维文档
└── _deprecated_20260925/    # ⛔ 老管线归档（勿用；不参与 lint / pytest / import）
```

## 10. 核心资产

| 资产 | 路径 | 规模 |
|---|---|---|
| 角色图 | `assets/cast/library/` + `roles.yaml` | 照片级角色库（城市/欧美/时尚等组） |
| 音色库 | `assets/cast/voice/real/` + `docs/音色-角色映射表-20260925.md` | 真人音色样本 |
| 产品图 | `assets/products/` | 三视图（展开态必给三张） |
| 产品事实 | `assets/products/claims.yaml` | Claims Registry（数值/认证/质保/疗效口径） |
| BGM 库 | `assets/bgm_trending/` + `INDEX.md` | 抖音热门曲库 |
| 音效 | `assets/sfx/` | 自动插入音效 |
| 字体 | `lib.tools.font_dir()` 解析（默认 `assets/fonts`，可设 `AYHMJ_FONTS_DIR`） | 新青年体等 |

## 11. 成本参考

| 项 | 单价 |
|---|---|
| H3 出片 768p | ¥0.06/秒（15s ≈ ¥0.9/条） |
| 快测 480p | ¥0.04/秒（5s ≈ ¥0.2） |
| 预设筛（prescreen） | 约为正式生成的 1/3（仅高风险构图触发） |
| **单条成片合计** | **约 ¥1.0** |

每条 job 都在 DB 里记 `cost_estimate / cost_spent / budget_cap`；超 `budget_cap` 立即 `BLOCKED_BUDGET`。

## 12. 更多文档

- [`docs/architecture/vnext.md`](docs/architecture/vnext.md) — vNext 架构、数据库 ER、状态机
- [`docs/architecture/current_pipeline.md`](docs/architecture/current_pipeline.md) — Phase 0 改造前基线快照
- [`docs/operations.md`](docs/operations.md) — 常见故障与恢复流程
- [`docs/creative_system.md`](docs/creative_system.md) — CreativeDNA / StorySpec / QA / Repair / Learner
- [`tools/README.md`](tools/README.md) — tools/ 脚本分类
- [`docs/codex_final_acceptance.md`](docs/codex_final_acceptance.md) — 最终验收报告

## 历史

- 2026-09-23：四池体系定型，模板链路停用
- 2026-09-24：one-take 工艺首条（后备箱魔术）
- 2026-09-25：真人音色库 / 照片级角色图 / BGM 库 / 官方 Ref2VA 规范 / 字幕三条规范 → 执行标准定稿 + 老管线清退
- 2026-09-30：Phase 0–15 重构为 vNext（JobStore 唯一事实源 / Orchestrator 唯一入口 / 恢复与幂等 / 合规与发布 Gate）

## License

MIT
