# 现行流水线真实调用链（Phase 0 基线快照）

> 记录时间：2026-09-30 ｜ 基线 commit：`61349e8`（branch `codex/ayh-mj-vNext` 起点）
> 目的：在改动生产主链之前，先把"现在真正在跑什么"钉死成可核对的文档。
> 本文件描述**改造前**的事实；Phase 3 起会新增 `docs/architecture/vnext.md` 描述目标架构。

---

## 1. 入口与调用链总览

```text
浏览器 (webui/static/app.js + index.html)
   │  HTTP / WS
   ▼
webui/server.py  (FastAPI, 127.0.0.1:8899)
   ├─ GET  /api/state      ← state/run_status.json + lib.state.get_stats() + hermes_bridge 状态 + 机器资源
   ├─ POST /api/settings   ← state/console.json（schema 白名单校验）
   ├─ POST /api/start      → subprocess: tools/run_all.py [--dry] [--only ...]
   ├─ POST /api/stop       → taskkill 进程树（PID 取自 state/engine.pid）
   ├─ GET  /api/outputs    → 扫描 out/ 目录（字符串/文件名推断）
   └─ WS   /ws/hermes      → webui/hermes_bridge.py → hermes serve (tui_gateway JSON-RPC)

tools/run_all.py  （队列调度器）
   │  读 state/queue_15s/*.json
   ├─ 逐条 subprocess: tools/make_15s.py run <spec>
   └─ 写 state/run_status.json / state/run_progress.jsonl

tools/make_15s.py run   （真正的 one-take 产线 = 生成 + 后期 + 归档）
   ├─ ① 预检            assert_lines(字数/数字/句长) + prompt 长度 ≤ 9800
   ├─ ② 生成            s4_generate/gen_one_take.py <spec>
   │                       └─ s4_generate/autodl_client.py → AutoDL.Art H3
   ├─ ③ 转写            tools/transcribe_local.py        (faster-whisper **small**)
   ├─ ④ 一致性自检       转写 vs docs/onetake_lines_<uid>.txt（difflib 逐字一致率）
   ├─ ⑤ 字级字幕         tools/lines_to_srt.py           (faster-whisper **medium**，二次推理)
   │                       └─ s5_compose/burn_subtitles._split_natural 拆行
   ├─ ⑥ 烧字幕           s5_compose/burn_subtitles.py（新青年体 + 关键词高亮）
   ├─ ⑦ BGM              tools/audio_polish.py（按文件大小挑"最近未使用"）
   ├─ ⑧ 音效             make_15s._mix_sfx（固定第 4/5/7/8 句 + ding/whoosh/pop）
   ├─ ⑨ 抽帧验收卡        tools/frames_card.py（4 镜 × 2 帧 → 人工看图）
   └─ ⑩ 归档             out/approved/ + tools/rename_approved.py + tools/sync_desktop.py

发布（**另一条独立链路**，与上面不共享任务事实源）
s6_publish/publish.py --job <uid>
   ├─ 读 state/pipeline.db 的 jobs 表（要求 status='ready'）
   ├─ 国内：vendor/postflow CLI（douyin / xiaohongshu / tencent=视频号）
   ├─ 海外：s6_publish/uploadpost.py（REST）
   └─ 写 publishes 表 + state/publish_pacing.json（配额）
s6_publish/engage.py  评论区/私信分类回复（红旗词转人工）
```

---

## 2. 两套"事实源"（P0 问题 #1 / #2 的根源）

| 事实源 | 写入方 | 读取方 | 问题 |
|---|---|---|---|
| `state/pipeline.db` → `jobs` 表 | `lib/state.py`（旧模板链路） | `s6_publish`、`/api/stats`、`/api/jobs` | one-take 主链**从不写**它 |
| `state/queue_15s/*.json` + `state/run_status.json` | `run_all.py` / `make_15s.py` | `/api/state`、前端进度条 | 与 DB 无关联，删/重建即丢事实 |

结果：WebUI 展示的"任务数/阶段"来自 `run_status.json` 的**字符串**，而"待发布任务"来自 `jobs` 表，两者可以互相矛盾。
"六阶段"（trend/copy/storyboard/generate/compose/publish）是**前端写死的 id**，执行器（`run_all.py`）只写 `generate`/`compose` 两个字符串，其余阶段没有任何执行体 —— 即 P0 #1「UI 有能力、执行器无能力」。

## 3. 设置如何"贯穿"（P0 #3）

`state/console.json` 里的 `daily_target / gen_concurrency / real_publish / publish_platforms / real_engage`：
- `dry_mode`：**有**贯穿（`/api/start` 传 `--dry` 给 `run_all.py`）。
- `daily_target`：**无**执行体（`run_all.py` 只看队列文件条数）。
- `gen_concurrency`：**无**执行体（`run_all.py` 串行 for 循环）。
- `real_publish / publish_platforms / real_engage`：不在启动链路上，需要人工另跑 `s6_publish/publish.py --yes`。

## 4. 生成能力矩阵（`s4_generate/workflow_router.py`）

- `WORKFLOW_SPECS`：15 个工作流（多图/多图+音频/六图/首尾帧/文生），含 `duration` 区间、`audio`、`ref_images_max`、`tier`。
- `route()` 已能按 `n_images / has_audio / duration / first_last / prefer_hq` 给出优先级链。
- **但主链不调用它**：`gen_one_take.py` 使用 spec 里人工写死的 `workflow` + `fallback_workflows`（P0 #7）。
- `make_15s.py` 造脚本时把 workflow 固定为 `minimax_h3_image_audio_to_video_v2_15s`，`fallback_workflows` 为空。

## 5. 结构多样性（P0 #8）

`make_15s.py new` 只有一种骨架：**4 镜 × 2 句 = 8 句**、双人对撞、时长硬编码 `0-4 / 4-8 / 8-11 / 11-14.5`。
`lib/genres.py` 有 10 种片型、`lib/angles.py` 有 50 条思路、`lib/products.py` 有 20 个卖点，但 `make_15s.py new` 只把它们当作**文字素材**，不改变镜头结构。

## 6. 后期重复计算（P1）

同一段视频被转写两次：`transcribe_local.py`（small，用于一致性自检）与 `lines_to_srt.py`（medium，用于字级对齐）。两次推理、两套时间轴。

## 7. 硬编码与本机专属路径（P1，Phase 1 处理清单）

| 文件 | 硬编码 |
|---|---|
| `lib/keyfile.py` | `D:/BaiduSyncdisk/2 @AI编程/Api Key/爱优护api.txt` |
| `s4_generate/autodl_client.py` | 3 个已知 `.env` 绝对路径 |
| `s4_generate/ark_image.py` | `D:/@kaifa/ayh-mj/state/ark.env` |
| `lib/tools.py` | `D:/@kaifa/tools/ffmpeg/bin`、`C:/Users/xxx13/...` |
| `s5_compose/burn_subtitles.py` | `C:/Users/xxx13/.../Python312/python.exe`、`D:/@kaifa/fonts-douyin` |
| `s6_publish/publish.py`、`tools/bootstrap.py` | `D:/@kaifa/ayh-mj/vendor/postflow` |
| `tools/rename_approved.py`、`tools/sync_desktop.py` | `C:/Users/xxx13/Desktop/ayh-mj` |
| `tools/audio_polish.py` | `D:/BaiduSyncdisk/3 艾伦和艾薇/免费音乐` |

## 8. 环境隐患（Phase 0 实测）

- 机器 `PYTHONPATH` 指向 `D:\@佳康顺矩阵\hermes`，其中存在一个**同名 `tools` 包**，会遮蔽本仓库的 `tools/`。Phase 0 通过给 `tools/` 加 `__init__.py` 让其成为常规包并优先命中，同时记录为环境风险。
- `vendor/` 被 `.gitignore` 忽略，但 `bootstrap.py`/`publish.py` 假设它"随仓库存在"（Phase 1 决策）。
