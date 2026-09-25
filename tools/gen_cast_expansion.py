"""角色组扩充到每组 20 人 — 批量生成 55 张角色图（2026-09-25 宝哥令）

- 核心卡司 5→20（+15，老王亲友团）
- 欧美组 5→20（+15）
- 时尚组 10→20（+10）
- 老外时尚组 5→20（+15）
城市组 20 已达标不动。
输出: assets/cast/library/*.png
用法: .venv/Scripts/python.exe tools/gen_cast_expansion.py [--dry]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv/Scripts/python.exe"
ARK = ROOT / "s4_generate/ark_image.py"
OUT_DIR = ROOT / "assets/cast/library"

TAIL = "，半身定妆参考照，人物正面朝向镜头，面部五官清晰可见，都市生活/时尚环境背景虚化，柔和自然光，写实摄影风格，高清细节，画面只有这一个人，无文字无水印"

CASES = [
    # ── 核心卡司 +15（老王亲友团）──
    ("core_wife_66", "66岁中国老太太，老王的妻子，花白短发烫卷，深红色针织开衫内搭碎花衬衫，慈祥温和"),
    ("core_son_38", "38岁中国男性，老王的儿子，黑色短发，浅蓝色衬衫，稳重可靠，微胖"),
    ("core_daughter_35", "35岁中国女性，老王的女儿，齐肩黑发，米色风衣，干练温柔"),
    ("core_grandson_12", "12岁中国男孩，老王的孙子，短寸头，蓝白校服外套，活泼机灵"),
    ("core_granddaughter_8", "8岁中国女孩，老王的孙女，双马尾，粉色卫衣，天真可爱"),
    ("core_dil_33", "33岁中国女性，老王的儿媳，披肩发马尾，浅灰毛衣，温婉勤快"),
    ("core_sil_37", "37岁中国男性，老王的女婿，短发干净，深蓝色夹克，斯文"),
    ("core_neighbor_li_68", "68岁中国男性，老王的老邻居老李，稀疏短发，棕色夹克，热情爱聊天"),
    ("core_chess_friend_70", "70岁中国男性，老王的棋友，白色短须，深灰马甲，慢悠悠"),
    ("core_dance_partner_64", "64岁中国女性，老王的舞伴，黑色烫发，红色丝巾，爽朗爱笑"),
    ("core_doctor_45", "45岁中国男性，社区医生，白大褂内搭浅蓝衬衫，戴眼镜，温和专业"),
    ("core_shop_owner_50", "50岁中国男性，小卖部老板，深蓝围裙内搭格子衬衫，圆脸和善"),
    ("core_nurse_young_26", "26岁中国女性，社区护理员，浅粉色制服，马尾辫，亲切"),
    ("core_old_comrade_72", "72岁中国男性，老王的老战友，银色寸头，旧军绿色外套，硬朗"),
    ("core_postman_40", "40岁中国男性，老邮递员，灰色制服帽，深绿工装，朴实"),
    # ── 欧美组 +15 ──
    ("western_granny_70", "70岁欧美老奶奶，银白色短卷发，浅紫色针织开衫，戴老花镜，慈祥和蔼"),
    ("western_aunt_55", "55岁欧美女性，金色盘发，米色风衣，珍珠耳钉，优雅"),
    ("western_uncle_50", "50岁欧美男性，灰棕色短发，卡其夹克，络腮胡修剪整齐，稳健"),
    ("western_lady_45", "45岁欧美女性，栗色中长发，墨绿色连衣裙，知性优雅"),
    ("western_gent_60", "60岁欧美男性，银灰色背头，灰色三件套西装，怀表链，老派绅士"),
    ("western_doctor_42", "42岁欧美男性，深棕短发，白大褂，蓝色眼睛，专业亲和"),
    ("western_teacher_38", "38岁欧美女性，金发波波头，驼色针织衫，温和笑容"),
    ("western_chef_35", "35岁欧美男性，深色短发留胡茬，白色厨师服，爽朗"),
    ("western_athlete_26", "26岁欧美男性，金棕色短发，深灰运动T恤，肌肉匀称，阳光"),
    ("western_artist_29", "29岁欧美女性，大波浪棕发，贝雷帽，姜黄色毛衣，文艺气质"),
    ("western_businessman_50", "50岁欧美男性，花白背头，藏蓝西装，白衬衫，商务气质"),
    ("western_neighbor_62", "62岁欧美男性，银发微卷，绿色polo衫，随和邻家感"),
    ("western_teen_boy_16", "16岁欧美少年，浅金色碎发，连帽卫衣，青春朝气"),
    ("western_teen_girl_15", "15岁欧美少女，棕色长马尾，白色卫衣，明亮活泼"),
    ("western_kid_girl_7", "7岁欧美小女孩，金色双马尾，黄色连衣裙，萌态可掬"),
    # ── 时尚组 +10 ──
    ("fashion_lady_50", "50岁中国时尚阿姨，深棕色利落短发，酒红色丝质衬衫，成熟优雅"),
    ("fashion_gent_55", "55岁中国时尚绅士，银灰背头，深绿色西装外套，口袋巾，儒雅有型"),
    ("fashion_girl_20", "20岁中国时尚女孩，黑色齐耳短发挑染蓝色，oversize西装，酷甜风格"),
    ("fashion_boy_22", "22岁中国时尚男生，栗棕色卷发，米色针织polo衫，慵懒文艺"),
    ("fashion_woman_32", "32岁中国时尚女性，黑色长直发，白色廓形衬衫，简约高级"),
    ("fashion_man_35", "35岁中国时尚男性，寸头干净，黑色高领毛衣，极简主义"),
    ("fashion_granny_2", "70岁中国时尚奶奶，银发短发别发夹，宝蓝色大衣，涂豆沙色口红，精神矍铄"),
    ("fashion_grandpa_2", "75岁中国时尚爷爷，白发圆顶帽，驼色大衣内搭高领毛衣，慢生活雅士"),
    ("fashion_girl_2", "26岁中国时尚女孩，栗色中长卷发，格纹西装外套，通勤时尚"),
    ("fashion_man_2", "40岁中国时尚男性，短发利落，深灰色薄款风衣，都市型男"),
    # ── 老外时尚组 +15 ──
    ("fashion_western_lady_50", "50岁欧美时尚女性，金色利落短发，白色西装套装，气场强大"),
    ("fashion_western_gent_55", "55岁欧美时尚男性，银白发后梳，深紫色西装，口袋巾，艺术品味"),
    ("fashion_western_girl_20", "20岁欧美时尚女孩，黑色波波头，银色皮衣，酷感十足"),
    ("fashion_western_boy_22", "22岁欧美时尚男生，深金卷发，燕麦色针织衫，文艺清新"),
    ("fashion_western_woman_2", "32岁欧美时尚女性，红棕色长卷发，黑色大衣，知性时髦"),
    ("fashion_western_man_2", "35岁欧美时尚男性，深棕短发，深蓝色针织polo衫，沉稳休闲"),
    ("fashion_western_granny_2", "72岁欧美时尚奶奶，银发盘发，墨绿色丝绒外套，胸针点缀，雍容"),
    ("fashion_western_grandpa_2", "74岁欧美时尚爷爷，白发白须，粗花呢西装外套，英伦绅士"),
    ("fashion_western_teen_girl_16", "16岁欧美少女，浅金色长直发，粉色羊羔绒外套，青春甜美"),
    ("fashion_western_teen_boy_17", "17岁欧美少年，棕色卷发，条纹毛衣，腼腆清秀"),
    ("fashion_western_kid_girl_8", "8岁欧美小女孩，金棕色双辫，红色呢子大衣，活泼可爱"),
    ("fashion_western_kid_boy_9", "9岁欧美小男孩，金色短发，海军蓝毛衣，精灵古怪"),
    ("fashion_western_athlete_26", "26岁欧美男性，深金色短发，白色运动夹克，活力四射"),
    ("fashion_western_artist_29", "29岁欧美女性，深棕色编发，橙色针织衫，艺术感配饰，自由气质"),
    ("fashion_western_singer_24", "24岁欧美女性，黑色长卷发，银色吊带上衣，舞台感，明艳"),
]


def main(dry: bool = False) -> None:
    todo = [(n, p) for n, p in CASES if not (OUT_DIR / f"{n}.png").exists() or "--force" in sys.argv]
    print(f"🎨 角色组扩充：{len(todo)}/{len(CASES)} 张待生成", flush=True)
    for i, (name, person) in enumerate(todo, 1):
        out = OUT_DIR / f"{name}.png"
        print(f"[{i}/{len(todo)}] {name} ...", flush=True)
        if dry:
            continue
        subprocess.run([str(PY), str(ARK), "--prompt", person + TAIL, "--aspect", "3:4", "-o", str(out)],
                       capture_output=True, text=True, cwd=str(ROOT))
        ok = out.exists()
        print(f"   {'✓' if ok else '✗'} {out.name} {out.stat().st_size//1024 if ok else 0}KB", flush=True)
    print("✓ 全部完成", flush=True)


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
