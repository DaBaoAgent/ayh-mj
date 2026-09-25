# Pixabay 真人素材候选网格（2026-09-25）

## 怎么用

每个文件 = 一张横排对比网格：
- **第 1 格**：原 AI 角色图（现有 library/*.png）
- **第 2-5 格**：Pixabay 真人照片候选（已按竖版/热门排序）

**挑选方式**：看到合适的，直接告诉我（例如「city_grandpa_75 选 2 号」），我把它设为该角色新参考图。

## 清单

| 网格文件 | 候选数 | 备注 |
|---|---|---|
| city_grandpa_75_候选网格.png | 4 | 亚裔男性、老人 |
| city_grandma_70_候选网格.png | 4 | 偏年轻（亚裔老年女素材少） |
| city_mom_45_候选网格.png | 4 | |
| city_young_man_30_候选网格.png | 4 | |
| fashion_granny_silver_候选网格.png | 4 | 银发（补搜词：silver hair woman） |
| fashion_girl_20_候选网格.png | 3 | |
| western_grandpa_70_候选网格.png | 4 | |
| western_young_woman_28_候选网格.png | 4 | |
| city_boy_10_候选网格.png | 4 | |
| fashion_gent_55_候选网格.png | 3 | |

## 说明

- **素材源**：Pixabay API（您的 key），搜索词见 `tools/gen_pixabay_cast.py`
- **局限**：Pixabay「亚裔老人」素材有限，部分候选在**年龄或人种上不完美**——真实感优先，若不合适可选：
  1. 换词再搜（告诉我想要的特征）
  2. 用 AI 照片级版（已生成 10 张在 `library_real/`）
  3. 混合使用（真人脸 + AI 服装/场景）
- **候选原图**：`assets/cast/pixabay/*.jpg`（未裁剪原尺寸）

## 相关

- 照片级 AI 版对比：`assets/cast/compare/`（10 张）
- 音色→角色映射表：`docs/音色-角色映射表-20260925.md`
