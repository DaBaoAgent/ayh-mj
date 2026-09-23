"""工作流精确探测 v2 — 安全协议：每个请求必须被校验拒绝

防误提交断言：响应不含"参数/缺少/未定义"关键字 → 立即中止该工作流并报警。
目标：完整参数矩阵（必填/时长范围/分辨率 options）→ state/workflows_matrix.json
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx

from s4_generate.autodl_client import BASE_URL, _headers

FAKE_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
FAKE_AUDIO = "data:audio/mp3;base64,//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAACcQCA"

# 目标工作流（项目相关的 10 个核心）
TARGETS = [
    "minimax_h3_lightx2v_v5",
    "minimax_h3_lightx2v_v5_15s",
    "minimax_h3_zm_u08",
    "minimax_h3_zm_u24",
    "minimax_h3_image_audio_to_video_v2",
    "minimax_h3_image_audio_to_video_v2_15s",
    "minimax_h3_image_audio_to_video",
    "minimax_h3_z0902",
    "minimax_h3_z0903",
    "minimax_h3_b99_003_12s",
    "minimax_h3_lightx2v_no_pic",
    "minimax_h3_lightx2v",
]


class UnsafeResponse(Exception):
    pass


def probe(wf: str, payload: dict) -> str:
    """提交探测；响应必须含校验关键字，否则抛 UnsafeResponse（网络抖动重试）"""
    url = f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/{wf}"
    last_err = None
    for attempt in range(4):
        try:
            r = httpx.post(url, headers=_headers(), json=payload, timeout=40)
            body = r.json()
            break
        except (httpx.ConnectError, httpx.SSLError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_err = e
            time.sleep(5)
    else:
        raise RuntimeError(f"网络失败4次: {last_err}")
    msg = str(body.get("msg", ""))
    code = body.get("code", "")
    if code == "Success":
        raise UnsafeResponse(f"⚠⚠ 任务被提交了！{wf} {str(body)[:200]}")
    if not any(k in msg for k in ("参数", "缺少", "未定义", "不在")):
        raise UnsafeResponse(f"未知响应 {wf}: {str(body)[:200]}")
    return msg


def probe_workflow(wf: str) -> dict:
    meta = {"id": wf, "required": [], "duration_key": None, "duration_min": None,
            "duration_max": None, "resolutions": None, "accepts_audio": False, "notes": []}

    # 基础 payload 始终带非法 duration 护身（首次请求就不可能提交）
    payload = {"prompt": "probe", "duration": -999}

    for _ in range(10):
        msg = probe(wf, payload)
        # 未定义 duration → 换 audio_duration 探
        if "未定义" in msg and "duration" in payload and payload.get("duration") == -999:
            del payload["duration"]
            payload["audio_duration"] = -999
            continue
        if "未定义" in msg and payload.get("audio_duration") == -999:
            # 两个都不是 → 该工作流不接受时长参数（或参数名特殊）
            del payload["audio_duration"]
            payload["_keep_alive"] = -999  # 非法参数护身
            msg2 = probe(wf, payload)
            meta["notes"].append(f"无时长参数；护身探测: {msg2[:80]}")
            break
        if "缺少必填参数" in msg:
            missing = msg.split("：")[-1].strip()
            if missing in meta["required"]:
                break
            meta["required"].append(missing)
            if "audio" in missing.lower():
                payload[missing] = FAKE_AUDIO
                meta["accepts_audio"] = True
            elif missing in ("first_frame", "last_frame"):
                payload[missing] = FAKE_IMG
            else:
                payload[missing] = FAKE_IMG
            continue
        # duration 范围
        dkey = "duration" if "duration" in payload else ("audio_duration" if "audio_duration" in payload else None)
        if dkey and "小于最小值" in msg:
            meta["duration_key"] = dkey
            m = re.search(r"最小值\s*(\d+)", msg)
            meta["duration_min"] = int(m.group(1)) if m else None
            payload[dkey] = 999
            continue
        if dkey and "大于最大值" in msg:
            m = re.search(r"最大值\s*(\d+)", msg)
            meta["duration_max"] = int(m.group(1)) if m else None
            payload[dkey] = 5
            continue
        # resolution options
        if "resolution" in msg and ("不在" in msg or "options" in msg) and payload.get("resolution") != "BAD_PROBE":
            m = re.findall(r"\d+p[竖横]", msg)
            meta["resolutions"] = sorted(set(m)) or None
            payload["resolution"] = "BAD_PROBE2"
            continue
        break

    # 补全分辨率 options（有些流 resolution 校验在 duration 之前）
    if not meta["resolutions"]:
        p = dict(payload)
        p.pop("duration", None)
        p.pop("audio_duration", None)
        if "duration_key" in meta and meta["duration_key"]:
            p[meta["duration_key"]] = 5
        p["resolution"] = "BAD_PROBE3"
        try:
            msg = probe(wf, p)
            if "不在" in msg or "options" in msg:
                m = re.findall(r"\d+p[竖横]", msg)
                meta["resolutions"] = sorted(set(m)) or None
        except UnsafeResponse as e:
            meta["notes"].append(str(e)[:150])

    return meta


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "state" / "workflows_matrix.json"
    print(f"🔍 精确探测 {len(TARGETS)} 个工作流（安全协议）...\n", flush=True)
    results = {}
    for wf in TARGETS:
        try:
            meta = probe_workflow(wf)
            results[wf] = meta
            req = ",".join(meta["required"]) or "无"
            dur = "?"
            if meta["duration_key"]:
                dur = f"{meta['duration_min']}-{meta['duration_max']}s ({meta['duration_key']})"
            print(f"  {wf}\n    必填: {req} | 时长: {dur} | 音频: {meta['accepts_audio']} | 分辨率: {len(meta['resolutions'] or [])}种",
                  flush=True)
        except UnsafeResponse as e:
            results[wf] = {"id": wf, "UNSAFE": str(e)}
            print(f"  {wf}: ⚠⚠ {str(e)[:120]}", flush=True)
        except Exception as e:
            results[wf] = {"id": wf, "error": str(e)[:200]}
            print(f"  {wf}: 异常 {str(e)[:120]}", flush=True)
        time.sleep(0.6)

    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✓ 矩阵: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
