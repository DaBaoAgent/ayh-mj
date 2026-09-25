# T07 宠物视角 · 单条多镜头版 — 制作记录

> 状态：**生成中（v2）** ｜ job: `job_20260924_135019_414348_21`
> 新工艺：一次调用生成含全部 4 镜的整条 12s（v2_15s + 双音色克隆 + 明快档）

## 一、方案概览（四重轮换）

| 项 | 值 |
|---|---|
| 模板 | **T07 宠物视角**（未用模板） |
| 思路 | **B6 快递小哥视角**（未用池） |
| 卖点 | **能上飞机免费托运**（首次主打） |
| 角色组 | 城市家庭组（爸爸 50 / 妈妈 45 / 狗） |
| 热点 | 父母年纪大了，什么才是真正的孝顺 |
| 故事 | 快递小哥送货盯着箱子看傻了 → 狗凑近闻车、抢先试坐 → 奶奶把占座的狗抱下来收尾 |

## 二、四镜台词（52 字 / 12s，铺满 99.2%）

| 镜 | 时段 | 说话人 | 台词 | 字数 |
|---|---|---|---|---|
| 1 | 0-3s | S1 | 快递小哥盯着这箱子，彻底傻了。 | 13 |
| 2 | 3-6s | S1 | 小哥感叹，他也想给他妈买一个。 | 13 |
| 3 | 6-9s | S1 | 这车厉害了，上飞机都免费托运。 | 13 |
| 4 | 9-12s | S2 | 哎，快下来！这就是爱优护轻便侠。 | 13 |

## 三、H3 提示词全文（v2）

```text
integrated_multimodal_description: Live-action documentary drama in a playful low pet-camera style, vertical framing, natural daylight. This 12-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and brisk: the first line starts within the first quarter second, every speaker begins speaking immediately after the previous speaker's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera stays low, near the ground at a small dog's eye level, wide angle, and every person's full body from head to toe is fully visible whenever they appear. Cast: exactly three people and exactly one dog in the whole video — a young Chinese delivery rider (28) in a yellow jacket and black helmet, a 50-year-old Chinese man in dark blue work clothes matching the second reference image, a 45-year-old Chinese woman in a beige cardigan matching the third reference image, and one small beige bichon frise dog matching the first reference image; every one of them appears EXACTLY ONCE per shot — never duplicate, clone, mirror, split or twin any person or the dog into a second figure anywhere in the frame (foreground, background, edge, doorway, glass or blur); no extra bystanders, no stand-ins. The silver-grey lightweight electric wheelchair always keeps its exact form from the reference images: when folded, it stands upright on the ground as a compact vertical column resting on its large rear wheel and small anti-tip caster — never laid flat on its side, never floats in mid-air and never turns into a bicycle, scooter, motorcycle or any other vehicle; when unfolded, its four small wheels, seat frame and armrests are clearly visible.

[Shot 1, 0 to 3 seconds] Low wide shot from a dog's eye level inside a doorway of a residential compound, looking out at the entrance. A young delivery rider in a yellow jacket and black helmet sets down one large cardboard box on the ground, straightens up and stares at it, completely dumbfounded, mouth closed, scratching the back of his head; the small beige bichon frise dog stands inside the doorway looking up at the box. The 50-year-old man (S1) in dark blue work clothes stands at the doorway beside them, looking at the rider with an amused smile, and says in a warm, amused tone at a slightly brisk pace: <d>[Chinese] 快递小哥盯着这箱子，彻底傻了。</d> Only (S1) speaks in this shot; the rider's mouth stays closed and he does not speak; the dog makes no sound.

[Shot 2, 3 to 6 seconds] Hard cut to the same doorway from a low wide angle: the 50-year-old man (S1), whose face, hair and dark blue work clothes exactly match the second reference image, cuts open the box and lifts out a folded electric wheelchair; he unfolds it on the ground — its four small wheels settle down and the seat frame locks into place. The rider leans in, eyes wide, mouth closed, then takes out his phone and snaps a photo; the dog steps closer and sniffs the frame. The man (S1) says in a proud, playful tone at a slightly brisk pace: <d>[Chinese] 小哥感叹，他也想给他妈买一个。</d> Only (S1) speaks in this shot; the rider and the dog keep their mouths closed and never move them.

[Shot 3, 6 to 9 seconds] Hard cut to a low wide shot at the doorway, next to a small suitcase standing on the ground: the bichon frise dog has climbed onto the unfolded wheelchair and sits on its seat with its tail wagging, looking straight into the camera; the rider stands beside it with his mouth closed and gives a big thumbs-up; the 50-year-old man (S1) stands at the other side of the wheelchair and says in a cheerful, bragging tone at a slightly brisk pace: <d>[Chinese] 这车厉害了，上飞机都免费托运。</d> Only (S1) speaks in this shot; the rider and the dog keep their mouths closed and never move them.

[Shot 4, 9 to 12 seconds] Hard cut to a low wide shot at the same spot: the 45-year-old woman (S2), whose face, hair and beige cardigan exactly match the third reference image, walks over, bends down and scoops the dog up into her arms, smiling; the unfolded wheelchair stands beside them and the rider watches with a grin. The woman (S2) says in a warm, amused scolding tone at a slightly brisk pace: <d>[Chinese] 哎，快下来！这就是爱优护轻便侠。</d> She finishes the line right before the video ends. The rider stays silent; his lips remain completely closed.

Only one person speaks at a time in this exact order — (S1) in shots 1, 2 and 3, (S2) in shot 4; every speaker is fully visible on screen while speaking. The dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repetition, no interruption, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet residential compound ambience, light breeze, a soft cardboard thud as the box is set down, a light mechanical click as the wheelchair frame unfolds, one happy little dog pant, and a friendly camera-shutter click. Voices clear and natural outdoors.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference image; the electric wheelchair must never turn into a bicycle, scooter or motorcycle; no background music; everyone keeps complete visual consistency with the reference images throughout; the four shots are joined by immediate hard cuts with no fades or dissolves.
```

## 四、生成参数

| 项 | 值 |
|---|---|
| 工作流 | minimax_h3_image_audio_to_video_v2_15s（失败自动降级） |
| 时长/分辨率 | 12s / 768p竖 |
| 参考图 (4) | ① 比熊犬定妆 ② 城市爸爸 ③ 城市妈妈 ④ 产品折叠态 |
| 参考音频 (2) | city_dad_50.mp3 / city_mom_45.mp3 |
| 成本 | ≈¥0.72/条（两次尝试 ¥1.44） |

## 五、迭代记录（诚实留档）

**v1 问题**（task f4b15c74）：
1. 画外音镜头（镜1/3）里快递小哥张嘴——把旁白当成自己在说话，口型归属错乱
2. 儿子（S1）全程未入画——镜2「拆箱展车」动作被派给快递小哥，S1 台词无归属
（台词本身 100% 正确，small+medium 双模型复核；狗/场景/产品正常）

**v2 修正 + 残留问题**（task 55e2cf9d）：
- 修正生效：镜1 儿子入画 ✓、镜2 儿子拆箱展车 ✓、画外音已去除
- 残留：**镜3 儿子未入画**（台词又落到画面里的骑手身上→骑手张嘴）；镜4 骑手露齿笑被画成张嘴

**v3 修正**（当前）：
1. 镜3：儿子前置到段首 + 「exactly match the second reference image」绑定 + 「stands right beside the wheelchair」位置强调；骑手降级「stands a little farther back, mouth closed」
2. 镜4：骑手闭嘴强化（「smiling with his mouth completely closed」）

**教训（已入技能）**：one-take 里多人物同框时——说话人必须写段首 + 参考图绑定 + 位置强调；配角一律降级+显式闭嘴；禁用画外音设计

**v5/v6 产品保真重跑**（2026-09-24 下午，宝哥反馈「轮椅不真实，不像我们的爱优护轻便侠」后）：
- **根因确认**：T07 为给 3 个角色腾参考图位子，砍了「正侧（展开态）」图 → 展开态无锚定，H3 脑补成通用手动轮椅
- **480p 对照测试**（A/B/C 三组）：A 折叠单图 = ❌"手动轮椅"；B 折叠+正侧 = ✅"像中高端电动轮椅"；C 折叠+正侧+45度 = ✅✅ 细节最全（含真车靠背绿线）——详见 `docs/test-product-ref.md`
- **宝哥立铁律**：展开状态轮椅必须「折叠+正侧+45度」**三张全给**（技能/记忆/代码三层落地）
- **v5** = 5 图（3角色+折叠+正侧）；**v6** = 6 图（3角色+折叠+正侧+45度，按新规）→ 终版从 v5/v6 择优

## 六、验收结果（v6 定稿 ✅ · 6 图版）

- [x] 4 镜切换 ✓ / 人物与狗一致 ✓ / 无克隆 ✓（逐帧抽检）
- [x] 台词 100%（4 句全对）
- [x] 口型：快递骑手镜 1/2/3/4 **全闭嘴** ✓（v4 镜1微张已修）；说话人全画面内 ✓
- [x] **产品（核心升级）：品牌字首次正确渲染 "Ainsnbot" ✓ + 操纵杆/电动感可见 ✓ + 红弹簧 ✓ + 靠背绿线还原 ✓ → 判读「中高档电动轮椅」✓**
- [x] 字幕：8 条自然分句全部 ≤10 字，位于画面下方 1/3
- [x] 节奏明快档：12.25s → **10.86s**
- [x] 归档：`out/approved/T07_宠物视角_20260924.mp4`（v6 六图版）

**版本演进全记录**：v1 画外音失败 → v2 人物修好 → v3 口型全过 → v4 红弹簧 → v5 五图 → **v6 六图（品牌字正确，定稿）**
**本条成本**：≈¥4.92（4 次重跑 + ¥0.6 对照测试 + v5/v6）——偏高，根因=产品参考图规范缺失（宝哥已立铁律，下条起不再犯）

## 七、归档

- 成片：`out/approved/T07_宠物视角_20260924.mp4`（11.07s 带字幕，job → ready）
- 过程版本留档：gen 目录 `onetake_v1_骑手搬车版.mp4` / `onetake_v2_镜3缺儿子.mp4` / `onetake_v3_人物全过产品弱.mp4`
