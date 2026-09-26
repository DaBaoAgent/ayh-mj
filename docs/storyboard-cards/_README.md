# 真人分镜配方卡（storyboard-cards）

> 格式借自 [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) 的
> `references/shots/` 镜头配方卡（157 张）：**一句话 + 适用 + 时长 + 能量 + 画面核心 +
> 参数表 + 声音 + 已知坑 + 参考成片**。
>
> 但内容全部换成 **ayh-mj 自己验证过的真人拍摄分镜** —— video-shotcraft 的卡是为
> Remotion 动效（网页/桌面 2.5D 运镜）写的，跟 H3 真人短剧不通用；通用的是
> **卡片这个载体**：把"能用的写法"和"踩过的坑"固化下来，避免每次重写 prompt 时再踩一遍。

## 用法

写新 prep 时：先按 `docs/sequences/30s-two-part.md`（或 15s 单段）定能量骨架 → 逐镜
挑卡 → 读卡的「画面核心」直接抄进 spec 的 `desc` → 对照「已知坑」自检 → 跑
`node tools/check_dialogue.mjs`（0 ERROR）+ `python tools/check_collision.py`（0 撞车）。

## 卡片清单

| 卡 | 用在 | 关键作用 |
|---|---|---|
| `cold-open-05s.md` | 镜1 起手 | 0.5s 大特写钩子 |
| `confront-block.md` | 镜1 | 张臂横挡立靶子（对抗起点） |
| `seat-slap-contempt.md` | 镜1-2 | 拍产品轻蔑 → 主角拨开（第一轮对撞） |
| `bet-with-fingers.md` | 镜2 | 当众下注（赌约引擎） |
| `self-verify-sit.md` | 镜3 | 质疑者亲自验证（反转） |
| `gawk-shock-beat.md` | 镜3-4 | 瞪眼张嘴反应拍（爽感交付） |
| `narrow-squeeze-park.md` | 镜3 | 窄缝泊车（空间精度可视化） |
| `brand-line-to-lens.md` | 镜4 | 品牌句看镜头（唯一一次） |

## 加新卡的规矩

1. **必须有已拍成片背书**（除标注"待验证"的新卡）—— 没出过片的写法不进卡库。
2. 「已知坑」写**实测现象 + 改法**，不写"要注意"这类空话。
3. 每条卡都要有「参考成片」指向 `out/approved/` 里的具体文件。
