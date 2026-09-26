# Higgsfield《Hell Grind》三件套接入说明

> 2026-09-26 宝哥令接入 ayh-mj 流水线
> 来源：Higgsfield 官方开源生产技能（95 分钟 AI 长片《Hell Grind》的提示词系统）
> 官方 Brief 页：https://higgsfield.ai/@higgsfield.studio/projects/hell-grind

## 一、三件套是什么

| 文件 | 体量 | 定位 |
|---|---|---|
| `LIRA SKILL.md` | 30KB / 619 行 | **图像层** —— `name: lira-image-prompts`，把任意输入变成可直接投产的图像提示词 |
| `CINEDANCE HIGGSFIELD SKILL.md` | 33KB / 1330 行 | **视频层** —— CINEDANCE V4，Seedance 2.0 / H3 的提示词导演系统 |
| `ACTING SKILL.md` | 26KB / 444 行 | **表演层** —— 表演是「压力下的行为」，不是情绪展示 |

原文 MD5（两个互不相关的镜像仓库逐字节一致，确认为官方原文）：

```
dbda9c9aaac7f12dfa7c11db797d27b1  LIRA SKILL.md
1ad963e23e869929b562e5a8609c1bd6  CINEDANCE HIGGSFIELD SKILL.md
070c75fc8e8a0bdc977de937a7fef983  ACTING SKILL.md
```

原文副本：`D:\@kaifa\higgsfield-hell-grind-skills\`
Hermes 技能：`media/lira-image-prompts` · `media/cinedance-seedance` · `media/acting-performance`

## 二、在 ayh-mj 里对应哪三个环节

```
① 人物定妆照  ←── LIRA      图像提示词：先诊断"这张图会怎么失败"，再针对性下锁
② 视频提示词  ←── CINEDANCE  镜头语言：FOV 度数 / 首帧占位 / 视线与身体朝向分开 / 光锁 / 物理锁
③ 表演系统    ←── ACTING     角色行为层：目标是动词、面具要有裂纹、眼神必须给任务
```

**代码落点**

| 文件 | 作用 |
|---|---|
| `lib/hellgrind.py` | 三件套接入层：`cast_prompt()` / `CINEDANCE_CONSTANTS` / `shot_block()` / `acting_block()` / `load_master()` / `tail_constants()` |
| `lib/prompt_parts.py` | `compose()` 新增两个可选参数：`cinedance=True`（拼电影语言总纲）、`acting=<文本>`（拼表演层）——默认关闭，向后兼容 |
| `tools/gen_cast_scene.py` | LIRA 环节正式入口：同一个人 + 新场景的全身定妆图（`--list` / `--dry`） |
| `assets/cast/acting/` | ACTING 表演主档案（`<角色id>.md`，永久源真相）+ 片专用场景改写版（`scene_<片>_<角色>.md`） |
| `assets/cast/scene/` | LIRA 出的场景版定妆图（按 `<角色>_<场景>_<片>.png` 命名，不覆盖通用库资产） |

**冲突处理铁律**：ayh-mj 的实测坑位（H3 能力边界 / SPEAKER LOCK / 产品三图铁律 / 10000 字符上限）
**优先于**三件套的通用规则；两者叠加时以 ayh-mj 为准。

## 三、三条实测纪律

### 1. H3 prompt 硬上限 10000 字符 → 三件套增量必须是「净零」

ayh-mj 原 spec 已经贴着上限（X1《一秒三折》= 9768 字符）。直接叠加
CINEDANCE(353) + ACTING(~1200) 会冲到 **12796 字符 → H3 提交前直接拒收**（服务端校验，未扣费）。

压缩招（按收益排序）：

| # | 招式 | 收益 |
|---|---|---|
| ① | 每镜 SPEAKER LOCK 压成 `SPEAKER LOCK — (S2) the grandpa only.`，规则本体放 CAST 段的全局 SPEAKER RULE | ~460 |
| ② | `compose(cold_open=False)`（镜 1 描述自带入场） | ~270 |
| ③ | WHEEL / extra_tail 与 CAST 段**去重**（CROWD RULE 曾两处都写） | ~170 |
| ④ | 场景改写版**去 Beats 行**（每镜已有 BEATS） | ~180 |
| ⑤ | 眼神细节只留一处（场景改写版 or `EYE_RULE`，用 `acting_block(eye=False)`） | ~386 |

实操：**任何新增约束都要先量 `len(prompt)`**，超 9800 就继续压。
`tools/prep_g5_jingdian.py` 已内置长度闸；`gen_one_take.py` 有代码级硬拦。

### 2. ACTING 主档案不进 prompt

- 主档案 150-220 词，写一次，存 `assets/cast/acting/<角色id>.md` —— 这是**永久源真相**
- 每条片取其**场景改写版** `scene_<片>_<角色>.md`（ACTING §8：改写而非粘贴）
- 改写规则：保留核心（身份/声线/招牌小动作/眼神/情绪主线），按本片换场景与节拍重写

### 3. 同性别配对必须验音色 f0 差 ≥ 60Hz

G5 首次 spec 用两个男声：

```
r09_adult_male  145.5 Hz
r12_elder_male  136.8 Hz   → 只差 8.7 Hz  ⚠️ H3 混音色危险区
```

改用 `r03_young_male`（225.4 Hz）→ 差 **88.6 Hz** ✅

音色库画像见 `assets/cast/voice/real/INDEX.md`（如 r03 = 青年男·孝顺（儿子/女婿），正好贴合语境）。
⚠️ 自相关 f0 估算有整数 lag 量化误差（会出现多个音色同值），**只看相对排序**。

## 四、首个全流程实例：G5《景点打卡》

**四池组合**：核心卡司组 / 卖点 `load_100` 承重100kg / 角度 `B11` 景点打卡 / 片型 `G5` 情感故事

**全流程命令**

```bash
cd D:/@kaifa/ayh-mj && PY=.venv/Scripts/python.exe

# ① 四池选组合
$PY tools/pick_combo.py --commit job_G5

# ② 台词 + 撞车检查（70 纯汉字，逐句 [12,9,8,8,8,8,11,6]，0 拦截）
$PY tools/check_collision.py docs/onetake_lines_G5_jingdian.txt

# ③ LIRA：同人换场景的定妆图
$PY tools/gen_cast_scene.py --role son,elder --scene jingdian --uid G5
$PY tools/ask_img.py assets/cast/scene/son_jingdian_G5.png --ch deepseek "是不是全身(含鞋子)…"

# ④ CINEDANCE + ACTING：一键组装 spec（自带长度闸 + 门禁）
$PY tools/prep_g5_jingdian.py --gate

# ⑤ 出片（H3 15s/768p，¥0.9，10-18 分钟）
$PY tools/make_15s.py run state/onetake_prompt_job_G5_jingdian.json
```

**台词（4 镜 8 句）**

| 镜 | 说话人 | 台词 | 功能 |
|---|---|---|---|
| 1 | 儿子 | 爸，这景点走下来得两万步呢。 | 劝阻（先抑） |
| 1 | 老王 | 怕啥，我又不是走不动。 | 反驳 |
| 2 | 儿子 | 不行了，我腿都软了。 | 体力崩溃 |
| 2 | 老王 | 你这才走了多远啊。 | 得意碾压 |
| 3 | 儿子 | 这车真能扛得住我？ | 质疑承重 |
| 3 | 老王 | 你放心，它载得动你。 | 承诺（承重靠画面演） |
| 4 | 儿子 | 爸，你比我这年轻人还利索。 | 泪点 |
| 4 | 老王 | 爱优护轻便侠。 | 品牌句（看镜头） |

**验收数据**：spec 9797 字符（安全线内）｜门禁 0 ERROR / 1 WARN（R26 体量经验值）｜
定妆照 2 张（elder 一次过；son 首版继承参考图的半截构图 → 加全身锁重出后含鞋达标）。

## 五、已知边界

- **R26 WARN 常驻**：本项目 spec 体量约 2500（中文按字、英文按 1/3 计），远超经验上限 400。
  这是历史既成事实（X1 同档），非本次引入；真要压到 400 需砍掉 CAST/约束段，会直接牺牲出片稳定性。
- **CINEDANCE 的长镜头语言与 H3 能力边界冲突时以 H3 为准**：H3 不擅长坡道/楼梯/动态失败/一镜多事件。
- **ACTING 的「Voice prompt 逐字锁定」在本仓的对应物就是参考音色样本**（`ref_audio_0/1/2`）。
