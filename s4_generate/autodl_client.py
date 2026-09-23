"""AutoDL.Art MiniMax H3 视频生成客户端

协议（实测来自 autodl 技能）：
  · POST /api/v1/comfyui/comfyui_workflow/{workflow_id}  鉴权 Authorization: <token>（明文，无 Bearer）
  · GET  /api/v1/comfyui/comfyui_workflow/result/{task_id}   轮询 20s
  · 响应 {code, msg, data}，成功 code="Success"
  · 结果 URL 短时效 → SUCCESS 后立即下载
  · 价格：480p ¥0.04/秒、768p ¥0.06/秒、1080p ¥0.10/秒
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE_URL = "https://autodl.art"
WORKFLOWS = {
    "multi_image": "minimax_h3_lightx2v_v5",       # 多图参考 1-10s
    "text2video": "minimax_h3_lightx2v_no_pic",     # 文生视频 1-10s
    "first_last": "minimax_h3_lightx2v",            # 首尾帧 1-10s
    "image_audio": "minimax_h3_image_audio_to_video",  # 对口型 1-15s
}
RESOLUTIONS = ["480p竖", "768p竖", "1080p竖", "480p横", "768p横", "1080p横"]
PRICE_PER_SEC = {"480p": 0.04, "768p": 0.06, "1080p": 0.10}
POLL_INTERVAL = 20
MAX_WAIT = 25 * 60
RESIZE_MAX_SIDE = 1280
RESIZE_MAX_BYTES = 1.5 * 1024 * 1024

# 已知 token 位置
KNOWN_ENV_FILES = [
    Path("D:/自动剪辑/AutoDL/scripts/.env"),
    Path("D:/自动剪辑/AutoDL/佳康顺/.env"),
]


def load_key() -> str:
    """加载 AUTODL_API_KEY：环境变量 → 已知 .env 文件"""
    key = os.environ.get("AUTODL_API_KEY", "")
    if key:
        return key
    for env_file in KNOWN_ENV_FILES:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("AUTODL_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


API_KEY = load_key()


def _headers() -> dict:
    if not API_KEY:
        raise ValueError("AUTODL_API_KEY 未设置（环境变量或已知 .env 位置都没有）")
    return {"Authorization": API_KEY, "Content-Type": "application/json"}


def to_data_url(path_or_url: str, resize: bool = True) -> str:
    """本地文件 → data URL（自动缩到 ≤1280px / ≤1.5MB）；URL 原样返回"""
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    p = Path(path_or_url)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {path_or_url}")

    if resize:
        try:
            from PIL import Image
            import io
            img = Image.open(p)
            # 透明转白底
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                img_rgba = img.convert("RGBA")
                bg.paste(img_rgba, mask=img_rgba.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            # 缩放
            if max(img.size) > RESIZE_MAX_SIDE:
                ratio = RESIZE_MAX_SIDE / max(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)),
                                 Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88)
            data = buf.getvalue()
            mime = "image/jpeg"
        except ImportError:
            data = p.read_bytes()
            mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    else:
        data = p.read_bytes()
        mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"

    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def create_task(workflow_id: str, payload: dict, retries: int = 3) -> str:
    """提交任务（POST 不重试防重复扣费 —— 只对连接错误重试）"""
    url = f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/{workflow_id}"
    last_err = None
    for attempt in range(retries):
        try:
            resp = httpx.post(url, headers=_headers(), json=payload, timeout=180)
            body = resp.json()
            if body.get("code") != "Success":
                raise RuntimeError(f"提交失败: {body.get('msg') or body}")
            return body["data"]["task_id"]
        except httpx.ConnectError as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(10)
    raise RuntimeError(f"提交失败（连接错误 {retries} 次）: {last_err}")


def query_task(task_id: str, retries: int = 5) -> dict:
    """查询任务状态（GET，可安全重试）"""
    url = f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/result/{task_id}"
    last_err = None
    for attempt in range(retries):
        try:
            resp = httpx.get(url, headers=_headers(), timeout=30)
            body = resp.json()
            if body.get("code") != "Success":
                raise RuntimeError(f"查询失败: {body.get('msg') or body}")
            return body.get("data", {})
        except (httpx.SSLError, httpx.ConnectError, httpx.TimeoutException) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(10)
    raise RuntimeError(f"查询失败（网络抖动 {retries} 次）: {last_err}")


def poll_task(task_id: str, label: str = "", interval: int = POLL_INTERVAL,
              max_wait: int = MAX_WAIT, on_status=None) -> str:
    """轮询直至完成，返回视频 URL"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        data = query_task(task_id)
        status = data.get("status", "")
        if on_status:
            on_status(status, data)
        if status == "SUCCESS":
            for r in (data.get("results") or []):
                if r.get("type") == "video" and r.get("url"):
                    return r["url"]
            raise RuntimeError(f"任务完成但无视频 URL: {data}")
        if status in ("FAILED", "ERROR", "CANCELLED"):
            raise RuntimeError(f"任务失败: {data}")
        time.sleep(interval)
    raise RuntimeError(f"等待超时（{max_wait // 60} 分钟）: {task_id}")


def download(url: str, out_path: str, retries: int = 4) -> str:
    """下载成片（URL 短时效，须立即下载）"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    last_err = None
    for attempt in range(retries):
        try:
            with httpx.stream("GET", url, timeout=300, follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1 << 16):
                        f.write(chunk)
            tmp.replace(out)
            return str(out)
        except (httpx.SSLError, httpx.ConnectError, httpx.TimeoutException,
                httpx.HTTPStatusError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(10)
    raise RuntimeError(f"下载失败（{retries} 次）: {last_err}")


def generate_video(
    prompt: str,
    ref_images: list[str] = None,
    duration: int = 5,
    resolution: str = "768p竖",
    out_path: str = None,
    workflow: str = "multi_image",
    on_status=None,
) -> dict:
    """一站式：提交 → 轮询 → 下载

    Returns: {task_id, video_path, duration, resolution, cost}
    """
    ref_images = ref_images or []
    workflow_id = WORKFLOWS.get(workflow, workflow)

    # 组装 payload
    payload = {
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
    }
    for i, img in enumerate(ref_images[:3]):  # v5 上限 9 张，但保守 3 张
        payload[f"ref_image_{i}"] = to_data_url(img)

    if on_status:
        on_status("SUBMITTING", {})

    task_id = create_task(workflow_id, payload)

    video_url = poll_task(task_id, on_status=on_status)

    if out_path:
        download(video_url, out_path)

    # 计费
    res_key = resolution[:resolution.index("p") + 1] if "p" in resolution else "768p"
    cost = PRICE_PER_SEC.get(res_key, 0.06) * duration

    return {
        "task_id": task_id,
        "video_path": out_path,
        "duration": duration,
        "resolution": resolution,
        "cost": round(cost, 3),
    }


if __name__ == "__main__":
    # 自检：查询 key 是否可用（不发任务不花钱）
    print("AUTODL_API_KEY:", "已加载" if API_KEY else "未找到", f"({len(API_KEY)} chars)" if API_KEY else "")
