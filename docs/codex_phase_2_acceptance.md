# Phase 2 验收记录 — 统一 JobStore 与任务状态机

- 阶段：Phase 2
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 2
- commit：`phase-2: introduce canonical job store and state machine`

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| schema 版本化 | `lib/migrations.py`（新） | migration 表 `schema_migrations`；v1=既有基线、v2=canonical job store；旧库自动识别为 v1 基线只补记；应用前自动备份到 `state/backups/`（保留最近 10 份） |
| canonical 仓库 | `lib/jobstore.py`（新） | `JobStore`：jobs/attempts/artifacts/events/evaluations/publish_records/performance_metrics 全部读写入口 + 状态机 + 成本累计 + 完整 `detail()` 视图 |
| 状态机 | `lib/jobstore.py` | 13 个主线状态 + 4 个旁路状态；`transition()` 是唯一改状态入口，非法转换抛 `InvalidTransition` 并写明允许集合；每次转换写 event |
| 兼容映射 | `lib/migrations.py` | 旧 status → canonical 一次性映射（pending→PLANNING / ready→READY / published→DONE …），迁移时逐 job 写 migration event |
| 兼容门面 | `lib/state.py` | 保留连接/trends/publishes/interactions；`create_job/update_job/get_job/list_jobs/get_stats` 全部委托 JobStore（状态走状态机校验，裸 SQL 改状态被移除） |
| 队列定位 | `lib/dispatch.py`（新） | `state/queue_15s/*.json` 降级为 **artifact/dispatch 缓存**：按 spec 内容 sha256 作 fingerprint 幂等登记，uid 沿用文件名 stem 与归档目录对应 |
| 执行器接线 | `tools/run_all.py` | 队列启动时 `sync_queue()` 登记任务；出片期间真实推进 GENERATING → QA → COMPOSING → READY（失败 → FAILED + error_code）；登记失败不阻断出片但留痕 |
| WebUI | `webui/server.py` | `/api/job/{uid}` 返回完整 trace（job+attempts+artifacts+events+evaluations+publishes）；统计口径改为 JobStore 聚合 |
| 测试 | `tests/unit/test_jobstore.py`、`test_migrations.py`、`test_dispatch.py`（新）+ `test_job_state.py`（对齐 canonical） | 20 例新增/改写 |
| 证据 | `docs/codex/phase2_jobstore_trace.txt` | PLANNING→DONE 全链转换 + 非法转换拒绝原始输出 |

## 2. 数据模型

```text
jobs            uid / status / current_stage / goal / priority / budget_cap
                cost_estimate / cost_spent / fingerprint / config_snapshot
                error_code / pause_reason / started_at / finished_at / …
attempts        job_id / stage / attempt_no / provider / model / workflow
                fingerprint / status / error_code / cost / started_at / finished_at
artifacts       job_id / type / version / stage / path / sha256 / bytes / meta
events          job_id / ts / type / from_status / to_status / stage / message / data
evaluations     job_id / kind / score / passed / stage / detail
publish_records job_id / platform / post_id / post_url / external_id / status
                ai_disclosure / error          （唯一索引 job+platform+external_id → 幂等）
performance_metrics  job_id / platform / post_id / snapshot_time / 16 项指标（可 NULL）/ raw
```

## 3. 状态机

```text
PLANNING → RESEARCHING → SCRIPTING → PREFLIGHT → GENERATING → QA
         → REPAIRING → COMPOSING → PACKAGING → READY → PUBLISHING
         → LEARNING → DONE

旁路：PAUSED / BLOCKED / FAILED / CANCELLED（可恢复到任意未终结主线状态）
终态：DONE（不可再转）、CANCELLED（仅可 retry 回 PLANNING）
特例：QA → COMPOSING（验片通过直接进入后期，跳过 REPAIRING）
```

## 4. 验收标准逐条对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 任意任务可查询完整状态、attempt、artifact、event | ✅ | `JobStore.detail()`；`docs/codex/phase2_jobstore_trace.txt`（1 job → 1 attempt / 1 artifact / 1 evaluation / 13 events） |
| WebUI 任务总数与 JobStore 实际数量一致 | ✅ | `state.get_stats()` 直接由 `store.counts()` 聚合；`test_dispatch.py::test_webui_stats_match_jobstore_counts` |
| 一个任务从 `PLANNING` 走到 `DONE`，所有转换可追溯 | ✅ | `test_jobstore.py::test_state_machine_walks_planning_to_done` + 证据文件（13 条 status_change event 完整成链） |
| 非法状态转换会被拒绝并写明原因 | ✅ | `InvalidTransition`：`DONE → PLANNING`、`PLANNING → READY` 均被拒绝且给出允许集合；`test_jobstore.py` 断言被拒后状态与事件均无变化 |
| 旧数据库备份后可成功迁移；覆盖空库 + 有数据两种 | ✅ | `test_migrations.py`：空库 `applied=[1,2]`；旧库 `applied=[2]` + 备份文件 + 6 行历史数据与状态映射全部校验 |
| queue 文件被删除/重建不会导致 JobStore 丢失任务事实 | ✅ | queue 只是 dispatch 缓存；`test_dispatch.py::test_removing_queue_keeps_jobstore_facts` |
| 禁止靠 `CREATE TABLE IF NOT EXISTS` 静默漂移 schema | ✅ | schema 由 `schema_migrations` 版本化管理；启动只跑未应用的 migration |
| 所有 job status 更新必须经 JobStore API | ✅ | `state.update_job` 委托 `store.transition()`；`store.set_fields(status=…)` 直接报错；`test_job_state.py` 断言 |

## 5. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q
93 passed, 1 skipped in 3.96s        # 1 skipped = paid placeholder

$ .venv/Scripts/python.exe -m pytest -q -m frontend
3 passed, 91 deselected in 2.57s

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
```

真实 `state/pipeline.db` 已迁移到 v2（`schema_migrations = [1, 2]`，jobs 新增 12 列，
7 张新表），迁移前自动备份 `state/backups/pipeline_<ts>.db`。

**AutoDL 付费任务提交数 = 0**（本阶段所有测试只操作本地 SQLite）。

## 6. 遗留与限制

- 旧 `publishes` / `interactions` 表仍在（`s6_publish` 读写），`publish_records` 已是 canonical
  写入目标接口；两表合并统一在 Phase 10 完成，本阶段不删历史数据。
- `webui/static/app.js` 仍按字符串匹配旧状态推断进度条（Phase 12 改为 canonical job/event UI）。
- queue 中的 spec 若与已登记 job 同名但内容不同，只更新 fingerprint 并追加 artifact 版本，
  不会重建 job（保证历史可追溯）。
- 状态机暂未把 `REQUIRE_HUMAN` 做成独立状态（Phase 4 的 RepairEngine 用 `BLOCKED` 表达）。
