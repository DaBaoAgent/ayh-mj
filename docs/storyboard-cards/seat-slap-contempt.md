---
name: seat-slap-contempt
一句话: 对手单手拍/按产品两下表示轻蔑，主角用手背把他的手掌拨开——一拍一拨完成第一轮对撞
适用: 狗血短剧"能力羞辱"型镜1-镜2
时长: 2-3s
能量: 中高（身体接触级对抗）
实证: W3《轮椅组就您一个人》镜1（宝哥定稿结构范本）
---

## 意图

"看不起"要用**触碰产品的方式**表达——拍一下、按一下、用脚踢一下。主角的回应也必须
是身体动作（拨开/拍回），语言只做辅助。这是 W3 定稿结构里的第一轮对撞。

## 画面核心（H3 prompt 写法）

```
she slaps the wheelchair's cushion twice with one flat hand in contempt, chin high,
eyes on the grandpa; he flicks her hand off the seat with the back of his hand,
chin up, and gives her a sharp defiant look
```

**动作成对**：拍 → 拨，一收一放写在同一个镜头里。

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 拍击次数 | 2 下 | 1 下太轻、3 下像打鼓 |
| 拨开方式 | `back of his hand`（手背） | 用手掌会像握手/牵手 |
| 两人距离 | 一臂内，同框 | 必须 `keeping BOTH of them in frame` |
| 视线 | 两人互看，都不看镜头 | GAZE 规则 |

## 声音

拍击配 `impact/hit-weak.mp3`（0.45），拨开配 `ui/switch-click-quick.mp3`（0.35）。
**同一帧不叠两个 impact。**

## 已知坑

- 写"拍车座"但不写"两下 + 单手平掌"，H3 会画成抚摸
- 拨开动作若不写 `from the seat`，容易画成两人握手
- 手与产品的接触点必须落在**坐垫/车把**这类明确部件上，写"拍车身"会让 H3 到处乱放

## 参考成片

`out/approved/48 轮椅组就您一个人.mp4`（W3 定稿，宝哥口述结构范本）。
