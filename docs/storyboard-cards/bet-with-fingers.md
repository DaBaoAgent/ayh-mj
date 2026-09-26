---
name: bet-with-fingers
一句话: 对手当众下注并举起具体根数的手指示意，赌注必须在结尾能用身体动作兑现
适用: 狗血短剧镜2 加压（赌约型）
时长: 2-4s
能量: 中高（悬念拉满）
实证: W3 镜2（指胸口下注）、D2_01 镜2、D2_09 镜2、S30《老邻居的新车》段1 镜2 / 段2 镜1
---

## 意图

**赌约是狗血短剧的引擎**：对手下注 → 观众等兑现 → 结尾用画面兑现。赌注要"具体、
可视、能用身体动作演出来"（俯卧撑 / 请客 / 三顿饭 / 做一百个）。

## 画面核心（H3 prompt 写法）

```
he holds up THREE FINGERS right in front of his chest, chin high and eyebrows raised,
making his bet
```

或手指标的方向：

```
she jabs a finger straight at the grandpa's chest in a loud public bet, chin thrust out
```

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 手势 | 举手指 / 手指指向对方胸口 | `THREE FINGERS` 要全大写＋数字英文，H3 才数得对 |
| 表情 | `chin high` + `eyebrows raised` | 傲慢三件套之一 |
| 台词长度 | 单句 ≤13 字 | 超过会被念断（H3 硬约束） |
| 赌注形式 | 能演的动作 > 口头承诺 | "请客/三顿饭"靠**掏钱/点头**演出来 |

## 声音

下注句落 `glass/glass-hit-cine.mp3`（0.4，悬念）+ 落定后 0.2s 接 `crowd/heartbeat-single.mp3`。

## 已知坑

- 赌注写成"你要能 X 我就 Y"，但结尾没有**可演的动作**兑现 → 全片爽感归零
- 举手指不写根数（`THREE FINGERS`），H3 会画成挥手
- 手指指向对方胸口时若两人距离过近，会画成戳人 → 保持一臂以上

## 参考成片

`out/approved/48 轮椅组就您一个人.mp4`；30s 双段结构用法见 `docs/sequences/30s-two-part.md`。
