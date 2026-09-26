---
name: confront-block
一句话: 对手张开双臂横在车前/车位前，把冲突在第一秒摆到物理空间上
适用: 狗血短剧镜1 立靶子；一切"拦车/占位/挡路"型开局
时长: 3-4s（镜1 全程）
能量: 中高（冲突起点，身体动作而非嘴仗）
实证: D2_02《校门口急停》、D2_07《庙会慢行》、D2_09《露营收车》、D2_01《夜市摞货》
---

## 意图

短剧的"冲突"必须是**看得见的位置争夺**，不是口头意见不合。张臂横挡 = 一眼看懂的
领地宣告，观众 1 秒内就站好了队（被挡的一方天然是主角）。

## 画面核心（H3 prompt 写法）

```
the <对手> stands with BOTH ARMS RAISED STRAIGHT OUT SIDEWAYS, palms forward,
blocking <车位/车前/门口> behind him, chin high and eyes on <主角>
```

**必须写全三个要素**，少一个 H3 就会降级：
1. `BOTH ARMS RAISED STRAIGHT OUT SIDEWAYS`（不是"张开手"——会被降级成说话手势）
2. `palms forward`（掌心朝外，这才是"挡"）
3. `blocking <具体位置>` + `chin high`（说清挡的是什么 + 傲慢表情）

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 手臂位置 | 与肩同高的水平伸展 | D2 批实测：写"张开双臂挡车"被降级成说话动作；补 `at shoulder height` + `keeps them raised through the whole shot` 才成立 |
| 保持时长 | 整个镜头不放 | `keeps them raised through the whole shot` |
| 视线 | 看主角（三/四侧脸），**不瞪镜头** | 瞪镜头是品牌句的专利 |
| 对手站位 | 主角前方 1-1.5m，**不要入画动作** | 新人物必须一开始就在场，H3 画不好 walks into frame |

## 声音

落 `impact/stomp-apocalyptic.mp3` 或 `ui/switch-click-quick.mp3`（轻量版，0.4）
钉在"手臂张到位"那一帧。

## 已知坑

- **降级是常态**：不写 `both arms straight out sideways` + `palms forward`，
  H3 大概率出成"聊天的老头"，拦车动作消失（D2 批 6/10 条踩过）
- 对手入画（`walks into frame`）必崩 → 开场就要在场
- 手臂与车把重叠时容易被画成扶车 → 让对手站**车前偏侧**，别正对车把

## 参考成片

`out/approved/` 28-45 号段（D2 十连批次）；配对本卡的反击卡见 `self-verify-sit.md`。
