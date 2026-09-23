"""AutoDL 全工作流探测 — 免费收集每个工作流的必填参数/时长范围/分辨率/单价

方法：POST 非法参数触发校验拒绝（不扣费），从报错信息反推参数结构。
产出：state/workflows_meta.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx

from s4_generate.autodl_client import BASE_URL, _headers

FAKE_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
FAKE_AUDIO = "data:audio/mp3;base64,//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAACcQCA"

# 全部 17 个工作流（2026-09-23 从 autodl.art/large-model/comfyui 抓取）
WORKFLOWS = [
    "minimax_h3_z0903",                      # 六图三音频（高质量音画融合）
    "minimax_h3_z0902",                      # 六图生视频（多图一致性）
    "minimax_h3_z0901",                      # 文生视频（高质量创意）
    "minimax_h3_zm_u24",                     # 多图多音频（升级画质）
    "minimax_h3_zm_u08",                     # 多图多音频（高速版）
    "minimax_h3_b99_002",                    # 首尾帧
    "minimax_h3_b99_001",                    # 文生视频
    "minimax_h3_b99_003_12s",                # 多图生视频12秒
    "minimax_h3_image_audio_to_video_v2_15s",  # 多图多音频15秒
    "minimax_h3_lightx2v_v5_15s",            # 多图生视频15秒
    "minimax_h3_image_audio_to_video_v2",    # 多图多音频
    "minimax_h3_image_audio_to_video",       # 图生视频-音频同步（对口型）
    "minimax_h3_lightx2v_v5",                # 多图参考
    "minimax_h3_lightx2v_no_pic",            # 文生视频
    "minimax_h3_lightx2v",                   # 首尾帧
    "wan2.2animate-v4-motion_retargeting",   # 动作迁移
    "indextts2-v1",                          # TTS
]


def probe(wf: str, payload: dict) -> str:
    """提交探测（参数校验拒绝——不扣费），返回 msg"""
    url = f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/{wf}"
    try:
        r = httpx.post(url, headers=_headers(), json=payload, timeout=30)
        body = r.json()
        return str(body.get("msg", ""))[:250]
    except Exception as e:
        return f"__ERR__ {str(e)[:150]}"


def probe_workflow(wf: str) -> dict:
    """迭代探测一个工作流的参数结构"""
    meta = {"id": wf, "required": [], "duration_min": None, "duration_max": None,
            "resolutions": None, "accepts_audio": False}

    # 1. 空 body 探测第一个必填
    payload = {"prompt": "probe"}
    seen = set()
    for _ in range(8):
        msg = probe(wf, payload)
        if "__ERR__" in msg:
            meta["error"] = msg
            return meta
        if "缺少必填参数" in msg:
            missing = msg.split("：")[-1].strip()
            if missing in seen:
                break
            seen.add(missing)
            meta["required"].append(missing)
            # 给缺失参数填假值
            if "audio" in missing.lower():
                payload[missing] = FAKE_AUDIO
                meta["accepts_audio"] = True
            elif "duration" in missing.lower():
                payload[missing] = 5
            else:
                payload[missing] = FAKE_IMG
            continue
        break

    # 2. duration 范围（如果吃到 duration）
    if "duration" in payload or "audio_duration" in payload:
        dkey = "audio_duration" if "audio_duration" in payload else "duration"
        p2 = dict(payload)
        p2[dkey] = -999
        msg = probe(wf, p2)
        if "大于最大值" in msg or "不能大于" in msg:
            try:
                meta["duration_max"] = int(msg.split("最大值")[-1].strip().split()[0].rstrip("，。"))
            except Exception:
                pass
        if "小于最小值" in msg:
            try:
                meta["duration_min"] = int(msg.split("最小值")[-1].strip().split()[0].rstrip("，。"))
            except Exception:
                pass
        # 上限再探
        p3 = dict(payload)
        p3[dkey] = 999
        msg3 = probe(wf, p3)
        if "最大值" in msg3:
            try:
                meta["duration_max"] = int(msg3.split("最大值")[-1].strip().split()[0].rstrip("，。"))
            except Exception:
                pass
        elif "duration" in msg3.lower() and "值" in msg3:
            pass

    # 3. resolution options
    p4 = dict(payload)
    if "resolution" in payload:
        p4["resolution"] = "xxxp竖"
        msg = probe(wf, p4)
        if "options" in msg or "列表" in msg:
            import re
            opts = re.findall(r"[\d]+p[竖横]", msg)
            meta["resolutions"] = sorted(set(opts))
    return meta


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "state" / "workflows_meta.json"
    print(f"🔍 探测 {len(WORKFLOWS)} 个工作流（免费）...\n", flush=True)
    results = {}
    for wf in WORKFLOWS:
        meta = probe_workflow(wf)
        results[wf] = meta
        req = ",".join(meta["required"]) or "无"
        dur = f"{meta['duration_min']}-{meta['duration_max']}s" if meta["duration_min"] or meta["duration_max"] else "?"
        print(f"  {wf}\n    必填: {req} | 时长: {dur} | 音频: {meta['accepts_audio']}",
              flush=True)
        time.sleep(0.5)

    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✓ 元数据: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
