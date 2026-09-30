"""能力探测 / 体检（Phase 1）—— 全仓唯一的 capability matrix 来源。

用法：
    python tools/health_check.py            # 人类可读
    python tools/health_check.py --json     # 机器可读（WebUI /api/state 用它）

状态语义：
    READY     该能力可用
    DEGRADED  可用但有缺失/降级（例如字体缺失 → 字幕会退化，但流程能跑）
    BLOCKED   该能力不可用，依赖它的阶段必须停（例如无 ffmpeg）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.console import enable_utf8_console  # noqa: E402

enable_utf8_console()

READY, DEGRADED, BLOCKED = "READY", "DEGRADED", "BLOCKED"
_ORDER = {BLOCKED: 0, DEGRADED: 1, READY: 2}

FONT_HINTS = ("新青年", "青年体", "YaHei", "msyh", "SourceHan", "Noto")


def _cap(name: str, status: str, detail: str, *, required: bool = True,
         fix: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail,
            "required": required, "fix": fix}


def check_python() -> dict:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 11)
    return _cap("python", READY if ok else BLOCKED,
                f"{v.major}.{v.minor}.{v.micro} @ {sys.executable}",
                fix="安装 Python ≥ 3.11")


def check_ffmpeg() -> dict:
    from lib.tools import ffmpeg, ffprobe
    try:
        ff, fp = ffmpeg(), ffprobe()
    except FileNotFoundError as e:
        return _cap("ffmpeg", BLOCKED, str(e), fix="安装 ffmpeg 或设置 FFMPEG_PATH")
    return _cap("ffmpeg", READY, f"{ff} | {fp}")


def check_font() -> dict:
    from lib.settings import get_settings
    s = get_settings()
    dirs = [s.resolve(s.paths.fonts_dir)] if s.paths.fonts_dir else []
    dirs += [s.root / "assets" / "fonts", Path("C:/Windows/Fonts")]
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            for f in d.iterdir():
                if any(h.lower() in f.name.lower() for h in FONT_HINTS):
                    return _cap("font", READY, f"{f.name} @ {d}", required=False)
        except OSError:
            continue
    return _cap("font", DEGRADED, "未找到字幕字体（新青年体/雅黑），字幕将回退默认字体",
                required=False, fix="把字体放进 assets/fonts 或设置 AYHMJ_FONTS_DIR")


def check_whisper() -> dict:
    from lib.settings import get_settings
    model = get_settings().asr.model
    if importlib.util.find_spec("faster_whisper") is None:
        return _cap("whisper", DEGRADED, "faster_whisper 未安装：转写/字级字幕不可用",
                    required=False, fix="uv pip install faster-whisper（或 pip install -e '.[asr]'）")
    return _cap("whisper", READY, f"faster-whisper 已安装（模型 {model}）", required=False)


def check_secret(name: str, *, required: bool, label: str, fix: str) -> dict:
    from lib.secrets import secret_source
    src = secret_source(name)
    if src == "missing":
        return _cap(label, DEGRADED if not required else BLOCKED, "未配置",
                    required=required, fix=fix)
    return _cap(label, READY, f"来源 {src}", required=required)


def check_douyin_profile() -> dict:
    from lib.settings import get_settings
    profile = get_settings().state_dir / "browser-profile"
    if profile.is_dir() and any(profile.iterdir()):
        return _cap("douyin_profile", READY, f"{profile}", required=False)
    return _cap("douyin_profile", DEGRADED, f"登录态目录不存在或为空：{profile}",
                required=False, fix="python s1_trend/browser.py --login 扫码")


def check_postflow() -> dict:
    from lib.settings import get_settings
    d = get_settings().postflow_dir
    exe = d / ".venv" / "Scripts" / "postflow.exe"
    if not exe.is_file():
        exe = d / "postflow.exe"
    if exe.is_file():
        return _cap("postflow", READY, str(exe), required=False)
    return _cap("postflow", DEGRADED, f"未安装：{d}（国内发布不可用）",
                required=False, fix="设置 AYHMJ_POSTFLOW_DIR 或把 PostFlow 放到 vendor/postflow")


def check_uploadpost() -> dict:
    return check_secret("uploadpost", required=False, label="upload_post",
                        fix="keyring set uploadpost api_key 或 export UPLOADPOST_API_KEY")


def check_db() -> dict:
    from lib.settings import get_settings
    db = get_settings().state_dir / "pipeline.db"
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db), timeout=5)
        conn.execute("CREATE TABLE IF NOT EXISTS _health_probe (t INTEGER)")
        conn.execute("DROP TABLE _health_probe")
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        return _cap("db", BLOCKED, f"SQLite 不可写: {e}", fix="检查 state/ 权限")
    return _cap("db", READY, str(db))


def check_disk(min_free_gb: float = 2.0) -> dict:
    from lib.settings import get_settings
    target = get_settings().root
    try:
        usage = shutil.disk_usage(target)
    except OSError as e:
        return _cap("disk", DEGRADED, f"无法读取磁盘信息: {e}", required=False)
    free_gb = usage.free / 1024 ** 3
    status = READY if free_gb >= min_free_gb else DEGRADED
    return _cap("disk", status, f"剩余 {free_gb:.1f} GB（阈值 {min_free_gb} GB）", required=False)


def run_health() -> dict:
    """返回 capability matrix + 汇总状态。"""
    caps = [
        check_python(), check_ffmpeg(), check_font(), check_whisper(),
        check_secret("autodl", required=False, label="autodl",
                     fix="export AUTODL_API_KEY 或写入 keyring"),
        check_secret("deepseek", required=False, label="deepseek",
                     fix="export DEEPSEEK_API_KEY（.env.example）"),
        check_douyin_profile(), check_postflow(), check_uploadpost(),
        check_db(), check_disk(),
    ]
    blocking = [c["name"] for c in caps if c["status"] == BLOCKED and c["required"]]
    degraded = [c["name"] for c in caps if c["status"] == DEGRADED]
    overall = BLOCKED if blocking else (DEGRADED if degraded else READY)
    from lib.settings import get_settings
    s = get_settings()
    return {
        "status": overall,
        "root": str(s.root),
        "blocking": blocking,
        "degraded": degraded,
        "capabilities": caps,
    }


def _icon(status: str) -> str:
    return {READY: "✓", DEGRADED: "△", BLOCKED: "✗"}.get(status, "?")


def format_report(report: dict) -> str:
    """人类可读渲染（bootstrap 与 CLI 共用）。"""
    lines = [f"🏥 ayh-mj 能力体检 ｜ 总状态 {_icon(report['status'])} {report['status']}",
             f"   仓库根：{report['root']}",
             "=" * 64]
    for c in report["capabilities"]:
        tag = "必需" if c["required"] else "可选"
        lines.append(f"  {_icon(c['status'])} {c['name']:<16} [{tag}] {c['detail']}")
        if c["status"] != READY and c["fix"]:
            lines.append(f"      ↳ 修复：{c['fix']}")
    lines.append("=" * 64)
    lines.append(f"{report['status']}｜阻塞 {len(report['blocking'])} 项 / "
                 f"降级 {len(report['degraded'])} 项")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="ayh-mj 能力体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    report = run_health()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["status"] != BLOCKED else 1

    print(format_report(report))
    return 0 if report["status"] != BLOCKED else 1


if __name__ == "__main__":
    raise SystemExit(main())
