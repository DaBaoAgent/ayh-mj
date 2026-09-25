"""技术验证：一条视频多镜头 + 双说话人双音色（ref_audio_0/1）

验证两个关键假设（新工艺「所有分镜在一个视频里生」的前提）：
  1. 一条 H3 视频内可做多镜头切换（[Shot 1] → [Shot 2] hard cut）
  2. ref_audio_0/ref_audio_1 分别克隆两个说话人的音色（S1=儿子 / S2=母亲）

用法: python tools/test_onetake_dualvoice.py [--dry]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from s4_generate import autodl_client as ac

CAST = ROOT / "assets" / "cast"
SON_IMG = CAST / "emotions" / "son_full.png"
MOM_IMG = CAST / "emotions" / "mother_full.png"
PROD = ROOT / "assets" / "products" / "折叠-无阴影.png"
SON_VOICE = CAST / "voice" / "son_voice.mp3"
MOM_VOICE = CAST / "voice" / "mother_voice.mp3"

WF = "minimax_h3_image_audio_to_video_v2_15s"

HARD = ("Hard constraints: render no watermarks, subtitles, captions, floating text, letters, "
        "numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; "
        "keep the product's own brand lettering exactly as it appears in the reference image; "
        "no background music; both characters keep complete visual consistency with their reference "
        "images throughout.")

PROMPT = f"""integrated_multimodal_description: Live-action documentary drama. This 5-second video contains exactly two consecutive shots separated by one hard cut. [Shot 1] Bright Chinese apartment living room, soft daylight from a window, light wood floor. A 45-year-old Chinese man (S1) in a black jacket and blue jeans kneels beside a silver-grey lightweight electric wheelchair that matches the reference images exactly (its four small wheels, seat frame and armrests clearly visible, and it never turns into a bicycle, scooter or motorcycle). He pats the folded frame, looks toward the camera and says at a slightly brisk pace (clear articulation, a bit faster than natural): <d>[Chinese] 妈，这车过坎一点不颠。</d> He finishes the line right before the shot ends. [Shot 2] The video hard-cuts to a 68-year-old Chinese woman (S2) in a plum-red fleece jacket sitting on a sofa nearby, looking surprised; she says with curiosity: <d>[Chinese] 真的假的？我试试。</d> Only (S1) speaks in the first shot and only (S2) speaks in the second shot; whoever is not speaking keeps their lips completely closed and never moves their mouth. Each person appears EXACTLY ONCE in the whole video and keeps their exact face, hairstyle and clothing from the reference images. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet indoor room tone, a faint hum from the street outside, a soft click as the man pats the folded wheelchair frame. Voices clear and natural.

non_diegetic_music: N/A

{HARD}"""


def main():
    out_dir = ROOT / "out" / "tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "onetake_dualvoice_test.mp4"

    payload = {
        "prompt": PROMPT,
        "duration": 5,
        "resolution": "768p竖",
        "ref_image_0": ac.to_data_url(str(SON_IMG)),
        "ref_image_1": ac.to_data_url(str(MOM_IMG)),
        "ref_image_2": ac.to_data_url(str(PROD)),
        "ref_audio_0": ac.to_data_url(str(SON_VOICE), resize=False),
        "ref_audio_1": ac.to_data_url(str(MOM_VOICE), resize=False),
    }
    print("提交测试任务（5s / 768p竖 / v2_15s / 双音频）...", flush=True)
    task_id = ac.create_task(WF, payload)
    print("task_id:", task_id, flush=True)
    url = ac.poll_task(task_id, interval=20)
    print("下载:", flush=True)
    ac.download(url, str(out))
    print("完成:", out, flush=True)


if __name__ == "__main__":
    main()
