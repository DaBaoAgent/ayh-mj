"""工作流智能路由 — 按任务需求自动选最优工作流 + 失败切换链

路由维度：
  1. 需求匹配：图数（1图/多图/六图）/ 音频（音色克隆）/ 时长（1-10/11-15/12专属）/ 首尾帧 / 纯文生
  2. 质量档：draft(480p) / standard(768p) / premium(1080p)
  3. 失败切换：主工作流失败 → 按优先级链自动降级

价格参考：480p ¥0.04/s、768p ¥0.06/s、1080p ¥0.10/s（按输出秒数）

探测情报（2026-09-23 两轮实测）：
  · v5/zm_u08/zm_u24/v5_15s/no_pic/12s/首尾帧：prompt+duration(1-10或1-15)+ref_image_0 组合合法
  · image_audio_to_video（对口型）：**不接受 duration/resolution**，用 audio_duration（参数集不同）
  · z0903（六图三音频）：**ref_audio 需 WAV 格式**（mp3 报"文件类型不正确"）
  · z0902（六图）：ref_image_0 必填
  ⚠️ 探测血泪教训：参数探测时"回填合法值"是致命的——合法即提交。
     正确协议：每次请求必须携带至少一个非法 marker（-999/BAD_X），拿到范围立即停止。
"""
from __future__ import annotations

# ── 工作流能力矩阵（2026-09-23 探测 + 官方页面核验）────────────
WORKFLOW_SPECS = {
    # 多图参考系列
    "minimax_h3_lightx2v_v5": {
        "kind": "multi_image", "duration": (1, 10), "audio": False,
        "ref_images_max": 9, "tier": "standard", "pop_7d": "58.8k",
    },
    "minimax_h3_lightx2v_v5_15s": {
        "kind": "multi_image", "duration": (1, 15), "audio": False,
        "ref_images_max": 9, "tier": "standard", "pop_7d": "93.9k",
    },
    "minimax_h3_b99_003_12s": {
        "kind": "multi_image", "duration": (12, 12), "audio": False,
        "ref_images_max": 9, "tier": "standard", "pop_7d": "7.4k",
    },
    # 多图+音频（音色克隆）系列
    "minimax_h3_zm_u08": {
        "kind": "multi_image_audio", "duration": (1, 15), "audio": True,
        "ref_images_max": 9, "tier": "fast", "pop_7d": "14.2k",
    },
    "minimax_h3_zm_u24": {
        "kind": "multi_image_audio", "duration": (1, 15), "audio": True,
        "ref_images_max": 9, "tier": "hq", "pop_7d": "75.8k",
    },
    "minimax_h3_image_audio_to_video_v2": {
        "kind": "multi_image_audio", "duration": (1, 15), "audio": True,
        "ref_images_max": 9, "tier": "standard", "pop_7d": "11.1k",
    },
    "minimax_h3_image_audio_to_video_v2_15s": {
        "kind": "multi_image_audio", "duration": (1, 15), "audio": True,
        "ref_images_max": 9, "tier": "standard", "pop_7d": "99.6k",
    },
    "minimax_h3_image_audio_to_video": {
        "kind": "image_audio_lipsync", "duration": (1, 15), "audio": True,
        "ref_images_max": 1, "tier": "standard", "pop_7d": "3.0k",
    },
    # 六图系列（多角色一致性）
    "minimax_h3_z0902": {
        "kind": "six_image", "duration": (1, 10), "audio": False,
        "ref_images_max": 6, "tier": "standard", "pop_7d": "1.1k",
    },
    "minimax_h3_z0903": {
        "kind": "six_image_audio", "duration": (1, 10), "audio": True,
        "ref_images_max": 6, "tier": "standard", "pop_7d": "1.0k",
    },
    # 首尾帧
    "minimax_h3_lightx2v": {
        "kind": "first_last", "duration": (1, 10), "audio": False,
        "ref_images_max": 2, "tier": "standard", "pop_7d": "4.3k",
    },
    "minimax_h3_b99_002": {
        "kind": "first_last", "duration": (1, 10), "audio": False,
        "ref_images_max": 2, "tier": "standard", "pop_7d": "910",
    },
    # 文生视频
    "minimax_h3_lightx2v_no_pic": {
        "kind": "text2video", "duration": (1, 10), "audio": False,
        "ref_images_max": 0, "tier": "standard", "pop_7d": "16.7k",
    },
    "minimax_h3_b99_001": {
        "kind": "text2video", "duration": (1, 10), "audio": False,
        "ref_images_max": 0, "tier": "standard", "pop_7d": "753",
    },
    "minimax_h3_z0901": {
        "kind": "text2video", "duration": (1, 10), "audio": False,
        "ref_images_max": 0, "tier": "standard", "pop_7d": "403",
    },
}

# ── 失败切换链（同级优先换人气/稳定度高的）────────────────────
FALLBACK_CHAINS = {
    "minimax_h3_zm_u08": ["minimax_h3_zm_u24", "minimax_h3_image_audio_to_video_v2"],
    "minimax_h3_zm_u24": ["minimax_h3_zm_u08", "minimax_h3_image_audio_to_video_v2"],
    "minimax_h3_image_audio_to_video_v2": ["minimax_h3_zm_u08"],
    "minimax_h3_image_audio_to_video_v2_15s": ["minimax_h3_zm_u08", "minimax_h3_zm_u24"],
    "minimax_h3_lightx2v_v5": ["minimax_h3_lightx2v_v5_15s", "minimax_h3_b99_003_12s"],
    "minimax_h3_lightx2v_v5_15s": ["minimax_h3_lightx2v_v5"],
    "minimax_h3_b99_003_12s": ["minimax_h3_lightx2v_v5_15s"],
    "minimax_h3_lightx2v": ["minimax_h3_b99_002"],
    "minimax_h3_b99_002": ["minimax_h3_lightx2v"],
    "minimax_h3_lightx2v_no_pic": ["minimax_h3_b99_001", "minimax_h3_z0901"],
    "minimax_h3_b99_001": ["minimax_h3_lightx2v_no_pic"],
    "minimax_h3_z0901": ["minimax_h3_lightx2v_no_pic"],
    "minimax_h3_z0902": ["minimax_h3_lightx2v_v5"],
    "minimax_h3_z0903": ["minimax_h3_zm_u08"],
    "minimax_h3_image_audio_to_video": ["minimax_h3_zm_u08"],
}

# 质量档 → 分辨率
QUALITY_RESOLUTION = {
    "draft": "480p竖",
    "standard": "768p竖",
    "premium": "1080p竖",
}
QUALITY_RESOLUTION_H = {
    "draft": "480p横",
    "standard": "768p横",
    "premium": "1080p横",
}
PRICE_PER_SEC = {"480p": 0.04, "768p": 0.06, "1080p": 0.10}


def route(*, n_images: int = 0, has_audio: bool = False, duration: int = 5,
          first_last: bool = False, text_only: bool = False,
          quality: str = "standard", prefer_hq: bool = False) -> list[str]:
    """返回工作流优先级链（首选在前，含 fallback）

    n_images: 参考图数量；has_audio: 是否音色克隆；first_last: 首尾帧模式
    """
    chain: list[str] = []

    if first_last:
        chain = ["minimax_h3_lightx2v", "minimax_h3_b99_002"]
    elif text_only or n_images == 0:
        chain = ["minimax_h3_lightx2v_no_pic", "minimax_h3_b99_001"]
    elif has_audio:
        if duration > 10:
            chain = ["minimax_h3_image_audio_to_video_v2_15s", "minimax_h3_zm_u08"]
        elif prefer_hq:
            chain = ["minimax_h3_zm_u24", "minimax_h3_zm_u08"]
        else:
            chain = ["minimax_h3_zm_u08", "minimax_h3_zm_u24"]
    else:
        if n_images >= 5:
            chain = ["minimax_h3_z0902", "minimax_h3_lightx2v_v5"]
        elif duration == 12:
            chain = ["minimax_h3_b99_003_12s", "minimax_h3_lightx2v_v5_15s"]
        elif duration > 10:
            chain = ["minimax_h3_lightx2v_v5_15s", "minimax_h3_lightx2v_v5"]
        else:
            chain = ["minimax_h3_lightx2v_v5", "minimax_h3_lightx2v_v5_15s"]

    # 追加注册的 fallback（去重）
    for wf in list(chain):
        for fb in FALLBACK_CHAINS.get(wf, []):
            if fb not in chain:
                chain.append(fb)
    return chain


def resolution_for(quality: str = "standard", vertical: bool = True) -> str:
    return (QUALITY_RESOLUTION if vertical else QUALITY_RESOLUTION_H).get(quality, "768p竖")


def validate_chain(chain: list[str], duration: int, has_audio: bool) -> list[str]:
    """过滤链条：时长超范围 / 不支持音频的工作流剔除"""
    out = []
    for wf in chain:
        spec = WORKFLOW_SPECS.get(wf)
        if not spec:
            out.append(wf)  # 未知工作流不拦（用户显式指定）
            continue
        lo, hi = spec["duration"]
        if not (lo <= duration <= hi):
            continue
        if has_audio and not spec["audio"]:
            continue
        out.append(wf)
    return out or chain[:1]


def estimate_cost(duration: int, quality: str = "standard") -> float:
    res = resolution_for(quality)
    key = res[:res.index("p") + 1]
    return round(PRICE_PER_SEC.get(key, 0.06) * duration, 3)


if __name__ == "__main__":
    # 自检：典型场景
    cases = [
        ("4镜母子对白（音色克隆）", dict(n_images=3, has_audio=True, duration=4)),
        ("15s长镜头对白", dict(n_images=3, has_audio=True, duration=15)),
        ("高品质出片", dict(n_images=3, has_audio=True, duration=4, prefer_hq=True)),
        ("12s多图", dict(n_images=2, duration=12)),
        ("六图多角色", dict(n_images=6, duration=5)),
        ("首尾帧折叠", dict(n_images=2, first_last=True, duration=5)),
        ("纯文生", dict(text_only=True, duration=5)),
    ]
    for name, kw in cases:
        chain = route(**kw)
        q = kw.get("quality", "standard")
        cost = estimate_cost(kw.get("duration", 5), q)
        print(f"{name}:\n  → {' > '.join(chain)}\n  成本≈¥{cost}")
