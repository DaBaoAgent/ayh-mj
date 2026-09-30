# Phase 0 验收记录 — 冻结基线、建立安全网

- 阶段：Phase 0
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 基线 commit：`61349e88204081978c452dcb6c830ad1972a5453`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 0

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 分支 | — | 从 `master@61349e8` 建 `codex/ayh-mj-vNext`，后续所有提交只进此分支 |
| 测试基建 | `pyproject.toml` | 新增 `[tool.pytest.ini_options]`：testpaths、norecursedirs、6 个 marker、告警过滤 |
| 测试基建 | `tests/conftest.py` | marker 门禁（live/paid 默认跳过）、`tmp_state`（隔离落盘）、`fake_providers` |
| 测试基建 | `tests/fakes/providers.py` | FakeEnv：假 AutoDL / LLM / Upload-Post + create/query/download/llm/upload 调用计数 |
| 单测 | `tests/unit/*.py` | 6 个模块 45 例：state / workflow_router / 创意选择器 / novelty / SRT+拆行 / publish 配额 / 安全网自证 |
| 付费门禁 | `tests/paid/test_paid_placeholder.py` | 只有 `AYHMJ_RUN_PAID=1` 才可能执行 |
| 前端 smoke | `tests/frontend/test_webui_smoke.py` | Playwright：页面渲染、settings 加载、Start/Stop、Hermes 不可用不崩 |
| 文档 | `docs/architecture/current_pipeline.md` | 现网真实调用链 + 两套事实源 + 硬编码清单 |
| 文档 | `docs/codex/phase0_*.txt` | bootstrap / engage demo / check_dialogue 自检原始输出、环境快照 |
| 修复 | `lib/console.py` + `lib/__init__.py` / `tools/bootstrap.py` / `s6_publish/engage.py` | **基线缺陷**：Windows GBK 控制台打印 ✓/emoji 直接 UnicodeEncodeError；统一开启 UTF-8 |
| 修复 | `tools/__init__.py` | **基线缺陷**：本机 `PYTHONPATH` 里同名 `tools` 包遮蔽仓库 `tools/`；加 `__init__.py` 让常规包优先命中 |
| 清理 | `pyproject.toml` ruff `exclude` | 把 `_deprecated_*` / `assets` / `docs` / `scripts` 排除出 lint（历史归档与一次性抓取脚本） |
| 清理 | 12 个源码文件 | 机械修掉 42 条既有 lint（E741/E702/SIM105/E402/F841/B007/PLW0603…），`ruff check .` 归零 |

## 2. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q
48 passed, 1 skipped in 2.82s        # 唯一 skipped = paid placeholder（默认门禁生效）

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!

$ .venv/Scripts/python.exe -m pytest tests/frontend -q
3 passed in 11.35s                   # Playwright chromium，真实起 uvicorn（--lifespan off）
```

**AutoDL 付费任务提交数 = 0**（fake provider 自证：`tests/unit/test_safety_net.py` 断言
`create_task` 只累加本地计数、不产生网络请求；全量测试期间无任何真实 `create_task`）。

## 3. 基线自检输出（原文见 `docs/codex/`）

- `phase0_bootstrap_check.txt` — 5 项就绪 / 2 项待办：
  - ○ 抖音登录：`state/browser-profile` 缺失（需扫码）
  - ○ PostFlow：`vendor/postflow` 缺失（`vendor/` 被 .gitignore 忽略，与"应随仓库存在"矛盾 → Phase 1 决策）
  - ✓ venv / 核心依赖 / ffmpeg / DeepSeek+AutoDL 凭据 / Upload-Post key
- `phase0_engage_demo.txt` — 评论分类自检 7/7 通过
- `phase0_check_dialogue.txt` — `docs/onetake_check_W2_carvoice.txt` 0 ERROR / 1 WARN（R26 体量提示，历史产物）

## 4. 已记录的基线缺陷（不掩盖）

1. **GBK 控制台崩溃**（已修）：`tools/bootstrap.py`、`s6_publish/engage.py` 在 GBK 控制台直接 UnicodeEncodeError。
   → 统一 `lib/console.enable_utf8_console()`；仍建议 Phase 1 把它接进 settings/health 体系。
2. **`PYTHONPATH` 遮蔽**（已缓解）：机器级 `PYTHONPATH=D:\@佳康顺矩阵\hermes` 内含同名 `tools` 包。
   → 本仓库 `tools/__init__.py` 缓解；环境级隐患记入 Phase 1（能力探测需自证 import 来源）。
3. **lint 基线脏**（已收敛）：改造前 `ruff check .` 有 230 条，其中 167 条来自 `_deprecated_*`/`assets`/`docs`/`scripts` 等非源码目录。
   → 收窄 lint 范围后真实源码 63 条，本阶段全部机械修复。
4. **`tools/check_xinao10*.py` 导入即读文件**：模块级读 `state/_xinao10_lines.json`，`import` 会 FileNotFoundError。
   → 属一次性校验脚本，Phase 14 legacy 收敛时处理。
5. **两套事实源 / 六阶段假状态 / 设置不贯穿**：见 `docs/architecture/current_pipeline.md` §2、§3；
   分别在 Phase 2（JobStore）、Phase 3（Orchestrator）、Phase 12（WebUI）解决。
6. **后期重复 ASR**：small + medium 两次转写，Phase 9 收敛为 canonical transcript。
7. **`vendor/` 与 `.gitignore` 冲突**：Phase 1 决策（submodule / 安装步骤 / 可配置路径）。
8. **无 `state/queue_15s/`**：当前仓库队列为空；`/api/start` 在空队列下只是写状态后退出（无副作用，smoke 已验证）。

## 5. 验收标准核对

| 标准 | 结果 |
|---|---|
| `pytest` 基础测试全部通过 | ✅ 48 passed / 1 skipped(gated) |
| 测试期间 AutoDL 提交数 = 0 | ✅ fake 自证 + 无真实调用 |
| WebUI smoke 通过 | ✅ 3 passed（Playwright） |
| 已知基线缺陷写入 acceptance 文档 | ✅ 上文 §4 共 8 项 |
| commit `phase-0: freeze baseline and add regression safety net` | ✅ 见 git log |

## 6. 遗留到后续 Phase 的项

- Phase 1：`lib/settings.py`、能力探测 health check、去硬编码路径、`vendor/` 决策、依赖锁定。
- Phase 2：migration-backed JobStore 取代 `lib/state.py` 裸 SQL。
- Phase 3：唯一 PipelineOrchestrator 统一 WebUI/CLI/Hermes。
- Phase 9：单一 canonical transcript。
- Phase 12：WebUI 以 JobStore/事件流为唯一事实源。
- Phase 14：`tools/check_xinao10*.py` 等一次性脚本收敛。
