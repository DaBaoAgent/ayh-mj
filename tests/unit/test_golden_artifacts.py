"""Phase 13 Golden —— 冻结"稳定输入 → 关键结构 + hard constraints"，不比较自然语言全文。

计划要求：保存若干稳定 StorySpec / CreativeDNA，验证重构后 compiler 仍满足关键
结构和 hard constraints；**不要**比较随机自然语言的全文完全一致。

所以这里断言的是：
  · 结构不变量（镜头数、台词数、层名、预算未压缩）；
  · hard constraints 真的在（Hard constraints 尾巴、单件产品保真、无源音乐声明）；
  · 台词保真（每句台词原样出现在 prompt 里，编译不许偷偷丢句）；
  · 编译是纯函数（同一输入连编两次结果完全一致）。
期望值全部由稳定规则现算，不存"上一次的输出文本"，避免措辞变化导致假红。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lib.creative.compiler import (
    CINEDANCE_GENRES,
    PROMPT_MAX,
    compile_spec,
    gate_text,
)
from lib.prompt_parts import HARD_TAIL
from tests.p7_support import REF_IMAGES

pytestmark = pytest.mark.unit

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden" / "creative"
MANIFEST = json.loads((GOLDEN_DIR / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = MANIFEST["entries"]
IDS = [e["structure_id"] for e in ENTRIES]


def _load(entry: dict) -> dict:
    doc = json.loads((GOLDEN_DIR / entry["file"]).read_text(encoding="utf-8"))
    # fixture 里存的是相对路径，运行时换成真实存在的参考图
    doc["ref_images"] = list(REF_IMAGES)
    doc["story_spec"]["ref_images"] = list(REF_IMAGES)
    return doc


def test_manifest_is_non_empty_and_each_entry_files_exist():
    assert ENTRIES, "golden manifest 不能为空"
    for entry in ENTRIES:
        assert (GOLDEN_DIR / entry["file"]).is_file(), entry["file"]


def test_golden_inputs_cover_more_than_one_genre():
    genres = {e["genre"] for e in ENTRIES}
    assert len(genres) >= 3, f"golden 覆盖面太窄：{sorted(genres)}"


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_compiled_prompt_stays_within_budget(entry):
    compiled = compile_spec(_load(entry))
    assert 0 < len(compiled.prompt) <= PROMPT_MAX
    assert compiled.budget.compressed is False
    assert compiled.budget.limit == PROMPT_MAX


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_structure_is_preserved(entry):
    compiled = compile_spec(_load(entry))
    assert compiled.shot_count == entry["shots"], "镜头数变了"
    assert compiled.line_count == entry["lines"], "台词数变了"
    assert compiled.layers[0] == "header"
    assert compiled.layers.count("hard_tail") == 1
    shot_layers = [layer for layer in compiled.layers if re.fullmatch(r"shot\d+", layer)]
    assert len(shot_layers) == entry["shots"], compiled.layers
    assert len(shot_layers) == len(dict.fromkeys(shot_layers))


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_cinedance_activation_matches_the_genre_table(entry):
    compiled = compile_spec(_load(entry))
    assert compiled.cinedance is (entry["genre"] in CINEDANCE_GENRES)


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_hard_constraints_are_present(entry):
    compiled = compile_spec(_load(entry))
    prompt = compiled.prompt
    assert "Hard constraints:" in prompt
    assert HARD_TAIL in prompt
    assert "SINGLE UNIT" in prompt
    assert "non_diegetic_music: N/A" in prompt
    assert prompt.count("Hard cut.") >= entry["shots"]


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_every_spoken_line_survives_compilation(entry):
    doc = _load(entry)
    compiled = compile_spec(doc)
    texts = [str(line.get("text") or "").strip()
             for line in doc["story_spec"]["lines"] if str(line.get("text") or "").strip()]
    assert len(texts) == entry["lines"]
    for text in texts:
        assert text in compiled.prompt, f"台词被编译丢了：{text}"


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_compilation_is_a_pure_function(entry):
    doc = _load(entry)
    first = compile_spec(doc)
    second = compile_spec(doc)
    assert first.prompt == second.prompt
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_gate_text_wraps_the_prompt_with_duration_and_resolution(entry):
    compiled = compile_spec(_load(entry))
    payload = gate_text(compiled.prompt, duration=entry["duration"],
                        resolution=entry["resolution"])
    assert f'duration="{entry["duration"]}"' in payload
    assert f'resolution="{entry["resolution"]}"' in payload
    assert compiled.prompt in payload


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_prompt_carries_no_leftover_template_placeholders(entry):
    compiled = compile_spec(_load(entry))
    for token in ("{", "}", "%s", "None", "TODO"):
        assert token not in compiled.prompt, f"prompt 里残留了模板痕迹：{token}"


def test_silent_story_has_no_speaker_lock_but_still_has_hard_constraints():
    entry = next(e for e in ENTRIES if e["dialogue_mode"] == "无对白")
    compiled = compile_spec(_load(entry))
    assert "SPEAKER LOCK" not in compiled.prompt
    assert "Hard constraints:" in compiled.prompt
