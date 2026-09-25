"""一次性：T07 提示词 v3→v4（只强化产品视觉特征：红弹簧/品牌字/电动感）"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "state/onetake_prompt_job_20260924_135019_414348_21.json"
spec = json.loads(p.read_text(encoding="utf-8"))
t = spec["prompt"]

repl = [
    # 1) 总起段产品描述：加红弹簧+品牌字视觉特征
    ("The silver-grey lightweight electric wheelchair always keeps its exact form from the reference images: when folded, it stands upright on the ground as a compact vertical column resting on its large rear wheel and small anti-tip caster — never laid flat on its side, never floats in mid-air and never turns into a bicycle, scooter, motorcycle or any other vehicle; when unfolded, its four small wheels, seat frame and armrests are clearly visible.",
     "The silver-grey lightweight electric wheelchair always keeps its exact look from the reference images: its silver-grey metal frame, black seat, four wheels and the distinctive RED shock-absorbing springs on the frame are clearly visible whenever it is on screen, and its own brand lettering stays exactly as in the reference image. When folded, it stands upright on the ground as a compact vertical column resting on its large rear wheel and small anti-tip caster — never laid flat on its side, never floats in mid-air and never turns into a bicycle, scooter, motorcycle or any other vehicle; when unfolded, its four small wheels, seat frame and armrests are clearly visible. It is an electric wheelchair, never a plain manual wheelchair."),
    # 2) 镜2：展开后加产品特征
    ("he unfolds it on the ground — its four small wheels settle down and the seat frame locks into place.",
     "he unfolds it on the ground — its four small wheels settle down and the seat frame locks into place; the silver-grey frame with its red shock-absorbing springs faces the camera."),
    # 3) 镜3：轮椅描述加特征
    ("the bichon frise dog has climbed onto the wheelchair and sits on its seat with its tail wagging, looking straight into the camera;",
     "the bichon frise dog has climbed onto the silver-grey electric wheelchair with its red shock springs and now sits on its seat with its tail wagging, looking straight into the camera;"),
]
for old, new in repl:
    assert old in t, f"未命中: {old[:50]}"
    t = t.replace(old, new)

spec["prompt"] = t
spec["lines_meta"]["v4_change"] = "产品视觉特征强化：红弹簧/品牌字/电动感（明确 never a plain manual wheelchair）"
p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

header = '<h3:ReferenceVideo id="onetake-check" duration="12" resolution="768P" aspect-ratio="9:16">\n'
(ROOT / "docs/onetake_check_T07.txt").write_text(header + t + "\n", encoding="utf-8")
print("v4 已写")
