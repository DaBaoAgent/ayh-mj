"""全角色照片级版：生成 + 替换原版（备份原图）

流程：
  1) 现有 library_real/ 10 张直接采用
  2) 其余角色按 roles.yaml (age/gender/region/trait) 生成照片级版
  3) 备份原 library/ → library_ai_backup/，然后用 library_real/ 覆盖 library/
用法: .venv/Scripts/python.exe tools/gen_all_realistic.py [--dry]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ARK = ROOT / "s4_generate/ark_image.py"
PY = ROOT / ".venv/Scripts/python.exe"
LIB = ROOT / "assets/cast/library"
REAL = ROOT / "assets/cast/library_real"
BACKUP = ROOT / "assets/cast/library_ai_backup"
REAL.mkdir(parents=True, exist_ok=True)

TMPL = ("照片级真人半身肖像摄影：{desc}。正面面向镜头，真实纪实摄影质感，85mm 定焦镜头，浅景深，"
        "背景自然虚化，柔和自然光，超写实皮肤纹理与毛发细节，高清，无文字，无水印")

REGION = {"城市": "中国", "时尚": "中国", "欧美": "欧美"}


def load_roles() -> list[dict]:
    d = yaml.safe_load((LIB / "roles.yaml").read_text(encoding="utf-8"))
    return d.get("roles", [])


def gen_one(r: dict) -> bool:
    rid = r["id"]
    out = REAL / f"{rid}.png"
    if out.exists():
        return True
    region = REGION.get(r.get("region", "城市"), "中国")
    desc = f"{region}的{r.get('age','')}岁{r.get('gender','')}性，{r.get('trait','')}"
    prompt = TMPL.format(desc=desc)
    for attempt in range(3):
        subprocess.run([str(PY), str(ARK), "--prompt", prompt, "--aspect", "3:4", "-o", str(out)],
                       capture_output=True, text=True)
        if out.exists() and out.stat().st_size > 10000:
            return True
        time.sleep(2)
    return False


def apply_replace() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(REAL.glob("*.png")):
        src = LIB / p.name
        if src.exists():
            bak = BACKUP / p.name
            if not bak.exists():
                bak.write_bytes(src.read_bytes())
            src.write_bytes(p.read_bytes())
            n += 1
    print(f"✓ 替换 {n} 个角色（原版备份在 {BACKUP}）")


def main(dry: bool = False) -> None:
    roles = load_roles()
    print(f"角色总数: {len(roles)}")
    if dry:
        for r in roles:
            print(" ", r["id"], "✓已有" if (REAL / f"{r['id']}.png").exists() else "→ 待生成")
        return
    done, fail = 0, []
    for i, r in enumerate(roles, 1):
        if (REAL / f"{r['id']}.png").exists():
            done += 1
            continue
        ok = gen_one(r)
        if ok:
            done += 1
        else:
            fail.append(r["id"])
        print(f"[{i}/{len(roles)}] {r['id']} {'✓' if ok else '✗'}", flush=True)
    print(f"\n✓ 完成 {done}/{len(roles)}，失败 {len(fail)}: {fail}")
    if not fail:
        apply_replace()
        # 记录
        (ROOT / "state/cast_realistic_applied.json").write_text(
            json.dumps({"count": done, "backup": str(BACKUP), "date": "2026-09-25"}, ensure_ascii=False, indent=1),
            encoding="utf-8")


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
