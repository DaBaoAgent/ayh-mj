# Phase 3 验收记录 — 建立唯一 PipelineOrchestrator，打通 WebUI/Hermes/CLI

- 阶段：Phase 3
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 3
- commit：`phase-3: centralize execution in pipeline orchestrator`

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 编排内核（新） | `lib/orchestrator/service.py` | `PipelineOrchestrator.start/resume/retry/cancel/wait/status/recover_interrupted`；job 级线程池上限 = `gen_concurrency`；协作式取消（`CANCEL_REQUESTED` → kill 子进程树 → `CANCELLED`） |
| 阶段契约（新） | `lib/orchestrator/models.py` | `StageResult(success/artifacts/metrics/error_code/message/next_action)`、`RunConfig`（配置快照）、`StageContext`（子进程执行器，Cancel 可终止） |
| 阶段实现（新） | `lib/orchestrator/stages.py` | plan / preflight / generate / qa / compose / package；检查类在进程内完成，生成与后期调既有脚本（`s4_generate/gen_one_take.py`、`tools/make_15s.py run --skip-gen`），**全部幂等** |
| 错误与恢复（新） | `lib/orchestrator/errors.py`、`lib/orchestrator/recovery.py` | 稳定 `error_code`（NO_SPEC/PREFLIGHT_FAILED/GENERATION_FAILED/QA_FAILED/COMPOSE_FAILED/BLOCKED_BUDGET/CANCEL_REQUESTED…）+ `RepairEngine.decide()` 白名单决策 + 重启收敛 |
| CLI adapter | `tools/orchestrate.py`（新）、`tools/run_all.py`（重写） | `orchestrate.py` 是唯一 CLI；`run_all.py` 降级为参数翻译器（不再扫队列/推状态/写 run_status.json） |
| WebUI | `webui/server.py` | `/api/start` 创建**真实 Job**（不再起脚本子进程）；`/api/state` 数据源改为 Orchestrator/JobStore；`/api/logs` SSE 改读 JobStore event stream；`/api/stop` 改协作式取消；新增 `/api/jobs/{uid}/cancel|retry|resume`；lifespan 启动时收敛遗留任务 |
| Hermes | `webui/hermes_bridge.py` | 新增 `request_production()` / `production_status()` —— Hermes 生产请求走的与 WebUI 完全同一个 Orchestrator 接口 |
| 状态机 | `lib/jobstore.py` | 旁路状态（PAUSED/BLOCKED/FAILED）现在也可直接转 `CANCELLED`（人工终止意图永远有效）；新增 `recent_events()/max_event_id()` 供 SSE 用 |
| 测试 | `tests/unit/test_orchestrator.py`（新，17 例） | 覆盖本阶段全部验收标准 |
| 证据 | `docs/codex/phase3_orchestrator_cli.txt`、`phase3_failure_paths.txt`、`phase3_webui_wiring.txt`、`phase3_restart_recovery.txt` | CLI / 失败路径 / WebUI 接线 / 重启恢复 的原始输出 |

## 2. 唯一执行链路

```text
        WebUI  POST /api/start ─┐
        CLI    tools/orchestrate.py start ─┤
        Hermes hermes_bridge.request_production ─┤
                                            ↓
                             lib.orchestrator.start_production()
                                            ↓
                        PipelineOrchestrator（唯一执行内核）
                  ┌─────────────────┴──────────────────┐
             JobStore（唯一事实源）              阶段执行 + 取消 + 并发
        jobs/attempts/artifacts/events            plan→preflight→generate
                                                →qa→compose→package
                                            ↓
                              WebUI /api/state / /api/logs(SSE)
```

## 3. 阶段与 canonical 状态

| stage | 推进的 canonical 状态 | 产物/指标 |
|---|---|---|
| plan | RESEARCHING → SCRIPTING | spec artifact |
| preflight | PREFLIGHT | 台词字数/句数 + prompt 长度 + 对白门禁（0 ERROR） |
| generate | GENERATING | `out/gen_<uid>/onetake.mp4` + `cost` |
| qa | QA | 成片存在性/大小/时长 + `evaluations(qa_basic)` |
| compose | COMPOSING | `onetake_final.mp4`（裁剪/字幕/BGM/音效/归档） |
| package | PACKAGING → READY | final + archive artifact |

Status 只经 `JobStore.transition()`；每阶段写 `stage_start` / `stage_end` / `stage_failed`
事件（含 metrics、耗时、尝试次数），下游在任一阶段失败时立即停止。

## 4. 验收标准逐条对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| WebUI / CLI / Hermes 启动的任务在 DB 中结构完全一致 | ✅ | `test_orchestrator.py::test_webui_cli_hermes_create_identical_jobs`：三条入口各建 1 个 dry job，比较 jobs 列集合 + config_snapshot 键集合 + 事件类型序列 + 终态，全部相等 |
| `daily_target=2` → 恰好 2 个 job，不多不少 | ✅ | `test_daily_target_creates_exactly_that_many_jobs`（两次启动各 2 条、uid 不重叠、总数 4）；`docs/codex/phase3_orchestrator_cli.txt` 真实 CLI 输出 2/2 |
| `gen_concurrency` 真正限制并行任务数 | ✅ | `test_gen_concurrency_limits_parallel_jobs`：6 个任务 + `gen_concurrency=2` → generate 阶段实测并发峰值 = 2（线程池上限即该值） |
| Stop/Cancel 后无孤儿子进程，job 明确进 `CANCELLED` | ✅ | `test_cancel_is_cooperative_and_leaves_no_orphan`：generate 阶段真起一个 `python -c sleep 30` 子进程，cancel 后 `proc.poll() is not None` + job=CANCELLED + `cancel_requested`/`cancelled` 事件；另有 `test_cancel_without_active_handle_is_immediate`、`test_cancel_all_only_touches_running_jobs`（Stop 不动 READY/PLANNING） |
| 重启 WebUI 不影响已存在 job 的查询与恢复 | ✅ | `test_restart_recovers_interrupted_jobs`（新实例 → `recover_interrupted()` → PAUSED → 可查询 → `resume()` 从 generate 续跑到 READY）；`docs/codex/phase3_restart_recovery.txt` 真实 DB 演示 |
| WebUI `/api/start` 创建真实 Job（不是简单起脚本子进程） | ✅ | `docs/codex/phase3_webui_wiring.txt`：`/api/start` 返回 `run_id` + `jobs[]` + config 快照；`/api/state` 的 `run.source_of_truth == "jobstore"` |
| settings（daily_target/concurrency/publish/engage/platforms）落进运行时 config snapshot | ✅ | `RunConfig.to_dict()` → `jobs.config_snapshot`（`docs/codex/phase3_orchestrator_cli.txt` 可见 dry_mode/stages/publish_platforms 等）；`resume/retry` 从快照重建配置 |
| 所有 stage 输出结构化 `StageResult` | ✅ | `lib/orchestrator/models.py::StageResult`；attempts 表按 stage 落 status/error_code/cost/message，events 落 metrics |
| 任一 stage 失败必须停止下游 | ✅ | `test_stage_failure_stops_downstream`：preflight 失败 → 实际只跑了 plan+preflight，job=FAILED/`PREFLIGHT_FAILED`；`docs/codex/phase3_failure_paths.txt` 真实 NO_SPEC 失败（cost=0） |
| SSE/WebUI 从 JobStore event stream 获取状态 | ✅ | `webui/server.py::api_logs` 读 `store.recent_events()`；证据文件里 SSE 帧为 `event/log/status`，event 即 JobStore 事件 |
| 旧 `/api/state` 保留但数据源改为 JobStore/Orchestrator | ✅ | `api_state()` 返回 `orchestrator.status()`；`run_status.json` 读取逻辑与 `engine_alive()` 已删除 |
| Stop 为 cooperative cancellation（记 `CANCEL_REQUESTED`） | ✅ | `cancel_one()` 先写 `cancel_requested` 事件，再 kill 进程树；无活动句柄时直接落 `CANCELLED` |
| commit 名 | ✅ | `phase-3: centralize execution in pipeline orchestrator` |

## 5. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q
110 passed, 1 skipped in 7.46s        # 1 skipped = paid placeholder

$ .venv/Scripts/python.exe -m pytest -m frontend -q
3 passed, 108 deselected in 2.47s

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
```

**AutoDL 付费任务提交数 = 0**：本阶段所有测试与证据运行都是 dry-run 或本地 SQLite 操作，
真实 `state/pipeline.db` 在证据采集后已清理回 `counts={"total": 0}`。

## 6. 遗留与限制（交给后续 Phase）

- `preflight` 的门禁实现复用 `tools/make_15s.py`（同一份口径），compose 仍调
  `make_15s.py run --skip-gen`；阶段内部的进一步拆分（转写/字幕/混音各自成 stage）
  留到 Phase 9「后期统一」。
- `plan` 目前只做"取 spec / 占位"：真正的 Planner + Trend Research + CreativeDNA
  在 Phase 5，本阶段不做选题生成。
- 错误 taxonomy 只有本阶段用到的子集；20 个 error_code 的完整清单与预算保护细节在
  Phase 4 落地（本阶段已有最小可用版本：`cost_spent >= budget_cap` 时在付费阶段前
  返回 `BLOCKED_BUDGET`）。
- 前端仍是旧的 6 段进度条（把 canonical stage 映射回旧的 6 个 id）；完整
  job 列表 / cancel / retry / resume 的 UI 在 Phase 12 重构。
- 同一进程内的 `orchestrator` 是单例；跨进程（CLI 与 WebUI 同时跑）不做互斥，
  仅靠 JobStore 状态机保证不会写坏数据。
