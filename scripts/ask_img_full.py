"""识图全量输出（ask_img 只打印尾部，本脚本把完整回复落盘）

用法: .venv/Scripts/python.exe scripts/ask_img_full.py <图片或目录> "<问题>" [--ch deepseek] [--out out.md]
目录模式: 对目录内所有图片按序逐张提问，结果按文件名分节写入 out.md
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import httpx

from lib.keyfile import load_from_keyfile


def encode(img: Path) -> str:
    b64 = base64.b64encode(img.read_bytes()).decode()
    mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def ask_one(img: Path, q: str, ch: str = "deepseek", max_tokens: int = 8000) -> str:
    url, key = "https://api.deepseek.com/v1/chat/completions", load_from_keyfile("deepseek")
    if ch == "local":
        url, key = "http://127.0.0.1:1235/v1/chat/completions", "local"
    payload = {
        "model": "deepseek-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": q},
                {"type": "image_url", "image_url": {"url": encode(img)}},
            ],
        }],
        "max_tokens": max_tokens,
    }
    r = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {key}"}, timeout=300)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    body = (msg.get("content") or "").strip()
    reason = (msg.get("reasoning_content") or "").strip()
    return body if body else f"[空content，reasoning尾部]\n{reason}"


def main() -> None:
    target = Path(sys.argv[1])
    q = sys.argv[2]
    args = sys.argv[3:]
    ch = "deepseek"
    out = ROOT / "references" / "recreate_X2102381914586034213" / "vision_out.md"
    if "--ch" in args:
        ch = args[args.index("--ch") + 1]
    if "--out" in args:
        out = Path(args[args.index("--out") + 1])

    items = sorted(target.glob("*.jpg")) + sorted(target.glob("*.png")) if target.is_dir() else [target]
    if not items:
        print(f"✗ {target} 里没有图片 → 不写文件（防止空内容覆盖已有证据）")
        sys.exit(1)
    parts = []
    for img in items:
        try:
            ans = ask_one(img, q, ch)
        except Exception as e:  # noqa: BLE001
            ans = f"[失败] {type(e).__name__}: {e}"
        parts.append(f"\n## {img.name}\n{ans}\n")
        print(f"✓ {img.name} ({len(ans)} 字)", flush=True)

    out.write_text("".join(parts), encoding="utf-8")
    print(f"SAVED {out}")


if __name__ == "__main__":
    main()
