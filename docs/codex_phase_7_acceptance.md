# Phase 7 验收记录 — StorySpec → PromptCompiler → 智能 Generation Router

- 阶段：Phase 7
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 7
- commit：`phase-7: compile structured stories and route generation intelligently`
- 原始证据：
  - `docs/codex/phase7_compile_matrix.txt`（10 骨架编译矩阵）
  - `docs/codex/phase7_prompt_budget.txt`（预算器去重/压缩/超限阻断）
  - `docs/codex/phase7_router.txt`（能力感知路由 + 不兼容拒绝）
  - `docs/codex/phase7_prescreen.txt`（风险分级 + 5s 预筛改写）
  - `docs/codex/phase7_dialogue_gate.txt`（10 骨架过静态对白门禁）
  - `docs/codex/phase7_verification.txt`（ruff / 全量 pytest / 前端 smoke）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 编译器（新） | `lib/creative/compiler.py`（472 行） | `PromptCompiler` / `compile_spec()` / `gate_text()` / `budget_prompt()` / `PromptBudget` / `PromptBudgetExceeded` / `spoken_line()` / `lines_from_file()` / `time_plan()`。把 StorySpec 编成 H3 prompt：CINEDANCE 依 genre 动态启用；ACTING 逐镜生成行为节拍；speaker lock / GAZE / RIDER / 产品单元保真按场景注入；预算器去重 + 压缩。常量 `PROMPT_MAX=10000` / `PROMPT_SAFE=9800` / `COMPILER_VERSION="prompt-compiler/1.0"` |
| 路由（新） | `lib/creative/workflow.py`（294 行） | `Requirement` / `RoutePlan` / `canonical()` / `compatible()` / `validate_chain()` / `choose()` / `route_for_spec()` / `within_budget()`；能力真源取 `s4_generate/workflow_router.WORKFLOW_SPECS`（15 型号），排序用 `历史成功率 → tier → 热度`；简名归一（`multi_image_15s` → `minimax_h3_lightx2v_v5_15s` 等） |
| 预筛（新） | `lib/creative/prescreen.py`（126 行） | `risk_of()` / `needs_prescreen()` / `build_prescreen_spec()` / `record_prescreen()` / `prescreen_passed()`；`PRESCREEN_SECONDS=5` |
| 表演（新） | `lib/creative/acting.py`（151 行） | `profile_for()` / `role_label()` / `blocks()` / `clauses()` / `beat_line()`；按角色/场景产出节拍，**同一 spec 内不重复同一 clause**（跨镜去重） |
| StorySpec | `lib/creative/storiespec.py` | 新增 `lines`（句数随骨架变）/ `prompt_meta` / `spec_version` / `workflow_source` / `first_last` / `text_only`；`SPEC_VERSION="storyspec/1.0"`；`to_dict()`/`to_spec_json()` 全量输出 |
| Planner | `lib/creative/planner.py` | 新增 `_attach_lines()`（台词稿搬运，与编译器同一 `lines_from_file`）/ `_attach_assets()`（`@槽位` → 定妆图 + 音色 + 产品单元素材）/ `_compile_prompt()` / `_route_prompt()`；`PlannedJob.gate_path`；`plan_for()` 落盘 `prompt_ready=True` 的 spec + 静态门禁 payload |
| 编排接线 | `lib/orchestrator/stages.py` | 新增 `_spec_metrics()`（把编译/路由结果写进 plan 阶段 metrics）、`_spoken_copy()`（只抽对外文案）、`_static_dialogue_gate()`、`_workflow_gate()`、`_prescreen_gate()`；`stage_preflight` 重排为 ①编译就绪 ②claims ③prompt 预算 ④工作流链能力 ⑤高风险预筛 ⑥静态对白门禁 ⑦要说话的片必须有词 |
| 错误码 | `lib/orchestrator/errors.py` | 新增 `PROMPT_BUDGET_EXCEEDED` / `WORKFLOW_INCOMPATIBLE` / `PRESCREEN_REQUIRED` / `PRESCREEN_FAILED`（`REPAIR_MAP`：预算超限 → `COMPRESS_PROMPT`，其余 `REQUIRE_HUMAN`）；`BUSINESS_CODES` 仍恰好 20 条 |
| Claims | `lib/claims.py` | `_NUMERIC_RE` 加 `(?![A-Za-z0-9])` —— 修 `85mm 镜头` 被读成产品参数 `85m` 的误报；`第一人称/第一视角` 加负向断言（广告法绝对化用语误伤修复） |
| 静态门禁 | `tools/check_dialogue.mjs` | R26 旧阈值「400 单位（中文按字、英文按 1/3 计）」**作废**，改为 H3 实测**字符数**上限 10000 / 安全线 9800；`promptWeight()` 改按字符数；R10/R28 语速预算只在 payload 带 `duration="N"` 时生效（产线 payload 一定带） |
| 文档 | `docs/rules-dialogue.md` | R26 改 ERROR 级 + 10000/9800 口径；补产线 payload 说明 |
| 资产 | `assets/cast/acting/dark_knight.md`、`assets/cast/acting/scene_H1_dark_knight.md` | `before he speaks` → `before he commits`（无对白/字幕驱动片不该写"说话"） |
| 测试（新） | `tests/p7_support.py` + 4 个单测 + 1 个集成测试 | 见 §5 |
| 测试（改） | `tests/unit/test_planner.py`、`tests/integration/test_planner_pipeline.py`、`tests/integration/test_claims_pipeline.py` | 按 Phase 7 语义更新（`prompt_ready=True` / `workflow_source=="router"` / 合规门只看对外文案） |

## 2. 必做任务逐条对照

| # | 任务 | 结果 | 证据 |
|---|---|---|---|
| 1 | 新增 `StorySpec` 强类型 schema；镜数、角色、台词模式均可变 | ✅ | `StorySpec.lines` + `shots` 由骨架决定（3/4/5 镜）；`SPEC_VERSION="storyspec/1.0"`；矩阵显示 3/4/5 镜、0-4 句并存 |
| 2 | `PromptCompiler` 把 StorySpec 编译为 provider-specific prompt | ✅ | `compile_spec()` / `PromptCompiler.compile()`；10/10 骨架编译出非空 prompt（4949–8569 字符） |
| 3 | CINEDANCE 依片型动态启用，不再作为独立外挂脚本 | ✅ | `CINEDANCE_GENRES={G1,G2,G3,G4,G8,G10}`；矩阵中 6 个片型 `cinedance=True`、4 个 False |
| 4 | ACTING 依角色/场景生成行为节拍；不把 master profile 原文无脑重复塞每镜 | ✅ | `acting.beat_line()` 轮转 profile 的 blocks 并跨镜去重；`test_acting_beats_never_repeat_a_clause_within_a_spec`、`test_acting_lines_rotate_through_the_profile_blocks` |
| 5 | Speaker Lock / GAZE / RIDER / 产品单元保真由 compiler 按场景注入 | ✅ | 编译产物分层 `header / pace_realism / gaze / cast / eye_rule / cold_open / product / rider / shot…`；`test_dialogue_skeleton_carries_speaker_lock_and_chinese_lines` |
| 6 | Prompt Budgeter 在提交前计算字符/token 风险，自动去重重复约束；不靠生成失败才发现超长 | ✅ | `budget_prompt()`：重复长句 `dropped_sentences=1`；>9800 压缩；>10000 抛 `PromptBudgetExceeded`（`chars=10005 limit=10000`） |
| 7 | `check_dialogue.mjs` 继续做静态 gate，与 15 秒 one-take 真实限制一致，清理失效旧阈值 | ✅ | R26 `400 单位` → `10000 字符`（ERROR）/ `9800`（WARN）；10/10 骨架 0 ERROR |
| 8 | 生成入口统一调用 capability-aware router；不再由 spec 人工固定空 fallback | ✅ | `planner._route_prompt()` → `route_for_spec()`；spec `workflow_source="router"`；`test_research_and_scoring_are_traceable_artifacts`（`spec["workflow_source"]=="router"`）、`test_autonomous_start_produces_job_and_creative_dna`（plan metrics） |
| 9 | Router 依 `duration / ref_images / audio / quality / first_last / risk / historical_success` 选链 | ✅ | `requirements_from_spec()` 取全部维度；`_rank()` = 历史成功率 → tier → `pop_7d`；`must_keep` 硬需求不漏 |
| 10 | provider adapter 返回统一 `ProviderTask`，禁止业务层依赖 AutoDL 私有字段 | ✅ | `ProviderTask` 已在 Phase 4 落地（`lib/orchestrator/providers.py`）；本轮复核：compiler/router/编排只读**能力表** `WORKFLOW_SPECS`，不碰 AutoDL 请求/响应私有字段 |
| 11 | 高风险新构图自动触发 `prescreen`：多人、复杂交互、特殊道具、品牌字、危险形变动作 | ✅ | `risk_of()` 命中：多人（`MANY_PEOPLE`）、特殊交互调度、特殊道具/光效、危险形变动作、品牌字/收口句、没拍过的骨架 |
| 12 | prescreen 结果进入 evaluation；PASS 才允许完整 15 秒付费生成 | ✅ | `_prescreen_gate()`：高风险未过 → `PRESCREEN_REQUIRED`（0 付费提交）；`prescreen_passed()` 读 evaluation 落盘 |
| 13 | 所有 prompt/spec/compiler 版本写入 artifact metadata | ✅ | `spec.prompt_meta{compiler_version, spec_version, route, risk}` + 顶层 `spec_version`；`test_compiled_prompt_carries_versions_and_facts_digest` |

## 3. 验收标准逐条对照（计划原文 5 条）

| # | 验收标准 | 结果 | 证据 |
|---|---|---|---|
| 1 | 10 种 StorySpec 至少各能通过 fake provider 编译和**执行**，不再被固定 4 镜×8 句限制 | ✅ | `test_every_skeleton_compiles_and_executes[10 参数]` 走完 plan→preflight→generate（fake provider）；`test_no_skeleton_is_limited_to_four_shots_and_eight_lines`；矩阵显示镜数 3/4/5、句数 0–4 |
| 2 | prompt 超限可在 provider 调用**前**阻断或自动压缩 | ✅ | 编译期 `PromptBudgetExceeded`（10005 > 10000）；服务端 `stage_preflight` 复核 `>10000 → PROMPT_BUDGET_EXCEEDED`；`>9800 → WARN 先压缩`；`test_oversized_prompt_is_blocked_before_any_submission`（`provider.submit_count == 0`） |
| 3 | 故意让首选 workflow 返回失败，router 能在预算内切换兼容 fallback | ✅ | `test_failed_preferred_workflow_switches_to_a_compatible_fallback`：10s 需求链 `minimax_h3_lightx2v_v5 > minimax_h3_lightx2v_v5_15s > minimax_h3_lightx2v > minimax_h3_z0902`，首选失败后切换成功 |
| 4 | fallback 不得偷偷丢失音频/参考图/时长关键能力；能力不兼容时必须**拒绝**切换 | ✅ | `validate_chain()` 逐型号校验 `duration/n_images/audio/first_last`；`test_incompatible_chain_is_refused_instead_of_silently_downgraded`；router 证据中 5 个不兼容型号全部 `ok=False` 并给出理由；15s 纯文生 → `WorkflowIncompatible` |
| 5 | 高风险 StorySpec 会先进入 prescreen，低风险任务可直接生成 | ✅ | `S_pov_first` = `high 0.95` → `needs_prescreen=True` → `PRESCREEN_REQUIRED`；其余 9 个 `medium` → `needs_prescreen=False` 直接放行；`test_high_risk_spec_is_gated_until_a_prescreen_passes`、`test_low_risk_spec_generates_without_a_prescreen` |

## 4. 关键实测数据

**编译矩阵**（`phase7_compile_matrix.txt`）：10/10 骨架编译出非空 prompt，4949–8569 字符；镜数 3/4/5，句数 0–4；CINEDANCE 6 开 4 关。

**预算器**（`phase7_prompt_budget.txt`）：
```
① 去重: dropped_sentences=1  出现次数=1
② 压缩: 原始 9852 → 9851  compressed=True（safe=9800, limit=10000）
③ 超硬上限: 抛 PromptBudgetExceeded chars=10005 limit=10000 error_code=PROMPT_TOO_LONG
```

**路由**（`phase7_router.txt`）：15s + 2 图 + 无音频 → 首选 `minimax_h3_lightx2v_v5_15s`（15s 多图唯一可用型号，**fallback 为空是正确行为**）；10s → 4 段 fallback 链，估算 ¥0.600。不兼容拒绝 5/5 全部给出可读理由。

**预筛**（`phase7_prescreen.txt`）：10 骨架风险分级 `medium 0.35–0.65` 9 个 + `high 0.95` 1 个（`S_pov_first`）；高风险 spec 改写为 5s 单镜预筛 payload（`duration=5`、`shot=2`）。

**静态对白门禁**（`phase7_dialogue_gate.txt`）：10/10 骨架 **0 ERROR**；5 个有台词片触发 R28 WARN（仿真台词 25–34 字 < 65 字下限），无对白/字幕驱动片 0 WARN。

## 5. 测试结果

```text
$ .venv/Scripts/python.exe -m ruff check .
All checks passed!

$ .venv/Scripts/python.exe -m pytest -q
342 passed, 1 skipped, 1 warning in 295.48s      # 1 skipped = paid placeholder；Phase 6 结束为 249 passed / 1 skipped

$ .venv/Scripts/python.exe -m pytest -m frontend -q
3 passed, 340 deselected
```

Phase 7 新增/修改的定向测试：

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/unit/test_creative_compiler.py` | 39 | 骨架编译、CINEDANCE 开关、镜/句数、ACTING 去重、`<d>` 语法、预算器、版本 metadata |
| `tests/unit/test_creative_acting.py` | 10 | 节拍轮转、跨镜去重、角色标签 |
| `tests/unit/test_prescreen.py` | 7 | 风险分级、高风险触发、预筛 spec 改写、passed 落盘 |
| `tests/unit/test_workflow_router.py` | 25 | 简名归一、能力校验、fallback 链、不兼容拒绝、预算 |
| `tests/integration/test_compile_pipeline.py` | 17 | 10 骨架 fake provider 全链 + 超限阻断/压缩 + fallback 切换 + 不兼容拒绝 + 预筛门 |
| `tests/p7_support.py` | — | 共享夹具（参考图、片型映射、spec/dna/shots/lines 构造） |

> 集成测试每条用例都真跑一次 `node tools/check_dialogue.mjs` 静态门禁，因此 `test_compile_pipeline.py` 单文件约 285s。

## 6. 本阶段修掉的既有缺陷

1. **`compiler._view()` 漏读 `dna.genre`**：同一个 spec 传 dataclass 还是 dict，CINEDANCE 开关结果不同（`_view` 只从 one 处取 genre）。已统一为 spec 对象/字典同源。
2. **`acting.beat_line()` 去重表用错大小写**：入 `used` set 用大写后的 clause、比对却用原文，导致**同角色跨镜重复同一句**。已改为入 set 用原文。
3. **无对白/字幕驱动片仍套 PACE + SPEAKER LOCK + "before he speaks"**：静态门禁 R1 判 ERROR（"提到人说却没台词块"）。已改为 `spoken = bool(lines) and dialogue_mode not in CAPTION_MODES` 才加 PACE/LOCK，并把 SOUNDSCAPES 措辞改成 "no spoken lines at all"。
4. **`spoken_line()` 画外音措辞不命中 R8**：原措辞跨句，正则匹配不到 "lips remain completely closed"。已改为同句 `lips remain completely closed for the whole line`。
5. **`85mm 镜头` 被读成产品参数 `85m`**：`_NUMERIC_RE` 的单位后没有边界，`mm` 被截成 `m`。已加 `(?![A-Za-z0-9])`。
6. **"POV 第一人称" 被判广告法绝对化用语**：SUPERLATIVE 组 `第一` 无负向断言。已加 `(?!人称|视角|次|天|时间|步|现场|次见面)`。
7. **`check_dialogue.mjs` R26 阈值对每一条在产 prompt 误报**：旧阈值「400 单位（中文按字、英文按 1/3 计）」是 2026-09-17 中文短提示词时代的经验值，而现役英文结构提示词稳定 5.5k–6.5k 字符。已按 H3 实测**字符数** 10000/9800 重设。
8. **合规门扫整段 prompt**：编译产物是英文制作说明（`85mm 镜头`/`f/2`/`17k+5 帧`），整段扫会把摄影参数当产品参数报出来。已改为 `_spoken_copy()` 只抽 `<d>` 台词块 + 画面字幕。

## 7. 遗留与限制（交给后续 Phase）

- **prescreen 只做了"门禁 + spec 改写"接线，没有真跑过 5s 预筛**：真跑需要一次真实付费生成，留到 Phase 15.5 受预算保护的真实验收。
- **任务 10 的 `ProviderTask` 边界是 Phase 4 的成果**，本轮为复核（业务层不 import AutoDL 请求/响应私有字段，只读能力表 `WORKFLOW_SPECS`）。
- **5 个有台词骨架触发 R28 WARN**：仿真台词只有 25–34 字，低于 15s 档 65 字下限。这是**正确告警**（真实产片需把口播铺满），不是缺陷。
- **15s + 多图场景 fallback 为空是正确行为**：能力表里唯一满足的型号是 `minimax_h3_lightx2v_v5_15s`，没有第二个可切；只有 10s 需求才存在 fallback 链。
- **Phase 6 遗留的 5 条 `needs_verification` 口径仍未解决**（`shock_18` / `range_39` / `lithium_safe` / `cert_medical_device` / `patent_27`），需人工补证——见 `docs/codex_phase_6_acceptance.md` §4。
- **台词稿来源**：`_attach_lines()` 从 `docs/onetake_lines_<uid>.txt` 搬运；"自动写词"属 Phase 13 之后的能力，本轮不新增。