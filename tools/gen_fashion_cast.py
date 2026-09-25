"""时尚组 10 角色定妆图批量生成（Seedream，对齐全库风格：半身/正面/实景虚化/写实）

输出: assets/cast/library/fashion_*.png (1536x2048)
用法: .venv/Scripts/python.exe tools/gen_fashion_cast.py [--dry]
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
    ("fashion_granny_silver", "68岁中国时尚奶奶，精致银色大波浪短发，黑框墨镜推到头顶，米色长款风衣内搭黑色高领衫，涂着红唇，气质优雅出众"),
    ("fashion_grandpa_cool", "70岁中国潮爷，满头白发梳成背头，修剪整齐的白色胡茬，深蓝色西装外套内搭白衬衫，墨镜挂在领口，老绅士气场十足"),
    ("fashion_granny_qipao", "72岁中国奶奶，银色头发盘成优雅发髻，身穿深紫色丝绸旗袍，佩戴珍珠耳坠，端庄典雅富有东方韵味"),
    ("fashion_girl_street", "24岁中国女孩，双色挑染及肩长发，黑色皮质机车夹克，浅色工装裤，街头潮流感十足，表情酷而自信"),
    ("fashion_boy_fresh", "27岁中国男生，清爽利落短发，浅蓝色亚麻衬衫外套内搭纯白T恤，干净阳光，微笑自然"),
    ("fashion_woman_chic", "35岁中国女性，栗色大波浪卷发，奶茶色羊绒大衣，金色细项链，都市精致感，神情自信从容"),
    ("fashion_man_gentle", "48岁中国男性，花白鬓角灰发，细框金属眼镜，墨绿色针织开衫内搭白衬衫，文艺雅痞气质"),
    ("fashion_girl_sporty", "22岁中国女孩，高扎黑色马尾辫，白色防风运动外套搭配深色运动内搭，运动时尚感，活力笑容"),
    ("fashion_woman_office", "42岁中国女性，利落黑色齐耳短发，灰色西装外套与同色套裙，内搭白衬衫，干练精英气场"),
    ("fashion_man_suit", "45岁中国男性，侧梳背头，藏蓝色西装三件套，白衬衫银色领带，沉稳有型，商务精英"),
]


def main(dry: bool = False) -> None:
    todo = [(n, p) for n, p in CASES if not (OUT_DIR / f"{n}.png").exists() or "--force" in sys.argv]
    print(f"🎨 时尚组角色图：{len(todo)}/{len(CASES)} 张待生成", flush=True)
    for i, (name, person) in enumerate(todo, 1):
        out = OUT_DIR / f"{name}.png"
        prompt = person + STYLE_TAIL
        print(f"[{i}/{len(todo)}] {name} ...", flush=True)
        if dry:
            print("   ", prompt[:80], flush=True)
            continue
        r = subprocess.run([str(PY), str(ARK), "--prompt", prompt, "--aspect", "3:4", "-o", str(out)],
                           capture_output=True, text=True, cwd=str(ROOT))
        ok = out.exists()
        print(f"   {'✓' if ok else '✗'} {out.name} {out.stat().st_size//1024 if ok else 0}KB", flush=True)
        if not ok:
            print("   stderr:", r.stderr[-200:], flush=True)
    print("✓ 全部完成", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
