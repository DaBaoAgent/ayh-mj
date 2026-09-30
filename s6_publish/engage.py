"""评论/私信维护：读评论 → 分类 → 生成回复 → 回复（默认演练）

三条红线转人工（绝不自动回复）：
  ① 价格/优惠/发票/购买链接
  ② 医疗类（能不能治/康复效果）
  ③ 投诉/退款/差评

Phase 6：产品事实**只在** `assets/products/claims.yaml`（经 lib/claims.py 读取），
本文件不再内置任何参数文案；生成的回复还要过 Claims 合规门，不通过就转人工。

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

from lib import claims as claims_mod
from lib.console import enable_utf8_console
from lib.llm import chat
from lib.safety import EngageGuard
from lib.safety import load_state as load_engage_state
from lib.safety import save_state as save_engage_state
from lib.settings import get_settings
from lib.state import connect

enable_utf8_console()

# 红线关键词（中文+英文）
RED_LINES = {
    "price": ["价格", "多少钱", "优惠", "折扣", "便宜", "发票", "购买", "链接", "下单",
              "price", "cost", "buy", "discount", "order"],
    "medical": ["治", "康复", "病症", "医用", "疗效", "病人能用吗", "治疗",
                "treat", "cure", "medical", "therapy"],
    "complaint": ["投诉", "退款", "退货", "差评", "骗子", "举报",
                  "refund", "complaint", "scam", "cheat"],
}
SPAM_MARKERS = ["加v", "加微信", "私聊我", "推广", "刷粉", "兼职", "http", "www.",
                "telegram.me", "t.me/"]

ENGAGE_CHANNEL = "engage"

ROOT = get_settings().root


def build_guard() -> EngageGuard:
    """Phase 10 任务 10：限流/查重/熔断护栏（阈值来自 lib.settings.engage）。"""
    e = get_settings().engage
    return EngageGuard(
        load_engage_state(ROOT),
        max_per_hour=e.max_replies_per_hour,
        cooldown_seconds=e.reply_cooldown_seconds,
        jitter_seconds=e.reply_jitter_seconds,
        dup_window=e.duplicate_window,
        circuit_threshold=e.circuit_breaker_failures,
    )


def flush_guard(guard: EngageGuard) -> None:
    save_engage_state(ROOT, guard.state)


def product_facts(channel: str = ENGAGE_CHANNEL) -> str:
    """产品事实块 —— 唯一来源是 Claims Registry（Phase 6 任务 3/6）。

    旧版这里写死了 PRODUCT_POINTS（且把 13.8kg 写成"约20kg"），已删除：
    参数只允许有一个权威来源。
    """
    try:
        reg = claims_mod.load()
    except claims_mod.RegistryError as exc:      # 注册表坏了就别硬编
        return f"（产品事项目前不可用，禁止编造：{exc}）"
    return reg.facts_block(channel) or "（该渠道没有可用产品事实）"


def review_reply(reply: str, channel: str = ENGAGE_CHANNEL) -> tuple[bool, str]:
    """回复合规门：数值/认证/质保/疗效/绝对化表述必须映射到已登记且可用的 claim。"""
    if not str(reply or "").strip():
        return False, "空回复"
    try:
        result = claims_mod.gate(reply, channel)
    except claims_mod.RegistryError as exc:
        return False, f"claims 注册表不可用：{exc}"
    return (True, "") if result.ok else (False, result.message())


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
    facts = product_facts()
    brand = get_settings().product.brand
    system = f"""你在运营抖音/Instagram上的电动轮椅产品号（品牌：{brand}）。

产品信息（唯一来源：Claims Registry；只能基于这个说，绝不编造参数）：
{facts}

回复规则：
- 口语化中文（对方用英文则回英文），1-2句，不用"您好""亲"
- 夸赞 → 感谢+一句有信息量的延伸
- 提问 → 基于产品真实卖点回答
- 不谈价格、不承诺疗效、不主动推销
- 不要说"最"字（广告法）
- 不要报任何没在上面列出的数字（重量/续航/承重/尺寸/质保年限等）"""
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
             "spam": 0, "skipped": 0, "dry": 0, "blocked_claims": 0,
             "rate_limited": 0, "duplicate": 0, "circuit_open": False}
    guard = build_guard()

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
        ok, why = review_reply(reply)
        if not ok:
            print(f"    [转人工/合规] @{who}: {text[:30]}（{why[:80]}）", flush=True)
            if yes:
                record(platform, post_id or post_url, cid, text, who, "blocked_claims", reply)
            stats["blocked_claims"] += 1
            continue
        if not yes:
            print(f"    (演练) @{who}: {text[:30]} → {reply[:50]}", flush=True)
            stats["dry"] += 1
            continue

        allowed, why = guard.allow()
        if not allowed:
            print(f"    ⏸ 护栏拦下（{why}）", flush=True)
            stats["rate_limited"] += 1
            if "熔断" in why:
                stats["circuit_open"] = True
                break
            continue
        if guard.duplicate(reply, target=who):
            print(f"    ♻ 重复回复检测拦下 @{who}", flush=True)
            stats["duplicate"] += 1
            continue

        try:
            uploadpost.create_comment(platform, reply,
                                      post_id=post_id, post_url=post_url,
                                      comment_id=cid if platform == "instagram" else None)
            record(platform, post_id or post_url, cid, text, who, "replied", reply)
            guard.record_reply(reply, target=who)
            print(f"    ✓ 已回 @{who}", flush=True)
            stats["replied"] += 1
        except Exception as e:
            msg = str(e)[:120]
            print(f"    ✗ 回复失败 @{who}: {msg[:60]}", flush=True)
            record(platform, post_id or post_url, cid, text, who, "pending", reply)
            stats["skipped"] += 1
            if guard.record_failure(msg):
                print("    🛑 账号异常连续失败，已熔断，停止自动回复", flush=True)
                stats["circuit_open"] = True
                break

    flush_guard(guard)
    return stats


def handle_dms(yes: bool = False) -> dict:
    """IG 私信维护"""
    from s6_publish import uploadpost

    print("📬 读取 IG 私信会话...", flush=True)
    result = uploadpost.dm_conversations("instagram")
    convs = result.get("conversations") or []
    print(f"  共 {len(convs)} 个会话", flush=True)

    stats = {"total": len(convs), "replied": 0, "escalated": 0, "dry": 0,
             "blocked_claims": 0, "rate_limited": 0, "duplicate": 0,
             "circuit_open": False}
    guard = build_guard()
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
        ok, why = review_reply(reply)
        if not ok:
            print(f"    [转人工/合规] {sender}: {text[:30]}（{why[:80]}）", flush=True)
            stats["blocked_claims"] += 1
            continue
        if not yes:
            print(f"    (演练) {sender}: {text[:30]} → {reply[:40]}", flush=True)
            stats["dry"] += 1
            continue

        allowed, why = guard.allow()
        if not allowed:
            print(f"    ⏸ 护栏拦下（{why}）", flush=True)
            stats["rate_limited"] += 1
            if "熔断" in why:
                stats["circuit_open"] = True
                break
            continue
        if guard.duplicate(reply, target=sender):
            print(f"    ♻ 重复回复检测拦下 {sender}", flush=True)
            stats["duplicate"] += 1
            continue

        try:
            uploadpost.dm_send(str(recipient_id), reply)
            guard.record_reply(reply, target=sender)
            print(f"    ✓ 已回私信 {sender}", flush=True)
            stats["replied"] += 1
        except Exception as e:
            msg = str(e)[:120]
            print(f"    ✗ 私信失败 {sender}: {msg[:60]}", flush=True)
            if guard.record_failure(msg):
                print("    🛑 账号异常连续失败，已熔断，停止自动回复", flush=True)
                stats["circuit_open"] = True
                break

    flush_guard(guard)
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

    # Phase 6：产品事实来自 Claims Registry（不再内置），回复再过合规门
    facts = product_facts()
    print("\n  产品事实（Claims Registry / engage 渠道）：")
    for line in facts.splitlines():
        print("   ", line)
    gate_cases = [
        ("能上飞机，免费托运，推着上电梯", True),
        ("约20kg，单手可拎", False),          # 13.8kg 的禁用改写
        ("充一次跑39公里", False),             # 续航口径待核验
        ("能治疗腿脚不便", False),             # 医疗疗效
        ("销量第一", False),                   # 绝对化用语
    ]
    print("\n  回复合规门自检：")
    for text, expect in gate_cases:
        got, why = review_reply(text)
        match = "✓" if got == expect else "✗"
        if got == expect:
            ok += 1
        print(f"  {match} [gate={'pass' if got else 'block'}] {text[:36]}")
        if not got:
            print(f"        {why[:110]}")
    tests = list(tests) + gate_cases
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
