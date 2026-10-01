"""StorySpec 文案层：选题/卖点定稿后，先写完整台词，再允许编译付费 Prompt。

恢复 2026-09-26 稳定链的关键合同：双人 15 秒 = 4 镜 8 句、65–72 个纯汉字、
单句不超过 13 个汉字、无阿拉伯数字。vNext 可以有其它骨架，但任何需要文字的
片型都不能以空 lines 进入 PromptCompiler / AutoDL。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..llm import chat_json
from ..products import point_facts
from .compiler import CAPTION_MODES, SPEECH_MODES
from .structures import line_plan_for

DUO_MIN_CJK = 65
DUO_MAX_CJK = 72
SPEECH_MIN_CJK = 65
SPEECH_MAX_CJK = 72
MAX_LINE_CJK = 13


class StoryWritingError(RuntimeError):
    """文案缺失或不满足出片合同；必须在任何付费生成之前阻断。"""


@dataclass
class StoryDraft:
    title: str
    goal: str
    payoff: str
    ending: str
    cta: str
    lines: list[dict] = field(default_factory=list)
    shot_notes: list[str] = field(default_factory=list)
    source: str = "llm"


def cjk_count(text: str) -> int:
    return len(re.sub(r"[^\u4e00-\u9fff]", "", str(text or "")))


def needs_text(dialogue_mode: str) -> bool:
    return str(dialogue_mode or "") in SPEECH_MODES | CAPTION_MODES


def _slots(dna) -> list[str]:
    return [x for x in str(dna.cast_pattern or "").split("+") if x.strip()]


def _map_lines(raw: list, *, dna, structure: dict) -> list[dict]:
    plan = line_plan_for(str(structure.get("id") or ""))
    slots = _slots(dna) or ["S1"]
    rows: list[dict] = []
    pos = 0
    speaker_i = 0
    for shot, count in enumerate(plan, 1):
        for _ in range(count):
            item = raw[pos] if pos < len(raw) else ""
            text = str(item.get("text") if isinstance(item, dict) else item or "").strip()
            speaker = slots[speaker_i % len(slots)]
            rows.append({"shot": shot, "speaker": speaker, "text": text})
            pos += 1
            if dna.dialogue_mode in ("双人对白", "街访问答"):
                speaker_i += 1
    return rows


def validate_lines(lines: list[dict], *, dna, structure: dict) -> list[str]:
    mode = str(dna.dialogue_mode or "")
    plan = line_plan_for(str(structure.get("id") or ""))
    expected = sum(plan)
    problems: list[str] = []
    if not needs_text(mode):
        return problems
    if len(lines) != expected:
        problems.append(f"{mode} 应有 {expected} 句，实际 {len(lines)} 句")
    texts = [str(row.get("text") or "").strip() for row in lines]
    if any(not text for text in texts):
        problems.append("存在空台词或空字幕")
    counts = [cjk_count(text) for text in texts]
    if any(n > MAX_LINE_CJK for n in counts):
        problems.append(f"单句超过 {MAX_LINE_CJK} 个汉字：{counts}")
    if any(re.search(r"[0-9]", text) for text in texts):
        problems.append("台词含阿拉伯数字，需要改为中文读法")
    if any(re.search(r"[A-Za-z]", text) for text in texts):
        problems.append("台词夹英文或型号，需要改成中文说法")
    keys = [re.sub(r"\s+", "", text)[:12] for text in texts]
    if len(keys) != len(set(keys)):
        problems.append("存在重复台词，容易触发重复口播/重复表演")
    total = sum(counts)
    if mode == "双人对白" and structure.get("id") == "S_duo_conflict":
        if not (DUO_MIN_CJK <= total <= DUO_MAX_CJK):
            problems.append(f"4镜双人对白纯汉字 {total}，要求 {DUO_MIN_CJK}-{DUO_MAX_CJK}")
    elif mode in SPEECH_MODES and not (SPEECH_MIN_CJK <= total <= SPEECH_MAX_CJK):
        problems.append(f"15秒口播纯汉字 {total}，要求 {SPEECH_MIN_CJK}-{SPEECH_MAX_CJK}")
    slots = _slots(dna)
    if mode in ("双人对白", "街访问答") and len(slots) >= 2:
        expected_speakers = [slots[i % 2] for i in range(len(lines))]
        actual = [str(row.get("speaker") or "") for row in lines]
        if actual != expected_speakers:
            problems.append("双人对白说话人没有严格交替")
    return problems


def validate_draft(draft: StoryDraft, *, dna, structure: dict) -> list[str]:
    problems = validate_lines(draft.lines, dna=dna, structure=structure)
    if needs_text(dna.dialogue_mode) and len(draft.shot_notes) != int(structure.get("shots") or 0):
        problems.append("分镜描述数量与镜头数不一致")
    for name in ("title", "goal", "payoff", "ending"):
        if not str(getattr(draft, name) or "").strip():
            problems.append(f"{name} 为空")
    return problems


class StoryWriter:
    """把定稿 CreativeDNA 写成可直接送入旧版 one-take 合同的完整脚本。"""

    def __init__(self, *, attempts: int = 3) -> None:
        self.attempts = max(1, int(attempts))
    def write(self, *, hotspot: dict, dna, structure: dict, research: dict | None = None) -> StoryDraft:
        plan = line_plan_for(str(structure.get("id") or ""))
        if not needs_text(dna.dialogue_mode):
            topic = str((hotspot or {}).get("title") or dna.hotspot or "主题")
            return StoryDraft(title=topic[:28], goal=dna.goal, payoff=dna.payoff,
                              ending=dna.ending, cta=dna.CTA, lines=[],
                              shot_notes=[str(structure.get("directions") or "")] * int(structure.get("shots") or 0),
                              source="silent")

        expected = sum(plan)
        facts = point_facts(dna.sales_point, "script")
        if not facts:
            raise StoryWritingError(f"卖点 {dna.sales_point} 没有可用 Claims 文案，停止写稿")
        topic = str((hotspot or {}).get("title") or dna.hotspot or "").strip()
        if not topic:
            raise StoryWritingError("选题为空，不能写稿")

        min_chars = (DUO_MIN_CJK if dna.dialogue_mode == "双人对白"
                     and structure.get("id") == "S_duo_conflict" else SPEECH_MIN_CJK)
        max_chars = (DUO_MAX_CJK if dna.dialogue_mode == "双人对白"
                     and structure.get("id") == "S_duo_conflict" else SPEECH_MAX_CJK)
        per_line_min = min_chars // max(1, expected)
        per_line_max = min(MAX_LINE_CJK, (max_chars + max(1, expected) - 1) // max(1, expected))
        cast = _slots(dna)
        system = self._system_prompt(dna=dna, structure=structure, expected=expected,
                                     facts=facts, topic=topic, cast=cast)
        feedback = ""
        last_problems: list[str] = []
        last_lines: list[dict] = []
        last_notes: list[str] = []
        for _ in range(self.attempts):
            user = f"选题：{topic}\n"
            if feedback:
                user += ("上一次未通过，请基于这版逐句修正，不要另起空稿："
                         + "；".join(last_problems) + "。上一版台词："
                         + "；".join(str(row.get("text") or "") for row in last_lines)
                         + "。上一版分镜描述："
                         + "；".join(last_notes)
                         + f"。分镜描述必须正好 {int(structure.get('shots') or 0)} 条，"
                           f"台词必须正好 {expected} 句，每句 {per_line_min}-{per_line_max} 个汉字，"
                           "按逐句目标修改，同时保持事实不变。\n")
            user += "只返回约定 JSON，不要解释。"
            data = chat_json([{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                             temperature=0.35, max_tokens=2400, retries=1,
                             thinking=False)
            draft = self._from_json(data, dna=dna, structure=structure)
            last_problems = validate_draft(draft, dna=dna, structure=structure)
            if not last_problems:
                return draft
            last_lines = draft.lines
            last_notes = draft.shot_notes
            feedback = "repair"
        raise StoryWritingError("文案连续未通过旧版 one-take 合同：" + "；".join(last_problems))
    @staticmethod
    def _system_prompt(*, dna, structure: dict, expected: int, facts: str,
                       topic: str, cast: list[str]) -> str:
        line_plan = list(line_plan_for(str(structure.get("id") or "")))
        min_chars = (DUO_MIN_CJK if dna.dialogue_mode == "双人对白"
                     and structure.get("id") == "S_duo_conflict" else SPEECH_MIN_CJK)
        max_chars = (DUO_MAX_CJK if dna.dialogue_mode == "双人对白"
                     and structure.get("id") == "S_duo_conflict" else SPEECH_MAX_CJK)
        per_line_min = min_chars // max(1, expected)
        per_line_max = min(MAX_LINE_CJK, (max_chars + max(1, expected) - 1) // max(1, expected))
        total_rule = (f"纯汉字总数必须 {DUO_MIN_CJK}-{DUO_MAX_CJK}"
                      if dna.dialogue_mode == "双人对白" and structure.get("id") == "S_duo_conflict"
                      else f"口播纯汉字总数 {SPEECH_MIN_CJK}-{SPEECH_MAX_CJK}")
        return f"""你是15秒短视频编剧。先尊重选题，再自然植入一个与选题匹配的产品卖点。

硬事实：只允许使用这一条卖点事实：{facts}
选题：{topic}
片型：{dna.genre}；骨架：{structure.get('name')}；对白模式：{dna.dialogue_mode}
角色槽：{cast}；镜头数：{structure.get('shots')}；每镜句数：{line_plan}

硬规则：
1. 不得把原选题改造成另一个主题；卖点只能服务故事，不能反客为主。
2. 人物新闻/亲情/老兵/圆梦类选题一律按“虚构演绎/情景借鉴”处理，不冒充真实当事人，不消费人物尊严。
3. 共 {expected} 句；每句目标 {per_line_min}-{per_line_max} 个汉字且最多 {MAX_LINE_CJK} 个；{total_rule}；不写阿拉伯数字。
4. 双人对白必须两个角色严格轮流说，口语自然，有问有答，不允许空句。
5. 只出现已给角色，不新增老人、路人、围观者或重复人物。
6. 必须返回正好 {int(structure.get('shots') or 0)} 条英文 shot_notes，按镜头顺序各一条；只描述动作、位置和单一产品，不加字幕文字。
7. 禁止另造参数、疗效、价格、认证、质保等事实；CTA 轻，不硬卖。

严格返回 JSON：
{{"title":"短标题","goal":"一句话故事目标","payoff":"自然收获/卖点落点","ending":"结尾动作",
"cta":"轻CTA","lines":["第1句", "..."],"shot_notes":["English shot 1", "..."]}}
"""

    @staticmethod
    def _from_json(data: dict, *, dna, structure: dict) -> StoryDraft:
        raw_lines = data.get("lines") if isinstance(data, dict) else []
        raw_notes = data.get("shot_notes") if isinstance(data, dict) else []
        return StoryDraft(
            title=str(data.get("title") or "").strip(),
            goal=str(data.get("goal") or "").strip(),
            payoff=str(data.get("payoff") or "").strip(),
            ending=str(data.get("ending") or "").strip(),
            cta=str(data.get("cta") or "").strip(),
            lines=_map_lines(list(raw_lines or []), dna=dna, structure=structure),
            shot_notes=[str(x or "").strip() for x in list(raw_notes or [])],
        )
