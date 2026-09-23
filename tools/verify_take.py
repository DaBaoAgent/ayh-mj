"""出片验收：whisperx 转写 + check-take 逐字比对（R22）

用法：
    python tools/verify_take.py <视频路径> "<期望台词全文>"

流程：
  1. whisperx 转写（系统 Python 3.12 的 whisperx CLI）
  2. 生成 <视频名>.json 转录
  3. node check-take.mjs 逐字比对 + 语速检查
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def transcribe(video_path: str) -> str:
    """whisperx 转写 → 返回 JSON 路径（独立 transcripts 子目录，避免与 result.json 混淆）"""
    video = Path(video_path).resolve()
    out_dir = video.parent / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 精确匹配本次视频的转录（whisperx 用视频 stem 命名）
    json_path = out_dir / f"{video.stem}.json"
    if json_path.exists():
        print(f"↻ 转录已存在: {json_path}", flush=True)
        return str(json_path)

    print("🎧 whisperx 转写中（首次可能下载模型）...", flush=True)
    # whisperx 在系统 Python 3.12 的 Scripts 里；国内走 hf-mirror
    whisperx = r"C:\Users\xxx13\AppData\Local\Programs\Python\Python312\Scripts\whisperx.exe"
    env = {**os.environ,
           "HF_ENDPOINT": "https://hf-mirror.com",
           "HF_HUB_DISABLE_XET": "1"}
    cmd = [whisperx, str(video), "--language", "zh", "--model", "small",
           "--output_dir", str(out_dir), "--output_format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=1800)

    if not json_path.exists():
        print("✗ 转写失败：", (result.stderr or result.stdout or "")[-800:], flush=True)
        raise RuntimeError("whisperx 未产出 JSON")

    return str(json_path)


def check_take(json_path: str, expected: str) -> int:
    """check-take.mjs 比对（AutoAYH 脚本）"""
    checker = Path("D:/@kaifa/AutoAYH/scripts/check-take.mjs")
    if not checker.exists():
        print(f"⚠ check-take.mjs 不存在: {checker}", file=sys.stderr)
        return 1

    print("📋 逐字比对（check-take）...", flush=True)
    cmd = ["node", str(checker), json_path, expected]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    print(result.stdout or "", flush=True)
    if result.stderr:
        print("STDERR:", result.stderr[:500], flush=True)
    return result.returncode


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    video, expected = sys.argv[1], sys.argv[2]
    json_path = transcribe(video)

    # 打印转录文本预览
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        text = "".join(seg.get("text", "") for seg in data)
    else:
        text = data.get("text", "")
    print(f"\n转录文本: {text[:200]}", flush=True)

    return check_take(json_path, expected)


if __name__ == "__main__":
    raise SystemExit(main())
