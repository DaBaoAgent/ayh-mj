---
name: narrow-squeeze-park
一句话: 产品挤进只比自身宽一点的窄缝并停稳，用空间余量证明操控精度
适用: 狗血短剧"操控/灵活"型卖点（joystick_360、原地调头）
时长: 3-4s（镜3 反转）
能量: 高（反转）
实证: S30《老邻居的新车》段1（新卡，首次使用，待出片验证）
---

## 意图

"灵活"是抽象词，**窄缝**是它的可视化极限：两车之间只剩一掌宽，产品贴边通过。
观众不需要懂参数，看一眼就知道"这玩意儿真能钻"。

## 画面核心（H3 prompt 写法）

```
the wheelchair rolls slowly FORWARD INTO the narrow gap between the two parked cars,
its sides passing only a hand's width from the cars, then it stops neatly inside the gap
```

**四要素**：
1. `FORWARD INTO the narrow gap`（方向写死，否则会横向漂）
2. `only a hand's width from`（余量写成可比的手掌宽）
3. `stops neatly inside`（落点写死，否则会撞上去）
4. 背景车只露下半截：`only their LOWER HALVES are visible, cut off by the top of the frame`

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 缝宽 | 产品宽 + 一掌 | 太宽不震撼、太窄 H3 会撞车 |
| 速度 | `rolls slowly` | 快 = 危险动作，慢 = 精准操控 |
| 接触 | 必须写 `never touches the parked cars, never scrapes them` | 不写就会刮蹭/穿模 |
| 镜头 | 侧向跟随，两人同框 | 单拍产品会失去"被看着"的对抗感 |
| 落点 | 停在缝内正中 | 写 `stops neatly inside the gap` |

## 声音

- 推进过程铺 `mech/mech-tech-movement.mp3`（0.18，低音量）
- 停稳那帧落 `ui/ui-success-soft.mp3`（0.45）
- 对手反应拍 → `impact/hit-fast-exciting.mp3`

## 已知坑

- **缝宽不写数字量级** → H3 会把缝画成一条马路，毫无难度
- 两侧车导流罩/后视镜容易被画成与产品融合 → 写 `keep the parked cars simple, never touching the wheelchair`
- 若让主角**下车推**，动作意图全毁 → 写死 `ALWAYS SEATED with his hand on the joystick while it moves`
- 本卡尚未出片验证，首次使用按 `docs/执行标准-20260925.md` 先跑快测（¥0.2）

## 参考成片

待出片：`state/onetake_prompt_job_S30_1_zhaifeng.json`（30s 双段《老邻居的新车》段1）。
