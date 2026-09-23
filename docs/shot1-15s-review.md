# 15秒对白镜头 — 审核单（第1镜）

> 状态：✅ 老板已确认（2026-09-23）→ 出片中（工作流 minimax_h3_lightx2v_v5_15s）
> 生成通道：AutoDL `minimax_h3_lightx2v_v5_15s`（15秒多图工作流，实测可跑通）
> 音频方案：H3 原生生成对白+口型+现场音效（不做后期配音，无背景音乐）

---

## 一、对白脚本（5句 / 62字 / 15秒）

真实母子拉扯：儿子发现旧车刹车坏了坚持换 → 母亲固执+心疼钱 → 儿子摆事实 → 母亲松动

| # | 说话人 | 台词 | 字数 |
|---|---|---|---|
| 1 | (S1) 儿子 | 妈，这车刹不住了，不能再骑。 | 13 |
| 2 | (S2) 母亲 | 我用十年了，说扔就扔？ | 11 |
| 3 | (S1) 儿子 | 这个才十三点八公斤，一只手拎得动。 | 17 |
| 4 | (S2) 母亲 | 花那冤枉钱干嘛。 | 8 |
| 5 | (S1) 儿子 | 你先试试，一键折叠，塞后备箱就走。 | 15 |

- 总字数 64 / 15秒容量 64.5（4.5字/秒×15−0.6秒余量）= **99% 铺满** ✓
- 无阿拉伯数字、无英文夹带；“十三点八”“二一八”均为中文读法 ✓
- 时轴无重叠：S1→S2→S1→S2→S1 依次交替

## 二、H3 提示词（官方三段式）

```
integrated_multimodal_description: [Shot 1] Live-action documentary style, one continuous steady shot. Autumn afternoon in a Chinese residential community, grey paving tiles, blurred green trees, soft dappled sunlight. A 45-year-old Chinese man (S1) in a black jacket and blue jeans kneels beside a silver-grey lightweight electric wheelchair with red front springs; a 68-year-old Chinese woman (S2) in a plum-red fleece jacket sits in the wheelchair. Both faces stay unobstructed in a medium two-shot and keep their exact faces, hairstyles and clothing from the reference images. The man (S1) says with concern: <d>[Chinese] 妈，这车刹不住了，不能再骑。</d> The woman (S2) replies stubbornly: <d>[Chinese] 我用十年了，说扔就扔？</d> The man (S1) pats the folded frame: <d>[Chinese] 这个才十三点八公斤，一只手拎得动。</d> The woman (S2) mutters: <d>[Chinese] 花那冤枉钱干嘛。</d> The man (S1) unfolds it one-handed: <d>[Chinese] 你先试试，一键折叠，塞后备箱就走。</d> Speak at a natural, brisk conversational pace with no long pauses. Only one person speaks at a time in this exact order, verbatim: no overlap, no extra words, no omissions, no repetition, no interruption, no invented lines. The wheelchair keeps its exact frame shape, color and brand lettering from the reference image. Camera holds steady, no cuts.

overall_soundscape: Quiet residential community ambience: a light breeze through trees, distant birds, faint footsteps on paving tiles, and a soft mechanical click when the wheelchair frame folds. Voices clear and natural outdoors.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference image; no background music; both characters keep complete visual consistency with their reference images throughout.
```

## 三、生成参数

| 项 | 值 |
|---|---|
| workflow | `minimax_h3_lightx2v_v5_15s` |
| duration | 15 |
| resolution | 768p竖 |
| 参考图 | ①母亲定妆图 ②儿子定妆图 ③产品白底图（正侧） |

## 四、对照官方规则自检（rules-dialogue R1-R30）

| 规则 | 状态 |
|---|---|
| R1 `<d>[Chinese]</d>` 语法 | ✓ 5句全部包裹 |
| R2 台词一字不改、基础标点 | ✓ |
| R5 (S1)(S2) 固定编号 | ✓ 跨句一致 |
| R7 编号在 `<d>` 外 | ✓ |
| R10 字数≤时长×4.5-0.6s | ✓ 62≤64.5 |
| R13 官方三段式 | ✓ |
| R14 台词只在 description | ✓ |
| R15 正文英文+台词中文 | ✓ |
| R18/R19 无阿拉伯数字/英文 | ✓ |
| R25 品牌字保留+平台水印禁止 | ✓ 已显式声明 |
| R26 体量 | ✓ 约390单位（英文/3+中文字） |
| R28 铺满90-100% | ✓ 96% |
| R29 显式语速 | ✓ brisk conversational pace |
| 抢话/重复/加词禁止 | ✓ 已显式声明 |

## 五、出片后验收方案

1. `whisperx` 转写（AutoAYH 已装）→ 逐字比对剧本，一致率须 100%
2. 检查口型归属（S1 说话时 S2 嘴不动）
3. 检查现场音效存在、无背景音乐
4. 检查画面无乱码文字/产品品牌字正常
