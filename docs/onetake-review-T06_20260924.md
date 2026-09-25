# T06 后备箱魔术 · 单条多镜头版 — 审核单

> 状态：**✅ 已交付并归档（2026-09-24）** → `out/approved/T06_后备箱魔术_20260924.mp4`（13.6s/带字幕/明快档）
> 成片实测：4 镜切换 ✓ / 折叠态竖立 ✓ / 台词全对（双模型复核） / 双音色女男声 ✓ / 画面无乱字 ✓
> 新工艺：**全部 4 个分镜在一条 15 秒视频里一次生成**——人物一致性与声音一致性由单次生成 + 定妆图 + 双音色克隆保证，不再逐镜拼接。
> 宝哥批准附加项：① 节奏「**明快档**」固化为以后默认（停顿 ≥0.35s→0.20s、头尾 ≤0.15s）② **折叠态必须竖立立在地面**（已写进提示词，按产品参考图形态）
> 日期：2026-09-24 ｜ job: `job_20260924_113354_828826_20`

---

## 一、方案概览（四重轮换：全部换新）

| 项 | 值 | 说明 |
|---|---|---|
| 模板 | **T06 后备箱魔术** | 第 6 号，未用过（T01-T05 已用），系统自动选出 |
| 思路 | **B5 孝心礼物真香** | 未用过（A1-A7/B1-B4 已用）：偷偷买礼物被爸妈嫌弃→用起来真香 |
| 卖点 | **18 股护脊减震**（shock_18） | 11 个卖点里从未当主打过；可视化证据 = 一筐生鸡蛋过减速带不碎 |
| 角色组 | **核心卡司**（儿子 45 + 母亲 68） | 4 组轮换（欧美组→核心卡司组），回到第 1 组 |
| 绑定热点 | 上一辈的节俭，让人心疼还是无奈 | 化为母亲一句「又乱花钱……退了去」 |

**一句话故事**：后备箱塞满行李和老家鸡蛋，母亲盯着刚拆箱的新车数落「又乱花钱，明儿退了去」→ 儿子不辩解，把鸡蛋筐搁上车、扶妈坐下一句「您先坐上去遛一圈」→ 车碾过减速带，一筐鸡蛋一个没碎，母亲愣住改口 → 儿子点破「全靠这十八股减震」，品牌收尾。

## 二、四镜分镜表（一条 15s 视频内）

| 镜 | 时段 | 时长 | 画面（起→止） | 说话人 | 台词 | 字数 |
|---|---|---|---|---|---|---|
| 1 | 0-4.0s | 4.0s | 塞满的后备箱、顶上搁一筐鸡蛋；母亲盯着新车皱眉，手推车架想塞回去 | S2 母亲 | 哎哟又乱花钱，这新车明儿赶紧给我退了去。 | 18 |
| 2 | 4.0-7.5s | 3.5s | 儿子把鸡蛋筐搁上踏板、展开车架、扶母亲坐上去，一拍车把 | S1 儿子 | 退啥呀？妈您先坐上去，遛一圈再试试。 | 15 |
| 3 | 7.5-11.5s | 4.0s | 车碾过减速带，鸡蛋筐晃都没晃；母亲低头看鸡蛋，眉头松开 | S2 母亲 | 哎？车碾过减速带，这筐鸡蛋咋一个都没碎呀？ | 18 |
| 4 | 11.5-15s | 3.5s | 折叠车塞进后备箱最后一点空位、盖子合上鸡蛋完好；母子相视一笑，母亲摸车把 | S1 儿子 | 全靠这十八股减震呢，爱优护轻便侠。 | 15 |

**台词合计 66 字**（校验器口径：15s 档下限 65 / 上限 72）→ 铺满率 **98.7%**（4.5 字/秒 × 15s − 0.6s 余量 = 66.9 字）。

## 三、H3 提示词全文（一条视频四镜，官方三段式）

```text
integrated_multimodal_description: Live-action documentary drama, vertical framing, natural daylight. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. The camera stays wide in every shot: every person's full body from head to toe fully visible with the environment around, each figure occupying roughly half of the frame height. The same 45-year-old Chinese man (S1) in a black jacket and blue jeans and the same 68-year-old Chinese woman (S2) with short silver-grey hair in a plum-red fleece jacket appear across the shots, keeping their exact faces, hairstyles and clothing from the reference images. Their two voices are clearly distinct from each other: the man (S1) speaks in a low-pitched, warm masculine voice, and the woman (S2) speaks in a soft, higher-pitched elderly feminine voice; each of them keeps the same individual voice in every shot they speak in. Cast: exactly two people in the whole video; shot 1 shows the woman only, shot 2 shows both, shot 3 shows the woman only, shot 4 shows both; each person appears EXACTLY ONCE in every shot — never duplicate, clone, mirror, split or twin any person into a second figure anywhere in the frame (foreground, background, edge, doorway, glass or blur); no extra bystanders, no stand-ins. The silver-grey lightweight electric wheelchair always keeps its exact form from the reference images — its four small wheels, seat frame and armrests clearly visible whenever it is on screen — and never turns into a bicycle, scooter, motorcycle or any other vehicle.

[Shot 1, 0 to 4 seconds] Wide shot from a slightly high angle over the open trunk of a parked car at a quiet residential compound: the trunk is packed full with luggage and vegetables, a wicker basket of fresh eggs resting on top. The woman (S2) stands beside the trunk frowning at a brand-new folded electric wheelchair just taken out of its box; she pushes the folded frame with one hand as if trying to shove it back in, and complains in an annoyed, grumbling tone at a slightly brisk pace (clear articulation, a bit faster than natural): <d>[Chinese] 哎哟又乱花钱，这新车明儿赶紧给我退了去。</d> She finishes the line right before the shot ends.

[Shot 2, 4 to 7.5 seconds] Hard cut to a wide eye-level view of the same spot: the man (S1) sets the egg basket carefully onto the wheelchair's footrest, then unfolds the frame — its four small wheels settle onto the ground and the seat frame locks into place — and helps the woman (S2) sit down on the seat. He pats the handlebar and says in a confident, coaxing tone at a slightly brisk pace: <d>[Chinese] 退啥呀？妈您先坐上去，遛一圈再试试。</d> He finishes the line right before the shot ends.

[Shot 3, 7.5 to 11.5 seconds] Hard cut to a wide low-angle tracking shot: the wheelchair with the woman (S2) in it and the egg basket on its footrest rolls over a speed bump; the basket does not shake or tip at all. The woman looks down at the intact eggs and says in sudden surprise at a slightly brisk pace: <d>[Chinese] 哎？车碾过减速带，这筐鸡蛋咋一个都没碎呀？</d> Her frown relaxes while she speaks.

[Shot 4, 11.5 to 15 seconds] Hard cut to a wide shot of the trunk being closed: the folded wheelchair sits neatly in the last remaining corner of the packed trunk, everything still fits, and the lid closes with the eggs intact. The man (S1) smiles and says with a satisfied, warm tone at a slightly brisk pace: <d>[Chinese] 全靠这十八股减震呢，爱优护轻便侠。</d> The woman (S2) reaches out and pats the handlebar, smiling back. He finishes the line right before the video ends.

Only one person speaks at a time in this exact order — (S2) in shot 1, (S1) in shot 2, (S2) in shot 3, (S1) in shot 4; whoever is not speaking at that moment keeps their lips completely closed and never moves their mouth; the dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repetition, no interruption, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet residential compound ambience, light breeze, faint distant birds, a soft click when the trunk lid closes, a gentle rattle of the wicker basket settling, the low hum of the wheelchair motor. Voices clear and natural outdoors.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference image; the electric wheelchair must never turn into a bicycle, scooter or motorcycle; no background music; everyone keeps complete visual consistency with the reference images throughout; the four shots are joined by immediate hard cuts with no fades or dissolves.
```

## 四、生成参数

| 项 | 值 |
|---|---|
| 工作流 | `minimax_h3_image_audio_to_video_v2_15s`（多图多音频 15 秒版；失败自动切 `zm_u08`→`zm_u24`） |
| 时长 / 分辨率 | 15s / 768p竖 |
| 参考图 (4) | ① 儿子全身定妆 ② 母亲全身定妆 ③ 产品折叠态 ④ 产品正侧 |
| 参考音频 (2) | ① `son_voice.mp3`（儿子音色）② `mother_voice.mp3`（母亲音色）→ ref_audio_0/ref_audio_1 双音色克隆 |
| 预估成本 | **约 ¥0.6**（15s × ¥0.04/s；旧价 ¥0.9） |
| 生成耗时 | 约 9-12 分钟（15s 档） |
| 节奏 | **明快档（宝哥定，默认）**：停顿 ≥0.35s → 0.20s、头尾 ≤0.15s（`trim_onetake.py`，生成后自动执行） |
| 后期 | 无拼接（单条即整片）→ 节奏裁剪 → 烧字幕（≤10 字/行）→ 归档 |

**多音频实测**：已用免费探测确认 `ref_audio_0` / `ref_audio_1` 均为该工作流合法字段（未知字段会报「存在未定义的参数」，ref_audio_1 不报；ref_audio_9 越界被拒）。

## 五、技术验证（实测 5s 小片，每条约 ¥0.2）

| 验证片 | 目的 | 结果 |
|---|---|---|
| 1. 双镜+双音色（S1 先说） | ①一条视频内多镜头切换 ②两个音色各自分离 ③台词准确性 | ✅ **镜头切换成立**（儿子镜头→母亲镜头，抽帧确认）；✅ **台词 100% 正确**（whisper 转写："妈这车过坎一点不颠/真的假的 我试试"，与剧本一致）；✅ 人物与定妆图一致 |
| 2. 说话顺序映射（S2 先说、S1 后说，原挂载） | 正式片是母亲先开口，验证音色是否受影响 | ✅ 台词/归属正确；基频读数：段1(母亲)=262Hz、段2(儿子)=219Hz |
| 3. 挂载交换对照（同 2，但 ref_audio_0↔1 交换） | 判定音色分配是否与「挂载顺序」有关 | ✅ 段1(母亲)=**262Hz**、段2(儿子)=**203Hz** —— 与验证片 2 几乎一致 → **音色分配不受挂载顺序影响**（H3 稳定给母亲配女声、儿子配男声） |

> 音色底数（同一分析器读数，供对照）：son_voice=258Hz、mother_voice=184Hz；T05 已验收成片男角=168-205Hz；T01 儿子=155Hz/母亲=281Hz。
> **结论**：正式片保持「儿子→ref_audio_0、母亲→ref_audio_1」的索引挂载即可；生成后按听感复核（若个别音色不符，交换挂载重跑一次，成本 +¥0.6）。

## 六、花钱前自检（check_dialogue.mjs，0 ERROR）

| 检查 | 结果 |
|---|---|
| `<d>[Chinese] …</d>` 语法 / (S1)(S2) 编号 / 编号在 `<d>` 外 | ✓ |
| 台词无阿拉伯数字 / 无英文 / 无重复标点 | ✓ |
| 台词量 66 字 ∈ [65, 72]（15s 档，4.5-5 字/秒铺满） | ✓ |
| 语速声明（slightly brisk ×4） | ✓ |
| 三段式结构 / 台词不重复进 soundscape / 正文英文+台词中文 | ✓ |
| 画面无文字声明 + 品牌字保留声明 | ✓ |
| 提示词体量 1305（较 T05 实测成功的 823-991 高 32%） | ⚠ 先试，失败则压缩重试（见风险） |

## 七、风险与 Fallback

1. **参考图 4 张**：有历史教训（某些工作流 ≥4 张推理期 FAILED 且不报参数错）→ 若失败，降为 3 张（儿子/母亲/正侧）重试。
2. **提示词体量 1305**：T05 用 823-991 成功 → 先试；若推理失败，压缩版（删重复约束，~1100）重试。
3. **多镜头切换**：✅ 已在测试片验证成立；正式片验收时仍复核 4 个切换点（0/4/7.5/11.5s）。
4. **音色分配**：✅ 对照实验完成——交换挂载后母亲段仍 262Hz / 儿子段 203Hz（与未交换版一致）→ 分配稳定，正式片保持索引挂载；若成片听感不符，交换重跑（+¥0.6）。
5. **音色区分度**：母亲稳定 ≈262Hz（女声）、儿子稳定 ≈203-219Hz（男声），男/女区分清晰；提示词已加「两人音色明显不同」文字描述；成片逐句听感验收。
6. **品牌字渲染**：H3 历史已知会把品牌字渲染成竞品名/乱码字母（测试片中出现 "airfly" 字样）→ 成片按 R23 复核产品品牌字，不符则重跑。
7. **动作保真度**：测试片中个别姿势与提示词有偏差（如"半蹲抓车"而非"跪在车旁"）→ 正式片验收时核对 4 个关键动作（推车/扶坐/过坎/关箱）。

## 八、生成后验收方案

1. `whisperx` 转写 → 逐字比对 4 句台词（要求 100%）
2. 抽帧检查：镜头数 = 4（切换时刻对齐 0/4/7.5/11.5s±0.5s）、人物与定妆图同人、无克隆人、产品不变形
3. 听感：两句话音色分别吻合 son/mother 样本；环境音存在；无背景音乐
4. 画面无文字/水印，产品品牌字保留
5. 通过 → 烧字幕 → 归档 `out/approved/T06_后备箱魔术_20260924.mp4`

## 九、下一步

宝哥审核：**① 故事/台词 ② 提示词 ③ 参数（¥0.6）** 任一项要改直接说；回复「就这样跑」即生成。
