# Phase 14 验收记录 — Legacy 收敛、文档更新与最终架构清理

- 阶段：Phase 14
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 14（685–711 行）
- commit：`phase-14: retire legacy pipeline and document vnext architecture`
- 原始证据：
  - `docs/codex/phase14_legacy_retirement.txt`（10 段实测：基线 / pipeline.yaml / run_all / BGM-SFX 唯一入口 /
    `_deprecated_*` 隔离 / 配置权威 / 去硬编码路径 / tools 分类 / fresh clone / 文档交付）
  - `docs/codex/phase14_verification.txt`（ruff / 定向 pytest / marker 分布 / 全量 pytest / collect-only / CI 门禁）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 唯一权威配置（收敛） | **删除** `config/pipeline.yaml`；`lib/settings.py`、`s1_trend/run.py`、`s1_trend/competitor.py`、`s6_publish/uploadpost.py` | 全仓最后一个"第二套配置来源"被移除。`load_settings()` 只剩 `config/default.yaml` + `_env_overrides()`，不再有"文件缺失就回退到 pipeline.yaml"的兜底分支，也不再打印 deprecation 警告。删掉 `LEGACY_CONFIG` / `_read_yaml` 兜底 / `_WARNED` / `sys` import。 |
| 本机路径清理 | `config/default.yaml` / `lib/hellgrind.py` / **untrack** `assets/cast/voice/_audition_tmp/` / `.gitignore` | `legacy_keyfiles` 删掉两条本机不存在的路径（`D:/自动剪辑/AutoDL/scripts/.env`、`佳康顺/.env`），只保留仍在用的那一条；`lib/hellgrind.py` 去掉 `D:\@kaifa\higgsfield-hell-grind-skills\` 绝对路径；试听缓存目录（内含写着 `D:/@kaifa/...` 的 ffmpeg list）从索引移除并加入 `.gitignore`，**本地文件保留不是删除**。 |
| 旧入口声明废弃 | `tools/run_all.py` | docstring 改为明确 DEPRECATED，`main()` 向 stderr 打印 `[deprecated] ... 生产请直接用 tools/orchestrate.py`。旧参数翻译能力保留（WebUI 与老脚本仍可用），但身份不再含糊。 |
| 产品事实去重 | `lib/llm.py` / `s6_publish/engage.py` / `s5_compose/burn_subtitles.py` / `assets/products/claims.yaml` | LLM 默认文案不再写第二套品牌/卖点硬编码（改由 `get_settings().product` 取）；`gen_reply()` 品牌名取自 settings；字幕高亮词从手写 12 词改为 `highlight_words()` **派生**（品牌 + 产品中文主名 + Claims Registry `usable("subtitle")` 的词 + 台标口号），并**刻意剔除** registry 里仍是 `needs_verification` 的「医疗级/锂电/屋里充」；给 `brand_cta` / `light_13.8` / `fold_1s` 补 `subtitle` 渠道，使字幕渠道有可用事实。 |
| BGM/SFX 唯一策略入口（核实） | `tools/audio_polish.py` / `tools/make_15s.py` | 核实两处都只调 `lib.post.audio_director.select_bgm` 与 `lib.post.sfx.plan_sfx`；全仓已无 `random.choice/sample/randint/shuffle` 选曲（证据 §④）。`make_15s._recent_bgm()` 只作为"最近未使用"惩罚项输入，不是第二套逻辑。 |
| 工具身份钉死 | **新增** `tools/README.md` | 把 `tools/` 分成 A 入口 / B 可复用服务 / C 一次性人工工具三类并逐条列出，明确"唯一入口是 orchestrate.py"。 |
| 门禁噪音清理 | `tools/ci.py` | `TYPECHECK_TARGETS` 过滤掉已归档、不存在的 `s2_copy` / `s3_storyboard`，`compileall` 不再每次打印 `Can't list`（否则真正的语法错误更难被看见）。 |
| 回归守卫（新增测试） | `tests/unit/test_legacy_fact_sources.py`（7 条） | 用 AST（注释/docstring 不算依赖）守住四类旧事实源：`pipeline.yaml` 不得再被当路径读、音频选曲不得回到 `random.*`、`_deprecated_*` 不得被 import 或当 `sys.path` 拼进去、`run_all.py` 必须自声明废弃；另加 `config/default.yaml` 不得含本机绝对路径。 |
| 文档 | **新增** `docs/architecture/vnext.md` / `docs/operations.md` / `docs/creative_system.md`；**重写** `README.md` | vNext 架构 + 数据库 ER（mermaid）+ 状态机（mermaid）；运维与故障处置；创意系统（CreativeDNA/StorySpec/QA/Repair/Learner）；README 覆盖安装·health check·启动·创建目标·恢复任务·人工阻断·发布安全·测试方法。 |

## 2. 计划必做任务逐条

| # | 计划要求 | 实现 | 实测 |
|---|---|---|---|
| 1 | 搜索所有对旧 `run_all.py`、旧六阶段状态、旧 queue 事实源的引用 | `tests/unit/test_legacy_fact_sources.py` + 证据 §②③ | 旧六阶段状态只剩 `STATUS_ALIASES` 归一（v2 迁移已折算历史行）；`state/run_status.json` / `run_progress.jsonl` 在业务代码里已**无读取**，仅出现在 `tools/cleanup_project.py` 的保留名单与注释中；`webui/server.py` 明写"不再读 run_status.json 猜阶段" |
| 2 | 确认 Orchestrator 已覆盖后，把旧入口标记 deprecated 或移入 legacy | `tools/run_all.py` 标 DEPRECATED + 运行时 stderr 提示 | 证据 §③：`含 [deprecated]=True`、`含 DEPRECATED=True`、`指向 orchestrate=True` |
| 3 | `pipeline.yaml` 删除已无效字段；保留则必须发 deprecated warning | **直接删除**（唯一权威 = `default.yaml`），因此无需 warning | 证据 §②：文件不存在、git 未跟踪、AST 扫描**零命中**；只剩 5 处注释/docstring 提及 |
| 4 | 合并重复 BGM/SFX 选择逻辑，AudioDirector 为唯一策略入口 | 核实 + 守卫测试 | 证据 §④：`select_bgm` 只定义在 `lib/post/audio_director.py`，调用方只有 `tools/audio_polish.py` / `tools/make_15s.py`（+ `lib/post/__init__.py` 再导出）；`random.*` 选曲 0 处（2 处命中均为解释历史的中文注释） |
| 5 | 合并重复产品事实文本，Claims Registry 为唯一事实来源 | `lib/llm.py` `_product_defaults()`、`s6_publish/engage.py`、`s5_compose/burn_subtitles.py` `highlight_words()`、`assets/products/claims.yaml` | `python lib/secrets.py` 正常；`default_profile()` → `xiangge`；字幕高亮词不再含未核验口径 |
| 6 | 清理不再使用的本机绝对路径和历史临时脚本 | 见 §1「本机路径清理」+ `tools/README.md` C 类清单 | 证据 §⑦：业务代码/配置里仅剩 `config/default.yaml` 那条**仍在用**的 keyfile 路径（有意保留，注释已说明换机改这里）；`_audition_tmp` 已 untrack 且被 gitignore 命中 |
| 7 | `_deprecated_*` 不参与运行、测试 discovery、module import 和 WebUI | 四个守门点 + AST 扫描 | 证据 §⑤：`pyproject.toml`（ruff exclude + `norecursedirs`）、`lib/claims.py` `SKIP_DIRS`、`tools/cleanup_project.py`、`tests/unit/test_no_hardcoded_paths.py`；**import 命中 0 处**；`pytest --collect-only` 收集 742 条，**来自归档目录 0 条**（归档下确有 17 个 `test_*.py`） |
| 8 | 更新 README：安装 / health check / 启动 / 创建目标 / 恢复任务 / 人工阻断 / 发布安全 / 测试方法 | 重写 `README.md`（269 行） | 证据 §⑩：8 个小节全部 ✓ |
| 9 | 新增 `docs/architecture/vnext.md` 与数据库 ER/状态机图 | 新建（350 行） | 含 5 条不变量分层图、6 个 stage 表、4 个 migration 版本的 mermaid `erDiagram`、`stateDiagram-v2` 状态机、幂等与恢复、两道合规门、与旧管线的收敛对照表 |
| 10 | 新增 `docs/operations.md`：常见故障 / 恢复流程 / 成本异常 / 账号登录异常 / provider 异常 | 新建（190 行） | 8 节全部覆盖，另含数据库、人工阻断清单、排障命令速查 |
| 11 | 新增 `docs/creative_system.md`：CreativeDNA / StorySpec / QA / Repair / Learner | 新建（253 行） | 闭环图 + 20 字段表 + 10 骨架表（实测值）+ 10 维评分表 + 六维度 QA 表 + 8 个修复动作表 + Learner 三原则 + 可追溯性表 |

## 3. 验收标准逐条

| # | 标准 | 结论 | 证据 |
|---|---|---|---|
| 1 | 全仓搜索不存在业务代码继续依赖已废弃事实源 | **通过** | `tests/unit/test_legacy_fact_sources.py` 7/7 通过；证据 §②③④⑤ 四类旧事实源全部零业务依赖 |
| 2 | fresh clone + 文档步骤能启动到 DEGRADED/READY 可解释状态 | **通过** | 证据 §⑨：依赖清单齐备 → venv 解释器存在 → `tools/health_check.py` 输出 `DEGRADED｜阻塞 0 项 / 降级 3 项`（whisper 未装 / 抖音未登录 / PostFlow 未装，每项都带 `修复：`）→ DB 迁移到 `SCHEMA_VERSION=4`、`applied=[1,2,3,4]` |
| 3 | 全部非 live 测试通过 | **通过** | `741 passed, 1 deselected`（全量 313.6s）；`tools/ci.py` 七步全 PASS（318s） |
| 4 | commit：`phase-14: retire legacy pipeline and document vnext architecture` | **完成** | 本阶段独立 commit |

## 4. 测试结果

```text
$ python -m ruff check lib tests tools webui s6_publish s7_learn
All checks passed!

$ python -m pytest -q tests/unit/test_legacy_fact_sources.py
7 passed

$ python -m pytest -q -m "not live and not paid"
741 passed, 1 deselected, 1 warning in 313.57s

$ python -m pytest --collect-only -q
742 tests collected

marker 分布：unit 628 / contract 50 / integration 54 / frontend 9 / paid(+live) 1

$ python tools/ci.py
  PASS  lint / typecheck / unit / contract / integration / frontend / migration
全部门禁通过（总耗时 318.5s），returncode = 0
```

Phase 13 结束时为 `734 passed / 1 skipped`、`735 collected`；本阶段 **+7 条**（`tests/unit/test_legacy_fact_sources.py`），
`741 + 1 deselected = 742`，与 collect 数一致。

## 5. 新增/修改文件清单

**新增**：`tools/README.md`、`docs/architecture/vnext.md`、`docs/operations.md`、`docs/creative_system.md`、
`tests/unit/test_legacy_fact_sources.py`、`docs/codex/phase14_legacy_retirement.txt`、`docs/codex/phase14_verification.txt`。

**修改**：`README.md`、`config/default.yaml`、`lib/settings.py`、`lib/llm.py`、`lib/hellgrind.py`、
`s1_trend/run.py`、`s1_trend/competitor.py`、`s5_compose/burn_subtitles.py`、`s6_publish/engage.py`、
`s6_publish/uploadpost.py`、`assets/products/claims.yaml`、`tools/run_all.py`、`tools/ci.py`、
`tests/unit/test_settings.py`、`.gitignore`。

**删除**：`config/pipeline.yaml`（索引与工作区同时删除）。

**从索引移除（本地保留）**：`assets/cast/voice/_audition_tmp/`（15 个文件，含写着本机绝对路径的 ffmpeg list）。

## 6. 本阶段修掉的缺陷

1. **`config/default.yaml` 里两条本机不存在的 keyfile 路径**：`health_check` / `lib/secrets.py` 每次都要对不存在
   的路径做一次探测，且把"本机专用"写进了仓库配置。删掉后 `python lib/secrets.py` 输出干净
   （autodl / deepseek / 火山 / uploadpost 全部 ✓），不再有 deprecation 警告。
2. **`lib/llm.py` 的第二套产品事实**：`generate_script()` 里另有一份硬编码品牌/卖点默认值，
   与 `config/default.yaml` 的 `product` 段可以悄悄漂移。改为 `_product_defaults()` 从 settings 取，**一处定义**。
3. **字幕高亮词把未核验口径当事实用**：原 `HIGHLIGHT_WORDS` 手写 12 词里含「医疗级/锂电/屋里充」，
   而 Claims Registry 里这三条仍是 `needs_verification`。改为从 registry 派生并剔除，**合规门与字幕口径对齐**。
4. **`tools/ci.py` 的 `compileall` 一直在说 "Can't list 's2_copy'"**：这两个目录随老管线归档后已不存在，
   每次门禁都在刷无意义噪音；真正的语法错误会被淹掉。改为只编译实际存在的目录。
5. **`tools/run_all.py` 名字仍是"唯一入口"的样子**：docstring 与运行行为都不说明它已降级，
   后来人容易继续往里加逻辑。改为显式 DEPRECATED + 运行时 stderr 提示。
6. **仓库里躺着写着本机绝对路径的临时产物**：`assets/cast/voice/_audition_tmp/list.txt` 内容是
   `D:/@kaifa/ayh-mj/...` 的 ffmpeg concat 清单。这是 `tools/make_voice_audition.py` 的一次性产物，
   已 untrack + gitignore（本地文件保留）。

## 7. 遗留与限制

1. **`config/default.yaml` 仍有 1 条本机绝对路径**（`paths.legacy_keyfiles` 里的
   `D:/BaiduSyncdisk/2 @AI编程/Api Key/爱优护api.txt`）。这是**有意保留**的：它当前就是本机凭据来源，
   删掉会让 health check 从 ✓ 变 △。文件里已用注释指明"换机器时改这里或设 `AYHMJ_KEYFILE`"。
   如果要求"仓库里零绝对路径"，需要把凭据迁到 keyring / 环境变量后再删（属运维动作，不是代码改动）。
2. **`tools/` 的 C 类一次性脚本（27 个）保留在原地**，没有移入 `tools/legacy/`。原因：移动会改变
   `tools/*.py` 相对仓库根的深度，破坏这些脚本里的 `ROOT = parents[1]` 与 `pyproject.toml` 的
   `per-file-ignores` 作用域，属于"清理"换来的新破损。改用 `tools/README.md` 分类 + 守卫测试
   锁定"它们不被主链引用"，同样达到收敛目的。
3. **`tools/check_xinao10.py` / `tools/check_xinao10_takes.py` / `tools/check_hellgrind.py` 会报错**
   （缺素材 / 报 7 项缺失）。这是**预期行为**：它们是当时某条片子的一次性校验脚本，输入文件早已随
   中间产物清理，已在 `tools/README.md` C 类里说明。
4. **`pipeline.yaml` 的名字仍出现在 5 处注释/docstring**（`lib/settings.py` ×2、`s1_trend/run.py`、
   `tests/contract/test_production_wiring.py`、`tests/unit/test_settings.py`）。这是**刻意保留的历史说明**：
   守卫测试用 AST 判定，注释/docstring 不算依赖；全部删掉会让"它已经删了"这件事失去文档痕迹。
5. **`publishes` 表仍留在库里（v1 遗留）**。Phase 10 起不再写入，但历史行不删（迁移原则：只增不删）。
   想彻底移除需要一次 v5 迁移 + 数据归档，属后续阶段。
6. **README 里的 `python -m uvicorn webui.server:app` 启动方式未在本阶段实测**（Phase 12 已实测
   Playwright 夹具以同一入口拉起控制台）。本阶段只验证 `health_check` → DEGRADED 与 `orchestrate` CLI 可用。
7. **Phase 11 遗留的六条限制全部沿用**（无官方只读采集通道、学习结论未回写线上策略、工程默认值待真实
   数据校准、Phase 6 的 5 条 `needs_verification`、`vision` 仍由 fixture 承载、
   `ai_disclosure_confirmable` 与 `domestic_draft_args` 待人工补齐）。
