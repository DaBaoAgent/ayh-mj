# Phase 1 验收记录 — 配置统一、依赖锁定、去硬编码

- 阶段：Phase 1
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 1
- commit：`phase-1: unify settings dependencies and capability discovery`

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 唯一配置源 | `config/default.yaml`（新） | 全仓唯一权威非敏感默认配置：product/paths/llm/generate/asr/trend/storyboard/compose/publish/engage/webui |
| 强类型配置 | `lib/settings.py`（新） | Pydantic 模型 + ROOT 自解析（`Path(__file__).parent.parent`）+ `AYHMJ_<SEC>__<KEY>` 环境覆盖 + `pathx.*` 路径属性 |
| 密钥统一 | `lib/secrets.py`（新） | 唯一入口：env → keyring → dotenv → 兼容 keyfile；`secret_source()` 只报来源不泄值；找不到返回空串由 health 层降级 |
| 兼容层 | `lib/keyfile.py` | 删除机器专属默认路径；支持显式 `path=`；默认路径改为动态解析（`$AYHMJ_KEYFILE` / `<root>/config/api_keys.txt` / `paths.legacy_keyfiles`） |
| 工具定位 | `lib/tools.py` | ffmpeg/ffprobe/yt-dlp 解析顺序：settings → 环境变量 → PATH → 候选目录；新增 `font_dir()` / `find_font()` |
| 能力探测 | `tools/health_check.py`（新） | capability matrix：READY/DEGRADED/BLOCKED + 修复建议；`--json` 供 WebUI 消费 |
| 部署入口 | `tools/bootstrap.py` | 体检逻辑委托 health_check，不再自己维护一份判断 |
| 去硬编码 | `lib/llm.py`、`s4_generate/autodl_client.py`、`s4_generate/ark_image.py`、`s5_compose/burn_subtitles.py`、`tools/audio_polish.py`、`tools/rename_approved.py`、`tools/sync_desktop.py`、`tools/check_hellgrind.py`、`tools/append_wide_tail.py`、`tools/make_voice_audition.py`、`tools/frames_card.py`、`tools/make_review_card.py`、`scripts/tr_medium.py` | 全部改走 settings / lib.tools；无 `D:/@kaifa`、`C:/Users/<用户>` 残留 |
| 配置收敛 | `config/pipeline.yaml` | 顶部加 DEPRECATED 横幅；加载时只兜底并打印 deprecation 警告；权威源唯一 |
| 发布链 | `s6_publish/publish.py` | `load_config()` 改读 settings；PostFlow 目录走 `settings.postflow_dir`；夜间静默/平台间隔/窗口全部配置驱动 |
| WebUI | `webui/server.py` | `/api/state` 增加 `health` 摘要；新增 `GET /api/system/health`；`/` 注入 `window.__AYHMJ_ROOT__` |
| WebUI | `webui/templates/index.html`、`webui/static/app.js` | Hermes 会话 `cwd` 由服务端注入，删除写死的 `D:/@kaifa/ayh-mj` |
| 依赖 | `pyproject.toml` / `requirements.txt` / `uv.lock` | 补齐真实 import（pydantic/Pillow/websockets…）；可选能力拆 extras（`asr`/`metrics`/`learn`/`dev`）；`uv.lock` 锁定 94 个包 |
| 依赖矛盾 | `.gitignore` + `vendor/README.md` | 明确方案：vendor 不随仓库分发（安装步骤 + `AYHMJ_POSTFLOW_DIR` 可配置路径），但保留 `vendor/README.md` |
| 文档 | `.env.example` | 只列变量名，不含真实 key |
| 测试 | `tests/unit/test_settings.py`、`test_secrets.py`、`test_health_check.py`、`test_no_hardcoded_paths.py` | 25 例新增回归（配置解析/覆盖/搬家、密钥优先级、能力矩阵、去硬编码守卫） |
| 证据 | `docs/codex/phase1_health_check.txt`、`docs/codex/phase1_verification.txt` | 体检输出、搬家测试、密钥来源、环境覆盖原始输出 |

## 2. 验收标准逐条对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 仓库复制到不同目录后，无需改源码即可通过基础 health check | ✅ | `docs/codex/phase1_verification.txt` §1：复制到 `%TEMP%` 后 `health_check.py` 退出码 0、`ROOT 跟随仓库=True`、`state/` 自动创建、0 阻塞 |
| 缺少某能力时给出 `DEGRADED` 与明确原因，而不是 import crash | ✅ | 本机 3 项降级：whisper（未装 faster-whisper）、douyin_profile（未扫码）、postflow（未安装）；每项都带"修复"提示；`test_health_check.py` 断言依赖损坏也不抛异常 |
| `pytest` 全绿，WebUI smoke 不退化 | ✅ | 见 §3 |
| 业务代码不再有固定 `D:/@kaifa/...`、`C:/Users/...` | ✅ | `test_no_hardcoded_paths.py` 守卫；`config/default.yaml` 的 legacy keyfile 为显式标注的可选兼容项 |
| API key 优先级统一为 env → keyring → dotenv → legacy keyfile | ✅ | `lib/secrets.py`；`test_secrets.py` 覆盖全部优先级与"找不到即空串" |
| 旧 `pipeline.yaml` 仅兼容、唯一权威源 | ✅ | 加载时打印 deprecation；`test_settings.py` 验证权威源优先 |
| health check 输出 ≥10 项能力 | ✅ | python/ffmpeg/font/whisper/autodl/deepseek/douyin_profile/postflow/upload_post/db/disk（11 项） |
| WebUI `/api/state` 增加 health summary（不重写 UI） | ✅ | `/api/state.health.status=DEGRADED`，新增只读 `/api/system/health` |

## 3. 测试结果

```text
$ .venv/Scripts/python.exe -m pytest -q
73 passed, 1 skipped in 3.13s        # 1 skipped = paid placeholder（默认门禁生效）

$ .venv/Scripts/python.exe -m pytest -q -m frontend
3 passed, 71 deselected in 2.63s     # Playwright chromium，真实起 uvicorn（--lifespan off）

$ .venv/Scripts/python.exe -m ruff check .
All checks passed!

$ uv lock --check
Resolved 94 packages
```

**AutoDL 付费任务提交数 = 0**（全量测试仅用 fake provider；`tools/health_check.py` 只做本地探测）。

## 4. 关键实现说明

1. **ROOT 自解析**：`lib/settings.py` 用 `Path(__file__).resolve().parent.parent`；可用 `AYHMJ_ROOT` 覆盖。
   所有相对路径 (`state/out/logs/assets/config`) 都相对它解析，因此仓库可任意搬迁。
2. **环境覆盖语法**：`AYHMJ_<SECTION>__<KEY>`，双下划线分层，值自动做 bool/int/float 强转。
   例：`AYHMJ_LLM__MODEL=deepseek-v4-pro`、`AYHMJ_PATHS__FFMPEG=D:\bin\ffmpeg.exe`。
3. **能力语义**：`BLOCKED` 只给"必需且缺失"（python/ffmpeg/db）；`DEGRADED` 给"可选缺失"。
   总状态 = 有阻塞则 BLOCKED，否则有降级则 DEGRADED，否则 READY。
4. **PostFlow 矛盾决策**：不引入 submodule（会让 fresh clone 变重且需额外凭据），
   采用"安装步骤 + 独立可配置路径"：默认 `<root>/vendor/postflow`，可用 `AYHMJ_POSTFLOW_DIR` 指向任意位置。
5. **lockfile**：`uv.lock` 以官方 PyPI 为准生成（94 包），`requirements.txt` 与
   `pyproject.toml [project.dependencies]` 保持一致；可选能力拆分 extras。

## 5. 遗留与限制

- `whisper` / `douyin_profile` / `postflow` 三项在本机仍为 `DEGRADED`，属环境能力缺失（非代码缺陷）：
  分别需要 `uv pip install -e ".[asr]"`、扫码登录、安装 PostFlow。
- `tools/check_hellgrind.py` 可正常 import 与运行，但因本机没有 Higgsfield 原文副本与 Hermes
  技能目录而报 7 项缺失 —— 这是"自检报告"的预期输出，非失败；Phase 14 会收敛该脚本。
- `config/default.yaml` 仍保留 `paths.legacy_keyfiles`（本机旧 key 文件路径），
  它**仅作可选兼容**：文件不存在即静默跳过，不是运行必需条件。Phase 14 视情况删除。
- 本阶段未接入 uv 的 CI 校验（Phase 13 负责 `lint → typecheck → unit → …` 门禁）。
