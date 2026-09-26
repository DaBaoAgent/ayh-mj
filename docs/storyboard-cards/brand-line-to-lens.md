---
name: brand-line-to-lens
一句话: 全片只有品牌句那一句让说话人转脸直视镜头，其余所有对话一律看对方
适用: 每条片的最后一句
时长: 1-1.5s
能量: 收束
实证: GAZE 规则（宝哥 2026-09-25 令），48 条已拍全适用
---

## 意图

看镜头 = 打破第四面墙 = "这句话是说给观众听的"。**稀缺才有效**：全片只此一次，
观众立刻知道这是品牌落点。若对话中也看镜头，就变成了廉价的"对镜头说话"。

## 画面核心（H3 prompt 写法）

```
for the branding line only, he turns his face to the camera and looks straight into the lens
```

配套（写在 CAST/GAZE 段）：

```
GAZE RULE: while the two people talk to each other, each speaker turns their face TOWARD THE
OTHER PERSON — a natural three-quarter view from the camera, never a straight-to-camera stare.
```

## 参数表

| 项 | 值 | 说明 |
|---|---|---|
| 品牌句形式 | **只报品牌名**，不挂卖点口号（"爱优护轻便侠。"=6 字） | 宝哥 2026-09-26 令 |
| 时长 | 1-1.5s，全片最后 | 结尾静默 ≤0.15s（明快档） |
| 镜头 | 缓缓拉远（pull back） | 让品牌句有呼吸，且露出双方关系 |
| 视线 | 直视 lens，不斜视、不瞪 | `looks straight into the lens` |

## 声音

品牌句落 `ui/chime-crystal.mp3`（0.35）或 `light/sparkle-touch.mp3`（0.4），
BGM 在此句提升 3-5dB 收尾。

## 已知坑

- 品牌名会被 H3 渲染成竞品名（实测）→ prompt 里写死 "brand lettering as in references"
- 品牌句挂口号（"皮实又省心，认准爱优护轻便侠"）→ 已改为极简式，只报品牌名
- 不看镜头 = 品牌句白写；所有人都在看镜头 = 品牌句失效

## 参考成片

`out/approved/48 轮椅组就您一个人.mp4`（品牌句极简式范本）；实现见
`lib/prompt_parts.py::GAZE`。
