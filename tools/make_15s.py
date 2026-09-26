"""15 秒软广产线（ayh-mj）— 一条命令：从对白到成片归档

把 2026-09-25/26 手工跑通的链路（W2《车会说话》/ W3《轮椅组就您一个人》/ W4《鸽子都比您这车快》）
固化为单一入口，内置全部已知坑位。

两种模式
────────────────────────────────────────────────────────────
① 造脚本（4 镜 8 句对撞结构模板）
   python tools/make_15s.py new --uid W5_xxx --lines 对白.txt --shots 分镜.txt \
       --cast-a fashion_girl_sporty --cast-b fashion_western_grandpa --scene "英文场景句"
   对白.txt：8 行 = 4 镜 × 2 句（奇=对手 S1，偶=车主 S2，自动分配）
   分镜.txt：4 段英文画面描述（一段一行）
   → 产出 spec + 门禁(0 ERROR 拦截) + 字数校验(65-72 纯汉字) + 撞车自检

② 出片（生成 → 后期 → 验收 → 归档，全自动）
   python tools/make_15s.py run state/onetake_prompt_job_W5_xxx.json [--bgm auto|曲名.mp3]
   # 已生成过、只补后期：  --skip-gen
   # 演练不花钱：          --dry
────────────────────────────────────────────────────────────
内置坑位（全部实测）：
  · 字数口径：门禁不查字数 → 自己按纯汉字 65-72 校验（口径 68-75/15s）
  · 阿拉伯数字：门禁 R18 拦截，字幕层再转回数字
  · 字幕孤行：时长<0.35s 或 ≤2 字且夹在两句之间 → 并进下一行
  · 音效：audio_polish 的 SFX_RULES 对无标点转写失效 → 本工具按 SRT 节拍自混（素材先归一化电平）
  · 音效电平：ding/whoosh/pop 素材仅 -25dB → 混音前必须 +19~26dB，混后 alimiter
  · 归档：rename_approved 统一「序号 主体.mp4」+ 桌面同步
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LIB = "assets/cast/library"
VOICE_DIR = "assets/cast/voice/real"
PROD = ROOT / "assets/products"
REFS_TAIL = [PROD / "折叠-无阴影.png", PROD / "正侧-3-无阴影.png", PROD / "45度-加水杯-无阴影.png"]
MIN_CJK, MAX_CJK = 65, 72
PROMPT_MAX, PROMPT_SAFE = 10000, 9800   # H3 prompt 硬上限 / 安全线（2026-09-26 实测）

# ── 音效：按 SRT 节拍自动选点（三类各一 + 品牌前一拍）──
SFX_PLAN = [
    ("赌约", 4, "ding.mp3", 20),    # 第 4 句起点（赌注钉死）
    ("崩溃", 5, "whoosh.mp3", 26),  # 第 5 句起点（力竭求饶）
    ("兑现", 7, "pop.mp3", 24),     # 第 7 句起点（打脸动作/兑现赌注）
    ("品牌", 8, "pop.mp3", 17),     # 第 8 句起点（品牌句）
]


def run(cmd, **kw):
    cmd = [str(c) for c in cmd]
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def cjk_count(s: str) -> int:
    return len(re.sub(r"[^\u4e00-\u9fff]", "", s))


def load_lines(uid: str) -> list[str]:
    p = ROOT / f"docs/onetake_lines_{uid}.txt"
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def check_dialogue(spec_path: Path) -> tuple[bool, str]:
    uid = json.loads(spec_path.read_text(encoding="utf-8"))["job_uid"]
    chk = ROOT / f"docs/onetake_check_{uid}.txt"
    r = run(["node", str(ROOT / "tools/check_dialogue.mjs"), str(chk)])
    out = (r.stdout or "").strip()
    ok = "0 ERROR" in out
    return ok, out.replace("\n", " | ")


def assert_lines(uid: str) -> tuple[bool, str]:
    """字数 + 阿拉伯数字 + 单句长度自检（门禁不查这些）"""
    lines = load_lines(uid)
    counts = [cjk_count(l) for l in lines]
    total = sum(counts)
    msgs = [f"台词 {len(lines)} 句 / 纯汉字 {total} / 单句 {counts}"]
    ok = True
    if len(lines) != 8:
        msgs.append(f"✗ 句数 {len(lines)} ≠ 8（4 镜 × 2 句）")
        ok = False
    if not (MIN_CJK <= total <= MAX_CJK):
        msgs.append(f"✗ 纯汉字 {total} 不在 {MIN_CJK}-{MAX_CJK}（15s 档）")
        ok = False
    long = [c for c in counts if c > 13]
    if long:
        msgs.append(f"✗ 单句超 13 字：{long}（H3 易念断/丢句）")
        ok = False
    if any(re.search(r"[0-9]", l) for l in lines):
        msgs.append("✗ 台词含阿拉伯数字（门禁 R18）→ 改中文读法")
        ok = False
    return ok, " ｜ ".join(msgs)


# ── 模式①：造脚本 ───────────────────────────────────────────
def cmd_new(a) -> int:
    uid = a.uid
    lines = [l.strip() for l in Path(a.lines).read_text(encoding="utf-8").splitlines() if l.strip()]
    shots = [l.strip() for l in Path(a.shots).read_text(encoding="utf-8").splitlines() if l.strip()]

    def cast_block(img: str, voice: str, desc: str, short: str, vnote: str):
        return {"short": short, "img": f"{LIB}/{img}.png", "audio": f"{VOICE_DIR}/{voice}",
                "desc": desc, "voice": vnote or "a clear, natural speaking voice, age-appropriate"}

    cast_a = cast_block(a.cast_a, a.voice_a, a.desc_a, a.short_a, a.voice_note_a)
    cast_b = cast_block(a.cast_b, a.voice_b, a.desc_b, a.short_b, a.voice_note_b)

    from lib import prompt_parts as pp

    cast_txt = (
        "CAST (STRICTLY BIND — exactly 2 people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned, mirrored or twinned into a second similar figure; no extra "
        "bystanders, no crowd): " + a.cast_note + "\n"
        f"- (S1) {cast_a['desc']}, exactly as in reference image 1. VOICE (S1): {cast_a['voice']} (reference audio 1).\n"
        f"- (S2) {cast_b['desc']}, exactly as in reference image 2. VOICE (S2): {cast_b['voice']} (reference audio 2).\n"
        "The two voices are clearly DIFFERENT in pitch and age; never swap them.\n"
        + (a.wheel.strip() + "\n" if a.wheel else "")
    )

    times = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]
    shots_txt = ""
    for i in range(4):
        pair = lines[i * 2:i * 2 + 2]
        seg = f"[Shot {i + 1}, {times[i]}] {shots[i] if i < len(shots) else 'Shot description missing.'} "
        for j, text in enumerate(pair):
            who = "S1" if j == 0 else "S2"
            short = cast_a["short"] if j == 0 else cast_b["short"]
            verb = "says" if j == 0 else "replies"
            seg += f"({who}) the {short} {verb}: <d>[Chinese] {text}</d> "
        seg += "ONLY the speaker's mouth moves; the other person's lips stay completely closed. "
        if i < 3:
            seg += "Hard cut. "
        shots_txt += seg + "\n\n"

    prompt = pp.compose(
        shots=shots_txt, cast=cast_txt, soundscape=a.soundscape,
        extra_tail=a.extra_tail or (
            "The grandpa drives the wheelchair smoothly, steadily and never wobbling; the other person never "
            "touches or pushes the moving wheelchair."),
    )
    refs = [str(ROOT / cast_a["img"]), str(ROOT / cast_b["img"])] + [str(p) for p in REFS_TAIL]
    spec = {
        "job_uid": uid, "title": a.title or uid, "template_id": "manual", "template_name": "manual", "mode": "manual",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s", "fallback_workflows": [],
        "duration": 15, "resolution": "768p竖",
        "ref_images": refs,
        "ref_audios": [str(ROOT / cast_a["audio"]), str(ROOT / cast_b["audio"])],
        "prompt": prompt, "lines_meta": [],
    }
    (ROOT / f"state/onetake_prompt_job_{uid}.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / f"docs/onetake_check_{uid}.txt").write_text(prompt, encoding="utf-8")
    (ROOT / f"docs/onetake_lines_{uid}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    miss = [p for p in spec["ref_images"] + spec["ref_audios"] if not Path(p).exists()]
    ok_lines, msg_lines = assert_lines(uid)
    ok_gate, msg_gate = check_dialogue(ROOT / f"state/onetake_prompt_job_{uid}.json")

    print(f"✓ spec: state/onetake_prompt_job_{uid}.json（图 {len(refs)} / 音 2）")
    if miss:
        print("✗ 缺失素材:", miss)
    print(("✓ " if ok_lines else "⚠ ") + msg_lines)
    print(("✓ 门禁 " if ok_gate else "✗ 门禁 ") + msg_gate)
    return 0 if (not miss and ok_lines and ok_gate) else 1


# ── 模式②：出片 ────────────────────────────────────────────
def cmd_run(a) -> int:
    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    uid = spec["job_uid"]
    g = ROOT / "out" / f"gen_{uid}"
    raw, trim = g / "onetake.mp4", g / "onetake_trim.mp4"
    sub, clip, final = g / "onetake_trim_sub.mp4", g / "onetake_sub_polished.mp4", g / "onetake_final.mp4"
    lines_f, srt = ROOT / f"docs/onetake_lines_{uid}.txt", g / "onetake_trim.srt"
    trj = g / "transcripts" / "onetake_trim.json"
    g.mkdir(parents=True, exist_ok=True)

    steps = []
    def do(desc, fn):
        steps.append(desc)
        if a.dry:
            print(f"  (dry) {desc}")
            return True
        ok = fn()
        print(("  ✓ " if ok else "  ✗ ") + desc)
        return ok

    ok_lines, msg_lines = assert_lines(uid)
    print("【预检】" + msg_lines)
    n_prompt = len(spec.get("prompt", ""))
    ok_prompt = n_prompt <= PROMPT_SAFE
    print(f"【预检】prompt 长度 {n_prompt}/{PROMPT_MAX} 字符"
          + (" ✓" if ok_prompt else " ✗ 超限/贴近上限 → 先压缩再出片（H3 会拒收，白等）"))
    if (not ok_lines or not ok_prompt) and not a.force:
        print("✗ 预检未过（--force 可强制继续）")
        return 1
    if not g.exists():
        return 1

    # 1 生成
    def do_gen() -> bool:
        r = run([PY, str(ROOT / "s4_generate/gen_one_take.py"), str(spec_path)], timeout=3600)
        if r.returncode != 0:
            tail = (r.stdout or r.stderr or "").strip().splitlines()[-12:]
            print("    ↓ 生成器原始输出（末 12 行，勿再被吞掉）:")
            for ln in tail:
                print("      " + ln)
        return r.returncode == 0

    if not (raw.exists() and a.skip_gen):
        do("H3 生成 15s/768p（¥0.9，约 10 分钟）", do_gen)
    else:
        print("  ↻ 已有 onetake.mp4，跳过生成")

    # 2 明快档裁剪（无静默可裁时兜底复制，幂等）
    def do_trim():
        r = run([PY, str(ROOT / "tools/trim_onetake.py"), str(raw), "--apply"])
        if r.returncode != 0:
            return False
        if not trim.exists():
            trim.write_bytes(raw.read_bytes())   # trim 脚本在"无需裁剪"时不产出文件
        return True

    if not trim.exists():
        do("明快档裁剪（停顿 ≥0.35s → 0.2s）", do_trim)
    else:
        print("  ↻ 已有 onetake_trim.mp4，跳过裁剪")

    # 3 转写
    if not trj.exists():
        do("转写（faster-whisper small）",
           lambda: run([PY, str(ROOT / "tools/transcribe_local.py"), str(trim)]).returncode == 0)
    else:
        print("  ↻ 已有转写 json，跳过")

    # 4 一致性自检
    if trj.exists() and not a.dry:
        import difflib
        d = json.loads(trj.read_text(encoding="utf-8"))
        segs = d if isinstance(d, list) else d.get("segments", [])
        exp = "".join(re.sub(r"[^\u4e00-\u9fff]", "", l) for l in load_lines(uid))
        hyp = "".join(re.sub(r"[^\u4e00-\u9fff]", "", s.get("text", "")) for s in segs)
        ratio = difflib.SequenceMatcher(None, exp, hyp).ratio()
        print(f"【验收】转写 {len(segs)} 段 vs 台词 8 句 ｜ 逐字一致率 {ratio*100:.1f}%（基线 75.4%）")
        if len(segs) < 8 or ratio < 0.6:
            print("  ⚠ 一致率或段数异常 → 建议人工看片（差异多为同音字误识）")

    # 5 字级字幕 + 孤行合并
    if not srt.exists():
        def make_srt():
            r = run([PY, str(ROOT / "tools/lines_to_srt.py"), str(trim), str(lines_f), str(srt)])
            if r.returncode != 0:
                return False
            rows, out = [], []
            for blk in srt.read_text(encoding="utf-8").strip().split("\n\n"):
                L = blk.splitlines()
                if len(L) >= 3:
                    t0, t1 = L[1].split(" --> ")
                    rows.append([t0, t1, " ".join(L[2:])])
            def sec(t):
                h, m, rest = t.split(":"); s, ms = rest.split(",")
                return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
            def fmt(x):
                h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60
                return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
            i = 0
            while i < len(rows):
                a0, a1, txt = rows[i]
                dur, n = sec(a1) - sec(a0), cjk_count(txt)
                if i + 1 < len(rows) and (dur < 0.35 or n <= 2):
                    rows[i + 1][0] = a0
                    rows[i + 1][2] = txt + rows[i + 1][2]
                    i += 1
                else:
                    out.append((a0, a1, txt)); i += 1
            srt.write_text("\n\n".join(f"{k+1}\n{a0} --> {a1}\n{t}" for k, (a0, a1, t) in enumerate(out)) + "\n",
                           encoding="utf-8")
            print(f"    字幕 {len(out)} 行（孤行已合并）")
            return True
        do("字级对齐字幕（含孤行合并）", make_srt)
    else:
        print("  ↻ 已有 SRT，跳过")

    # 6 烧字幕
    if not sub.exists():
        do("烧字幕（新青年体·无标点·关键词高亮）",
           lambda: run([PY, str(ROOT / "s5_compose/burn_subtitles.py"), str(trim), "--srt", str(srt)]).returncode == 0)
    else:
        print("  ↻ 已有带字幕版，跳过")

    # 7 BGM
    bgm = a.bgm
    if bgm == "auto":
        pool = [p for p in (ROOT / "assets/bgm_trending").glob("*.mp3") if p.stat().st_size > 200_000]
        used = set()
        for f in ROOT.glob("docs/bgm分配*.json"):
            try:
                used |= {v["bgm"] for v in json.loads(f.read_text(encoding="utf-8")).get("assignments", {}).values()}
            except Exception:
                pass
        cand = [p for p in pool if p.name not in used] or pool
        bgm = str(sorted(cand, key=lambda p: p.stat().st_size)[0])
    if not clip.exists():
        do(f"BGM 铺底（{Path(bgm).name}）",
           lambda: run([PY, str(ROOT / "tools/audio_polish.py"), str(sub), "--bgm", bgm]).returncode == 0)
    else:
        print("  ↻ 已有 BGM 版，跳过")

    # 8 音效（按台词句时间轴自动混，素材先归一化电平）
    do("音效 4 点（ding/whoosh/pop 电平归一化 + 限幅）", lambda: _mix_sfx(clip, srt, load_lines(uid), final))

    if a.dry:
        print("\n(dry) 未执行后续归档步骤")
        return 0

    # 9 抽帧验收卡
    do("抽帧验收卡（4 镜 × 2 帧）",
       lambda: run([PY, str(ROOT / "tools/frames_card.py"), str(final),
                    "--shots", "0-3.5,3.5-6.6,6.6-10.4,10.4-14.3",
                    "--out", str(g / "_frames_tmp" / "card.png")]).returncode == 0)

    # 10 归档 + 桌面同步（用中文标题，避免 rename_approved 生成拼音条目/重复号）
    title = spec.get("title") or uid
    arch = ROOT / "out/approved" / f"{title}_{_today()}.mp4"
    arch.write_bytes(final.read_bytes())
    r = run([PY, str(ROOT / "tools/rename_approved.py")])
    tail = (r.stdout or "").strip().splitlines()
    print("  ✓ 归档：" + (tail[-1] if tail else arch.name))
    r = run([PY, str(ROOT / "tools/sync_desktop.py")])
    tail = (r.stdout or "").strip().splitlines()
    print("  ✓ 桌面同步：" + (tail[-1] if tail else ""))
    print(f"\n🎬 成片：{title}（out/approved/ + 桌面，命名规则自动排号）")
    return 0


def _read_srt(srt: Path) -> list[tuple[float, float, str]]:
    def sec(t: str) -> float:
        h, m, rest = t.split(":"); s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    rows = []
    for blk in srt.read_text(encoding="utf-8").strip().split("\n\n"):
        L = blk.splitlines()
        if len(L) >= 3:
            t0, t1 = L[1].split(" --> ")
            rows.append((sec(t0), sec(t1), " ".join(L[2:])))
    return rows


def _merge_len(s: str) -> int:
    """归并用的字长：CJK 字数 + 数字串按中文读数折算（字幕层「一百」→「100」，1 串≈2 字）"""
    return cjk_count(s) + 2 * len(re.findall(r"[0-9]+", s))


def _sentence_spans(rows, lines: list[str]) -> list[tuple[float, float]]:
    """字幕行（可能被拆成 >8 行）按字数归并回 N 句 → 每句 (start, end)
    坑：① 不要用行号索引（8 句常被拆成 10-12 行）② 数字串要折算（否则「100」那行少 2 字、整条错位）"""
    need = [_merge_len(l) for l in lines]
    spans, gi, acc, start = [], 0, 0, None
    for t0, t1, txt in rows:
        if start is None:
            start = t0
        acc += _merge_len(txt)
        if gi < len(need) and acc >= max(1, need[gi] - 1):   # 留 1 字容差
            spans.append((start, t1))
            gi += 1; acc = 0; start = None
            if gi >= len(need):
                break
    while len(spans) < len(need):
        spans.append(spans[-1] if spans else (0.0, 0.0))
    return spans


def _mix_sfx(clip: Path, srt: Path, lines: list[str], final: Path) -> bool:
    """按台词句的时间轴自动插 4 个音效（素材 -25dB → 先归一化，混后限幅）"""
    from lib import tools as T
    ff = T.ffmpeg()
    spans = _sentence_spans(_read_srt(srt), lines)
    inputs, fc, labels, names = [], [], [], []
    for i, (label, k, fname, gain) in enumerate(SFX_PLAN, start=1):
        if k > len(spans):
            continue
        at = max(0.0, spans[k - 1][0] - 0.05)
        inputs += ["-i", str(ROOT / "assets/sfx" / fname)]
        pre = "highpass=f=700," if fname.startswith("ding") else ""
        ms = int(at * 1000)
        fc.append(f"[{i}:a]{pre}volume={gain}dB,adelay={ms}|{ms}[s{i}]")
        labels.append(f"[s{i}]")
        names.append(f"{label}@{at:.2f}s")
    if not labels:
        print("    ⚠ 未定位到音效点，跳过")
        return False
    fc.insert(0, "[0:a]volume=-1dB[base]")
    fc.append(f"[base]{''.join(labels)}amix=inputs={len(labels)+1}:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    cmd = [ff, "-y", "-i", str(clip)] + inputs + ["-filter_complex", ";".join(fc),
           "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(final)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode == 0:
        print("    音效点：" + ", ".join(names))
    return r.returncode == 0


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d")


def main() -> None:
    ap = argparse.ArgumentParser(prog="make_15s", description="15 秒软广产线")
    sub = ap.add_subparsers(dest="mode", required=True)

    n = sub.add_parser("new", help="造脚本（4 镜 8 句对撞结构）")
    n.add_argument("--uid", required=True)
    n.add_argument("--title", default="", help="成片中文标题（归档名用，如「鸽子都比您这车快」）")
    n.add_argument("--lines", required=True, help="对白文件：8 行（奇=对手 S1 / 偶=车主 S2）")
    n.add_argument("--shots", required=True, help="分镜文件：4 行英文画面描述")
    n.add_argument("--cast-a", required=True, help="对手角色 id（library 文件名，无 .png）")
    n.add_argument("--cast-b", required=True, help="车主角色 id")
    n.add_argument("--voice-a", required=True, help="对手音色（real/ 下文件名）")
    n.add_argument("--voice-b", required=True, help="车主音色")
    n.add_argument("--scene", default="", help="英文场景句（写进 soundscape 参考）")
    n.add_argument("--desc-a", required=True, help="对手英文形象描述（族裔/年龄/发型/服装）")
    n.add_argument("--desc-b", required=True, help="车主英文形象描述")
    n.add_argument("--short-a", default="girl")
    n.add_argument("--short-b", default="grandpa")
    n.add_argument("--cast-note", default="a young athlete and a 70-year-old grandpa, both Chinese.")
    n.add_argument("--wheel", default="", help="产品保真段（留空用默认无；建议贴 W3 的 WHEEL 段）")
    n.add_argument("--soundscape", default="Quiet open-air outdoor room tone, light wind, clear natural voices. No music.")
    n.add_argument("--extra-tail", default="")
    n.add_argument("--voice-note-a", default="", help="对手音色描述（英文）")
    n.add_argument("--voice-note-b", default="", help="车主音色描述（英文）")
    n.set_defaults(func=cmd_new)

    r = sub.add_parser("run", help="出片全流程（生成→后期→验收→归档）")
    r.add_argument("spec")
    r.add_argument("--bgm", default="auto", help="auto | 曲名.mp3")
    r.add_argument("--skip-gen", action="store_true", help="已有 onetake.mp4，只补后期")
    r.add_argument("--dry", action="store_true", help="演练，不花钱不写文件")
    r.add_argument("--force", action="store_true", help="台词自检不过也继续")
    r.set_defaults(func=cmd_run)

    a = ap.parse_args()
    raise SystemExit(a.func(a))


if __name__ == "__main__":
    main()
