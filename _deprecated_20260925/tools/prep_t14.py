"""T14《魔性三连·超轻篇》准备：建 job + 欧美组（手动） + 轮换记录 + spec + check 文件

7 图方案：4 欧美角色 + 轻便侠×3
3 音色（首次）：grandpa / mom / young_man（爸爸静音）
魔性片型：同句×2 + 同动作×3
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles, cast, products, state
from s3_storyboard import templates

PROMPT = """integrated_multimodal_description: Live-action fun commercial in vertical framing, natural daylight at the entrance of a residential compound. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and bouncy: the first line starts within the first quarter second, every line begins immediately after the previous line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Performances are exaggerated and comical: big wide eyes, raised eyebrows, jaws dropping, tiny half-steps back. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it; no speaker is ever out of frame or seen only from behind while delivering a line.

CAST (STRICTLY BIND — each person appears EXACTLY ONCE per shot, never duplicated, cloned, mirrored, split or twinned; no extra bystanders): exactly four people and exactly ONE wheelchair in the whole video. All four are foreigners who speak Chinese.
- Man A (S1): a 70-year-old foreign man with white hair and blue eyes, beige cardigan and glasses (matching the FIRST reference image) — the demonstrator.
- Woman B (S2): a 40-year-old foreign woman with red-brown curly hair, green eyes, grey turtleneck (matching the SECOND reference image).
- Man C (S3): a 30-year-old foreign man with sandy-blond short hair, dark-blue pilot jacket (matching the THIRD reference image).
- Man D: a 45-year-old foreign man with brown-and-grey hair, army-green jacket (matching the FOURTH reference image). He NEVER speaks — only facial expressions, lips stay closed the whole time.
THE WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching the FIFTH, SIXTH and SEVENTH reference images: silver-grey metal frame, black seat, four wheels, red shock-absorbing springs on the frame, its own brand lettering exactly as in the reference images; it is an electric wheelchair, never a bicycle, scooter or a plain manual wheelchair). It is the very same single wheelchair in all four shots — it is never duplicated, and nobody ever sits in it during the whole video.

[Shot 1, 0 to 4 seconds] The camera sweeps sideways: Woman B (S2) walks around the lightweight wheelchair, sizing it up with curious exaggerated eyes, and asks, skeptical: <d>[Chinese] 这得有三十公斤？</d> — immediately Man A (S1) steps in, grasps the wheelchair frame with ONE hand and lifts the whole wheelchair up off the ground, holding it effortlessly at his side like it weighs nothing, calm and proud, and says at a slightly brisk pace: <d>[Chinese] 十三点八公斤。</d> Woman B's eyes go wide and she takes a tiny half-step back, stunned. Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 2, 4 to 8 seconds] Hard cut to a closer shot: Man C (S3) leans in, doubtful, and asks: <d>[Chinese] 真这么轻？</d> — Man A (S1) holds the wheelchair toward him with one hand and says: <d>[Chinese] 你试试。</d> — Man C (S3) takes the wheelchair with ONE hand, instantly wide-eyed and frozen, his jaw drops, and he blurts out: <d>[Chinese] 哎哟，真轻！</d> Only these three speak in this shot, strictly one after another with no overlap.

[Shot 3, 8 to 12 seconds] Hard cut, the camera sways slightly: Man D walks up with his hands behind his back, looking unconvinced (he stays silent, lips closed, only a skeptical face). Man A (S1) lifts the whole wheelchair up again with ONE hand, holding it effortlessly toward him, and says: <d>[Chinese] 十三点八公斤。</d> Man D's eyes bulge and he rocks back on his heels, amazed. Only Man A speaks in this shot; everyone else stays silent with their lips closed.

[Shot 4, 12 to 15 seconds] Hard cut, the camera pulls back into a wide shot: the three men gather close around Man A (S1), who pats the seat of the lightweight wheelchair and says, finishing right before the video ends: <d>[Chinese] 爱优护轻便侠。</d> Everyone nods with impressed, exaggerated faces. Only Man A speaks in this final shot; everyone else stays silent with their lips closed.

Only one person speaks at a time in this exact order — (S2) then (S1) in shot 1; (S3) then (S1) then (S3) in shot 2; (S1) in shot 3; (S1) in shot 4. The exact same sentence 十三点八公斤 is said twice by the same man (S1), in shot 1 and again in shot 3. All dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no interruptions, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Quiet residential compound ambience, light birds, a soft light metallic touch as the wheelchair is lifted with one hand, plus clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference images; the wheelchair is lifted with one hand and looks clearly very light; the wheelchair is never duplicated in frame; nobody ever sits in the wheelchair; the four people never swap clothes, faces or roles; no background music; every person's appearance, hair and clothing must stay exactly consistent with the reference images throughout all four shots; the four shots are joined by immediate hard cuts with no fades or dissolves."""

REF_IMAGES = [
    "assets/cast/library/western_grandpa_70.png",
    "assets/cast/library/western_mom_40.png",
    "assets/cast/library/western_young_man_30.png",
    "assets/cast/library/western_dad_45.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_grandpa_70.mp3",
    "assets/cast/voice/western_mom_40.mp3",
    "assets/cast/voice/western_young_man_30.mp3",
]


def main() -> None:
    uid = state.create_job()
    # 手动指定欧美组（宝哥要求"角色换成老外"）——不推进自动轮换序号
    hist_path = cast.CASTING_STATE
    hist = json.loads(hist_path.read_text(encoding="utf-8"))
    hist.setdefault("_group_of_job", {})[uid] = 3
    tmp = hist_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(hist_path)

    group = cast._role_group_for(uid)
    print("uid:", uid)
    print("role_group:", group["name"])
    assert group["name"] == "欧美组", f"组指定不对: {group['name']}"

    templates.mark_used("T14")
    angles.record_angle("B19", uid)
    products.record_point("light_13.8", uid)
    state.update_job(uid, status="storyboard")
    print("轮换记录: T14 / B19 / light_13.8 ✓")

    spec = {
        "job_uid": uid,
        "template_id": "T14",
        "template_name": "魔性三连·超轻篇",
        "mode": "one_take",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": REF_IMAGES,
        "ref_audios": REF_AUDIOS,
        "prompt": PROMPT,
        "lines_meta": {
            "template": "T14", "template_name": "魔性三连·超轻篇",
            "angle": "B19 魔性重复洗脑",
            "sales_point": "light_13.8（13.8公斤·单手可提，卖点池首次）",
            "role_group": group["name"] + "（手动指定）",
            "mode": "magic_commercial", "shots": 4, "lines": 7, "chars": 44,
            "ref_count": 7, "audios": 3,
            "magic": "同句「十三点八公斤」×2 + 同动作「单手提起」×3",
            "camera": "横移→推近→轻摇→拉远",
            "script_doc": "docs/script-T14-魔性广告-20260924.md",
        },
    }
    p = ROOT / f"state/onetake_prompt_{uid}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("spec:", p)

    header = '<h3:ReferenceVideo id="onetake-check" duration="15" resolution="768P" aspect-ratio="9:16">\n'
    (ROOT / "docs/onetake_check_T14.txt").write_text(header + PROMPT + "\n", encoding="utf-8")
    print("check 文件就绪")


if __name__ == "__main__":
    main()
