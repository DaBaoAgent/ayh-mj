# Phase 8 验收记录 — 自动 QA Critic + RepairEngine 完整闭环

- 阶段：Phase 8
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 8
- commit：`phase-8: add automated qa critic and bounded self repair`
- 原始证据：
  - `docs/codex/phase8_qa_report.txt`（同一份证据 → 结构化 JSON + 人类可读 Markdown）
  - `docs/codex/phase8_failure_matrix.txt`（10 种失败 fixture → error_code → 修复动作 → 回退目标）
  - `docs/codex/phase8_repair_loop.txt`（自动 QA → 定点回退 → 到上限转人工 的真实轨迹）
  - `docs/codex/phase8_repairs_db.txt`（repairs 表：次数 / 成本 / 结果）
  - `docs/codex/phase8_verification.txt`（ruff / 定向 pytest / 全量 pytest / 前端 smoke）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| QA 报告契约（新） | `lib/qa/report.py`（179 行） | `QaFinding`（`dimension/severity/error_code` 三件套，**没有 error_code 直接抛错**）、`QaReport`（`findings` / `dimensions` / `coverage` / `score` / `codes` / `primary_error` / `to_dict` / `to_json` / `to_markdown`）。6 个维度 `product/cast/audio/retention/compliance/delivery`；`PRIMARY_PRIORITY` 决定多 FAIL 时交给 RepairEngine 的那一个码 |
| QA 判定（新） | `lib/qa/checks.py`（424 行） | 纯函数 `check_delivery/product/cast/audio/retention/compliance` + `run_checks()` + `coverage()`；阈值集中声明（`MIN_FINAL_BYTES=100_000`、`DURATION_TOLERANCE=1.5`、`HOOK_MAX_SECONDS=2.0`、`STATIC_MAX_SECONDS=2.0`、`PAYOFF_MAX_RATIO=0.85`、`SUB_OVERLAP_TOLERANCE=0.12`、`SUB_MAX_CHARS_PER_LINE=16`、`LOUDNESS_BAND=(-17,-9)`、`TRUE_PEAK_MAX=-1.0`） |
| QA 取证（新） | `lib/qa/critic.py`（168 行） | `gather_evidence()`（ffprobe 探成片 + 读 spec 期望 + 读 subtitles/transcript artifact + 跑合规门）、`QaCritic.analyze()`、`critique()`；`PHASE_DIMENSIONS`：`gen`=全维度、`final`=(delivery, audio)。**取不到的证据留空 → 记 `skipped`，绝不算 pass** |
| 修复计划（新） | `lib/orchestrator/repairs.py`（150 行） | `REPAIR_TARGET`（动作 → 回退 stage）、`PLAYBOOK`（每个码的可读修复说明）、`RepairPlan`、`plan_repair()`、`repair_target()`。**只重做必要部分**：字幕只重建字幕、下载失败只重下、文案违规不放行 |
| 修复闭环 | `lib/orchestrator/service.py` | `_run_stages` 支持**定点回退**（REPAIRING → 目标 stage），上限 `cfg.max_repairs`，越界转 `REQUIRE_HUMAN/BLOCKED`；`_repairs_used()` 读 DB（resume/retry 也累计预算）；`_record_repair()` 落计划、`_finalize_repair()` 回填**真实成本/结果** |
| 数据层 | `lib/migrations.py` / `lib/jobstore.py` | 迁移 **v4 `qa_repair_records` → `repairs` 表**（`SCHEMA_VERSION=4`）；`add_repair/list_repairs/update_repair/repair_summary`；状态机加 **REPAIRING** 中枢（<READY 的线型态可进 REPAIRING，REPAIRING 可回退到更早线型态） |
| 阶段接线 | `lib/orchestrator/stages.py` | 新增 `_qa_gate(ctx, phase, stage)`：Critic 判定 → 落 `qa/qa_report_{phase}.json|md` artifact → 每维度 + 总分写 `evaluation` → 失败带 `findings` + 主错误码返回。`stage_qa` 走 `phase="gen"`；`stage_compose` 末尾走 `phase="final"` |
| 策略 | `lib/orchestrator/policies.py` | `qa` 白名单 = `_QA_CODES`（画面/人物/产品/字幕/下载类可进修复环）；`compose` 增加 `QA_FAILED/DOWNLOAD_FAILED` |
| 配置 | `lib/orchestrator/models.py` | `RunConfig.max_repairs`（0–10 夹取，默认 3）并进 `to_dict()` 快照 |
| 导出 | `lib/orchestrator/__init__.py` | 导出 `plan_repair / repair_target / RepairPlan / PLAYBOOK / REPAIR_TARGET` |
| 测试（新） | 4 个测试文件 | 见 §5（59 条） |
| 测试（改） | `tests/unit/test_migrations.py`、`tests/unit/test_repair_policies.py`、`tests/unit/test_idempotency.py` | 迁移断言补 v4；Phase 4 的「qa 阶段不含 VISUAL_QA_FAIL」语义按 Phase 8 **反转**；e2e 注入 QA 证据（假供应商产不出真视频流） |

## 2. 必做任务逐条对照

| # | 任务 | 结果 | 证据 |
|---|---|---|---|
| 1 | QA 输出结构化 JSON + 人类可读报告 | ✅ | `QaReport.to_json()` / `to_markdown()`；`phase8_qa_report.txt` 同一份证据两份产物 |
| 2 | 每个 FAIL 必须映射到 error_code | ✅ | `QaFinding.__post_init__` 空码即 `ValueError`；`test_fail_finding_without_error_code_is_rejected`；MD 表头含 `error_code` 列 |
| 3 | ≥8 种失败 fixture 验证 repair routing | ✅ | **10 种**（产品数漂移/形变/解剖/错嘴/ASR 漏词/字幕越界/钩子过晚/未登记承诺/成片缺失/无视频流）→ `phase8_failure_matrix.txt` |
| 4 | repair 次数、成本和最终结果均写 DB | ✅ | `repairs` 表（v4）+ `add_repair`/`update_repair`/`repair_summary`；`phase8_repairs_db.txt` 见 `attempt/budget/cost/status` |
| 5 | 达上限转 `REQUIRE_HUMAN/BLOCKED`，禁止无限循环 | ✅ | `test_visual_failure_rewinds_generate_then_blocks_at_repair_limit`（上限 2 → generate 3 次后 BLOCKED）；`repair_exhausted=True` 事件；预算跨 retry 累计 |
| 6 | QA 维度覆盖（产品/人物/音频/留存/合规） | ✅ | `checks` 六维度逐条实现在 §3 |

## 3. QA 维度对照（计划 §Phase 8「QA 维度」）

| 计划维度 | 落地检查 | error_code |
|---|---|---|
| 视觉产品保真：数量/形变/换车型/漂移 | `check_product`（`products_seen` vs `products_expected`、`product_count_per_shot` 漂移、`product_deformed`、`product_color_ok`、`product_drift_shots`、`logo_ok`） | `PRODUCT_DEFORMED` |
| 人物与表演：畸形/人数/身份/闭嘴/音色 | `check_cast`（`anatomy_ok`+`anatomy_issues`、`people_seen`、`cast_consistent`、`wrong_speaker_shots`/`voice_swapped`、`non_speaker_mouth_open`） | `HUMAN_ANATOMY_FAIL` / `VISUAL_QA_FAIL` / `WRONG_SPEAKER` |
| 音频/对白：ASR 一致/漏句/长尾/语速 | `check_audio` + `_check_subtitle`（期望台词对 ASR、同音识别降级为 WARN、`tail_silence_seconds`、`rate_cps` vs `speech_band`、字幕时间轴/重叠/越界/安全区/断句/与台词一致） | `ASR_MISMATCH` / `SUBTITLE_ALIGN_FAIL` |
| 镜头与留存：0–2s 钩子 / 静止 / 失焦 / payoff | `check_retention`（`first_hook_seconds`、`static_seconds`+尾静默、`subject_too_small`、`out_of_focus_seconds`、`payoff_seconds` vs 时长×0.85） | `VISUAL_QA_FAIL` |
| 品牌/合规：Claims Registry / AI 声明 | `check_compliance`（`lib.claims.gate()`：未登记→FAIL、禁用→FAIL；`ai_generated` 未记录声明→FAIL） | `COMPLIANCE_BLOCK` |
| 成片完整性（工程前置） | `check_delivery`（文件存在/体量/视频流/有对白必须有音频流/时长偏差/响度与真峰值 WARN） | `DOWNLOAD_FAILED` / `QA_FAILED` |

> **阈值说明**：计划只给了维度、没给具体数值。上表阈值是本轮按 15s one-take 产线实测定的工程默认值，已集中声明在 `lib/qa/checks.py` 顶部，改动只需一处。

## 4. Repair 映射对照（计划 §Phase 8「Repair 映射示例」）

| 计划要求 | 落地（`REPAIR_MAP` 动作 / `REPAIR_TARGET` 回退 / `PLAYBOOK` 说明） | 验证 |
|---|---|---|
| `PROMPT_TOO_LONG` → `COMPRESS_PROMPT`，不生成 | `COMPRESS_PROMPT` → 回 `generate`；说明「不生成 —— 超限的提交必被服务端拒收」 | `test_repair_plan.py` 参数化 |
| `WRONG_SPEAKER` → 强化 speaker lock / 减少同镜角色重生 | `REGENERATE_SHOT` → 回 `generate` | 同上；`phase8_failure_matrix.txt` |
| `PRODUCT_DEFORMED` → 简化+加强 refs，优先重生问题镜 | `REGENERATE_SHOT` → 回 `generate` | 闭环实测见 §6 |
| `HUMAN_ANATOMY_FAIL` → 调 occupancy/距离重生 | `REGENERATE_SHOT` → 回 `generate` | 同上 |
| `ASR_MISMATCH` → 同音只重建字幕、真漏词重生 | `REBUILD_SUBTITLE` → 回 `compose`（同音证据降级为 WARN，不触发修复） | `test_asr_homophone_only_warns` |
| `SUBTITLE_ALIGN_FAIL` → 只重建字幕，不重新生成视频 | `REBUILD_SUBTITLE` → 回 `compose`；**generate 调用次数 = 1** | `test_subtitle_failure_rewinds_compose_without_regenerating` |
| `DOWNLOAD_FAILED` → 只重下 provider artifact | `RETRY_SAME`，就地重跑（不重新提交付费任务） | `test_repair_plan.py`；Phase 4 已验提交数不变 |
| `COMPLIANCE_BLOCK` → 改文案/claim，不允许绕过 | `REQUIRE_HUMAN`（**不重生成**） | `test_compliance_failure_goes_straight_to_human` |

## 5. 测试结果

```text
$ python -m ruff check lib tests tools webui
All checks passed!

$ python -m pytest tests/unit/test_qa_report.py tests/unit/test_qa_checks.py tests/unit/test_repair_plan.py tests/integration/test_qa_repair_pipeline.py -q
59 passed in 1.39s

$ python -m pytest -q
401 passed, 1 skipped, 1 warning in 297.19s     # Phase 7 结束为 342 passed / 1 skipped

$ python -m pytest tests/frontend -q
3 passed in 2.59s
```

Phase 8 新增测试：

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/unit/test_qa_report.py` | 8 | FAIL 无 error_code 抛错；维度/严重度校验；score 权重；codes 优先级与去重；JSON/MD 双产物；coverage |
| `tests/unit/test_qa_checks.py` | 24 | 10 种失败 fixture 矩阵 + 边界（同音=WARN、字幕重叠/孤行、响度峰值仅 WARN、无证据=skipped、缺成片=FAIL） |
| `tests/unit/test_repair_plan.py` | 22 | 计划列出的 8 条映射参数化；回退目标；未知码 → ABORT；合规**不得**路由到重生；target_shot 提取 |
| `tests/integration/test_qa_repair_pipeline.py` | 5 | 画面不合格→回退 generate→到上限 BLOCKED；字幕问题只回退 compose（generate=1 次）；合规直接人工；修复预算跨 retry 累计；成本/结果回填 |

> `tests/integration/test_qa_repair_pipeline.py` 用**真实** `stage_qa`（真读证据 JSON、真跑 ffprobe 分支、真写 artifact/evaluation），只有 generate/compose 换成假实现，全程 0 付费。

## 6. 关键结果（实测）

**失败 fixture 矩阵**（`phase8_failure_matrix.txt`）：10 种失败 → 9 个不同 error_code；`product_count_drift / product_deformed → PRODUCT_DEFORMED → REGENERATE_SHOT → generate`；`unregistered_claim → COMPLIANCE_BLOCK → REQUIRE_HUMAN`；`no_video_stream → QA_FAILED → REGENERATE_SHOT`。

**修复闭环**（`phase8_repair_loop.txt`）：

```
P8EV_A 画面不合格（products_seen=2）→ 回退 generate，到上限转人工
  generate 调用 3 次 / compose 0 次；终态 BLOCKED（PRODUCT_DEFORMED）；修复次数 2
  ↺ 定点修复 1/2：PRODUCT_DEFORMED → REGENERATE_SHOT（回退到 generate）
  ↺ 定点修复 2/2：PRODUCT_DEFORMED → REGENERATE_SHOT（回退到 generate）
  ✗ BLOCKED（PRODUCT_DEFORMED）：定点修复已达上限 2 次

P8EV_B 字幕越界 → 只回退 compose 重建字幕（不重生视频）
  generate 调用 1 次 / compose 1 次；终态 COMPOSING；修复次数 1
  ↺ 定点修复 1/3：SUBTITLE_ALIGN_FAIL → REBUILD_SUBTITLE（回退到 compose）

P8EV_C 未登记承诺 → 直接人工，不烧重生
  generate 调用 1 次 / compose 0 次；终态 BLOCKED（COMPLIANCE_BLOCK）；修复次数 0
```

**repairs 表**（`phase8_repairs_db.txt`）：每条修复都有 `stage / error_code / action / rewind_to / attempt / budget / cost / status`；`P8EV_A` 两条（`EXECUTED` → `FAILED`，即"修了但没修好、被上限截断"），`P8EV_B` 一条 `EXECUTED`。

**QA 报告**（`phase8_qa_report.txt`）：同一份证据 → `to_json()`（`passed/score/coverage/dimensions/codes/primary_error/findings` 全字段）与 `to_markdown()`（维度表 + 每条 FAIL 带 `error_code`、镜号、修复方向）。

## 7. 本阶段修掉的既有缺陷

1. **`_run_stages` 断点续跑会截断回退目标**：`retry` 从 `qa` 恢复时 `stages` 只剩 `[qa, compose]`，而修复目标是 `generate` → 直接 `FAILED`（本该 `BLOCKED`）。已改为：回退目标只要在本配置的 stage 顺序里，就补回完整链再定位。
2. **`repair_done` 事件被静默吞掉**：`store.add_event()` 不接受 `error_code` 参数，`_finalize_repair` 传了 → `TypeError` 被 `suppress` 掩盖，导致"结果"没落库。已从调用里去掉该参数（码保留在 `data`）。
3. **修复只有计划、没有结果**：原 `_record_repair` 只写 `status="PLANNED"`、`cost=0.0`，验收要求的"成本/结果写 DB"落不了地。已补 `update_repair()` + `_finalize_repair()`，用**成本增量**回填真实花费，状态 `PLANNED → EXECUTED / FAILED`。
4. **Phase 4 测试语义过期**：`test_stage_policy_whitelist_blocks_out_of_scope_codes` 断言"qa 阶段不含 VISUAL_QA_FAIL"，与 Phase 8 的 `_QA_CODES` 直接冲突。已按新语义改写为「同一 error_code 在不同阶段行为不同」。
5. **迁移测试断言落后于 v4**：`[1,2,3]` / `[2,3]` → `[1,2,3,4]` / `[2,3,4]`。

## 8. 遗留与限制（交给后续 Phase）

- **画面类证据来自 fixture / 人工回填**：本轮 `vision` 段（产品形变、解剖、说话人、钩子时间）由 `qa_evidence_<uid>.json` 承载；真实"看画面"的多模态接入（`media_analysis`）留到 Phase 9+，`critic.gather_evidence()` 已留好同一 schema 的插口。**没有证据的维度记 `skipped`，绝不当通过。**
- **阈值是工程默认值**：计划未给具体数值（`HOOK_MAX_SECONDS=2.0` 等），待真实产片积累后再校准；改动集中在一处。
- **`stage_compose` 的 `final` 验片只在真实 `make_15s` 跑完后生效**：本轮集成测试用假 compose 绕开了子进程，真实字幕重建留到带预算保护的实片验收（Phase 15.5）。
- **修复成本口径**：`repairs.cost` 记的是"该次修复窗口内的 job 成本增量"。当前 `generate` 的付费发生在 Phase 4 的 `IdempotentGenerator`，两者口径一致（都读 `jobs.cost_spent`）。
- **Phase 6 遗留的 5 条 `needs_verification` 口径仍未解决**（`shock_18` / `range_39` / `lithium_safe` / `cert_medical_device` / `patent_27`），需人工补证——见 `docs/codex_phase_6_acceptance.md` §4。
