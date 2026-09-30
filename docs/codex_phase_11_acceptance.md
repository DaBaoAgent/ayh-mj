# Phase 11 验收记录 — Performance Learner：让系统越做越聪明

- 阶段：Phase 11
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 11
- commit：`phase-11: add closed loop creative performance learning`
- 原始证据：
  - `docs/codex/phase11_performance_learning.txt`（幂等导入 / 跨平台标准化 / 表现差异 / 结论可追溯 / low confidence / Planner 历史先验与探索 / 复盘落盘，共 7 段实测）
  - `docs/codex/phase11_verification.txt`（ruff / 定向 pytest / 全量 pytest / 前端 smoke）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 采集（新） | `s7_learn/collector.py`（136 行） | `METRIC_FIELDS` = 计划 §指标模型 的 **16 个指标一个不多一个不少**；`clean_metrics()` 把缺失/空串**一律丢弃（落 NULL）**，绝不编造 0；`normalize_snapshot()` 缺 `timestamp/uid/platform` 直接 `ValueError`；`import_snapshots()` 幂等（按 `snapshot_key` 去重，返回 `total/imported/skipped/errors`）；`load_fixture()` 支持 `.json` 数组 / `{snapshots:[...]}` / 单对象 / `.jsonl` 四种形状；`collect_from_store()` **只读**库，返回 `metrics` + `missing`；`fetch_official()` 在**没有可信只读通道时抛 `CollectionRefused`**，不做任何浏览器绕过（计划任务 2）。 |
| 标准化（新） | `s7_learn/normalizer.py`（157 行） | `COMPOSITE_WEIGHTS`：completion .20 / avg_watch_pct .20 / retention_5s .15 / saves .10 / shares .10 / follows .10 / comments .05 / likes .05 / views .05；`Scale.pct()` 用 **p10–p90 线性映射 + clamp**（抗离群值）；`platform_scales()` 在**样本 < `MIN_SCALE_N=3` 时不产出百分位**（不猜）；`composite_of()` **只在存在的指标上重新归一**，一个都没有 → `(None, 0.0)`（"没数据"≠"表现极差"）。 |
| 特征（新） | `s7_learn/features.py`（145 行） | `FEATURE_FIELDS = tuple(REQUIRED_FIELDS)` —— **CreativeDNA 全部 20 个字段一个不排除**（计划任务 3）；`CATEGORICAL_FIELDS`(19 单值) + `MULTI_FIELDS=("risk_flags",)`（多值）；DNA 只从 Planner 落盘的 `state/creative/dna_<uid>.json` 读（唯一事实来源，不二次推导）；`join_samples()` **丢弃没有 DNA 的快照**并记 `dropped_uids`。 |
| 评分（新） | `s7_learn/scorer.py`（255 行） | `Cell` 带 `n / mean / smoothed / confidence / window_days / sample_uids`；`learn()` 平滑 `(n*mean + prior_n*global) / (n + prior_n)`（`prior_n=5.0`）；置信度分档 `min_medium=8 / min_high=30`；`historical_performance()` 无模型 → **None**，组合无匹配 → 全库均值 + `insufficient=True`；`select(ratio)` 的 **ratio = 利用概率**（1.0 必利用 / 0.0 必探索），探索池空则回退（计划任务 5/6/7）。 |
| 复盘（新） | `s7_learn/report.py`（156 行） | `SUMMARY_FIELDS` 覆盖计划点名的 genre/hook_type/angle/sales_point/cast_pattern/shot_pattern **再加 4 个**；`FIELD_LABELS` 中文字段名；Markdown 表头 `| 取值 | n | 窗口(天) | 均值 | 平滑 | 置信度 |`（每条结论都带样本量与时间窗口，计划任务 9）；JSON 与 Markdown **同一份数据**；`daily_summary()` / `weekly_summary()`。 |
| 接线（新） | `s7_learn/pipeline.py`（80 行） | `build_samples / learn_from_store / history_for_planner / import_fixture / summary_of` —— 只做接线，算法口径全部留在上面 5 个模块。 |
| CLI（新） | `s7_learn/run.py`（76 行） | `import <fixture> [--dry-run]` / `report [--day]` / `show [--day]`，读 `settings.learn`。 |
| 数据层 | `lib/jobstore.py`（LF） | 新增 `list_performance_metrics(uid=None, *, platform=None, since=None, limit=None)`：JOIN `jobs` 带 `job_uid`，统一 `_decode(raw)`。 |
| 评分契约 | `lib/creative/scoring.py`（CRLF） | 新增 `HISTORICAL_DIMENSION="HistoricalPerformance"` 与 `DEFAULT_HISTORY_WEIGHT=0.25`；`score_dna` **先算完 Phase 5 的 10 维 total，再** `total = (1-w)*total + w*prior`，并把该维度写进 `scores` 与 `reasons`（**10 维契约与权重断言完全不动**）；`explain()` 追加历史表现说明。 |
| 决策 | `lib/creative/director.py`（LF） | `decide(..., selection=None)`：选探索时终选 = 探索候选，并**并入 shortlist**（保证 TOP3 里看得见探索项）；返回新增 `explored` / `exploration`。 |
| 规划 | `lib/creative/planner.py`（LF） | `__init__` 新增 `learn/explore_ratio/rng`；`learn_config()`（settings 不可用退回内置默认）、`performance_model()`（`n_samples==0` → None，异常静默 → None）；`plan_for` 注入 `context["history"]`、把 `scorer.select(ratio=...)` 结果交给 `decide`，`rationale["history"]` 只存摘要（不落 chosen 对象）。 |
| 配置 | `lib/settings.py`（CRLF）+ `config/default.yaml`（CRLF） | `LearnSettings`：`enabled / exploit_ratio=0.8 / window_days=30 / history_weight=0.25 / prior_n=5.0 / min_samples_medium=8 / min_samples_high=30`。 |
| 导出 | `lib/creative/__init__.py`（LF） | 导出 `HISTORICAL_DIMENSION / DEFAULT_HISTORY_WEIGHT`。 |
| 工具 | `pyproject.toml`（CRLF） | per-file-ignores 增加 `"s7_learn/*.py" = ["E402"]`。 |
| Fixture（新） | `tests/fixtures/performance/{corpus.json, snapshots.json}` | 16 个 job：`LRN_G1_01..06` 强 / `LRN_G5_01..06` 弱（douyin）、`LRN_XHS_01..03` 缺指标（xiaohongshu）、`LRN_NODNA_01` 无 DNA（应被丢弃）；种子 20260930，可复现。 |
| 测试（新） | 7 个新文件 + 1 个共享工具 | 见 §5（+63 条）。 |

## 2. 必做任务逐条对照

| # | 任务 | 结果 | 证据 |
|---|---|---|---|
| 1 | `performance_metrics` 关联 job、platform、post_id、snapshot_time | ✅ | `lib/jobstore.py` 的 `list_performance_metrics()` JOIN jobs 取 `job_uid`；`collector.normalize_snapshot()` 强制四要素，缺一即 `ValueError`；`test_snapshot_requires_identity_and_timestamp` / `test_collect_from_store_is_read_only_and_keeps_all_platforms` |
| 2 | 优先官方/可信接口；需要浏览器时只低频只读，不做激进反自动化绕过 | ✅ | `collector.fetch_official()` 在无可信只读通道时**抛 `CollectionRefused`**，代码里没有任何浏览器/CDP/签名绕过路径；`test_official_fetch_is_refused_without_a_read_only_channel` |
| 3 | CreativeDNA 全部成为可分析 feature | ✅ | `FEATURE_FIELDS = tuple(REQUIRED_FIELDS)`（20 个）；`test_all_twenty_dna_fields_are_analysable_features` 断言集合**完全相等**（不多不少）；`risk_flags` 走多值通道 `test_feature_values_carries_risk_flags_as_multi_valued` |
| 4 | 每日 performance summary：genre/hook/angle/sales_point/cast/shot_pattern 表现分布 | ✅ | `report.SUMMARY_FIELDS` 含计划点名 6 项；`daily_summary()` 落盘 `state/learn/summary_<day>.{json,md}`；`test_summary_covers_the_six_dimensions_named_in_the_plan` / `test_report_lands_under_state_learn_with_both_formats` |
| 5 | Planner 候选评分加入 `HistoricalPerformance`，但必须保留探索机会 | ✅ | `HISTORICAL_DIMENSION` 进 `scores`/`reasons`；`director.decide(selection=)` 把探索候选并入 shortlist；实测 16 个候选**全部**因历史改分、top3 由 `G6/G1/G10` 变为 `G6/G9/G10`；`test_history_changes_the_scores_for_the_same_candidates` / `test_exploration_is_always_kept_in_the_shortlist` |
| 6 | 初始 80% 利用 + 20% 探索，**比例配置化不写死** | ✅ | `DEFAULT_EXPLOIT_RATIO=0.8` 只是默认值，实际从 `settings.learn.exploit_ratio`（`config/default.yaml` 的 `learn:` 段）读取，可改；`planner.__init__(learn=..., explore_ratio=..., rng=...)` 均可注入；`test_ratio_is_configurable_and_clamped` |
| 7 | 小样本用平滑/置信度，不因一条偶然爆/扑永久淘汰片型 | ✅ | 平滑 `(n*mean + prior_n*global)/(n+prior_n)`；实测 `G5` 均值 0.032 被拉回 0.236，1 条样本整体判 `low`；`test_thin_data_is_reported_as_low_confidence` / `test_small_samples_are_shrunk_toward_the_global_mean` / `test_unknown_combination_is_low_confidence_and_not_punished` |
| 8 | 不做"下一条一定爆"的预测承诺 | ✅ | `scorer.NO_PREDICTION_NOTE` 随每条结论输出："本分数只表示『相对本账号历史分布的更好/更差』，不构成『下一条一定爆』的预测"；Markdown 报告顶部引用同一句；`test_planner_decision_never_claims_a_guaranteed_hit` |
| 9 | 每条学习结论必须能追溯到样本量和时间窗口 | ✅ | `Cell.describe()` / 报告表头恒带 `n` + `窗口(天)`，`Cell.sample_uids` 记录样本 uid；实测 `genre=G1（近 30 天 n=6 均值 0.89 平滑 0.70，low 置信）` + 样本列表；`test_every_conclusion_carries_sample_size_and_time_window` |

## 3. 验收标准逐条对照（计划 §Phase 11）

| # | 验收标准 | 结果 | 证据 |
|---|---|---|---|
| 1 | 导入一组 fixture 表现数据后，系统可输出不同 CreativeDNA 的表现差异 | ✅ | 导入 16 条快照（15 条可用 + 1 条无 DNA 丢弃）后输出 `genre: G1 均值 0.890 / G7 0.567 / G5 0.032`，hook 与 shot_pattern 同向；`docs/codex/phase11_performance_learning.txt` ③④ 段；`test_fixture_import_then_report_shows_genre_differences` |
| 2 | Planner 在相同候选下受历史数据影响，但仍保留探索候选 | ✅ | 同一批 16 候选：无历史 → `G6/G1/G10`，有历史 → `G6/G9/G10`，16 个候选评分全部改变；`ratio=0.8` 时探索池仍有 16 个候选，`ratio=0.0` 强制探索（`explored=True`）；`test_planner_uses_the_learning_loop_end_to_end` / `test_exploration_pool_collects_candidates_without_enough_evidence` |
| 3 | 数据不足时明确显示 low confidence | ✅ | 1 条样本 → `confidence=low`、`low_confidence=True`；15 条样本 → `medium`；报告与 `Cell` 都带该字段；`test_thin_data_is_reported_as_low_confidence` |
| 4 | commit 文案 | ✅ | `phase-11: add closed loop creative performance learning` |

## 4. 关键实测结果（`phase11_performance_learning.txt`）

**① 幂等导入**：首次 `imported=16 skipped=0`；第二次 `imported=0 skipped=16`；库里行数恒为 16 —— 重复导入不会产生重复样本。

**② 跨平台标准化 + 缺失保持 NULL**：同一 `completion` 字段在不同平台的参照分布完全不同（douyin `n=13, p10=0.109, median=0.463, p90=0.563`；xiaohongshu `n=3, p10=0.231, median=0.258, p90=0.288`），所以**跨平台必须先各自归一**再比较。小红书样本 16 项指标只拿到 7 项，`impressions` 的 `norm` 为 `None`（缺失 → NULL，绝不是 0）。

**③ 学习结果（表现差异）**：15 条可用样本、窗口 30 天、全库均值 0.482、整体置信度 `medium`。`genre G1 n=6 均值 0.890 平滑 0.705` / `G5 n=6 均值 0.032 平滑 0.236`；`hook_type 冲突质问 0.890 / 痛点共鸣 0.032`；`shot_pattern 四镜双人对撞 0.890 / 五镜情感递进 0.032`。

**④ 结论可追溯**：每条 `Cell` 打印 `(近 30 天 n=6 均值 0.89 平滑 0.70，low 置信)` 并列出样本 uid（`LRN_G1_01..`），同一条结论能回指到具体样本与时间窗口。

**⑤ low confidence**：1 条样本 → `n_samples=1 confidence=low low_confidence=True`；报告里 `conclusion_rule` 明写"n 低于中置信阈值一律标注 low confidence，不据此淘汰任何片型"。

**⑥ Planner 历史先验 + 探索**：16 个候选全部因历史改变评分，top3 由 `G6(0.810)/G1(0.790)/G10(0.790)` 变为 `G6(0.756)/G9(0.754)/G10(0.753)`（历史先验本身从 0.593 到 0.296 分化）；`ratio=1.0` → `explored=False`，`ratio=0.0` → `explored=True`；真实规划 `P11EV` 的 `explored=True`、探索池 16 个、模型置信度 `medium`、样本 15 条；`note` 保留"不构成『下一条一定爆』的预测"口径；终选 `G6` 确实出现在 shortlist `G6、G9、G10` 中。

**⑦ 复盘落盘**：`state/learn/summary_2026-09-30.json` 与 `.md` 同源；Markdown 带样本数、时间窗口、全库均值、整体置信度、平台列表，以及两条不预测/不淘汰的说明。

## 5. 测试结果

```
ruff check lib tests tools webui s6_publish s7_learn   →  All checks passed!
定向 63 条（Phase 11 新增）                            →  63 passed
全量 pytest                                           →  571 passed, 1 skipped（Phase 10 结束为 508+1）
tests/frontend                                         →  3 passed
```

| 新增测试文件 | 条数 | 覆盖 |
|---|---|---|
| `tests/unit/test_learn_collector.py` | 11 | 16 指标字段精确一致 / 缺失不编造 0 / 幂等导入 / 快照键 / 四种 fixture 形状 / 只读 collect / 无可信通道即拒绝 |
| `tests/unit/test_learn_normalizer.py` | 8 | 逐平台参照分布 / 样本不足不产百分位 / p10–p90 映射与 clamp / 缺失保持 NULL / 只在存在维度重归一 |
| `tests/unit/test_learn_features.py` | 6 | 20 字段一个不排除 / risk_flags 多值 / 无 DNA 必丢弃 / 非法 DNA 跳过 / 只读 planner 落盘 |
| `tests/unit/test_learn_scorer.py` | 14 | 平滑拉回先验 / 置信度分档 / 无模型 → None / 结论带 n+窗口+uid / ratio=1 必利用、ratio=0 必探索 / 探索池空回退 |
| `tests/unit/test_learn_report.py` | 7 | 计划点名 6 维度都在 / 中文字段名 / JSON 与 Markdown 同源 / 落盘路径 / 日报与周报 |
| `tests/unit/test_planner_history.py` | 10 | 历史先验改变排序 / Phase 5 的 10 维契约不动 / 无样本不进先验 / 探索候选进 shortlist / 异常静默降级 |
| `tests/integration/test_learn_pipeline.py` | 7 | 导入 → 标准化 → 特征 → 学习 → 复盘端到端 + Planner 接线 + 无 DNA 丢弃 |

## 6. 本阶段修掉的缺陷

1. **`historical_performance` 把字符串按字符迭代**（真实 bug）：`values.get(field)` 在单值特征上返回 `str`，`for value in raw` 会逐字符匹配，导致 `G1` 这类组合"永远匹配不到样本"。已改为 `items = raw if isinstance(raw, (list, tuple, set)) else [raw]`；修前实测 G1 组合命中 0 条，修后 6 条。
2. `s7_learn` 4 个文件被 PowerShell 管道写入混杂 CRLF → 统一 LF，并在 `logs/_w.py` 里强制 `\r\n → \n`，杜绝再次复发。
3. `collector.import_snapshots` 对生成器先 `len()` 再遍历 → 改为 `list(snapshots)` 后再统计。
4. `scorer.NO_PREDICTION_NOTE` 中文引号内嵌双引号导致语法冲突 → 内层改『』。
5. ruff 多项：PLW2901（normalizer 循环变量覆写）、I001（`run.py` import 排序）、SIM300（Yoda 条件）、SIM115（测试 `open()` 未用 context manager）、F401（未用 import）全部修掉。
6. `test_load_fixture_supports_both_shapes` 里两处 `assert model.media if False else True` / `thin_samples = ...` 死代码已删。

## 7. 遗留与限制

1. **无官方只读采集通道**：`collector.fetch_official()` 在缺可信通道时按设计拒绝（计划任务 2 要求"不做激进反自动化绕过"），所以本阶段实测数据全部来自 fixture 与本地库导入；真实平台指标接入方式需要人工确认后再填 `fetch_official` 的实现。
2. **学习结论尚未回写任何线上策略**：模型目前只影响 Planner 的候选评分与复盘报告，不会自动改发布节奏、片型配额或提示词。计划未要求自动回写，故保持只读 + 建议。
3. **工程默认值待真实数据校准**：`history_weight=0.25`、`prior_n=5.0`、置信度阈值 `8/30`、`MIN_SCALE_N=3` 都是工程默认，不是从真实表现拟合出来的，真实数据接入后需要重新校准。
4. **Phase 6 遗留的 5 条 `needs_verification`** 仍在（`shock_18` / `range_39` / `lithium_safe` / `cert_medical_device` / `patent_27`），需人工核对来源。
5. **`vision` 段仍由 fixture 承载**（Phase 8 起），未接真实视觉模型。
6. **Phase 10 遗留**：`ai_disclosure_confirmable` 与 `domestic_draft_args` 仍是空配置，抖音等平台在真实发布前需人工补齐，否则只能转人工。
