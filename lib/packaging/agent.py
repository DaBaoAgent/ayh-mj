"""PackagingAgent（Phase 10）—— 每条 READY 视频的发布物料。

对应计划 §Phase 10「PackagingAgent 输出」：
  ① 3 个标题候选 + 最终选择与理由；
  ② 封面文案 / 首帧策略；
  ③ description；
  ④ hashtags；
  ⑤ 首评候选；
  ⑥ 引用的 claim_ids；
  ⑦ `ai_generated` 与每平台声明需求；
  ⑧ 发布目标平台、时间窗与模式（direct / draft / require_human）。

为什么是**确定性模板**而不是再调一次 LLM：发布文案只允许复用 CreativeDNA 里
已经过合规门的那套创意词（audience / sales_point / payoff / angle / conflict_type），
凭空让 LLM 再写一段，就等于在最后一公里重新引入未登记的产品表述风险。
三个候选分别来自三种**不同角度**（问句钩子 / 卖点直给 / 场景收尾），
选择理由是可复核的加权打分（权重是模块常量），不是"模型觉得好"。
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from .platforms import policy_for

TITLE_ANGLES = ("hook_question", "benefit", "scene")

# 标题打分权重（唯一声明处；改这里就改全链）
W_SALES = 0.30        # 卖点是否出现在标题里
W_HOOK = 0.25         # 与片型偏好的标题角度是否一致
W_LEN = 0.20          # 长度是否适配（可用区间内得分最高）
W_NOVELTY = 0.15      # 与最近用过的标题的差异度
W_GAP = 0.10          # 是否留了好奇心缺口

# 片型 → 更有效的标题角度（工程先验；与 Phase 9 的片型表同一套 genre id）
GENRE_TITLE_PREF = {
    "G1": "benefit", "G2": "hook_question", "G3": "hook_question", "G4": "scene",
    "G5": "benefit", "G6": "hook_question", "G7": "benefit", "G8": "hook_question",
    "G9": "scene", "G10": "scene",
}

CURIOSITY = ("？", "?", "竟然", "居然", "没想到", "第一次", "到底")

COVER_MAX_CHARS = 12
DEFAULT_HASHTAG_CAP = 10


def _hash01(text: str, salt: str = "") -> float:
    digest = hashlib.sha256(f"{salt}:{text}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2 ** 32


def _doc_parts(spec_doc: dict | None) -> tuple[dict, dict, dict, list[str]]:
    """(dna, hotspot, story, lines) —— 兼容 Planner 落盘口径与裸 StorySpec。"""
    doc = spec_doc or {}
    story = doc.get("story_spec") or {}
    creative = doc.get("creative") or {}
    dna = creative.get("dna") or story.get("dna") or {}
    hotspot = doc.get("hotspot") or story.get("hotspot") or {}
    lines = [str(x.get("text") or "") if isinstance(x, dict) else str(x)
             for x in (story.get("lines") or [])]
    return dict(dna), dict(hotspot), dict(story), [ln for ln in lines if ln.strip()]


def claim_ids_of(spec_doc: dict | None) -> list[str]:
    """spec 里声明的 claim_ids（顶层 / creative / story_spec 三处合并，去重保序）。"""
    doc = spec_doc or {}
    story = doc.get("story_spec") or {}
    creative = doc.get("creative") or {}
    out: list[str] = []
    for src in (doc.get("claim_ids"), creative.get("claim_ids"), story.get("claim_ids")):
        for cid in (src or []):
            if str(cid) and str(cid) not in out:
                out.append(str(cid))
    return out


def _titles(dna: dict, hotspot: dict, story: dict, lines: list[str]) -> list[dict]:
    audience = str(dna.get("audience") or "家里长辈")
    sales = str(dna.get("sales_point") or "轻便好收")
    hook = str(dna.get("hook_type") or "")
    angle = str(dna.get("angle") or dna.get("narrative_arc") or "生活场景")
    conflict = str(dna.get("conflict_type") or "")
    payoff = str(dna.get("payoff") or "")
    ending = str(dna.get("ending") or "")
    scene = str(hotspot.get("title") or story.get("structure_name") or angle)
    first_line = lines[0] if lines else ""

    return [
        {"angle": "hook_question",
         "text": f"{audience}最在意的{sales}，到底怎么看？",
         "rationale": f"用提问把{hook or '钩子'}提前，制造好奇心缺口"},
        {"angle": "benefit",
         "text": f"{sales}这件事，{payoff or ending or '一个动作就说明白了'}",
         "rationale": "把卖点放在最前面，让不看完的人也记住一句"},
        {"angle": "scene",
         "text": f"{scene}：{conflict or first_line or '一个动作收住全场'}",
         "rationale": f"复述场景({angle})，让标题与画面互相解释"},
    ]


def _score(cand: dict, *, dna: dict, genre: str, platform_max: int,
           recent_titles: tuple[str, ...] = ()) -> tuple[float, list[str]]:
    text = str(cand["text"])
    sales = str(dna.get("sales_point") or "")
    parts: list[tuple[str, float]] = []

    sales_hit = bool(sales) and sales in text
    parts.append((f"卖点命中({'是' if sales_hit else '否'})", W_SALES if sales_hit else 0.0))

    pref = GENRE_TITLE_PREF.get(genre, "hook_question")
    hook_hit = cand["angle"] == pref
    parts.append((f"角度匹配{pref}({'是' if hook_hit else '否'})", W_HOOK if hook_hit else 0.0))

    n = len(text)
    if 8 <= n <= max(8, platform_max):
        len_score = W_LEN
        why = f"长度{n}适配"
    elif n < 8:
        len_score = W_LEN * 0.4
        why = f"长度{n}偏短"
    else:
        len_score = W_LEN * 0.2
        why = f"长度{n}超上限{platform_max}"
    parts.append((why, len_score))

    if recent_titles:
        worst = max(_similarity(text, prev) for prev in recent_titles)
        novelty = W_NOVELTY * (1.0 - worst)
        parts.append((f"与最近标题最高相似度{worst:.2f}", novelty))
    else:
        parts.append(("无历史标题可比", W_NOVELTY * 0.5))

    gap = any(tok in text for tok in CURIOSITY)
    parts.append((f"好奇心缺口({'有' if gap else '无'})", W_GAP if gap else 0.0))

    return round(sum(v for _, v in parts), 4), [f"{k} +{v:.3f}" for k, v in parts]


def _similarity(a: str, b: str) -> float:
    """字符 2-gram Dice 相似度（0..1）—— 只看"像不像"，不做语义判断。"""
    if not a or not b:
        return 0.0
    ga = {a[i:i + 2] for i in range(len(a) - 1)} or {a}
    gb = {b[i:i + 2] for i in range(len(b) - 1)} or {b}
    inter = len(ga & gb)
    return round(2 * inter / (len(ga) + len(gb)), 4)


def _cover(dna: dict, story: dict) -> dict:
    sales = str(dna.get("sales_point") or "轻便")
    genre = str(dna.get("genre") or "")
    shot = str(dna.get("shot_pattern") or "")
    motif = str(dna.get("visual_motif") or "")
    text = (sales + "，一眼看懂")[:COVER_MAX_CHARS]
    if genre in ("G3", "G8"):
        strategy = "首帧用夸张表情特写 + 大字，1 秒内交代冲突"
    elif genre in ("G5", "G9"):
        strategy = f"首帧用人物情绪特写（{motif or '暖光'}），标题只在下方留一行"
    elif shot in ("product_first", "product_test"):
        strategy = "首帧直接给产品动作定格（" + (motif or "产品全貌") + "）"
    else:
        strategy = "首帧停在钩子句对应的动作瞬间，人物与产品同框"
    return {"text": text, "first_frame": strategy}


def _description(dna: dict, story: dict, lines: list[str]) -> str:
    hook = str(dna.get("hook_type") or "")
    angle = str(dna.get("angle") or "")
    sales = str(dna.get("sales_point") or "")
    cta = str(dna.get("CTA") or "点开头像看看同款")
    body = [str(lines[0])] if lines else []
    head = f"{hook}｜{angle}" if hook or angle else "日常出行的一个小场景"
    mid = f"{sales}，看完这段就知道了" if sales else "看完这段就明白了"
    return "\n".join([head, *body, mid, cta])


def _hashtags(dna: dict, hotspot: dict, product_keywords: list[str]) -> list[str]:
    tags: list[str] = []
    for tag in (product_keywords or []):
        if tag and tag not in tags:
            tags.append(str(tag))
    genre = str(dna.get("genre") or "")
    genre_tags = {"G1": ["轻便出行"], "G2": ["生活小妙招"], "G3": ["搞笑日常"],
                  "G4": ["科普一下"], "G5": ["陪伴"], "G6": ["街头采访"],
                  "G7": ["生活记录"], "G8": ["沙雕日常"], "G9": ["反转剧情"],
                  "G10": ["实测"], "G11": ["母婴日常"]}
    for tag in genre_tags.get(genre, ["出行日常"]):
        if tag not in tags:
            tags.append(tag)
    for tag in ("适老化", "好物分享", "AI生成"):
        if tag not in tags:
            tags.append(tag)
    scene = str(hotspot.get("title") or "").strip()
    if scene and len(scene) <= 12 and scene not in tags:
        tags.append(scene)
    return tags


def _first_comments(dna: dict, story: dict) -> list[str]:
    audience = str(dna.get("audience") or "大家")
    sales = str(dna.get("sales_point") or "轻便")
    return [
        f"{audience}平时最在意哪一点？评论区说说",
        f"这段里{sales}的部分，要不要再拆细一点？",
    ]


def _mode_for(platform: str, *, ai_generated: bool, confirmable: dict) -> tuple[str, str]:
    """→ (mode, why)。mode ∈ direct | draft | require_human。"""
    policy = policy_for(platform)
    if policy is None:
        return "require_human", "未知平台，无法确认声明要求"
    if not ai_generated or not policy.requires_ai_disclosure:
        return "direct", "无需声明" if not policy.requires_ai_disclosure else "非 AI 生成"
    if confirmable.get(platform):
        return "direct", "声明已确认可程序化提交"
    if policy.supports_draft:
        return "draft", f"声明无法程序化确认 → 只上传草稿（{policy.draft_mechanism}）"
    return "require_human", "声明无法程序化确认，且该平台没有草稿通道"


def build_brief(spec_doc: dict | None, *, uid: str = "", platforms=("douyin",),
                ai_generated: bool = True, disclosure_confirmable: dict | None = None,
                product_keywords: list[str] | None = None, windows: list[dict] | None = None,
                mode: str | None = None, recent_titles: tuple[str, ...] = (),
                now: datetime | None = None) -> dict:
    """装配 packaging brief（纯函数，无 IO、无网络、无随机）。"""
    dna, hotspot, story, lines = _doc_parts(spec_doc)
    uid = uid or str((spec_doc or {}).get("job_uid") or story.get("uid") or "")
    genre = str(dna.get("genre") or "")
    confirmable = {k: bool(v) for k, v in (disclosure_confirmable or {}).items()}
    plats = [str(p) for p in (platforms or []) if str(p)]

    limits = [policy_for(p) for p in plats]
    platform_max = max([p.max_title_chars for p in limits if p] or [55])

    cands: list[dict] = []
    for cand in _titles(dna, hotspot, story, lines):
        score, why = _score(cand, dna=dna, genre=genre, platform_max=platform_max,
                            recent_titles=tuple(recent_titles or ()))
        cands.append({**cand, "score": score, "score_parts": why})
    chosen = max(cands, key=lambda c: (c["score"], -TITLE_ANGLES.index(c["angle"])))

    targets: list[dict] = []
    for platform in plats:
        policy = policy_for(platform)
        resolved, why = _mode_for(platform, ai_generated=ai_generated, confirmable=confirmable)
        if mode:                      # 显式指定（如强制演练/强制草稿）
            resolved = str(mode)
            why = f"显式指定 {mode}"
        targets.append({
            "platform": platform,
            "channel": policy.channel if policy else "unknown",
            "mode": resolved,
            "mode_reason": why,
            "requires_ai_disclosure": bool(policy.requires_ai_disclosure) if policy else True,
            "ai_disclosure_confirmable": bool(confirmable.get(platform)),
            "max_title_chars": policy.max_title_chars if policy else 55,
            "max_description_chars": policy.max_description_chars if policy else 1000,
            "max_hashtags": policy.max_hashtags if policy else DEFAULT_HASHTAG_CAP,
            "window": dict((windows or [{}])[0]) if windows else {},
        })

    tags = _hashtags(dna, hotspot, list(product_keywords or []))
    return {
        "uid": uid,
        "spec_version": str(story.get("spec_version") or ""),
        "title_candidates": cands,
        "title": chosen["text"],
        "title_angle": chosen["angle"],
        "title_reason": (f"选「{chosen['angle']}」({chosen['score']:.3f})：" +
                         "；".join(chosen["score_parts"])),
        "cover": _cover(dna, story),
        "description": _description(dna, story, lines),
        "hashtags": tags,
        "first_comment_candidates": _first_comments(dna, story),
        "claim_ids": claim_ids_of(spec_doc),
        "ai_generated": bool(ai_generated),
        "disclosure": {
            "required_by": [t["platform"] for t in targets if t["requires_ai_disclosure"]],
            "confirmable": {t["platform"]: t["ai_disclosure_confirmable"] for t in targets},
            "mode": {t["platform"]: t["mode"] for t in targets},
        },
        "targets": targets,
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
    }


def materialize(brief: dict, platform: str) -> dict:
    """把 brief 落成**某个平台**的最终发布文案（标题/描述/话题按上限裁剪）。"""
    targets = [t for t in (brief.get("targets") or []) if t.get("platform") == platform]
    if not targets:
        raise KeyError(f"brief 里没有 {platform} 这个发布目标")
    t = targets[0]
    title = str(brief.get("title") or "")
    if len(title) > t["max_title_chars"]:
        title = title[:max(1, t["max_title_chars"] - 1)] + "…"
    description = str(brief.get("description") or "")
    if len(description) > t["max_description_chars"]:
        description = description[:t["max_description_chars"]]
    tags = list(brief.get("hashtags") or [])[:t["max_hashtags"]]
    first_comment = (brief.get("first_comment_candidates") or [""])[0]
    return {
        "platform": platform,
        "title": title,
        "description": description,
        "hashtags": tags,
        "cover_text": str((brief.get("cover") or {}).get("text") or ""),
        "first_comment": first_comment,
        "mode": t["mode"],
        "draft_mechanism": (policy_for(platform).draft_mechanism
                            if policy_for(platform) else ""),
        "ai_generated": bool(brief.get("ai_generated")),
    }


# 必须"非空"的字段（claim_ids 不在此列：一条视频可以不引用任何 claim）
REQUIRED_FIELDS = ("title", "title_candidates", "cover", "description", "hashtags",
                   "first_comment_candidates", "ai_generated", "disclosure", "targets")


def validate(brief: dict | None) -> list[str]:
    """缺失/不完整字段清单（空列表 = 完整）。gate 拿它当"artifact 完整性"依据。"""
    if not isinstance(brief, dict):
        return ["packaging brief 缺失或不是对象"]
    problems: list[str] = []
    for key in REQUIRED_FIELDS:
        if key not in brief or brief[key] in (None, "", [], {}):
            problems.append(f"缺少字段 {key}")
    if not isinstance(brief.get("ai_generated"), bool):
        problems.append("ai_generated 必须是布尔（不能是 None/字符串）")
    if "claim_ids" not in brief or not isinstance(brief.get("claim_ids"), list):
        problems.append("claim_ids 必须是列表（可以为空，但不能缺）")
    if isinstance(brief.get("title_candidates"), list) and len(brief["title_candidates"]) < 3:
        problems.append(f"标题候选不足 3 个（实得 {len(brief['title_candidates'])}）")
    cover = brief.get("cover")
    if isinstance(cover, dict) and (not cover.get("text") or not cover.get("first_frame")):
        problems.append("cover 必须同时有 text 与 first_frame")
    if isinstance(brief.get("targets"), list):
        for t in brief["targets"]:
            if t.get("mode") not in ("direct", "draft", "require_human"):
                problems.append(f"目标 {t.get('platform')} 的 mode 非法：{t.get('mode')}")
    if not brief.get("title_reason"):
        problems.append("缺少最终标题的选择理由")
    return problems
