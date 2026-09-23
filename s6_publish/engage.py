"""评论/私信维护：读评论 → 分类 → 生成回复 → 回复（默认演练）

三条红线转人工（绝不自动回复）：
  ① 价格/优惠/发票/购买链接
  ② 医疗类（能不能治/康复效果）
  ③ 投诉/退款/差评

用法：
    python s6_publish/engage.py --demo                    # 分类自检（免费）
    python s6_publish/engage.py --comments instagram --post-id xxx   # 读评论+判定（演练）
    python s6_publish/engage.py --comments instagram --post-id xxx --yes  # 真回复
    python s6_publish/engage.py --dms --yes               # IG 私信维护
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.llm import chat
from lib.state import connect

# 红线关键词（中文+英文）
RED_LINES = {
    "price": ["价格", "多少钱", "优惠", "折扣", "便宜", "发票", "购买", "链接", "下单",
              "price", "cost", "buy", "discount", "order"],
    "medical": ["治疗", "治好", "康复", "病症", "医用", "疗效", "病人能用吗",
                "treat", "cure", "medical", "therapy"],
    "complaint": ["投诉", "退款", "退货", "差评", "骗子", "举报",
                  "refund", "complaint", "scam", "cheat"],
}
SPAM_MARKERS = ["加v", "加微信", "私聊我", "推广", "刷粉", "兼职", "http", "www.",
                "telegram.me", "t.me/"]

# 产品卖点（回复用，绝不编造）
PRODUCT_POINTS = """爱优护轻便侠218电动轮椅：
- 一键自动折叠，单手可拎（约20kg）
- 折叠后可放进汽车后备箱
- 适合老人日常出行、公园遛弯
- 详情可以看看我主页"""


def classify(text: str) -> tuple[str, str]:
    """分类：normal / spam / escalate_price / escalate_medical / escalate_complaint"""
    t = text.lower()
    for marker in SPAM_MARKERS:
        if marker in t:
            return "spam", marker
    for kind, words in RED_LINES.items():
        for w in words:
            if w in t:
                return f"escalate_{kind}", w
    return "normal", ""


def gen_reply(text: str, context: str = "comment") -> str:
    """生成回复（顾问语气，1-2句）"""
    system = f"""你在运营抖音/Instagram上的电动轮椅产品号（品牌：爱优护）。

产品信息（只能基于这个说，绝不编造参数）：
{PRODUCT_POINTS}

回复规则：
- 口语化中文（对方用英文则回英文），1-2句，不用"您好""亲"
- 夸赞 → 感谢+一句有信息量的延伸
- 提问 → 基于产品真实卖点回答
- 不谈价格、不承诺疗效、不主动推销
- 不要说"最"字（广告法）"""
    try:
        return chat([
            {"role": "system", "content": system},
            {"role": "user", "content": f"粉丝评论：{text}"},
        ], temperature=0.7, max_tokens=1500).strip()
    except Exception as e:
        return f"[生成失败: {str(e)[:50]}]"


def already_handled(comment_id: str) -> bool:
    """幂等查重"""
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM interactions WHERE comment_id = ?",
            (str(comment_id),)).fetchone()
        return row is not None


def record(platform: str, post_id: str, comment_id: str, comment: str,
           commenter: str, status: str, reply: str = None):
    """记录互动"""
    with connect() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO interactions
            (platform, post_id, comment_id, comment_text, commenter, reply_text, reply_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (platform, str(post_id), str(comment_id), comment, commenter, reply, status))
        conn.commit()


def handle_comments(platform: str, post_id: str = None, post_url: str = None,
                    yes: bool = False, limit: int = 30) -> dict:
    """处理评论（默认演练）"""
    from s6_publish import uploadpost

    print(f"📖 拉取评论 {platform}...", flush=True)
    result = uploadpost.comments(platform, post_id=post_id, post_url=post_url, limit=limit)
    comments = result.get("comments") or []
    print(f"  共 {len(comments)} 条", flush=True)

    stats = {"total": len(comments), "replied": 0, "escalated": 0,
             "spam": 0, "skipped": 0, "dry": 0}

    for c in comments:
        cid = str(c.get("id") or c.get("comment_id") or "")
        text = str(c.get("text") or c.get("message") or "")
        who = (c.get("user") or {}).get("username") or c.get("username") or "?"

        # 自己发的跳过
        if c.get("from_self") or c.get("is_owner"):
            continue
        # 幂等
        if cid and already_handled(cid):
            stats["skipped"] += 1
            continue

        kind, hit = classify(text)
        if kind == "spam":
            print(f"    [spam] @{who}: {text[:40]}", flush=True)
            record(platform, post_id or post_url, cid, text, who, "spam")
            stats["spam"] += 1
            continue

        if kind.startswith("escalate"):
            print(f"    [转人工] @{who}: {text[:40]}（命中: {hit}）", flush=True)
            record(platform, post_id or post_url, cid, text, who, "escalated")
            stats["escalated"] += 1
            continue

        # 生成回复
        reply = gen_reply(text)
        if not yes:
            print(f"    (演练) @{who}: {text[:30]} → {reply[:50]}", flush=True)
            stats["dry"] += 1
            continue

        try:
            uploadpost.create_comment(platform, reply,
                                      post_id=post_id, post_url=post_url,
                                      comment_id=cid if platform == "instagram" else None)
            record(platform, post_id or post_url, cid, text, who, "replied", reply)
            print(f"    ✓ 已回 @{who}", flush=True)
            stats["replied"] += 1
        except Exception as e:
            print(f"    ✗ 回复失败 @{who}: {str(e)[:60]}", flush=True)
            record(platform, post_id or post_url, cid, text, who, "pending", reply)
            stats["skipped"] += 1

    return stats


def handle_dms(yes: bool = False) -> dict:
    """IG 私信维护"""
    from s6_publish import uploadpost

    print("📬 读取 IG 私信会话...", flush=True)
    result = uploadpost.dm_conversations("instagram")
    convs = result.get("conversations") or []
    print(f"  共 {len(convs)} 个会话", flush=True)

    stats = {"total": len(convs), "replied": 0, "escalated": 0, "dry": 0}
    for conv in convs[:20]:
        msgs = conv.get("messages") or []
        if not msgs:
            continue
        last = msgs[-1]
        sender = (last.get("from") or {}).get("username") or ""
        text = last.get("message") or ""
        recipient_id = (last.get("from") or {}).get("id")

        # 最后一条是我方发的 → 无需回复
        if str(recipient_id) == str(conv.get("id", "")):
            continue

        kind, hit = classify(text)
        if kind.startswith("escalate"):
            print(f"    [转人工] {sender}: {text[:40]}", flush=True)
            stats["escalated"] += 1
            continue
        if kind == "spam":
            continue

        reply = gen_reply(text, context="dm")
        if not yes:
            print(f"    (演练) {sender}: {text[:30]} → {reply[:40]}", flush=True)
            stats["dry"] += 1
            continue

        try:
            uploadpost.dm_send(str(recipient_id), reply)
            print(f"    ✓ 已回私信 {sender}", flush=True)
            stats["replied"] += 1
        except Exception as e:
            print(f"    ✗ 私信失败 {sender}: {str(e)[:60]}", flush=True)

    return stats


def demo() -> int:
    """分类自检（不调 API）"""
    tests = [
        ("这个轮椅多少钱？", "escalate_price"),
        ("能治腿脚不便吗", "escalate_medical"),
        ("我要退款！", "escalate_complaint"),
        ("加微信了解更多", "spam"),
        ("奶奶用这个好方便啊", "normal"),
        ("how much does it cost?", "escalate_price"),
        ("My grandma loves it!", "normal"),
    ]
    ok = 0
    for text, expect in tests:
        kind, hit = classify(text)
        match = "✓" if kind == expect else "✗"
        if kind == expect:
            ok += 1
        print(f"  {match} [{kind}] {text[:40]}")
    print(f"\n{demo.__name__}: {ok}/{len(tests)} 通过")
    return 0 if ok == len(tests) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="评论/私信维护")
    parser.add_argument("--demo", action="store_true", help="分类自检")
    parser.add_argument("--comments", help="平台名（instagram/youtube/facebook/tiktok）")
    parser.add_argument("--post-id", help="帖子ID")
    parser.add_argument("--post-url", help="帖子URL")
    parser.add_argument("--dms", action="store_true", help="IG 私信维护")
    parser.add_argument("--yes", action="store_true", help="真回复（默认演练）")
    args = parser.parse_args()

    if args.demo:
        return demo()

    if args.comments:
        stats = handle_comments(args.comments, post_id=args.post_id,
                                post_url=args.post_url, yes=args.yes)
        print(json.dumps(stats, ensure_ascii=False))
        return 0

    if args.dms:
        stats = handle_dms(yes=args.yes)
        print(json.dumps(stats, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
