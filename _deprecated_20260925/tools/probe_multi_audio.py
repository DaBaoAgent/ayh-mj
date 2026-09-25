"""免费探测：多音频参考（ref_audio_1/2）在工作流中的支持情况

安全协议（血泪教训 2026-09-23）：每次请求必带非法 marker（duration=-999 + resolution=PROBE-INVALID），
服务在参数校验阶段即报错，绝不真提交付费任务。

用途：一条视频里有两个说话人时，需要 ref_audio_0（S1 音色）+ ref_audio_1（S2 音色）。
"""
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate.autodl_client import BASE_URL, _headers, to_data_url

IMG = ROOT / "assets" / "cast" / "library" / "western_dad_45.png"
A0 = ROOT / "assets" / "cast" / "voice" / "western_dad_45.mp3"
A1 = ROOT / "assets" / "cast" / "voice" / "western_grandpa_70.mp3"


def probe(wf: str, label: str, extra: dict, duration=-999, resolution="PROBE-INVALID"):
    payload = {"prompt": "probe", "duration": duration, "resolution": resolution,
               "ref_image_0": to_data_url(str(IMG))}
    payload.update(extra)
    try:
        r = httpx.post(f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/{wf}",
                       headers=_headers(), json=payload, timeout=180)
        b = r.json()
        print(f"[{label}] http={r.status_code} code={b.get('code')} msg={str(b.get('msg'))[:260]}")
    except Exception as e:
        print(f"[{label}] 异常: {str(e)[:260]}")


if __name__ == "__main__":
    a0 = to_data_url(str(A0), resize=False)
    a1 = to_data_url(str(A1), resize=False)
    cases = [
        # 对照组：单音频（已知支持） vs 多音频
        ("minimax_h3_image_audio_to_video_v2_15s", "v2_15s  ctrl ref_audio_0", {"ref_audio_0": a0}),
        ("minimax_h3_image_audio_to_video_v2_15s", "v2_15s  +ref_audio_1", {"ref_audio_0": a0, "ref_audio_1": a1}),
        ("minimax_h3_zm_u08", "zm_u08 ctrl ref_audio_0", {"ref_audio_0": a0}),
        ("minimax_h3_zm_u08", "zm_u08  +ref_audio_1", {"ref_audio_0": a0, "ref_audio_1": a1}),
        ("minimax_h3_zm_u24", "zm_u24 +ref_audio_1", {"ref_audio_0": a0, "ref_audio_1": a1}),
        ("minimax_h3_z0903", "z0903  +ref_audio_1+2", {"ref_audio_0": a0, "ref_audio_1": a1, "ref_audio_2": a0}),
    ]
    for wf, label, extra in cases:
        probe(wf, label, extra)
