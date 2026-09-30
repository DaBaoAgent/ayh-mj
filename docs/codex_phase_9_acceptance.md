# Phase 9 验收记录 — 后期链统一：ASR、字幕、BGM、SFX、节奏

- 阶段：Phase 9
- 日期：2026-09-30
- 分支：`codex/ayh-mj-vNext`
- 计划依据：`ayh-mj_Codex完整迭代开发与验收计划_2026-09-30.md` §Phase 9
- commit：`phase-9: unify post production and make audio story aware`
- 原始证据：
  - `docs/codex/phase9_canonical_transcript.txt`（同一份 canonical transcript 的产生 / 复用 / 失效重推 / 时间对齐）
  - `docs/codex/phase9_trim_validation.txt`（`trim_onetake` 正常路径：段数 / 时长 / 音视频流校验）
  - `docs/codex/phase9_trim_failure_paths.txt`（裁剪失败必须显式报错，不得静默跳过）
  - `docs/codex/phase9_loudness.txt`（AudioDirector 选曲 + SFX 放置 + 母线统一响度闭环）
  - `docs/codex/phase9_genre_matrix.txt`（37 首真曲库 × 10 片型：选曲 / SFX 策略差异）
  - `docs/codex/phase9_bgm_metadata.txt`（BGM 元数据覆盖情况）
  - `docs/codex/phase9_verification.txt`（ruff / 定向 pytest / 全量 pytest / 前端 smoke）

---

## 1. 本阶段改了什么

| 类别 | 文件 | 说明 |
|---|---|---|
| 转写统一（新） | `lib/post/transcript.py`（390 行） | `CanonicalTranscript`（`fingerprint` / `matches_source`）+ `ensure()`（**一次高质量 ASR**，落 `transcripts/canonical.json`，源变更才失效重推）+ `align_spans()` / `rows_from_spans()` / `build_rows()`（字幕时间**只来自这一份**）+ `write_srt()` + `split_line()`（自然断句 / 每行字数上限） |
| 音频导演（新） | `lib/post/audio_director.py`（227 行） | `BGM_META_FIELDS`（9 字段 `bpm/energy/mood/intro_strength/drop_time/genre/vocal/comedic/emotional`）、`GENRE_BGM_PROFILE`（片型先验）、`infer_metadata()`、`load_library()`、`score_track()`、`select_bgm()`（**mood_curve/beat_map 主导** + 片型先验 + recent 防重复）、`pick_bgm()` |
| 音效（新） | `lib/post/sfx.py`（188 行） | `GENRE_SFX_POLICY`（片型密度/上限）、`plan_sfx()`（按**动作 / 反转 / punchline / 品牌 beat** 触发，替代固定第 4/5/7/8 句模板）、`asset_peak_db()` / `asset_gain_db()`（**按实测峰值定标**）、`SFX_BED_PEAK=-12.0`、`resolve_files()` |
| 响度（新） | `lib/post/loudness.py`（166 行） | 统一阈值单一来源：`LOUDNESS_BAND=(-17,-9)` / `TRUE_PEAK_MAX=-1.0` / `LOUDNESS_TARGET=-16` / `LOUDNESS_TP=-1.5`；`limiter_filter()`（**由 TP 同源换算**的 alimiter limit）、`master_gain()`（由实测响度算**静态**增益）、`master_for_mix()`（渲染完整滤波图 → ebur128 实测 → 返回母线串）、`measure()` / `issues()` / `summarize()` |
| 后期门面（新） | `lib/post/__init__.py`（86 行） | 导出上述能力 + `story_audio_brief(spec_doc)`（把一份 spec 拆成 `mood_curve/beat_map/genre/lines` 给后期用） |
| 故事结构 | `lib/creative/storiespec.py`（+74） | 新增 `BEAT_BASE` / `_genre_profile()` / `_tone()` / `build_beat_map()`；`StorySpec` 新增 `mood_curve` / `beat_map` 并进 `to_dict()` |
| QA 阈值同源 | `lib/qa/checks.py` | 响度阈值改为从 `..post.loudness` **import**（不再本地复制一份） |
| QA 取证 | `lib/qa/critic.py` | `_probe_video(measure_audio=)`；`TRANSCRIPT_FILENAME` 指向 `transcripts/canonical.json`（字幕类证据读同一事实源） |
| 字幕烧制 | `s5_compose/burn_subtitles.py` | 字号 / 安全区 / 每行字数**走 settings**（配置化，去硬编码） |
| 转写 CLI | `tools/transcribe_local.py` | 收敛为 canonical transcript service（不再 small+medium 两次推理） |
| 字幕 CLI | `tools/lines_to_srt.py` | 消费 canonical transcript artifact，不再自行 ASR |
| 后期 CLI | `tools/audio_polish.py` | 由 AudioDirector 选曲 + `master_for_mix` 统一母线（去随机 / 文件大小选曲） |
| 15s 组装 | `tools/make_15s.py` | `_mix_sfx` 与 audio_polish **共用同一条母线**；SFX 走 `plan_sfx` |
| 裁剪 | `tools/trim_onetake.py` | 增加 **segment count / 输出总时长 / 音视频流完整性** 校验；失败显式返回 `ok=False + errors` |
| 素材 | `assets/bgm_trending/_metadata.json` | 36/37 首人工整理元数据（其余走推断，见 §6） |
| 测试（新） | 6 个测试文件 | 见 §5（44 条） |
| 测试（改） | `tests/unit/test_orchestrator.py` | 集成用例补一个轻量假 `package` 阶段（见 §6 缺陷 1） |

## 2. 必做任务逐条对照

| # | 任务 | 结果 | 证据 |
|---|---|---|---|
| 1 | ASR 每条视频只做一次 word timestamp 转写，保存 artifact 并被后续复用 | ✅ | `lib/post/transcript.py::ensure()` → `transcripts/canonical.json`；`phase9_canonical_transcript.txt` 首次 ASR 1 次 |
| 2 | 移除 `small` 一次 + `medium` 再一次的重复推理 | ✅ | 再 ensure `reuse=True`、ASR 调用仍 1 次；`tools/{transcribe_local,lines_to_srt}.py` 全部改为走 canonical |
| 3 | 字幕保留台词校正 / 孤行合并 / 自然断句 / 关键词高亮，字体与安全区配置化 | ✅ | `burn_subtitles.py` 字号 / 安全区 / 每行字数走 settings；`transcript.split_line()` 自然断句 |
| 4 | 所有字幕时间来自同一 transcript artifact | ✅ | `align_spans` / `build_rows` 同源；`phase9_canonical_transcript.txt`：`align_spans[0][0]==build_rows[0][0]==0.5` |
| 5 | `trim_onetake` 增加段数 / 总时长 / 音视频流校验；局部 ffmpeg 失败不得静默跳过 | ✅ | `phase9_trim_validation.txt`（正常）+ `phase9_trim_failure_paths.txt`（失败显式报错） |
| 6 | BGM 建立 9 字段 metadata | ✅ | `BGM_META_FIELDS`；`_metadata.json` 36/37；`phase9_bgm_metadata.txt` |
| 7 | StorySpec 输出 `mood_curve/beat_map`，AudioDirector 据此选曲，不靠文件大小 / random | ✅ | `storiespec.build_beat_map()`；`select_bgm()` 以 mood_curve 主导；`phase9_genre_matrix.txt` 10 片型全不同 |
| 8 | 保留"最近未使用"防重复，但不是唯一逻辑 | ✅ | `select_bgm(recent=...)` 仅作惩罚项，主分来自 mood/energy/片型；`test_audio_director.py` 覆盖 |
| 9 | SFX 从动作 / 反转 / punchline / 品牌 beat 动态放置，移除固定第 4/5/7/8 句模板 | ✅ | `plan_sfx()` + `_triggers()`；`phase9_loudness.txt` G3 → 3 个不同触发 |
| 10 | 不同 genre 允许不同后期（Vlog 更自然 / 魔性广告高密度 / 情感片不硬塞音效） | ✅ | `GENRE_SFX_POLICY`；G5(emotional) → 0 个；G3(comedic) → high/max5；`phase9_genre_matrix.txt` |
| 11 | 输出统一 Loudness/Peak 检测，避免过爆或人声被压住 | ✅ | `loudness.measure/issues/summarize` + `master_for_mix`；`phase9_loudness.txt` 闭环 −26.1 → −16.4 LUFS / −1.3 dBTP |

## 3. 验收标准逐条对照（计划原文 4 条）

| # | 验收标准 | 结果 | 证据 |
|---|---|---|---|
| 1 | 一条视频只产生一个 canonical transcript | ✅ | `phase9_canonical_transcript.txt`：首次 / 复用 / 源变更三种情况下产物恒为 `['canonical.json']`，`仍然只有一份 canonical：True` |
| 2 | 同一 StorySpec 重跑后期不触发视频重新生成 | ✅ | `tests/integration/test_post_pipeline.py::test_post_chain_produces_one_canonical_and_no_regeneration`（重跑后期 generate 调用数不增） |
| 3 | 至少 5 种 genre 的 BGM/SFX 选择策略明显不同 | ✅ | `phase9_genre_matrix.txt` **10 种片型全不同**；`test_audio_director.py::test_at_least_five_genres_pick_different_strategies` / `test_sfx_placement.py::test_at_least_five_genres_have_distinct_sfx_policies` |
| 4 | 无字幕越界、孤字、明显重叠，语音期间 BGM 可懂度合格 | ✅ | `transcript.split_line()`（每行 ≤ max_chars，避免孤行）+ `build_rows()`（不重叠）；QA `checks.py` 的 `SUB_MAX_CHARS_PER_LINE` / `SUB_OVERLAP_TOLERANCE` 与 `LOUDNESS_BAND` 同源；`phase9_loudness.txt` 母线把整体响度落回带内、真峰值 −1.3 dBTP（BGM 不压人声） |

## 4. 关键实测数据

**canonical transcript 唯一性**（`phase9_canonical_transcript.txt`）：

```text
[1] 首次转写：ASR 调用 1 次 | 产物 ['canonical.json'] | fingerprint 972e552717fd0ea6
[2] 再次 ensure：ASR 调用 1 次（不重推） | reuse=True
[3] 字幕时间来自同一 transcript：align_spans[0][0]=0.5 build_rows[0][0]=0.5 （同一事实源：True）
[4] 源视频变化后：ASR 调用 2 次（失效重推） | 仍然只有一份 canonical：True
```

**trim 校验**（`phase9_trim_validation.txt` / `phase9_trim_failure_paths.txt`）：

```text
total=4.20s silences=[(1.02, 2.21)] cuts=1 keep=2
TRIM ok=True parts 2/2 dur 3.277 vs 3.216 streams 1 1 errors=[]
反例 1（保留段为空）   : ok=False errors=["保留段为空，无可裁剪"]
反例 2（时长不符，容差0）: ok=False errors=["输出时长 0.22s 与保留时长 0.20s 偏差超过 0.00s"]
```

**片型矩阵**（`phase9_genre_matrix.txt`，37 首真曲库 × 10 片型，全部不同）：

| genre | mood_curve | BGM 选曲 | SFX policy |
|---|---|---|---|
| G1 | upbeat,upbeat,neutral,neutral | 舞会吉他阳光.mp3 | low(max1) |
| G2 | epic,epic,upbeat,upbeat | 欢喜欢快喜庆.mp3 | high(max4) |
| G3 | upbeat,upbeat,comedic,comedic | 搞笑滑稽搞怪.mp3 | high(max5) |
| G4 | upbeat,upbeat,comedic,comedic | 三只小猪.mp3 | medium(max3) |
| G5 | emotional ×4 | 第一缕阳光.mp3 | **none(max0)** |
| G6 | neutral ×4 | Try - Andre Juss.mp3 | low(max1) |
| G7 | calm ×4 | 轻快悠闲.mp3 | low(max1) |
| G8 | comedic ×4 | 搞笑滑稽沙雕.mp3 | high(max4) |
| G9 | epic ×4 | 无人扶我青云志.mp3 | medium(max2) |
| G10 | epic,epic,upbeat,upbeat | 舞会吉他阳光.mp3 | medium(max2) |

**母线统一响度闭环**（`phase9_loudness.txt`，真 ffmpeg）：

```text
🎵 AudioDirector 选曲：喜剧幽默搞笑古风.mp3（mood=comedic energy=0.82 genre=G3 score=7.825）
  bgm: 喜剧幽默搞笑古风.mp3 | sfx: ['whoosh.mp3', 'whoosh.mp3', 'pop.mp3']
  母线实测：-26.1 LUFS / 20.0 LU / -8.8 dBTP → volume=10.1dB,alimiter=limit=0.8414:level=0
  统一响度检测：-16.4 LUFS / 20.0 LU / -1.3 dBTP ✓
```

（未过母线时真峰值 −0.4 dBTP、响度 −26.1 LUFS 均在带外；`master_for_mix` 实测后给出静态增益 +10.1 dB，**限幅在前、增益是静态的**，落盘 −1.3 dBTP / −16.4 LUFS，QA 与后期同源同结论。）

**BGM 元数据**（`phase9_bgm_metadata.txt`）：`curated: 36 | 未在库中的键: []`；仅 `Try - Andre Juss.mp3` 走推断。

## 5. 测试结果

**命令（全部实测，见 `docs/codex/phase9_verification.txt`）：**

```text
$ python -m ruff check lib tests tools webui
All checks passed!

$ python -m pytest tests/unit/test_post_transcript.py tests/unit/test_audio_director.py \
        tests/unit/test_sfx_placement.py tests/unit/test_trim_validation.py \
        tests/unit/test_loudness_master.py tests/integration/test_post_pipeline.py -q
44 passed in 0.77s

$ python -m pytest -q          # 全量（含 tests/frontend）
445 passed, 1 skipped, 1 warning in 297.87s (0:04:57)

$ python -m pytest tests/frontend -q
3 passed in 2.74s
```

**数值对照（Phase 8 → Phase 9）：**

| 指标 | Phase 8 | Phase 9 | 变化 |
|---|---|---|---|
| pytest 全量 | 401 passed + 1 skipped | **445 passed + 1 skipped** | +44 |
| 前端 smoke | 3 passed | 3 passed | — |
| ruff | All checks passed! | All checks passed! | — |

**本阶段新增测试清单（44 条）：**

| 文件 | 条数 | 覆盖 |
|---|---|---|
| `tests/unit/test_post_transcript.py` | 7 | 一次 ASR / 复用不重推 / 源变更失效 / 只有一份 canonical / 词级对齐 / 长行分句不重叠 / 损坏文件返回 None / 旧 segments 升级 |
| `tests/unit/test_audio_director.py` | 9 | 9 字段齐全 / 推断确定性且与文件大小无关 / sidecar 覆盖推断 / 选曲确定性 / mood_curve 主导而非文件大小 / recent 只是惩罚项 / ≥5 片型策略不同 / 空库返回 None / `pick_bgm` 真目录返回路径 |
| `tests/unit/test_sfx_placement.py` | 9 | 四类触发 / 位置随内容而非固定句序 / 情感片 0 音效 / 魔性广告密度 > Vlog / ≥5 片型策略不同 / 上限与优先级且不叠加 / beat_map 标注 / 未知片型默认 / 缺素材跳过 |
| `tests/unit/test_trim_validation.py` | 7 | 正常通过 / 失败段不得静默丢弃 / 缺音轨拒绝 / 时长不符拒绝 / 空保留段拒绝 / 校验失败 `main` 非零退出 / 成功路径 |
| `tests/unit/test_loudness_master.py` | 9 | 阈值单一来源 / QA 与后期同源 import / 限幅由 TP 同源换算而非硬编码 / 增益打到目标 / 量不到不增益（有护栏）/ `in_band` 与 `issues` 一致 / 未实测不下结论 / `master_for_mix` 失败回退不抛 / SFX bed 增益按实测非硬编码 |
| `tests/integration/test_post_pipeline.py` | 3 | 一条 canonical + 重跑后期不重生视频 / 字幕与 SFX 共用 StorySpec+transcript / 真曲库元数据大部分人工整理 |

> `tests/integration/test_post_pipeline.py` 走**真实** `lib/post/*`（真读真曲库、真 `align_spans`）、只有生成层用 fake；autouse fixture 让 `s4_generate.autodl_client.create_task` 直接抛错，确保自动测试 **0 次 AutoDL 提交**。

## 6. 本阶段修掉的既有缺陷

1. **集成测试卡在 `COMPOSING`**：假 compose 不走状态机 → job 停在 `COMPOSING`，`service.start()` 的"READY/DONE/CANCELLED 才跳过"没命中 → 再 start 触发 `不能倒退：COMPOSING → GENERATING`。修法：测试里加一个轻量假 `package` 阶段（`stages=[..., "package"]`），job 走到 `READY` 终态；并断言 `store.get_job(UID)["status"] == JobState.READY`、`again["skipped"]` 含 UID。**没有改 service 的跳过逻辑**（避免跨阶段风险）。
2. **响度口径自相矛盾（核心修复）**：原 `MIX_MASTER = loudnorm + alimiter` 单遍动态 loudnorm 实测落在 **−17.5 LUFS**，低于自家 `LOUDNESS_BAND=(-17,-9)` 下沿 → 自己的成片被自己的 QA 判不合格；再叠加限幅后甚至掉到 −22.9。探明 **loudnorm 自报 `output_i`（动态模式 −16.00）与 ebur128+alimiter 对落盘素材的实测（−22.9）能差 ~6 dB**（动态窗口 + 前瞻），"按它报的数归一"完全不可信。最终设计（已验证 ✓）：`lib/post/loudness.py` 新增 `limiter_filter()`（`limit` 由 `LOUDNESS_TP=-1.5` 换算 = 0.8414，**同源**，废除拍脑袋的 0.95）、`master_gain()`（由实测响度算**静态**增益，只做荒谬值防护 `max_boost=18 / max_cut=24`，峰值顶棚交给同源 alimiter）、`master_for_mix()`（渲染**完整**滤波图 → ebur128 实测 → 返回母线过滤串）。母线 = `volume=g,alimiter(同源)`，**限幅在前、增益是静态的**；`tools/audio_polish.py` 与 `tools/make_15s.py::_mix_sfx` 共用这一条。
   - 踩过的坑 A：`master_for_mix` 一开始只传了末尾 `…amix=…[prem]` 片段（缺 `[s1]…[v0]…[bgd]` 标签定义）→ ffmpeg 在只剩输入 0 的图上产出**另一条信号**（实测 −26.1 LUFS vs 真实 −24.4）→ 算出的增益错。**必须传整条 filter_complex**（`";".join(fc + [mix])`）。
   - 踩过的坑 B：`master_for_mix` 的 `mix_argv` 必须是**完整 argv（含 ffmpeg 可执行文件本身）**，否则输出文件被当成 ffmpeg 自身路径（报 `Unable to choose an output format for '...ffmpeg.EXE'`）。
3. **SFX bed 电平拍脑袋**：原 `_GAIN_DB = {ding:20, whoosh:26, pop:24}`，而 whoosh/pop 素材只有 **−24 dBTP** → +26 dB 抬过头 → 混音峰值全由音效支配 → 母线不得不大幅压低整片。修法：`lib/post/sfx.py` 新增 `SFX_BED_PEAK=-12.0`、`asset_peak_db(path)`（按 size/mtime 缓存）、`asset_gain_db(path)`（按**实测峰值**定标，实测 ding=−25.4→+13、whoosh=−24.7→+13、pop=−23.7→+12、beep=−4.1→−8）；`resolve_files()` 现返回 `replace(hit, gain_db=gain)`；`_GAIN_DB` 只作量不到时的兜底（改为 13/13/12/13）。
4. **`test_cancel_is_cooperative_and_leaves_no_orphan` 竞态**（全量跑偶发 `IndexError: list index out of range`）：`captured.append(ctx)` 在 `run_subprocess` **之前**执行 → 轮询到 `captured` 时 `spawned` 可能还空。修法：循环条件改为等到 `captured[0].spawned` 也非空，并加 `assert captured[0].spawned`。**未改任何生产逻辑**，修复后连续两轮全量 442/445 全绿。

## 7. 遗留与限制（交给后续 Phase）

- **`bpm / intro_strength / drop_time` 是工程推断值，不是真实声学分析**：`assets/bgm_trending/_metadata.json` 的 `_note` 已明确声明。它们用于**相对**打分（选曲/防重复），不用于任何对外声明；若后续要做真实节拍/落点分析，替换 `audio_director.infer_metadata()` 一处即可，选曲调用方无需改动。
- **响度阈值来自 Phase 8 的工程默认**：计划未给具体数值，`LOUDNESS_BAND=(-17,-9)` / `TRUE_PEAK_MAX=-1.0` 沿用 P8 默认；本阶段把它们收敛到 `lib/post/loudness.py` **单一来源**，`lib/qa/checks.py` 改为 import 同一份（改一处即全链生效）。
- **画面类证据仍由 fixture 承载**：`vision` 段（产品形变/解剖/说话人/钩子时间）本阶段未接入真实多模态，仍由 `qa_evidence_<uid>.json` 承载；`lib/qa/critic.py::gather_evidence()` 已留同一 schema 插口。**响度这一维度本阶段已改为真实检测，不再靠 fixture。**
- **SFX 素材是占位资产**：`ding/whoosh/pop/beep_device` 为现有素材；`asset_gain_db()` 按实测峰值定标，替换素材后自动重新标定，无需改代码。
- **Phase 6 遗留的 5 条 `needs_verification` 口径仍未解决**（`shock_18` / `range_39` / `lithium_safe` / `cert_medical_device` / `patent_27`），需人工补证——见 `docs/codex_phase_6_acceptance.md` §4。
