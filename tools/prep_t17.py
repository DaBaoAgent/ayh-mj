"""T17《竞速打脸》准备 — 智能组合第2片（2026-09-25）

组合：老外时尚组（首发）× tire_puncture（防扎防爆胎）× B8 轮椅竞速 × G2 短剧爽文
角色：fashion_western_grandpa（主角）+ fashion_western_gent_55（对手）+ fashion_western_girl_20（围观）
道具车：对手车 = 普通电动轮椅-参考.png (7th)
音色：借用（western_grandpa_70 / western_dad_45 / western_young_woman_28）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles, genres, products, state

PROMPT = """integrated_multimodal_description: Live-action short comedy-drama in vertical framing, natural daylight in a park lane. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and bouncy: the first line starts within the first quarter second, every line begins immediately after the previous line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Performances are exaggerated and comical: raised eyebrows, proud smirks, panicked faces, wide amazed eyes. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it.

CAST (STRICTLY BIND — exactly three people and exactly TWO wheelchairs in the whole video; each person appears EXACTLY ONCE per shot, never duplicated, cloned, mirrored, split or twinned; no extra bystanders): all three are foreigners who speak Chinese, all standing on a park lane.
- Man A (S1): a 70-year-old foreign stylish man with neat white hair and a trimmed white beard, dark blue suit over a white shirt, sunglasses hanging at his collar, exactly as in the FIRST reference image — the hero.
- Man B (S2): a 55-year-old foreign stylish man with silver-white hair combed back, deep purple suit with a pocket square, exactly as in the SECOND reference image — the rival.
- Woman C (S3): a 20-year-old foreign cool girl with black bob hair and a silver leather jacket, exactly as in the THIRD reference image — the bystander and race starter.
WHEELCHAIR A (the hero's): the small silver-grey LIGHTWEIGHT electric wheelchair (matching the FOURTH, FIFTH and SIXTH reference images: silver-grey metal frame, black seat, red shock-absorbing springs, its own brand lettering exactly as in the reference images; an electric wheelchair, never manual). WHEELCHAIR B (the rival's): a big heavy old-school electric wheelchair with a silver-grey tube frame, wide black seat and big rear wheels, exactly as in the SEVENTH reference image, looking bulky and dated. The two wheelchairs are clearly different and never swap owners or merge into one.

[Shot 1, 0 to 4 seconds] The camera sweeps sideways along the park lane: the two wheelchairs are parked side by side at a starting line — the slim silver-grey one on one side, the big bulky old one on the other; small pieces of broken glass and scattered pebbles lie on the lane just ahead. Man B (S2) pats his big wheelchair, proud and smug, and says: <d>[Chinese] 我这台进口的，稳赢你。</d> — Man A (S1) answers calmly at a slightly brisk pace: <d>[Chinese] 比一把就知道了。</d> — Woman C (S3) raises her hand high like a race starter and shouts: <d>[Chinese] 我数三下，就出发！</d> Only these three speak in this shot, taking turns one right after the other with no overlap.

[Shot 2, 4 to 8 seconds] Hard cut to the race: both wheelchairs roll forward along the lane; suddenly the big bulky wheelchair wobbles and stalls — Man B (S2) looks down in panic at its flat wheels and cries: <d>[Chinese] 等会儿！我这轮子咋了？！</d> — meanwhile the small silver-grey wheelchair rolls steadily right over the broken glass and pebbles without the slightest wobble; Man A (S1) stays calm and says: <d>[Chinese] 实心胎，扎不着。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 3, 8 to 12 seconds] Hard cut to the finish area: the small silver-grey wheelchair comes to a smooth stop past a finish marker; Woman C (S3) runs up, amazed, and exclaims: <d>[Chinese] 扎过去都没事？！</d> In the background Man B (S2) pushes his stalled big wheelchair along on foot, sulking. Only Woman C speaks in this shot; everyone else stays silent with their lips closed.

[Shot 4, 12 to 15 seconds] Hard cut, the camera pulls back into a wide shot: Man A (S1) turns his head back calmly on the small silver-grey wheelchair and says, finishing right before the video ends: <d>[Chinese] 防扎防爆胎，爱优护轻便侠。</d> Woman C nods with an impressed face; in the background Man B (S2) stands beside his stalled bulky wheelchair, completely deflated. Only Man A speaks in this final shot; everyone else stays silent with their lips closed.

Only one person speaks at a time in this exact order — (S2) then (S1) then (S3) in shot 1; (S2) then (S1) in shot 2; (S3) in shot 3; (S1) in shot 4. All dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repeated lines, no interruptions, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Park ambience, light birds, the two wheelchairs' soft electric motor hum; a brief deflating hiss and wobble when the big wheelchair stalls; clear natural outdoor voices.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference images; the two wheelchairs never swap owners, merge or turn into each other; the small wheelchair rolls over the broken glass and pebbles without any problem and never loses a wheel; the big wheelchair never tips over — it only stalls and wobbles on its flat wheels; the three people never swap clothes, faces or roles; no extra people ever appear; no background music; every person's appearance, hair and clothing must stay exactly consistent with the reference images throughout all four shots; the four shots are joined by immediate hard cuts with no fades or dissolves."""

REF_IMAGES = [
    "assets/cast/library/fashion_western_grandpa.png",
    "assets/cast/library/fashion_western_gent_55.png",
    "assets/cast/library/fashion_western_girl_20.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
    "assets/products/普通电动轮椅-参考.png",
]
REF_AUDIOS = [
    "assets/cast/voice/western_grandpa_70.mp3",    # 借：主角（70男）
    "assets/cast/voice/western_dad_45.mp3",        # 借：对手（55男）
    "assets/cast/voice/western_young_woman_28.mp3",# 借：围观（20女）
]


def main() -> None:
    uid = state.create_job()
    print("uid:", uid)
    state.update_job(uid, status="storyboard")

    gused_path = ROOT / "state" / "groups_used.json"
    gused = json.loads(gused_path.read_text(encoding="utf-8")) if gused_path.exists() else {}
    gused.setdefault("老外时尚组", [])
    if uid not in gused["老外时尚组"]:
        gused["老外时尚组"].append(uid)
    gused_path.write_text(json.dumps(gused, ensure_ascii=False, indent=1), encoding="utf-8")
    products.record_point("tire_puncture", uid)
    angles.record_angle("B8", uid)
    genres.record_genre("G2", uid)
    print("轮换记录: 老外时尚组 / tire_puncture / B8 / G2 ✓")

    spec = {
        "job_uid": uid,
        "template_id": "T17",
        "template_name": "竞速打脸（智能组合第2片）",
        "mode": "one_take",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": REF_IMAGES,
        "ref_audios": REF_AUDIOS,
        "prompt": PROMPT,
        "lines_meta": {
            "template": "T17", "template_name": "竞速打脸",
            "combo": "老外时尚组 × tire_puncture × B8 × G2（pick_combo 第2片）",
            "role_group": "老外时尚组（首发）",
            "mode": "short_drama", "shots": 4, "lines": 7, "chars": 68,
            "ref_count": 7, "audios": 3, "two_chairs": "轻便侠(4-6图,主角) vs 普通大车(7图,对手)",
            "voices_note": "借音色（老外时尚组专属音色待制作）",
            "camera": "横移→推近（赛跑）→推近（过线）→拉远",
        },
    }
    p = ROOT / f"state/onetake_prompt_{uid}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("spec:", p)

    header = '<h3:ReferenceVideo id="onetake-check" duration="15" resolution="768P" aspect-ratio="9:16">\n'
    (ROOT / "docs/onetake_check_T17.txt").write_text(header + PROMPT + "\n", encoding="utf-8")
    print("check 文件就绪")


if __name__ == "__main__":
    main()
