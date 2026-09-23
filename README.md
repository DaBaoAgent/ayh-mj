# ayh-mj — 轻便侠·AI视频工厂

电动轮椅软广视频全自动生产系统：从热点爆款 → 文案脚本 → 分镜 → H3视频生成 → 合成烧字幕 → 9平台发布 → 评论互动，10-20秒抖音爆款成片。

## 目录结构

```
ayh-mj/
├── README.md                 # 本文件
├── config/
│   └── pipeline.yaml         # 流水线配置（API密钥引用、发布账号、风控参数）
├── lib/                      # 公共库
│   ├── __init__.py
│   ├── state.py              # SQLite 状态管理
│   ├── llm.py                # DeepSeek Flash 接口
│   ├── tools.py              # ffmpeg/ffprobe 等工具定位
│   └── pacing.py             # 发布节奏控制
├── s1_trend/                 # 阶段1：热点爆款抓取
│   ├── __init__.py
│   ├── douyin_hot.py         # 抖音热榜
│   ├── competitor.py         # 同行对标账号
│   └── keyword_search.py     # 关键词搜索
├── s2_copy/                  # 阶段2：爆款文案生成
│   ├── __init__.py
│   ├── analyze.py            # 爆款分析
│   └── gen_script.py         # 软广脚本生成
├── s3_storyboard/            # 阶段3：智能分镜
│   ├── __init__.py
│   ├── split.py              # 脚本拆分镜头
│   └── match_product.py      # 产品图匹配
├── s4_generate/              # 阶段4：H3视频生成
│   ├── __init__.py
│   ├── autodl_client.py      # AutoDL API 客户端
│   └── batch_gen.py          # 批量生成
├── s5_compose/               # 阶段5：合成烧字幕
│   ├── __init__.py
│   ├── tts.py                # edge-tts 配音
│   ├── subtitle.py           # 字幕生成
│   └── merge.py              # ffmpeg 合成
├── s6_publish/               # 阶段6：发布互动
│   ├── __init__.py
│   ├── postflow.py           # 国内3平台（抖音/小红书/视频号）
│   ├── uploadpost.py         # 海外6平台
│   └── engage.py             # 评论/私信互动
├── webui/                    # 可视化控制台
│   ├── server.py             # FastAPI 后端
│   ├── static/
│   │   ├── style.css
│   │   └── app.js
│   └── templates/
│       └── index.html
├── tools/
│   ├── run_all.py            # 全流程引擎（唯一执行入口）
│   ├── bootstrap.py          # 一键部署
│   └── cron/                 # 定时任务脚本
├── assets/
│   ├── products/             # 产品图（白底参考图）
│   └── templates/            # 分镜模板
├── state/                    # 运行状态（不进git）
├── out/                      # 成片输出（不进git）
└── logs/                     # 日志（不进git）
```

## 快速开始

```bash
# 1. 克隆并进入目录
git clone https://github.com/DaBaoAgent/ayh-mj && cd ayh-mj

# 2. 一键部署
python tools/bootstrap.py --check   # 先体检
python tools/bootstrap.py           # 补齐依赖

# 3. 启动控制台
python webui/server.py
# → http://127.0.0.1:8899
```

## 6阶段流水线

| 阶段 | 功能 | 接入服务 |
|---|---|---|
| s1_trend | 抓热点爆款 | 抖音Web API |
| s2_copy | 生成软广文案 | DeepSeek Flash |
| s3_storyboard | 智能分镜 | DeepSeek + 模板 |
| s4_generate | H3视频生成 | AutoDL API |
| s5_compose | 合成烧字幕 | edge-tts + ffmpeg |
| s6_publish | 9平台发布 | PostFlow + Upload-Post |

## 产品线

- **轻便侠218电动轮椅**（爱优护品牌）
- 白底参考图：`轻便侠218白底参考图/`
- 主图参数：`轻便侠218主图参数卖点/`

## 成本预估

| 项 | 单价 | 日均 | 月成本 |
|---|---|---|---|
| AutoDL H3 768p | ¥0.06/秒 | 300秒 | ¥540 |
| 火山Seedream | ¥0.04/张 | 120张 | ¥144 |
| DeepSeek Flash | ¥0.0001/token | 50万 | ¥50 |
| **合计** | | | **~¥750** |

## 凭据（不进仓库）

```bash
# DeepSeek
setx DEEPSEEK_API_KEY "sk-xxx"

# AutoDL
setx AUTODL_API_KEY "xxx"

# Upload-Post（海外发布）
python -c "import keyring;keyring.set_password('uploadpost','api_key','xxx')"
```

## License

MIT
