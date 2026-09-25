"""建立标准普通话真人样本库 — 从两盘真人审核带切分 18 个样本

来源：
  音色审核带_补充13.mp3（13 段真人录音：老年/中年/青年/儿童）
  音色审核带_欧美5.mp3（5 段老外真人中文）
输出：assets/cast/voice/real/（+ INDEX.md 索引）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

V = ROOT / "assets/cast/voice"
OUT = V / "real"
OUT.mkdir(parents=True, exist_ok=True)

# (文件名, 源文件, 起始秒, 时长秒, 内容, 推断角色)
SEGS = [
    ("r01_elder_female", "补充13", 0.0, 4.6, "我今年七十五，腿脚还利索", "老年女·75岁（老王老伴/时尚奶奶类）"),
    ("r02_mature_female", "补充13", 4.6, 4.0, "晚上给你们炖排骨，早点回来", "中老年女·温暖（妈妈/奶奶）"),
    ("r03_young_male", "补充13", 8.6, 4.0, "妈，我明天陪你去复查", "青年男·孝顺（儿子/女婿）"),
    ("r04_child_girl", "补充13", 12.6, 2.8, "奶奶，这道题我会做", "儿童女（孙女）"),
    ("r05_young_female", "补充13", 16.6, 3.2, "爸爸，我拍全家福了", "青年女·甜美（女儿）"),
    ("r06_child_boy", "补充13", 20.8, 3.0, "爷爷，教我下象棋呗", "儿童男（孙子）"),
    ("r07_nurse_female", "补充13", 25.2, 3.2, "阿姨，血压正常，放心吧", "青年女·专业（护士/社区）"),
    ("r08_aunt_female", "补充13", 28.4, 5.0, "老姐姐，今天广场舞去不去？", "中年女·爽利（邻居阿姨）"),
    ("r09_adult_male", "补充13", 33.4, 3.0, "哦，五楼，麻烦您了", "成年男（快递/物业/保安）"),
    ("r10_female", "补充13", 36.4, 5.0, "这个颜色真好看，我要了", "女·时尚（姐姐/潮女）"),
    ("r11_mother_female", "补充13", 41.4, 4.0, "路上慢点，到了打电话", "中年女·操心（母亲）"),
    ("r12_elder_male", "补充13", 45.4, 4.0, "聊一会儿，不着急走", "老年男·从容（老王/教授）"),
    ("r13_rider_male", "补充13", 49.4, 3.0, "好，楼下取一下快递", "青年男（快递员/邻居）"),
    ("w01_foreign_male", "欧美5", 0.0, 4.24, "我在这儿住了十年，中国话没问题", "老外男A（外国爷爷类）"),
    ("w02_foreign_male2", "欧美5", 4.24, 4.16, "我太太是中国人，我妈也说中文", "老外男B（外国爸爸类）"),
    ("w03_foreign_male3", "欧美5", 8.4, 3.2, "轻得很，我一只手就能提", "老外男C（外国小伙类）"),
    ("w04_foreign_female", "欧美5", 11.6, 4.4, "这个设计比我想的聪明多了", "老外女（外国妈妈/姑娘类）"),
    ("w05_foreign", "欧美5", 16.0, 3.0, "试试这个，真挺轻的", "老外（待认领）"),
]

SRC = {
    "补充13": V / "音色审核带_补充13.mp3",
    "欧美5": V / "音色审核带_欧美5.mp3",
}


def main() -> None:
    rows = []
    for name, src, ss, dur, text, role in SEGS:
        out = OUT / f"{name}.mp3"
        subprocess.run([
            ffmpeg(), "-y", "-ss", f"{ss}", "-t", f"{dur}", "-i", str(SRC[src]),
            "-af", "loudnorm=I=-18:TP=-2:LRA=9", "-ar", "32000", "-ac", "1", "-b:a", "96k", str(out),
        ], capture_output=True)
        ok = out.exists()
        print(f"{'✓' if ok else '✗'} {name}.mp3  {out.stat().st_size//1024 if ok else 0}KB", flush=True)
        rows.append((name, src, f"{ss:.1f}-{ss+dur:.1f}s", text, role))

    idx = ["# 标准普通话真人样本库", "",
           "> 来源：真人录音审核带（2026-09-23 录制）切片；全部标准普通话、单人、无 BGM",
           "> 用法：H3 生成时挂 `ref_audio_N`；**角色对应为 AI 推断，请宝哥人耳核准**", "",
           "| 文件 | 源 | 时间 | 内容 | 推断角色 |", "|---|---|---|---|---|"]
    for name, src, t, text, role in rows:
        idx.append(f"| {name}.mp3 | {src} | {t} | {text} | {role} |")
    idx += ["", "## 已用于", "- T18：w01_foreign_male（主角）——口音略重、清晰度一般，宜作'特色老外'",
            "", "## 缺口", "- 100 角色仍缺真人样本：优先补核心卡司/各组主角（可用 H3 现有样本过渡）",
            "- 外部真人素材下载通道：YouTube 403 / B站 412（已试），备选=播客 RSS 直连"]
    (OUT / "INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print(f"\n✓ 建库完成：{len(rows)} 个样本 → {OUT}")
    print("✓ 索引: INDEX.md")


if __name__ == "__main__":
    main()
