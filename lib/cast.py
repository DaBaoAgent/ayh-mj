"""角色卡司库 — 人物一致性（定妆图/情绪图）+ 声音一致性（音色样本）

人物一致性：每个角色有基础定妆图 + 情绪变体；分镜 cast_refs 引用简称，自动解析。
声音一致性：每个角色有音色样本（从生成成片中提取）；生成时作为 ref_audio 传入 H3 克隆音色。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAST_DIR = ROOT / "assets" / "cast"
EMO_DIR = CAST_DIR / "emotions"
VOICE_DIR = CAST_DIR / "voice"
PRODUCT_DIR = ROOT / "assets" / "products"

# ── 角色卡司 ──────────────────────────────────────────────
CAST = {
    "son": {
        "name": "儿子",
        "desc": "45岁中国男性，黑色夹克+蓝牛仔裤，胡茬，长相普通",
        "emotions": {
            "neutral": CAST_DIR / "son_portrait.png",
            "urgent": EMO_DIR / "son_urgent.png",
            "proud": EMO_DIR / "son_proud.png",
        },
        "voice": VOICE_DIR / "son_voice.mp3",
    },
    "mother": {
        "name": "母亲",
        "desc": "68岁中国女性，银灰短发+酒红色抓绒衣",
        "emotions": {
            "neutral": CAST_DIR / "mother_portrait.png",
            "stubborn": EMO_DIR / "mother_stubborn.png",
            "softening": EMO_DIR / "mother_softening.png",
        },
        "voice": VOICE_DIR / "mother_voice.mp3",
    },
    "elder": {
        "name": "邻居大爷",
        "desc": "65岁中国男性，灰白短发+深蓝夹克，爱唠嗑",
        "emotions": {
            "neutral": CAST_DIR / "elder_portrait.png",
            "amazed": EMO_DIR / "elder_amazed.png",
        },
        "voice": VOICE_DIR / "elder_voice.mp3",
    },
    "courier": {
        "name": "快递员",
        "desc": "30岁中国男性，蓝色工服+鸭舌帽",
        "emotions": {
            "neutral": CAST_DIR / "courier_portrait.png",
        },
        "voice": VOICE_DIR / "courier_voice.mp3",
    },
    "dog": {
        "name": "旺财（宠物狗）",
        "desc": "米白色比熊犬，圆眼，蓬松",
        "emotions": {
            "neutral": CAST_DIR / "dog_portrait.png",
        },
        "voice": None,  # 无对白
    },
}

# ── 道具/产品图 ──────────────────────────────────────────
PROPS = {
    "old_wheelchair": CAST_DIR / "old_wheelchair.png",
    "折叠": PRODUCT_DIR / "折叠-无阴影.png",
    "正侧": PRODUCT_DIR / "正侧-3-无阴影.png",
    "45度": PRODUCT_DIR / "45度-加水杯-无阴影.png",
}

# ── 分镜 cast_refs 简称 → 解析 ────────────────────────────
# 命名规则：<角色>_<情绪>；产品用 折叠/正侧/侧面
def resolve_refs(cast_refs: list[str]) -> list[Path]:
    """把分镜里的简称列表解析成实际文件路径（保持顺序，人物在前产品在后）"""
    people, props_ = [], []
    for ref in cast_refs:
        ref = ref.strip()
        if ref in PROPS:
            props_.append(PROPS[ref])
            continue
        # 情绪引用: son_urgent / mother_stubborn / dog (默认 neutral)
        parts = ref.split("_", 1)
        role = parts[0]
        if role not in CAST:
            raise KeyError(f"未知角色引用: {ref}（可用: {list(CAST)} + {list(PROPS)}）")
        emo = parts[1] if len(parts) > 1 else "neutral"
        emos = CAST[role]["emotions"]
        if emo not in emos:
            raise KeyError(f"角色 {role} 无情绪 '{emo}'（可用: {list(emos)}）")
        people.append(emos[emo])
    return people + props_


def resolve_voice(speaker: str) -> Path | None:
    """说话人 → 音色样本路径（S1→son, S2→mother, S3→elder…）；找不到返回 None"""
    if not speaker or "画外" in speaker:
        # "S2+S1画外" 这类混合取第一个有音色的
        for token in ("S1", "S2", "S3"):
            if token in speaker:
                return _voice_of(token)
        return None
    return _voice_of(speaker.strip())


def _voice_of(token: str) -> Path | None:
    token = token.upper()
    role = {"S1": "son", "S2": "mother", "S3": "elder"}.get(token)
    if not role or role not in CAST:
        return None
    v = CAST[role].get("voice")
    return v if v and Path(v).exists() else None


def missing_assets() -> list[str]:
    """体检：列出缺失的定妆图/情绪图/音色样本"""
    missing = []
    for role, cfg in CAST.items():
        for emo, p in cfg["emotions"].items():
            if not Path(p).exists():
                missing.append(f"缺失情绪图: {cfg['name']} {role}/{emo} → {p}")
        v = cfg.get("voice")
        if v and not Path(v).exists():
            missing.append(f"缺失音色: {cfg['name']} {role} → {v}")
    for name, p in PROPS.items():
        if not Path(p).exists():
            missing.append(f"缺失道具图: {name} → {p}")
    return missing


if __name__ == "__main__":
    print("=== 角色卡司体检 ===")
    ms = missing_assets()
    if ms:
        for m in ms:
            print(" ⚠", m)
    else:
        print(" ✓ 全部资产就绪")
    print(f"\n角色数: {len(CAST)} | 道具数: {len(PROPS)}")
