# ayh-mj — Codex 完整迭代开发与验收计划

> 仓库：`DaBaoAgent/ayh-mj`
> 基线：`master` / `61349e88204081978c452dcb6c830ad1972a5453`
> 日期：2026-09-30
> 执行者：Codex
> 目标：把现有 one-take 视频工具链升级为可自主规划、可恢复、可自修复、可验收、可发布、可学习的 AI 短视频生产系统。

---

## 0. Codex 执行总规则

本文档不是建议清单，而是开发执行规范。Codex 必须严格按 Phase 顺序实施，不得跨阶段大改。
每个 Phase 必须独立完成：代码修改、测试、真实或演练 smoke test、文档更新、Git commit、验收记录。
上一阶段未达到 Acceptance Criteria，不得进入下一阶段。
禁止为了“顺手优化”重写与当前阶段无关模块；禁止一次性重构整个仓库；禁止无测试地直接修改生产主链。

### 0.1 Git 工作方式

1. 从当前 `master` 基线创建独立开发分支：`codex/ayh-mj-vNext`。
2. 禁止 Codex 直接向 `master` 提交。
3. 每个 Phase 至少一个独立 commit，格式：`phase-N: <明确成果>`。
4. 大 Phase 内可以拆子提交，但必须保持每个 commit 可运行、可回滚。
5. 每阶段结束生成 `docs/codex_phase_N_acceptance.md`，记录改动、测试、失败项、遗留项。
6. 如发现基线已变化，先 rebase/merge 并重新执行上一阶段回归测试，再继续。

### 0.2 完成定义（Definition of Done）

最终系统必须满足：
- 用户只需要给出目标，例如“今天生产 5 条”，系统即可自主完成研究、创意、脚本、生成、验片、修复、后期、包装和发布准备。
- WebUI、Hermes、CLI、Scheduler 看到同一任务、同一状态、同一配置，不允许多套事实源。
- 任一步骤失败后能够识别错误类型并执行针对性 repair，而不是简单无限 retry。
- 进程/服务/电脑中断后能够恢复，不重复提交已付费的 H3 任务。
- 片型、角色、钩子、镜头结构、音乐、音效具有结构级多样性，而不是仅换台词。
- 所有产品事实、参数、认证、售后、广告声明来自唯一 Claims Registry。
- 自动发布经过平台安全和合规 Gate；不能确认 AI 声明时只允许草稿/待人工确认。
- 发布后的表现数据进入学习层，反哺下一轮创意决策。
- fresh clone 后可以用统一 bootstrap/health check 明确能力状态并完成部署。
- 关键路径拥有 unit / integration / contract / frontend smoke / golden tests。

### 0.3 不得破坏的现有能力

Codex 必须优先复用而不是推倒：
- `tools/make_15s.py` 已跑通的 one-take 后期经验。
- `s4_generate/workflow_router.py` 的工作流能力矩阵与 fallback 思路。
- `tools/prescreen.py` 的 5 秒预筛能力。
- `lib/hellgrind.py` 的 CINEDANCE / ACTING 能力。
- `lib/ideas.py`、`lib/genres.py`、`lib/angles.py`、`lib/products.py` 的创意资产。
- `s6_publish/` 的发布、互动、限流与 Upload-Post 能力。
- `webui/hermes_bridge.py` 的 Hermes 桥接。

---

## 1. 当前关键问题（Codex 开工前必须理解）

### P0：会直接阻碍自主运行

1. WebUI 展示六阶段，但当前 one-take 主链并不真正按六阶段执行，存在“UI 有能力、执行器无能力”的错觉。
2. `pipeline.db` 与 `state/queue_15s/*.json` 不是同一事实源，WebUI 统计和真实生产队列可能不一致。
3. `daily_target / gen_concurrency / real_publish / publish_platforms / real_engage` 等设置没有完整贯穿到执行器。
4. 启动后不会自主创建创意任务，主要消费已有 spec，因此还不是自主视频工厂。
5. `make_15s.py` 多步骤串联缺少统一失败 Gate，某一步失败可能继续执行后续步骤。
6. H3 已提交 task 后缺少系统级 resume/reconcile，异常重跑可能重复花费。
7. one-take 当前没有充分使用仓库已有的智能 workflow router/fallback。
8. 通用 4 镜×8句×双人对撞骨架限制片型多样性。
9. one-take 生产 job 与 `s6_publish` 要求的 SQLite `ready` job 没有统一生命周期。
10. 发布链没有把 AI 生成内容声明设为不可绕过的合规 Gate。

### P1：严重影响质量、可维护性和部署

- `pipeline.yaml` 与现行生产逻辑存在配置漂移。
- 产品事实在不同模块存在口径不一致风险。
- 热点、短剧结构、Creative Research 与生产主链连接不足。
- ASR/字幕存在重复推理和资源浪费。
- 抽帧验片存在，但还没有成为主线自动 QA Gate。
- BGM/SFX 选择逻辑存在多套实现且模板感明显。
- 大量 Windows 绝对路径、本机 Python、字体、PostFlow、API key 路径硬编码。
- requirements 与实际运行依赖不完全一致。
- 缺少系统性的测试和 CI。

---

## 2. 最终目标架构

```text
WebUI / Hermes / CLI / Scheduler
             │
             ▼
      PipelineOrchestrator
             │
      ┌──────┴────────┐
      ▼               ▼
   Planner         JobStore
      │               │
      ▼               ▼
TrendResearch → CreativeDirector → StorySpec / CreativeDNA
                                      │
                         CINEDANCE / ACTING / Claims
                                      │
                                      ▼
                               PromptCompiler
                                      │
                           Preflight / Prescreen
                                      │
                                      ▼
                             GenerationRouter
                                      │
                                      ▼
                                  QACritic
                               ┌──────┴──────┐
                             PASS           FAIL
                               │              │
                               │        RepairEngine
                               └──────◀───────┘
                                      │
                                      ▼
                          PostProduction / Packaging
                                      │
                                      ▼
                           Compliance / Publish
                                      │
                                      ▼
                              PerformanceLearner
                                      │
                                      └──► 下一轮 Planner
```

---

# Phase 0 — 冻结基线、建立安全网

## 目标

在修改生产主链前，先让 Codex 能证明“改前什么能工作、改后没有退化”。

## 必做任务

1. 在 `D:/@kaifa/ayh-mj` 创建开发分支 `codex/ayh-mj-vNext`。
2. 记录基线环境：Python、Node、ffmpeg、ffprobe、Hermes、AutoDL key 状态、DeepSeek key 状态、Upload-Post 状态。
3. 新增 `docs/architecture/current_pipeline.md`，画出现有 WebUI → run_all → make_15s → generation → compose → publish 的真实调用链。
4. 新增 `tests/`，先覆盖不花钱的核心逻辑：
   - `lib.state`
   - `workflow_router`
   - `ideas.novelty_issue`
   - `products/angles/genres` 选择器
   - SRT 时间格式和字幕拆行
   - publish quota 判断
5. 建立 provider fake/fixture，禁止自动测试真正提交 AutoDL 付费任务。
6. 新增统一 test marker：`unit / integration / live / paid`。
7. `paid` 测试默认永远不执行，只有显式环境变量允许。
8. 运行现有 bootstrap/check_dialogue/engage demo 等无付费自检，并保存输出。
9. 对当前 WebUI 做最小 Playwright smoke：页面能打开、settings 能加载、Start/Stop API 能响应、Hermes WS 失败时 UI 不崩。
10. 生成 `docs/codex_phase_0_acceptance.md`。

## 验收标准

- `pytest` 基础测试全部通过。
- 测试过程中 AutoDL 任务提交数必须为 0。
- WebUI smoke 通过。
- 当前已知基线缺陷必须写入 acceptance 文档，不能偷偷修改后不记录。
- commit：`phase-0: freeze baseline and add regression safety net`。

---

# Phase 1 — 配置统一、依赖锁定、去硬编码

## 目标

让项目不再依赖“只有当前电脑才存在”的路径和隐式环境，建立唯一配置入口和能力探测。

## 建议新增/重构

- `lib/settings.py`：使用 Pydantic Settings 或等价强类型配置模型。
- `config/default.yaml`：非敏感默认值。
- `.env.example`：仅列变量名，不含真实 key。
- `tools/health_check.py`：输出 capability matrix。
- `pyproject.toml` + lockfile（优先 uv），把真实运行依赖完整锁定。

## 必做任务

1. 收敛 `pipeline.yaml`：旧配置字段标记 deprecated，现行配置必须只有一个权威来源。
2. 移除业务代码中的固定 `D:/@kaifa/...`、`C:/Users/...` 路径；ROOT 从仓库自身解析。
3. Python、ffmpeg、ffprobe、字体、PostFlow 通过 settings/capability discovery 获取。
4. API key 优先级统一为安全存储/环境变量，不允许业务模块各自猜不同文件位置。
5. 清理 `lib/keyfile.py` 的机器专属路径依赖；可兼容 legacy，但不得成为默认必需条件。
6. 解决 `.gitignore vendor/` 与 PostFlow“应随仓库存在”的矛盾：选择明确方案（submodule、安装步骤或独立可配置路径）。
7. `requirements.txt`/pyproject 补齐实际 import：Pillow、faster-whisper 等。
8. health check 至少输出：Python、ffmpeg、ffprobe、font、Whisper、AutoDL、DeepSeek、Douyin profile、PostFlow、Upload-Post、DB、磁盘空间。
9. WebUI `/api/state` 增加 health summary，但此阶段不要重写 UI。

## 验收标准

- 把仓库复制到不同目录后，无需改源码即可通过基础 health check。
- 缺少某能力时给出 `DEGRADED` 与明确原因，而不是 import crash。
- `pytest` 全绿，WebUI smoke 不退化。
- commit：`phase-1: unify settings dependencies and capability discovery`。

---

# Phase 2 — 统一 JobStore 与任务状态机

## 目标

彻底解决 `pipeline.db`、queue JSON、WebUI 统计、发布状态彼此不一致的问题。

## 数据模型要求

至少新增/迁移以下实体：
- `jobs`：业务任务；包含 `uid/status/goal/priority/current_stage/created_at/updated_at`。
- `attempts`：每次生成/修复尝试；包含 `job_id/stage/attempt_no/provider/model/workflow/status/error_code/cost`。
- `artifacts`：spec、prompt、原片、字幕、成片、封面、QA 报告等；包含 hash/path/type/version。
- `events`：任务事件流，用于 WebUI/SSE 和审计。
- `evaluations`：ASR/视觉/合规/创意评分。
- `publish_records`：平台发布结果、post id/url、AI 声明状态。
- `performance_metrics`：后续学习层预留。

## 状态机

主状态至少为：
`PLANNING → RESEARCHING → SCRIPTING → PREFLIGHT → GENERATING → QA → REPAIRING → COMPOSING → PACKAGING → READY → PUBLISHING → LEARNING → DONE`
并允许：`PAUSED / BLOCKED / FAILED / CANCELLED`。

## 必做任务

1. 为 SQLite 建 migration/version 机制，禁止启动时靠 `CREATE TABLE IF NOT EXISTS` 静默漂移 schema。
2. queue JSON 改为 artifact/dispatch cache，不再是任务事实源。
3. 所有 job status 更新必须经 JobStore API，不允许散落 SQL 直接随意改状态。
4. 所有状态转换做合法性校验，并记录 event。
5. 旧 jobs 数据提供一次性兼容迁移；不能直接删现有数据。

## Phase 2 验收标准

- 任意任务在 DB 中可查询完整状态、attempt、artifact 和 event。
- WebUI 任务总数与 JobStore 实际数量一致。
- 一个任务从 `PLANNING` 模拟走到 `DONE`，所有转换可追溯。
- 非法状态转换会被拒绝并写明原因。
- 旧数据库备份后可成功迁移；迁移测试覆盖空库和已有数据两种情况。
- queue 文件被删除/重建不会导致 JobStore 丢失任务事实。
- commit：`phase-2: introduce canonical job store and state machine`。

---

# Phase 3 — 建立唯一 PipelineOrchestrator，打通 WebUI/Hermes/CLI

## 目标

所有入口最终只调用一个 Orchestrator，彻底结束“WebUI 一套、脚本一套、Hermes 又一套”的并行逻辑。

## 建议结构

```text
lib/orchestrator/
  service.py
  stages.py
  models.py
  errors.py
  recovery.py
```

## 必做任务

1. 将 `run_all.py` 降级为 CLI adapter，不再承担核心业务编排。
2. 新建 `PipelineOrchestrator.start(goal/config)`、`resume(job_id)`、`cancel(job_id)`、`retry(job_id)`。
3. WebUI `/api/start` 必须创建/启动真实 Job，而不是简单启动脚本子进程。
4. Hermes 若要求“生产 N 条视频”，必须调用与 WebUI 相同的 Orchestrator 接口。
5. settings 中 `daily_target / concurrency / publish / engage / platforms` 真正进入运行时 config snapshot，并保存在 job 上。
6. 所有 stage 输出结构化 `StageResult`：`success/artifacts/metrics/error_code/message/next_action`。

7. 任一 stage 返回失败必须停止下游执行，除非 RepairEngine 明确给出可继续动作。
8. SSE/WebUI 从 JobStore event stream 获取状态，避免“轮询脚本字符串猜阶段”。
9. 旧 `/api/state` 可保留兼容，但数据来源必须改为 JobStore/Orchestrator。
10. Stop 必须是 cooperative cancellation：记录 `CANCEL_REQUESTED`，安全终止子进程并收尾 artifact。

## 验收标准

- 从 WebUI 启动、CLI 启动和 Hermes 启动的任务在 DB 中结构完全一致。
- 设置 `daily_target=2` 后模拟 provider 能自动生成 2 个 job，不多不少。
- `gen_concurrency` 能真正限制并行任务数。
- Stop/Cancel 后没有孤儿子进程，job 明确进入 `CANCELLED` 或可恢复状态。
- 重启 WebUI 不影响后台已存在 job 的查询与恢复。
- commit：`phase-3: centralize execution in pipeline orchestrator`。

---

# Phase 4 — 任务恢复、幂等、成本保护与 RepairEngine 基础

## 目标

做到“有问题自己处理”之前，先做到“不重复花钱、不无限重试、不因重启丢任务”。

## Error Taxonomy

至少定义：
`CONFIG_MISSING / AUTH_EXPIRED / NETWORK_TRANSIENT / RATE_LIMIT / PROMPT_TOO_LONG / ASSET_MISSING / PROVIDER_REJECTED / GENERATION_FAILED / GENERATION_TIMEOUT / DOWNLOAD_FAILED / ASR_MISMATCH / SUBTITLE_ALIGN_FAIL / VISUAL_QA_FAIL / PRODUCT_DEFORMED / WRONG_SPEAKER / HUMAN_ANATOMY_FAIL / COMPLIANCE_BLOCK / PUBLISH_QUOTA / PUBLISH_AUTH / UNKNOWN`。

## 必做任务

1. 每个 provider 提交前生成 idempotency fingerprint：job + stage + prompt hash + refs hash + workflow。
2. 保存 task id 后必须立即落 DB，再进入轮询。
3. 进程恢复时：如果已有 task id，先 query provider；禁止盲目重新 create_task。
4. provider SUCCESS 但下载失败，只允许重下，不允许重生成。
5. transient 网络错误指数退避；业务错误不允许网络式无限重试。
6. 每个 stage 定义 `max_attempts`、`max_cost`、`repairable`。
7. job 定义总成本预算，超过预算自动 `BLOCKED_BUDGET`。

8. `RepairEngine` 初版先只负责“根据 error_code 选择动作”，不要一开始做自由 Agent。
9. 修复动作必须是白名单：`RETRY_SAME / SWITCH_WORKFLOW / COMPRESS_PROMPT / REGENERATE_SHOT / REBUILD_SUBTITLE / WAIT_AND_RESUME / REQUIRE_HUMAN / ABORT`。
10. 所有 repair decision 写入 events，并记录为什么这样修。

## 验收场景

- 模拟 H3 create_task 成功后进程崩溃；重启后只 query 原 task，不产生第二个提交。
- 模拟 provider SUCCESS、下载失败两次；最终只发生下载重试。
- 模拟 prompt 超 10000 字；系统应在付费前压缩/阻断，AutoDL 提交数为 0。
- 模拟连续 3 次 generation failed；达到上限后 job BLOCKED/FAILED，不无限烧钱。
- 模拟 publish quota；系统等待/调度，不把它当生成失败。
- commit：`phase-4: add resumability idempotency and repair policies`。

---

# Phase 5 — Planner + Trend Research + CreativeDNA

## 目标

让“开始生产 N 条”不再依赖人工预先塞 spec，而是系统自己完成选题和创意规划。

## CreativeDNA 建议字段

`audience / goal / hotspot / genre / angle / sales_point / hook_type / narrative_arc / shot_pattern / cast_pattern / product_role / conflict_type / visual_motif / camera_language / dialogue_mode / audio_mode / payoff / ending / CTA / risk_flags`。

## 必做任务

1. Planner 根据 `daily_target - active_or_completed_today` 自动补齐需要创建的 job 数。
2. 接入 `creative_research.py`，研究结果必须保存为 artifact，而不是只拼进 prompt 后消失。
3. 热点数据统一 normalize：来源、标题、发布时间、热度、互动、相关性、新鲜度、证据 URL。
4. 不把 evergreen 当“实时热点”；必须明确标记 source type。
5. `pick_combo.py` 从“最少使用就选”升级成候选评分器，但保留使用次数作为 novelty 特征。
6. 一次先生成 10–20 个廉价结构化 CreativeDNA 候选，不直接付费出片。
7. Creative Director 对候选做结构化评分，筛选 top 3，再选最终方案。

8. 候选评分至少包含：`Novelty / AudienceFit / TrendFit / SalesPointFit / VisualPotential / ConflictStrength / GenerationFeasibility / BrandSafety / ClaimRisk / EstimatedCost`。
9. 不允许简单把“未使用第一个”作为最终选择算法。
10. 历史 `used_ideas`、角度/片型/角色使用记录继续作为特征，不能丢。
11. Planner 必须避免同一天连续生成相似 hook、相似故事骨架、相同角色组合。
12. 生成明确 `StorySpec`，不要直接让 LLM 输出最终 H3 大 prompt。

## 结构多样性要求

至少支持以下不同 StorySpec，而不是全部套 4×8：
- 双人对撞短剧
- 单人 Vlog/生活流
- 街访/伪纪录
- 悬念揭晓
- 魔性动作循环
- 产品实验/对比
- POV 第一人称
- 无对白肢体喜剧
- 情感故事
- 评论区续集/回应型

## 验收标准

- 空 queue 情况下，点击 Start 可自动产生新 job 和 CreativeDNA。
- 一次规划 5 条，至少在 genre/hook/shot_pattern 三个维度中有明显结构差异。
- Planner 失败不会进入付费 GENERATING。
- 所有 CreativeDNA、研究依据和筛选评分可在 artifact/event 中追溯。
- commit：`phase-5: add autonomous planner and structured creative dna`。

---

# Phase 6 — 建立产品 Claims Registry 与内容合规事实层

## 目标

彻底消除产品参数在 `products.py`、`engage.py`、prompt、标题中各写一套的问题。

## 建议新增

`assets/products/claims.yaml`，每个 claim 至少包含：
`claim_id / sku / display_text / spoken_text / value / unit / evidence / certificate / valid_from / valid_to / allowed_channels / risk_level / forbidden_rewrites`。

## 必做任务

1. 盘点现有 `lib/products.py`、产品 markdown、互动回复、历史 prompt 中所有参数和承诺。
2. 对互相冲突的参数不能由 Codex 猜正确值；标记 `needs_verification`，阻止自动对外使用。
3. Script/Packaging/Engage 只能通过 Claims Service 获取产品事实。
4. LLM 输出如果包含数值/认证/质保/疗效相关表述，必须映射到 claim_id；映射失败则 Gate 不通过。
5. 禁止自动生成医疗疗效承诺、绝对化广告词和无法证实的认证信息。
6. `engage.py` 删除内置重复 PRODUCT_POINTS，改读 Claims Registry。
7. 发布 artifact 保存本条视频实际引用的 claim_id 列表。
8. 建立 claim regression tests：参数口径变更时能知道哪些模板/内容受到影响。

## 验收标准

- 同一个重量、续航、承重等参数只存在一个权威机器可读来源。
- 故意让 LLM 输出未登记参数时，系统必须阻断而不是“看起来合理就通过”。
- 互动回复、脚本和发布文案引用相同事实层。
- commit：`phase-6: centralize product claims and compliance facts`。

---

# Phase 7 — StorySpec → PromptCompiler → 智能 Generation Router

## 目标

把仓库已有 CINEDANCE、ACTING、speaker lock、产品保真、workflow router 真正接入主链，并避免手写大 prompt 四处复制。

## 必做任务

1. 新增 `StorySpec` 强类型 schema；镜头数量、角色、台词模式均可变。
2. `PromptCompiler` 负责把 StorySpec 编译为 provider-specific prompt。
3. CINEDANCE 根据片型动态启用，不再作为独立外挂脚本。
4. ACTING 根据角色/场景生成行为节拍；不能把 master profile 原文无脑重复塞每镜。

5. Speaker Lock、GAZE、RIDER、产品单元保真等约束由 compiler 按场景注入，避免 prep 脚本重复粘贴。
6. Prompt Budgeter 在提交前计算字符/token 风险，自动去重重复约束；不得靠生成失败后才发现超长。
7. `check_dialogue.mjs` 继续做静态 gate，但需要和 15 秒 one-take 真实限制保持一致，清理已经失效的旧阈值。
8. 生成入口统一调用 capability-aware router；不再由 spec 人工固定空 fallback。
9. Router 根据 `duration / ref_images / audio / quality / first_last / risk / historical_success` 选择 workflow 链。
10. provider adapter 返回统一 `ProviderTask`，禁止业务层依赖 AutoDL 私有字段。
11. 高风险新构图自动触发 `prescreen`：多人、复杂交互、特殊道具、品牌字、危险形变动作等。
12. prescreen 结果进入 evaluation；PASS 才允许完整 15 秒付费生成。
13. 所有 prompt/spec/compiler 版本写入 artifact metadata，保证复现。

## 验收标准

- 10 种 StorySpec 至少各能通过 fake provider 编译和执行，不再被固定 4 镜×8句限制。
- prompt 超限可在 provider 调用前阻断或自动压缩。
- 故意让首选 workflow 返回失败，router 能在预算内切换兼容 fallback。
- fallback 不得偷偷丢失音频/参考图/时长关键能力；能力不兼容时必须拒绝切换。
- 高风险 StorySpec 会先进入 prescreen，低风险任务可直接生成。
- commit：`phase-7: compile structured stories and route generation intelligently`。

---

# Phase 8 — 自动 QA Critic + RepairEngine 完整闭环

## 目标

把“抽帧给人看”升级为机器 Gate，使系统能知道为什么不合格、该修哪里，并只重做必要部分。

## QA 维度

### 视觉产品保真
- 产品数量必须符合 StorySpec。
- 颜色、车架、轮子、脚踏、控制器、靠背、LOGO/品牌区域不能异常形变。
- 同一条视频内不得莫名换车型、重复产品或产品漂移。

### 人物与表演
- 人脸、手、脚、腿、身体结构无明显畸形。
- 人物数量正确、身份一致、服装/年龄/发型连续。
- 非说话人闭嘴，说话人与声音匹配。

### 音频/对白
- ASR 与期望台词一致率达到配置阈值。
- 无明显漏句、串声、角色音色交换、长尾静默。
- 语速和总时长适合对应 StorySpec，而不是所有片型都强制相同密度。

### 镜头与留存代理指标
- 0–2 秒是否存在明确视觉/冲突/声音钩子。
- 2–5 秒是否仍有未解决的问题或动作推进。
- 是否存在无意义静止、长停顿、构图失焦、主体过小。
- payoff 是否过晚或没有兑现前文冲突。

### 品牌/合规
- 产品卖点来自 Claims Registry。
- 无未经登记的参数、认证、医疗疗效或绝对化承诺。
- 发布前 AI 内容声明要求已记录。

## Repair 映射示例

- `PROMPT_TOO_LONG` → `COMPRESS_PROMPT`，不生成。
- `WRONG_SPEAKER` → 强化该镜 speaker lock；必要时减少同镜角色后重生。
- `PRODUCT_DEFORMED` → 简化动作/构图、加强产品 refs，优先重生问题镜。
- `HUMAN_ANATOMY_FAIL` → 调整 occupancy/镜头距离/动作复杂度后重生。
- `ASR_MISMATCH` → 区分同音识别与真实漏词；真实漏词则缩句/调整节奏后生成。
- `SUBTITLE_ALIGN_FAIL` → 只重做字幕，不允许重新生成视频。
- `DOWNLOAD_FAILED` → 只重下 provider artifact。
- `COMPLIANCE_BLOCK` → 改文案/claim，不允许绕过 gate。

## 验收标准

- QA 输出结构化 JSON + 人类可读报告。
- 每个 FAIL 都必须映射到 error_code，不允许只有“质量不好”。
- 至少构造 8 种失败 fixture 验证 repair routing。
- repair 次数、成本和最终结果均写 DB。
- 达到修复上限后转 `REQUIRE_HUMAN/BLOCKED`，禁止无限循环。
- commit：`phase-8: add automated qa critic and bounded self repair`。

---

# Phase 9 — 后期链统一：ASR、字幕、BGM、SFX、节奏

## 目标

减少重复计算和固定模板味，让后期由 StorySpec/剧情节拍驱动，同时保持现有已验证的 ffmpeg 经验。

## 必做任务

1. ASR 每条视频只做一次高质量 word timestamp 转写，结果保存为 artifact 并被所有后续步骤复用。
2. 移除当前 `small` 一次 + `medium` 再一次的重复推理。
3. 字幕继续保留：已知台词校正、孤行合并、自然断句、关键词高亮，但配置化字体和安全区。
4. 所有字幕时间必须来自同一 transcript artifact，避免不同阶段各自产生时间轴。
5. `trim_onetake` 增加 segment count、输出总时长、音视频流完整性校验；局部 ffmpeg 失败不得静默跳过。
6. BGM 建立 metadata：`BPM/energy/mood/intro_strength/drop_time/genre/vocal/comedic/emotional`。
7. StorySpec 输出 `mood_curve/beat_map`，AudioDirector 据此选曲，不允许再靠文件大小或单纯 random。
8. 保留“最近未使用”作为防重复特征，但不能成为唯一选曲逻辑。
9. SFX 从动作、反转、punchline、品牌 beat 动态放置；移除固定第 4/5/7/8 句的通用模板依赖。
10. 对不同 genre 允许不同后期：Vlog 可更自然、魔性广告可高密度、情感片不应强塞 ding/whoosh/pop。
11. 输出统一 Loudness/Peak 检测结果，避免混音过爆或人声被 BGM 压住。

## 验收标准

- 一条视频只产生一个 canonical transcript。
- 同一 StorySpec 重跑后期不触发视频重新生成。
- 至少 5 种 genre 的 BGM/SFX 选择策略明显不同。
- 无字幕越界、孤字、明显重叠，语音期间 BGM 可懂度合格。
- commit：`phase-9: unify post production and make audio story aware`。

---

# Phase 10 — Packaging、发布接线、账号安全与 AI 合规

## 目标

把生产 job 与发布 job 合为同一个生命周期，并确保自动化不会为了“全自动”牺牲账号安全。

## PackagingAgent 输出

每条 READY 视频至少生成并保存：
- 3 个标题候选及最终选择理由。
- 封面文案/首帧策略。
- description。
- hashtags。
- 首评候选。
- 引用的 claim_ids。
- `ai_generated=true` 与平台声明需求。
- 发布目标平台、时间窗和模式。

## 必做任务

1. 删除 `publish.py` 中写死的标题/标签，全部从 Packaging artifact 读取。
2. one-take job 达到 READY 后可被同一 JobStore 发布，不再要求另一套旧 jobs 状态。
3. 保留并加强发布窗口、daily limit、min interval、平台间 pacing。
4. 发布采用幂等 external_id/job id，防止重试产生重复帖子。
5. AUTH_EXPIRED 时立即暂停该平台，禁止持续刷新、暴力扫码或反复发布。
6. AI 生成内容声明成为 publish gate 的硬字段。
7. 若 PostFlow/API 无法确认抖音 AI 内容声明，则抖音自动化只能上传草稿/进入 `REQUIRE_HUMAN_PUBLISH`，不得直接真发。
8. 发布失败按平台独立记录；某一平台失败不得抹掉其他平台成功结果。
9. 评论/私信自动互动继续保留价格、医疗、投诉等转人工红线，并改用 Claims Registry。
10. 自动互动加入每小时上限、随机安全间隔、重复回复检测、账号异常立即熔断。

## 验收标准

- fake provider 下可完整执行 READY → PUBLISHING → DONE。
- 同一 job 重复调用 publish 不会产生第二次真实发布请求。
- 抖音 AI 声明无法确认时，测试必须证明系统拒绝 direct publish。
- 发布标题/描述中出现未登记 claim 时被 Compliance Gate 拦截。
- commit：`phase-10: connect packaging publishing safety and ai compliance`。

---

# Phase 11 — Performance Learner：让系统越做越聪明

## 目标

建立真正的创意反馈闭环。不要把网上所谓固定“爆款权重”写死，而是学习本账号自己的表现。

## 建议新增

`s7_learn/`：
- `collector.py`：只读采集/导入平台表现。
- `normalizer.py`：跨平台指标标准化。
- `features.py`：CreativeDNA → 机器学习/评分特征。
- `scorer.py`：策略评分。
- `report.py`：每日/每周复盘。

## 指标模型

在平台实际可获得的前提下记录：
`impressions / views / 2s_skip / 5s_retention / avg_watch_time / avg_watch_pct / completion / rewatches / likes / comments / shares / saves / follows / profile_visits / DMs / conversion_proxy`。
缺失字段必须为 NULL/unknown，禁止编造 0。

## 必做任务

1. `performance_metrics` 关联 job、platform、post_id、snapshot_time。
2. 指标采集优先官方/已有可信接口；需要浏览器时只做低频只读采集，不做激进反自动化绕过。
3. CreativeDNA 全部成为可分析 feature。
4. 每日生成 performance summary：genre/hook/angle/sales_point/cast/shot_pattern 的表现分布。
5. Planner 的候选评分加入 `HistoricalPerformance`，但新策略必须保留探索机会。
6. 建议初始策略：80% exploitation + 20% exploration，比例配置化，不写死为不可改规则。
7. 小样本时使用平滑/置信度，不因为一条偶然爆或扑就永久淘汰某片型。
8. 不做“下一条一定爆”的预测承诺；只做基于历史数据的相对策略优化。
9. 每条学习结论必须能追溯到样本量和时间窗口。

## 验收标准

- 导入一组 fixture 表现数据后，系统可以输出不同 CreativeDNA 的表现差异。
- Planner 在相同候选下会受到历史数据影响，但仍保留探索候选。
- 数据不足时明确显示 low confidence。
- commit：`phase-11: add closed loop creative performance learning`。

---

# Phase 12 — WebUI 重构为真实任务控制台

## 目标

前端不再猜脚本状态，而是完整展示 JobStore/Orchestrator 的真实任务、成本、QA、修复和发布状态。

## 后端 API 最低要求

- `POST /api/jobs`：创建生产目标/job。
- `GET /api/jobs`：任务列表与过滤。
- `GET /api/jobs/{id}`：完整任务详情。
- `POST /api/jobs/{id}/cancel`。
- `POST /api/jobs/{id}/retry`。
- `POST /api/jobs/{id}/resume`。
- `GET /api/jobs/{id}/artifacts`。
- `GET /api/jobs/{id}/events`。
- `GET /api/system/health`。
- SSE/WS：结构化 job events。

## 前端要求

1. 将当前大 `app.js` 至少拆成：`api / store / hermes / jobs / settings / outputs / health` 模块。
2. Pipeline 面板展示真实状态机，而不是固定六阶段假状态。
3. 每个 job 可看到：CreativeDNA、当前 stage、attempt、成本、provider task、QA 分数、repair history、artifacts。
4. BLOCKED 状态必须明确告诉用户“为什么需要人工”，不能只显示失败。
5. Settings 保存后显示 runtime 生效值；被忽略字段必须指出原因。
6. System Health 用 `READY / DEGRADED / BLOCKED` 显示每个能力。
7. 成片区展示视频、QA 摘要、标题/封面方案、发布状态和性能数据。
8. Hermes 对话只作为 Operator/Copilot，不再维护另一套任务真相。

## 验收标准

- 页面刷新后正在运行的 job 仍能正确恢复显示。
- Cancel/Retry/Resume 操作与 DB 状态一致。
- 前端没有通过字符串包含“失败/完成”来推断核心业务状态。
- Playwright 覆盖启动、取消、失败修复、READY、发布阻断等流程。
- commit：`phase-12: rebuild web console around canonical jobs and events`。

---

# Phase 13 — 测试体系、CI 与自动开发护栏

## 目标

让 Codex 后续可以持续自主迭代，而不是每次修改都靠人工猜有没有弄坏主链。

## 测试层级

### Unit
覆盖：状态机、settings、claims、router、creative scoring、repair policy、subtitle/audio 工具纯逻辑、publish quota。

### Contract
为 DeepSeek、AutoDL、Upload-Post、PostFlow 建响应 fixture；验证第三方字段变化时能尽早报警。

### Integration
使用 fake LLM + fake generator + fixture video 跑：Planner → Script → Generate → QA → Repair → Compose → Packaging → READY。

### Frontend
Playwright 覆盖 WebUI 关键操作和 WS/SSE 断线恢复。

### Golden
保存若干稳定 StorySpec/CreativeDNA，验证重构后 compiler 仍满足关键结构和 hard constraints；不要比较随机自然语言全文完全一致。

### Live / Paid
必须显式开启，例如 `AYHMJ_RUN_LIVE=1`；默认 CI 永远不允许提交付费任务或真实发布。

## CI 门禁

建议顺序：`lint → typecheck → unit → contract → integration → frontend smoke → migration test`。
PR 未全绿禁止合并。

## 验收标准

- 一条命令可运行所有非 live 测试。
- fake 端到端主链可在无网络、无付费条件下完成。
- 任意 provider contract fixture 改坏时测试明确失败。
- commit：`phase-13: establish ci and autonomous development guardrails`。

---

# Phase 14 — Legacy 收敛、文档更新与最终架构清理

## 目标

只有新主链已经通过完整回归后，才删除/归档旧入口，防止过早清理导致无法回退。

## 必做任务

1. 搜索所有对旧 `run_all.py`、旧六阶段状态、旧 queue 事实源的引用。
2. 确认新 Orchestrator 已覆盖功能后，再将旧入口标记 deprecated 或移入 legacy。
3. `pipeline.yaml` 删除已无效字段；如果为兼容保留，必须启动时发 deprecated warning。
4. 合并重复 BGM/SFX 选择逻辑，确保 AudioDirector 为唯一策略入口。
5. 合并重复产品事实文本，Claims Registry 为唯一事实来源。
6. 清理不再使用的本机绝对路径和历史临时脚本。
7. `_deprecated_*` 不参与运行、测试 discovery、module import 和 WebUI。
8. 更新 README：安装、health check、启动、创建目标、恢复任务、人工阻断、发布安全、测试方法。
9. 新增 `docs/architecture/vnext.md` 与数据库 ER/状态机图。
10. 新增 `docs/operations.md`：常见故障、恢复流程、成本异常、账号登录异常、provider 异常。
11. 新增 `docs/creative_system.md`：CreativeDNA、StorySpec、QA、Repair、Learner 说明。

## 验收标准

- 全仓搜索不存在业务代码继续依赖已废弃事实源。
- fresh clone + 文档步骤能启动到 DEGRADED/READY 可解释状态。
- 全部非 live 测试通过。
- commit：`phase-14: retire legacy pipeline and document vnext architecture`。

---

# Phase 15 — 最终端到端验收

本阶段不再新增功能，只修验收中发现的问题。任何新增需求必须回到相应 Phase 设计，不允许在 Final Acceptance 临时堆补丁。

## 15.1 无付费全链验收

使用 fake provider + fixture media，完成至少 5 个不同 CreativeDNA 的任务：

1. `daily_target=5`，空 queue、空当日任务开始。
2. Planner 自动创建 5 个 job，不依赖人工 spec。
3. 5 个 job 的 genre/hook/shot_pattern 至少三个维度存在结构差异。
4. Research artifact、CreativeDNA、StorySpec、compiled prompt 均可查询。
5. Claims Gate 能阻断一个故意注入的虚假参数候选。
6. Prescreen 能只对高风险任务触发。
7. Router 能模拟首选 workflow 失败并正确 fallback。
8. QA 能分别识别：错嘴、产品形变、ASR 漏词、字幕失败 fixture。
9. RepairEngine 根据 error_code 执行不同修复动作。
10. 修复达到上限后正确 BLOCKED，不无限循环。
11. 后期只使用一个 canonical transcript。
12. Packaging 为每条生成标题/描述/claim ids/AI disclosure 信息。
13. Publish fake adapter 幂等执行，同一 job 重试不重复发帖。
14. Performance fixture 回流后 Planner 下一轮评分发生合理变化。
15. WebUI 全程显示与 JobStore 一致的状态、attempt、cost、QA、repair。

### 通过标准

- 5/5 job 均达到预期终态（DONE 或人为设计的 BLOCKED）。
- 无 orphan process。
- 无未捕获异常。
- 无重复 provider submit。
- 无非法状态跳转。
- DB/event/artifact 可完整追踪每个 job。

## 15.2 故障恢复验收

逐项人工注入故障并验证：
- WebUI 进程重启。
- Orchestrator 进程在 provider submit 后立即退出。
- 网络查询超时。
- provider SUCCESS 后下载失败。
- SQLite busy/短暂锁等待。
- 磁盘空间不足模拟。
- 缺字体/缺 ffmpeg/缺 Upload-Post key。

每项故障的预期行为必须明确：
- 可自动恢复的进入 WAIT/RETRY/RESUME，不创建重复付费任务。
- 环境能力缺失进入 DEGRADED/BLOCKED，并给出具体修复提示。
- 不可恢复错误停止下游 stage，不产生伪成功 artifact。
- 重启后 WebUI 能从 DB 恢复真实状态。

## 15.3 成本与幂等验收

1. fake provider 统计 create/query/download 调用次数。
2. 同一 attempt 重跑不得重复 create_task。
3. 下载失败只增加 download 次数。
4. provider 业务拒绝不得被当网络异常无限重试。
5. 每个 job 显示预估成本、已发生成本、repair 成本和总成本。
6. 超预算时立即 BLOCKED_BUDGET。
7. prescreen 成本和正式生成成本分别记录。

## 15.4 成片多样性验收

连续规划至少 10 个 StorySpec，要求：
- 不得 10 条全部为两人对话。
- 至少包含 5 种 genre。
- 至少包含 5 种 hook_type。
- 至少包含 4 种 shot_pattern。
- 至少有 1 条低对白/无对白方案。
- 至少有 1 条 Vlog/生活流、1 条悬念、1 条实验/对比、1 条喜剧/魔性或 POV。
- 相邻作品不能同时复用 `genre + hook + angle + cast` 的完整组合。
- 历史相似度超过阈值的脚本必须重新规划。

## 15.5 真实生成验收（受预算保护）

只有以上无付费测试全绿后才允许执行。
默认最多选择 2 条不同片型进行真实 H3 验收，且必须配置明确 cost cap。
真实验收重点不是“是否爆款”，而是验证 provider、恢复、QA、后期和 artifact 真实链路。
如果用户没有显式开启真实发布，最终验收只到 READY/草稿，不得为测试擅自真发社媒。

## 15.6 发布安全验收

- `real_publish=false` 时任何路径都不得真发。
- `real_publish=true` 也必须通过 quota、time window、auth、AI disclosure、claims、artifact 完整性 Gate。
- 平台 auth 异常触发熔断，不得循环登录或连续发布。
- 同一 post external_id 幂等。
- 自动评论命中价格/医疗/投诉红线时转人工。
- 账号异常、平台验证码、风控提示一律 `REQUIRE_HUMAN`，不做绕过。

## 15.7 最终 Acceptance Report

Codex 必须生成 `docs/codex_final_acceptance.md`，至少包含：
1. 最终 commit SHA 与分支。
2. 各 Phase commit 列表。
3. 数据库 schema version。
4. 全部测试命令与结果摘要。
5. live/paid 测试是否执行、成本多少、task id 数量。
6. 10 条 CreativeDNA 多样性统计。
7. 故障恢复测试结果。
8. 仍需人工介入的能力清单。
9. 已知限制/第三方平台限制。
10. 未完成项必须明确写 `NOT ACCEPTED`，不得用“基本完成”替代。

只有下列条件全部满足，才允许标记项目 vNext 验收完成：
- 非 live CI 全绿。
- P0 问题归零。
- 主链不再依赖人工预放 queue spec。
- JobStore 为唯一事实源。
- Orchestrator 为唯一执行入口。
- 恢复/幂等/预算保护测试通过。
- QA/Repair 闭环通过 fixture 验收。
- Claims/AI disclosure 发布 Gate 有自动测试。
- WebUI 与真实任务状态一致。
- 生成多样性验收通过。

---

## 16. Codex 文件级改造地图

| 现有位置 | 处理方向 |
|---|---|
| `lib/state.py` | 升级为 migration-backed JobStore；逐步移出裸 SQL 业务操作 |
| `tools/run_all.py` | 降级为 CLI adapter，最终只调用 Orchestrator |
| `tools/make_15s.py` | 保留成熟后期能力；拆出 stage service，不再承担系统编排 |
| `s4_generate/gen_one_take.py` | provider adapter 化、幂等 task、resume/reconcile |
| `s4_generate/autodl_client.py` | 统一 Provider API，网络错误与业务错误分类 |
| `s4_generate/workflow_router.py` | 接入主链，增加 capability/历史成功率/成本条件 |
| `tools/prescreen.py` | 变成 Orchestrator 的可调用 Stage，而不是孤立 CLI |
| `lib/prompt_parts.py` | PromptCompiler 的约束片段库，去重复硬编码 |
| `lib/hellgrind.py` | CINEDANCE/ACTING 服务化并由 StorySpec 调用 |
| `lib/ideas.py` | 保留 novelty 数据，接入 Creative Scorer |
| `lib/genres.py` / `lib/angles.py` | 从轮换器升级为特征/候选库 |
| `lib/products.py` | 卖点定义迁移/关联 Claims Registry |
| `lib/creative_research.py` | Research Stage，产出可追溯 artifact |
| `tools/transcribe_local.py` | 收敛为 canonical transcript service |
| `tools/lines_to_srt.py` | 消费 transcript artifact，避免再次完整 ASR |
| `s5_compose/burn_subtitles.py` | 配置化字体/安全区，消费统一字幕时间轴 |
| `tools/audio_polish.py` | 由 AudioDirector 调用，去随机/重复选曲策略 |
| `s6_publish/publish.py` | 消费 Packaging artifact + canonical JobStore |
| `s6_publish/engage.py` | Claims Service + 风控/熔断/频率限制 |
| `webui/server.py` | API adapter/service 分层，去脚本状态猜测 |
| `webui/static/app.js` | 拆模块，改成 canonical job/event UI |
| `webui/hermes_bridge.py` | 保留桥接，但 Hermes 任务操作统一走 Orchestrator |
| `config/pipeline.yaml` | 迁移到统一 Settings，清理失效配置 |
| `tools/bootstrap.py` | 升级为可部署 bootstrap + capability health check |

---

## 17. Codex 每阶段固定执行流程

Codex 在每个 Phase 必须机械执行以下顺序：

```powershell
# 1. 确认分支和工作区
cd D:\@kaifa\ayh-mj
git status
git branch --show-current

# 2. 先跑阶段开始前的回归基线
uv run ruff check .
uv run pytest -m "not live and not paid"

# 3. 只实现当前 Phase
# 禁止把下一 Phase 的大重构顺手混入当前提交

# 4. 再跑回归 + 当前阶段新增测试
uv run ruff check .
uv run pytest -m "not live and not paid"

# 5. 必要时运行 WebUI/Playwright smoke
# 具体命令以 Phase 0 最终落地的 package scripts 为准

# 6. 更新 docs/codex_phase_N_acceptance.md
# 写清：改了什么、测试结果、仍有什么限制

# 7. 检查 diff 后提交
git diff --check
git status
git add -A
git commit -m "phase-N: ..."
```

如果当前仓库还没有 uv/pytest/ruff 配置，则 Phase 0/1 负责建立；建立后后续阶段必须统一使用，不能再每个脚本自己发明运行方式。

### Codex 遇到测试失败时的规则

- 先判断失败是本阶段引入还是基线已有。
- 本阶段引入的失败必须修复后才能提交。
- 基线已有问题必须记录并在对应 Phase 修复，禁止用 skip/xfailed 无理由掩盖。
- 不允许删测试来“让 CI 变绿”。
- 不允许因为第三方 API 暂时不可用就把核心逻辑测试改成真实网络测试。

---

## 18. 给 Codex 的最终执行指令

从 Phase 0 开始连续执行到 Phase 15 验收完成。正常情况下不要每个小步骤都停下来询问用户；使用本文档已给出的目标、约束和验收标准自行推进。

只有以下情况允许暂停并要求人工输入：
1. Claims Registry 出现互相冲突的产品事实，且仓库内没有可靠证据判断哪个正确。
2. 缺失真实 API 凭据/账号登录，导致必须进行 live 验收。
3. 需要真发社媒，但用户没有显式开启 `real_publish=true`。
4. 平台出现验证码、风控、账号异常、权限变更或 AI 声明能力无法确认。
5. 预计真实付费测试将突破配置的 cost cap。
6. 发现需要删除用户数据、历史成片或不可逆迁移。

除此之外，遇到普通代码错误、测试失败、依赖冲突、数据库迁移问题、provider fixture 问题，应由 Codex 自行诊断、修复并继续。

### 最终输出要求

开发完成时 Codex 应向用户只汇报可验证结果：
- 完成到哪个 Phase。
- 当前分支与最终 commit SHA。
- 测试通过数量/失败数量。
- 是否执行真实 H3 验收及实际成本。
- 是否执行真实社媒发布；如果没有，明确停在 READY/草稿。
- 最终架构中仍需人工处理的事项。
- `docs/codex_final_acceptance.md` 的路径。

不要以“代码已写完”作为完成；必须以 Phase 15 Acceptance 全部通过作为完成。

---

## 19. 最终目标一句话

**ayh-mj vNext 不是一个会调用很多脚本的 Agent，而是一套有统一状态、可恢复、可审计、能规划、能验片、能针对性修复、能安全发布、并能用真实表现持续学习的自主短视频生产系统。**
