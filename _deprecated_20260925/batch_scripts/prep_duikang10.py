"""短剧狗血10连·对抗加码版 — prompt 组装（10 条 → 10 个 spec）

格局继承 prep_brain2.py（T20 v3 成功版：STYLE + CAST 绑定 + WHEELCHAIR + 4 镜 + 约束）。
本批特性（宝哥令：动作要有对抗、人物表情要激烈）：
- 每镜 desc 显式写「对抗动作成对出现」（对手做 A → 主角回 B）+ 激烈表情节拍 + 运镜
- 遵守 H3 能力边界：无坡道/无溜坡/无狼狈叙事；每镜 ≤3 事件；新人物「一开始就在场」
- 台词 65-72 纯汉字（14.5s 档 check_dialogue 口径），单句 ≤13，禁破折号
- 与已拍 36 条零撞车（脚本级比对 docs/onetake_check_*.txt）
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = "assets/cast/library"
VOICE = "assets/cast/voice/real"

# ── 角色库（img/audio/desc/voice）────────────────────────────────
CAST_LIB = {
    "grandma": {
        "short": "grandma",
        "img": f"{LIB}/city_grandma_70.png",
        "audio": f"{VOICE}/r01_elder_female.mp3",
        "desc": "a 70-year-old Chinese grandma with silver permed hair, a purple cardigan and a pearl necklace",
        "voice": "an ELDERLY woman's voice — warm, low and unhurried",
    },
    "grandpa": {
        "short": "grandpa",
        "img": f"{LIB}/city_grandpa_75.png",
        "audio": f"{VOICE}/r12_elder_male.mp3",
        "desc": "a 75-year-old Chinese grandpa with white hair and deep wrinkles, a grey knit sweater",
        "voice": "an ELDERLY man's voice — low, deep and slow",
    },
    "mom": {
        "short": "mother",
        "img": f"{LIB}/city_mom_45.png",
        "audio": f"{VOICE}/r11_mother_female.mp3",
        "desc": "a 45-year-old Chinese woman with shoulder-length black hair, a soft beige knit top and reading glasses pushed up on her head",
        "voice": "a MIDDLE-AGED woman's voice — warm, clear and unhurried",
    },
    "daughter": {
        "short": "daughter",
        "img": f"{LIB}/city_daughter_35.png",
        "audio": f"{VOICE}/r05_young_female.mp3",
        "desc": "a 35-year-old Chinese woman in commuting clothes, capable and gentle",
        "voice": "a YOUNG woman's voice — clear and gentle",
    },
    "aunt": {
        "short": "neighbour aunt",
        "img": f"{LIB}/city_neighbor_aunt_55.png",
        "audio": f"{VOICE}/r08_aunt_female.mp3",
        "desc": "a 55-year-old Chinese neighbor aunt with curly hair, a purple sportswear jacket and a chatty look",
        "voice": "a MATURE woman's voice — bright, chatty and gossipy",
    },
    "youngman": {
        "short": "young man",
        "img": f"{LIB}/city_young_man_30.png",
        "audio": f"{VOICE}/r03_young_male.mp3",
        "desc": "a 30-year-old Chinese man in a green work jacket, tired but friendly",
        "voice": "a YOUNG man's voice — lighter, quicker and casual",
    },
    "rider": {
        "short": "mover",
        "img": f"{LIB}/city_delivery_rider_28.png",
        "audio": f"{VOICE}/r13_rider_male.mp3",
        "desc": "a 28-year-old mover in a yellow work jacket with the sleeves rolled up, strong forearms",
        "voice": "a YOUNG man's voice — quick, bright and busy",
    },
    "shop_owner": {
        "short": "stall owner",
        "img": f"{LIB}/core_shop_owner_50.png",
        "audio": f"{VOICE}/r09_adult_male.mp3",
        "desc": "a 50-year-old night-market stall owner with a round face, a blue apron over a checked shirt and a dish towel over his shoulder",
        "voice": "a MIDDLE-AGED man's voice — loud, blunt and street-smart",
    },
    "old_comrade": {
        "short": "old classmate",
        "img": f"{LIB}/core_old_comrade_72.png",
        "audio": f"{VOICE}/r12_elder_male.mp3",
        "desc": "a 72-year-old Chinese man with thinning grey hair, a dark green zip jacket and thick-framed glasses",
        "voice": "an ELDERLY man's voice — raspy, know-it-all and confident",
    },
    "driver": {
        "short": "coach driver",
        "img": f"{LIB}/city_dad_50.png",
        "audio": f"{VOICE}/r09_adult_male.mp3",
        "desc": "a 50-year-old Chinese coach driver in a navy uniform shirt, a lanyard and a peaked cap",
        "voice": "a MIDDLE-AGED man's voice — brisk, official and impatient",
    },
    "chess_friend": {
        "short": "old friend",
        "img": f"{LIB}/core_chess_friend_70.png",
        "audio": f"{VOICE}/p_yinfa_1_1.mp3",
        "desc": "a 70-year-old Chinese man with neat white hair, a maroon cardigan over a shirt and a proud, showy manner",
        "voice": "an ELDERLY man's voice — boastful, deliberate and theatrical",
    },
    "neighbor_li": {
        "short": "neighbour",
        "img": f"{LIB}/core_neighbor_li_68.png",
        "audio": f"{VOICE}/p_storyfm_j_1.mp3",
        "desc": "a 68-year-old Chinese neighbour with short grey hair, a brown jacket and a plain, worried face",
        "voice": "an ELDERLY man's voice — plain, doubtful and matter-of-fact",
    },
    "teen_boy": {
        "short": "boy",
        "img": f"{LIB}/city_son_teen_16.png",
        "audio": f"{VOICE}/r06_child_boy.mp3",
        "desc": "a 14-year-old Chinese boy in a blue school hoodie and shorts, energetic",
        "voice": "a TEENAGE boy's voice — bright, fast and cheeky",
    },
}

PROD = ROOT / "assets/products"
REFS_TAIL = [
    PROD / "折叠-无阴影.png",
    PROD / "正侧-3-无阴影.png",
    PROD / "45度-加水杯-无阴影.png",
]

STYLE = (
    "integrated_multimodal_description: Live-action fun commercial in vertical framing. "
    "Pacing is tight and bouncy; everyone speaks at a natural, brisk conversational pace. The first line starts "
    "within the first quarter second, every line begins immediately after the previous line's last word and "
    "immediately after each cut, gaps between lines stay under a quarter second, no pause exceeds a third of a "
    "second, and the final line ends right at the last moment of the video, with no trailing silence. The camera is "
    "always gently moving — a sideways sweep, a push-in, a slight sway and a pull-back — never static. Shot like "
    "real documentary footage: natural available light with soft realistic shadows, lifelike skin texture with "
    "visible pores and fine lines, natural hair detail, true-to-life colors, shallow depth of field like an 85mm "
    "lens at f/2, photorealistic and candid — no plastic skin, no over-smoothing. Faces are expressive and "
    "theatrical with big visible emotion: narrowed eyes, raised eyebrows, wide-open mouths, clenched jaws and "
    "startled recoils, held clearly long enough for the camera to catch them.\n\n"
)

WHEEL = (
    "WHEELCHAIR: the small silver-grey LIGHTWEIGHT electric wheelchair (matching reference images 3, 4 and 5: "
    "silver-grey frame, black cushion seat, red springs, brand lettering as in references). Its four small wheels "
    "rest on the ground and the seat frame is locked into place; it is an ELECTRIC wheelchair with visible motor "
    "hubs, the distinctive RED shock-absorbing springs and the JOYSTICK CONTROLLER clearly visible on the right "
    "armrest in every shot — never a plain manual wheelchair with large hand rims, never a bicycle, scooter or "
    "motorcycle, and it never deforms, morphs or changes shape. The SAME single wheelchair in every shot.\n"
    "RIDING RULE: the person who uses it is ALWAYS SEATED on the cushion with both hands on the joystick "
    "while it moves; NOBODY ever pushes it from behind, stands beside it while it rolls, or holds the "
    "backrest — it is driven, never pushed.\n"
    "BOTH PEOPLE STAY FULLY VISIBLE in every shot of the whole video; whenever anyone speaks, their face stays "
    "clearly visible to the camera and turned toward it; no speaker is ever out of frame or seen only from behind "
    "while delivering a line. Each person keeps both hands on the wheelchair or at their sides, touching nothing "
    "else, and only the speaker's mouth moves.\n\n"
)

SHOT_TIMES = ["0 to 4 seconds", "4 to 8 seconds", "8 to 11 seconds", "11 to 14.5 seconds"]

TITLES = {
    "D2_01_yeshi": "夜市摞货",
    "D2_02_menkou": "校门口急停",
    "D2_03_laonian": "老年大学抢座",
    "D2_04_daba": "旅游团大巴",
    "D2_05_banjia": "搬新家",
    "D2_06_chalou": "茶楼踢轮",
    "D2_07_miaohui": "庙会慢行",
    "D2_08_yutian": "雨天尾灯",
    "D2_09_luying": "露营收车",
    "D2_10_muqin": "母亲节电量",
}


def build_prompt(script: dict) -> str:
    cast = [CAST_LIB[k] for k in script["cast"]]
    n = len(cast)
    lines = [STYLE]
    lines.append(
        f"CAST (STRICTLY BIND — exactly {n} people and exactly ONE wheelchair; each person appears EXACTLY ONCE "
        "per shot, never duplicated, never cloned or mirrored into a second similar figure; no extra bystanders): "
        "all Chinese, speaking standard Mandarin. The two people must look CLEARLY DIFFERENT from each other at "
        "all times — different age, face shape, hair colour and hairstyle, clothing colour; they must NEVER be "
        "drawn with the same face, hair or outfit, and never look like twins.\n"
    )
    for i, c in enumerate(cast):
        lines.append(
            f"- (S{i + 1}) {c['desc']}, exactly as in reference image {i + 1}. "
            f"VOICE (S{i + 1}): {c['voice']} (reference audio {i + 1}).\n"
        )
    lines.append(
        "The voices are clearly DIFFERENT in pitch and age; never swap them.\n" + WHEEL
    )
    for i, shot in enumerate(script["shots"]):
        segs = [f"[Shot {i + 1}, {SHOT_TIMES[i]}] {shot['desc']} "]
        for j, (who, text) in enumerate(shot["lines"]):
            idx = script["cast"].index(who) + 1
            verb = "says" if j == 0 else "replies"
            short = CAST_LIB[who].get("short", "person")
            # 说话人绑定带角色名：实测 H3 会把 S1/S2 交替对话串人（D2_01 第7句被派给 S1）
            segs.append(f"(S{idx}) the {short} {verb}: <d>[Chinese] {text}</d> ")
        segs.append("ONLY the speaker's mouth moves; the other person's lips stay completely closed. ")
        if i < 3:
            segs.append("Hard cut. ")
        lines.append("".join(segs) + "\n\n")
    lines.append(
        f"Scene: {script['scene']}. Only these people speak, taking turns with no overlap, in exactly this order. "
        "EVERY LINE IS SPOKEN EXACTLY ONCE, no line is ever repeated, doubled or echoed. All dialogue spoken "
        "verbatim, no extra words, no omissions. No on-screen text; dialogue is audio only.\n\n"
    )
    lines.append(
        "overall_soundscape: Ambient outdoor/indoor room tone fitting the scene, clear natural voices.\n\n"
        "non_diegetic_music: N/A\n\n"
        "Hard constraints: exactly ONE wheelchair, always the small silver-grey ELECTRIC lightweight one; each "
        "person appears exactly once per shot and is never duplicated; the two people never swap clothes, faces, "
        "voices or roles; no extra people; no background music; render no watermarks, subtitles or text anywhere; "
        "looks stay exactly consistent with the reference images; hard cuts only, no fades."
    )
    return "".join(lines)


SCRIPTS = [
    # ── #1 夜市摞货 · load_100 ───────────────────────────────
    {
        "uid": "D2_01_yeshi",
        "cast": ["grandpa", "shop_owner"],
        "scene": "a busy night-market lane at dusk, food stalls with warm hanging bulbs on both sides, steam rising, crowd blurred in the background",
        "shots": [
            {"desc": "The round-faced stall owner steps forward and sweeps his right arm across the front of the "
                     "wheelchair, blocking it and pointing his chin at his stall; the grandpa stops calmly and "
                     "smiles, hands resting on the armrests. The camera pushes in slightly on the owner's scowling "
                     "face.",
             "lines": [("shop_owner", "哎，车别停我摊前边。"), ("grandpa", "我帮你搭把手。")]},
            {"desc": "The owner slaps the seat with his flat palm and smirks, eyebrows raised; the grandpa walks "
                     "back into frame carrying two stacked cardboard boxes and sets them down on the wheelchair's "
                     "footrest. The camera pans smoothly from the owner to the grandpa.",
             "lines": [("shop_owner", "就这小车？两箱就压趴。"), ("grandpa", "那你看着。"),
                       ("shop_owner", "扛住，我请客！")]},
            {"desc": "The grandpa stacks a third box, then drops down onto the seat himself with a solid thump; the "
                     "wheelchair does not budge an inch. The owner's eyes go wide and round, his mouth drops open "
                     "and he takes half a step back. The camera sways slightly and holds on the owner's stunned "
                     "face.",
             "lines": [("grandpa", "你说的啊。"), ("shop_owner", "三箱货，你还坐上去？")]},
            {"desc": "The grandfather leans back comfortably; the owner stares at the motionless wheelchair, blinks "
                     "and nods in disbelief. The camera pulls back slowly to show both people and the fully loaded "
                     "wheelchair.",
             "lines": [("grandpa", "两百斤，随便坐。"), ("shop_owner", "哎哟，动都不动。"),
                       ("grandpa", "皮实又省心，认准爱优护轻便侠。")]},
        ],
    },
    # ── #2 校门口急停 · auto_stop ────────────────────────────
    {
        "uid": "D2_02_menkou",
        "cast": ["grandma", "aunt", "teen_boy"],
        "scene": "the pavement outside a school gate after class, metal railing and blurred students behind, bright afternoon light",
        "shots": [
            {"desc": "The aunt raises BOTH arms straight out sideways at shoulder height with palms facing forward "
                     "and keeps them raised in front of the wheelchair through the whole shot, chin lifted and eyes "
                     "narrowed; the grandma sits calmly on the seat. The camera pushes in on her mocking face.",
             "lines": [("aunt", "大娘，接孩子人多，刹得住吗？"), ("grandma", "刹不住，我敢来？")]},
            {"desc": "The aunt jabs a finger at the crowded gate, eyebrows arched mockingly; the grandma raises a "
                     "palm to quiet her. The camera glides gently sideways. The teenage boy is already standing at "
                     "the school gate, bouncing on his toes.",
             "lines": [("aunt", "孩子冲出来，你准撞着。"), ("grandma", "那你看着。"),
                       ("aunt", "你真停住，我帮你拎一月菜。"), ("grandma", "你说的啊。")]},
            {"desc": "The boy runs fast out of the school gate and cuts right across the front of the wheelchair, both "
                     "arms up; the grandma lifts both hands straight up off the controls and holds them in the air. "
                     "The wheelchair stops dead at once. The aunt's eyes snap wide open and her mouth drops open "
                     "in a shout. The camera sways hard and holds on her face.",
             "lines": [("teen_boy", "奶奶！"), ("aunt", "哎哟，孩子！")]},
            {"desc": "The boy skids to a stop beside the frozen wheelchair, laughing; the aunt stares at the "
                     "wheelchair, then at her own feet where it stopped, speechless. The camera pulls back slowly to "
                     "show all three people.",
             "lines": [("grandma", "松手就停，稳稳当当。"), ("aunt", "还真停住了。爱优护轻便侠。")]},
        ],
    },
    # ── #3 老年大学抢座 · cushion_comfy ──────────────────────
    {
        "uid": "D2_03_laonian",
        "cast": ["grandma", "old_comrade"],
        "scene": "the doorway of a community college for seniors, chalkboard and rows of desks behind, corridor light from the left",
        "shots": [
            {"desc": "The old comrade clamps one hand down on the front of the wheelchair, chin forward and brows "
                     "knitted in disdain; the grandma swats his hand away with a flat palm. The camera pushes in "
                     "slightly.",
             "lines": [("old_comrade", "手机都不会使，还玩这个？"), ("grandma", "你撒手，我自己的车。")]},
            {"desc": "The old comrade throws one leg over and lowers himself onto the cushion, one hand still raised "
                     "in protest; the grandma steps aside with folded arms. The camera pans smoothly sideways.",
             "lines": [("old_comrade", "我坐坐看，硬了别怪我。"), ("old_comrade", "哎，这椅子咋这么软乎？")]},
            {"desc": "The old comrade presses both palms into the thick cushion, eyes wide with surprise, shoulders "
                     "melting down; the grandma taps the cushion edge. The camera pushes in slightly on his "
                     "astonished face.",
             "lines": [("grandma", "四公分厚海绵，坐一天不硌。"), ("old_comrade", "我腰疼五年，头回舒坦。")]},
            {"desc": "The grandma reaches for the armrest; the old comrade waves her off and settles deeper, "
                     "grinning like a child, and she shakes her head with a laugh. The camera pulls back slowly.",
             "lines": [("grandma", "那你还不下来？"), ("old_comrade", "别急，我歇会儿。"),
                       ("grandma", "爱优护轻便侠。")]},
        ],
    },
    # ── #4 旅游团大巴 · lcd_screen ───────────────────────────
    {
        "uid": "D2_04_daba",
        "cast": ["grandpa", "driver"],
        "scene": "beside a tour coach on a sunny coach park, the open luggage bay and coach body behind, asphalt ground",
        "shots": [
            {"desc": "The coach driver plants his arm across the gap between the wheelchair and the open luggage "
                     "bay, frowning and shaking his head; the grandpa stands beside the wheelchair with one hand on "
                     "the frame. The camera pushes in slightly.",
             "lines": [("driver", "大爷，这车别搬上去。"), ("grandpa", "我自己拎，磕不着。")]},
            {"desc": "The grandpa grips the folded wheelchair frame with ONE hand and lifts it straight up off the "
                     "ground until it hangs beside him at knee height, his arm straight, and holds it there while he "
                     "speaks; the driver's eyes pop wide open and his mouth drops open. The camera sways slightly.",
             "lines": [("driver", "这么沉，你一个人行？"), ("grandpa", "你瞧，一只手。"),
                       ("driver", "真就一只手？")]},
            {"desc": "The grandpa sets the wheelchair upright on the ground and taps the display on the armrest; the "
                     "driver bends at the waist, hands on knees, squinting at the lit screen. The camera pushes in "
                     "on the screen then tilts up to both faces.",
             "lines": [("grandpa", "还有百分之八十。"), ("driver", "这屏还能看电量？"),
                       ("grandpa", "大太阳底下也看得清。")]},
            {"desc": "The driver straightens up, wipes his brow and gives a thumbs-up toward the grandpa; the "
                     "grandpa nods, one hand still resting on the wheelchair. The camera pulls back slowly.",
             "lines": [("driver", "比我手机还清楚。爱优护轻便侠。")]},
        ],
    },
    # ── #5 搬新家 · shock_18 ────────────────────────────────
    {
        "uid": "D2_05_banjia",
        "cast": ["grandpa", "rider"],
        "scene": "in front of a newly moved-in flat, doorframe with a raised threshold behind, moving boxes stacked along the corridor wall",
        "shots": [
            {"desc": "The mover plants a sack barrow down on the floor with a thud and stands with one hand on his "
                     "hip, smirking down at the wheelchair; the grandpa pats the seat twice. The camera pushes in "
                     "slightly.",
             "lines": [("rider", "你这小玩意儿能扛箱子？"), ("grandpa", "放上来。")]},
            {"desc": "The mover heaves a heavy carton onto the wheelchair and shakes his head, lip curled; the "
                     "grandpa lifts a full glass of water off a box and holds it out to him. The camera pans "
                     "smoothly sideways.",
             "lines": [("rider", "过门槛，东西准颠散。"), ("grandpa", "你端着杯子跟上。")]},
            {"desc": "The grandpa drives the loaded wheelchair across the rough paved ground of the corridor while the "
                     "mover walks beside him holding a full glass of water at chest height; the water surface stays "
                     "perfectly flat with not one ripple. The mover leans in, eyes wide and mouth open, staring at "
                     "the glass. The camera stays close on the glass.",
             "lines": [("rider", "过门槛，水一口没洒？"), ("grandpa", "十八股减震，汽车级的。")]},
            {"desc": "The mover sets the glass down, grips the armrest and starts to sit; the grandpa taps his "
                     "shoulder and he straightens up laughing, then slaps the wheelchair frame. The camera pulls "
                     "back slowly.",
             "lines": [("rider", "我试试，真不颠？"), ("grandpa", "下去，你压不着。"),
                       ("rider", "比手推车稳。爱优护轻便侠。")]},
        ],
    },
    # ── #6 茶楼踢轮 · tire_puncture（平地，无坡；v3：动作精简+表情强化）──
    {
        "uid": "D2_06_chalou",
        "cast": ["grandpa", "chess_friend"],
        "scene": "the flat paved forecourt in front of an old teahouse, wooden benches and a lattice door behind, morning light",
        "shots": [
            {"desc": "The chess friend lifts his right foot and taps the side of the wheelchair's front wheel with "
                     "the toe of his shoe — shoe and wheel touch clearly — then folds his arms and tips his head back "
                     "with a mocking sneer. The grandpa stands beside the wheelchair, calm, one hand on the frame. "
                     "The camera pushes in slightly.",
             "lines": [("chess_friend", "老王，你这胎扎一下就废。"), ("grandpa", "扎了我不推车，信吗？")]},
            {"desc": "The chess friend rocks back on his heels and juts his chin out, disbelieving. The grandpa takes "
                     "a small drawing pin out of his pocket and holds it up between two fingers at chest height. The "
                     "camera glides gently sideways and holds on the pin.",
             "lines": [("chess_friend", "我不信，漏了算你的。"), ("grandpa", "你睁眼瞧。")]},
            {"desc": "The grandpa presses the pin hard against the side of the tyre and it bites into the rubber and "
                     "stays there — the tyre does not deflate at all. The chess friend's eyes bulge, his mouth drops "
                     "wide open and he flinches backwards. The camera pushes in hard on the tyre then snaps to his "
                     "face.",
             "lines": [("chess_friend", "钉子按上去不瘪？"), ("grandpa", "镁合金实心胎，扎不动。")]},
            {"desc": "The chess friend stoops down, presses the tyre with both thumbs and straightens up shaking his "
                     "head, mouth still open in disbelief. The grandpa taps the frame once, satisfied. The camera "
                     "pulls back slowly.",
             "lines": [("grandpa", "零维护，不打气。"), ("chess_friend", "得，我换车。爱优护轻便侠。")]},
        ],
    },
    # ── #7 庙会慢行 · speed_6 ───────────────────────────────
    {
        "uid": "D2_07_miaohui",
        "cast": ["grandma", "youngman"],
        "scene": "a packed temple-fair alley, red lanterns and stalls overhead, dense crowd filling the background",
        "shots": [
            {"desc": "The young man raises BOTH arms straight out sideways at shoulder height with palms forward and "
                     "keeps them raised in front of the wheelchair through the whole shot, smirking down at it; the "
                     "grandma keeps both hands on the joystick. The camera pushes in slightly.",
             "lines": [("youngman", "大娘，前边人堆，您这车过不去。"), ("grandma", "你让让，我往前挪。")]},
            {"desc": "The young man folds his arms and shakes his head, sneering; the grandma tips the joystick "
                     "forward and the wheelchair creeps ahead at a snail's pace, stopping dead a hand-span from his "
                     "shin. The camera glides gently sideways.",
             "lines": [("youngman", "一会儿撞着人，可别怪我。"), ("grandma", "低档，两步一停。")]},
            {"desc": "The wheelchair noses past his knee, holding a steady crawling pace; the young man's eyes go "
                     "wide and he leans back against the crowd, mouth open. The camera sways slightly and holds on "
                     "both faces.",
             "lines": [("youngman", "嚯，这么稳还这么慢？"), ("grandma", "人多就用低档，碰不着人。")]},
            {"desc": "The young man steps aside and waves her through, then lifts his phone and films the wheelchair "
                     "as it edges away between the stalls; the grandma glances back with a small smile. The camera "
                     "pulls back slowly.",
             "lines": [("youngman", "您先过。"), ("grandma", "急啥，稳住就行。"),
                       ("youngman", "这车稳当。爱优护轻便侠。")]},
        ],
    },
    # ── #8 雨天尾灯 · brake_light ───────────────────────────
    {
        "uid": "D2_08_yutian",
        "cast": ["grandpa", "neighbor_li"],
        "scene": "a residential lane in heavy rain, wet asphalt with reflections, parked cars along the kerb, rain streaks on the lens",
        "shots": [
            {"desc": "The neighbour jogs up with a tilted umbrella and throws one arm out in front of the "
                     "wheelchair, squinting through the rain; the grandpa stops and looks up at him from the seat. "
                     "The camera pushes in slightly.",
             "lines": [("neighbor_li", "下这么大雨，刹得住吗？"), ("grandpa", "刹不住我还敢出门？")]},
            {"desc": "The grandpa points a thumb back over his shoulder; the neighbour ducks his head sideways to "
                     "look down the lane behind. The camera pans smoothly around behind the wheelchair.",
             "lines": [("grandpa", "你瞧车后头。")]},
            {"desc": "The grandpa lifts both hands clear off the controls; the wheelchair halts on the wet asphalt "
                     "and the red tail light snaps on, glowing through the rain. The neighbour's eyes go wide and "
                     "his mouth opens, umbrella tipping off his shoulder. The camera holds close on the lit tail "
                     "light.",
             "lines": [("neighbor_li", "车停住了，尾灯还亮？"), ("grandpa", "松手即停，灯自己亮。")]},
            {"desc": "The neighbour straightens his umbrella, peers at the red light and nods with a grin; the "
                     "grandpa settles back on the seat, rain bouncing off the frame. The camera pulls back slowly.",
             "lines": [("neighbor_li", "灯真亮，雨里老远看得见。"), ("grandpa", "越是下雨越得亮。"),
                       ("neighbor_li", "得，明天我去瞅瞅。爱优护轻便侠。")]},
        ],
    },
    # ── #9 露营收车 · fold_1s ───────────────────────────────
    {
        "uid": "D2_09_luying",
        "cast": ["grandpa", "teen_boy"],
        "scene": "a grassy campsite at golden hour, a pitched tent and a parked car with an open boot behind, soft long shadows",
        "shots": [
            {"desc": "The boy raises BOTH arms straight out sideways at shoulder height with palms forward and holds "
                     "them up in front of the wheelchair through the whole shot, chin up and grinning with doubt; the "
                     "grandpa sits relaxed on the seat. The camera pushes in slightly.",
             "lines": [("teen_boy", "这车收起来得五分钟。"), ("grandpa", "你掐着表。")]},
            {"desc": "The boy turns away and bends for a tent pole, still talking over his shoulder; the grandpa "
                     "stands up with a grin, one foot already braced against the frame. The camera glides gently "
                     "sideways.",
             "lines": [("teen_boy", "您收着，我先扛帐篷。"), ("grandpa", "回头看。")]},
            {"desc": "The grandpa presses the release and folds the wheelchair down in one smooth movement — it "
                     "clicks into a compact column standing upright on the ground. The boy spins round mid-turn, "
                     "eyes bulging, mouth wide open. The camera pushes in hard on the folded wheelchair then tilts "
                     "up to his face.",
             "lines": [("teen_boy", "哎，成这么快？"), ("grandpa", "镁铝合金，一秒折好。")]},
            {"desc": "The grandpa picks the folded wheelchair up by its handle with one hand and swings it into the "
                     "car boot; the boy spreads his arms to measure it, laughing, and the grandpa claps his "
                     "shoulder. The camera pulls back slowly to show the car and the campsite.",
             "lines": [("teen_boy", "这么点大，比凳子小。"), ("grandpa", "顺手丢后备箱，不占地儿。"),
                       ("teen_boy", "爷爷，这车真行。爱优护轻便侠。")]},
        ],
    },
    # ── #10 母亲节电量 · range_39 ───────────────────────────
    {
        "uid": "D2_10_muqin",
        "cast": ["mom", "daughter"],
        "scene": "the courtyard of a family house on a bright afternoon, potted plants and a low wall behind, bicycle leaning on the wall",
        "shots": [
            {"desc": "The daughter raises BOTH arms straight up above her head with palms forward and keeps them raised "
                     "in front of the wheelchair through the whole shot, frowning with worry; the mom sits on the "
                     "seat, hands folded and patient. The camera pushes in slightly.",
             "lines": [("daughter", "妈别去，这电撑不到集市。"), ("mom", "我昨天刚充的。")]},
            {"desc": "The daughter counts on her fingers and points down the lane, eyebrows knitted; the mom turns "
                     "the joystick and rolls away out of the courtyard. The camera glides gently sideways, keeping "
                     "both in frame.",
             "lines": [("daughter", "来回两趟，半路没电咋办？"), ("mom", "你等着，我跑你看。")]},
            {"desc": "The mom comes rolling back in, unhurried and smiling; the daughter stares down at her, hands on "
                     "hips, eyes wide and mouth open, then bends to look at the armrest display. The camera sways "
                     "slightly and holds on the lit screen.",
             "lines": [("daughter", "妈，您都跑两趟了？"), ("mom", "三十九公里，够来回跑。")]},
            {"desc": "The daughter taps the armrest display once, straightens up and laughs, raising both hands in "
                     "surrender; the mom nods, satisfied, hands on the joystick. The camera pulls back slowly over "
                     "the sunny courtyard.",
             "lines": [("daughter", "哎，电量还这么多？"), ("mom", "以后别拦我。"),
                       ("daughter", "行，我服了。爱优护轻便侠。")]},
        ],
    },
]


def main() -> None:
    for s in SCRIPTS:
        prompt = build_prompt(s)
        cast = [CAST_LIB[k] for k in s["cast"]]
        refs = [str(ROOT / c["img"]) for c in cast] + [str(p) for p in REFS_TAIL]
        audios = [str(ROOT / c["audio"]) for c in cast]
        spec = {
            "job_uid": s["uid"],
            "template_id": "manual", "template_name": "manual", "mode": "manual",
            "workflow": "minimax_h3_image_audio_to_video_v2_15s",
            "fallback_workflows": [],
            "duration": 15,
            "resolution": "768p竖",
            "ref_images": refs,
            "ref_audios": audios,
            "prompt": prompt,
            "lines_meta": [],
        }
        jp = ROOT / f"state/onetake_prompt_job_{s['uid']}.json"
        jp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / f"docs/onetake_check_{s['uid']}.txt").write_text(prompt, encoding="utf-8")
        print(f"✓ {TITLES[s['uid']]:8s} → {jp.name}  (图 {len(refs)} / 音 {len(audios)})")
    print(f"\n共 {len(SCRIPTS)} 条 spec 已生成")


if __name__ == "__main__":
    main()
