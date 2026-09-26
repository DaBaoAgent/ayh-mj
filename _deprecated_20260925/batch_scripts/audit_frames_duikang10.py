"""短剧狗血10连 — 成片画面批量判读（抽帧卡 → ask_img/deepseek 读图）

用法： .venv/Scripts/python.exe tools/audit_frames_duikang10.py [uid ...]
产出： state/frames/card_<uid>.png + state/audit_duikang10.json + 控制台摘要

判读 4 项（技能验收铁律）：
  ① 人数/复制人 ② 电动 or 手动轮椅 ③ 本条关键对抗动作是否出现 ④ 表情是否激烈
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv/Scripts/python.exe")

# 每条的关键对抗动作（写进问题里逐条问）
KEY_ACTION = {
    "D2_01_yeshi": "男子伸臂拦在车前、手拍车座、老人把纸箱摞上车、老人一屁股坐上轮椅",
    "D2_02_menkou": "妇女张开双臂挡在车前、男孩突然从校门跑出来横穿车前、老人双手抬起离开车把",
    "D2_03_laonian": "老头一巴掌按在车头、老太太拍开他的手、老头坐上坐垫、老头赖在车上不下来",
    "D2_04_daba": "司机手臂横挡在车与行李舱之间、老人单手把轮椅提离地面、司机弯腰看显示屏",
    "D2_05_banjia": "搬运工把手推车墩在地上、把纸箱抡上轮椅、有人端着一杯水、轮椅碾过门槛、水面平稳",
    "D2_06_chalou": "有人抬脚踢车轮、有人手持小钉子按在轮胎上、有人蹲下双手按轮胎",
    "D2_07_miaohui": "年轻人张开双臂挡在车前、轮椅以很慢速度贴近他小腿停下、年轻人侧身让路并掏手机拍",
    "D2_08_yutian": "有人在雨中打伞伸臂拦车、老人双手抬离车把、轮椅后方的红色尾灯亮起、有人弯腰凑近看尾灯",
    "D2_09_luying": "男孩张开双臂拦车、老人把轮椅一秒折叠收起、折叠后轮椅竖立站在地面上、老人单手拎起折叠车放进后备箱",
    "D2_10_muqin": "女儿双手举高拦车、妈妈开出院门又开回来、女儿双手叉腰瞪视、女儿弯腰看屏、女儿双手举起投降",
}

PROMPT = (
    "这是同一条15秒广告的8格分镜抽帧（横排，从左到右按时间顺序）。请只回答以下4点，每点一到两句话，"
    "不要复述画面细节：\n"
    "1) 人数：画面里有几个人？是否出现两个长相完全相同的人（复制人）？\n"
    "2) 轮椅类型：是电动轮椅（有操纵杆、银灰色车架、红色弹簧、黑色坐垫）还是手动轮椅（大圈手推轮）？\n"
    "3) 关键动作：有没有出现这些动作——{action}？逐个说'出现/未出现'。\n"
    "4) 表情：人物表情是否激烈（瞪眼、张大嘴、仰头、惊讶退缩）？还是只是平静说话？\n"
)


def main() -> None:
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.path.insert(0, str(ROOT / "tools"))
    from prep_duikang10 import SCRIPTS, TITLES
    uids = only if only else [s["uid"] for s in SCRIPTS]
    results = {}
    for uid in uids:
        video = ROOT / f"out/gen_job_{uid}/onetake.mp4"
        card = ROOT / f"state/frames/card_{uid}.png"
        if not video.exists():
            print(f"✗ {uid} 无成片"); continue
        if not card.exists():
            subprocess.run([PY, str(ROOT / "tools/frames_card.py"), str(video),
                            "--shots", "0-4,4-8,8-11,11-14.5", "--out", str(card)],
                           capture_output=True, text=True, encoding="utf-8")
        q = PROMPT.format(action=KEY_ACTION[uid])
        r = subprocess.run([PY, str(ROOT / "tools/ask_img.py"), str(card), "--ch", "deepseek", q],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        txt = (r.stdout or "") + (r.stderr or "")
        # ask_img 空 content 时打印 reasoning 尾部，取有效正文
        body = txt.split("reasoning 尾部:")[-1].strip() if "reasoning 尾部:" in txt else txt.strip()
        results[uid] = {"title": TITLES[uid], "raw": body[-3000:]}
        print(f"\n{'=' * 60}\n▶ {uid} {TITLES[uid]}\n{body[-1600:]}")
    (ROOT / "state/audit_duikang10.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✓ 已存 state/audit_duikang10.json（{len(results)} 条）")


if __name__ == "__main__":
    main()
