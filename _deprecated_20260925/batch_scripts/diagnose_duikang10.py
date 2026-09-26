"""D2 十连 — 全面诊断：字幕时间轴偏差 + 台词逐句差异（word-level）

用法： .venv/Scripts/python.exe tools/diagnose_duikang10.py [uid ...]
产出： state/diagnose_duikang10.json + 控制台逐条报告

诊断 3 件事：
  A. 台词表 vs 实际转写：漏句 / 多句 / 顺序错（difflib SequenceMatcher 差异块）
  B. 字幕时间轴偏差：拿逐字时间戳把"我的 SRT 行"映射到实际语音位置，算提前/滞后
  C. 每镜实际语音时长 vs 台词分配（看是否挤在某一镜）
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from faster_whisper import WhisperModel  # noqa: E402
from prep_duikang10 import SCRIPTS, TITLES  # noqa: E402


def cjk(x: str) -> str:
    return re.sub(r"[^\u3400-\u9fff0-9a-zA-Z]", "", x)


def read_srt(p: Path) -> list[tuple[float, float, str]]:
    if not p.exists():
        return []
    rows = []
    for block in re.split(r"\n\s*\n", p.read_text(encoding="utf-8").strip()):
        ls = block.strip().splitlines()
        if len(ls) >= 3 and "-->" in ls[1]:
            a, b = [x.strip() for x in ls[1].split("-->")]
            def _p(ts):
                hh, mm, rest = ts.split(":"); ss, ms = rest.split(",")
                return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000
            rows.append((_p(a), _p(b), "".join(ls[2:])))
    return rows


def main() -> None:
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    uids = only if only else [s["uid"] for s in SCRIPTS]
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    report = {}

    for uid in uids:
        s = next(x for x in SCRIPTS if x["uid"] == uid)
        video = ROOT / f"out/gen_job_{uid}/onetake_trim.mp4"
        if not video.exists():
            video = ROOT / f"out/gen_job_{uid}/onetake.mp4"
        if not video.exists():
            print(f"✗ {uid} 无视频"); continue
        lines_exp = [t for sh in s["shots"] for _, t in sh["lines"]]
        srt = read_srt(ROOT / f"out/gen_job_{uid}/onetake_trim.srt")

        segs, _ = model.transcribe(str(video), language="zh", vad_filter=True, word_timestamps=True)
        segs = list(segs)
        # 逐字序列（带时间）
        words = []
        for sg in segs:
            for w in (sg.words or []):
                for ch in cjk(w.word):
                    words.append((ch, w.start, w.end))
        got = "".join(c for c, _, _ in words)
        exp = cjk("".join(lines_exp))

        print(f"\n{'=' * 62}\n▶ {uid} {TITLES[uid]}  时长 {words[-1][2] if words else 0:.1f}s"
              f"｜台词 {len(lines_exp)} 句 {len(exp)} 字｜转写 {len(segs)} 段 {len(got)} 字")

        rep = {"title": TITLES[uid], "n_lines": len(lines_exp), "n_segs": len(segs),
               "exp_chars": len(exp), "got_chars": len(got), "issues": [], "srt_shift": []}

        # ── A. 台词差异（difflib 差异块）
        sm = SequenceMatcher(None, exp, got, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            e, g = exp[i1:i2], got[j1:j2]
            kind = {"delete": "漏字(台词有实际无)", "insert": "多字(实际有台词无)",
                    "replace": "错字/错序"}[tag]
            if len(e) + len(g) >= 2:
                rep["issues"].append({"kind": kind, "expect": e[:40], "actual": g[:40],
                                      "exp_pos": i1})
                print(f"  【{kind}】期望「{e[:30]}」 实际「{g[:30]}」")

        # ── B. 字幕时间轴偏差：把 SRT 行的文本映射到逐字时间
        def shift_of(rows):
            out = []
            for a, b, text in rows:
                key = cjk(text)
                if not key:
                    continue
                best, best_r = None, 0.0
                for st in range(0, max(1, len(words) - len(key) + 1)):
                    cand = "".join(c for c, _, _ in words[st:st + len(key)])
                    r = SequenceMatcher(None, cand, key).ratio()
                    if r > best_r:
                        best_r, best = r, st
                if best is None or best_r < 0.5:
                    continue
                rs = words[best][1]
                re_ = words[min(best + len(key) - 1, len(words) - 1)][2]
                out.append({"line": text, "srt": [round(a, 2), round(b, 2)],
                            "real": [round(rs, 2), round(re_, 2)], "shift": round(rs - a, 2),
                            "match": round(best_r, 2)})
            return out

        for a, b, text in srt:
            key = cjk(text)
            if not key:
                continue
            break  # 已用函数统一计算
        rep["srt_shift"] = shift_of(srt)

        # ── B2. 修复后路径的偏差：优先读字级对齐产物 onetake_words.srt（现行），退回段级 DP
        words_srt = ROOT / f"out/gen_job_{uid}/onetake_words.srt"
        if words_srt.exists():
            rep["srt_shift_dp"] = shift_of(read_srt(words_srt))
            rep["dp_rows"] = len(rep["srt_shift_dp"])
            rep["dp_kind"] = "字级对齐"
        try:
            import sys as _s
            _s.path.insert(0, str(ROOT / "s5_compose"))
            import burn_subtitles as B
            segs_dict = [{"start": sg.start, "end": sg.end, "text": sg.text} for sg in segs]
            aligned = B._try_align(segs_dict, lines_exp)
            segs_a, texts_a = aligned if aligned else (segs_dict, None)
            rows_dp = B._no_overlap(B._explode_rows(segs_a, texts_a, max_chars=10))
            if not rep.get("srt_shift_dp"):
                rep["srt_shift_dp"] = shift_of(rows_dp)
                rep["dp_rows"] = len(rows_dp)
                rep["dp_kind"] = "DP段级"
        except Exception as e:
            rep["srt_shift_dp"] = []
            print("  DP 路径异常:", str(e)[:120])

        if rep["srt_shift"]:
            shifts = [abs(x["shift"]) for x in rep["srt_shift"]]
            big = [x for x in rep["srt_shift"] if abs(x["shift"]) >= 0.8]
            print(f"  【字幕偏差】{len(rep['srt_shift'])} 行｜平均 {sum(shifts)/len(shifts):.2f}s"
                  f"｜最大 {max(shifts):.2f}s｜偏差≥0.8s 的行：{len(big)}")
            for x in big[:6]:
                print(f"     · 「{x['line'][:14]}」字幕{x['srt'][0]:.1f}s → 实际{x['real'][0]:.1f}s"
                      f"（差 {x['shift']:+.2f}s）")
        if rep.get("srt_shift_dp"):
            dp = rep["srt_shift_dp"]
            dsh = [abs(x["shift"]) for x in dp]
            db = sum(1 for x in dp if abs(x["shift"]) >= 0.8)
            print(f"  【修复后·{rep.get('dp_kind', 'DP')}】{len(dp)} 行（原 {len(rep['srt_shift'])} 行）｜平均 {sum(dsh)/len(dsh):.2f}s"
                  f"｜最大 {max(dsh):.2f}s｜偏差≥0.8s：{db} 行"
                  f"  → {'✅ 明显改善' if db < sum(1 for x in rep['srt_shift'] if abs(x['shift'])>=0.8) else '⚠️ 未改善'}")
        report[uid] = rep

    (ROOT / "state/diagnose_duikang10.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✓ 已存 state/diagnose_duikang10.json（{len(report)} 条）")


if __name__ == "__main__":
    main()
