"""火山方舟 Seedream 5.0 生图客户端

用途：人物定妆图、场景底图、封面底图。
协议（实测 + AutoAYH 沉淀）：
  · POST https://ark.cn-beijing.volces.com/api/v3/images/generations
  · model: doubao-seedream-5-0-pro-260628
  · 参考图 images[]（URL 或 data URL），1 张传字符串、多张传数组
  · nsfwCheck 必须 true（平台审核无条件执行）；watermark: false
  · 返回 URL 短时效 → 立即下载

用法：
    python s4_generate/ark_image.py --prompt "提示词" -o out.png
    python s4_generate/ark_image.py --prompt "提示词" --size 1536x2048 -o out.png
    python s4_generate/ark_image.py --prompt "提示词" --ref 参考图.png -o out.png
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-pro-260628"

# 尺寸映射（长边 basic 1536 / high 2048 / ultra 2560，面积上限 4.3M px）
SIZE_MAP = {
    "9:16": {"basic": "864x1536", "high": "1152x2048", "ultra": "1440x2560"},
    "3:4": {"basic": "1152x1536", "high": "1536x2048", "ultra": "1776x2368"},
    "16:9": {"basic": "1536x864", "high": "2048x1152", "ultra": "2560x1440"},
    "1:1": {"basic": "1536x1536", "high": "2048x2048", "ultra": "2048x2048"},
}


def load_key() -> str:
    """VOLCANO_API_KEY：环境变量 → 常见位置"""
    key = os.environ.get("VOLCANO_API_KEY", "")
    if key:
        return key
    for env_file in [Path("D:/@kaifa/ayh-mj/state/ark.env"),
                     Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"]:
        if env_file.exists():
            for raw in env_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith("VOLCANO_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


API_KEY = load_key()


def _to_data_url(path_or_url: str) -> str:
    """本地文件 → data URL；URL 原样返回"""
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    p = Path(path_or_url)
    if not p.exists():
        raise FileNotFoundError(f"参考图不存在: {path_or_url}")
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    data = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{data}"


def gen_image(prompt: str, out_path: str, size: str = None,
              aspect: str = "3:4", quality: str = "high",
              ref_images: list[str] = None) -> dict:
    """生成一张图（返回 {out_path, url, size}）"""
    if not API_KEY:
        raise ValueError("VOLCANO_API_KEY 未设置")

    size = size or SIZE_MAP.get(aspect, {}).get(quality, "1536x2048")

    payload: dict = {
        "model": MODEL,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "watermark": False,
    }
    refs = ref_images or []
    if len(refs) == 1:
        payload["image"] = _to_data_url(refs[0])
    elif len(refs) > 1:
        payload["image"] = [_to_data_url(r) for r in refs]

    # 提交（重试连接错误，不重试业务错误）
    last_err = None
    for attempt in range(3):
        try:
            resp = httpx.post(ARK_URL,
                              headers={"Authorization": f"Bearer {API_KEY}",
                                       "Content-Type": "application/json"},
                              json=payload, timeout=180, proxy=None)
            body = resp.json()
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {str(body)[:300]}")
            break
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_err = e
            if attempt < 2:
                time.sleep(8)
    else:
        raise RuntimeError(f"提交失败（网络 {3} 次）: {last_err}")

    url = body["data"][0]["url"]

    # 立即下载（URL 短时效）
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=120, follow_redirects=True, proxy=None) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 16):
                f.write(chunk)

    return {"out_path": str(out), "url": url, "size": size,
            "bytes": out.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description="火山方舟 Seedream 5.0 生图")
    parser.add_argument("--prompt", required=True, help="生图提示词")
    parser.add_argument("-o", "--out", required=True, help="输出路径")
    parser.add_argument("--size", help="直接指定尺寸（如 1536x2048）")
    parser.add_argument("--aspect", default="3:4", choices=list(SIZE_MAP.keys()))
    parser.add_argument("--quality", default="high", choices=["basic", "high", "ultra"])
    parser.add_argument("--ref", action="append", help="参考图（可多次传）")
    args = parser.parse_args()

    print(f"🎨 Seedream 生图 → {args.out}", flush=True)
    result = gen_image(args.prompt, args.out, size=args.size,
                       aspect=args.aspect, quality=args.quality,
                       ref_images=args.ref)
    print(f"✓ {result['out_path']} ({result['bytes'] / 1024:.0f}KB, {result['size']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
