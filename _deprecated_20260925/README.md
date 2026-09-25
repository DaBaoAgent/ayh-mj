# 已弃用脚本归档（2026-09-25）

> 本目录内容**全部弃用**，保留仅为追溯参考。**请勿使用**。
> 现行标准见项目根 `docs/执行标准-20260925.md`。

## 内容

| 目录 | 原位置 | 内容 | 弃用原因 |
|---|---|---|---|
| `tools/` | `tools/` | run_all / prep_t11~t20_v2 / gen_cast系列 / gen_fashion系列 / gen_voice_cast系列 / gen_pixabay / gen_realistic_faces / gen_all_realistic / build_audit_tape_v2,v3 / test_*.py / probe_* / check_dual_voice / verify_voice_clone / voice_match / verify_take / compare_side_by_side / _add_roles / _append_web / _fix_t07 | 一次性脚本或已被新管线取代 |
| `s4_generate/` | `s4_generate/` | gen_from_storyboard.py（逐镜版）、batch_gen.py | 已被 one-take（gen_one_take.py）取代 |
| `s3_storyboard/` | `s3_storyboard/` | split.py、templates.py | 模板链路停用（宝哥令 2026-09-25：删掉模板） |
| `merge.py` / `subtitle.py` / `tts.py` | `s5_compose/` | 旧装配组件（镜头拼接+TTS+SRT） | 已被 one-take + burn_subtitles/audio_polish 取代 |
| `tools/check-dialogue.mjs` | `tools/` | 与 check_dialogue.mjs 完全重复 | 重复文件 |

## 现行替代

| 老 | 新 |
|---|---|
| run_all.py（模板全流程） | `tools/pick_combo.py` + `tools/prep_*.py` + `s4_generate/gen_one_take.py` |
| gen_from_storyboard.py（逐镜） | `s4_generate/gen_one_take.py`（单条多镜 one-take） |
| gen_cast*.py（角色图生成） | 资产已就绪：`assets/cast/library/` 95 张 |
| build_audit_tape_v2.py | `build_audit_tape_v3.py`（后移至本目录）→ 现用 `notes` 内听审流程 |
| merge/subtitle/tts.py | `s5_compose/burn_subtitles.py` + `tools/audio_polish.py` |
