"""台词撞车校验 —— 新脚本 vs 已拍全部台词库（宝哥 2026-09-25 立的规矩）

背景：D2 十连 v1 曾有三句台词与已拍成片一字不差。此后立规：**≥0.6 相似度即拦截**。

语料来源（自动全扫，不需要维护清单）：
  · state/onetake_prompt_job_*.json      → 现行 prep 的 <d>[Chinese] …</d>
  · state/onetake_check_*.txt            → check 稿
  · docs/onetake_lines_*.txt             → 逐句稿
  · docs/script*.md / docs/scripts*.md   → 历史剧本表格里的台词列
  · out/gen_job*/**/prompt*.txt          → 生成现场留下的 prompt

用法：
  python tools/check_collision.py docs/onetake_lines_S30_1_zhaifeng.txt docs/onetake_lines_S30_2_tangping.txt
  python tools/check_collision.py --all          # 全库自检（找历史重复）
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THRESHOLD = 0.6
CJK = re.compile(r"[\u4e00-\u9fff]")

# 品牌句与卖点术语允许重复（宝哥 2026-09-25 明示例外）
WHITELIST = {
    "爱优护轻便侠", "爱优护轻便侠。",
    "皮实又省心，认准爱优护轻便侠", "皮实又省心，认准爱优护轻便侠。",
}


def norm(text: str) -> str:
    return CJK.sub(lambda m: m.group(0), text).strip()


def _from_prompt(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"<d>\[Chinese\]\s*([^<]+?)\s*</d>", text)]


def _from_md_table(text: str) -> list[str]:
    """剧本 md 里的台词表格行：| 1 | 摊主 | 哎，车别停我摊前边。 | 8 | 镜1 |"""
    out = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        cand = cells[2]
        if not cand or cand in ("台词", "---") or set(cand) <= set("-: "):
            continue
        if len(CJK.findall(cand)) >= 3:
            out.append(cand)
    return out


def harvest(exclude: set[str], exclude_uids: set[str] | None = None) -> dict[str, str]:
    """返回 {台词: 来源标签}；exclude_uids 用于排除新稿自身的 spec（双段互相比对会误报）"""
    exclude_uids = exclude_uids or set()
    corpus: dict[str, str] = {}
    globs = [
        ("state/onetake_prompt_job_*.json", "job"),
        ("state/onetake_check_*.txt", "check"),
        ("docs/onetake_lines_*.txt", "lines"),
        ("docs/script*.md", "md"),
        ("docs/scripts*.md", "md"),
        ("out/gen_job*/**/prompt*.txt", "gen"),
        ("out/gen_job*/**/*.txt", "gen"),
    ]
    for pattern, tag in globs:
        for p in ROOT.glob(pattern):
            if not p.is_file() or p.name in exclude:
                continue
            if any(uid in p.name for uid in exclude_uids):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            found = _from_prompt(text) if tag != "md" else _from_md_table(text)
            for line in found:
                key = norm(line)
                if len(key) < 3:
                    continue
                corpus.setdefault(key, f"{tag}:{p.relative_to(ROOT).as_posix()}")
    return corpus


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def report(new_lines: list[str], corpus: dict[str, str]) -> int:
    hits = 0
    for line in new_lines:
        key = norm(line)
        if len(key) < 3:
            continue
        if key in WHITELIST or any(key in w or w in key for w in WHITELIST if len(w) > 4):
            print(f"  ⚪ {key}  → 品牌句/术语白名单，跳过")
            continue
        best, best_src = 0.0, ""
        for old, src in corpus.items():
            if old == key:
                continue
            r = sim(key, old)
            if r > best:
                best, best_src = r, f"{old}（{src}）"
        flag = "✗" if best >= THRESHOLD else ("·" if best >= 0.45 else "✓")
        mark = "拦截" if best >= THRESHOLD else ("观察" if best >= 0.45 else "安全")
        print(f"  {flag} {key}  → 相似度 {best:.2f} {mark}")
        if best >= 0.45:
            print(f"      最像：{best_src}")
        if best >= THRESHOLD:
            hits += 1
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="新台词稿（每行一句）")
    ap.add_argument("--all", action="store_true", help="全库自检（找历史重复句）")
    args = ap.parse_args()

    new_lines: list[str] = []
    uids: set[str] = set()
    if args.all:
        for f in sorted(ROOT.glob("docs/onetake_lines_*.txt")):
            new_lines += [x.strip() for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    elif args.files:
        for f in args.files:
            p = Path(f) if Path(f).is_absolute() else ROOT / f
            new_lines += [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            # onetake_lines_S31_1_zijizou.txt → 前缀 S31（同批双段互比会误报，整批排除）
            stem = p.stem.replace("onetake_lines_", "")
            if stem:
                uids.add(stem.split("_")[0] or stem)
    else:
        ap.error("给文件或 --all")

    exclude = {Path(f).name for f in args.files}
    corpus = harvest(exclude, exclude_uids=uids)
    print(f"已拍台词库：{len(corpus)} 句 ｜ 待检台词：{len(new_lines)} 句 ｜ 阈值 {THRESHOLD}"
          + (f" ｜ 已排除自身稿件 {sorted(uids)}" if uids else ""))
    hits = report(new_lines, corpus)
    print(f"\n{'✗ 有撞车' if hits else '✓ 无撞车'}：{hits} 句达到/超过 {THRESHOLD}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
