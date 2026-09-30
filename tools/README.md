# tools/ 脚本清单（Phase 14 归档说明）

本目录**不是**主链入口的集合，而是"编排器 + 可复用服务 + 一次性人工工具"三种东西混放的
历史结果。Phase 14 把它们的身份钉死在这张表里，避免后来人误以为每个脚本都是产线的一环。

> 唯一生产入口是 `tools/orchestrate.py`。任何"绕过 Orchestrator 直接跑脚本出片"的用法都是
> 人工应急通道，不是产线。

## A. 主链与运维入口（唯一入口，长期维护）

| 脚本 | 作用 |
|---|---|
| `orchestrate.py` | **唯一生产编排入口**：`start / status / resume / retry / cancel / recover` |
| `ci.py` | 门禁：lint / typecheck / unit / contract / integration / frontend / migration 七步 |
| `health_check.py` | 能力体检：输出 READY / DEGRADED / BLOCKED 与每项的修复提示 |
| `bootstrap.py` | 换机三步就绪（venv + 依赖 + 体检）；体检逻辑已收敛到 `health_check.py` |
| `cleanup_project.py` | 中间产物清理（WebUI 的 `/api/action/cleanup` 调它） |

## B. 主链 stage 依赖的可复用脚本（由 Orchestrator 经子进程调用）

这些脚本保留成熟的工艺实现，但**编排、幂等、状态都归 Orchestrator**，脚本本身不承担系统编排。

| 脚本 | 作用 |
|---|---|
| `make_15s.py` | 15 秒 one-take 产线实现（预检 / 生成 / 转写 / 字幕 / BGM / 音效 / 归档） |
| `audio_polish.py` | 后期音频：人声链 + BGM + 音效。**选曲唯一入口是 `lib.post.audio_director.select_bgm`**，音效唯一入口是 `lib.post.sfx.plan_sfx` |
| `transcribe_local.py` | canonical transcript 服务（全链只做一次 ASR） |
| `lines_to_srt.py` | 消费 transcript artifact 生成字级 SRT（不再二次 ASR） |
| `trim_onetake.py` | 明快档裁剪（头尾 <=0.15s / 停顿 >=0.35s 压缩） |
| `frames_card.py` | 抽帧 / 审片卡 |
| `pick_combo.py` | 四池组合 CLI（逻辑已在 `lib/creative/`，脚本是薄壳） |
| `check_dialogue.mjs` | 台词门禁（Node）：字数 / 句长 / 禁用符号 |
| `check-take.mjs` | 被 `transcribe_local.py` 调用的逐字对齐校验 |
| `rename_approved.py` / `sync_desktop.py` | 归档命名与桌面同步，由 `make_15s.py` 调用 |

## C. 一次性 / 人工工具（不参与主链运行，保留作复现证据）

这些脚本是"当时做某一条片子/某一批素材时写的"，**没有生产代码引用**，也不进任何 stage。
保留它们是为了让历史结论可复现。它们坏掉（缺素材 / 缺本机路径）是**预期行为**，不算回归。

| 类别 | 脚本 |
|---|---|
| 历史成片 prep（某条片子的一次性 spec 组装） | `prep_g5_jingdian.py` `prep_h1_hero.py` `prep_s30_park.py` `prep_t20_v3.py` `prep_w1_magic.py` `prep_w3_lunyizu.py` `prep_xinao10.py` |
| 历史验收 / 对拍 | `check_xinao10.py` `check_xinao10_takes.py` `check_hellgrind.py` `check_collision.py` |
| 素材库建设期一次性工具 | `build_real_voice_library.py` `make_voice_sample.py` `make_voice_audition.py` `podcast_voice_harvest.py` `gen_cast_scene.py` `gen_sfx.py` `import_shotcraft_sfx.py` `ask_img.py` |
| 单条后期手工工具 | `concat_takes.py` `rescore_lines.py` `retime.mjs` `append_wide_tail.py` `make_review_card.py` `update_real_index.py` |
| 趋势抓取探针 | `fetch_trends_multi.py` `fetch_bridges.py` |
| 旧入口（已声明废弃） | `run_all.py`（运行时会打印 `[deprecated]` 并提示改用 `orchestrate.py`） |
| 旧预筛 CLI | `prescreen.py`（编排层的能力已上移到 `lib/creative/prescreen.py`，由 `plan` stage 调用） |
| 旧断点续跑 CLI | `resume_task.py`（由 `orchestrate.py resume` 取代） |

## D. 约定

1. 新脚本若要进主链，必须先在 `lib/` 里落一份可测逻辑，再由 Orchestrator 的 stage 调用；
   不要让 Orchestrator 直接依赖一个只有 `if __name__ == "__main__"` 的脚本。
2. C 类脚本不允许被 A/B 类 import。`tests/unit/test_legacy_fact_sources.py` 会检查这一点。
3. 一次性脚本不要写"本机绝对路径"当默认值；需要本机资源时走 `lib.settings` 或环境变量。
