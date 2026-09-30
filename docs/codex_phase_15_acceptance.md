# Phase 15 验收记录 — 最终端到端验收

- 阶段：Phase 15
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 15（含 15.1–15.7）
- commit：`phase-15: accept autonomous end-to-end pipeline`
- 原始证据：
  - `docs/codex/phase15_verification.txt`（12 节实测：环境/基线 · ruff · 全量 pytest · marker 纪律 ·
    Phase 15 全部用例逐条 · §15.1 十五条对照 · 20 条自主规划多样性表 · 成本幂等 · 故障恢复 ·
    发布安全 · 全链/学习/多样性 · §15.5 未执行说明）
  - `docs/codex/phase15_ci_guardrails.txt`（CI 门禁 7 步原始输出）

> 本阶段**不新增功能**：只补验收装置（fake provider / fixture media / fake 发布通道）+ 修验收中查出的缺陷。
> 全部自动测试 0 网络、0 付费、0 真实发布；任何真实 `create_task` 都会被 monkeypatch 成 `AssertionError`。

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 新增验收装置 | `tests/p15_support.py` | 5 类 fixture 替身：① 台词稿（写作步骤 `docs/onetake_lines_<uid>.txt` 的替身，与「fixture media 替真实成片」同口径）；② QA 证据（vision/transcript/subtitle 按 spec 现造，缺陷用关键字注入）；③ 后期渲染（落 `onetake_final.mp4`，验片仍走产线真实门禁）；④ `FakePublishAdapter`；⑤ 多样性统计（按 CreativeDNA 维度）。**判定逻辑一律是真实实现**（`lib.qa.critic` / `lib.orchestrator.stages._qa_gate` / `PublishService`）。 |
| 新增验收用例 | `tests/integration/test_p15_full_chain.py`(10) · `test_p15_router_prescreen.py`(3) · `test_p15_qa_repair.py`(6) · `test_p15_cost_idempotency.py`(6) · `test_p15_recovery.py`(9) · `test_p15_diversity.py`(2) · `test_p15_publish_safety.py`(21) · `test_p15_learning_reflow.py`(2) | 59 条，逐条对应 §15.1–§15.6 的验收条目（对照表见 §4 与证据 §⑥）。 |
| 平台风控信号分类（缺陷修复） | `lib/contracts.py`（+`POSTFLOW_HUMAN_MARKERS` / `postflow_needs_human`）· `s6_publish/publish.py`（+`_needs_human` / `_failure_status`） | §15.6 要求「账号异常、平台验证码、风控提示一律 REQUIRE_HUMAN，不做绕过」，此前这类提示会被当成普通 `FAILED`。现在**风控信号优先于凭据信号**判定，返回 `REQUIRE_HUMAN`。 |
| 发布熔断与伪成功（缺陷修复） | `lib/orchestrator/publishing.py` | ① 新增 `NEEDS_HUMAN` 状态：与 `AUTH_EXPIRED` 同一处理（`pause_platform` 熔断该平台），但错误码是 `REQUIRE_HUMAN_PUBLISH`；② `_finalize()` 修「**一条都没真发出去却记 DONE**」：平台处于暂停态重入时停在 `PAUSED`（`error_code=PLATFORM_PAUSED`），不再产生伪成功；③ `_mode_of()` 对 `brief=None` 不再 `AttributeError`（演练路径必须能如实报「物料缺失」）。 |
| 定时 bug（验收中查出） | `tests/integration/test_p15_diversity.py` | `zip()` 缺 `strict=` 导致 ruff 红灯 —— 修掉。 |

## 2. 计划验收标准逐条

### §15.1 无付费全链（15 条 → 全部通过）

| # | 计划要求 | 证据 | 结果 |
|---|---|---|---|
| 1–2 | 空 queue、`daily_target=5` 由 Planner 自动建 5 个 job | `test_autonomous_chain_plans_five_jobs_without_manual_specs` / `test_every_job_reaches_an_expected_state` | PASS |
| 3 | genre/hook/shot_pattern 至少三维结构差异 | `test_planned_dimensions_are_structurally_varied` | PASS |
| 4 | Research / CreativeDNA / StorySpec / compiled prompt 均可查询 | `test_creative_artifacts_and_compiled_prompt_are_queryable` | PASS |
| 5 | Claims Gate 阻断故意注入的虚假参数 | `test_claims_gate_blocks_injected_fabrication_before_paid_generation` | PASS |
| 6 | Prescreen 只对高风险任务触发 | `test_high_risk_spec_needs_a_real_prescreen_before_paid_generation`（+ low-risk 反例） | PASS |
| 7 | Router 首选 workflow 失败 → 正确 fallback | `test_rejected_preferred_workflow_falls_back_without_double_charging` | PASS |
| 8 | QA 分别识别错嘴 / 产品形变 / ASR 漏词 / 字幕失败 | `test_each_defect_class_is_detected_and_repaired_in_place`（4 个参数） | PASS |
| 9 | RepairEngine 按 error_code 执行不同动作 | `test_repair_engine_dispatches_every_error_code_to_its_own_action` | PASS |
| 10 | 修复到上限 → BLOCKED，不无限循环 | `test_repair_limit_blocks_instead_of_looping_forever` | PASS |
| 11 | 后期只用一份 canonical transcript | `test_post_stage_keeps_exactly_one_canonical_transcript` | PASS |
| 12 | Packaging 出标题/描述/claim_ids/AI 声明 | `test_every_ready_job_carries_complete_packaging` | PASS |
| 13 | Publish fake 适配器幂等（同一 job 重试不重复发帖） | `test_same_external_id_is_never_posted_twice`（+ `test_gate_pass_publishes_once_with_ai_disclosure_recorded`） | PASS |
| 14 | 表现 fixture 回流后 Planner 下一轮评分合理变化 | `test_next_planned_job_carries_the_reflowed_history`（+ `test_same_candidates_are_scored_differently_after_reflow`） | PASS |
| 15 | WebUI 全程与 JobStore 状态/attempt/cost/QA/repair 一致 | `test_webui_reports_the_same_truth_as_jobstore` | PASS |

**§15.1 通过标准**：5/5 job 达到预期终态（DONE 或人为设计的 BLOCKED）✓；无 orphan process ✓
（`test_batch_leaves_no_orphan_handle_or_uncaught_failure`）；无未捕获异常 ✓；无重复 provider submit ✓
（`test_batch_submits_each_paid_task_exactly_once`）；无非法状态跳转 ✓（状态机 `transition` 是唯一入口，
非法转换抛 `InvalidTransition`）；DB/event/artifact 可完整追踪每个 job ✓（全链用例断言 job→attempts→artifacts→events 链完整）。

### §15.2 故障恢复（8 项注入 → 逐项有明确预期）

| 故障 | 预期行为 | 用例 | 结果 |
|---|---|---|---|
| WebUI 进程重启 | 从 DB 恢复真实状态；无残留 running handle | `test_panel_restart_reads_the_db_and_leaves_no_running_handles` | PASS |
| submit 后进程立即退出 | 重启只 query，不重复提交（不重复付费） | `test_exit_right_after_submit_resumes_with_query_only` | PASS |
| 网络查询超时 | 退避续轮询，不换链、不重提交 | `test_transient_query_timeout_retries_instead_of_resubmitting` | PASS |
| provider SUCCESS 后下载失败 | 只增加 download 次数，不重提交 | `test_download_failure_after_success_only_retries_download` | PASS |
| SQLite 短暂锁 | 等锁通过（timeout 30s），不丢事件/不丢状态 | `test_short_sqlite_lock_is_waited_out_not_lost` | PASS |
| SQLite 硬错误 | 停在下游之前，0 付费、0 artifact，且可恢复 | `test_hard_sqlite_error_stops_before_paying_and_stays_recoverable` | PASS |
| 磁盘空间不足 | 下游停止，不产生伪成功 artifact | `test_disk_full_stops_downstream_without_fake_artifact` | PASS |
| 缺字体 / 缺 ffmpeg / 缺 Upload-Post key | 进 DEGRADED/BLOCKED 并给出具体修复提示 | `test_missing_capabilities_report_status_and_a_fix_without_crashing` · `test_capability_blocked_stops_downstream_and_explains_the_fix` | PASS |

### §15.3 成本与幂等（7 条 → 全部通过）

| 计划要求 | 用例 | 结果 |
|---|---|---|
| 统计 create/query/download 调用次数 | `test_repeat_generation_reuses_the_submitted_task` | PASS |
| 同一 attempt 重跑不得重复 create_task | 同上（`provider_reused`，DB 只有一条 `provider_tasks`） | PASS |
| 下载失败只增加 download 次数 | `test_download_failure_only_costs_extra_download_attempts` | PASS |
| provider 业务拒绝不得当网络异常无限重试 | `test_business_rejection_is_bounded_not_retried_as_network` | PASS |
| 每个 job 显示预估/已发生/repair/总成本 | `test_costs_are_reported_separately_for_job_and_repairs` | PASS |
| 超预算立即 BLOCKED_BUDGET | `test_budget_cap_blocks_before_any_paid_submission` | PASS |
| prescreen 成本与正式生成成本分别记录 | `test_prescreen_outcome_never_mixes_into_generation_cost` | PASS |

### §15.4 成片多样性（20 条真实规划实测，证据 §⑦）

- 10 条全部为两人对话？**不是**（20 条里 10 条双人对白，含 4 条无对白、2 条字幕驱动、1 条画外音旁白）。
- genre **10 种**（≥5 ✓）· hook_type **8 种**（≥5 ✓）· shot_pattern **10 种**（≥4 ✓）· dialogue_mode 6 种 · cast_pattern 9 种 · angle 20 种。
- 至少 1 条低对白/无对白 ✓（7/20）。
- 点名题材全部命中：Vlog/生活流 1 条（G7）· 悬念 1 条（G9）· 实验/对比 2 条（G10）· 喜剧魔性或 POV 3 条（G3/G8）。
- 相邻作品不得复用 `genre+hook+angle+cast` 完整组合 ✓（重复项 `[]`）。
- 骨架签名 20/20 唯一、选题 20/20 唯一、同日两批**零重叠** ✓（就是「相似度超阈值 → 重新规划」的直接证据）。
- 需预筛（高风险）1/20 —— prescreen 只在真高风险候选上触发，不是无脑全跑（§15.1 第 6 条同口径）。

### §15.5 真实生成验收（受预算保护）—— `NOT ACCEPTED`（未执行）

未执行，如实记录：计划要求「只有以上无付费测试全绿后才允许执行」，且必须**显式配置 cost cap**，
并明确「如果用户没有显式开启真实发布，最终验收只到 READY/草稿」。本轮为自动迭代，未获得付费授权、
未显式开启 `real_publish`，因此**没有执行任何真实 H3 生成**：

- live/paid 执行情况：**未执行**（`AYHMJ_RUN_LIVE` / `AYHMJ_RUN_PAID` 未设置；CI 会强制清除这两个变量）。
- 实际成本：**0 元**。
- task id 数量：**0**。
- 交付边界：所有任务停在 `READY`（packaging 已生成）或人为设计的 `BLOCKED`；未真发任何社媒。
- 该条按计划第 10 条要求写 `NOT ACCEPTED`，不用「基本完成」替代。

### §15.6 发布安全（全部通过）

| 计划要求 | 用例 | 结果 |
|---|---|---|
| `real_publish=false` 时任何路径都不得真发 | `test_dry_paths_never_reach_the_adapter`（显式 false / 配置 false / 无配置三条路径，适配器 0 调用、0 记录、状态不变）· `test_dry_run_still_reports_gate_failure_without_publishing` | PASS |
| `real_publish=true` 也要过 artifact 完整性 Gate | `test_missing_artifact_blocks_before_any_publish` | PASS |
| 过 AI 声明 Gate | `test_ai_disclosure_without_draft_channel_requires_human` | PASS |
| 过 Claims Gate | `test_unmapped_claim_in_publish_copy_is_blocked` | PASS |
| 过 quota / time window Gate | `test_quota_block_stops_before_the_adapter` | PASS |
| 平台 auth 异常触发熔断，不循环登录/连续发布 | `test_auth_expired_pauses_the_platform_and_never_loops`（第二次发布适配器 0 调用） | PASS |
| 同一 post external_id 幂等 | `test_same_external_id_is_never_posted_twice` | PASS |
| 自动评论命中价格/医疗/投诉红线 → 转人工 | `test_red_line_comments_go_to_human_and_are_never_answered`（3 条红线，`create_comment` 0 调用） | PASS |
| 账号异常/平台验证码/风控提示 → REQUIRE_HUMAN，不绕过 | `test_real_adapter_risk_signal_end_to_end_requires_human` · `test_platform_risk_control_is_recorded_as_require_human` · `test_cli_adapter_classifies_platform_risk_as_require_human`（4 种文案）· `test_cli_adapter_keeps_plain_failure_and_auth_failure_distinct`（反例：普通失败仍 FAILED、纯凭据失效仍 AUTH_EXPIRED） | PASS |

### §15.7 最终 Acceptance Report

见 `docs/codex_final_acceptance.md`（10 项齐全，含最终 commit SHA、各 Phase commit、schema version、
测试命令与结果、live/paid 是否执行、10 条 CreativeDNA 多样性统计、故障恢复结果、仍需人工的能力清单、
已知限制、`NOT ACCEPTED` 项）。

## 3. 验收执行记录

| 命令 | 结果 |
|---|---|
| `.venv/Scripts/python.exe -m ruff check lib tests tools webui s6_publish s7_learn` | `All checks passed!` |
| `.venv/Scripts/python.exe -m pytest -m "not live and not paid" -q` | **800 passed, 1 deselected**（362.5s） |
| `tests/unit` / `tests/contract` / `tests/integration` / `tests/frontend` | 628 / 50 / 113 / 9 passed（marker 纪律 4/4 ok） |
| `.venv/Scripts/python.exe -m pytest tests/integration -k p15 -v` | **59 passed, 54 deselected** |
| `.venv/Scripts/python.exe tools/ci.py` | **7/7 PASS**（lint · typecheck · unit · contract · integration · frontend · migration，总耗时 365.6s） |
| 数据库 | `SCHEMA_VERSION = 4`，`applied = [1, 2, 3, 4]` |

## 4. §15.1–§15.6 用例清单（59 条）

- `test_p15_full_chain.py`（10）：自主建 5 job · 终态 · 逐次付费提交唯一 · 无 orphan/未捕获异常 ·
  创意 artifact 与编译 prompt 可查 · 三维结构差异 · Claims 拦注入虚假参数 · 单一 canonical transcript ·
  每条 READY 都有完整 packaging · WebUI 与 JobStore 一致。
- `test_p15_router_prescreen.py`（3）：低风险免预筛 · 高风险必须真预筛 · 首选 workflow 被拒后 fallback 不重复付费。
- `test_p15_qa_repair.py`（6）：4 类缺陷各自被识别并原地修复 · error_code → 动作分派全覆盖 · 修复到上限 BLOCKED。
- `test_p15_cost_idempotency.py`（6）：重复生成复用已提交任务 · 下载失败只加下载次数 · 业务拒绝有界 ·
  预算拦截 · 成本分项 · prescreen 成本不混入生成成本。
- `test_p15_recovery.py`（9）：§15.2 八项故障 + 能力缺失阻断。
- `test_p15_diversity.py`（2）：10 条硬指标 · 同日第二批重新规划。
- `test_p15_publish_safety.py`（21）：§15.6 九条要求 + 失败按平台独立记录 + 幂等。
- `test_p15_learning_reflow.py`（2）：同一批候选评分变化 + 方向合理 · 下一轮 plan_for 带回流历史。

## 5. 新增/修改文件清单

**新增**：`tests/p15_support.py`、`tests/integration/test_p15_full_chain.py`、
`tests/integration/test_p15_router_prescreen.py`、`tests/integration/test_p15_qa_repair.py`、
`tests/integration/test_p15_cost_idempotency.py`、`tests/integration/test_p15_recovery.py`、
`tests/integration/test_p15_diversity.py`、`tests/integration/test_p15_publish_safety.py`、
`tests/integration/test_p15_learning_reflow.py`、`docs/codex_phase_15_acceptance.md`、
`docs/codex_final_acceptance.md`、`docs/codex/phase15_verification.txt`、
`docs/codex/phase15_ci_guardrails.txt`。

**修改**：`lib/contracts.py`、`s6_publish/publish.py`、`lib/orchestrator/publishing.py`。

## 6. 本阶段修掉的缺陷

1. **平台风控/验证码被当成普通失败**：`s6_publish/publish.py` 只按「凭据失效 / 其它」二分，一条
   「请求过于频繁，请完成验证码」会被记成 `FAILED` 并让流程继续 —— 这正是 §15.6 明确禁止的「绕过」。
   改为 `_failure_status()`：风控信号优先 → `REQUIRE_HUMAN`，并暂停该平台。
2. **一条都没发出去却记 DONE（伪成功）**：平台熔断后人工把 job 放回 READY 再发布，`_finalize()` 把
   `PLATFORM_PAUSED`（中性）算成「全绿」，任务直接 `LEARNING → DONE` —— WebUI 与统计会以为已经发布过。
   改为：没有任何平台成功时停在 `PAUSED`（`error_code=PLATFORM_PAUSED`），等人工解除暂停后续发。
3. **演练路径 `brief=None` 直接崩**：`PublishService.plan()` → `_mode_of()` → `materialize(None, ...)`
   抛 `AttributeError`（只 catch 了 `KeyError/TypeError`）。于是「缺 packaging 时的 dry-run」不是报
   `PACKAGING_INCOMPLETE`，而是未捕获异常。改为 `brief` 非 dict 时返回空 mode。
4. **`test_p15_diversity.py` 的 `zip()` 缺 `strict=`**：ruff B905 红灯，CI lint 步会直接失败。

## 7. 遗留与限制（含未完成项）

1. **§15.5 真实生成 / 真实发布未执行** → 标记 `NOT ACCEPTED`（原因见 §2 的 §15.5 小节）。
   平台凭据（PostFlow 登录态、Upload-Post key）与 `publish.domestic_draft_args` 都未在真实环境验证过。
2. **抖音 AI 声明仍是「草稿优先」**：`ai_disclosure_confirmable` 未确认时，Gate 只允许 `draft`
   （实测 `douyin` → `ok=True`，`instagram` 这类无草稿通道 → `REQUIRE_HUMAN_PUBLISH`）。
   要让抖音直发，必须先由人工确认声明可程序化提交。
3. **Phase 14 的 7 条遗留全部沿用**：`config/default.yaml` 1 条本机绝对路径；`tools/` 27 个 C 类脚本
   保留原地（靠 `tools/README.md` 分类 + 守卫测试锁定）；`check_xinao10*.py` 等一次性脚本仍会报缺素材；
   `pipeline.yaml` 名字仍出现在 5 处注释/docstring；`publishes` 表 v1 遗留行未删；
   README 的 uvicorn 启动方式未实测；Phase 11 六条学习层限制。
4. **Phase 11 六条**（沿用）：无官方只读采集通道；学习结论不回写线上策略（只影响候选评分）；
   工程默认值（`prior_n=5` / `min_medium=8` / `min_high=30` / `window_days=30`）待真实数据校准；
   Phase 6 的 5 条 `needs_verification` 卖点未核验；QA 的 `vision` 维度仍由 fixture 承载；
   `ai_disclosure_confirmable` / `domestic_draft_args` 待人工补齐。
5. **自动互动只验护栏，不验文案质量**：`gen_reply()` 的措辞质量（LLM 输出）不在验收范围，
   验收覆盖的是「红线 → 转人工」「spam → 跳过」「限流/查重/熔断」这些**安全接线**。
6. **学习层的模型按 Planner 实例记忆**：`CreativePlanner.performance_model()` 在一次规划内只读一次
   历史（`_model_loaded`）。同一进程内先冷启动规划、再回流数据，第二次必须新建实例才会看到新历史 ——
   这是**有意设计**（一次规划内历史必须一致），但验收脚本/调用方必须知道这条边界。
7. **`test_p15_*` 里的「台词稿」是 fixture**：写作步骤（`docs/onetake_lines_<uid>.txt`）在真实运行里
   由人工/写作环节产出，自动测试用 `install_lines()` 提供。因此「主链不依赖人工预放 queue spec」这条
   成立（选题/骨架/角色/钩子/角度全部由 Planner 自主决定），但**台词稿仍属人工产物**。
