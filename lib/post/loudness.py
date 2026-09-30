"""统一响度 / 真峰值检测（Phase 9 必做任务 11）。

为什么要统一：人声链、BGM 混音、QA 验片三处各自量一次响度，口径不同就会出现
「混音时觉得刚好、验片说爆表」。这里给出**唯一实现**与**唯一阈值**：

  · `measure()`      —— ffmpeg ebur128 扫全片 → 整体响度 LUFS / LRA / 真峰值 dBTP；
  · `in_band()`      —— 判定是否落在目标区间且不超峰值；
  · `LOUDNESS_BAND` / `TRUE_PEAK_MAX` —— 目标区间与限幅上限，`lib/qa/checks.py`
    直接从这里 import，不再各写一份。

探测失败（无 ffmpeg / 无音频流）返回带 `error` 的 dict，而不是抛异常：
验片不该因为一次探测失败就全挂。
"""
from __future__ import annotations

import re
import subprocess
from contextlib import suppress as _suppress
from pathlib import Path

# ── 唯一阈值（改这里等于全链改口径）────────────────────────────────────
LOUDNESS_BAND = (-17.0, -9.0)     # 对白片整体响度目标区间（LUFS）
TRUE_PEAK_MAX = -1.0              # 真峰值上限（dBTP），超过即有削波风险
LOUDNESS_TARGET = -16.0           # 混音 loudnorm 目标 I
LOUDNESS_TP = -1.5                # 混音 loudnorm 真峰值上限
LOUDNESS_LRA = 11.0               # 混音 loudnorm 动态范围

_I_RE = re.compile(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS")
_LRA_RE = re.compile(r"LRA:\s*(-?\d+(?:\.\d+)?)\s*LU")
_PEAK_RE = re.compile(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS")


def limiter_filter(tp: float | None = None) -> str:
    """与 TP 阈值同源的软限幅：`limit` 由 dBTP 换算，不再各处手写 0.891/0.95。

    限幅放在 loudnorm **之前**：先把 SFX 尖峰按同一阈值收住，再按响度目标做线性
    归一。顺序反了的话 loudnorm 刚归好的电平会被后面的限幅器再压一次，实测整片
    反而掉到 -17.5 LUFS（自己产出的成片被自己的 QA 判不合格）。
    """
    tp = LOUDNESS_TP if tp is None else float(tp)
    return f"alimiter=limit={10 ** (tp / 20):.4f}:level=0"


def master_gain(result: dict, *, target: float | None = None, max_boost: float = 18.0,
                max_cut: float = 24.0) -> float:
    """由**实测**响度求母线静态增益（dB）：把成片拉到响度目标。

    为什么不用 `loudnorm`：它自己报的 `input_i` 与 ebur128 对同一段素材的读数能差
    8dB（动态窗口 + 前瞻），照它报的数归一会把成片压过头。这里只信 ebur128 对
    **已落盘素材**的读数，增益是静态的 → 可复现、可验证。

    峰值**不在这里**设限：母线的 `alimiter` 负责兜住真峰值顶棚（SFX 尖峰几乎不贡献
    响度，靠它们反推增益只会把整片响度压到目标以下）。只做荒谬值防护。
    """
    tgt = LOUDNESS_TARGET if target is None else float(target)
    loud = result.get("loudness_lufs")
    if loud is None:
        return 0.0
    gain = tgt - float(loud)
    return round(max(-float(max_cut), min(float(max_boost), gain)), 2)


def master_for_mix(mix_argv: list[str], graph: str, out_wav: str | Path, *,
                   target: float | None = None, tp: float | None = None) -> tuple[str, dict]:
    """把「未过母线」的**完整**滤波图渲成 wav 实测 → 返回 (母线过滤串, 实测结果)。

    `graph` 必须是**整条** filter_complex（含各路 `[s1]…[v0]…[bgd]` 的定义），
    只给末尾那截 `…amix=…[prem]` 会让 ffmpeg 在缺标签的图上产出另一条信号
    （实测与出片能差 6dB 峰值）—— 那样算出来的母线增益是错的。

    两个后期工具（audio_polish / make_15s）共用这一条，保证「一套阈值 + 一次实测」。
    渲染失败或测不到就返回 0dB 增益 + 限幅（绝不因为量不出来就不出片）。
    """
    import subprocess as _sp

    # mix_argv 必须是**完整** argv（含 ffmpeg 可执行文件本身），与调用方最终出片用同一条。
    cmd = [*mix_argv, "-filter_complex", f"{graph}[prem]",
           "-map", "[prem]", "-c:a", "pcm_s16le", str(out_wav)]
    with _suppress(OSError, _sp.SubprocessError):
        _sp.run(cmd, capture_output=True, text=True, timeout=300)
    measured = measure(out_wav)
    gain = master_gain(measured, target=target)
    return f"volume={gain:g}dB,{limiter_filter(tp)}", measured


def _last(pattern: re.Pattern[str], text: str) -> float | None:
    hits = pattern.findall(text)
    if not hits:
        return None
    try:
        return round(float(hits[-1]), 2)
    except (TypeError, ValueError):
        return None


def measure(path: str | Path, *, timeout: float = 300.0) -> dict:
    """扫全片音频 → {loudness_lufs, lra, true_peak_db, ok, error?}。

    永远返回 dict（不抛异常）；探测不到就留 None 并写 error。
    """
    from ..tools import ffmpeg

    p = Path(path)
    out: dict = {"path": str(p), "loudness_lufs": None, "lra": None,
                 "true_peak_db": None, "ok": False}
    if not p.is_file():
        out["error"] = "file not found"
        return out
    cmd = [ffmpeg(), "-hide_banner", "-nostats", "-i", str(p),
           "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:      # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    text = r.stderr or ""
    out["loudness_lufs"] = _last(_I_RE, text)
    out["lra"] = _last(_LRA_RE, text)
    out["true_peak_db"] = _last(_PEAK_RE, text)
    if out["loudness_lufs"] is None and out["true_peak_db"] is None:
        lines = (r.stderr or "").strip().splitlines()
        out["error"] = lines[-1] if lines else "ebur128 produced no summary"
        return out
    out["ok"] = in_band(out["loudness_lufs"], out["true_peak_db"])
    return out


def in_band(loudness_lufs: float | None, true_peak_db: float | None) -> bool:
    """响度在目标区间且峰值不超限 → True；任一为 None 视为不通过（不猜）。"""
    if loudness_lufs is None or true_peak_db is None:
        return False
    return LOUDNESS_BAND[0] <= float(loudness_lufs) <= LOUDNESS_BAND[1] and \
        float(true_peak_db) <= TRUE_PEAK_MAX


def issues(result: dict) -> list[str]:
    """把一次 measure() 的结果翻成人话（QA/日志共用）。"""
    out: list[str] = []
    if not result:
        return ["未提供响度检测结果"]
    if result.get("error"):
        out.append(f"响度检测失败：{result['error']}")
    loud = result.get("loudness_lufs")
    if loud is None:
        out.append("未测得整体响度")
    elif not (LOUDNESS_BAND[0] <= float(loud) <= LOUDNESS_BAND[1]):
        out.append(f"整体响度 {float(loud):.1f} LUFS 不在 {LOUDNESS_BAND} 目标区间")
    peak = result.get("true_peak_db")
    if peak is None:
        out.append("未测得真峰值")
    elif float(peak) > TRUE_PEAK_MAX:
        out.append(f"真峰值 {float(peak):.1f} dBTP 超过 {TRUE_PEAK_MAX}（有削波风险）")
    return out


def summarize(result: dict) -> str:
    """一行日志：`-16.2 LUFS / 7.0 LU / -1.4 dBTP ✓`。"""
    loud = result.get("loudness_lufs")
    lra = result.get("lra")
    peak = result.get("true_peak_db")
    if loud is None and peak is None:
        return f"响度：未测得（{result.get('error') or 'unknown'}）"
    mark = "✓" if result.get("ok") else "✗"
    return (f"{loud if loud is not None else '?'} LUFS / "
            f"{lra if lra is not None else '?'} LU / "
            f"{peak if peak is not None else '?'} dBTP {mark}")
