"""爆款逻辑模式库 — 钩子/结构/CTA/热点绑定策略

用途：
  1. gen_script（从热点生成脚本）→ 注入模式提示词
  2. templates.adapt_lines（模板台词热点融入）→ 提供改写方向
  3. 新模板创作（从爆款逻辑生成新脑洞）
"""

# ── 开场钩子库（前3秒抓人） ────────────────────────────────
HOOKS = {
    "conflict": {
        "name": "冲突质问",
        "template": "一句质问/反驳开场，直接进入对抗（'妈！这车你还敢骑？'）",
        "when": "家庭关系类脚本首选",
    },
    "number": {
        "name": "数字冲击",
        "template": "用一个反差数字砸开（'13.8公斤，也就一桶水的重量'）",
        "when": "产品参数差异化时",
    },
    "suspense": {
        "name": "悬念钩子",
        "template": "半句话吊住（'千万别让我妈看到这个…'/'你要换车？先看完这条'）",
        "when": "泛流量场景",
    },
    "counterintuitive": {
        "name": "反常识",
        "template": "打破常理（'谁说轮椅又重又笨？'/'几十斤的铁架子，他一只手拎起来了'）",
        "when": "对比实验类",
    },
    "painpoint": {
        "name": "痛点直击",
        "template": "戳真实痛点（'我妈摔过那一次之后……'/'推过旧轮椅的都知道，那叫一个沉'）",
        "when": "情感场景类",
    },
    "contrast": {
        "name": "对比反差",
        "template": "前后画风突变（'以前我爸出门是这个画风'→换车后）",
        "when": "反差王者类",
    },
    "question": {
        "name": "路人疑惑",
        "template": "第三方视角发问（'哎，这就折上了？'）",
        "when": "路人三连类",
    },
}

# ── 洗脑结构库 ────────────────────────────────────────────
BRAINWASH = {
    "triple_repeat": {
        "name": "三连重复",
        "template": "同一动作/句式重复3次，节奏逐次加速（折叠：咔·咔·咔）",
    },
    "parallel_progress": {
        "name": "同句式递进",
        "template": "'一次…两次…三次…'或'你不信？—你看—你再看看'",
    },
    "beat_sync": {
        "name": "卡点节奏",
        "template": "对白/动作与音效卡点（每次折叠卡在鼓点上）",
    },
}

# ── CTA 结尾库（行动引导，禁硬广腔） ────────────────────────
CTAS = {
    "try_invite": {
        "name": "试驾邀请",
        "template": "'你先试试，折叠，塞后备箱。'（把决定权交给对方）",
    },
    "question_echo": {
        "name": "反问收尾",
        "template": "'十三点八公斤，你说呢？'（反问把卖点变成对方结论）",
    },
    "warm_daily": {
        "name": "日常陪伴",
        "template": "'能装，能拎，更能陪。'（情感落点收尾）",
    },
    "understatement": {
        "name": "轻描淡写",
        "template": "'反正我妈现在天天自己折着放后备箱。'（不吆喝，说事实）",
    },
}

# ── 热点绑定策略（四层从强到弱） ────────────────────────────
HOT_BINDING = [
    ("台词级", "热点话题写进开场冲突句/对白（最强，自然融入）", ["社会话题", "民生政策", "家庭梗"]),
    ("道具级", "热点元素作道具（年货/露营装备/开学行李塞后备箱）", ["节日", "节气", "时令"]),
    ("标题级", "发布标题+话题标签绑热点（不进画面）", ["娱乐梗", "明星热点", "赛事"]),
    ("不绑定", "热点与产品无关时放弃绑定，走常青内容（别硬蹭）", ["敏感话题", "负面新闻"]),
]

# ── 对标拆解模板 ──────────────────────────────────────────
BENCHMARK_TEMPLATE = """对标拆解框架（分析同行爆款时用）：
1. 开场钩子类型？（冲突/数字/悬念/反常识/痛点）
2. 前3秒给了什么信息？（人物关系+矛盾+悬念）
3. 中段节奏？（几秒一个转折/情绪点）
4. 产品出现时机？（第几秒，怎么出——动作带出而非口播介绍）
5. 结尾CTA类型？（试驾邀请/反问/日常陪伴）
6. 可复用点？可差异化点？（避免抄袭，学结构不学台词）"""


def hook_hint(hot_type: str = "") -> str:
    """按热点类型推荐钩子"""
    if "家庭" in hot_type or "情感" in hot_type:
        return HOOKS["conflict"]["template"]
    if "参数" in hot_type or "科技" in hot_type:
        return HOOKS["number"]["template"]
    return HOOKS["suspense"]["template"]


def patterns_prompt_block() -> str:
    """生成注入 LLM 的爆款逻辑提示词块"""
    hooks = "\n".join(f"- {v['name']}：{v['template']}（适用：{v['when']}）"
                      for v in HOOKS.values())
    brain = "\n".join(f"- {v['name']}：{v['template']}" for v in BRAINWASH.values())
    ctas = "\n".join(f"- {v['name']}：{v['template']}" for v in CTAS.values())
    binding = "\n".join(f"- {lvl}：{desc}" for lvl, desc, _ in HOT_BINDING)
    return f"""【爆款逻辑库（生成时主动选用）】

开场钩子（必选其一，前3秒）：
{hooks}

洗脑结构（脑洞类脚本建议启用）：
{brain}

结尾CTA（禁硬广腔，选其一）：
{ctas}

热点绑定层级（从强到弱，选最自然的）：
{binding}

铁律：钩子/结构/CTA 都是服务"真实感"的——宁可朴素真实，不要假大空广告腔。"""


if __name__ == "__main__":
    print(patterns_prompt_block())
