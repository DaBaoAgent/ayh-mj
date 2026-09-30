# 运维与故障处置

> 对应计划 Phase 14 必做任务 10。所有处置都**不绕过**状态机与合规门 —— 运维允许"等、重试、人工确认、取消"，
> 不允许"手改 DB 把状态改过去"。

---

## 0. 先看这三个地方

| 看什么 | 命令 / 位置 | 能回答 |
|---|---|---|
| 环境能不能跑 | `python tools/health_check.py` | 缺什么能力、影响哪些 stage |
| 任务现在在哪 | `python tools/orchestrate.py status [--uid <uid>]` | 状态、stage、attempt、成本、error_code |
| 为什么走到这一步 | `GET /api/jobs/<uid>/events`（WebUI）或 DB `events` 表 | 完整因果链（谁在什么时候把状态从 A 改到 B） |

**唯一事实源是 `state/pipeline.db`。** 如果 WebUI 显示和 DB 不一致，那是 WebUI 的 bug；
`recover` 后以 DB 为准。

---

## 1. 常见故障速查

| 症状 | 大概率原因 | 处置 |
|---|---|---|
| `health_check` 报 BLOCKED | 缺 python / ffmpeg / DB 不可写 | 按报告里的 `修复：` 提示补齐；DB 不可写检查 `state/` 权限 |
| 视频生成一直不结束 | provider 排队慢 | 看 `provider_tasks.status`；等待受 `max_wait_minutes` 约束，超时转 `GENERATION_TIMEOUT` |
| 生成失败反复重试 | 网络抖动 | `NETWORK_TRANSIENT` 会指数退避；退避上限 60s，不无限重试 |
| 片子出来了但字幕错位 | ASR 漏词 / 对齐失败 | `ASR_MISMATCH` / `SUBTITLE_ALIGN_FAIL` → `REBUILD_SUBTITLE`（只重建字幕，不重新生成） |
| 产品在画面里变形 | 生成质量问题 | `PRODUCT_DEFORMED` → `REGENERATE_SHOT`，修复次数达到上限转 `BLOCKED` |
| 任务停在 BLOCKED 说合规问题 | 文案里有未登记/待核验/红线表述 | 看 `error_code`：`CLAIM_UNMAPPED` / `CLAIM_NEEDS_VERIFICATION` / `CLAIM_FORBIDDEN`；改文案或补 claim 后 `retry` |
| 任务停在 PAUSED | 上一次进程被杀 / 平台配额等待 / 部分平台发布失败 | `orchestrate.py resume --uid <uid>` |
| WebUI 启动报端口占用 | 8899 已被占 | 改 `AYHMJ_WEBUI_PORT` 或结束旧进程；**不要 kill Hermes 通道进程** |
| Playwright 冒烟失败 | 没装浏览器 | `playwright install chromium`，或 `tools/ci.py --skip-frontend` |
| 磁盘告警 | 剩余 < 2 GB（阈值） | 清 `out/` 与 `state/backups/`，见 §5 |

---

## 2. 恢复流程

### 2.1 进程崩溃 / 断电 / 机器重启

```bash
python tools/orchestrate.py recover     # 把遗留"运行中"收敛为 PAUSED
python tools/orchestrate.py status      # 确认没有任务卡在中间态
python tools/orchestrate.py resume --uid <uid>   # 逐条续跑
```

`recover` **只改状态、不创造任务**，所以不会产生重复付费：

- 如果崩溃发生在 provider **提交之后**，`provider_tasks` 里已经有 `task_id`。
  重启后只会 **query** 那个 task，**不会再 create_task**。
- 如果崩溃发生在提交**之前**，没有 task_id，重跑就是正常的第一次提交。

### 2.2 想停掉所有生产

```bash
python tools/orchestrate.py cancel --all        # 协作式取消
```

取消是"先置取消标记，再按进程树安全终止子进程"，**不留孤儿进程**。取消后任务进 `CANCELLED`（终态）。

> ⛔ 不要用 `taskkill` 直接杀 Python 进程 —— 会留下"运行中"的假状态和不完整的产物文件。
> 要走 `cancel`（或 `recover`），让状态机自己收尾。

### 2.3 想重做某一条

```bash
python tools/orchestrate.py retry --uid <uid>   # FAILED / BLOCKED 任务重试
```

`retry` 会从**第一个没有可用产物的 stage** 重新开始；已经有产物的 stage 直接跳过（幂等）。

---

## 3. 成本异常

| 现象 | 查什么 | 说明 |
|---|---|---|
| 成本比预期高 | `orchestrate.py status` 的 `cost_spent` vs `cost_estimate` | 每条 job 都在 DB 记 `cost_estimate / cost_spent / budget_cap` |
| 一直涨 | `attempts` 表（每次尝试的 cost） | 重试会累加；`repairs` 表另记修复成本 |
| 超预算后还在跑 | —— | **不应该发生**。超 `budget_cap` 立即 `BLOCKED_BUDGET`，RepairEngine 不再动作 |
| 预筛和正式生成混在一起 | `evaluations.kind` / `repairs.detail` | prescreen 成本与正式生成成本**分别记录** |

**处置**：想降本 → 减小 `daily_target`；想禁止某类重试 → 调 `REPAIR_MAP` 之外的策略只改
`lib/orchestrator/policies.py`，**不要**临时改状态绕过预算门。

---

## 4. 账号登录异常

| 平台 | 现象 | 处置 |
|---|---|---|
| 抖音（趋势抓取 / 发布） | `douyin_profile` 报 DEGRADED | `python s1_trend/browser.py --login` 扫码 |
| 任意平台 | `AUTH_EXPIRED` / `PUBLISH_AUTH` | 该平台被**立即暂停**（写 `state/publish_paused.json`）；重新登录后再放开 |
| 任意平台 | 出现验证码 / 风控提示 | 一律 `REQUIRE_HUMAN` —— **不做绕过**（不打码、不模拟、不换 IP 硬闯） |
| 国内发布 | `postflow` 报 DEGRADED | 设 `AYHMJ_POSTFLOW_DIR` 或把 PostFlow 放到 `vendor/postflow` |

熔断规则：连续失败达 `publish.circuit_breaker_failures`（默认 3）即暂停该平台，
**不循环登录、不连续发布**。恢复前先确认账号本身没问题。

---

## 5. Provider 异常

供应商异常被 `classify_exception()` 归一成稳定的 `error_code`（**不解析中文文案**）：

| error_code | 含义 | 自动动作 |
|---|---|---|
| `NETWORK_TRANSIENT` | 连接错误 / 超时 / reset | `RETRY_SAME` + 指数退避 |
| `RATE_LIMIT` | 429 / 限流 | `RETRY_SAME` + 退避 |
| `DOWNLOAD_FAILED` | 成片下载断线 / `.part` 残留 | `RETRY_SAME`（只加 download 次数，**不重新提交**） |
| `GENERATION_TIMEOUT` | 轮询超过 `max_wait_minutes` | `SWITCH_WORKFLOW` |
| `PROVIDER_REJECTED` | 参数不被接受 / 提交失败 | `SWITCH_WORKFLOW` |
| `GENERATION_FAILED` | 服务端生成失败 | `RETRY_SAME` |
| `PROMPT_TOO_LONG` | 超过服务端 prompt 上限 | `COMPRESS_PROMPT` |
| `AUTH_EXPIRED` | 401/403/token 过期 | `REQUIRE_HUMAN`（暂停平台） |
| `ASSET_MISSING` | 输入资产缺失 | `REQUIRE_HUMAN` |
| `RATE_LIMIT` 之外的业务拒绝 | —— | **绝不当网络异常无限重试**（`PERMANENT_CODES`） |

排查命令：

```bash
python tools/orchestrate.py status --uid <uid>          # 看当前 error_code
python -m pytest tests/unit/test_idempotency.py -q      # 验证幂等仍然成立
python -m pytest tests/contract -q                      # 第三方响应契约是否漂移
```

如果**契约测试**红了 → 供应商改了返回结构，先修 `lib/contracts.py` 的解析再谈生产。

---

## 6. 数据库

```bash
python -m pytest tests/unit/test_migrations.py -q     # 迁移有版本、幂等、可回滚
python -m pytest tests/unit/test_job_state.py -q      # 状态机转换合法性
```

- 迁移前**自动备份**非空旧库到 `state/backups/`（保留最近 10 份）。
- 迁移是**只增不删**：历史行不丢，旧状态折算成 canonical 并写 `events`。
- `SQLite busy`（短暂锁等待）：连接 `timeout=30` + `WAL`，正常只会短暂等待；持续 busy 说明有进程
  长时间握着写事务，用 `status` 找出还在跑的任务并 `cancel`。
- 备份占空间：`state/backups/` 可安全删除旧文件，但别删最新一份。

磁盘不足时：`health_check` 的 `disk` 项会在剩余 < 2 GB 时转 DEGRADED 并提示；
**不要**在磁盘告急时启动新任务 —— 生成到一半写不下会留下半个 mp4，反而更难清理。

---

## 7. 人工阻断清单（系统主动停下来等人）

| 状态 / 事件 | 触发条件 | 人工要做的事 |
|---|---|---|
| `BLOCKED`（`COMPLIANCE_BLOCK` / `CLAIM_*`） | 文案含未登记、待核验或红线表述 | 改文案，或把事实登记进 `assets/products/claims.yaml` |
| `BLOCKED`（`REQUIRE_HUMAN` 系列） | 凭据缺失、资产缺失、能力缺失、预算超限 | 按 WebUI 的中文提示补齐 |
| `BLOCKED`（修复达上限） | RepairEngine 用满 `budget` | 看 `repairs` 表定位重复失败原因 |
| `REQUIRE_HUMAN_PUBLISH` | AI 声明无法程序化确认，且该平台没有草稿通道 | 人工发布，或确认该平台可程序化提交声明后改配置 |
| `AUTH_EXPIRED` / `PUBLISH_AUTH` | 平台登录失效 | 重新登录；系统已暂停该平台 |
| `ENGAGE_CIRCUIT_OPEN` | 自动互动连续异常 / 超频 | 查 `state/engage_state.json` 与账号状态 |
| 验证码 / 风控提示 | 平台反自动化 | 人工处理，**不绕过** |

---

## 8. 排障命令速查

```bash
# 环境
python tools/health_check.py
python tools/bootstrap.py --json

# 任务
python tools/orchestrate.py status
python tools/orchestrate.py status --uid <uid>
python tools/orchestrate.py recover
python tools/orchestrate.py resume --uid <uid>
python tools/orchestrate.py retry  --uid <uid>
python tools/orchestrate.py cancel --uid <uid>

# 回归（不含 live / paid）
python tools/ci.py
python tools/ci.py --skip-frontend

# 单点检查
python -m pytest tests/unit -q
python -m pytest tests/contract -q
python -m pytest tests/integration -q

# 清理（WebUI 的"清理"按钮等价）
python tools/cleanup_project.py
```
