# Phase 4 验收记录 — 任务恢复、幂等、成本保护与 RepairEngine 基础

- 阶段：Phase 4
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 4
- commit：`phase-4: add resumability idempotency and repair policies`

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| error taxonomy（新） | `lib/orchestrator/errors.py` | 计划要求的 **20 个业务 error_code** 全部登记；`TRANSIENT_CODES` / `RETRYABLE_CODES` / `PERMANENT_CODES` 三分类；`REPAIR_MAP`（error_code → 白名单动作）；`backoff_delay()`；`classify_exception()`（供应商文案 → error_code） |
| 阶段策略（新） | `lib/orchestrator/policies.py` | 每个 stage 声明 `max_attempts / max_cost / repairable / timeout`；未登记的阶段一律最保守（跑 1 次、不许重试） |
| 幂等指纹（新） | `lib/orchestrator/idempotency.py` | `fingerprint = sha256(job + stage + prompt_hash + refs_hash + workflow)`；`fingerprint_parts()` 供 artifact/event 追溯复现 |
| 供应商适配（新） | `lib/orchestrator/providers.py` | `ProviderTask` + `ProviderAdapter` 协议 + `AutoDLProvider`；所有供应商异常翻译成 taxonomy 异常，业务层不再碰 AutoDL 私有字段 |
| 幂等生成驱动（新） | `lib/orchestrator/generation.py` | 提交前算指纹 → 命中已提交任务则**只 query** → 否则提交并**立即落 `provider_tasks`** → 轮询 → 下载（只重下）；prompt 超限在付费前压缩/阻断 |
| RepairEngine（重写） | `lib/orchestrator/recovery.py` | 白名单决策：`RETRY_SAME / SWITCH_WORKFLOW / COMPRESS_PROMPT / REGENERATE_SHOT / REBUILD_SUBTITLE / WAIT_AND_RESUME / REQUIRE_HUMAN / ABORT`；每条 decision 带 reason，写入 events |
| 幂等表（新） | `lib/migrations.py`（v3）、`lib/jobstore.py` | `provider_tasks(job_id, fingerprint, task_id, status, output_path, cost, error_code)` + `upsert/find/list/finish_provider_task` |
| 编排接线 | `lib/orchestrator/service.py` | generate 阶段改用幂等驱动；stage 级 `max_cost` 预留检查（付费前拦停）；瞬时错误指数退避；终态语义按 repair 动作决定（PAUSED/BLOCKED/FAILED）；修复 `config_snapshot` 从未落库的真实缺陷 |
| 阶段实现 | `lib/orchestrator/stages.py` | `stage_generate` 走幂等驱动；落 `onetake_task.json` / `onetake_result.json` 快照；`StageContext` 增加 `provider / sleep / poll_interval / max_wait / download_retries` 注入点 |
| 生成 CLI | `s4_generate/gen_one_take.py` | 重写为**薄 CLI 包装**（唯一实现是 `generation.py`），命令行手动跑与编排器自动跑是同一代码路径 |
| 测试隔离 | `lib/__init__.py`、`tests/frontend/test_webui_smoke.py` | `STATE_DIR` 支持 `AYHMJ_STATE_DIR` 覆盖；前端 smoke 的 uvicorn 改跑临时 state（修复"测试污染真实 state/pipeline.db"缺陷） |
| 测试 | `tests/unit/test_repair_policies.py`（18 例）、`tests/unit/test_idempotency.py`（13 例）、`tests/unit/test_migrations.py`（v3 断言） |
| 证据 | `docs/codex/phase4_idempotency_repair.txt`、`docs/codex/phase4_cli_smoke.txt` |

## 2. 幂等生成链路

```text
stage_generate
      ↓
ensure_prompt_budget()          ← 付费前：>10000 字压缩，压不下去就 PromptTooLong（提交数 0）
      ↓
fingerprint(job, stage, prompt, refs, workflow)
      ↓
provider_tasks 命中 task_id ? ── 是 ─→ provider.query(task_id)   ← 只查询，绝不重新 create_task
      │ 否
      ↓
provider.submit() → **立即** upsert provider_tasks(task_id)      ← 崩溃也丢不掉
      ↓
轮询（瞬时错误退回退避继续；业务错误立刻定性）
      ↓
provider.download()  ← 失败只重下（1 + download_retries 次），永不重生成
      ↓
provider_tasks.status = DONE + output_path + cost
```

## 3. error taxonomy（计划要求的 20 个业务码）

| error_code | RepairEngine 动作 | 类别 |
|---|---|---|
| CONFIG_MISSING / AUTH_EXPIRED / ASSET_MISSING | REQUIRE_HUMAN | 业务（永久） |
| NETWORK_TRANSIENT / RATE_LIMIT | RETRY_SAME（指数退避 2→4→8…≤60s） | 瞬时 |
| PROMPT_TOO_LONG | COMPRESS_PROMPT | 输入 |
| PROVIDER_REJECTED / GENERATION_TIMEOUT | SWITCH_WORKFLOW | 供应商 |
| GENERATION_FAILED | RETRY_SAME | 供应商（可重试） |
| DOWNLOAD_FAILED | RETRY_SAME（只重下） | 供应商（可重试） |
| ASR_MISMATCH / SUBTITLE_ALIGN_FAIL | REBUILD_SUBTITLE | 质检 |
| VISUAL_QA_FAIL / PRODUCT_DEFORMED / WRONG_SPEAKER / HUMAN_ANATOMY_FAIL | REGENERATE_SHOT | 质检 |
| COMPLIANCE_BLOCK | REQUIRE_HUMAN | 合规 |
| PUBLISH_QUOTA | WAIT_AND_RESUME（→ job PAUSED） | 发布 |
| PUBLISH_AUTH | REQUIRE_HUMAN | 发布 |
| UNKNOWN | ABORT | 兜底 |

白名单动作只有这 8 个；`REPAIR_MAP` 之外的 error_code 一律 ABORT（绝不猜、绝不自由 Agent）。

## 4. 验收场景逐条对照

| 验收场景 | 结果 | 证据 |
|---|---|---|
| 模拟 H3 `create_task` 成功后进程崩溃；重启后只 query 原 task，不产生第二个提交 | ✅ | `test_idempotency.py::test_crash_after_submit_never_resubmits`（提交数 1 → 崩溃 → 重启后 `reused=True`、提交数仍 1、query 次数 >0）；编排层 `test_orchestrator_crash_then_retry_keeps_single_submission`；证据 §C |
| 模拟 provider SUCCESS、下载失败两次；最终只发生下载重试 | ✅ | `test_download_failure_only_retries_download`（提交数 1、download 3 次）；`test_download_exhausted_does_not_resubmit`（下载全失败也不重提交，行落 `FAILED/DOWNLOAD_FAILED`）；证据 §D |
| 模拟 prompt 超 10000 字；系统在付费前压缩/阻断，AutoDL 提交数为 0 | ✅ | `test_prompt_too_long_blocks_before_any_submission`（`submit_count == 0`、`provider_tasks` 空）；`test_ensure_prompt_budget_compresses_then_blocks`（重复行可压回安全线）；证据 §B（26489 字 → 阻断、提交 0） |
| 模拟连续 3 次 generation failed；达到上限后 job BLOCKED/FAILED，不无限烧钱 | ✅ | `test_retryable_stage_retries_then_stops` + `test_attempts_exhausted_aborts`；证据 §E（执行 3 次 → FAILED/GENERATION_FAILED、成本 ¥0） |
| 模拟 publish quota；系统等待/调度，不把它当生成失败 | ✅ | `test_publish_quota_waits_instead_of_counting_as_generation_failure`（动作 WAIT_AND_RESUME、终态 PAUSED）；`test_quota_failure_pauses_job_not_fails`（job=PAUSED + `PUBLISH_QUOTA`，decision 落 events）；证据 §F |
| 每个 provider 提交前生成 idempotency fingerprint | ✅ | `test_fingerprint_is_deterministic_and_sensitive`（prompt/workflow/job/stage/refs 任一变化指纹必变）；`test_refs_hash_tracks_file_size` |
| 保存 task id 后立即落 DB，再进入轮询 | ✅ | `generation.py` 在 `submit()` 之后、`_poll()` 之前 `upsert_provider_task`；证据 §C 显示崩溃时 task_id 已可查 |
| 每个 stage 定义 `max_attempts / max_cost / repairable` | ✅ | `lib/orchestrator/policies.py::STAGE_POLICIES`；`test_every_stage_declares_policy` |
| job 定义总成本预算，超过预算自动 `BLOCKED_BUDGET` | ✅ | `test_job_budget_blocks_paid_stage_before_spending`（已花 0.5 + 本阶段上限 1.2 > 预算 1.0 → 付费前拦停）、`test_job_budget_blocks_when_already_over` |
| RepairEngine 只按 error_code 选动作（不做自由 Agent） | ✅ | `recovery.py::RepairEngine.decide()` 唯一数据源是 `errors.REPAIR_MAP`；`test_stage_policy_whitelist_blocks_out_of_scope_codes` 证明阶段白名单优先 |
| 修复动作必须是白名单 | ✅ | `test_every_repair_action_is_whitelisted`（动作集合恰好 8 个） |
| 所有 repair decision 写入 events 并记录为什么这样修 | ✅ | `stage_failed` 事件携带 `decision` / `reason` / `repair`(完整 decision)；`test_quota_failure_pauses_job_not_fails` 断言 |
| transient 网络错误指数退避；业务错误不允许网络式无限重试 | ✅ | `test_backoff_is_exponential_and_capped`；`test_business_error_is_not_retried_forever`（COMPLIANCE_BLOCK → REQUIRE_HUMAN，不重试） |
| commit 名 | ✅ | `phase-4: add resumability idempotency and repair policies` |

## 5. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q
141 passed, 1 skipped in 8.3s          # 1 skipped = paid placeholder；Phase 3 结束为 110

$ .venv/Scripts/python.exe -m pytest -m frontend -q
3 passed, 139 deselected in 2.5s

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
```

`docs/codex/phase4_cli_smoke.txt` 记录了同一轮的 ruff / pytest / `orchestrate.py start --dry`
/ `status` / `run_all.py` 原始输出。

## 6. 本阶段修掉的既有缺陷

1. **`config_snapshot` 从来没落库**：spec 来自 `queue_15s/` 时，job 由 `sync_queue()` 先创建，
   `start()` 的 `else` 分支只写 fingerprint、不写快照 → `resume/retry` 永远用默认配置
   （重试时阶段列表会退回全量 6 阶段）。现在改为真的 `set_fields(config_snapshot=...)`。
2. **前端 smoke 污染真实 `state/pipeline.db`**：`pytest` 跑 `tests/frontend` 时会起真实 uvicorn，
   其 `/api/start` 写入仓库内 `state/`。现在 `STATE_DIR` 支持 `AYHMJ_STATE_DIR` 覆盖，
   前端 fixture 显式指向临时目录；实测跑完整套测试后真实库 jobs 数不再变化。
   （本次因此进入真实库的 8 条 dry 占位任务已按 UID 模式精确清理，真实库回到
   `counts={"total": 0}`。）

## 7. 遗留与限制（交给后续 Phase）

- `stage_generate` 现在是**进程内**调用 AutoDL（幂等驱动），不再起 `gen_one_take.py` 子进程；
  compose 仍然通过 `tools/make_15s.py run --skip-gen` 子进程执行（Phase 9 再拆细）。
- `prescreen` / `publish` 只是登记了策略（`max_cost`/`repairable`），真正的预检与发布接线
  在 Phase 7 / Phase 10。
- `REPAIR_MAP` 里 `REGENERATE_SHOT` / `REBUILD_SUBTITLE` / `SWITCH_WORKFLOW` 目前由
  generate 阶段的"同阶段重跑 / 换链"承接；等 QA Critic（Phase 8）与后期统一（Phase 9）
  落地后，这些动作会各自映射到真正的修复实现。
- 跨进程不做互斥（CLI 与 WebUI 同时跑）仍靠 JobStore 状态机 + `provider_tasks` 唯一约束
  保证不写坏数据；进程级锁留到 Phase 12/13 的并发收口。
