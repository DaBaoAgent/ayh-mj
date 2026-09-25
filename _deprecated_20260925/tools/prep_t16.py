"""T16《超市满载》准备 — 智能组合首片（2026-09-25 宝哥令"出一片"）

组合：时尚组 × cushion_comfy（加厚坐垫）× B7 超市满载 × G1 剧情短片
角色：fashion_granny_silver（主角）+ fashion_girl_street + fashion_boy_fresh
音色：借用（city_grandma_70 / city_young_woman_26 / city_young_man_30 —— 时尚组专属音色待后续制作）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles, genres, products, state

PROMPT = """integrated_multimodal_description: Live-action short drama in vertical framing, natural daylight at the entrance of a supermarket. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and brisk: the first line starts within the first quarter second, every line begins immediately after the previous line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Performances are warm and slightly comical: curious eyes, raised eyebrows, small nods of amazement. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it.

CAST (STRICTLY BIND — exactly three people and exactly ONE wheelchair in the whole video; each person appears EXACTLY ONCE per shot, never duplicated, cloned, mirrored, split or twinned; no extra bystanders):
- Woman A (S1): a 68-year-old Chinese stylish woman with silvery wavy hair, black-framed sunglasses pushed up on her head, a beige trench coat over a black turtleneck, red lipstick, exactly as in the FIRST reference image — the owner.
- Woman B (S2): a 24-year-old Chinese stylish girl with two-tone highlighted shoulder-length hair, a black leather biker jacket, exactly as in the SECOND reference image.
- Man C (S3): a 27-year-old Chinese fresh-looking man with short clean hair, a light blue linen shirt over a white tee, exactly as in the THIRD reference image.
THE WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH and SIXTH reference images: silver-grey metal frame, black seat with its thick cushion, four wheels, red shock-absorbing springs, its own brand lettering exactly as in the reference images; an electric wheelchair, never a manual wheelchair). Several full grocery shopping bags hang on its push handles and on its backrest — five or six plastic shopping bags bulging with groceries — while the wheelchair itself stays exactly the same as in the reference images. Nobody ever sits in it before shot 4.

[Shot 1, 0 to 4 seconds] The camera sweeps sideways at the supermarket entrance: the wheelchair stands loaded like a pack mule — shopping bags hanging all over its handles and backrest; Woman A (S1) is just tying one last bag onto the handle, then pats the ballooning bags, satisfied. Woman B (S2) walks past, stops and stares at the mountain of bags, amazed, and says: <d>[Chinese] 奶奶，您搬超市啊？</d> — Woman A (S1) turns her head proudly and answers at a slightly brisk pace: <d>[Chinese] 打折，一车全装下。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 2, 4 to 8 seconds] Hard cut to a closer shot: Woman B (S2) looks at the overloaded wheelchair with a worried face and asks: <d>[Chinese] 这么多，坐着还舒服吗？</d> — Woman A (S1) pats the thick black seat cushion twice with her hand, confident, and answers: <d>[Chinese] 加厚坐垫，逛仨小时不累。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 3, 8 to 12 seconds] Hard cut, the camera sways slightly: Man C (S3) leans in and presses the seat cushion with his fingers, as if testing a sofa, impressed, and says: <d>[Chinese] 这椅子比我沙发还舒服？</d> — Woman A (S1) laughs happily and answers: <d>[Chinese] 逛超市，就得一身轻松。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 4, 12 to 15 seconds] Hard cut, the camera pulls back into a wide shot: Woman A (S1) sits down in the wheelchair with all the shopping bags still hanging around her, settles herself comfortably, and says, finishing right before the video ends: <d>[Chinese] 爱优护轻便侠。</d> The wheelchair glides away smoothly toward the compound with her and the bags; Woman B and Man C watch her go, nodding with impressed smiles. Only Woman A speaks in this final shot; everyone else stays silent with their lips closed.

Only one person speaks at a time in this exact order — (S2) then (S1) in shot 1; (S2) then (S1) in shot 2; (S3) then (S1) in shot 3; (S1) in shot 4. All dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repeated lines, no interruptions, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Supermarket entrance ambience, distant shopping carts, the soft rustle of plastic shopping bags, a smooth quiet electric motor when the wheelchair glides away, plus clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference images; the wheelchair is never duplicated in frame; nobody sits in the wheelchair before shot 4; the shopping bags never fall and nobody drops anything; the three people never swap clothes, faces or roles; no extra people ever appear; no background music; every person's appearance, hair and clothing must stay exactly consistent with the reference images throughout all four shots; the four shots are joined by immediate hard cuts with no fades or dissolves."""

REF_IMAGES = [
    "assets/cast/library/fashion_granny_silver.png",
    "assets/cast/library/fashion_girl_street.png",
    "assets/cast/library/fashion_boy_fresh.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/city_grandma_70.mp3",      # 借：68女（时尚银发奶奶）
    "assets/cast/voice/city_young_woman_26.mp3",  # 借：24女（街头潮女）
    "assets/cast/voice/city_young_man_30.mp3",    # 借：27男（清爽潮男）
]


def main() -> None:
    uid = state.create_job()
    print("uid:", uid)

    state.update_job(uid, status="storyboard")

    # 记录四池使用（智能组合 commit）
    gused_path = ROOT / "state" / "groups_used.json"
    gused = json.loads(gused_path.read_text(encoding="utf-8")) if gused_path.exists() else {}
    gused.setdefault("时尚组", [])
    if uid not in gused["时尚组"]:
        gused["时尚组"].append(uid)
    gused_path.write_text(json.dumps(gused, ensure_ascii=False, indent=1), encoding="utf-8")
    products.record_point("cushion_comfy", uid)
    angles.record_angle("B7", uid)
    genres.record_genre("G1", uid)
    print("轮换记录: 时尚组 / cushion_comfy / B7 / G1 ✓")

    spec = {
        "job_uid": uid,
        "template_id": "T16",
        "template_name": "超市满载（智能组合首片）",
        "mode": "one_take",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": REF_IMAGES,
        "ref_audios": REF_AUDIOS,
        "prompt": PROMPT,
        "lines_meta": {
            "template": "T16", "template_name": "超市满载",
            "combo": "时尚组 × cushion_comfy × B7 × G1（pick_combo 首片）",
            "role_group": "时尚组（首发）",
            "mode": "story_short", "shots": 4, "lines": 7, "chars": 70,
            "ref_count": 6, "audios": 3,
            "voices_note": "借音色（时尚组专属音色待制作）",
            "camera": "横移→推近→轻摇→拉远",
        },
    }
    p = ROOT / f"state/onetake_prompt_{uid}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("spec:", p)

    header = '<h3:ReferenceVideo id="onetake-check" duration="15" resolution="768P" aspect-ratio="9:16">\n'
    (ROOT / "docs/onetake_check_T16.txt").write_text(header + PROMPT + "\n", encoding="utf-8")
    print("check 文件就绪")


if __name__ == "__main__":
    main()
