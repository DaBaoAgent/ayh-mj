# ayh-mj — 轻便侠 · AI 视频工厂

**电动轮椅软广短视频全自动生产**：「单条多镜」one-take 工艺 —— 一次 H3 调用生成整条 15 秒（含全部镜头切换 + 双音色对口型），后期烧字幕 / BGM / 音效，直接出抖音爆款成片。

> 🎯 **执行标准（唯一真相源）**：**[`docs/执行标准-20260925.md`](docs/执行标准-20260925.md)** —— 一切出片以此为准。
> 速查口诀：**四池选角 → 六段式提示词 → 明快档 → 新青年体无标点不加粗 → 抖音BGM按剧情**

---

## 一分钟看懂

| 维度 | 现行方案 |
|---|---|
| 工艺 | one-take：`minimax_h3_image_audio_to_video_v2_15s` 一次生成整条（4 镜） |
| 组合 | **四池智能组合**：角色 100 人（5组×20）× 卖点 20 × 角度 50 × 片型 10，保新优先 |
| 提示词 | **官方 Ref2VA 六段式**（`subject_definitions`→`retention_analysis`→`detailed_description`…，音色绑定显式声明） |
| 台词 | 68-75 汉字（15s）· 每镜 2-3 句 · 禁破折号 |
| 节奏 | 明快档（头尾 ≤0.15s、停顿 ≥0.35s→0.20s 自动压缩） |
| 字幕 | **新青年体 · 不加粗 · 无标点** · 关键词黄字高亮 + 弹跳 |
| BGM | 36 首抖音热门库（`assets/bgm_trending/`）**按剧情逐条分配·零重复** + 音效层 |
| 成本 | ≈ **¥1.0 / 条**（H3 ¥0.9 + 校验/杂项） |

## 出片 7 步（现行流水线）

```bash
cd D:/@kaifa/ayh-mj && PY=.venv/Scripts/python.exe

# 1) 组合选择（四池）
$PY tools/pick_combo.py --commit T99

# 2) 写 spec —— 参照最新样板 tools/prep_w1_magic.py（官方六段式）
#    或批量：tools/brain2_data.py（数据）→ tools/prep_brain2.py（组装）

# 3) 校验（必须 0 ERROR）
node tools/check_dialogue.mjs docs/onetake_check_*.txt

# 4) 生成（提交→轮询→下载，约 15-20 分钟/条）
$PY s4_generate/gen_one_take.py state/onetake_prompt_job_*.json

# 5) 验收（转写 / 抽帧 / pitch）
$PY tools/transcribe_local.py out/gen_job_*/onetake.mp4

# 6) 后期（明快档→字幕→BGM+音效）
$PY tools/trim_onetake.py out/gen_job_*/onetake.mp4 --apply
$PY s5_compose/burn_subtitles.py <trim.mp4> --srt <srt> --suffix _fx
$PY tools/audio_polish.py <fx.mp4> --bgm "assets/bgm_trending/xx.mp3" --sfx --transcripts <json>

# 7) 归档 out/approved/

# —— 批量出片（10 条一次）——
$PY tools/run_batch_brain2.py --submit   # 10 任务并行排队提交
$PY tools/run_batch_brain2.py --collect  # 轮询下载
$PY tools/post_batch_brain2.py           # 批量后期
```

## 核心资产

| 资产 | 路径 | 规模 |
|---|---|---|
| 角色图 | `assets/cast/library/` + `roles.yaml` | 95 张照片级 / 100 人（城市20+欧美5+时尚组…） |
| 音色库 | `assets/cast/voice/real/` + `docs/音色-角色映射表-20260925.md` | 42 个真人样本 |
| 产品图 | `assets/products/{折叠,正侧-3,45度-加水杯}-无阴影.png` | 三视图（展开态必给三张） |
| BGM 库 | `assets/bgm_trending/` + `INDEX.md` | 36 首抖音热门 |
| 音效 | `assets/sfx/{ding,whoosh,pop}.mp3` | 3 种自动插入 |
| 字体 | `D:/@kaifa/fonts-douyin/` | 抖音全套 10+ 款（新青年体等） |
| 四池数据 | `lib/{products,angles,genres}.py` | 20 卖点 / 50 角度 / 10 片型 |

## 目录结构（现行）

```
ayh-mj/
├── docs/
│   ├── 执行标准-20260925.md      # ★ 唯一真相源
│   ├── 音色-角色映射表-20260925.md
│   └── script-*/  bgm分配-*/  onetake_check_*
├── lib/                  # products(卖点20) / angles(角度50) / genres(片型10) / cast / keyfile
├── s4_generate/          # autodl_client / gen_one_take(★核心) / workflow_router / ark_image
├── s5_compose/           # burn_subtitles(字幕) 
├── s6_publish/           # 发布（dabao 体系在用）
├── tools/                # 26 个现行脚本（见执行标准第三节）
├── assets/               # cast(library95/voice42) / products / bgm_trending / sfx / templates
├── state/                # 运行状态（不进 git）
├── out/                  # 成片输出（不进 git）
│   └── approved/         #   已验收成片
├── _deprecated_20260925/ # ⛔ 老管线（模板链路/历史脚本），勿用
└── webui/                # FastAPI 控制台 8899
```

## 控制台运维规则（重要）

- 控制台以 uvicorn `--reload` 运行：改 `webui/` 下 Python 代码**保存即生效**，前端改完刷新即可
- ⛔ 禁止 `taskkill` 杀 `server.py`（=自断 Hermes 命令通道）；重启用 `POST http://127.0.0.1:8899/api/restart`
- `start_console.bat` 为守护模式（退出 5 秒自动拉起）

## 凭据

三平台 key 统一在 `D:/BaiduSyncdisk/2 @AI编程/Api Key/爱优护api.txt`（autodl/火山方舟/deepseek 中文标签段），`lib/keyfile.py` 解析，**该文件为权威源**。

## 成本参考

| 项 | 单价 |
|---|---|
| H3 出片 768p | ¥0.06/秒（15s ≈ ¥0.9/条） |
| 快测 480p | ¥0.04/秒（5s ≈ ¥0.2） |
| 角色图/音色（建库期） | Seedream ≈¥0.3/张（已完成，95图/42音色入库） |
| **单条成片合计** | **约 ¥1.0** |

## 测试与 CI 门禁（Phase 13）

一条命令跑完所有**非 live / 非 paid** 测试（不需要网络、不花钱）：

```bash
.venv/Scripts/python.exe tools/ci.py          # Windows
python tools/ci.py                            # 任意平台
```

按固定顺序执行，任一步失败立即停手：

| 顺序 | 步骤 | 内容 |
|---|---|---|
| 1 | `lint` | `ruff check lib tests tools webui s6_publish s7_learn` |
| 2 | `typecheck` | `compileall`（本仓没有 mypy，用"能不能编译"当语法闸门） |
| 3 | `unit` | 纯逻辑单测（状态机 / settings / claims / router / 创意评分 / 修复策略 / 发布配额）。跑完顺带做 marker 分类纪律检查：`tests/unit` 每条用例必须带 `unit` marker，忘打即红灯 |
| 4 | `contract` | 第三方响应契约 fixture（DeepSeek / AutoDL / Upload-Post / PostFlow） |
| 5 | `integration` | fake provider 驱动的多模块流程（含 Planner 到 READY 的完整主链） |
| 6 | `frontend` | Playwright WebUI 冒烟（无浏览器环境可加 `--skip-frontend`） |
| 7 | `migration` | 数据库迁移测试 |

测试层级：

- `unit` / `contract` / `integration` / `frontend` 默认全部执行
- `live`（要真实网络或账号）与 `paid`（真花钱）**默认永不执行**，必须显式
  `AYHMJ_RUN_LIVE=1` / `AYHMJ_RUN_PAID=1` 才放行。CI 与 `tools/ci.py` 里这两个变量被强制清空
- 自动测试对 AutoDL 的付费提交有硬约束：任何一次真实提交都会直接 AssertionError

单独跑某一层：

```bash
.venv/Scripts/python.exe -m pytest tests/unit -q
.venv/Scripts/python.exe -m pytest tests/contract -q
.venv/Scripts/python.exe -m pytest tests/integration -q
.venv/Scripts/python.exe -m pytest tests/frontend -q
```

契约 fixture 在 `tests/fixtures/contracts/`：`ok/` 是真实形状样本，`broken/` 是反例。
任意一份被改坏（字段缺失、类型漂移、取值越界），`tests/contract` 会**点名到字段**地失败，
这就是"第三方字段变化时尽早报警"的机制。生产解析路径上装了同一道闸
（`lib/contracts.assert_contract`），见 `tests/contract/test_production_wiring.py`。

Golden 样本在 `tests/golden/creative/`：只冻结**输入**（稳定 StorySpec / CreativeDNA），
断言编译后仍满足关键结构与 hard constraints，不比较自然语言全文。

CI 配置见 `.github/workflows/ci.yml`，PR 未全绿禁止合并。

## 历史

- 2026-09-23：四池体系定型（角色100/卖点20/角度50/片型10），模板链路停用
- 2026-09-24：one-take 工艺首条 T06（后备箱魔术）
- 2026-09-25：真人音色库 42 样本 / 照片级角色图 95 张 / BGM 库 36 首 / 官方 Ref2VA 规范 / 字幕新青年体三条规范 → **执行标准定稿 + 老管线清退**

## License

MIT
