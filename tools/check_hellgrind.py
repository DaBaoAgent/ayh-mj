"""三件套接入自检 — 一键确认 Higgsfield《Hell Grind》接入层完好（2026-09-26）

用途：升级/清理/换机后，或改动 lib/hellgrind.py 后，跑一次确认三件套没被拆散。
     只读检查，不花钱、不出片。

用法：
    .venv/Scripts/python.exe tools/check_hellgrind.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

OK, BAD = "✓", "✗"
fails: list[str] = []


def chk(cond: bool, label: str, detail: str = "") -> None:
    print(f"  {OK if cond else BAD} {label}" + (f"   {detail}" if detail else ""))
    if not cond:
        fails.append(label)


print("=" * 74)
print("Higgsfield《Hell Grind》三件套 —— 接入自检")
print("=" * 74)

# ── 1. 官方原文（本地副本 + MD5）──
print("\n【1】官方原文（D:\\@kaifa\\higgsfield-hell-grind-skills）")
import hashlib
EXPECT = {
    "LIRA SKILL.md": "dbda9c9aaac7f12dfa7c11db797d27b1",
    "CINEDANCE HIGGSFIELD SKILL.md": "1ad963e23e869929b562e5a8609c1bd6",
    "ACTING SKILL.md": "070c75fc8e8a0bdc977de937a7fef983",
}
SRC = Path("D:/@kaifa/higgsfield-hell-grind-skills")
for name, md5 in EXPECT.items():
    p = SRC / name
    if not p.exists():
        chk(False, f"{name}", "原文缺失")
        continue
    got = hashlib.md5(p.read_bytes()).hexdigest()
    chk(got == md5, f"{name}", f"{p.stat().st_size:,}B md5={got[:12]}")

# ── 2. Hermes 技能 ──
print("\n【2】Hermes 技能（media/）")
SK = Path.home() / "AppData" / "Local" / "hermes" / "skills" / "media"
for name in ("lira-image-prompts", "cinedance-seedance", "acting-performance"):
    d = SK / name
    sk = d / "SKILL.md"
    refs = list((d / "references").glob("*.md")) if (d / "references").exists() else []
    chk(sk.exists() and bool(refs), f"{name}",
        f"SKILL.md {sk.stat().st_size:,}B + references {len(refs)} 份" if sk.exists() else "缺失")

# ── 3. 代码接入层 ──
print("\n【3】代码接入层")
try:
    from lib import hellgrind as hg
    from lib import prompt_parts as pp
    import inspect
    chk(True, "lib/hellgrind.py 可导入")
    for fn in ("cast_prompt", "shot_block", "acting_block", "load_master", "master_profile_template",
               "tail_constants", "ensure_dirs"):
        chk(callable(getattr(hg, fn, None)), f"  hg.{fn}()")
    chk(len(hg.CINEDANCE_CONSTANTS) > 100, "CINEDANCE_CONSTANTS",
        f"{len(hg.CINEDANCE_CONSTANTS)} 字符")
    sig = inspect.signature(pp.compose)
    chk("cinedance" in sig.parameters, "pp.compose(cinedance=)")
    chk("acting" in sig.parameters, "pp.compose(acting=)")
except Exception as e:
    chk(False, "lib 接入层导入", str(e)[:120])

# ── 4. 资产目录 ──
print("\n【4】资产目录")
AD = ROOT / "assets" / "cast" / "acting"
SD = ROOT / "assets" / "cast" / "scene"
masters = sorted(p.stem for p in AD.glob("*.md") if not p.name.startswith("scene_")) if AD.exists() else []
scenes = sorted(p.name for p in AD.glob("scene_*.md")) if AD.exists() else []
chk(AD.exists(), "assets/cast/acting/", f"主档案 {masters} + 场景改写版 {len(scenes)} 份")
chk(SD.exists(), "assets/cast/scene/",
    f"{len(list(SD.glob('*.png')))} 张场景版定妆图" if SD.exists() else "缺失")

# ── 5. 工具 ──
print("\n【5】工具")
for t in ("tools/gen_cast_scene.py", "tools/prep_g5_jingdian.py", "lib/hellgrind.py"):
    chk((ROOT / t).exists(), t)

# ── 6. 首个实例的 spec ──
print("\n【6】首个实例 G5《景点打卡》")
sp = ROOT / "state" / "onetake_prompt_job_G5_jingdian.json"
if sp.exists():
    spec = json.loads(sp.read_text(encoding="utf-8"))
    n = len(spec.get("prompt", ""))
    chk(n <= 9800, f"spec prompt {n} 字符", "安全线 9800")
    chk(len(spec.get("ref_images", [])) >= 3, f"参考图 {len(spec.get('ref_images', []))} 张")
    chk(len(spec.get("ref_audios", [])) == 2, f"音色 {len(spec.get('ref_audios', []))} 条")
else:
    chk(False, "spec 缺失", str(sp))

print("\n" + "=" * 74)
if fails:
    print(f"✗ {len(fails)} 项未通过：")
    for f in fails:
        print(f"   - {f}")
    raise SystemExit(1)
print("✓ 三件套接入完好（原文 / 技能 / 代码 / 资产 / 工具 / 实例 全部就位）")
