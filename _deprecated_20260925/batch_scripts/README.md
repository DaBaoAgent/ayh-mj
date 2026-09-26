# 一次性批次脚本（2026-09-26 清退）

这些脚本服务于**已交付完成的批次**（B2 脑洞10连 / D2 短剧10连 / W2 / W4 / S31 / R2 等），
它们的中间产物（生片）已归档到 `out/_archive_onetake/`，成片在 `out/approved/`。

清退理由：占用 tools/ 命名空间、易与现行 15 秒管线混淆；其输入目录（out/gen_job_*）已不存在。

| 类别 | 脚本 |
|---|---|
| 批次数据 | brain2_data.py |
| 批次组装 | prep_brain2.py / prep_duikang10.py / prep_d1.py / prep_s31_nverxi.py / prep_w2_carvoice.py / prep_w4_gezi.py |
| 批次执行 | run_batch_brain2.py / run_batch_duikang10.py / run_r2_batch.py |
| 批次验收 | verify_batch_brain2.py / verify_batch_duikang10.py / audit_frames_duikang10.py / diagnose_duikang10.py |
| 批量重烧 | reburn_all.py（依赖已删除的 out/gen_job_* 目录） |

现行管线只用 `tools/make_15s.py`（+ `tools/run_all.py` 队列调度）。
需要做什么新片，从 `tools/prep_xinao10.py`（洗脑批）/ `prep_w3_lunyizu.py`（4镜8句对撞）/ `prep_s30_park.py`（30s 双段）复制结构改数据即可。

注意：`post_batch_duikang10.py` 里的「段名归一化不得硬编码批次前缀」是一条真实教训（写死 R1_ 后整段被静默跳过），
现行 `make_15s.py` 已无此问题。
