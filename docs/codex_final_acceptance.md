# ayh-mj vNext 最终验收报告（Phase 0 – Phase 15）

- 项目：ayh-mj vNext —— 统一状态、可恢复、可审计、能规划、能验片、能针对性修复、能安全发布、并能用真实表现持续学习的自主短视频生产系统。
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md`（Phase 0–15，§15.7 十项要求）
- 日期：2026-09-30（Asia/Shanghai）
- 分支：`codex/ayh-mj-vNext`；远端 `origin` = `https://github.com/DaBaoAgent/ayh-mj.git`（全程未使用 `master`）
- 总结论：**Phase 0–15 全部开发完成；非付费自动验收全绿；§15.5 真实生成 / 真实社媒发布未执行 → 标记 `NOT ACCEPTED`**（未获付费授权、未显式开启 `real_publish`）。除该条外，vNext 验收条件（§11）全部满足。
- 原始证据（可直接复现）：
  - `docs/codex/phase15_verification.txt` —— Phase 15 十二节实测（环境/基线 · ruff · 全量 pytest · marker 纪律 · 59 条用例逐条 · §15.1 对照 · 20 条多样性 · 预算幂等 · 故障恢复 · 发布安全 · 全链/学习/WebUI · §15.5 未执行说明）
  - `docs/codex/phase15_ci_guardrails.txt` —— CI 门禁 7 步原始输出
  - `docs/codex_phase_0_acceptance.md` … `docs/codex_phase_15_acceptance.md` —— 各阶段验收记录

---

## 1. 最终 commit SHA 与分支

| 项 | 值 |
|---|---|
| 分支 | `codex/ayh-mj-vNext` |
| 远端 | `origin` → `https://github.com/DaBaoAgent/ayh-mj.git` |
| 本阶段起点 | `7b6ba14`（phase-14） |
| Phase 15 提交 | `__PHASE15_SHA__` —— `phase-15: accept autonomous end-to-end pipeline`（含全部验收装置、缺陷修复与本文档） |
| 最终 tip | 以推送回执 / `git log -1 --format=%H` 为准（见 §12 交付说明） |

> 说明：本文档需要记录「包含它自己的提交」的 SHA，属于自引用，无法在文件内硬编码自身；因此此处记录 Phase 15 提交 SHA，tip 以仓库实际状态为准。

---

## 2. 各 Phase commit 列表

| Phase | commit | 主题 |
|---|---|---|
| 0 | `6e8acc5` | freeze baseline and add regression safety net |
| 1 | `745ccef` | unify settings dependencies and capability discovery |
| 2 | `7239092` | introduce canonical job store and state machine |
| 3 | `e30e9a7` | centralize execution in pipeline orchestrator |
| 4 | `289b2f2` | add resumability idempotency and repair policies |
| 5 | `4d953ff` | add autonomous planner and structured creative dna |
| 6 | `aa4a27e` | centralize product claims and compliance facts |
| 7 | `4d72c8a` | compile structured stories and route generation intelligently |
| 8 | `58528f5` | add automated qa critic and bounded self repair |
| 9 | `f4ec01b` | unify post production and make audio story aware |
| 10 | `b912bb7` | connect packaging publishing safety and ai compliance |
| 11 | `7f76dfa` | add closed loop creative performance learning |
| 12 | `c10b500` | rebuild web console around canonical jobs and events |
| 13 | `218ad06` | establish ci and autonomous development guardrails |
| 14 | `7b6ba14` | retire legacy pipeline and document vnext architecture |
| 15 | `__PHASE15_SHA__` | accept autonomous end-to-end pipeline |

---

## 3. 数据库 schema version

- `lib.state.DB_PATH` = `D:\@kaifa\ayh-mj\state\pipeline.db`
- `SCHEMA_VERSION` = **4**；已应用迁移 `applied = [1, 2, 3, 4]`
- JobStore（SQLite）是**唯一事实源**：job / attempt / artifact / event / publish_record / learning 全部经状态机 `transition` 写入，WebUI 只读同一份 DB。
- 迁移门禁：`tools/ci.py` 的 `migration` 步骤（5 条迁移测试）在 CI 中强制通过。

---

## 4. 全部测试命令与结果摘要

| 命令 | 结果 |
|---|---|
| `.venv/Scripts/python.exe -m ruff check lib tests tools webui s6_publish s7_learn` | `All checks passed!` |
| `.venv/Scripts/python.exe -m compileall`（CI typecheck 步） | 0 error |
| `.venv/Scripts/python.exe -m pytest -m "not live and not paid" -q` | **800 passed, 1 deselected**（359.5s） |
| `tests/unit` / `tests/contract` / `tests/integration` / `tests/frontend` | **628 / 50 / 113 / 9 passed** |
| marker 纪律（4 个目录各抽 1 条验证 marker 正确） | 4/4 ok |
| `.venv/Scripts/python.exe -m pytest tests/integration -k p15 -v` | **59 passed, 54 deselected**（36.7s） |
| `.venv/Scripts/python.exe tools/ci.py` | **7/7 PASS**（lint · typecheck · unit · contract · integration · frontend · migration；总 365.6s） |

Phase 15 分段结果（证据 §⑤/⑧/⑨/⑩/⑪）：`full_chain` 10 · `router_prescreen` 3 · `qa_repair` 6 · `cost_idempotency` 6 · `recovery` 9 · `diversity` 2 · `publish_safety` 21 · `learning_reflow` 2 = **59 条，全部 PASS**。

失败数：**0**。

---

## 5. live / paid 测试是否执行、成本、task id

| 项 | 值 |
|---|---|
| 是否执行 live 生成 | **否**（`AYHMJ_RUN_LIVE` / `AYHMJ_RUN_PAID` 未设置；CI 强制清除） |
| 是否执行 paid 生成（真实 H3） | **否** |
| 实际成本 | **0 元** |
| 真实 provider task id 数量 | **0** |
| 是否真实发布社媒 | **否**；全部停在 `READY`（packaging 已生成）或人为设计的 `BLOCKED` |
| 防护 | 自动测试中任何 `create_task` 都被 monkeypatch 成 `AssertionError`（`tests/p15_support.py::no_real_autodl`），付费路径不可能被误触发；`PublishService` 默认 `real=false`，只 `plan()` |

对应计划条款：§15.5 → **`NOT ACCEPTED`**（第 10 项要求，未用「基本完成」替代）。

---

## 6. 创意多样性统计（CreativeDNA）

计划要求 10 条；实际采集 **20 条**（真实 `CreativePlanner` 连续规划 10 条 + 同日第二批 10 条，证据 §⑦）。

### 6.1 硬指标（计划 §15.4）

| 指标 | 计划下限 | 实测 | 结果 |
|---|---|---|---|
| genre 种类 | ≥5 | **10** | PASS |
| hook_type 种类 | ≥5 | **8** | PASS |
| shot_pattern 种类 | ≥4 | **10** | PASS |
| dialogue_mode 种类 | —— | 6 | PASS |
| cast_pattern 种类 | —— | 9 | PASS |
| angle 种类 | —— | 20 | PASS |
| 「10 条是否全为两人对话」 | 不得全为 | **否**：双人对白 10/20 | PASS |
| 低对白 / 无对白 | ≥1 | **7/20** | PASS |
| 骨架签名唯一 | —— | **20/20** | PASS |
| 选题（热点）唯一 | —— | **20/20** | PASS |
| 同日两批重叠 | 0 | **0 条** | PASS |
| 相邻作品复用 genre+hook+angle+cast | 0 | **0 条** | PASS |
| 点名题材覆盖 | 全部命中 | Vlog/生活流 1 · 悬念 1 · 实验/对比 2 · 喜剧魔性或 POV 3 | PASS |
| 需预筛（高风险）比例 | 只在真高风险触发 | 1/20 | PASS |

### 6.2 前 10 条明细（第 1 批）

| # | genre | hook_type | shot_pattern | dialogue_mode | cast | angle |
|---|---|---|---|---|---|---|
| 1 | G6 | 身份代入 | POV主观视角 | 单人口播 | @mid_female | B15 |
| 2 | G1 | 冲突质问 | 四镜双人对撞 | 双人对白 | @elder_male+@mid_male | B1 |
| 3 | G8 | 反差打脸 | 实验对比双线 | 单人口播 | @mid_male+@young_male | B28 |
| 4 | G4 | 悬念设问 | 悬念三段式 | 字幕驱动 | @mid_female+@elder_female | B13 |
| 5 | G3 | 痛点共鸣 | 五镜生活流 | 画外音旁白 | @elder_male | B25 |
| 6 | G4 | 视觉奇观 | 无对白肢体三段 | 无对白 | @elder_male+@young_male | B19 |
| 7 | G4 | 神秘物件 | 评论区回应式 | 字幕驱动 | @elder_male+@young_female | B21 |
| 8 | G9 | 夸张数字 | 三镜魔性循环 | 无对白 | @elder_male | B16 |
| 9 | G5 | 悬念设问 | 手持街访 | 街访问答 | @neighbor_any+@mid_male | B12 |
| 10 | G10 | 冲突质问 | 四镜双人对撞 | 双人对白 | @elder_male+@mid_male | B10 |

第 2 批（11–20，同日再规划）genre 覆盖 G1–G10，angle 全部为新值（B11/B24/B26/B27/B30–B35 等），两批**零重叠**。

### 6.3 台词模式分布（20 条）

`单人口播 2 · 双人对白 10 · 字幕驱动 3 · 画外音旁白 1 · 无对白 3 · 街访问答 1`

> 台词稿（`docs/onetake_lines_<uid>.txt`）属「写作步骤」产物；本项只验收**规划层**多样性，全链验收中的台词稿由 fixture 提供。

---

## 7. 故障恢复测试结果（§15.2 八项 + 能力缺失）

| 故障注入 | 预期行为 | 用例 | 结果 |
|---|---|---|---|
| WebUI 进程重启 | 从 DB 恢复真实状态，无残留 running handle | `test_panel_restart_reads_the_db_and_leaves_no_running_handles` | PASS |
| submit 后进程立即退出 | 重启只 query，不重复提交（不重复付费） | `test_exit_right_after_submit_resumes_with_query_only` | PASS |
| 网络查询超时 | 退避续轮询，不换链、不重提交 | `test_transient_query_timeout_retries_instead_of_resubmitting` | PASS |
| provider SUCCESS 后下载失败 | 只增加 download 次数，不重提交 | `test_download_failure_after_success_only_retries_download` | PASS |
| SQLite 短暂锁 | 等锁通过（timeout 30s），不丢事件/状态 | `test_short_sqlite_lock_is_waited_out_not_lost` | PASS |
| SQLite 硬错误 | 停在下游之前：0 付费、0 artifact，且可恢复 | `test_hard_sqlite_error_stops_before_paying_and_stays_recoverable` | PASS |
| 磁盘空间不足 | 下游停止，不产生伪成功 artifact | `test_disk_full_stops_downstream_without_fake_artifact` | PASS |
| 缺字体 / 缺 ffmpeg / 缺 Upload-Post key | 进 DEGRADED/BLOCKED 并给出具体修复提示 | `test_missing_capabilities_report_status_and_a_fix_without_crashing` · `test_capability_blocked_stops_downstream_and_explains_the_fix` | PASS |

`tests/integration/test_p15_recovery.py`：**9 passed**。

---

## 8. 仍需人工介入的能力清单

1. **抖音 AI 声明确认**：`ai_disclosure_confirmable` 未由人工确认为 `true` 时，发布 Gate 只允许草稿通道（实测 `douyin` → 允许 `draft`；`instagram` 这类无草稿通道 → `REQUIRE_HUMAN_PUBLISH`）。要让抖音直发，必须先由人工确认声明可程序化提交。
2. **国内发布参数**：`publish.domestic_draft_args` 未在真实平台校验过（真实发布未执行）。
3. **平台凭据**：PostFlow 登录态 / Upload-Post key 在真实环境的有效期与权限未验证。
4. **红线与风控处置**：命中价格/医疗/投诉红线的评论一律转人工（`escalated`，不自动回复）；平台验证码 / 风控 / 账号异常一律 `REQUIRE_HUMAN` 并熔断该平台，需人工恢复。
5. **台词稿（写作环节）**：`docs/onetake_lines_<uid>.txt` 属人工/写作产物，主链不依赖人工预放 queue spec，但这一步仍是人的输入。
6. **卖点核验**：Phase 6 遗留的 5 条 `needs_verification` 卖点需人工核验后才能进字幕/文案渠道。
7. **真实付费与真发开关**：`AYHMJ_RUN_PAID` 与 `real_publish=true` 必须由人显式开启，且需先设 `budget_cap`。

---

## 9. 已知限制 / 第三方平台限制

**Phase 14 沿用（7 条）**
1. `config/default.yaml` 仍含 1 条本机绝对路径（`paths.legacy_keyfiles` 里仍在用的 keyfile `D:/BaiduSyncdisk/2 @AI编程/Api Key/爱优护api.txt`；**有意保留**，注释已说明换机改这里或设 `AYHMJ_KEYFILE`）。
2. `tools/` 下 27 个 C 类一次性脚本保留原地（靠 `tools/README.md` 分类 + 守卫测试锁定身份，未删除）。
3. `check_xinao10*.py` 等一次性脚本仍会报「缺素材」——属预期（本地无对应素材）。
4. `pipeline.yaml` 名字仍出现在 5 处注释/docstring（仅文字提及，AST 扫描零命中）。
5. `publishes` 表 v1 遗留行未删（保留历史，v2 发布记录写 `publish_records`）。
6. README 里的 `python -m uvicorn webui.server:app` 启动方式本轮未单独实测（Phase 12 的 Playwright 夹具以同一入口拉起控制台；本阶段只验证 `health_check` → DEGRADED 与 `orchestrate` CLI 可用）。
7. Phase 11 学习层六条限制（见下）。

**Phase 11 沿用（6 条）**
1. 无官方只读采集通道：表现数据靠人工/导出回流，未接平台官方 API。
2. 学习结论只影响**候选评分**，不回写线上发布策略。
3. 工程默认值（`prior_n=5` / `min_medium=8` / `min_high=30` / `window_days=30`）待真实数据校准。
4. Phase 6 的 5 条 `needs_verification` 卖点未核验。
5. QA 的 `vision` 维度在自动测试中仍由 fixture 承载（真实视觉模型调用属付费/联网路径）。
6. `ai_disclosure_confirmable` / `domestic_draft_args` 待人工补齐。

**第三方平台限制**
- 平台风控 / 验证码 / 账号异常**无法程序化绕过**，系统设计为 `REQUIRE_HUMAN` + 熔断，这是能力边界而非缺陷。
- 发布权限、频率限制（quota / 时间窗）由平台侧决定，系统只做本地 Gate 与配额记录。

**测试装置边界**
- `test_p15_*` 中的「成片 / 台词稿 / QA 证据」均为 fixture 替身；**判定逻辑一律是真实实现**（`lib.qa.critic`、`lib.orchestrator.stages._qa_gate`、`PublishService`）。
- `CreativePlanner.performance_model()` 按实例缓存历史（`_model_loaded`）：同一进程内先冷启动规划、再回流数据，第二次规划必须**新建实例**才读到新历史——这是「一次规划内历史必须一致」的有意设计。

---

## 10. 未完成项（必须明确）

1. **§15.5 真实生成验收（真实 H3 付费调用）** → **`NOT ACCEPTED`**。未执行，成本 0 元，task id 0 个。
2. **§15.5 真实社媒发布** → **`NOT ACCEPTED`**。未执行，全部停在 `READY` / 草稿。
3. **真实视觉 QA（付费/联网 vision 调用）** → **`NOT ACCEPTED`**（自动验收用 fixture 承载）。
4. **抖音 AI 声明程序化直发** → **`NOT ACCEPTED`**（待人工确认 `ai_disclosure_confirmable` 与 `domestic_draft_args`）。

以上四项均为**受授权/凭据/真发开关限制**的条目，非代码未完成；一经授权与凭据到位，可用同一套 Orchestrator 主链直接执行。

---

## 11. vNext 验收完成条件核对（计划 §15.7 硬门槛）

| 条件 | 状态 | 依据 |
|---|---|---|
| 非 live CI 全绿 | ✅ | `tools/ci.py` 7/7 PASS；全量 pytest 800 passed |
| P0 问题归零 | ✅ | 本阶段修掉 3 个真实缺陷后无 P0 遗留（见 `docs/codex_phase_15_acceptance.md` §6） |
| 主链不再依赖人工预放 queue spec | ✅ | 空 queue + `daily_target=5` 由 Planner 自动建 5 个 job |
| JobStore 为唯一事实源 | ✅ | schema v4；WebUI 与 JobStore 一致性用例 PASS |
| Orchestrator 为唯一执行入口 | ✅ | Phase 3/14 收敛；`run_all.py` 已标 DEPRECATED |
| 恢复/幂等/预算保护测试通过 | ✅ | `test_p15_recovery.py` 9 · `test_p15_cost_idempotency.py` 6 |
| QA/Repair 闭环通过 fixture 验收 | ✅ | `test_p15_qa_repair.py` 6（4 类缺陷 + error_code 分派 + 上限 BLOCKED） |
| Claims/AI disclosure 发布 Gate 有自动测试 | ✅ | `test_p15_publish_safety.py` 21 |
| WebUI 与真实任务状态一致 | ✅ | `test_webui_reports_the_same_truth_as_jobstore` |
| 生成多样性验收通过 | ✅ | §6（20 条实测，全部指标达标） |

**结论：除 §10 列出的 4 项受授权限制条目外，计划 §15.7 的十条硬门槛全部满足。**

---

## 12. 交付说明

- 代码与验收装置：Phase 0–15 全部提交在 `codex/ayh-mj-vNext`，最新提交为 `phase-15: accept autonomous end-to-end pipeline`。
- 最终 tip SHA 见推送回执 / `git log -1 --format=%H`（本文档自引用无法硬编码自身所在提交）。
- 复现验收：`.venv/Scripts/python.exe tools/ci.py`（7 步门禁），或 `.venv/Scripts/python.exe logs/_p15_evidence.py`（需 `logs/` 下脚本，仅本地生成证据，不入库）。
- 真实链路启用条件：设置 `AYHMJ_RUN_PAID=1` + `RunConfig.budget_cap`，并显式 `real_publish=true`；在此之前系统一律停在 `READY` / 草稿。
