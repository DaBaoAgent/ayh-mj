"""T12《遥控打脸》准备：建 job + 角色组(组3欧美) + 轮换记录 + spec + check 文件"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles, cast, products, state
from s3_storyboard import templates

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight in front of a modern suburban house with a driveway and green lawn. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and brisk with rapid back-and-forth dialogue: the first line starts within the first quarter second, every line begins immediately after the previous line's last word, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is always gently moving — a slow push-in, a smooth pan, a sideways tracking move and a pull-back — never static. Cast: exactly two people in the whole video — a 40-year-old Caucasian woman matching the FIRST reference image (auburn curly hair, grey turtleneck, warm and capable) and a 45-year-old Caucasian man matching the SECOND reference image (brown hair with grey at the temples, army-green jacket, easygoing and reliable), plus one silver-grey electric wheelchair matching the THIRD, FOURTH and FIFTH reference images. Each person appears EXACTLY ONCE per shot — never duplicate, clone, mirror, split or twin any person into a second figure anywhere in the frame (foreground, background, driveway, glass or blur); no extra bystanders, no stand-ins. The wheelchair must exactly match the THIRD, FOURTH and FIFTH reference images: silver-grey metal frame, black seat and backrest, four wheels, the distinctive RED shock-absorbing springs on the frame, and its own brand lettering exactly as in the reference images; it is an electric wheelchair with a motor in its rear wheels, never a plain manual wheelchair, never a bicycle or scooter. During shots 1 and 2 the wheelchair stands folded and upright on the ground beside the house, like a compact vertical column, never laid flat on its side; during shots 3 and 4 it is unfolded, and it moves entirely on its own — nobody pushes it and nobody sits on it — driving smoothly and steadily across the driveway by itself until it stops in front of the two people.

[Shot 1, 0 to 4.5 seconds] The camera slowly pushes in toward the woman: she has just walked up the driveway carrying a grocery bag, stops and frowns at the folded wheelchair standing beside the house, unimpressed; the man stands nearby, calm and relaxed. The woman (S1) says in a complaining tone at a slightly brisk pace: <d>[Chinese] 又乱花钱！这玩意儿得人推吧？</d> — and immediately, right after her last word, the man (S2) answers lightly: <d>[Chinese] 不用推，瞧好喽。</d> Only these two speak in this shot, taking turns one right after the other with no overlap; the woman's mouth moves only while (S1) speaks, and the man's mouth moves only while (S2) speaks; nobody else makes any sound.

[Shot 2, 4.5 to 8 seconds] Hard cut: the camera pans smoothly from the man's hand — he takes a small remote control out of his pocket and presses the button — across the driveway toward the far end where the driveway meets the street. The woman (S1) asks, skeptical: <d>[Chinese] 不推它咋走啊？</d> — and immediately the man (S2) answers: <d>[Chinese] 按一下，它自己就过来。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 3, 8 to 12 seconds] Hard cut to a sideways tracking shot on the driveway: the camera moves sideways together with the unfolded silver-grey wheelchair, keeping it centered as it drives smoothly toward the two people entirely by itself — the four small wheels roll on the ground and its red shock springs are visible; nobody pushes it and nobody sits on it; its brand lettering faces the camera. The woman's eyes go wide. The woman (S1) blurts out in disbelief: <d>[Chinese] 哎哟喂，真过来了！</d> — and immediately, calmly proud, the man (S2) says: <d>[Chinese] 十五米内，随叫随到。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 4, 12 to 15 seconds] Hard cut: the camera pulls back and rises slightly into a wider shot revealing the whole driveway: the wheelchair has stopped in front of them; the man (S2) pats its handlebar, pleased with himself; the woman (S1) stands with her mouth open, stunned, the grocery bag still in her hand. The man (S2) says in a warm, satisfied tone, finishing right before the video ends: <d>[Chinese] 省心又省力，认准爱优护轻便侠。</d> Only the man speaks in this shot; the woman keeps her lips completely closed and stays silent.

Only one person speaks at a time in this exact order — (S1) in shots 1, 2, 3 and (S2) in shots 1, 2, 3, 4, taking turns one right after the other inside each shot; all dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repetition, no interruption, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet suburban ambience, light birdsong, a soft grocery-bag rustle, one small remote-control click, and the soft rolling hum of the wheelchair's small wheels on concrete, plus clear natural voices outdoors.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference images; the wheelchair must never turn into a bicycle, scooter, motorcycle or a plain manual wheelchair, and it must never be pushed or touched by anyone while it is moving on its own; no background music; every person's appearance, hair and clothing must stay exactly consistent with the reference images throughout all four shots; the four shots are joined by immediate hard cuts with no fades or dissolves."""

REF_IMAGES = [
    "assets/cast/library/western_mom_40.png",
    "assets/cast/library/western_dad_45.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_mom_40.mp3",
    "assets/cast/voice/western_dad_45.mp3",
]


def main() -> None:
    uid = state.create_job()
    group = cast._role_group_for(uid)
    print("uid:", uid)
    print("role_group:", group["name"])
    assert group["name"] == "欧美组", f"组轮换不对: {group['name']}"

    templates.mark_used("T12")
    angles.record_angle("B17", uid)
    products.record_point("remote_15m", uid)
    state.update_job(uid, status="storyboard")
    print("轮换记录: T12 / B17 / remote_15m ✓")

    spec = {
        "job_uid": uid,
        "template_id": "T12",
        "template_name": "遥控打脸",
        "mode": "one_take",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": REF_IMAGES,
        "ref_audios": REF_AUDIOS,
        "prompt": PROMPT,
        "lines_meta": {
            "template": "T12", "template_name": "遥控打脸",
            "angle": "B17 遥控泊车演示",
            "sales_point": "remote_15m（15米遥控·剧情绑死）",
            "role_group": group["name"],
            "mode": "short_drama", "shots": 4, "lines": 7, "chars": 70,
            "camera": "推近→横摇→跟拍→拉远（运镜加强版）",
            "script_doc": "docs/script-T12-遥控打脸-20260924.md",
        },
    }
    p = ROOT / f"state/onetake_prompt_{uid}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("spec:", p)

    header = '<h3:ReferenceVideo id="onetake-check" duration="15" resolution="768P" aspect-ratio="9:16">\n'
    (ROOT / "docs/onetake_check_T12.txt").write_text(header + PROMPT + "\n", encoding="utf-8")
    print("check 文件就绪")


if __name__ == "__main__":
    main()
