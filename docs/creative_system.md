# 创意系统（Creative System）

> 对应计划 Phase 14 必做任务 11。覆盖 CreativeDNA、StorySpec、QA、Repair、Learner 五块。
> 一句话：**创意必须先变成结构化数据，才能被校验、被修复、被学习。**

---

## 0. 闭环

```text
                 ┌───────────────────────────────────────────────┐
                 │  s7_learn  历史表现回流（只学本账号自己的）      │
                 └──────────────────┬────────────────────────────┘
                                    │ HistoricalPerformance 先验
                                    ▼
  hotspot ──▶ Planner ──▶ CreativeDNA 候选(10–20) ──▶ 10 维评分 ──▶ top3 ──▶ 定稿
                                    │
                                    ▼
                              StorySpec（10 骨架之一 + 台词 + 镜头）
                                    │
                        Prescreen（高风险才跑 5s 预筛）
                                    ▼
                        PromptCompiler（六段式）+ Workflow Router
                                    │
                                    ▼
                     generate ──▶ QA（六维度）──▶ RepairEngine ──▶ compose
                                    │                    │
                                    └── 修不动 ──────────┘──▶ BLOCKED
```

每一环的产物都落成 **artifact 或 event**，所以出片之后仍能回答"为什么选这个方案"。

---

## 1. CreativeDNA（`lib/creative/dna.py`）

一条视频的**创意基因**：20 个必填字段，一个不多一个不少。

| 字段 | 取值来源 |
|---|---|
| `audience` | 受控词表（子女代购决策者 / 银发自用人群 / 家庭照护者 / 社区邻里围观者 / 图文比价人群） |
| `goal` | 受控词表（记住卖点 / 促成咨询 / 建立信任 / 场景种草 / 制造讨论） |
| `hotspot` | 趋势层给的热点词（`s1_trend` 产出；`validate()` 同样不允许为空） |
| `genre` | 池 id（片型，`lib/genres.py`） |
| `angle` | 池 id（角度，`lib/angles.py`） |
| `sales_point` | 池 id（卖点，`lib/products.py`） |
| `hook_type` | 受控词表（悬念设问 / 冲突质问 / 反差打脸 / 夸张数字 / 痛点共鸣 / 视觉奇观 / 身份代入 / 神秘物件） |
| `narrative_arc` | 受控词表（先抑后扬 / 打脸反转 / 悬念揭晓 / 重复强化 / 对比实验 / 日常纪实 / 误会解除 / 情感递进） |
| `shot_pattern` | 受控词表（10 种，见下） |
| `cast_pattern` | 角色槽位组合（`@elder_male+@mid_male` 形式） |
| `product_role` | 受控词表（解题工具 / 对比主角 / 配角道具 / 惊喜礼物 / 实验对象） |
| `conflict_type` | 受控词表（质疑能力 / 价格攀比 / 家人反对 / 陌生人误解 / 身体不便 / 旧物对照 / 时间紧迫 / 无冲突氛围向） |
| `visual_motif` | 受控词表（折叠收放 / 遥控轨迹 / 坡道爬升 / 后备箱装车 / 单手提起 / 轮圈细节 / 雨夜灯光 / 老照片对比） |
| `camera_language` | 受控词表（固定机位中景 / 手持跟拍 / 近景特写 / 俯拍全景 / 低角度仰拍 / 第一人称 POV / 侧移横移） |
| `dialogue_mode` | 受控词表（双人对白 / 单人口播 / 街访问答 / 无对白 / 画外音旁白 / 字幕驱动） |
| `audio_mode` | 受控词表（现场同期声 / BGM+音效 / 旁白+BGM / 纯音效 / 人声+字幕） |
| `payoff` | 自由文本（>= 4 字） |
| `ending` | 自由文本（>= 4 字） |
| `CTA` | 自由文本（>= 4 字） |
| `risk_flags` | 列表（如「数值承诺待核验」「卖点口径待核验/禁止对外使用」） |

**校验 `validate()` 的三条硬规则**（返回问题清单，空 = 合格）：

1. 20 个字段都不能为空（`risk_flags` 必须是列表）。
2. 受控词表字段的值**必须落在词表内** —— 不接受"看起来合理就通过"。
3. `payoff` / `ending` / `CTA` 不能是占位空串。

为什么用受控词表而不是让模型自由发挥：只有取值可控，**"相邻作品不得复用完整组合"**、
**"至少 5 种 genre / 5 种 hook_type / 4 种 shot_pattern"** 这些多样性约束才是可判定、可断言的。

---

## 2. StorySpec（`lib/creative/storiespec.py` + `lib/creative/structures.py`）

CreativeDNA 决定"是什么"，StorySpec 决定"怎么拍"。`structures.py` 提供 **10 个结构骨架**，
每个骨架自带镜头结构 / 叙事弧 / 台词模式 / 音轨模式 / 镜头语言 / 角色槽位 / 产品角色 /
冲突强度 / 视觉潜力 / 制作成本系数。

| 骨架 id | 名称 | 镜头 | 镜头模式 | 台词模式 | 叙事弧 | 冲突 / 成本 |
|---|---|---|---|---|---|---|
| `S_duo_conflict` | 双人对撞短剧 | 4 | 四镜双人对撞 | 双人对白 | 打脸反转 | 0.95 / 0.60 |
| `S_solo_vlog` | 单人 Vlog / 生活流 | 5 | 五镜生活流 | 画外音旁白 | 日常纪实 | 0.25 / 0.35 |
| `S_street_interview` | 街访 / 伪纪录 | 4 | 手持街访 | 街访问答 | 误会解除 | 0.60 / 0.55 |
| `S_suspense_reveal` | 悬念揭晓 | 4 | 悬念三段式 | 字幕驱动 | 悬念揭晓 | 0.70 / 0.50 |
| `S_magic_loop` | 魔性动作循环 | 3 | 三镜魔性循环 | 无对白 | 重复强化 | 0.20 / 0.25 |
| `S_product_test` | 产品实验 / 对比 | 4 | 实验对比双线 | 单人口播 | 对比实验 | 0.75 / 0.65 |
| `S_pov_first` | POV 第一人称 | 4 | POV 主观视角 | 单人口播 | 情感递进 | 0.55 / 0.40 |
| `S_silent_slapstick` | 无对白肢体喜剧 | 3 | 无对白肢体三段 | 无对白 | 误会解除 | 0.60 / 0.30 |
| `S_emotional_story` | 情感故事 | 5 | 五镜情感递进 | 双人对白 | 先抑后扬 | 0.50 / 0.70 |
| `S_comment_reply` | 评论区续集 / 回应型 | 4 | 评论区回应式 | 字幕驱动 | 误会解除 | 0.65 / 0.45 |

（"冲突 / 成本" 两列是骨架自带的 `conflict_strength` / `generation_cost` 系数，参与第 3 节的评分。）
`S_solo_vlog` / `S_magic_loop` / `S_silent_slapstick` 是无对白或低对白方案，
`S_product_test` 是实验对比、`S_suspense_reveal` 是悬念、`S_pov_first` 是 POV —— 多样性验收的素材来源。

骨架只描述**结构**，不写死内容 —— 内容由 DNA 的其余字段（卖点 / 角度 / 热点）填充。

**多样性是硬约束不是口号**（Phase 15 §15.4 验收）：
连续规划 >= 10 条时必须满足"不得全为两人对话 / >= 5 种 genre / >= 5 种 hook_type /
>= 4 种 shot_pattern / >= 1 条低对白 / 覆盖 Vlog·悬念·实验对比·喜剧魔性 POV"，
且**相邻作品不得同时复用 `genre + hook + angle + cast` 完整组合**。
历史相似度超过阈值 → 重新规划。

---

## 3. 候选评分（`lib/creative/scoring.py`）

Planner 先生成 10–20 个**廉价结构化候选**（不写散文、不写 H3 大 prompt），再用 10 个维度打分。

| 维度 | 权重 | 口径 |
|---|---|---|
| Novelty | 0.14 | 与历史用过的组合差异度 |
| AudienceFit | 0.13 | 骨架与受众的亲和度 |
| TrendFit | 0.10 | 与当下热点的贴合 |
| SalesPointFit | 0.12 | 卖点是否是这个方案的解题核心 |
| VisualPotential | 0.10 | 骨架的视觉潜力 |
| ConflictStrength | 0.10 | 骨架的冲突强度 |
| GenerationFeasibility | 0.11 | 生成可行性（角色数/镜头数/转场） |
| BrandSafety | 0.08 | 品牌安全 |
| ClaimRisk | 0.06 | **负向**，取 `1 - 风险` |
| EstimatedCost | 0.06 | **负向**，取 `1 - 成本` |

`total = Σ weight × score`，所有维度统一换算成"越高越好"，**不会因方向写反而失真**。
每个维度都带一句人话理由，落进 artifact 后可回答"为什么是这个方案"。

### 历史表现是先验，不是第 11 维

Phase 11 加入的 `HistoricalPerformance` **不改 Phase 5 钉死的 10 维与权重**，
只按 `learn.history_weight`（默认 0.25）把 `total` 往"历史上更像它的片子表现更好"的方向拉。
`context` 不带历史时，行为与 Phase 5 完全一致。

---

## 4. Prompt 编译与路由

- **PromptCompiler（`lib/creative/compiler.py`）**：把 StorySpec 编译成官方 Ref2VA 六段式
  （`subject_definitions` → `retention_analysis` → `detailed_description` …），
  并显式绑定音色。约束片段库在 `lib/prompt_parts.py`（**去重复硬编码的唯一落点**）。
- **预算门**：编译期就算字符数。超过服务端上限 → `PROMPT_TOO_LONG`（`COMPRESS_PROMPT` 修复）；
  压缩也压不下来 → `PROMPT_BUDGET_EXCEEDED`。
- **Workflow Router（`lib/creative/workflow.py`）**：按"必须保住的能力"（双音色对口型 / 多镜 / 15s）
  挑工作流；首选不可用或被拒时按兼容链 fallback（`SWITCH_WORKFLOW`）。
  **没有工作流能保住全部关键能力时拒绝提交**（`WORKFLOW_INCOMPATIBLE`），而不是降级出一个残废的片子。

---

## 5. Prescreen（`lib/creative/prescreen.py`）

高风险新构图先花约 1/3 的钱试拍 5 秒：

- `needs_prescreen(spec)`：**高风险**，或**中等风险 + 用了没拍过的骨架** → `True`。
- `build_prescreen_spec(spec, shot_no, seconds)`：生成与正式片同口径的 5s 预筛 spec。
- `record_prescreen(store, uid, passed=...)`：结论写进 `evaluations`（`kind = prescreen`）。
- `prescreen_passed(store, uid)`：正式生成前的放行判据。

**低风险任务不预筛**，不浪费预算；预筛成本与正式生成成本**分别记录**（Phase 15 §15.3 验收项 7）。

---

## 6. QA（`lib/qa/`）

`QaCritic` 输出六维度报告，**每个 finding 必须带稳定 `error_code`**（没有码的 finding 不成立）。

| 维度 | 标签 | 可能的 error_code |
|---|---|---|
| `product` | 视觉产品保真 | `PRODUCT_DEFORMED` |
| `cast` | 人物与表演 | `HUMAN_ANATOMY_FAIL` `WRONG_SPEAKER` `VISUAL_QA_FAIL` |
| `audio` | 音频 / 对白 | `ASR_MISMATCH` `SUBTITLE_ALIGN_FAIL` |
| `retention` | 镜头与留存代理指标 | `VISUAL_QA_FAIL` |
| `compliance` | 品牌 / 合规 | `COMPLIANCE_BLOCK` |
| `delivery` | 成片完整性 | `QA_FAILED` `DOWNLOAD_FAILED` |

严重度 `FAIL / WARN / INFO`，权重 0.35 / 0.10 / 0.0（`PASS` 只用于维度结论，不作为 finding）。

同时有多个 `FAIL` 时，`PRIMARY_PRIORITY` 决定用哪个码驱动修复：
`COMPLIANCE_BLOCK` > `DOWNLOAD_FAILED` > `PRODUCT_DEFORMED` > `WRONG_SPEAKER` > `HUMAN_ANATOMY_FAIL`
> `ASR_MISMATCH` > `SUBTITLE_ALIGN_FAIL` > `VISUAL_QA_FAIL` > `QA_FAILED`。

**合规优先**的理由很实际：先烧钱重生一版、再因为文案违规被拦下来，是最亏的顺序。

固定阈值（`lib/qa/checks.py`）：`MIN_FINAL_BYTES`、`DURATION_TOLERANCE`、`HOOK_MAX_SECONDS`、
`STATIC_MAX_SECONDS`、`PAYOFF_MAX_RATIO`、`SUB_MAX_CHARS_PER_LINE`。

---

## 7. Repair（`lib/orchestrator/recovery.py` + `errors.py`）

`RepairEngine` **只在 `REPAIR_MAP` 白名单里取动作，表外一律 `ABORT`，绝不猜**。

| 动作 | 语义 | 代表 error_code |
|---|---|---|
| `RETRY_SAME` | 同 workflow 同 prompt 再跑 | `NETWORK_TRANSIENT` `RATE_LIMIT` `DOWNLOAD_FAILED` `GENERATION_FAILED` |
| `SWITCH_WORKFLOW` | 换兼容 workflow 链 | `GENERATION_TIMEOUT` `PROVIDER_REJECTED` |
| `COMPRESS_PROMPT` | 压缩后再提交 | `PROMPT_TOO_LONG` `PROMPT_BUDGET_EXCEEDED` |
| `REGENERATE_SHOT` | 重出成片 | `VISUAL_QA_FAIL` `PRODUCT_DEFORMED` `WRONG_SPEAKER` `HUMAN_ANATOMY_FAIL` `QA_FAILED` |
| `REBUILD_SUBTITLE` | 只重建字幕 / 对齐，不重新生成 | `ASR_MISMATCH` `SUBTITLE_ALIGN_FAIL` |
| `WAIT_AND_RESUME` | 等窗口 / 配额（`PAUSED`，不算生成失败） | `PUBLISH_QUOTA` |
| `REQUIRE_HUMAN` | `BLOCKED` + 中文人工提示 | `COMPLIANCE_BLOCK` `AUTH_EXPIRED` `CLAIM_*` `CAPABILITY_BLOCKED` `BLOCKED_BUDGET` … |
| `ABORT` | `FAILED` | `UNKNOWN` 及表外 |

- 每条修复记录进 `repairs` 表：`error_code / action / rewind_to / target_shot / attempt / budget / cost / status`。
- **修复有上限**：达到 `budget` 立即 `BLOCKED`，不会无限循环（Phase 15 §15.1 验收项 10）。
- 人工提示只从 `HUMAN_HINTS` 取，**前端不解析中文 message 猜原因**（文案一改提示就哑）。

---

## 8. Learner（`s7_learn/`）

职责拆成五块，`pipeline.py` 只做接线不含算法：

| 模块 | 职责 |
|---|---|
| `collector.py` | 从本地库采集「视频 × 平台 × 快照」样本 |
| `normalizer.py` | 指标标准化（样本不足时给默认尺度 `MIN_SCALE_N`） |
| `features.py` | CreativeDNA → 可分析 feature。**20 个字段一个都不排除**（`risk_flags` 是多值） |
| `scorer.py` | 策略评分（见下） |
| `report.py` | 复盘报告 |

**特征数据来自 Planner 落盘的 `state/creative/dna_<uid>.json`（唯一事实来源）**，
这里只读它、不重新推导 DNA —— 否则"学习用的基因"和"生产用的基因"会对不上；
没有 DNA 的快照会被丢弃并记录 uid。

### 三条不能越界的原则

1. **80% 利用 + 20% 探索**（`learn.exploit_ratio`，**可配**，不是写死的规矩）。
2. **小样本必须平滑 / 给置信度**：
   `smoothed = (n * mean + prior_n * global_mean) / (n + prior_n)`。
   `prior_n` 是伪计数 —— `n` 越小越被拉回全局均值，一条偶然爆款不会让某片型直接封神。
   置信度：`n >= min_samples_medium(8)` → medium；`n >= min_samples_high(30)` → high；否则 low。
   **low confidence 的结论必须把 `n` 与时间窗口写进理由。**
3. **不做"下一条一定爆"的预测承诺**，只做基于本账号历史的相对比较。

学习窗口由 `learn.window_days`（默认 30）界定，每条结论都能追到这个窗口。

---

## 9. 可追溯性：每个环节都留证据

| 环节 | 落地 |
|---|---|
| 研究依据 | `creative.artifacts.research` |
| CreativeDNA | `creative.artifacts.dna`（同时落 `state/creative/dna_<uid>.json`） |
| 候选评分 | `creative.artifacts.scores` |
| 台词门禁 | `creative.artifacts.gate` |
| Claims 校验 | `creative.artifacts.claims` |
| 编译后的 prompt | job `artifacts`（type=`prompt`） |
| QA 报告 | `artifacts` + `evaluations` |
| 修复过程 | `repairs` 表 |
| 发布物料 | `artifacts`（type=`packaging`） |
| 表现回流 | `performance_metrics` 表 |

`plan` stage 会把这些路径整理成 artifact 清单写进 job —— 出片之后从 job 的 artifacts
就能直接翻到当初为什么选这个方案（`lib/orchestrator/stages.py` `_creative_artifacts()`）。
