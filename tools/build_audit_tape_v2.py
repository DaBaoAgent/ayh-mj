"""真人样本审核带 v2 — 20 个样本 + TTS 报幕拼接成一条（给宝哥听审）

输出: out/voices/真人样本审核带v2.mp3
流程: 每个样本前加 TTS 报幕（"1号，老年女"）+ 0.6s 间隔
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg
from s5_compose.tts import gen_tts

REAL = ROOT / "assets/cast/voice/real"
WORK = ROOT / "out/voices/audit_v2"
WORK.mkdir(parents=True, exist_ok=True)

# 顺序 = 审核带播放顺序：(文件名, 报幕词)
ORDER = [
    ("r01_elder_female", "1号，老年女，75岁"),
    ("r02_mature_female", "2号，中老年女，温暖"),
    ("r03_young_male", "3号，青年男，孝顺"),
    ("r04_child_girl", "4号，儿童女"),
    ("r05_young_female", "5号，青年女，甜美"),
    ("r06_child_boy", "6号，儿童男"),
    ("r07_nurse_female", "7号，青年女，护士"),
    ("r08_aunt_female", "8号，中年女，阿姨"),
    ("r09_adult_male", "9号，成年男"),
    ("r10_female", "10号，女性，时尚"),
    ("r11_mother_female", "11号，中年女，母亲"),
    ("r12_elder_male", "12号，老年男"),
    ("r13_rider_male", "13号，青年男，快递"),
    ("w01_foreign_male", "14号，老外男，一号"),
    ("w02_foreign_male2", "15号，老外男，二号"),
    ("w03_foreign_male3", "16号，老外男，三号"),
    ("w04_foreign_female", "17号，老外女"),
    ("w05_foreign", "18号，老外，待认领"),
    ("p01_honghuang_female", "19号，播客洪晃，中老年女"),
    ("p02_rensheng_male", "20号，播客人生杂叙，疑似播音腔"),
]


def norm(src: Path, dst: Path) -> None:
    """统一格式 32k mono 96k（拼接前提）"""
    subprocess.run([ffmpeg(), "-y", "-i", str(src), "-ar", "32000", "-ac", "1", "-b:a", "96k", str(dst)],
                   capture_output=True)


def main() -> None:
    parts = []
    silence = WORK / "sil.mp3"
    subprocess.run([ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono", "-t", "0.6",
                    "-b:a", "96k", str(silence)], capture_output=True)

    for i, (name, ann) in enumerate(ORDER, 1):
        src = REAL / f"{name}.mp3"
        assert src.exists(), f"缺样本: {src}"
        ann_out = WORK / f"a{i:02d}.mp3"
        if not ann_out.exists():
            gen_tts(ann, str(ann_out), rate="+20%")
        sample_out = WORK / f"s{i:02d}.mp3"
        norm(src, sample_out)
        parts += [ann_out, sample_out, silence]
        print(f"[{i}/20] {ann} ✓", flush=True)

    # concat demuxer 拼接
    lst = WORK / "list.txt"
    lst.write_text("\n".join(f"file '{p.name}'" for p in parts), encoding="utf-8")
    out = ROOT / "out/voices/真人样本审核带v2.mp3"
    r = subprocess.run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ar", "32000", "-ac", "1", "-b:a", "128k", str(out)],
                       capture_output=True, text=True, cwd=str(WORK))
    print(f"{'✓' if out.exists() else '✗'} {out} {out.stat().st_size//1024 if out.exists() else 0}KB", flush=True)


if __name__ == "__main__":
    main()
