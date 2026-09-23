# AutoDL H3 工作流矩阵（2026-09-23）

> 来源：autodl.art/large-model/comfyui 全量 17 条 + 两轮参数探测实测
> 引擎：`s4_generate/workflow_router.py`（自动路由+失败切换）

## 全清单（17 条，H3 家族 15 + 其他 2）

| workflow_id | 名称 | 类型 | 时长 | 音频 | 7天热度 |
|---|---|---|---|---|---|
| minimax_h3_zm_u24 | H3多图多音频(升级画质) | 多图+音频 | 1-15s | ✅ | 75.8k |
| minimax_h3_zm_u08 | H3多图多音频(高速版) | 多图+音频 | 1-15s | ✅ | 14.2k |
| minimax_h3_image_audio_to_video_v2_15s | H3多图多音频15秒 | 多图+音频 | 1-15s | ✅ | **99.6k（最热）** |
| minimax_h3_image_audio_to_video_v2 | H3多图多音频 | 多图+音频 | 1-15s | ✅ | 11.1k |
| minimax_h3_image_audio_to_video | H3图生视频-音频同步(对口型) | 单图+音频 | (audio_duration) | ✅ | 3.0k |
| minimax_h3_z0903 | H3六图三音频(高质量音画融合) | 六图+音频 | 1-10s | ✅（**需WAV**） | 1.0k |
| minimax_h3_z0902 | H3六图生视频(多图一致性) | 六图 | 1-10s | ❌ | 1.1k |
| minimax_h3_z0901 | H3文生视频(高质量创意) | 文生 | 1-10s | ❌ | 403 |
| minimax_h3_lightx2v_v5 | H3多图参考生视频 | 多图 | 1-10s | ❌ | 58.8k |
| minimax_h3_lightx2v_v5_15s | H3多图生视频15秒 | 多图 | 1-15s | ❌ | 93.9k |
| minimax_h3_b99_003_12s | H3多图生视频12秒 | 多图 | 12s | ❌ | 7.4k |
| minimax_h3_lightx2v | H3首尾帧生成视频 | 首尾帧 | 1-10s | ❌ | 4.3k |
| minimax_h3_b99_002 | H3首尾帧生成视频 | 首尾帧 | 1-10s | ❌ | 910 |
| minimax_h3_lightx2v_no_pic | H3文生视频 | 文生 | 1-10s | ❌ | 16.7k |
| minimax_h3_b99_001 | H3文生视频 | 文生 | 1-10s | ❌ | 753 |
| wan2.2animate-v4-motion_retargeting | 动作迁移 | 视频驱动 | - | ❌ | 1.8k（¥0.03-0.04/s 高峰/空闲） |
| indextts2-v1 | TTS | 文本→语音 | - | ✅ | 20.1k（¥0.001/s） |

## 价格（按分辨率，输出秒数计费）

| 分辨率 | 单价 |
|---|---|
| 480p | ¥0.04/秒 |
| 768p | ¥0.06/秒 |
| 1080p | ¥0.10/秒 |

（动作迁移/indextts2 单独计价如上表）

## 路由规则（workflow_router.route）

| 任务特征 | 首选 | 失败切换链 |
|---|---|---|
| 多图+音色克隆 ≤10s | zm_u08（高速） | zm_u24 → v2 |
| 多图+音色克隆 11-15s | v2_15s | zm_u08 → zm_u24 |
| 高品质模式 | zm_u24 | zm_u08 |
| 多图无音频 ≤10s | lightx2v_v5 | v5_15s → b99_003_12s |
| 多图无音频 11-15s | v5_15s | v5 |
| 恰好 12s | b99_003_12s | v5_15s |
| 六图（≥5 角色） | z0902 | lightx2v_v5 |
| 首尾帧 | lightx2v | b99_002 |
| 纯文生 | no_pic | b99_001 → z0901 |

## 参数结构（实测）

- **通用**：`{prompt, duration:int, resolution, ref_image_0..N}`（data URL 或公网 URL）
- **音色克隆**：+ `ref_audio_0`（mp3 OK；z0903 需 WAV）
- **对口型流**（image_audio_to_video）：**不接受 duration/resolution**，用 `audio_duration`
- **首尾帧流**：参数名是 `first_frame` / `last_frame`（不是 ref_image_0/1）
- 分辨率枚举：`480p竖/768p竖/1080p竖/480p横/768p横/1080p横`

## ⚠️ 探测安全铁律（血泪教训）

参数探测时"回填合法值"的那发请求 = **真实提交（扣费）**。
正确协议：每次请求必须携带至少一个非法 marker（-999 / BAD_X）；拿到信息立即停止。
两轮探测共误提交 9 个 probe 任务（代价约 ¥2.4）。
