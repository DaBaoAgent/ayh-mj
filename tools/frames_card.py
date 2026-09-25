"""抽帧拼图卡：视频 → 指定时间点抽帧 → 横排拼图（带时间标签）

用法:
  python tools/frames_card.py <video.mp4> --ts 1.0,2.0,4.0,5.0 [--out docs/card.png]
  python tools/frames_card.py <video.mp4> --shots 0-3,3-6,6-9,9-12   # 按镜头区间自动取中点±0.7s
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

from PIL import Image, ImageDraw, ImageFont

FONT_B = "C:/Windows/Fonts/msyhbd.ttc"


def grab(video: Path, t: float, out: Path) -> bool:
    subprocess.run([ffmpeg(), "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out)],
                   capture_output=True)
    return out.exists()


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(1)
    video = Path(args[0])
    ts: list[float] = []
    out_path = video.parent / f"{video.stem}_card.png"
    i = 1
    while i < len(args):
        if args[i] == "--ts":
            ts = [float(v) for v in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--shots":
            for rng in args[i + 1].split(","):
                a, b = [float(v) for v in rng.split("-")]
                mid = (a + b) / 2
                ts += [max(a + 0.3, mid - 0.7), mid + 0.7]
            i += 2
        elif args[i] == "--out":
            out_path = Path(args[i + 1])
            i += 2
        else:
            i += 1
    if not ts:
        raise SystemExit("需要 --ts 或 --shots")

    tmp = video.parent / "_frames_tmp"
    tmp.mkdir(exist_ok=True)
    W, H = 330, 578
    imgs = []
    for t in ts:
        p = tmp / f"t{t:.1f}.jpg"
        if grab(video, t, p):
            im = Image.open(p).convert("RGB")
            r = min(W / im.width, (H - 40) / im.height)
            imgs.append((t, im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)))
    if not imgs:
        raise SystemExit("抽帧失败")
    total_w = sum(im.width for _, im in imgs) + 20 * (len(imgs) + 1)
    canvas = Image.new("RGB", (total_w, H + 10), (250, 250, 252))
    d = ImageDraw.Draw(canvas)
    f_b = ImageFont.truetype(FONT_B, 28)
    x = 20
    for t, im in imgs:
        canvas.paste(im, (x, 5))
        d.text((x + 4, H - 32), f"{t}s", font=f_b, fill=(24, 28, 38))
        x += im.width + 20
    canvas.save(out_path)
    print("saved:", out_path, canvas.size)


if __name__ == "__main__":
    main()
