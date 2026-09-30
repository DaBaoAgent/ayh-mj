# Phase 12 验收记录 — WebUI 重构为真实任务控制台

- 阶段：Phase 12
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 12
- commit：`phase-12: rebuild web console around canonical jobs and events`
- 原始证据：
  - `docs/codex/phase12_web_console.txt`（17 段实测：环境与隔离 / 造数 / 10 个 REST 端点 / SSE 帧 / 动作与 DB 一致性 / 守卫 / runtime 生效值 / 成片物料卡 / 前端护栏 / 落盘）
  - `docs/codex/phase12_verification.txt`（ruff / 定向 pytest / 全量 pytest / Playwright）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 只读投影（新） | `webui/jobview.py`（344 行，CRLF） | 前端的**唯一数据来源**：把 `jobs / attempts / artifacts / events / evaluations / publishes / performance_metrics` 加 Planner 落盘的 `state/creative/dna_<uid>.json`、packaging artifact，投影成 UI 能直接渲染的字段。导出 `job_summary / detail_view / artifacts_view / events_view / materials / blocked_block / qa_view / perf_view / load_creative`，以及动作白名单 `CANCELLABLE / RETRYABLE / RESUMABLE / MATERIAL_STATES / PERF_FIELDS`。约定：只读不写、缺失一律 `None` 不编造、`blocked` 只对 FAILED/BLOCKED 出现且必须带 `human_action`。 |
| 人话错误表 | `lib/orchestrator/errors.py`（CRLF） | 新增 `HUMAN_HINTS`（**50 条** error_code -> 人话）与 `human_action_hint(error_code, message="")`：表内直出人话，表外按 `repair_action_for` 的 `WAIT_AND_RESUME / REQUIRE_HUMAN / ABORT` 兜底，**任何错误码都不会只丢一个代号给用户**。 |
| 后端 API | `webui/server.py`（879 行，CRLF） | 新增 `POST /api/jobs`、`GET /api/jobs`（status/limit/q 过滤 + `total.by_status`）、`GET /api/jobs/{uid}`、`GET /api/jobs/{uid}/artifacts`、`GET /api/jobs/{uid}/events?since=&limit=`、`GET /api/materials`、`GET /api/jobs/events`（SSE 结构化事件流）。`POST /api/jobs` 与 `/api/start` 共用同一个执行内核 `start_production` + `ENGINE_START_LOCK`。`POST /api/settings` 保存后回 `runtime`（`RunConfig.from_console(state).to_dict()`）与 `runtime_applies_to`。 |
| 前端拆分 | `webui/static/js/`（8 个模块）+ `webui/static/app.js`（4411 字节） | `ui / api / store / hermes / jobs / settings / outputs / health`。`app.js` 只剩装配（bindUI + boot + 4 个轮询 + SSE 订阅），不再承载任何业务逻辑。状态与阶段的展示口径集中在 `ui.js`（`CANONICAL_STAGES / CANONICAL_SIDE / STAGE_LABELS_CN / stateLabel / stateTone / stageLabel`），**判断一律用后端给的布尔量**。 |
| 界面 | `webui/templates/index.html` + `webui/static/phase12.css` | 新增 `#stateStrip`、任务台卡（`#jobsList / #jobsFilter / #jobsRefresh`）、任务抽屉（`#jobMask / #jobDrawer / #jobDrawerBody / #btnCloseJob`）、成片区（`#materialsList`）、System Health（`#healthStatus / #healthGrid`）、Settings 运行时框（`#runtimeBox`），并改为单行 `<script type="module" src="/static/app.js?v=phase12">`。 |
| 隔离 | `lib/__init__.py`（CRLF） | 新增 `OUT_DIR = Path(os.environ.get("AYHMJ_OUT_DIR") or OUT_DIR)`：让测试与多实例能把产出目录也隔离到临时目录，**默认行为不变**。 |
| 测试 | 4 个新文件 | `tests/p12_support.py` + `tests/p12_seed.py`（独立进程造数，保证与服务端共享同一份 canonical 事实源）、`tests/unit/test_jobview.py`(23)、`tests/unit/test_webui_jobs_api.py`(21)、`tests/unit/test_web_console_source.py`(11)、`tests/frontend/test_web_console.py`(6)。 |

## 2. 计划必做任务逐条

### 2.1 后端 API 清单（10 项，逐条实测见 `phase12_web_console.txt` ③-⑮）

| 计划要求 | 实现 | 实测 |
|---|---|---|
| `POST /api/jobs` | 与 `/api/start` 同内核，返回 `{ok,count,jobs,run}` | ⑬ HTTP 200，新建任务 `status=SCRIPTING` 起步、演练结束 `READY`、`cost_spent=0.0` |
| `GET /api/jobs` | canonical 列表 + `total.by_status` | ③ HTTP 200 `count=4 total={"total":4,"by_status":{...}}`，`status=` 与 `q=` 过滤都生效 |
| `GET /api/jobs/{id}` | `detail_view`：job/summary/creative/qa/attempts/provider_tasks/repairs/repair_summary/artifacts/publishes/performance/events/blocked | ④ 三种状态各一条，`keys` 完全一致，未知 uid -> 404 `{"error":"任务不存在"}` |
| `POST /api/jobs/{id}/cancel` | 协作式取消 | ⑨ READY -> `{"ok":true,"mode":"immediate"}`，API 复查与 DB 都是 `CANCELLED`，终态再取消 -> 404 |
| `POST /api/jobs/{id}/retry` | 只有 FAILED/BLOCKED 可重试 | ⑩ FAILED -> 真重跑 -> `READY` 且 `error_code=None`，⑫ READY retry -> 400 `JOB_NOT_RESUMABLE` 且 DB 未变 |
| `POST /api/jobs/{id}/resume` | 从断点继续 | ⑪ PAUSED -> 真跑 -> `READY`，⑫ 终态 resume -> 400 且 DB 未变 |
| `GET /api/jobs/{id}/artifacts` | 产物清单（含 `exists` / sha256 / `/media` URL） | ⑤ HTTP 200，落盘文件 `exists=true` |
| `GET /api/jobs/{id}/events` | 结构化事件 + `since` 增量 | ⑥ `count=7 last_id=17`，`since=17` -> `count=0`（无新事件必须为空） |
| `GET /api/system/health` | 能力矩阵 | ⑦ HTTP 200 `status=DEGRADED`（本机缺若干可选能力），`capabilities` 11 项 |
| SSE / WS 结构化 job events | `GET /api/jobs/events`，帧格式 `event: job\ndata: {canonical event}` + `event: snapshot\ndata: {orchestrator.status}` | ⑧ `content-type=text/event-stream`、`cache-control=no-cache`，第一帧解码即 canonical 事件，快照帧 `source_of_truth=jobstore` |

### 2.2 前端要求（8 条）

1. **拆分 `app.js`** -> `api / store / hermes / jobs / settings / outputs / health` 七个模块加一个 `ui` 共享层，`app.js` 4411 字节只做装配（护栏用例 `test_app_js_is_only_an_assembly_layer` 守住）。
2. **Pipeline 展示真实状态机** -> `#stateStrip` 与任务行都渲染 `jobs_by_status`，不写死阶段列表。
3. **每个 job 可见** CreativeDNA / 当前 stage / attempt / 成本 / provider task / QA / repair history / artifacts -> 抽屉按 `detail_view` 的 14 个 key 分区渲染（CreativeDNA、质检与评分、尝试与供应商、修复历史、产物、发布状态、表现数据）。
4. **BLOCKED 必须说明为什么需要人工** -> `blocked_block` 输出 `code / message / human_action / next_action / retryable`，人话来自 `HUMAN_HINTS`。实测 `AI_DISCLOSURE_UNCONFIRMED` -> "AI 生成声明无法确认：只能走草稿或人工发布，禁止直发。"
5. **Settings 保存后显示 runtime 生效值 + 被忽略字段原因** -> ⑭ `saved={"daily_target":3,"real_publish":false}`，`ignored={"bogus_key":"未知设置项","gen_concurrency":"超出范围 2-10"}`，`runtime` 里 `daily_target=3` 立刻生效。
6. **System Health 用 READY / DEGRADED / BLOCKED** -> ⑦ 实测返回 `DEGRADED`，前端按三档上色（`#healthStatus`）。
7. **成片区展示视频 / QA 摘要 / 标题封面方案 / 发布状态 / 表现数据** -> ⑮ 物料卡原始投影含 `video_url`、`qa`、`title`/`cover`/`hashtags`、`publish`、`performance`（`metric_count` 由后端投影）。
8. **Hermes 只作 Operator/Copilot** -> 状态事实全部走 REST/SSE，Hermes 只保留对话与工具卡（`hermes.js` 不出现任何状态推断）。

## 3. 验收标准

1. **页面刷新后运行中的 job 正确恢复显示** —— `test_running_job_survives_refresh_with_canonical_state`：造 `GENERATING` 与 `PAUSED` 两条任务，首次打开断言 `data-status="GENERATING"` 且行内是"视频生成"，`page.reload()` 后再断言一次（前端没有任何内存可依赖），`PAUSED` 同样如实显示。
2. **Cancel/Retry/Resume 与 DB 状态一致** —— 证据 ⑨⑩⑪⑫ 逐条对比"动作返回 / API 详情 / `store.get_job()`"三方。单测 `test_cancel_moves_job_to_cancelled`、`test_retry_reruns_failed_job_to_ready`、`test_resume_continues_paused_job` 以及三条守卫拒绝用例同时守住。
3. **前端没有通过字符串包含"失败/完成"来推断核心业务状态** —— `test_frontend_never_infers_business_state_from_prose` 用正则扫描全部前端文件，只把"中文字面量直接做比较/包含操作数"判为违规（展示型三元表达式不算），当前 **0 违规**。`test_frontend_does_not_parse_run_message_or_logs` 额外禁止解析 `message/msg/text/log`。证据 ⑯ 用同一套正则复跑并打印结果。
4. **Playwright 覆盖启动、取消、失败修复、READY、发布阻断** —— `test_start_button_creates_real_job_and_survives_refresh`(启动+刷新)、`test_cancel_from_drawer_matches_db`(取消)、`test_failed_job_explains_human_and_retry_recovers`(失败修复+重试)、`test_ready_material_card_shows_production_facts`(READY 成片事实)、`test_publish_blocked_job_tells_user_why`(发布阻断)，再加 `test_running_job_survives_refresh_with_canonical_state`(运行中刷新恢复)。真实 uvicorn + 真实 Chromium，全程演练快照。
5. **commit** —— `phase-12: rebuild web console around canonical jobs and events`。

## 4. 关键实测（详见 `docs/codex/phase12_web_console.txt`）

- **③ 列表与分布**：`count=4`、`total={"total":4,"by_status":{"BLOCKED":1,"FAILED":1,"PAUSED":1,"READY":1}}`，单条投影含 `status/stage/dry/actions`，`dry=true` 来自 `config_snapshot`。
- **④ 详情三态**：READY 的 `summary.actions={"cancel":true,"retry":false,"resume":false}`，FAILED 的 `actions.retry=true` 且 `blocked.human_action="画面质检不合格：需要按要求重出成片。"`，BLOCKED 的 `blocked.human_action` 明说"只能走草稿或人工发布，禁止直发"。
- **⑥ 事件**：`PLANNING -> RESEARCHING -> SCRIPTING -> PREFLIGHT -> GENERATING -> FAILED` 五条 `status_change` 加一条 `stage_failed`，`since=last_id` 返回空。
- **⑧ SSE**：`content-type=text/event-stream`，`event: job` 帧就是 DB 里的 canonical 事件，`event: snapshot` 帧 `source_of_truth=jobstore`。
- **⑪ 真恢复**：PAUSED 任务 `resume` 后后台真跑，`orchestrator.wait()` 结束后 DB 为 `READY`。
- **⑭ runtime**：保存 `gen_concurrency=999` 被判"超出范围 2-10"并**带回原因**，`runtime` 快照里 `daily_target=3` 立刻生效。
- **⑮ 物料卡**：`title="标题：单手拎起"`、`cover="封面：真轻"`、`hashtags=["#轻便","#出行"]`、`qa.latest_score=0.91`、`publish=[douyin/DRAFT]`、`performance.metric_count=3`，`video_url=/media/material_case.mp4`。
- **⑯ 护栏**：扫描 10 个前端文件，中文字面量状态推断 **0 行**、message/日志解析 **0 行**，`ui.js CANONICAL_STAGES == JobState.LINEAR` 与 `CANONICAL_SIDE == JobState.SIDE` 均为 `True`，`app.js=4411` 字节。

## 5. 测试结果

```
ruff check lib tests tools webui s6_publish s7_learn   ->  All checks passed!
定向 55 条（Phase 12 新增 unit）                        ->  55 passed
tests/frontend（3 条 Phase 0 smoke + 6 条 Phase 12）    ->  9 passed
全量 pytest                                            ->  632 passed, 1 skipped（Phase 11 结束为 571+1）
```

| 新增测试文件 | 条数 | 覆盖 |
|---|---|---|
| `tests/unit/test_jobview.py` | 23 | blocked 取码来源（event.data / repairs 兜底）、动作矩阵随状态机、dry 只认 config_snapshot、QA 不编造分数、artifacts 缺文件如实报告、events 增量、materials 只列已产出态、物料卡五要素、`/media` 只对 out 目录内文件开放 |
| `tests/unit/test_webui_jobs_api.py` | 21 | 10 个端点 + limit 边界 + 404 语义 + blocked 人话 + SSE 路由顺序 + SSE 帧格式 + cancel/retry/resume 迁移与守卫 + 同内核校验 + settings runtime/ignored |
| `tests/unit/test_web_console_source.py` | 11 | 静态护栏：禁止中文字面量状态推断、禁止解析 message/日志、装配层体量、store 唯一状态容器、模块导出契约、前端状态与后端一致、模板锚点 |
| `tests/frontend/test_web_console.py` | 6 | 启动+刷新、运行中刷新恢复、取消与 DB 一致、失败修复、READY 成片事实、发布阻断 |

## 6. 本阶段修掉的缺陷

1. **SSE 路由被详情路由抢先匹配（真实 bug）**：`/api/jobs/events` 注册在 `/api/jobs/{uid}` 之后时，FastAPI 会把它当成 `uid="events"` 的详情请求并返回 404。已把 SSE 移到详情之前注册，并加 `test_sse_route_is_registered_before_uid_route` 直接断言 `paths.index("/api/jobs/events") < paths.index("/api/jobs/{uid}")` 守住顺序。
2. **`blocked.code` 永远是空**：events 表**没有 `error_code` 列**，原实现读 `event["error_code"]` 恒为 `None`，导致"为什么需要人工"退化成没有错误码。改为读 `event["data"]["error_code"]`，并兜底取 `repairs[-1].error_code`。
3. **`job.dry_mode` 这个字段根本不存在**：演练标记在 `jobs.config_snapshot` 里。`_dry_of()` 改为解析 `config_snapshot.dry_mode`，**没有快照时返回 `None`**（前端显示 `—`，不猜成 False）。
4. **前端用 `Object.keys(metrics).length` 数指标是错的**：`perf_view` 保留了全部指标列（缺失为 `None`），数 key 会把空列也算进去。改为后端投影 `metric_count`，前端只显示这个数。
5. **Playwright 夹具 `stdout=subprocess.PIPE` 无人读取 -> uvicorn 整个进程被写 stdout 阻塞**：缓冲区（Windows 管道默认几 KB）写满后，uvicorn 卡在 `write()` 上，所有后续请求一律无响应，表现为"前几个用例通过、之后每次 `page.goto` 都 30s 超时，一次运行挂 90 秒"。改为把 stdout/stderr 重定向到日志文件（提前退出时仍读该文件报错）。这是本轮定位耗时最长的缺陷。
6. **`browser.new_page()` 隐式创建的 BrowserContext 从不回收**：每个用例的页面里都有 EventSource 长连接，context 不关就会跨用例堆积。改为显式 `context = browser.new_context()` + teardown `page.close(); context.close()`。
7. **区块标题被 CSS 转成大写，`inner_text()` 返回渲染后文本**：`CreativeDNA` 读回来是 `CREATIVEDNA`，断言失败。断言改为按渲染后文本比对（`drawer.upper()`），顺带证明读到的是用户真正看到的字。
8. **动作成功后抽屉有一段"加载任务详情…"的重载窗口**：测试立刻断言会读到旧标题或 loading 文案。改为 `page.wait_for_function` 等抽屉落定再断言。
9. **重写 `app.js` 时丢了 `window.__AYHMJ_ROOT__` 注入**：Phase 12 把 Hermes 逻辑拆到 `hermes.js` 后，守卫 `test_no_hardcoded_paths::test_frontend_cwd_is_injected_not_hardcoded` 仍要求装配层显式使用服务端注入的项目根。已改为 `Hermes.setRoot(window.__AYHMJ_ROOT__)`，`hermes.js` 内部两处 `cwd` 改读 `this.root`，模块不再直读全局。这是全量 pytest 唯一抓到的回归。
10. **ruff 两项**：`SIM115`（fixture 里的 `open()` 生命周期跨 `yield`，加 `noqa` 并说明由 `finally` 关闭）、`UP031`（造数用 percent format -> f-string）。

## 7. 遗留与限制

1. **Phase 11 的六条遗留全部沿用**：无官方只读采集通道（`fetch_official` 按设计拒绝）、学习结论未回写线上策略、工程默认值待真实数据校准、Phase 6 的 5 条 `needs_verification`、`vision` 仍由 fixture 承载、Phase 10 的 `ai_disclosure_confirmable` 与 `domestic_draft_args` 待人工补齐。
2. **`POST /api/jobs/{uid}/cancel` 的"不可取消"用 404 表达**（沿用 Phase 3 起的约定：`ok=false` -> 404），而不是 400。前端据此展示为"该任务当前不可取消"，没有引入新的状态推断。
3. **`/api/jobs` 的响应结构从裸列表变成 `{count,total,jobs}`**，`/api/job/{uid}`（单数，遗留兼容路由）与 `/api/jobs/{uid}` 一起改为返回 `detail_view`。全仓已确认没有其它调用方，但外部脚本若直连旧结构需要同步。
4. **`dry` 在缺少 `config_snapshot` 的历史任务上为 `None`**，前端显示 `—`。这是刻意的不猜，不是缺字段。
5. **`neural_v4.js` 依赖 ES module 加载顺序**（它从 `js/ui.js` 取 `NeuralStage`），因此模板必须保持 `type="module"` 单入口。
6. **Playwright 用例必须串行**（共享一个 uvicorn 实例与一个 Chromium），并且夹具的 stdout 必须落盘而不是进 PIPE，否则会重现缺陷 5。
