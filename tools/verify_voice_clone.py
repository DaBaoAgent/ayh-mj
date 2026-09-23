"""音色克隆验证：zm_u08(多图多音频) + ref_audio_0 音色样本 + 新台词

验证目标：新生成的语音音色与参考样本一致（跨镜音色锁定能力）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from s4_generate.autodl_client import to_data_url, create_task, poll_task, download, BASE_URL

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "voice_test"
OUT.mkdir(parents=True, exist_ok=True)

REF_IMG = ROOT / "assets" / "cast" / "emotions" / "son_urgent.png"
REF_AUDIO = ROOT / "assets" / "cast" / "voice" / "son_voice.mp3"

PROMPT = (
    "integrated_multimodal_description: [Shot 1] Live-action close-up, static shot. A "
    "45-year-old Chinese man (S1) in a black jacket, keeping his exact face and hairstyle from "
    "the reference image, speaks with a voice cloned from the reference audio clip. He looks at "
    "the camera and says at a natural, clear pace: <d>[Chinese] 这是音色一致性测试，你听听"
    "像不像我的声音。</d> Only he speaks; his lips move in sync. Mouth and eyes fully "
    "unobstructed in frame.\n\n"
    "overall_soundscape: Quiet room tone, his voice clear and close.\n\n"
    "non_diegetic_music: N/A\n\n"
    "Hard constraints: render no watermarks, subtitles, captions, floating text, letters, "
    "numbers, stickers, logos or UI elements anywhere in frame; no background music."
)

if __name__ == "__main__":
    payload = {
        "prompt": PROMPT,
        "duration": 5,
        "resolution": "768p竖",
        "ref_image_0": to_data_url(str(REF_IMG)),
        "ref_audio_0": to_data_url(str(REF_AUDIO)),
    }

    print("🎤 音色克隆验证任务提交...", flush=True)
    task_id = create_task("minimax_h3_zm_u08", payload)
    print(f"  task_id: {task_id}", flush=True)

    out_path = OUT / "voice_clone_test.mp4"
    url = poll_task(task_id, on_status=lambda s, d: print(f"  [{s}]", flush=True))
    download(url, str(out_path))
    print(f"✓ 验证视频: {out_path}", flush=True)

    (OUT / "result.json").write_text(
        json.dumps({"task_id": task_id, "video": str(out_path)}, ensure_ascii=False, indent=1),
        encoding="utf-8")
