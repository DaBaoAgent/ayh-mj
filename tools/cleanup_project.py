"""项目清理（现行版，2026-09-26 重写）

⚠️ 为什么重写
  旧版（2026-09-23）规则是「删除 out/ 下除 approved 外的一切」。在 15 秒 one-take 管线里这是**破坏性的**：
  它会把 `out/_archive_onetake/`（生片母版，重烧唯一依赖）与当前管线目录里的
  `onetake.mp4 / onetake_trim.mp4 / onetake_trim.srt / transcripts/`（重烧三件套）一起删掉，
  还依赖一批早已不存在的 `gen_job_2026...` 老目录。前端「清理」按钮（POST /api/action/cleanup）调的就是它。
  现改为**白名单保护式**：只删中间件与缓存，进保护清单的一律不动。

保护（永不删）
  · out/approved/**                成片 + _superseded 留档（50 条）
  · out/_archive_onetake/**        生片母版（重新做后期的唯一来源）
  · out/gen_<uid>/                 以下四类保留：onetake.mp4 / onetake_trim.mp4 / onetake_trim.srt / transcripts/
  · state/                         thumbs(前端缩略图) / browser-profile(抖音登录态) / console.json /
                                   hermes_bridge.json / chat_session.json / chat.json / logs/ / _archive/ /
                                   casting_history.json / combos_used.json / groups_used.json /
                                   sales_points_used.json / story_angles_used.json / genres_used.json /
                                   used_ideas.json / approved_order.json / pipeline.db / run_status.json
  · assets/ vendor/ webui/ tools/ lib/ s1_trend/ s4_generate/ s5_compose/ s6_publish/ scripts/ 整目录

删除（中间件 / 缓存 / 一次性产物）
  · out/gen_*/ 派生文件：*_sub*.mp4 *_polished*.mp4 *_final*.mp4 *.ass *_frames_tmp/ _frames_tmp/ *.trimmed
  · state/frames/  state/before_fix/
  · 全项目 __pycache__/、.ruff_cache/
  · %LOCALAPPDATA%/Temp/trim_onetake_*

用法
  .venv/Scripts/python.exe tools/cleanup_project.py --dry     # 预览
  .venv/Scripts/python.exe tools/cleanup_project.py           # 执行
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
STATE = ROOT / "state"
APPROVED = OUT / "approved"
ARCHIVE = OUT / "_archive_onetake"

# 管线目录里必须保留的四类（重烧三件套 + 生片）
KEEP_IN_GEN = {"onetake.mp4", "onetake_trim.mp4", "onetake_trim.srt", "onetake_task.json",
               "onetake_result.json", "transcripts"}
DERIVED_RE = re.compile(r"(_sub|_polished|_final|_fx|\.ass$|\.trimmed$|_frames_tmp|^_frames)", re.I)
STATE_KEEP = {
    "thumbs", "browser-profile", "console.json", "hermes_bridge.json", "chat_session.json", "chat.json",
    "logs", "_archive", "casting_history.json", "combos_used.json", "groups_used.json",
    "sales_points_used.json", "story_angles_used.json", "genres_used.json", "used_ideas.json",
    "approved_order.json", "pipeline.db", "run_status.json", "run_progress.jsonl",
    "console_action.json", "queue_15s", "restart_console.bat",
}

MB = 1024 * 1024
size = 0
actions: list[str] = []


def rm(p: Path, dry: bool) -> None:
    global size
    try:
        s = p.stat().st_size if p.is_file() else 0
        if p.is_dir():
            s = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        if not dry:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        size += s
        try:
            label = p.relative_to(ROOT)
        except ValueError:          # 项目外（如 %TEMP%）路径
            label = p
        actions.append(f"  🗑 {label}  ({s / MB:.2f}MB)")
    except OSError as e:
        actions.append(f"  ! 跳过 {p}（{e}）")


def main(dry: bool = False) -> None:
    print("=" * 64)
    print(("清理预览（不改动）" if dry else "开始清理（白名单保护式）"))
    print("=" * 64)

    # ① out/gen_*/ 只删派生中间件
    for g in sorted(OUT.glob("gen*")):
        if not g.is_dir():
            continue
        for item in sorted(g.iterdir()):
            if item.name in KEEP_IN_GEN:
                continue
            if item.is_dir() and "transcript" in item.name.lower():
                continue
            if item.is_dir() or DERIVED_RE.search(item.name):
                rm(item, dry)

    # ② state 过程产物
    for name in ["frames", "before_fix"]:
        p = STATE / name
        if p.exists():
            rm(p, dry)
    for item in sorted(STATE.iterdir()):
        if item.name in STATE_KEEP or item.name.startswith("."):
            continue
        # 现行管线的 spec / 预筛稿保留
        if item.name.startswith(("onetake_prompt_job_", "prescreen_job_")):
            continue
        if item.is_file() and item.suffix in {".tmp", ".part", ".log"}:
            rm(item, dry)

    # ③ 缓存
    for r, dirs, _ in os.walk(ROOT):
        if any(x in r for x in (".venv", ".git", os.sep + "vendor", "node_modules")) or r.endswith("_deprecated_20260925"):
            dirs[:] = []
            continue
        for d in list(dirs):
            if d in {"__pycache__", ".ruff_cache", ".pytest_cache"}:
                rm(Path(r) / d, dry)
                dirs.remove(d)

    # ④ ffmpeg 临时残留
    tmp = Path(tempfile.gettempdir())
    for p in tmp.glob("trim_onetake_*"):
        rm(p, dry)

    # ⑤ 回执
    print("\n".join(actions[:60]) + ("\n  ... 另 %d 项" % (len(actions) - 60) if len(actions) > 60 else ""))
    print(f"\n{'（dry）' if dry else ''}共 {len(actions)} 项 / {size / MB:.1f}MB")
    print("\n=== 保护清单（一律不删）===")
    n_app = len(list(APPROVED.glob("*.mp4"))) if APPROVED.exists() else 0
    n_arch = len(list(ARCHIVE.glob("*.mp4"))) if ARCHIVE.exists() else 0
    print(f"  ✓ out/approved/ 成片 {n_app} 条 ｜ out/_archive_onetake/ 生片 {n_arch} 条")
    print("  ✓ out/gen_*/ 的 onetake.mp4 · onetake_trim.mp4 · onetake_trim.srt · transcripts/")
    print("  ✓ state/thumbs（前端缩略图）· browser-profile（抖音登录态）· _archive/（老 spec）")
    print("  ✓ state/console.json · hermes_bridge.json · 四池轮换状态 · queue_15s/")


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
