"""播客批量采集 → 真人样本库（故事FM/老外你好 等）

流程：下载音频 → whisper 扫前段 → 找"连续单人说话 ≥12s"→ 切 13s 样本 → real/
用法: .venv/Scripts/python.exe tools/podcast_voice_harvest.py [--dry]
可反复运行：已下载/已切片的自动跳过；新 URL 加进 TASKS 即可
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.tools import ffmpeg

VOICES = ROOT / "out/voices"
REAL = ROOT / "assets/cast/voice/real"
REAL.mkdir(parents=True, exist_ok=True)
STATE = ROOT / "state/podcast_harvest.json"

# (url, 标签, 备注)  —— 故事FM 12集 + 老外你好 6集 + 人生杂叙
TASKS = [
    ("https://tk.wavpub.com/WPTK_PmpVcJJN000XVmFW.mp3", "storyfm_a", "故事FM"),
    ("https://tk.wavpub.com/WPTK_SkGhvd0RXWSWi2ER.mp3", "storyfm_b", "故事FM"),
    ("https://tk.wavpub.com/WPTK_VqokI7CW1K2MrcZx-870b076ab65c.mp3", "storyfm_c", "故事FM"),
    ("https://tk.wavpub.com/WPTK_cBaRUZ7ySOFKeoEO-e5bdfe02241a.mp3", "storyfm_d", "故事FM"),
    ("https://tk.wavpub.com/WPTK_B8tuq0hHCMCCF4JR-f09a58c091d3.mp3", "storyfm_e", "故事FM"),
    ("https://tk.wavpub.com/WPTK_ohmbxuv6aW5eRAg4-78ba3f9929a0.mp3", "storyfm_f", "故事FM"),
    ("https://tk.wavpub.com/WPTK_RlkZId12zklhXxmv-ced65a22f1ec.mp3", "storyfm_g", "故事FM"),
    ("https://tk.wavpub.com/WPTK_KmjXn4bA4N3DoxC9-ab626171fec3.mp3", "storyfm_h", "故事FM"),
    ("https://tk.wavpub.com/WPTK_LZ0JlbJ9Qhj8Z6Mw-46a6c3cb1c88.mp3", "storyfm_i", "故事FM"),
    ("https://tk.wavpub.com/WPTK_Dj9lHx9c4RqxBNZV-90cc6c6cad83.mp3", "storyfm_j", "故事FM"),
    ("https://tk.wavpub.com/WPTK_K01WS8JEz40T9NIN-b819ec4de99b.mp3", "storyfm_k", "故事FM"),
    ("https://tk.wavpub.com/WPTK_3xDdjckBpplKTtQW-37afba1192ed.mp3", "storyfm_l", "故事FM"),
    ("https://aod.cos.tx.xmcdn.com/group9/M09/42/4E/wKgDZlWjEQ7iZdUiANbATBl9gz0509.m4a", "laowai_1", "老外你好"),
    ("https://aod.cos.tx.xmcdn.com/group11/M00/25/AE/wKgDa1WBNK_TSepbAO8k8sY7dkc167.m4a", "laowai_2", "老外你好"),
    ("https://aod.cos.tx.xmcdn.com/group3/M0A/67/A6/wKgDsVNojh3hepPbAmNQAezH3b8351.mp3", "laowai_3", "老外你好"),
    ("https://aod.cos.tx.xmcdn.com/group11/M04/1F/E8/wKgDa1V63wqCPFcZAOwFnBCbduI167.m4a", "laowai_4", "老外你好"),
    ("https://aod.cos.tx.xmcdn.com/group4/M00/35/D0/wKgDs1NDccrAL8J3Amq-3LIND3k783.mp3", "laowai_5", "老外你好"),
    ("https://aod.cos.tx.xmcdn.com/group15/M02/4B/53/wKgDaFWumbDRaJ8yACVxY5Crs-g239.m4a", "laowai_6", "老外你好"),
    ("https://aod.cos.tx.xmcdn.com/storages/6759-audiofreehighqps/82/52/GKwRIasLLwcTABkOsAM-rE4c.m4a", "storyfm_xm", "人生杂叙(xm)"),
    # 二批：一席/白金时代/银发世代
    ("https://dts-api.xiaoyuzhoufm.com/track/5e285326418a84a04627343f/6ab23744f04646b3a955652e/media.xyzcdn.net/5e285326418a84a04627343f/lo8SlDF_lcRs3zCIZHbQGRTJP1lO.m4a", "yixi_1", "一席"),
    ("https://dts-api.xiaoyuzhoufm.com/track/5e285326418a84a04627343f/6aaa7b029d326477816a22f9/media.xyzcdn.net/5e285326418a84a04627343f/lmXDROfOTKshqpa4UHk-AmdtNNGn.m4a", "yixi_2", "一席"),
    ("https://dts-api.xiaoyuzhoufm.com/track/5e285326418a84a04627343f/6aa12f789d32647781668a98/media.xyzcdn.net/5e285326418a84a04627343f/lmbCbmks9n8UpQO6o6tXb8p9Awf-.m4a", "yixi_3", "一席"),
    ("https://dts-api.xiaoyuzhoufm.com/track/5e285326418a84a04627343f/6a981ee8a0210c197dcc65f9/media.xyzcdn.net/5e285326418a84a04627343f/lnFz9Il0aSeKkc2amesyXhP28Pl1.m4a", "yixi_4", "一席"),
    ("https://dts-api.xiaoyuzhoufm.com/track/67889f271fcebeacba1da6ea/6a737235ab3a91c24a1075ba/media.xyzcdn.net/67889f271fcebeacba1da6ea/lqY8rkXoZZBy1JWPg_KbIFd9Zoqj.m4a", "baijin_1", "白金时代"),
    ("https://dts-api.xiaoyuzhoufm.com/track/67889f271fcebeacba1da6ea/6a736ccd1b5e24969ce992a9/media.xyzcdn.net/67889f271fcebeacba1da6ea/lm1PvrEDz00aQ-dqUygscpE0gEcL.m4a", "baijin_2", "白金时代"),
    ("https://dts-api.xiaoyuzhoufm.com/track/67889f271fcebeacba1da6ea/6a68ddf9b581962ce2bcff58/media.xyzcdn.net/67889f271fcebeacba1da6ea/lqgG-xK1Ejg2ba1-S0tHtG5yfhcA.m4a", "baijin_3", "白金时代"),
    ("https://aod.cos.tx.xmcdn.com/storages/19a0-audiofreehighqps/E9/BF/GKwRIaIIiXeDABoffwI48gmm.m4a", "yinf a_1".replace(" ", ""), "银发世代"),
    ("https://aod.cos.tx.xmcdn.com/storages/e7ab-audiofreehighqps/44/0D/GKwRIUEIiXegAIF_oAI48hfm.m4a", "yifa_2", "银发世代"),
    ("https://aod.cos.tx.xmcdn.com/storages/f13f-audiofreehighqps/79/AB/GKwRIRwIiXefAEmoZwI48he7.m4a", "yifa_3", "银发世代"),
]

MIN_LEN = 11.0


def bad_text(t: str) -> bool:
    """质量过滤：中文占比低 / 重复词乱码 / 太短"""
    from collections import Counter
    t2 = t.replace(" ", "")
    if len(t2) < 8:
        return True
    cn = sum(1 for c in t2 if "\u4e00" <= c <= "\u9fff")
    if cn / len(t2) < 0.55:
        return True  # 英文段/外语段
    grams = [t2[i:i + 2] for i in range(len(t2) - 1)]
    if grams and Counter(grams).most_common(1)[0][1] >= 4:
        return True  # 复读/乱码
    return False


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save_state(d: dict) -> None:
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def find_windows(segs, scan_end: float):
    """返回 [(start, dur, text)] 候选窗口（连续说话，间隔<1.6s，时长 11~16s）"""
    out = []
    i = 0
    while i < len(segs):
        j = i
        while j + 1 < len(segs) and (segs[j + 1].start - segs[j].end) < 1.6:
            j += 1
        span = segs[j].end - segs[i].start
        if MIN_LEN <= span <= 17 and segs[i].start < scan_end:
            out.append((segs[i].start, min(13.0, span), " ".join(s.text.strip() for s in segs[i:j+1])))
        i = j + 1
    return out


def density_windows(segs, scan_end: float):
    """fallback：滑窗找语音密度最高、且时长≥11s 的 13s 窗口（适配访谈/对话间隙大的节目）"""
    import math
    best = None
    t_end = min(scan_end, max((s.end for s in segs), default=0) - 13)
    t0 = 0.0
    while t0 < t_end:
        t1 = t0 + 13.0
        spoken = sum(max(0.0, min(s.end, t1) - max(s.start, t0)) for s in segs if s.end > t0 and s.start < t1)
        txt = " ".join(s.text.strip() for s in segs if s.start >= t0 - 0.5 and s.end <= t1 + 0.5)
        if spoken >= 8.5 and not bad_text(txt):
            score = spoken
            if best is None or score > best[0]:
                best = (score, t0, txt)
        t0 += 1.0
    if best:
        return [(best[1], 13.0, best[2])]
    return []


def main(dry: bool = False) -> None:
    from faster_whisper import WhisperModel
    model = None
    state = load_state()

    for url, tag, note in TASKS:
        st = state.get(tag, {})
        if st.get("done") and st.get("made"):
            print(f"⏭ {tag} 已处理", flush=True)
            continue
        src = VOICES / f"pod_{tag}.mp3"
        if not src.exists():
            print(f"⬇ 下载 {tag} ...", flush=True)
            if dry:
                continue
            r = subprocess.run(["curl", "-sL", "-m", "280", "-o", str(src), url], capture_output=True)
            if not src.exists() or src.stat().st_size < 50000:
                print(f"  ✗ 下载失败 {tag}", flush=True)
                continue
        print(f"🎧 {tag}: 裁前10分钟 → 转写扫段 ...", flush=True)
        if model is None:
            model = WhisperModel("base", device="cpu", compute_type="int8")
        scan = VOICES / f"scan_{tag}.mp3"
        if not scan.exists():
            subprocess.run([ffmpeg(), "-y", "-t", "600", "-i", str(src), "-ar", "16000", "-ac", "1", str(scan)],
                           capture_output=True)
        segs, info = model.transcribe(str(scan), language="zh", vad_filter=False, condition_on_previous_text=False)
        segs = [s for s in segs if s.start < 600]  # 只扫前 10 分钟
        wins = find_windows(segs, scan_end=560)
        if not wins:
            wins = density_windows(segs, scan_end=560)  # fallback：密度滑窗
        picked = [w for w in wins if not bad_text(w[2])][:2]  # 质量过滤后取前 2 个
        made = []
        for k, (ss, dur, text) in enumerate(picked, 1):
            out = REAL / f"p_{tag}_{k}.mp3"
            subprocess.run([ffmpeg(), "-y", "-ss", f"{ss:.2f}", "-t", f"{dur:.2f}", "-i", str(src),
                            "-af", "loudnorm=I=-18:TP=-2:LRA=9", "-ar", "32000", "-ac", "1", "-b:a", "96k", str(out)],
                           capture_output=True)
            if out.exists():
                made.append({"file": out.name, "text": text[:60], "len": round(dur, 1), "from": note})
                print(f"  ✓ {out.name} ({dur:.1f}s) {text[:40]}", flush=True)
        state[tag] = {"done": True, "made": made}
        save_state(state)

    # 汇总
    total = len(list(REAL.glob("*.mp3")))
    print(f"\n✓ 本批完成。样本库现有 {total} 个样本")


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
