# Phase 10 验收记录 — Packaging、发布接线、账号安全与 AI 合规

- 阶段：Phase 10
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 10
- commit：`phase-10: connect packaging publishing safety and ai compliance`
- 原始证据：
  - `docs/codex/phase10_packaging_publish.txt`（PackagingAgent 物料 / 平台策略矩阵 / Gate 判定矩阵 / PublishService 全流程 / 互动护栏）
  - `docs/codex/phase10_verification.txt`（ruff / 定向 pytest / 全量 pytest / 前端 smoke）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 平台策略（新） | `lib/packaging/platforms.py`（88 行） | 9 个平台的策略表 `POLICIES`：`channel`（domestic/overseas）、`requires_ai_disclosure`、`supports_draft` + `DRAFT_MECHANISM`（`postflow_draft` / `MEDIA_UPLOAD` / `privacy=private`）、标题与话题字段上限、发布窗口；`is_known / policy_for / channel_of`。 |
| 打包 Agent（新） | `lib/packaging/agent.py`（346 行） | `build_brief()` **纯函数**：3 个角度互不相同的标题候选 + 加权打分给出选择理由、封面文案/首帧策略、description、hashtags、首评候选、`claim_ids`、`ai_generated`、声明需求、发布目标（平台/窗口/模式）。`materialize()` 按平台字段上限裁剪；`validate()` 校验完整性；`REQUIRED_FIELDS` 中 **`claim_ids` 只要求"是列表"**（不强制非空 —— 有些片子本就不引用 claim）。 |
| 发布 Gate（新） | `lib/packaging/gate.py`（141 行） | `check()` 顺序恒为 **完整性 → AI 声明 → Claims 合规**；`disclosure_check()` 三种 verdict（`draft_ok` / `unconfirmed_direct` / `no_draft_channel`）；`publish_text()` 把标题+选择理由+描述+话题+首评+封面拼成唯一的合规扫描文本。 |
| 打包/暂停状态（新） | `lib/packaging/state.py`（86 行） | 唯一落盘位置：`packaging.json`（物料）与 `state/publish_paused.json`（平台暂停）；`pause_platform / resume_platform / paused_platforms / pause_reason`。 |
| 互动护栏（新） | `lib/safety/engage_guard.py`（143 行） | `EngageGuard`：滚动 1 小时上限 + 冷却+随机抖动 + **查重只看文本不看对象** + 连续失败熔断 + 状态落盘。 |
| 发布编排（新） | `lib/orchestrator/publishing.py`（319 行） | `PublishService`：把生产 job 与发布 job 合成**同一个生命周期**；`plan()` 纯演练（不改状态）；`publish()` 走 READY→PUBLISHING→LEARNING→DONE / 部分失败→PAUSED / 全失败→BLOCKED / Gate 不过→BLOCKED；幂等靠 `published()` + `publish_records.external_id=<uid>:<platform>`；AUTH_EXPIRED 立即 `pause_platform`。 |
| 错误码 | `lib/orchestrator/errors.py` | 新增 `PACKAGING_INCOMPLETE / AI_DISCLOSURE_UNCONFIRMED / REQUIRE_HUMAN_PUBLISH / PLATFORM_PAUSED / ENGAGE_CIRCUIT_OPEN / NOT_READY`。 |
| 阶段接线 | `lib/orchestrator/stages.py` | `stage_package` 在归档前**生成并保存 packaging artifact**（失败即 `PACKAGE_FAILED`），保证"每条 READY 视频都有一份完整物料"。 |
| 数据口径 | `lib/state.py` | `get_stats().published_today` 由旧 `publishes` 表改读 canonical `publish_records`（`status IN (SUCCESS, DRAFT)`）。 |
| 配置 | `lib/settings.py` + `config/default.yaml` | `publish.ai_generated / ai_disclosure_confirmable / domestic_draft_args`；`engage.reply_jitter_seconds / duplicate_window / circuit_breaker_failures`。 |
| 发布入口 | `s6_publish/publish.py`（303 行，整文件重写） | **删掉写死的标题/标签**，文案改读 packaging artifact；新增 `CliPublishAdapter`（按 Gate 裁决的 mode 走直发/草稿/转人工）；新增 `--pause/--resume`；`check_quota` 增加平台暂停检查。 |
| 互动入口 | `s6_publish/engage.py` | 评论与私信两条循环都接入 `EngageGuard`（限流/查重/熔断），价格/医疗/投诉红线与 Claims Registry 逻辑保留。 |
| 测试（新） | 5 个新文件 + 1 个补充 | 见 §5（+63 条）。 |

## 2. 必做任务逐条对照

| # | 任务 | 结果 | 证据 |
|---|---|---|---|
| 1 | 删除 `publish.py` 写死的标题/标签，全部读 Packaging artifact | ✅ | 原文件 3 处硬编码 `轻便侠218电动轮椅` + 固定 tags 全部移除；`CliPublishAdapter` 的 `copy["title"] / ["description"] / ["hashtags"]` 全部来自 packaging；`test_publish_uses_the_packaging_artifact_not_hardcoded_copy` |
| 2 | one-take job 到 READY 后可被同一 JobStore 发布，不再要求另一套旧 jobs 状态 | ✅ | `PublishService` 只认 `lib.jobstore` 的 `JobState.READY`；`show_list()` 列的就是 canonical READY；旧 `publishes` 表不再写入；`test_job_must_be_ready_to_publish` / `test_second_publish_call_after_done_is_refused` |
| 3 | 保留并加强发布窗口 / daily limit / min interval / 平台间 pacing | ✅ | `check_quota()` 保留窗口+日限+最小间隔，新增**平台暂停**拦截；`platforms.py` 逐平台带窗口与字段上限；`test_platform_pause_blocks_publish_before_channel_call`（`tests/unit/test_publish_quota.py`） |
| 4 | 幂等 external_id/job id，重试不产生重复帖子 | ✅ | `publish_records.external_id = "<uid>:<platform>"`；重入直接返回 `SKIPPED_IDEMPOTENT`，**适配器调用 0 次**；`test_republish_is_idempotent_and_never_calls_adapter_twice` / `test_repeated_publish_never_double_posts` |
| 5 | AUTH_EXPIRED 立即暂停该平台，禁止刷新/扫码/反复发布 | ✅ | `_publish_one` 见 `AUTH_EXPIRED` 即 `pause_platform`；第二次调用只返回 `PLATFORM_PAUSED` 且**通道调用数不增**；`test_auth_expired_pauses_the_platform_for_good` |
| 6 | AI 生成内容声明成为 publish gate 硬字段 | ✅ | `disclosure_check()` 是 Gate 第二步；`requires_ai_disclosure` 且 `mode=="direct"` 而声明未确认 → `AI_DISCLOSURE_UNCONFIRMED`；`ai_disclosure` 随发布结果写 `publish_records`；`test_unconfirmed_disclosure_blocks_direct_publish` |
| 7 | 抖音声明无法确认时只能草稿 / REQUIRE_HUMAN_PUBLISH，不得真发 | ✅ | 默认 `ai_disclosure_confirmable={}` → 抖音 `mode=draft`；无草稿通道的平台 → `REQUIRE_HUMAN_PUBLISH`（证据矩阵里的 `instagram`）；`CliPublishAdapter` 在 `draft` 且未配置 `domestic_draft_args` 时**拒绝执行并返回 FAILED**，绝不退化成直发；`test_douyin_ai_disclosure_cannot_be_confirmed_so_no_direct_publish` / `test_platform_without_draft_channel_requires_human` |
| 8 | 发布失败按平台独立记录，一平台失败不抹掉其他成功 | ✅ | `_finalize` 聚合逐平台结果；`SUCCESS/DRAFT/FAILED/AUTH_EXPIRED/QUOTA_BLOCKED` 各自落 `publish_records`；半成功 → `PAUSED`（可续发），全失败 → `BLOCKED`；`test_partial_failure_goes_to_paused_with_per_platform_records` / `test_adapter_exception_does_not_kill_other_platforms` |
| 9 | 互动保留价格/医疗/投诉等红线，并改用 Claims Registry | ✅ | `escalate_keywords` + `product_facts()`（唯一来源 `lib.claims`）+ 回复前过 `claims.gate()`；本轮只叠加护栏，红线逻辑不变；`test_engage_flow.py` 4 条覆盖 |
| 10 | 互动加每小时上限 / 随机安全间隔 / 重复回复检测 / 异常立即熔断 | ✅ | `EngageGuard.allow / duplicate / record_failure`；评论与私信两条循环都接入；`test_engage_guard.py` 12 条 + `test_engage_flow.py` 4 条 |

## 3. 验收标准逐条对照（计划 §Phase 10）

| # | 验收标准 | 结果 | 证据 |
|---|---|---|---|
| 1 | fake provider 下可完整执行 READY → PUBLISHING → DONE | ✅ | 事件链实测 `PUBLISHING → publish_done → LEARNING → DONE`；适配器调用 `[('douyin','draft'),('youtube','draft')]`；`test_ready_publishes_through_publishing_to_done` / `test_package_artifact_then_publish_reaches_done` |
| 2 | 同一 job 重复 publish 不产生第二次真实发布请求 | ✅ | 重入适配器调用 **0 次**、结果 `SKIPPED_IDEMPOTENT`；`test_republish_is_idempotent_and_never_calls_adapter_twice` / `test_repeated_publish_never_double_posts` |
| 3 | 抖音 AI 声明无法确认时，测试证明系统拒绝 direct publish | ✅ | 默认配置下抖音 `mode=draft`（不是 direct）；Gate 对 `mode=direct` 且未确认 → `AI_DISCLOSURE_UNCONFIRMED` 拦截；`CliPublishAdapter` 在草稿参数未配置时拒绝执行；`test_douyin_ai_disclosure_cannot_be_confirmed_so_no_direct_publish` / `test_unconfirmed_disclosure_blocks_direct_publish` |
| 4 | 发布标题/描述出现未登记 claim 被 Compliance Gate 拦截 | ✅ | `CLAIM_UNMAPPED`（未登记数字 120 公里）与 `CLAIM_FORBIDDEN`（禁用改写「约20kg」，实为 13.8kg）两种拦截实测；`test_unregistered_number_in_publish_copy_is_blocked` / `test_forbidden_rewrite_in_publish_copy_is_blocked` / `test_unregistered_claim_in_publish_copy_is_blocked` |

## 4. 关键实测结果（`phase10_packaging_publish.txt`）

**① PackagingAgent 物料**：一次 `build_brief()` 产出 3 个角度不同的标题候选，加权打分给出选择理由（卖点命中 +0.300 / 角度匹配 +0.250 / 长度适配 +0.200 / 无历史 +0.075），外加封面文案、首帧策略、描述、7 个话题、2 条首评候选、`claim_ids=['takeoff_13_8kg']`、`ai_generated=True`。

**② 平台策略矩阵**：domestic（douyin/xiaohongshu/shipinhao，草稿机制 `postflow_draft`）与 overseas（tiktok 走 `MEDIA_UPLOAD`、youtube 走 `privacy=private`，instagram/facebook/telegram/x 无草稿通道）；标题上限 20–100 字逐平台不同。

**③ Gate 判定矩阵**：

```
PASS                         完整 packaging（声明未确认 → 草稿）
BLOCK REQUIRE_HUMAN_PUBLISH  平台=instagram（无草稿通道）
PASS                         声明已人工确认 → 允许直发
BLOCK CLAIM_UNMAPPED         标题出现未登记数字 120 公里
BLOCK CLAIM_FORBIDDEN        描述使用禁用改写「约20kg」（实为13.8kg）
BLOCK PACKAGING_INCOMPLETE   标题候选只有 2 个
```

**④ PublishService**：`READY → PUBLISHING → DONE`；`publish_records` 带 `ai_disclosure=AI 生成内容（本视频画面/配音由 AI 生成）`；幂等重入 0 次调用；AUTH_EXPIRED → `BLOCKED/PUBLISH_AUTH` 并把平台写进 `state/publish_paused.json`，之后该平台只返回 `PLATFORM_PAUSED`（通道调用数保持 1）；配额拦截时通道调用 0 次。

**⑤ 互动护栏**：冷却 30s 拦、61s 过；`近一小时已回复 2/2 条（每小时上限）`；抖动样本 `[75,100,124,125,142,73,88,136]`；查重同句 True、换说法 False；连续 3 次失败熔断（前两次 False、第三次 True），人工复位后放行。

## 5. 测试结果

```text
$ python -m ruff check lib tests tools webui s6_publish
All checks passed!

$ python -m pytest -q tests/unit/test_packaging_agent.py tests/unit/test_packaging_gate.py \
        tests/unit/test_publish_service.py tests/unit/test_engage_guard.py \
        tests/unit/test_engage_flow.py tests/unit/test_publish_quota.py \
        tests/integration/test_publish_pipeline.py
69 passed in 1.27s

$ python -m pytest -q
508 passed, 1 skipped, 1 warning in 298.49s    # Phase 9 结束为 445 passed / 1 skipped（+63）

$ python -m pytest tests/frontend -q
3 passed in 2.43s
```

Phase 10 新增测试：

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/unit/test_packaging_agent.py` | 12 | 3 个标题候选/打分理由/封面/描述/话题/首评/claim_ids/声明需求/目标平台/按平台裁剪/validate/纯函数不改输入 |
| `tests/unit/test_packaging_gate.py` | 16 | Gate 顺序（完整性→声明→合规）；10 条 parametrize 的"缺字段即不完整"；草稿退路；无草稿通道转人工；未登记数字拦截；禁用改写拦截；逐平台 mode 回读 |
| `tests/unit/test_publish_service.py` | 12 | 演练不改状态；必须 READY；READY→DONE；幂等 0 次调用；DONE 后拒绝；半成功→PAUSED；全失败→BLOCKED；AUTH_EXPIRED 永久暂停；配额逐平台记录；缺 packaging 拦截；DRAFT 也算已发布；适配器抛异常不连坐 |
| `tests/unit/test_engage_guard.py` | 12 | 每小时上限/冷却/抖动/查重/熔断/落盘/人工复位 |
| `tests/unit/test_engage_flow.py` | 4 | 接入真实回复循环：每小时上限真的少发、同句不重发、连续失败开熔断并停、护栏状态落盘 |
| `tests/unit/test_publish_quota.py` | 7（+1） | 原有 6 条保留，新增"平台暂停态在调通道前就拦下" |
| `tests/integration/test_publish_pipeline.py` | 6 | 打包→合规→发布→学习 端到端（fake provider） |

> `tests/integration/test_publish_pipeline.py` 用**真实** `stage_package`（真生成 packaging artifact）+ **真实** Gate + **真实** `PublishService`，只把发布通道换成假通道；`tests/integration/*` 的 autouse fixture 把 `s4_generate.autodl_client.create_task` 换成抛错桩 —— 全程无网络、无付费、无真实发帖，付费提交数恒为 0。

## 6. 本阶段修掉的既有缺陷

1. **`publish.py` 写死文案**：原文件 3 处硬编码 `title = "轻便侠218电动轮椅"` 与固定 tags，任何片子发出去都是同一套文案。已改为全部从 packaging artifact 读取。
2. **发布有两条事实源**：旧 `publishes` 表 + `update_job(status="published")` 与 canonical `publish_records` 并存，统计与去重都对不上。已统一到 `PublishService` + `publish_records`；`lib/state.py` 的 `published_today` 改读 `publish_records(status IN (SUCCESS, DRAFT))`。
3. **发布前没有任何门**：原来只要能拼出命令就发。已加完整 Gate（完整性 → AI 声明 → Claims 合规），三条任一不过都不许"真发"。
4. **国内草稿能力未知却被当作可直发**：`domestic_draft_args` 默认空时 `CliPublishAdapter` 现在**拒绝执行并返回 FAILED**（不猜参数、不退化成直发）；这是"拒绝 direct publish"在通道层的落地。
5. **平台暂停没有状态**：AUTH_EXPIRED 以前只是本次失败，下次还会再撞。现在落盘 `state/publish_paused.json`，同平台后续直接 `PLATFORM_PAUSED`，并可用 `--pause/--resume` 人工管理。
6. **自动互动零节流**：原 `engage.py` 循环只按 `comment_id` 幂等，其余不限速。已接入 `EngageGuard`（每小时上限 + 冷却 + 随机抖动 + 查重 + 熔断）。
7. **`add_event()` 不接受 `error_code`**（Phase 8 已踩过的坑）：本轮 `publish_blocked` 事件把错误码放进 `data`，不再触发 `TypeError`。
8. **ruff 两处规范问题**：`SIM102`（可合并的嵌套 if）与 `UP012`（`str.encode("utf-8")` 冗余实参）已按规范修掉，`ruff check lib tests tools webui s6_publish` 全绿。

## 7. 遗留与限制（交给后续 Phase）

- **AI 声明全是"未确认"**：`publish.ai_disclosure_confirmable` 默认空 → 当前行为是"**所有平台只能草稿**"。要靠人工逐平台确认能否程序化提交 AI 声明（例如确认后可设 `douyin: true`），确认之前不会有任何 direct 发布。这是计划任务 7 的预期形态，不是缺陷。
- **`domestic_draft_args` 需要人工补齐**：`vendor/postflow` 不在本机，无法读它的 CLI 参数来确认草稿开关，因此默认留空 → 国内草稿模式直接拒绝执行。确认参数后（例如 `["--draft"]`）才能跑通。
- **真实发布通道本轮一次都没调用**：全部为 fake provider（测试）与 CLI 参数校验；真实直发/真草稿留到 Phase 15.5 的带预算实片验收。
- **Phase 6 遗留的 5 条 `needs_verification` 仍在**（`shock_18` / `range_39` / `lithium_safe` / `cert_medical_device` / `patent_27`），需人工补证 —— 见 `docs/codex_phase_6_acceptance.md` §4。发布 Gate 引用 `claim_ids` 时同样受此约束。
- **`vision` 段仍由 fixture 承载**（Phase 8 遗留）：PackagingAgent 在拿不到真实画面证据时用"首帧策略"文字兜底，不假装看过画面。真实多模态接入计划在后续 Phase。
- **发布窗口/日限/最小间隔仍是既有 pacing 文件的实现**：本轮只加了"平台暂停"这一层拦截，未做跨平台真实排队与时区边界验证。
- **`platforms.py` 的字段上限是按各平台公开规则填的工程默认值**：平台规则会变，改动集中在这一张表里，便于后续校准。
