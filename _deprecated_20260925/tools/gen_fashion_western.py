"""老外时尚组 5 角色图批量生成（对齐时尚组风格：半身/正面/实景虚化/写实）

输出: assets/cast/library/fashion_western_*.png (3:4)
用法: .venv/Scripts/python.exe tools/gen_fashion_western.py [--dry]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv/Scripts/python.exe"
ARK = ROOT / "s4_generate/ark_image.py"
OUT_DIR = ROOT / "assets/cast/library"

STYLE_TAIL = "，半身定妆参考照，人物正面朝向镜头，面部五官清晰可见，都市时尚环境背景虚化，柔和自然光，写实摄影风格，高清细节，画面只有这一个人，无文字无水印"

CASES = [
    ("fashion_western_granny", "68岁欧美时尚奶奶，优雅的银白色大波浪卷发，黑框墨镜推到头顶，米白色长款风衣内搭黑色高领衫，涂着红唇，法式优雅超模气质"),
    ("fashion_western_grandpa", "70岁欧美时尚潮爷，整齐梳理的白发，修剪精致的花白胡须，深蓝色西装外套内搭白衬衫，墨镜挂在领口，老绅士风度"),
    ("fashion_western_woman", "30岁欧美时尚女性，金棕色大波浪长发，绿色眼睛，驼色风衣内搭白色高领毛衣，都市时尚气质，自信微笑"),
    ("fashion_western_man", "28岁欧美时尚男青年，沙金色利落短发，浅灰色休闲西装外套内搭纯净白T恤，干净帅气，笑容阳光"),
    ("fashion_western_exec", "40岁欧美职场精英女性，深棕色利落齐肩短发，藏蓝色职业套装内搭白衬衫，干练专业气场，神情从容"),
]


def main(dry: bool = False) -> None:
    todo = [(n, p) for n, p in CASES if not (OUT_DIR / f"{n}.png").exists() or "--force" in sys.argv]
    print(f"🎨 老外时尚组：{len(todo)}/{len(CASES)} 张待生成", flush=True)
    for i, (name, person) in enumerate(todo, 1):
        out = OUT_DIR / f"{name}.png"
        print(f"[{i}/{len(todo)}] {name} ...", flush=True)
        if dry:
            print("   ", person[:60], flush=True)
            continue
        r = subprocess.run([str(PY), str(ARK), "--prompt", person + STYLE_TAIL, "--aspect", "3:4", "-o", str(out)],
                           capture_output=True, text=True, cwd=str(ROOT))
        ok = out.exists()
        print(f"   {'✓' if ok else '✗'} {out.name} {out.stat().st_size//1024 if ok else 0}KB", flush=True)
    print("✓ 全部完成", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
