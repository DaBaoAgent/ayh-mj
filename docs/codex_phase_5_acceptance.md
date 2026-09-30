# Phase 5 验收记录 — 自主 Planner + Trend Research + CreativeDNA

- 阶段：Phase 5
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 5
- commit：`phase-5: add autonomous planner and structured creative dna`

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| CreativeDNA（新） | `lib/creative/dna.py` | 计划要求的 **20 字段**逐一登记（字段名与计划完全一致）；受控词表 `HOOK_TYPES(8) / NARRATIVE_ARCS(8) / SHOT_PATTERNS(10) / AUDIENCES(5) / GOALS(5) / CONFLICT_TYPES(8) / VISUAL_MOTIFS(8) / CAMERA_LANGUAGES(7) / DIALOGUE_MODES(6) / AUDIO_MODES(5)`；`validate()` 做词表 + 池 id + 卡司槽位三重校验；`signature()` = (genre, hook, shot_pattern) |
| 热点归一（新） | `lib/creative/hotspot.py` | `Hotspot`(frozen) + `normalize_hotspot()`；统一 9 个字段 `source / source_type / title / published_at / heat / engagement / relevance / freshness / evidence_url`；**source_type 硬分界**（任务 4） |
| 结构库（新） | `lib/creative/structures.py` | **10 个 StorySpec 骨架**，shot_pattern 两两不同，每个带 visual_potential / conflict_strength / generation_cost / directions |
| StorySpec（新） | `lib/creative/storiespec.py` | `StorySpec` + `build_story_spec()` + `build_shots()`（BEAT_LADDER 节拍表）+ `to_spec_json()`；队列 spec 明确 `plan_only=True / prompt_ready=False / prompt=""`（任务 12） |
| 评分器（新） | `lib/creative/scoring.py` | 计划要求的 **10 个评分维度**，权重和 = 1.0；`score_dna()` 每维 0..1「越高越好」，负向维（ClaimRisk / EstimatedCost）已取反，逐维带 reason（任务 8） |
| Creative Director（新） | `lib/creative/director.py` | `rank()/shortlist()/decide()`；终选规则 `DECISION_RULE`（任务 9） |
| 卡司组（新） | `lib/creative/cast_groups.py` | 5 组角色（从 `pick_combo` 上移成唯一实现）+ `use_counts()/pick_group()/group_members()/record_group()` |
| Planner（新） | `lib/creative/planner.py`（498 行） | `CreativePlanner` + `PlannedJob` + `PlannerError` + `plan_missing()`；`needed()` 补齐、`candidates()` 10–20 廉价候选、`plan_for()` 全流程、`plan_batch()`；产物全部落盘 |
| 候选评分器（重写） | `tools/pick_combo.py` | 从"最少使用就选"升级为 16 候选 → top3 → 终选；保留 `--group/--point/--angle/--genre/--commit/--json` |
| 编排接线 | `lib/orchestrator/stages.py` | `stage_plan` 全新：有 spec → 展开 `creative.artifacts`；dry → 虚拟 spec；否则**自主规划**；失败 → `PLAN_FAILED`。`stage_preflight` 前置 `plan_only=True` → `PROMPT_NOT_COMPILED` 直接 BLOCKED（不上付费生成） |
| 编排接线 | `lib/orchestrator/service.py` | `_plan_batch` 非 dry 且队列不足时调用 `CreativePlanner`（空队列走 `needed(target)`，部分有料只补缺口）；`start()` 捕获 `PlannerError` → `ok=False, error_code=PLAN_FAILED` 且**不建任何 job**；artifact 登记去重（修掉 spec 重复登记） |
| 错误码 | `lib/orchestrator/errors.py` | 新增 `PLAN_FAILED`（可修复→REQUIRE_HUMAN）、`PROMPT_NOT_COMPILED` |
| 测试隔离 | `lib/genres.py` / `angles.py` / `products.py` / `ideas.py` | 使用次数文件的 STATE 目录跟随 `AYHMJ_STATE_DIR`，测试不再污染真实 state |
| 测试 | `tests/unit/test_creative_dna.py`(11)、`test_hotspot_normalize.py`(7)、`test_creative_scoring.py`(9)、`test_planner.py`(11)、`tests/integration/test_planner_pipeline.py`(4) | 另改写 `test_orchestrator.py` 两条为自主规划语义 |
| 证据 | `docs/codex/phase5_planner_diversity.txt`、`phase5_paid_gate_trace.txt`、`phase5_pick_combo.txt`、`phase5_verification.txt` | |

## 2. 自主规划链路（空队列点 Start）

```text
start(daily_target=N)
      ↓
_plan_batch：队列有料且够 → 原样；非 dry 且不足 → CreativePlanner
      ↓
needed(N) = N - 今日已存在/已完成（FAILED/CANCELLED 不计，任务 1）
      ↓
build_research_brief()  → 整份落 research_<uid>.json（任务 2：研究依据不只在 prompt 里）
      ↓
normalize_hotspot()     → 标 source_type / freshness（任务 3/4）
      ↓
candidates(16)          → 10–20 个廉价结构化 CreativeDNA，全程零付费（任务 6）
      ↓
CreativeDirector.rank() → 10 维评分（任务 8）
      ↓
shortlist(3) → decide() → 综合分最高（同分比 Novelty>TrendFit>SalesPointFit，再同分按骨架指纹 crc32）（任务 7/9）
      ↓
同日硬约束：signature 不重复、hook 优先未用、structure/cast 不重复（任务 11）
      ↓
build_story_spec()      → StorySpec（plan_only=True, prompt=""，任务 12）
      ↓
落 4 份产物 + 记使用次数 + 追加当日台账
      ↓
stage_preflight：plan_only=True → BLOCKED(PROMPT_NOT_COMPILED)，提交数 = 0
```

## 3. 结构多样性（计划要求的 10 种）

| id | 名称 | shot_pattern | 主叙事弧 |
|---|---|---|---|
| `S_duo_conflict` | 双人对撞短剧 | 四镜双人对撞 | 打脸反转 |
| `S_solo_vlog` | 单人 Vlog/生活流 | 五镜生活流 | 日常纪实 |
| `S_street_interview` | 街访/伪纪录 | 手持街访 | 误会解除 |
| `S_suspense_reveal` | 悬念揭晓 | 悬念三段式 | 悬念揭晓 |
| `S_magic_loop` | 魔性动作循环 | 三镜魔性循环 | 重复强化 |
| `S_product_test` | 产品实验/对比 | 实验对比双线 | 对比实验 |
| `S_pov_first` | POV 第一人称 | POV主观视角 | 情感递进 |
| `S_silent_slapstick` | 无对白肢体喜剧 | 无对白肢体三段 | 误会解除 |
| `S_emotional_story` | 情感故事 | 五镜情感递进 | 先抑后扬 |
| `S_comment_reply` | 评论区续集/回应型 | 评论区回应式 | 误会解除 |

**shot_pattern 两两不同**（10 个骨架 = 10 个不同 shot_pattern），不再"全部套 4×8"。

## 4. 必做任务逐条对照

| # | 必做任务 | 结果 | 落地位置 / 证据 |
|---|---|---|---|
| 1 | 按 `daily_target - active_or_completed_today` 补齐 | ✅ | `planner.needed()`；证据 `phase5_planner_diversity.txt`「补齐语义」段（seed 3 → needed(8)=5 → 落库后 needed(8)=0） |
| 2 | 研究结果存 artifact，不只拼 prompt | ✅ | `research_<uid>.json` 全文落盘 + 登记为 `research` artifact；`test_autonomous_start_produces_job_and_creative_dna` 断言 |
| 3 | 热点统一 normalize 9 字段 | ✅ | `hotspot.NORMALIZED_FIELDS`（来源/标题/发布时间/热度/互动/相关性/新鲜度/证据 URL + source_type）；`test_hotspot_normalize.py` 7 例 |
| 4 | 不把 evergreen 当实时热点 | ✅ | `source_type` 硬分界：live 必须「非常青平台 + 有互动量 + 可解析发布时间」；无发布时间 `freshness=None`（不假装新鲜）；常青素材 risk_flag「热点为常青素材，时效性弱」；证据见 DNA `risk_flags` |
| 5 | `pick_combo` 升级为候选评分器，保留使用次数 novelty | ✅ | `tools/pick_combo.py` 16 候选 → top3 → 终选；`used_counts()` 仍是 Novelty 特征；`--commit` 仍写 `genres_used/groups_used/sales_points_used/story_angles_used`；证据 `phase5_pick_combo.txt` |
| 6 | 先 10–20 廉价结构化候选，不直接付费 | ✅ | `CANDIDATE_MIN/MAX = 10/20`，默认 16；证据显示 `candidates=16`、`submit_count=0` |
| 7 | Creative Director 评分 → top3 → 终选 | ✅ | `director.shortlist()`（`DEFAULT_SHORTLIST=3`）；证据 `shortlist structures` 3 条 |
| 8 | 10 个评分维度 | ✅ | `scoring.SCORE_DIMENSIONS` 恰为计划的 10 维，权重和 1.0；`test_creative_scoring.py` |
| 9 | 不允许"未使用第一个"作终选 | ✅ | `DECISION_RULE` 明确写「绝不用'第一个未使用'」；`test_director_does_not_pick_the_first_candidate` + 确定性测试 |
| 10 | 历史 `used_ideas` / 角度 / 片型 / 角色记录仍作特征 | ✅ | `used_counts()` 聚合 5 类使用文件；`_record_usage()` 出片规划后回写；`test_planner.py` 相关断言 |
| 11 | 同日避免相似 hook / 骨架 / 角色组合 | ✅ | `plan_for` 同日硬约束（signature/hook/structure/cast 不重复）；证据 5 条 distinct=5/5/5/5 |
| 12 | 输出明确 StorySpec，不直接吐 H3 大 prompt | ✅ | `to_spec_json()`：`plan_only=True, prompt_ready=False, prompt=""`，只带 `story_spec` 结构；证据 `spec.plan_only=True prompt_ready=False prompt=''` |

## 5. 验收标准逐条对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 空 queue 点 Start 自动产生新 job 和 CreativeDNA | ✅ | `test_autonomous_start_produces_job_and_creative_dna`；`phase5_paid_gate_trace.txt`（空队列 → 2 条 job，各带 spec/research/dna/scores 四类 artifact）；`phase5_planner_diversity.txt`（5 条完整 DNA） |
| 一次规划 5 条，genre/hook/shot_pattern 三维明显结构差异 | ✅ | 证据 `distinct genre=5  hook_type=5  shot_pattern=5`（另 structure=5、cast_pattern=5、titles=5） |
| Planner 失败不进付费 GENERATING | ✅ | `test_planner_failure_creates_no_job_and_no_submission`（0 job、提交 0）+ `test_plan_stage_failure_stops_before_generation`（BLOCKED/PLAN_FAILED、只跑 plan）；另有 `test_plan_only_spec_is_blocked_before_paid_generation`（BLOCKED/PROMPT_NOT_COMPILED、提交 0） |
| CreativeDNA / 研究依据 / 筛选评分可在 artifact/event 追溯 | ✅ | job 的 artifacts = spec + research + creative_dna + creative_scores；`stage_end(plan)` 事件 metrics 带 `hook_type/shot_pattern/genre/structure/plan_only`；`scores_<uid>.json` 含 16 候选逐维分 + top3 + 终选规则 |
| commit 名 | ✅ | `phase-5: add autonomous planner and structured creative dna` |

## 6. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q
183 passed, 1 skipped in 9.45s        # 1 skipped = paid placeholder；Phase 4 结束为 141

$ .venv/Scripts/python.exe -m pytest -m frontend -q
3 passed, 181 deselected in 2.67s    # 真起 uvicorn

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!

Phase 5 定向：42 passed
Phase 3 编排器回归：17 passed
```

原始输出见 `docs/codex/phase5_verification.txt`；另有
`phase5_planner_diversity.txt`（5 条多样性 + 可追溯 + 补齐语义）、
`phase5_paid_gate_trace.txt`（真实编排器跑出的 BLOCKED 门禁 + artifact/event 追溯）、
`phase5_pick_combo.txt`（候选评分器 + 使用记录）。

## 7. 本阶段修掉的既有缺陷

1. **spec artifact 重复登记**：`start()` 建 job 时已登记 `spec`，`stage_plan` 又登记一次
   → 同一 job 的 artifacts 里出现两条 spec。现在 `_record_artifact()` 对
   (type, path) 去重，证据 `phase5_paid_gate_trace.txt` 中 spec 仅一条。
2. **测试污染真实 state**：`lib/genres.py / angles.py / products.py / ideas.py` 的使用次数
   文件原先写死仓库 `state/`，导致单测跑完污染真实使用记录。现改为跟随 `STATE_DIR`
   （`AYHMJ_STATE_DIR` 覆盖）。
3. **`pick_combo` 的"最少使用就选"**：已升级为候选评分器（任务 5），不再是确定性轮转。

## 8. 遗留与限制（交给后续 Phase）

- **`plan_only=True` 停在 BLOCKED 是设计内的边界**：StorySpec 已就绪，但把它编译成最终
  H3 大 prompt 的 `PromptCompiler` 属于 Phase 7。为不浪费付费额度（单条视频成本极高），
  本阶段**故意**让 preflight 拦在 `PROMPT_NOT_COMPILED`。Phase 7 落地 PromptCompiler 后
  该 gate 自动解开，届时 `prompt_ready` 变 True 即可放行。
- **热点来源仍以本地研究库为主**：`build_research_brief()` 目前从 `lib/creative_research.py`
  的知识库/常青库取素材，因此 `source_type` 多为 `evergreen`；真正的实时抓取（live 判定
  的非常青平台 + 互动量 + 发布时间链路）已在 `hotspot.py` 就位，接真实数据源即可生效。
- **评分权重是首版经验值**：`DIMENSION_WEIGHTS` 为手工设定（和 = 1.0），Phase 11
  Performance Learner 会用真实表现数据回填/校准。
- **`prompt` 字段在 plan_only spec 中为空串**：队列 spec 的 `prompt=""`、`story_spec` 带
  分镜/节拍；下游 Phase 7 负责据此生成真正可提交的 prompt。
- **卡司组 5 组**：`核心卡司 / 城市组 / 欧美组 / 时尚组 / 老外时尚组`，与 Phase 0 基线一致；
  组内成员池扩充属资产工作，不影响本阶段逻辑。
