"""审核预览卡：参考图 + 四镜分镜表 → PNG（给老板审核用）

用法: python tools/make_review_card.py
输出: docs/review_card_T06_20260924.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W = 1240
FONT = "C:/Windows/Fonts/msyh.ttc"
FONT_B = "C:/Windows/Fonts/msyhbd.ttc"


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except Exception:
        return ImageFont.truetype(FONT, size)


def load_rgb(p: Path):
    img = Image.open(p)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    return img.convert("RGB")


def fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    r = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)


def main():
    refs = [
        ("儿子定妆（45岁）", ROOT / "assets/cast/emotions/son_full.png"),
        ("母亲定妆（68岁）", ROOT / "assets/cast/emotions/mother_full.png"),
        ("产品·折叠态", ROOT / "assets/products/折叠-无阴影.png"),
        ("产品·正侧", ROOT / "assets/products/正侧-3-无阴影.png"),
    ]
    shots = [
        ("镜1  0-4.0s", "母亲（抱怨）", "哎哟又乱花钱，这新车明儿赶紧给我退了去。", "18字"),
        ("镜2  4.0-7.5s", "儿子（笃定）", "退啥呀？妈您先坐上去，遛一圈再试试。", "15字"),
        ("镜3  7.5-11.5s", "母亲（惊讶）", "哎？车碾过减速带，这筐鸡蛋咋一个都没碎呀？", "18字"),
        ("镜4  11.5-15s", "儿子（收尾）", "全靠这十八股减震呢，爱优护轻便侠。", "15字"),
    ]

    card = Image.new("RGB", (W, 1180), (250, 250, 252))
    d = ImageDraw.Draw(card)

    # 标题
    d.rectangle([0, 0, W, 84], fill=(24, 28, 38))
    d.text((40, 18), "T06 后备箱魔术 · 单条多镜头（4镜一条15s）· 待审核", font=font(36, True), fill=(255, 255, 255))
    d.text((40, 96), "新工艺：全部 4 个分镜在一条 15 秒视频里一次生成 —— 人物与声音全程一致（双音色克隆）",
           font=font(24), fill=(90, 90, 100))

    # 参考图区
    box_w, box_h = 272, 400
    x0, y0 = 32, 140
    for i, (label, p) in enumerate(refs):
        x = x0 + i * (box_w + 24)
        d.rectangle([x, y0, x + box_w, y0 + box_h], outline=(210, 210, 218), width=2, fill=(255, 255, 255))
        img = fit(load_rgb(p), box_w - 12, box_h - 52)
        card.paste(img, (x + (box_w - img.width) // 2, y0 + 8 + (box_h - 52 - img.height) // 2))
        d.text((x + 10, y0 + box_h - 40), label, font=font(22, True), fill=(30, 30, 40))

    # 分镜区
    ys = y0 + box_h + 36
    d.rectangle([32, ys, W - 32, ys + 420], outline=(210, 210, 218), width=2, fill=(255, 255, 255))
    d.text((52, ys + 14), "四镜分镜（台词总量 66 字 / 铺满率 98.7%）", font=font(26, True), fill=(24, 28, 38))
    yy = ys + 64
    for t, who, line, chars in shots:
        d.text((52, yy), t, font=font(24, True), fill=(200, 60, 40))
        d.text((230, yy), who, font=font(24), fill=(60, 60, 80))
        d.text((420, yy), line, font=font(24), fill=(20, 20, 30))
        d.text((W - 130, yy), chars, font=font(22), fill=(120, 120, 130))
        yy += 84

    # 底部参数
    d.text((32, ys + 448), "工作流 minimax_h3_image_audio_to_video_v2_15s ｜ 15s / 768p竖 ｜ 参考图 4 张 ｜ 音色 2 条 ｜ 预估 ¥0.6",
           font=font(22), fill=(90, 90, 100))
    d.text((32, ys + 486), "审核点：① 故事/台词  ② H3 提示词（见会审文档）  ③ 参数与成本", font=font(22), fill=(90, 90, 100))

    out = ROOT / "docs" / "review_card_T06_20260924.png"
    card.save(out)
    print("saved:", out)


if __name__ == "__main__":
    main()
