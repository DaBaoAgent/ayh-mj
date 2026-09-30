# Phase 13 验收记录 — 测试体系、CI 与自动开发护栏

- 阶段：Phase 13
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 13
- commit：`phase-13: establish ci and autonomous development guardrails`
- 原始证据：
  - `docs/codex/phase13_ci_guardrails.txt`（12 段实测：环境快照 / 契约表 / 正例 fixture / 反例 fixture / PostFlow 文本 / 生产接线 / 故意改坏 fixture / 一条命令 / marker 纪律 / live 与 paid / fake 主链轨迹 / golden）
  - `docs/codex/phase13_verification.txt`（ruff / 定向 pytest / 全量 pytest / tools/ci.py 汇总）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 契约闸门（新） | `lib/contracts.py`（281 行） | 第三方响应契约的**声明式**登记与校验。`Rule(path / types / required / enum / nonempty / when / note)` 描述"主链真正读取的字段"，`Contract(name / endpoint / consumer / rules / custom)` 描述一个端点，`CONTRACTS` 登记 6 份。导出 `ContractError / Rule / Contract / CONTRACTS / names() / validate() / is_valid() / assert_contract()`，外加 PostFlow CLI 契约常量 `POSTFLOW_SUBCOMMAND / POSTFLOW_REQUIRED_FLAGS / POSTFLOW_AUTH_MARKERS`。约定：只声明主链真读的字段，**多出来的字段一律放行**（provider 加字段不该让生产崩），缺字段 / 类型变化 / 取值越界则抛 `ContractError` 并点名到字段。 |
| 生产接线（改） | `lib/llm.py` | `chat()` 拿到响应后 `body = assert_contract("deepseek_chat", resp.json())`，再取 `body["choices"][0]["message"]["content"]`。原来裸取三层字典，字段一变就是难懂的 `KeyError`。 |
| 生产接线（改） | `s4_generate/autodl_client.py` | `create_task` 在 `code.get("code") != "Success"` 判负之后加 `assert_contract("autodl_submit", body)`。`query_task` 同位置加 `assert_contract("autodl_result", body)`。**空 `task_id` 当场被拒**——付费任务 id 为空是绝对不能接受的。 |
| 生产接线（改） | `s6_publish/uploadpost.py` | `whoami` / `upload_video` / `upload_status` 三处用 `assert_contract("uploadpost_me" / "uploadpost_upload" / "uploadpost_status", ...)` 包住原有的 `_check(...)`。 |
| 生产接线（改） | `s6_publish/publish.py` | `_AUTH_MARKERS = POSTFLOW_AUTH_MARKERS`（直接来自 `lib.contracts`，**同一对象**，测试断言 `is` 关系），`_is_auth_error` 改为 `return postflow_is_auth_error(text)`。凭据失效判定只有一个事实源。 |
| 正例 fixture（新） | `tests/fixtures/contracts/ok/`（7 份） | 每个 provider 至少一份真实形状样本：`autodl_result.running/success`、`autodl_submit.queued`、`deepseek_chat.chat_completion`、`uploadpost_me.profile`、`uploadpost_status.completed`、`uploadpost_upload.queued`。 |
| 反例 fixture（新） | `tests/fixtures/contracts/broken/`（10 份） | 每份对应一条被破坏的契约，断言**必须被拒绝**，并在证据里逐份打印首条理由。 |
| PostFlow 文本样本（新） | `tests/fixtures/contracts/postflow/`（4 份） | CLI 纯文本输出：登录失效 / 草稿成功 / 编码失败 / 直接发布成功。 |
| 契约测试（新） | `tests/contract/test_providers.py`（35） | 全量校验 `ok/` 与 `broken/`，逐份断言"合规 / 被拒绝"，并断言拒绝理由点名到字段。 |
| 契约测试（新） | `tests/contract/test_production_wiring.py`（15） | 把坏响应**注入真实客户端**（`lib.llm.chat`、`autodl_client.create_task/query_task`、`uploadpost.whoami/upload_video/upload_status`），断言当场抛 `ContractError`。 |
| 契约单测（新） | `tests/unit/test_contracts.py`（23） | 校验器自身的纯逻辑：路径下钻 `a.b` 与 `a[]`、条件规则 `when`、`enum / nonempty / types`、`bool` 不当 `int`、`is_valid` 不抛、`ContractError` 文本、PostFlow 判定。 |
| golden（新） | `tests/golden/creative/`（manifest + 3 份） | 3 份稳定 StorySpec：`duo_conflict`（双人对峙）/ `silent_slapstick`（无对白闹剧）/ `solo_vlog`（画外音生活流）。 |
| golden 测试（新） | `tests/unit/test_golden_artifacts.py`（27） | 只断言关键结构（shot_count / line_count / cinedance）、hard constraints 与**编译纯函数性**（两次编译输出完全一致），不比较自然语言全文。 |
| 端到端（新） | `tests/integration/test_main_chain_e2e.py`（2） | fake provider + fixture media 跑 Planner -> READY 全链，含一次**真实修复回退**（PRODUCT_DEFORMED -> REGENERATE_SHOT），并断言无孤儿状态、可重复跑。 |
| 一条命令（新） | `tools/ci.py`（4960 字节） | 非 live 全量门禁：`lint -> typecheck -> unit -> marker 纪律 -> contract -> integration -> frontend -> migration`，任一步非零立即停手。**主动清除** `AYHMJ_RUN_LIVE / AYHMJ_RUN_PAID`。支持 `--skip-frontend`、`--list`。 |
| CI 工作流（新） | `.github/workflows/ci.yml` | GitHub Actions：checkout -> setup-python 3.11 -> `pip install -e ".[dev]"` -> `playwright install chromium` -> `python tools/ci.py`，失败时上传 pytest 缓存与日志。`env` 里 `AYHMJ_RUN_LIVE / AYHMJ_RUN_PAID` 显式置空。 |
| 测试纪律（改） | `tests/unit/test_jobview.py` | 补 `pytestmark = pytest.mark.unit`——Phase 12 的 23 条用例漏了 marker，会被 `-m unit` 悄悄漏跑。 |
| 文档（改） | `README.md` | 新增"测试与 CI 门禁（Phase 13）"章节：分层、一条命令、marker 纪律、live/paid 硬约束、契约 fixture 怎么加。 |

## 2. 计划必做任务逐条

### 2.1 测试层级（计划 §测试层级）

| 计划要求 | 实现 | 实测（`phase13_ci_guardrails.txt`） |
|---|---|---|
| Unit：状态机、settings、claims、router、creative scoring、repair policy、subtitle/audio 工具纯逻辑、publish quota | `tests/unit/`（33 个文件） | 621 条全绿，20.8s。且 `tests/unit -m "not unit"` 收集到 0 条（§9 第 1 行） |
| Contract：为 DeepSeek、AutoDL、Upload-Post、PostFlow 建响应 fixture | `lib/contracts.py` + `tests/contract/`（50 条）+ 21 份 fixture | 正例 7/7 合规、反例 10/10 被拒（§3 / §4），真实客户端注入 5 处全部当场拦截（§6） |
| Integration：fake LLM + fake generator + fixture video 跑 Planner -> Script -> Generate -> QA -> Repair -> Compose -> Packaging -> READY | `tests/integration/test_main_chain_e2e.py` | `P13_E2E` 终态 `READY`，8 次 stage 尝试 + 1 条 `REGENERATE_SHOT` 修复，`create_task=1`（§11） |
| Frontend：Playwright 覆盖 WebUI 关键操作和 WS/SSE 断线恢复 | `tests/frontend/` | 9 条全绿，11.5s（Phase 0 的 3 条 smoke + Phase 12 的 6 条任务台） |
| Golden：保存稳定 StorySpec/CreativeDNA，验证重构后 compiler 仍满足关键结构和 hard constraints，不比较自然语言全文 | `tests/golden/creative/` + `tests/unit/test_golden_artifacts.py` | 3 份样本 shot/line/cinedance 全对，prompt 均在上限内且未触发压缩，`Hard constraints` + 尾部完整 + `SINGLE UNIT` 均在，两次编译输出完全一致（§12） |
| Live / Paid：必须显式开启，默认 CI 永不允许提交付费任务或真实发布 | `tests/conftest.py` 的 `AYHMJ_RUN_LIVE / AYHMJ_RUN_PAID` + `tools/ci.py::_child_env` 主动 pop | `pytest tests -m "live or paid"` 默认 `1 skipped, 734 deselected`，未带任何 `AYHMJ_RUN_*` 变量，returncode=0（§10） |

### 2.2 CI 门禁（计划 §CI 门禁）

计划建议顺序：`lint -> typecheck -> unit -> contract -> integration -> frontend smoke -> migration test`。

`tools/ci.py` 逐项对齐，并在 `unit` 之后插入一道 **marker 分类纪律**检查（`tests/<layer>` 下每条用例必须带对应 marker，否则该用例会悄悄逃出门禁）。任一步非零退出即停手（"PR 未全绿禁止合并"）。`typecheck` 在本仓 = `compileall` 语法闸门，因为仓库没有 mypy，本阶段也不引入新依赖。

## 3. 验收标准 4 条对照

| # | 计划验收标准 | 结果 | 证据 |
|---|---|---|---|
| ① | 一条命令可运行所有非 live 测试 | 通过 | `.venv/Scripts/python.exe tools/ci.py` -> 7 步全 `PASS`，`returncode = 0 => 全绿`。该命令**主动清除** `AYHMJ_RUN_LIVE / AYHMJ_RUN_PAID`，所以它跑不到 live/paid（§8） |
| ② | fake 端到端主链可在无网络、无付费条件下完成 | 通过 | §11：`P13_E2E` 由 Planner 走到 `READY`，`FakeEnv` 计数 `create_task=1 / download=1 / llm=0 / upload=0`，全程无网络（fake provider 全部在进程内），`cost_spent=0.9`（768p x 15s x 0.06） |
| ③ | 任意 provider contract fixture 改坏时测试明确失败 | 通过 | §7：把 `ok/autodl_submit.queued.json` 的 `data.task_id` 改成空串，`pytest tests/contract` 立刻 `1 failed, 34 deselected`，报错文本点名 `data.task_id（付费任务 id） 不能是空字符串`，`returncode = 1`。还原后 `1 passed` 复绿 |
| ④ | commit：`phase-13: establish ci and autonomous development guardrails` | 通过 | 本阶段独立 commit，见 `git log --oneline -1` |

## 4. 关键实测

1. **契约表 6 份**：`autodl_result`（6 条规则）/ `autodl_submit`（2）/ `deepseek_chat`（2）/ `uploadpost_me`（0 条规则 + 自定义校验）/ `uploadpost_status`（0 + 自定义）/ `uploadpost_upload`（1）。PostFlow CLI 契约：子命令 `upload-video`，必需 flag `--account / --video / --title / --desc / --tags`，凭据失效信号 10 个。
2. **反例逐份点名**（§4）：`autodl_submit.empty_task_id` -> `data.task_id（付费任务 id） 不能是空字符串`。`autodl_submit.error_code` -> `code 取值 'Failed' 不在 ('Success',)`。`autodl_result.results_not_list` -> `data.results 类型应为 list，实际 dict`。`deepseek_chat.choices_not_list` -> 同类。`uploadpost_status.item_not_object` -> `results[tiktok] 应为对象，实际 str`。**10 份反例 0 份被错误接受。**
3. **生产接线当场拦截**（§6，把坏响应注入真实函数，不是另写一份校验）：`lib.llm.chat`、`autodl_client.create_task`、`autodl_client.query_task`、`uploadpost.upload_status`、`uploadpost.whoami` 全部抛 `ContractError`。`publish._AUTH_MARKERS is lib.contracts.POSTFLOW_AUTH_MARKERS -> True`。
4. **主链只提交一次付费任务**（§11）：`generate` 因为 `onetake.mp4` 已存在而在修复重跑时**跳过生成**，`create_task` 停在 1。`qa` 调了 2 次（第一次 `passed=False`，修复后 `passed=True`），`compose=1`。修复回退不重复计费。
5. **全量收集 735 条**（§9 末行），五个 marker 分布：`unit=621 / contract=50 / integration=54 / frontend=9 / paid=1`（该 paid 用例同时带 `live`，所以 621+50+54+9+1=735）。
6. **默认不跑 live/paid**（§10）：`1 skipped, 734 deselected`，`returncode=0`。

## 5. 测试结果

- `python -m ruff check lib tests tools webui s6_publish s7_learn` -> `All checks passed!`
- 定向：`pytest -q tests/unit/test_contracts.py tests/unit/test_golden_artifacts.py tests/contract` -> `100 passed in 0.46s`
- 全量：`pytest -q` -> `734 passed, 1 skipped, 1 warning in 319.75s`（Phase 12 结束为 632 passed / 1 skipped，本阶段 **+102**）
- 门禁：`python tools/ci.py` -> 7 步全 `PASS`

| 新增测试文件 | 条数 | 覆盖 |
|---|---|---|
| `tests/unit/test_contracts.py` | 23 | 校验器纯逻辑：路径下钻与 `a[]`、条件 `when`、`enum / nonempty / types`、`bool` 不当 `int`、`is_valid` 不抛、`ContractError` 文本、PostFlow 判定 |
| `tests/contract/test_providers.py` | 35 | `ok/` 7 份逐份合规、`broken/` 10 份逐份被拒且理由点名到字段、PostFlow 4 份文本判定 |
| `tests/contract/test_production_wiring.py` | 15 | 坏响应注入 6 个真实客户端函数，全部当场 `ContractError`。`_AUTH_MARKERS` 同一对象。`_is_auth_error` 转发 |
| `tests/unit/test_golden_artifacts.py` | 27 | 3 份 golden 的 shot/line/cinedance、prompt 上限、hard constraints 与尾部、`SINGLE UNIT`、编译纯函数性 |
| `tests/integration/test_main_chain_e2e.py` | 2 | Planner -> READY 全链（含修复回退、只提交一次付费任务）。无孤儿状态且可重复跑 |

## 6. 本阶段修掉的缺陷

1. **`tools/ci.py` 的 `unit` 步根本没跑单测**（本阶段真实 bug）：最初写成 `code = _marker_hygiene() if name == "unit" else _run(argv)`，`_marker_hygiene()` 顶替了 `_run(argv)`，于是"门禁全绿"其实一条单测都没跑（第一次全量门禁 `unit` 只耗时 1.6s 才暴露）。改为"先 `_run(argv)`，成功后再做 marker 纪律检查"。
2. **主链 fixture 尺寸不真实**：端到端测试最初用 9728 字节的假 mp4，被真实 delivery 检查判 `QA_FAILED`（阈值 `<100000` 字节）。改为 `VIDEO_BYTES = b"fixture-mp4-payload" * 6000`，并在 generate 阶段把 fake 落地的文件补到该尺寸。
3. **`store.list_evaluations` 需要 `kind=` 才能区分两次 `qa_report_gen`**：同一 uid 下第一次 `passed=False`、修复后 `passed=True`，不按 kind 过滤就读不出"验片结论按发生顺序"。
4. **`FileNotFoundError` 风险**：`tests/contract/test_production_wiring.py` 依赖 `tests/contract/__init__.py` 才能按包导入——已确认该文件自 Phase 0 起就存在（否则是隐藏的导入期崩溃，不是断言失败）。
5. **证据脚本 §11 读了不存在的字段**：`store.list_attempts()` 的表只有 `started_at / finished_at`，没有 `seconds`，原写法会打印一片空字符串（"看起来有数据"的假证据）。改为报 `attempt_no / status / cost / error_code`。
6. **成本不是 0**：主链断言的正确定义是"只记一次生成、修复回退不重复计费"，不是"成本为 0"。`cost_spent=0.9` 是 768p x 15s x 0.06 的真实记账。
7. **`tests/unit/test_jobview.py` 漏 marker**（Phase 12 遗留）：23 条用例没带 `pytestmark = pytest.mark.unit`，`-m unit` 会静默漏跑它们。本阶段补上，并由 `tools/ci.py` 的 marker 纪律检查长期守住。
8. **ruff**：证据脚本的 `I001 / PIE810 / F401 / UP032 / UP020 / SIM115` 全部修掉，`lib/contracts.py` 与新增测试一次性全绿。

## 7. 遗留与限制

1. **`typecheck` 是语法闸门，不是类型闸门**：本仓没有 mypy，本阶段不引入新依赖，`tools/ci.py` 用 `compileall` 表达"能不能编译"。真要类型检查需要单独一个 Phase。
2. **`frontend` 步需要 Chromium**：无浏览器环境用 `tools/ci.py --skip-frontend` 可以跳过，但那种运行**不是**全绿等价物，CI workflow 里始终会装 Playwright。
3. **契约只覆盖主链真正读取的字段**：provider 新增字段会被放行（刻意的，避免 provider 加字段就让生产崩），因此契约测试不会发现"新字段语义变化"。这是成本与收益的取舍，不是遗漏。
4. **fixture 是手工维护的真实形状快照**：provider 改响应结构时 fixture 不会自动更新，只能靠线上报警后回来改——这正是契约测试的预期用法（尽早报警，而不是自动适配）。
5. **golden 不比较自然语言全文**：计划明确要求"不要比较随机自然语言全文完全一致"，所以 golden 只锁结构、hard constraints 与编译纯函数性，prompt 文本本身允许演进。
6. **CI workflow 未在 GitHub 上真实跑过一次**：`ci.yml` 是本机 `tools/ci.py` 的封装（含 Playwright 安装与失败产物上传），首次 push 后需要在 GitHub Actions 上核对一次解释器与依赖差异。
7. **Phase 12 的六条遗留全部沿用**：无官方只读采集通道、学习结论未回写线上策略、工程默认值待真实数据校准、Phase 6 的 5 条 `needs_verification`、`vision` 仍由 fixture 承载、Phase 10 的 `ai_disclosure_confirmable` 与 `domestic_draft_args` 待人工补齐。
