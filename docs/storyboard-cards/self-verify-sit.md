---
name: self-verify-sit
一句话: 质疑者亲自做验证动作（坐上去/端水/按下去/踢一脚），打脸由行动完成而不是由台词宣布
适用: 狗血短剧反转镜（镜3）
时长: 3-4s
能量: 峰值（反转）
实证: D2_01（自己坐上车）、D2_05（端着满杯水过门槛）、D2_06（按图钉入胎）、D2_03（一屁股坐下）
---

## 意图

宝哥定的爽点上限 = **质疑者亲自验证 + 当场服气**。让对手自己动手，"打脸"就变成
不可辩驳的事实，比主角喊十句都硬。

## 画面核心（H3 prompt 写法）

```
he sinks down heavily onto the wheelchair's cushion with his full weight
（自己坐上去）
→ 车纹丝不动：the wheelchair does not move, wobble or flex at all
```

```
he pushes the thumbtack straight into the tyre tread with two fingers
（按图钉入胎）
→ the tyre does not deflate at all
```

**公式**：`质疑者的验证动作` + `产品固定不动的结果句`。

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 验证动作 | 一个干净动作，不写分解步骤 | T14 定律：塞太多 H3 会保台词弃动作 |
| 每镜事件数 | ≤3 | 超过就丢句 |
| 结果句 | 必须显式写"不动/不瘪/不洒/不颠" | 不写结果，H3 会自己编一个失败结局 |
| 对手表情 | 眼睛瞪圆 + 张嘴 | 见 `gawk-shock-beat.md` |

## 声音

验证动作落 `mech/machine-activate-short.mp3` 或 `impact/metal-spring-hit.mp3`（0.5），
结果句落 `impact/impact-cine-big.mp3`（0.6）。

## 已知坑

- 验证动作若依赖**地形**（坡道/门槛/台阶）→ H3 画不出。T13 坡道 4 次全败、
  D2_05 门槛+水面均未出现（已改写成 `rough paved ground`）→ **地形一律改平地**
- 结果句不写死（只写"很结实"）→ 出来的是"很结实"的解释性画面，没有物理反证
- 让质疑者做**危险动作**（踢高速移动的车轮）→ 出片会糊成安全动作，改成静态验证

## 参考成片

`out/approved/30-45 号段`（D2 十连）；`out/approved/17 躺平打脸.mp4`（T13）。
