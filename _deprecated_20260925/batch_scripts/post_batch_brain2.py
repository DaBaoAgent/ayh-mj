"""脑洞10连第二批 — 批量后期（trim → SRT → 烧字幕 → BGM/音效 → 归档）

依赖：
- state/batch_brain2_transcripts.json（转写验收结果，用于对比）
- state/batch_brain2_bgm.json（BGM 分配）
- tools/brain2_data.py（原始台词，SRT 文本用原文避免错字）
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from brain2_data import SCRIPTS  # noqa: E402

PY = str(ROOT / ".venv/Scripts/python.exe")
BGM = json.loads((ROOT / "state/batch_brain2_bgm.json").read_text(encoding="utf-8"))["assignments"]

UIDS = [
    "B2_01_kuaidi", "B2_02_diaoyu", "B2_03_luying", "B2_04_chongdian", "B2_05_xueche",
    "B2_06_zhaiXiang", "B2_07_jiedian", "B2_08_nianhuo", "B2_09_xiuche", "B2_10_jiaoChe",
]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def main() -> None:
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    todo = only if only else UIDS
    for uid in todo:
        s = next(x for x in SCRIPTS if x["uid"] == uid)
        g = ROOT / f"out/gen_job_{uid}"
        src = g / "onetake.mp4"
        if not src.exists():
            print(f"✗ {uid} 缺文件，跳过"); continue
        print(f"\n{'='*50}\n▶ {uid} {s['title']}")

        # 1) trim（若无需裁剪则复制原片作为 trim 版）
        if not (g / "onetake_trim.mp4").exists():
            r = run([PY, str(ROOT / "tools/trim_onetake.py"), str(src), "--apply"])
            print("  trim:", r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-120:])
        if not (g / "onetake_trim.mp4").exists():
            shutil.copy(src, g / "onetake_trim.mp4")
            print("  trim: 无裁剪，已复制原片为 trim 版")

        # 2) 转写 trim 版（small 快）
        tr_dir = g / "transcripts"
        tr_dir.mkdir(exist_ok=True)
        trj = tr_dir / "onetake_trim.json"
        if not trj.exists():
            run([PY, str(ROOT / "tools/transcribe_local.py"), str(g / "onetake_trim.mp4")], timeout=900)

        # 3) 对齐生成 SRT（转写段 vs 原始句——贪心对齐+段内按字数比例拆分）
        import re as _re
        from faster_whisper import WhisperModel
        lines_all = [t for sh in s["shots"] for _, t in sh["lines"]]
        model = WhisperModel("medium", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(g / "onetake_trim.mp4"), language="zh", vad_filter=True)
        segs = list(segs)
        print(f"  转写 {len(segs)} 段 vs 台词 {len(lines_all)} 句")

        def _cjk(x: str) -> int:
            return len(_re.findall(r"[\u3400-\u9fff]", x))

        if len(segs) == len(lines_all):
            srt_rows = [(sg.start, sg.end, txt) for sg, txt in zip(segs, lines_all)]
        else:
            # 贪心：转写段 i 覆盖台词句子 [cur, cur+n)，按每段实际字数贴近
            seg_chars = [max(_cjk(sg.text), 1) for sg in segs]
            line_chars = [max(_cjk(li), 1) for li in lines_all]
            cur = 0
            srt_rows = []
            for i, sg in enumerate(segs):
                acc, group = 0, []
                while cur < len(lines_all) and (acc < seg_chars[i] or not group):
                    acc += line_chars[cur]; group.append(cur); cur += 1
                if not group:
                    group = [min(cur, len(lines_all) - 1)]
                # 段内多句按字数比例拆分时间
                total = sum(line_chars[c] for c in group)
                t = sg.start
                span = sg.end - sg.start
                for c in group:
                    share = span * line_chars[c] / total
                    srt_rows.append((round(t, 2), round(t + share, 2), lines_all[c]))
                    t += share
            if len(srt_rows) != len(lines_all):
                print(f"  ⚠️ 对齐后 {len(srt_rows)} 行 vs {len(lines_all)} 句——需人工复核")

        def ts(t: float) -> str:
            h, r = divmod(t, 3600); m, sec = divmod(r, 60)
            return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int((t%1)*1000):03d}"

        srt_path = g / "onetake_trim.srt"
        srt_path.write_text("\n".join(
            f"{i+1}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(srt_rows)), encoding="utf-8")

        # 4) 烧字幕（动效）
        fx = g / "onetake_trim_fx.mp4"
        if not fx.exists():
            r = run([PY, str(ROOT / "s5_compose/burn_subtitles.py"), str(g / "onetake_trim.mp4"),
                     "--srt", str(srt_path), "--suffix", "_fx"])
            out = (r.stdout or "") + (r.stderr or "")
            print("  burn:", "✓" if "成片" in out or fx.exists() else out[-200:])

        # 5) BGM + 音效（audio_polish 固定输出：_trim_fx → _fx_polished）
        bgm_file = ROOT / "assets/bgm_trending" / BGM[uid]["bgm"]
        final = g / "onetake_fx_polished.mp4"
        r = run([PY, str(ROOT / "tools/audio_polish.py"), str(fx),
                 "--bgm", str(bgm_file), "--sfx",
                 "--transcripts", str(trj)])
        out = (r.stdout or "") + (r.stderr or "")
        print("  polish:", out.strip().splitlines()[-1] if out.strip() else "⚠️无输出")

        # 6) 归档
        if final.exists():
            dst = ROOT / "out/approved" / f"B2_{uid.split('_')[1]}_{s['title']}_20260925.mp4"
            shutil.copy(final, dst)
            print(f"  ✅ 归档 {dst.name}")
        else:
            print(f"  ✗ {uid} 最终文件缺失")

    print("\n全部处理完成")


if __name__ == "__main__":
    main()
