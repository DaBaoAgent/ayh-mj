"""识图备用通道（vision_analyze 服务故障时用）

用法: .venv/Scripts/python.exe tools/ask_img.py <图片> "<问题>" [--ch local|deepseek]

通道：
  local    → http://127.0.0.1:1235（Hermes 本地端点，背后主模型）
  deepseek → api.deepseek.com（deepseek-flash，读图须 base64）
默认先 local，失败自动回退 deepseek。
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


def ask(img: Path, q: str, ch: str = "auto") -> None:
    b64 = base64.b64encode(img.read_bytes()).decode()
    mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
    payload = {
        "model": "deepseek-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": q},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "max_tokens": 3000,
    }

    channels = []
    if ch in ("auto", "local"):
        channels.append(("local", "http://127.0.0.1:1235/v1/chat/completions", "local"))
    if ch in ("auto", "deepseek"):
        channels.append(("deepseek", "https://api.deepseek.com/v1/chat/completions",
                         load_from_keyfile("deepseek")))

    for name, url, key in channels:
        try:
            r = httpx.post(url, json=payload,
                           headers={"Authorization": f"Bearer {key}"},
                           timeout=180, trust_env=False)
            if r.status_code == 200:
                d = r.json()
                msg = d["choices"][0]["message"]
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                print(f"[{name}] OK")
                if content.strip():
                    print(content)
                else:
                    print("(空 content) reasoning 尾部:")
                    print(reasoning[-800:] if reasoning else "(无 reasoning)")
                return
            print(f"[{name}] HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            print(f"[{name}] ERR: {str(e)[:250]}")
    raise SystemExit("全部通道失败")


if __name__ == "__main__":
    ch = "auto"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--ch" in sys.argv:
        ch = sys.argv[sys.argv.index("--ch") + 1]
        args = [a for a in args if a != ch]
    ask(Path(args[0]), args[1], ch)
