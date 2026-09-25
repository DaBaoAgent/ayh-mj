"""T13《扮猪吃虎·陡坡篇》准备：建 job + 角色组(核心卡司) + 轮换记录 + spec + check 文件

7 图方案（首次）：3 角色 + 轻便侠×3 + 普通电动轮椅×1
两车-两人严格绑定（防画混）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles, cast, products, state
from s3_storyboard import templates

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight at the entrance of a residential compound with a noticeable uphill ramp nearby. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and brisk: the first line starts within the first quarter second, every line begins immediately after the previous line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is always gently moving — a sideways sweep, a push-in with a light handheld sway, a low-angle tracking move up the ramp and a pull-back — never static. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it; no speaker is ever out of frame or seen only from behind while delivering a line.

CAST AND VEHICLES (STRICTLY BIND THESE PAIRS — they never swap): exactly three people and exactly two wheelchairs in the whole video. Man A (S1) is a 75-year-old Chinese man with white hair and deep wrinkles in a grey sweater (matching the SECOND reference image); he ALWAYS stays with the BIG ORDINARY wheelchair (matching the SEVENTH reference image: a large heavy traditional electric wheelchair with a silver-grey tube frame, wide black seat and big rear wheels). Man B (S2) is a 70-year-old Chinese man with grey-white combed-back hair in dark blue work clothes (matching the FIRST reference image); he ALWAYS stays with the small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH and SIXTH reference images: silver-grey metal frame, black seat, four wheels, red shock-absorbing springs on the frame, and its own brand lettering exactly as in the reference images; it is an electric wheelchair, never a bicycle, scooter or a plain manual wheelchair). Woman C is a 70-year-old Chinese woman with silver curly hair in a purple cardigan carrying a grocery basket (matching the THIRD reference image); she only watches and reacts, she never speaks and never touches any wheelchair. Each person appears EXACTLY ONCE per shot — never duplicate, clone, mirror, split or twin any person into a second figure anywhere in the frame; no extra bystanders, no stand-ins. The two wheelchairs are clearly different from each other and never swap owners or merge into one.

[Shot 1, 0 to 4.5 seconds] The camera sweeps sideways across the compound entrance: two wheelchairs are parked side by side — on one side the big heavy ordinary wheelchair, on the other side the small silver-grey lightweight wheelchair; a noticeable uphill ramp is visible in the background. Man A (S1) pats his big wheelchair proudly, boasting at a slightly brisk pace: <d>[Chinese] 我这台一万八，进口原装！</d> — and immediately, right after his last word, Man B (S2) answers mildly, unimpressed: <d>[Chinese] 挺好。我也换了台，没您这台贵。</d> Woman C stands at the side watching with her grocery basket. Only these two men speak in this shot, taking turns one right after the other with no overlap; the speaker's mouth moves only while he speaks; nobody else makes any sound.

[Shot 2, 4.5 to 8 seconds] Hard cut to a closer shot: Man A (S1) smirks, waves dismissively at the small wheelchair and climbs into his big wheelchair: <d>[Chinese] 便宜货能行吗？我先上！</d> — then he drives it at the ramp; the big wheelchair labors halfway up, the wheels slip, it stalls and slides backwards down a short way, wobbling badly; he grips the armrests with both hands, panicking, and cries out at a slightly brisk pace: <d>[Chinese] 哎哎哎！咋还往下溜呢！</d> Man B (S2) stays calm on the ground, arms relaxed at his sides. Only Man A speaks in this shot; his mouth moves only while he speaks.

[Shot 3, 8 to 12 seconds] Hard cut to a low-angle tracking shot from the bottom of the ramp: Man B (S2) calmly climbs into the small silver-grey lightweight wheelchair and says, steady and confident: <d>[Chinese] 行，看我的。</d> — and the lightweight wheelchair climbs the ramp smoothly and steadily, staying level and straight with all four wheels on the ground, all the way up to the top, the red shock springs and brand lettering visible on its frame; nobody pushes it. At the bottom of the ramp, Man A (S1) stares up at it, dumbfounded, and blurts out in disbelief: <d>[Chinese] 哎哟喂！它还真上去了！</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 4, 12 to 15 seconds] Hard cut: the camera pulls back into a wide shot revealing the whole ramp: Man B (S2) sits at the top on his lightweight wheelchair, turns his head back, calm and satisfied, and says, finishing right before the video ends: <d>[Chinese] 三十度陡坡稳当，爱优护轻便侠。</d> At the bottom, Man A (S1) stands beside his big wheelchair, which stayed stuck on the ramp, stunned and speechless; Woman C stares with wide eyes, mouth slightly open. Only Man B speaks in this final shot; everyone else stays silent with their lips closed.

Only one person speaks at a time in this exact order — (S1) in shots 1, 2, 3 and (S2) in shots 1, 3, 4, taking turns one right after the other inside each shot; all dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repetition, no interruption, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet residential compound ambience, light birds, a soft grocery-basket rattle, the strained whining motor of the big wheelchair struggling and slipping on the ramp, brief tire-scuffing as it slides back, and the smooth steady motor hum of the lightweight wheelchair climbing, plus clear natural voices outdoors.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference images; the two wheelchairs must never swap owners, merge or turn into each other; the big wheelchair never tips over or crashes — it only stalls and slides back a short way; the lightweight wheelchair is never pushed and never turns into a bicycle, scooter or manual wheelchair; no background music; every person's appearance, hair and clothing must stay exactly consistent with the reference images throughout all four shots; the four shots are joined by immediate hard cuts with no fades or dissolves."""

REF_IMAGES = [
    "assets/cast/elder_portrait.png",
    "assets/cast/library/city_grandpa_75.png",
    "assets/cast/library/city_grandma_70.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/elder_voice.mp3",
    "assets/cast/voice/city_grandpa_75.mp3",
]


def main() -> None:
    uid = state.create_job()
    group = cast._role_group_for(uid)
    print("uid:", uid)
    print("role_group:", group["name"])
    assert group["name"] == "核心卡司", f"组轮换不对: {group['name']}"

    templates.mark_used("T13")
    angles.record_angle("B18", uid)
    products.record_point("anti_flip", uid)
    state.update_job(uid, status="storyboard")
    print("轮换记录: T13 / B18 / anti_flip ✓")

    spec = {
        "job_uid": uid,
        "template_id": "T13",
        "template_name": "扮猪吃虎·陡坡篇",
        "mode": "one_take",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": REF_IMAGES,
        "ref_audios": REF_AUDIOS,
        "prompt": PROMPT,
        "lines_meta": {
            "template": "T13", "template_name": "扮猪吃虎·陡坡篇",
            "angle": "B18 扮猪吃虎示弱",
            "sales_point": "anti_flip（30度陡坡·正反对比：老张爬不上 vs 老王稳上）",
            "role_group": group["name"],
            "mode": "short_drama", "shots": 4, "lines": 7, "chars": 66,
            "ref_count": 7, "two_chairs": "轻便侠(4-6图,老王) vs 普通轮椅(7图,老张)",
            "camera": "横移→推近轻晃→低角度跟拍→拉远",
            "script_doc": "docs/script-T13-扮猪吃虎-20260924.md",
        },
    }
    p = ROOT / f"state/onetake_prompt_{uid}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("spec:", p)

    header = '<h3:ReferenceVideo id="onetake-check" duration="15" resolution="768P" aspect-ratio="9:16">\n'
    (ROOT / "docs/onetake_check_T13.txt").write_text(header + PROMPT + "\n", encoding="utf-8")
    print("check 文件就绪")


if __name__ == "__main__":
    main()
