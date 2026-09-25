"""技术验证 2：说话顺序映射 —— 母亲(S2)先说、儿子(S1)后说（与 T06 正式片一致）

目的：确认 ref_audio_0=son_voice / ref_audio_1=mother_voice 挂载时，H3 是否按
「参考图索引配对」把音色给对人（而不是按说话先后顺序分配）。
听感验收：
  · 若母亲的话是女声、儿子的话是男声 → 映射正确（索引配对）✓
  · 若两者音色相反 → 需调换 ref_audio_0/1 顺序

用法: python tools/test_onetake_order.py
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

PROMPT = f"""integrated_multimodal_description: Live-action documentary drama. This 5-second video contains exactly two consecutive shots separated by one hard cut. [Shot 1] Bright Chinese apartment living room, soft daylight. A 68-year-old Chinese woman (S2) in a plum-red fleece jacket stands next to a silver-grey lightweight electric wheelchair that matches the reference images exactly (its four small wheels, seat frame and armrests clearly visible, and it never turns into a bicycle, scooter or motorcycle). She looks down at the folded wheelchair and says in a pleasantly surprised tone at a slightly brisk pace (clear articulation, a bit faster than natural): <d>[Chinese] 这车看着挺轻巧。</d> She finishes the line right before the shot ends. [Shot 2] The video hard-cuts to a 45-year-old Chinese man (S1) in a black jacket and blue jeans standing beside her, smiling; he says warmly: <d>[Chinese] 您上手试试嘛。</d> Only (S2) speaks in the first shot and only (S1) speaks in the second shot; whoever is not speaking keeps their lips completely closed and never moves their mouth. Each person appears EXACTLY ONCE in the whole video and keeps their exact face, hairstyle and clothing from the reference images. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet indoor room tone, a faint hum from the street outside, a soft click from the wheelchair frame. Voices clear and natural.

non_diegetic_music: N/A

{HARD}"""


def main():
    out_dir = ROOT / "out" / "tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "onetake_order_test.mp4"

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
    print("提交测试2（母亲先说 → 儿子后说）...", flush=True)
    task_id = ac.create_task(WF, payload)
    print("task_id:", task_id, flush=True)
    url = ac.poll_task(task_id, interval=20)
    print("下载:", flush=True)
    ac.download(url, str(out))
    print("完成:", out, flush=True)


if __name__ == "__main__":
    main()
