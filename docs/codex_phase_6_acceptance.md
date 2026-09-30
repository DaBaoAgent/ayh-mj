# Phase 6 验收记录 — 产品 Claims Registry 与内容合规事实层

- 阶段：Phase 6
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 6
- commit：`phase-6: centralize product claims and compliance facts`
- 原始证据：`docs/codex/phase6_claims_registry.txt`

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 事实层（新） | `assets/products/claims.yaml` | **27 条 claim**（20 `verified` / 5 `needs_verification` / 2 `forbidden`）；每条含计划要求的 13 个必填字段 + 5 个 Phase 6 扩展字段（`kind / status / numeric_tokens / keywords / notes`）。`valid_from / valid_to / allowed_channels / risk_level / forbidden_rewrites` 全部机器可读 |
| Claims Service（新） | `lib/claims.py`（~800 行） | `Claim`(frozen) / `ClaimsRegistry` / `load()` / `registry()` / `validate_doc()` / `RegistryError`；`tokens()`/`usable()`/`block_reason()`；`facts_block()/blocked_block()`；三态 + 有效期 + 渠道三重可用性判定 |
| 合规门（新） | `lib/claims.py` | `scan()`（禁用改写 → 数值 → 认证/质保/疗效/绝对化）+ `gate()` + `GateResult` + `Finding`；中文数字/单位等价（`十三点八公斤` ≡ `13.8kg`）；`GENERIC_TOKENS`（"认证/资质/备案/奖/专利技术"单独出现无资格映射）；**断言"未登记即阻断"** |
| 影响面分析（新） | `lib/claims.py` | `impact()` / `impact_summary()`：口径变更时列出引用了该 claim（含禁用改写）的文件与行 |
| CLI（新） | `lib/claims.py --check/--list/--facts/--gate/--impact` | 自检、导出渠道事实块、跑合规门、看影响面 |
| Engage 去重 | `s6_publish/engage.py` | **删除内置 `PRODUCT_POINTS`**（旧文案写"约20kg"，与 13.8kg 冲突）；`product_facts()` / `review_reply()` 改读 registry；自动回复过合规门，不通过转人工（新增 `blocked_claims` 统计）；`--demo` 扩到 12 项自检（7 分类 + 5 合规门），实测 **12/12** |
| 卖点池改造 | `lib/products.py` | **不再持有任何参数口径**；`SALES_POINTS` 由 registry 物化（带 `usable`/`claim_ids`/`blocked`）；新增 `claim_ids_for()`/`is_usable()`/`point_facts()`/`POINT_IDS`/`POINT_CLAIMS`；`next_point()` 优先可用卖点；`sales_points_brief()` 改读 registry 事实块；卖点显示名去掉参数（`shock_18`→"减震系统"、`light_13.8`→"轻便可提" …） |
| 评分器 | `lib/creative/scoring.py` | `NUMERIC_CLAIM_POINTS` 由 registry 派生（16 条）——注册表不可用时**保守地全部视为待核验**；`ClaimRisk` 的 reason 指向 Claims Registry |
| CreativeDNA | `lib/creative/dna.py` | 新增 `CLAIM_BLOCKED_FLAG = "卖点口径待核验/禁止对外使用"` |
| Planner | `lib/creative/planner.py` | `PlannedJob.claims_path` + `artifacts()` 增加 `claims`；`plan_for()` 落盘 `claims_<uid>.json`（`claim_ids` / `usable` / `claim` 快照 / `status_counts` / `digest` / `gate`）；卖点排序优先 `usable`；不可用卖点的 payoff 不带参数并打 `CLAIM_BLOCKED_FLAG` |
| StorySpec | `lib/creative/storiespec.py` | 新增 `claim_ids`，`to_dict()` 与 `to_spec_json()`（顶层 + `creative.claim_ids`）都输出 |
| 编排接线 | `lib/orchestrator/stages.py` | 新增 `_spec_claim_text()`（只扫会对外出现的文案）与 `_claims_gate()`；`_creative_artifacts()` 登记 `claims`；`stage_preflight` 在 `plan_only` 之后、付费生成之前调用合规门，不通过返回对应错误码并要求人工 |
| 错误码 | `lib/orchestrator/errors.py` | 新增 `CLAIM_UNMAPPED` / `CLAIM_NEEDS_VERIFICATION` / `CLAIM_FORBIDDEN`（均 `REQUIRE_HUMAN` → `BLOCKED`）；`BUSINESS_CODES` 仍恰好 20 条（既有测试断言） |
| 历史脚本清扫 | `tools/prep_g5_jingdian.py`、`tools/prep_s30_park.py` | 参数字样改为"口径见 Claims Registry" |

## 2. 必做任务逐条对照

| # | 任务 | 结果 | 证据 |
|---|---|---|---|
| 1 | 盘点 products.py / 产品 markdown / 互动回复 / 历史 prompt 的全部参数与承诺 | ✅ | `claims.yaml` 每条带 `evidence` 指回出处（如 `assets/products/轻便侠218_卖点.md#更安全`）；`--list` 输出 27 条全量 |
| 2 | 冲突参数不得由 Codex 猜正确值 → `needs_verification` + 阻止自动对外 | ✅ | 5 条 `needs_verification`（见 §4）；`Claim.usable()` 对非 verified 恒 False；`gate()` 命中即阻断 |
| 3 | Script / Packaging / Engage 只能经 Claims Service 获取产品事实 | ✅ | `lib/products.py` 已无参数口径（`test_products_source_holds_no_product_parameter_literal`）；`engage.py` 删除 `PRODUCT_POINTS`；`sales_points_brief()` 直读 registry |
| 4 | LLM 输出含数值/认证/质保/疗效表述必须映射到 claim_id，映射失败 Gate 不通过 | ✅ | `test_claims_gate.py` 30 例（矩阵 20 例正反例）；`test_unregistered_number_is_blocked_not_waved_through`（500公里/200公斤 → 阻断，`claim_ids == []`） |
| 5 | 禁止自动生成医疗疗效承诺、绝对化广告词、无法证实的认证信息 | ✅ | 疗效组 + 绝对化组 + 认证组（含 `GENERIC_TOKENS`：单独"认证/资质/备案/奖"无资格映射）；`test_plausible_but_unregistered_certificate_is_blocked`（"欧盟CE认证 + 德国红点奖" → 阻断） |
| 6 | `engage.py` 删除内置重复 PRODUCT_POINTS，改读 Claims Registry | ✅ | `product_facts()` / `review_reply()`；`--demo` 12/12（含 5 条合规门正反例） |
| 7 | 发布 artifact 保存本条视频实际引用的 claim_id 列表 | ✅ | `claims_<uid>.json` + `spec.claim_ids`；`test_planner_registers_a_claims_artifact_matching_the_spec`（两者一致、`gate.ok=True`、`digest` == registry digest） |
| 8 | claim regression tests：口径变更时知道哪些模板/内容受影响 | ✅ | `claim_ids_in()` + `impact()`/`impact_summary()`；`test_claims_impact.py` 7 例（含 `impact("light_13.8")` 命中 `lib/products.py`、`s6_publish/engage.py`、`assets/products/claims.yaml`） |

## 3. 验收标准逐条对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 同一重量/续航/承重等参数只存在一个权威机器可读来源 | ✅ | `assets/products/claims.yaml` 是唯一来源；`lib/products.py` 无参数字面量（正则扫描 0 命中）；`s6_publish/engage.py` 无内置口径 |
| 故意输出未登记参数时必须阻断，而不是"看起来合理就通过" | ✅ | `gate("充电只要20分钟")` → `CLAIM_UNMAPPED`；`gate("18股护脊减震")` → `CLAIM_FORBIDDEN`；端到端 `test_compliance_gate_blocks_before_paid_generation`（6 个入参 → job `BLOCKED`、`provider.submit_count == 0`、只跑了 plan+preflight） |
| 互动回复、脚本与发布文案引用同一事实层 | ✅ | 三者都调 `lib.claims`：Engage 走 `product_facts()`/合规门，Script 走 `sales_points_brief()`/`_claims_gate()`，发布文案走 `claims_<uid>.json` 的 `claim_ids` |
| commit 名 | ✅ | `phase-6: centralize product claims and compliance facts` |

## 4. 需要人工决策的 5 条 `needs_verification`（本阶段到此为止，不猜）

这 5 条口径互相冲突或缺证据，按计划任务 2「Codex 不猜正确值」，一律停用并转人工：

| claim_id | 冲突/缺失 | 需要人工提供什么 |
|---|---|---|
| `shock_18` | 卖点 md 写"18 股弹簧减震（12 股护脊：7 股座下 + 5 股靠背）"，历史脚本写"18 股护脊减震"——18 是总数还是护脊数无法判定 | 确认数字含义与允许的对外表述 |
| `range_39` | 续航随电池容量变化（10A→16km / 15A→25km / 22A→39km），脱开电池容量单说"续航 39 公里"属误导 | 确认是否必须带"22A 电池"限定 |
| `lithium_safe` | "医疗级"是等级/认证类表述，库内没有对应证书编号 | 补证书（如 GB 31241 / UN38.3 电池报告） |
| `cert_medical_device` | 只有一句"国家医疗器械认证"，无注册证编号/有效期 | 补注册证号与有效期 |
| `patent_27` | "27 项研发专利"无专利号清单 | 补专利清单 |

> 这 5 条只要仍为 `needs_verification`，任何包含其口径的文案都会被 `gate()` 阻断（数值/关键词命中即 block），
> 因此**不会**有未经核验的承诺流出。人工补齐后把 `status` 改回 `verified` 并填 `value/display_text` 即自动生效。

## 5. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q -m "not frontend"
249 passed, 1 skipped, 3 deselected        # 1 skipped = paid placeholder；Phase 5 结束为 183

$ .venv/Scripts/python.exe -m pytest -m frontend -q
3 passed, 250 deselected                   # 真起 uvicorn

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
```

Phase 6 新增/修改的定向测试：

| 文件 | 用例数 |
|---|---|
| `tests/unit/test_claims_registry.py` | 14 |
| `tests/unit/test_claims_gate.py` | 30 |
| `tests/unit/test_products_claims.py` | 8 |
| `tests/unit/test_claims_impact.py` | 7 |
| `tests/integration/test_claims_pipeline.py` | 9 |
| `tests/unit/test_creative_scoring.py`（改/加 2） | 10 |

原始输出见 `docs/codex/phase6_claims_registry.txt`（registry 自检、渠道事实块、合规门正反例、
影响面、engage 12/12 自检、pytest/ruff 汇总）。

## 6. 本阶段修掉的既有缺陷

1. **产品参数四套并存**：`lib/products.py`、`s6_publish/engage.py`、prompt 提示词、标题各写一套，
   且`engage.py` 的"约20kg"与产品页的 13.8kg 直接冲突。现在统一为 `assets/products/claims.yaml` 单一来源。
2. **未核验参数可被自动使用**：旧链路对"18 股护脊减震""续航 39 公里""国家医疗器械认证"没有拦截，
   现在全部标 `needs_verification` 并由 `gate()` 阻断。
3. **`products._claim_ids("")` 返回 `[""]`**：空/未知卖点 id 会带出一条空 claim_id，污染 artifact。现在返回空元组。
4. **泛化词误判**："CNAS认证"会被正则拆成 `CNAS` + `认证`，后者是泛化词、单独看无法映射，
   导致**正确**文案被判"未登记"。新增 `_absorb_host()` 把紧邻的泛化词并入具体关键词。
5. **"医疗级"类表述无检测入口**：登记在 `lithium_safe.keywords` 却不在任何检测组里，等于永不触发。
   认证组正则补入 `医疗级`，使等级/认证类表述真正可被阻断。
6. **禁用改写不可检索**：`impact()` 原先只搜 `numeric_tokens/keywords/value+unit`，旧文案里的"约20kg"
   搜不出来。现在把 `claim_id` 与 `forbidden_rewrites` 一并纳入检索。

## 7. 遗留与限制（交给后续 Phase）

- **`needs_verification` 的 5 条口径需人工补齐**（见 §4）——这是计划允许"停下来问用户"的情形之一。
- **合规门只扫"会对外出现"的文案**：`_spec_claim_text()` 取 `title` / `dna.payoff|ending|CTA|hook_type` /
  `story_spec.prompt` / 各镜 `line|dialogue|text|beat`。Phase 7 的 `PromptCompiler` 产出 prompt 后，
  同一门会自动覆盖到编译结果。
- **`products.py` 的卖点显示名仍是人工短语**（"减震系统"等）：这是"池成员命名"，不是参数口径；
  对外文案一律取 `display_text`/`spoken_text`。
- **`forbidden` 的 2 条（`sales_rank_1` / `guobu_15`）是法规/政策红线**，不是待补材料：
  即使补上佐证也不应自动使用（价格与优惠另有 engage 红线①）。
