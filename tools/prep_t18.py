"""T18《维修店·拎回家充》准备 — C档真人音色首发（2026-09-25）

组合：老外时尚组 × lithium_safe（医疗级锂电）× B9 维修店对比 × G3 魔性广告
音色（真人样本首发！）：
  - 主角 ref_audio_0 = sample_west_male_v2.mp3（真人老外男 15s，"音色审核带_欧美5"切片）
  - 技师 ref_audio_1 = sample_young_male_v2.mp3（真人青年男 4s，"音色审核带_补充13"切片）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import angles, genres, products, state

PROMPT = """integrated_multimodal_description: Live-action fun commercial in vertical framing, natural daylight inside a small wheelchair repair shop. This 15-second video contains exactly four consecutive shots joined by immediate hard cuts, no fades or dissolves. Pacing is tight and bouncy: the first line starts within the first quarter second, every line begins immediately after the previous line's last word and immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Performances are exaggerated and comical: raised eyebrows, wide eyes, small nods of amazement. Whenever anyone speaks, their face stays clearly visible to the camera and turned toward it.

CAST (STRICTLY BIND — exactly two people and exactly TWO wheelchairs in the whole video; each person appears EXACTLY ONCE per shot, never duplicated, cloned, mirrored, split or twinned; no extra bystanders): both are foreigners who speak Chinese.
- Man A (S1): a 70-year-old foreign stylish man with neat white hair and a trimmed white beard, dark blue suit over a white shirt, sunglasses hanging at his collar, exactly as in the FIRST reference image — the customer.
- Man B (S2): a 22-year-old foreign young man with deep golden wavy hair and an oatmeal knit sweater, exactly as in the SECOND reference image — the repair technician.
WHEELCHAIR 1 (the old junk one, standing in the shop): a big heavy old-school electric wheelchair with a rusty silver-grey tube frame and worn black seat, clearly old and battered, standing in the corner of the shop. WHEELCHAIR 2 (the hero's new one): the small silver-grey LIGHTWEIGHT electric wheelchair (matching the THIRD, FOURTH and FIFTH reference images: silver-grey metal frame, black seat with thick cushion, four wheels, red shock-absorbing springs, its own brand lettering exactly as in the reference images; an electric wheelchair, never manual). Its battery is a small black rectangular battery box that Man A can pick up with one hand — the same battery box in every shot. The two wheelchairs are clearly different and never swap or merge.

[Shot 1, 0 to 4 seconds] The camera sweeps sideways inside the repair shop: the old junk wheelchair stands in the corner; Man B (S2) wipes his hands on a rag, looks at the junk wheelchair, shakes his head and says: <d>[Chinese] 这车，修不动了。</d> — Man A (S1) walks in behind the small silver-grey wheelchair, smiling, and says: <d>[Chinese] 不用修，我换新的了。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 2, 4 to 8 seconds] Hard cut to a closer shot: Man B (S2) looks the small wheelchair up and down, nods, then frowns a little and says: <d>[Chinese] 新的是好，就是充电费劲吧？</d> — Man A (S1) reaches down, picks the small black battery box up off the wheelchair with one hand, holds it up and gives it a little shake twice, casual and confident, and says: <d>[Chinese] 电池拎回屋充，插上就完事。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 3, 8 to 12 seconds] Hard cut, the camera sways slightly: Man B (S2) stares at the battery box in Man A's hand, eyes wide, and asks: <d>[Chinese] 拎屋里充？！安全吗？</d> — Man A (S1) still holding the battery box up with one hand, pats it lightly with the other hand and answers calmly: <d>[Chinese] 医疗级锂电，放心睡。</d> Only these two speak in this shot, taking turns one right after the other with no overlap.

[Shot 4, 12 to 15 seconds] Hard cut, the camera pulls back into a wide shot: Man A (S1) carries the battery box and walks out of the shop beside his small silver-grey wheelchair, turning his head back to the camera and saying, finishing right before the video ends: <d>[Chinese] 爱优护轻便侠。</d> Man B (S2) watches them leave with an impressed face. Only Man A speaks in this final shot; everyone else stays silent with their lips closed.

Only one person speaks at a time in this exact order — (S2) then (S1) in shot 1; (S2) then (S1) in shot 2; (S2) then (S1) in shot 3; (S1) in shot 4. All dialogue must be spoken verbatim, no overlap, no extra words, no omissions, no repeated lines, no interruptions, no invented lines. No on-screen text or subtitles anywhere in frame; the spoken dialogue is audio only, never visualized as text.

overall_soundscape: Small repair shop ambience, a soft clink of tools, the light rattle of the battery box being shaken, smooth quiet footsteps, plus clear natural indoor voices.

non_diegetic_music: N/A

Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as it appears in the reference images; the small battery box stays small and handheld, held with ONE hand, the same box in every shot; the two wheelchairs are clearly different and never merge; the old junk wheelchair never moves on its own; nobody sits in any wheelchair; the two people never swap clothes, faces or roles; no extra people ever appear; no background music; every person's appearance, hair and clothing must stay exactly consistent with the reference images throughout all four shots; the four shots are joined by immediate hard cuts with no fades or dissolves."""

REF_IMAGES = [
    "assets/cast/library/fashion_western_grandpa.png",
    "assets/cast/library/fashion_western_boy_22.png",
    "assets/products/折叠-无阴影.png",
    "assets/products/正侧-3-无阴影.png",
    "assets/products/45度-加水杯-无阴影.png",
]
REF_AUDIOS = [
    "assets/cast/voice/sample_west_male_v2.mp3",    # 真人老外男 15s（C档首发）
    "assets/cast/voice/sample_young_male_v2.mp3",   # 真人青年男 4s
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
    products.record_point("lithium_safe", uid)
    angles.record_angle("B9", uid)
    genres.record_genre("G3", uid)
    print("轮换记录: 老外时尚组 / lithium_safe / B9 / G3 ✓")

    spec = {
        "job_uid": uid,
        "template_id": "T18",
        "template_name": "维修店·拎回家充（C档真人音色首发）",
        "mode": "one_take",
        "workflow": "minimax_h3_image_audio_to_video_v2_15s",
        "fallback_workflows": ["minimax_h3_lightx2v_v5_15s"],
        "duration": 15,
        "resolution": "768p竖",
        "ref_images": REF_IMAGES,
        "ref_audios": REF_AUDIOS,
        "prompt": PROMPT,
        "lines_meta": {
            "template": "T18", "template_name": "维修店·拎回家充",
            "combo": "老外时尚组 × lithium_safe × B9 × G3（pick_combo 第3片）",
            "role_group": "老外时尚组",
            "mode": "magic_commercial", "shots": 4, "lines": 7, "chars": 70,
            "ref_count": 5, "audios": 2,
            "voices": "真人样本首发（sample_west_male_v2 15s / sample_young_male_v2 4s）",
            "camera": "横移→推近（拎电池）→轻摇→拉远",
        },
    }
    p = ROOT / f"state/onetake_prompt_{uid}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("spec:", p)

    header = '<h3:ReferenceVideo id="onetake-check" duration="15" resolution="768P" aspect-ratio="9:16">\n'
    (ROOT / "docs/onetake_check_T18.txt").write_text(header + PROMPT + "\n", encoding="utf-8")
    print("check 文件就绪")


if __name__ == "__main__":
    main()
