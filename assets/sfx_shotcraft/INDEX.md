# 短剧音效包（来源：video-shotcraft · Mixkit Free License 免署名可商用）

> 由 `tools/import_shotcraft_sfx.py` 从 https://github.com/Vincentwei1021/video-shotcraft 引入。
> 30 个音效，逐文件授权 URL 见源库 `assets/audio/ATTRIBUTION.md`。
> **已剔除** 源库自认「无法反查、商用前须确认」的 5 个音（keyboard / pop / riser-cine / sparkle / whoosh-big）。
> ayh-mj 原有 3 个音效（`assets/sfx/{ding,whoosh,pop}.mp3`）继续可用，本包是扩充。

## 用法

```bash
# 单条配音效（配合台词时间轴）
python tools/audio_polish.py --bgm "assets/bgm_trending/xx.mp3" --sfx --transcripts <json>
# 手挑音效（钉点写入 audio_polish 的 cue 表）
```

## 用途映射

| 类别 | 文件 | 用途 | 建议钉点 |
|---|---|---|---|
| `impact/` | `hit-blow.mp3` | 打脸/耳光/撞击（全片最强一拍） | 对手被打脸那帧、动作落地那一刻 |
| `impact/` | `impact-cine-big.mp3` | 重击强调（大反转落定） | 底牌亮出、车纹丝不动那帧 |
| `impact/` | `impact-movie-epic.mp3` | 震撼收尾（碾压一句） | 品牌句前 1 句落点 |
| `impact/` | `hit-fast-exciting.mp3` | 兴奋快击（嘴硬/抢话） | 对手嚷话起句 |
| `impact/` | `metal-spring-hit.mp3` | 弹簧金属（减震/顶起） | 车身上抬、减震被压那帧 |
| `impact/` | `stomp-apocalyptic.mp3` | 脚步重踩（走近/压场） | 对手跨步逼近、一屁股坐下 |
| `impact/` | `bass-hit-short.mp3` | 低频重音（短促强调） | 切镜点 |
| `crowd/` | `clap-single.mp3` | 单人鼓掌（围观认可） | 旁观者服气那拍 |
| `crowd/` | `applause-rhythmic-loop.mp3` | 节奏掌声（人群哄笑/围观） | 当众打脸后 1s，音量压 0.25 |
| `crowd/` | `heartbeat-single.mp3` | 心跳（紧张/悬着） | 赌注抛出的那 0.5s |
| `transition/` | `sweep-fast.mp3` | 快扫转场（主用） | 每处硬切点 |
| `transition/` | `sweep-short.mp3` | 短扫转场（轻） | 镜内信息翻转 |
| `transition/` | `air-woosh-quick.mp3` | 快速空气呼啸 | 车快速驶过/拉镜 |
| `transition/` | `air-woosh-deep.mp3` | 低沉呼啸（预感） | 底牌揭晓前 0.3s |
| `transition/` | `air-whoosh-powerful.mp3` | 强风呼啸（大招） | 碾压动作起势 |
| `transition/` | `wind-swoosh-short.mp3` | 短风声（轻快） | 密集来回对话之间 |
| `ui/` | `switch-click-quick.mp3` | 按键（操纵杆/开关） | 拨调速档、按键那帧 |
| `ui/` | `ui-success-soft.mp3` | 成功确认音 | 验证成功、数字落定 |
| `ui/` | `chime-crystal.mp3` | 水晶铃（揭示） | 屏显数字、电量亮相 |
| `mech/` | `gear-lock-metallic.mp3` | 机械锁扣（折叠锁定） | 折叠卡扣合上那帧 |
| `mech/` | `machine-activate-short.mp3` | 机械启动（电机通电） | 车启动、坐上去那刻 |
| `mech/` | `lock-quick.mp3` | 快锁声 | 折叠到位 |
| `mech/` | `mech-tech-movement.mp3` | 机械运动（电机行进） | 车长距离移动（低音量铺底） |
| `light/` | `sparkle-touch.mp3` | 闪光（sparkle） | 强调点、字幕弹跳 |
| `light/` | `stardust-swish.mp3` | 星尘扫过 | 转场加亮 |
| `glass/` | `glass-hit-cine.mp3` | 玻璃紧张音（悬念） | 赌注/上屏悬念那拍 |
| `fluid/` | `water-splash.mp3` | 水花（满杯水验证） | 水晃动、过坎瞬间 |
| `counter/` | `clock-tick-single.mp3` | 钟表滴答（倒计时） | 限时验证 |
| `counter/` | `countdown-bleeps.mp3` | 倒计时哔 | 倒计时 3-2-1 |
| `film/` | `vinyl-scratch-small.mp3` | 黑胶刮擦（转场定格） | 硬切/闪回 |

## 选音三原则（承自 video-shotcraft sound-design）

1. **画面真有点击/开关就该配拟音**——不能整目录放行，每个音要试听后再钉。
2. **一个动作一个音**：同一帧不叠两个 impact（会糊成噪音）。
3. **音量分层**：impact 0.6-0.8 / transition 0.35-0.5 / mech 铺底 0.15-0.25 / crowd 0.2-0.3。
