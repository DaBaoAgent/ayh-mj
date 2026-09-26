---
name: gawk-shock-beat
一句话: 打脸瞬间给对手一个"瞪眼 + 张嘴 + 身体后仰"的反应拍，反应比主角的表演更重要
适用: 每条狗血短剧的反转后 0.5-1.5s（镜3 尾 / 镜4 头）
时长: 0.5-1.5s
能量: 峰值回落
实证: 全部 D2 十连 + W3；宝哥令「动作要有对抗，人物表情要激烈」（D2 批整改项）
---

## 意图

反转的爽感由**对手的表情**交付，不是由主角交付。D2 批验收时"表情激烈度 4/10 激烈"
被判不足 → 此后每条必写表情拍。

## 画面核心（H3 prompt 写法）

```
his eyes go wide and his mouth drops open, then he jabs his finger at the wheelchair
with his chin thrust out
```

**三件套**：`eyes go wide` + `mouth drops open` + 一个身体位移（后仰/倒退半步/弯腰）。

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 持续时间 | 0.5-1.5s | 短于 0.5s 观众读不到，长于 1.5s 变拖 |
| 身体位移 | 至少一个：`leans back` / `steps back half a step` / `bends forward` | 纯脸部特写会像静态图 |
| 时机 | 落定帧之后，**不在动作进行中** | 动作中给反应 = 反应被吃掉 |
| 台词 | 可给一句惊叫（"哎哟，真塞进去了？"） | 惊叹词是短剧的标点 |

## 声音

反应拍落 `impact/hit-fast-exciting.mp3`（0.45）；若是当众打脸，补
`crowd/applause-rhythmic-loop.mp3`（0.22，垫 1s）。

## 已知坑

- 只写 `looks surprised` → 出来是"面无表情地看"（D2 批实测）
- 反应拍与主角的碾压台词汇在同一镜里 → 分配要清楚（谁先谁后），否则两人嘴同帧动
- 对手手在忙（拿着东西）时表情拍会被手部动作抢走注意力 → 先让手停

## 参考成片

`out/approved/` 全库；表情节拍写法见 `docs/scripts-短剧狗血10连-对抗版-20260925.md` 各条的「表情节拍」行。
