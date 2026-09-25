"""对照探测 2：验证「未定义参数」报错形态 —— 确认 ref_audio_1 是否为合法字段

逻辑：
  · 传一个肯定不存在的字段（bogus_field_xyz）→ 若报「存在未定义的参数」→ 说明服务会检查未知字段
  · 那么 ref_audio_1 测试里从未触发该错误 → ref_audio_1 是合法字段
"""
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate.autodl_client import BASE_URL, _headers, to_data_url

IMG = ROOT / "assets" / "cast" / "library" / "western_dad_45.png"
A0 = ROOT / "assets" / "cast" / "voice" / "western_dad_45.mp3"


def probe(wf: str, label: str, extra: dict):
    payload = {"prompt": "probe", "duration": -999, "resolution": "768p竖",
               "ref_image_0": to_data_url(str(IMG))}
    payload.update(extra)
    try:
        r = httpx.post(f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/{wf}",
                       headers=_headers(), json=payload, timeout=180)
        b = r.json()
        print(f"[{label}] code={b.get('code')} msg={str(b.get('msg'))[:260]}")
    except Exception as e:
        print(f"[{label}] 异常: {str(e)[:260]}")


if __name__ == "__main__":
    a0 = to_data_url(str(A0), resize=False)
    wf = "minimax_h3_image_audio_to_video_v2_15s"
    # 1) 未知字段对照 ×3（看稳定性）
    for i in range(3):
        probe(wf, f"未知字段 bogus_field_xyz #{i+1}", {"bogus_field_xyz": "1"})
    # 2) 疑似越界字段 ref_audio_9
    probe(wf, "ref_audio_9", {"ref_audio_9": a0})
    # 3) ref_audio_1（对照，与未知字段结果比对）
    probe(wf, "ref_audio_1", {"ref_audio_1": a0})
    # 4) ref_audio_0 + ref_audio_1 同时（真实用法）
    probe(wf, "ref_audio_0+ref_audio_1", {"ref_audio_0": a0, "ref_audio_1": a0})
