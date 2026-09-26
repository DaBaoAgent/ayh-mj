"""场景版人物定妆图 — LIRA 环节正式入口（2026-09-26 三件套接入）

为什么需要：`assets/cast/` 里的通用定妆图是**社区场景**拍的；当一条片换到
景点/公园/商场/雨夜等新场景时，直接拿社区图当参考图会让 H3 把背景也搬过去。
本工具按 LIRA 口径为**具体片**出一版「同一个人 + 新场景 + 全身」的参考图，
存 `assets/cast/scene/`，供该片的 spec 引用。不覆盖通用库资产。

也支持**全新角色**（未在 assets/cast 出现过，`ref=None`）：此时不加参考图，纯文字生成。
用于本产线之外的题材验证（如 hero 组的英雄对决）。

LIRA 方法论落地：
  ① DIAGNOSE 先列这张图会怎么失败 → ② 逐条下锁（不是堆形容词）
  典型失败 → 锁：
    脸漂移/换人   → 传已有 full 图当 --ref（同一个人，只换场景）
    背景变影棚     → 写具体实景材质（地砖/石板/栏杆/远景虚化），禁 "studio/backdrop"
    服装被改       → 逐件写死颜色款式（来自该角色的既有定妆图）
    塑料皮肤/美颜  → LIRA_REALISM 锁（可见毛孔、细纹、无美颜）
    画面出文字     → 禁文字锁（产品品牌字除外）
    年龄漂移       → 写清年龄段

用法：
    PY=.venv/Scripts/python.exe
    $PY tools/gen_cast_scene.py --list                 # 看已内置的角色/场景
    $PY tools/gen_cast_scene.py --role elder --scene jingdian --uid G5
    $PY tools/gen_cast_scene.py --role elder,son --scene jingdian --uid G5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.hellgrind import cast_prompt  # noqa: E402
from s4_generate.ark_image import gen_image  # noqa: E402

OUT = ROOT / "assets" / "cast" / "scene"

# ── 角色外貌（锁服装，来自 assets/cast 既有定妆图，vision 提取）──
ROLES = {
    "elder": dict(
        label="老王（邻居大爷）",
        ref="assets/cast/emotions/elder_full.png",
        desc="a 70-year-old Chinese man with short neatly combed silver-grey hair and a slightly receding "
             "hairline, square-round face, high cheekbones, deep-set eyes with downturned outer corners and "
             "crow's feet, sparse grey brows, a low-bridged broad nose and thin lips with deep nasolabial "
             "folds, calm steady expression",
        wardrobe="wearing an open dark navy casual zip jacket with a lapel over a grey crewneck knit sweater, "
                 "black loose straight-leg trousers and black slip-on casual shoes",
    ),
    "son": dict(
        label="儿子",
        ref="assets/cast/emotions/son_full.png",
        desc="a 48-year-old Chinese man with short black hair showing grey at both temples, slightly puffy and "
             "slightly messy on top, a long rectangular face with prominent cheekbones and slightly hollow "
             "cheeks, dark brown almond eyes with inner double lids looking slightly tired, straight brows with "
             "a faint vertical frown line, a medium straight nose, thin lips and salt-and-pepper stubble",
        wardrobe="wearing an open black casual jacket over a dark grey crewneck t-shirt and dark blue "
                 "straight-leg jeans",
    ),
    # ── 全新角色（hero 组：无 ref，纯文字生成；不写任何专有名词，形象做适度泛化）──
    "dark_knight": dict(
        label="黑衣斗篷侠（hero 组）",
        ref=None,
        desc="a 40-year-old man with a heavy square jaw, a faint stubble shadow and a firm closed mouth, "
             "wearing a matte-black segmented tactical armoured suit with plates across the chest and "
             "shoulders, a long charcoal-grey cape hanging to his calves, and a black cowl covering the top "
             "half of his face with two short pointed ears so that only his jaw and mouth are visible; "
             "broad-shouldered and solidly built",
        wardrobe="heavy black armoured boots and black gauntlets on both hands",
    ),
    "blue_hero": dict(
        label="红蓝紧身衣侠（hero 组）",
        ref=None,
        desc="a 35-year-old clean-shaven man with a square jaw, dark hair with a single curl falling on his "
             "forehead and a calm steady gaze, wearing a deep-blue fitted suit with a high collar, a red "
             "cape falling to his knees, red boots and a red belt, and an abstract red diamond emblem "
             "centred on his chest; no mask, no glasses; tall and athletic with an open chest",
        wardrobe="red knee-high boots and a thick red cape",
    ),
}

# ── 场景（写具体材质，不写 studio/backdrop）──
SCENES = {
    "jingdian": dict(
        label="旅游景点（石板路 + 古建 + 远景游客虚化）",
        text="standing on a wide grey stone-paved walkway at a Chinese scenic tourist spot in autumn, "
             "a low stone balustrade and traditional grey-tiled eaves behind, distant hills and a few "
             "heavily blurred tourists far in the background, soft overcast daylight",
    ),
    "park": dict(
        label="城市公园（步道 + 草坪 + 长椅）",
        text="standing on a reddish rubberised park jogging path with a green lawn and low hedges behind, "
             "a few blurred park benches and trees, soft afternoon daylight",
    ),
    "rooftop_night": dict(
        label="夜晚城市天台（混凝土 + 矮女儿墙 + 水塔 + 远景灯火虚化）",
        text="standing on the concrete rooftop of a city building at night, low parapet walls and a few "
             "ventilation ducts behind, a water tank silhouette further back, the distant city skyline "
             "rendered as heavily blurred lit windows, cool blue night light with a faint warm glow "
             "coming up from the street below",
    ),
    "market": dict(
        label="清晨菜市场（水磨石地面 + 摊位 + 遮阳棚）",
        text="standing on a terrazzo-floored wet market aisle with vegetable stalls and green plastic crates "
             "on both sides and canvas awnings overhead, a few heavily blurred shoppers far behind, "
             "soft morning light",
    ),
}


def build(role: str, scene: str, uid: str) -> tuple[Path, str, Path]:
    r, sc = ROLES[role], SCENES[scene]
    prompt = cast_prompt(
        f"{r['desc']}, {r['wardrobe']}",
        shot="full",
        ethnicity="Chinese",
        scene=sc["text"],
        purpose=f"reference image for shot {uid} — same person as the reference photo, new location, "
                f"so the video model cannot carry the old background over",
    )
    out = OUT / f"{role}_{scene}_{uid}.png"
    ref = ROOT / r["ref"] if r.get("ref") else None
    return out, prompt, ref


def main() -> int:
    ap = argparse.ArgumentParser(description="场景版人物定妆图（LIRA 环节）")
    ap.add_argument("--role", help="角色 id，逗号分隔（elder,son）")
    ap.add_argument("--scene", default="jingdian", help="场景 id")
    ap.add_argument("--uid", default="adhoc", help="片标识（进文件名）")
    ap.add_argument("--list", action="store_true", help="列出内置角色/场景")
    ap.add_argument("--dry", action="store_true", help="只打印提示词，不出图")
    a = ap.parse_args()

    if a.list or not a.role:
        print("角色：")
        for k, v in ROLES.items():
            print(f"  {k:<8} {v['label']:<16} ref={v['ref']}")
        print("场景：")
        for k, v in SCENES.items():
            print(f"  {k:<10} {v['label']}")
        return 0

    if a.scene not in SCENES:
        print(f"未知场景 {a.scene}，可选：{list(SCENES)}")
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    for role in [x.strip() for x in a.role.split(",") if x.strip()]:
        if role not in ROLES:
            print(f"✗ 未知角色 {role}，可选：{list(ROLES)}")
            rc = 2
            continue
        out, prompt, ref = build(role, a.scene, a.uid)
        print(f"\n{'=' * 72}\n🎨 {role} @ {a.scene} → {out.name}\n{'=' * 72}")
        print(f"[ref] {ref if ref else '（无 — 全新角色，纯文字生成）'}")
        print(f"[prompt {len(prompt)} 字符]\n{prompt}\n")
        if a.dry:
            continue
        if out.exists():
            print(f"↻ 已存在，跳过：{out}")
            continue
        try:
            res = gen_image(prompt, str(out), aspect="3:4", quality="high",
                            ref_images=[str(ref)] if (ref and ref.exists()) else None)
            print(f"✓ {out}  ({res.get('bytes', 0) / 1024:.0f}KB)")
        except Exception as e:
            print(f"✗ 失败：{str(e)[:200]}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
