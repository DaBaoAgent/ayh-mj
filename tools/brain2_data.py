"""脑洞10连第二批 — 结构化数据（10 条 × 4 镜）

镜头分配原则（继承 T20 v3 经验）：
- 每镜 2-3 句，镜内双人来回
- 镜头动：拉/推/摇，零走位
- 每镜 ≤3 人；全片 2 人为主（#8 已简化为 2 人）
- 音色：r01奶奶 / r12爷爷 / r03青年 / r05女儿 / r06小男孩 / r08阿姨 / r09男成年 / r13骑手
"""
from __future__ import annotations

from pathlib import Path

LIB = "assets/cast/library"
VOICE = "assets/cast/voice/real"

# 共用角色定义（name -> img/desc/voice）
CAST_LIB = {
    "grandma": {
        "img": f"{LIB}/city_grandma_70.png",
        "audio": f"{VOICE}/r01_elder_female.mp3",
        "desc": "a 70-year-old Chinese grandma with silver permed hair, a purple cardigan and a pearl necklace",
        "voice": "an ELDERLY woman's voice — warm, low and unhurried",
    },
    "grandpa": {
        "img": f"{LIB}/city_grandpa_75.png",
        "audio": f"{VOICE}/r12_elder_male.mp3",
        "desc": "a 75-year-old Chinese grandpa with white hair and deep wrinkles, a grey knit sweater",
        "voice": "an ELDERLY man's voice — low, deep and slow",
    },
    "rider": {
        "img": f"{LIB}/city_delivery_rider_28.png",
        "audio": f"{VOICE}/r13_rider_male.mp3",
        "desc": "a 28-year-old delivery rider in a yellow jacket with a helmet slung on his arm",
        "voice": "a YOUNG man's voice — quick, bright and busy",
    },
    "youngman": {
        "img": f"{LIB}/city_young_man_30.png",
        "audio": f"{VOICE}/r03_young_male.mp3",
        "desc": "a 30-year-old Chinese man in a green work jacket, tired but friendly",
        "voice": "a YOUNG man's voice — lighter, quicker and casual",
    },
    "aunt": {
        "img": f"{LIB}/city_neighbor_aunt_55.png",
        "audio": f"{VOICE}/r08_aunt_female.mp3",
        "desc": "a 55-year-old Chinese neighbor aunt with curly hair, a purple sportswear jacket and a chatty look",
        "voice": "a MATURE woman's voice — bright, chatty and gossipy",
    },
    "daughter": {
        "img": f"{LIB}/city_daughter_35.png",
        "audio": f"{VOICE}/r05_young_female.mp3",
        "desc": "a 35-year-old Chinese woman in commuting clothes, capable and gentle",
        "voice": "a YOUNG woman's voice — clear and gentle",
    },
    "guard": {
        "img": f"{LIB}/city_security_guard_45.png",
        "audio": f"{VOICE}/r09_adult_male.mp3",
        "desc": "a 45-year-old community security guard in a dark blue uniform, simple and honest",
        "voice": "a MIDDLE-AGED man's voice — plain and honest",
    },
    "mechanic": {
        "img": f"{LIB}/city_dad_50.png",
        "audio": f"{VOICE}/r09_adult_male.mp3",
        "desc": "a 50-year-old repair-shop owner in dark blue work clothes, weathered and kind",
        "voice": "a MIDDLE-AGED man's voice — plain and honest",
    },
    "boy": {
        "img": f"{LIB}/city_boy_10.png",
        "audio": f"{VOICE}/r06_child_boy.mp3",
        "desc": "a 10-year-old Chinese boy with a buzz cut and a red-white sporty jacket, lively",
        "voice": "a BOY's voice — bright and chirpy",
    },
}

# 10 条脚本
SCRIPTS = [
    {
        "uid": "B2_01_kuaidi", "title": "快递驿站", "point": "small_boot",
        "scene": "the parcel pickup area of a residential compound, metal shelves packed with parcels",
        "cast": ["grandma", "rider"],
        "shots": [
            {"desc": "The rider scans a slim folded wheelchair leaning by the shelf over and over, puzzled, while the grandma waits with her arms crossed.",
             "lines": [("rider", "老板，这个包裹扫不上码。"), ("grandma", "那不是包裹，是我的车。")]},
            {"desc": "Close on the rider's shocked face, then the grandma grabs the folded frame and unfolds it with one pull — a complete wheelchair appears.",
             "lines": [("rider", "车？！这分明就是个箱子。"), ("grandma", "看好了——")]},
            {"desc": "The rider steps back, both hands up, then points at the now-unfolded wheelchair.",
             "lines": [("rider", "哎哟！一拉就是一台车？！"), ("grandma", "折起来三十公分，比行李箱小。")]},
            {"desc": "The grandma sits on it, calmly rolls one meter forward and stops, smug; the rider claps once.",
             "lines": [("rider", "这是变魔术吧？"), ("grandma", "年轻人，多学着点。"), ("rider", "服了服了。")]},
        ],
    },
    {
        "uid": "B2_02_diaoyu", "title": "钓鱼搭子", "point": "cushion_comfy",
        "scene": "a river embankment at dusk, fishing rods on stands, a bucket beside each man",
        "cast": ["grandpa", "youngman"],
        "shots": [
            {"desc": "The young man grips his lower back and groans as he tries to stand up from a tiny folding stool; the grandpa sits relaxed on the wheelchair beside him, rod in hand.",
             "lines": [("youngman", "坐一天了，我腰都快断了。"), ("grandpa", "你坐的是折叠凳吧？")]},
            {"desc": "The young man rubs his waist and looks at the grandpa enviously; the grandpa has not moved an inch.",
             "lines": [("youngman", "您坐一天不难受？"), ("grandpa", "四公分厚海绵，透气不闷。")]},
            {"desc": "The young man leans over to press the wheelchair seat with his palm, surprised.",
             "lines": [("youngman", "这坐垫比钓箱舒服。"), ("grandpa", "嘘，别惊了我的鱼。")]},
            {"desc": "The grandpa leans back and closes his eyes for a nap under a hat; the young man starts typing on his phone.",
             "lines": [("grandpa", "爱优护轻便侠，坐着舒服。"), ("youngman", "得，我明天也整一台。")]},
        ],
    },
    {
        "uid": "B2_03_luying", "title": "露营夜", "point": "tire_puncture",
        "scene": "a campsite with tents, a gravel path with small stones, string lights at dusk",
        "cast": ["grandpa", "youngman"],
        "shots": [
            {"desc": "The young man drags a suitcase whose wheels get stuck between stones with a thud; the grandpa rolls past him on the wheelchair over the same gravel, smooth as a breeze.",
             "lines": [("youngman", "这破石子路，箱子轮子要废了。"), ("grandpa", "我这车，专走这种路。")]},
            {"desc": "The young man looks down at the wheelchair's solid tires; the grandpa pats the wheel.",
             "lines": [("youngman", "实心的？扎不扎？"), ("grandpa", "镁合金实心胎，钉子都扎不动。")]},
            {"desc": "The young man crouches and taps the tire with a bottle-opener key — a hard clink; he looks impressed.",
             "lines": [("youngman", "还真硬！维护呢？"), ("grandpa", "零维护，不爆胎。")]},
            {"desc": "The grandpa rolls toward the tent unhurried; the young man jogs two steps after him.",
             "lines": [("youngman", "链接发我一个。"), ("grandpa", "搜轻便侠，自己找。"), ("youngman", "这个真不赖。")]},
        ],
    },
    {
        "uid": "B2_04_chongdian", "title": "客厅充电", "point": "lithium_safe",
        "scene": "a bright living room, the wheelchair parked next to the sofa charging from a wall socket",
        "cast": ["grandpa", "aunt"],
        "shots": [
            {"desc": "The aunt passes the open doorway, sees the wheelchair charging in the living room and freezes mid-step, pointing.",
             "lines": [("aunt", "诶？你咋在屋里充电？！"), ("grandpa", "咋了，有啥不行？")]},
            {"desc": "The aunt clutches her chest dramatically; the grandpa sits on the sofa sipping tea, unbothered.",
             "lines": [("aunt", "电动的东西，屋里多危险。"), ("grandpa", "医疗级锂电，我充仨月了。")]},
            {"desc": "Close on the charging port and its small indicator light; the aunt squints at it, half-convinced.",
             "lines": [("aunt", "真没事？"), ("grandpa", "过充保护，插着睡都行。")]},
            {"desc": "The aunt nods slowly, takes a photo of the wheelchair with her phone.",
             "lines": [("aunt", "那我彻底放心了。"), ("grandpa", "科技不一样喽。"), ("aunt", "那我家那个敢情得换了。")]},
        ],
    },
    {
        "uid": "B2_05_xueche", "title": "一分钟学会", "point": "voice_ai",
        "scene": "a community open ground with flower beds, morning light, an empty paved path",
        "cast": ["grandma", "daughter"],
        "shots": [
            {"desc": "The daughter bends over the handlebar pointing at buttons, talking fast; the grandma sits on the wheelchair with a resigned face.",
             "lines": [("daughter", "妈，先按这个，再推那个……"), ("grandma", "你别说了，我自己来。")]},
            {"desc": "The daughter throws her hands up, exasperated; the grandma presses the power button confidently, and the wheelchair chimes softly.",
             "lines": [("daughter", "哎呀妈，您又乱按。"), ("grandma", "按一下，推一下，走了。")]},
            {"desc": "The wheelchair glides forward smoothly a meter and stops neatly; the daughter stares, mouth open.",
             "lines": [("daughter", "就这么简单？"), ("grandma", "它有语音提示，跟着走就行。")]},
            {"desc": "The grandma circles back neatly in front of the frozen daughter and pats the armrest.",
             "lines": [("daughter", "我教半天没教会，您十秒就走了？"), ("grandma", "爱优护轻便侠，会说话。")]},
        ],
    },
    {
        "uid": "B2_06_zhaiXiang", "title": "窄巷调头", "point": "joystick_360",
        "scene": "a narrow old alley with grey brick walls, a dead end ahead, potted plants by the wall",
        "cast": ["grandma", "guard"],
        "shots": [
            {"desc": "The guard hurries along the alley waving his hand at the grandma; she keeps rolling toward the dead end calmly.",
             "lines": [("guard", "大娘，前头是死胡同，进不去。"), ("grandma", "我进去看看。")]},
            {"desc": "The guard stops at the alley mouth, arms crossed, shaking his head with a knowing look; the grandma's calm voice comes from inside.",
             "lines": [("guard", "进去容易，出来可就费劲了。"), ("grandma", "一把就出来。")]},
            {"desc": "At the dead end, the grandma rotates the joystick; the wheelchair spins neatly on the spot, 360 degrees, and faces back out.",
             "lines": [("guard", "好家伙，原地转了个圈？！"), ("grandma", "三百六十度操纵，窄地儿不卡。")]},
            {"desc": "The wheelchair glides back out past the stunned guard; he takes off his cap and scratches his head.",
             "lines": [("guard", "这车，神了！"), ("grandma", "少见多怪。"), ("guard", "我这得给你拍下来。")]},
        ],
    },
    {
        "uid": "B2_07_jiedian", "title": "接电话", "point": "auto_stop",
        "scene": "a gentle slope on a community path, low hedges along the sides, soft afternoon light",
        "cast": ["grandma", "daughter"],
        "shots": [
            {"desc": "The grandma rolls up the gentle slope; her phone rings in her pocket. The daughter stands at the bottom, cupping her hands and shouting.",
             "lines": [("daughter", "妈！坡上别松手！")]},
            {"desc": "The grandma takes out the phone and answers it, both hands occupied — the wheelchair stands perfectly still on the slope.",
             "lines": [("grandma", "喂？接个电话——"), ("daughter", "完了完了，溜坡了！")]},
            {"desc": "The daughter runs up, panting, and stops dead — the wheelchair has not moved an inch. She stares at it.",
             "lines": [("grandma", "嚷嚷啥，它自己停着呢。"), ("daughter", "真没动！一点都不溜！"), ("daughter", "这也太稳了吧！")]},
            {"desc": "The grandma hangs up, pats the armrest and points at the brake light on the wheelchair's rear.",
             "lines": [("grandma", "松手即停，电磁刹车。"), ("grandma", "你急啥，它有数。"), ("daughter", "给我婆婆也买一台。"), ("grandma", "爱优护轻便侠。")]},
        ],
    },
    {
        "uid": "B2_08_nianhuo", "title": "年货大队", "point": "load_100",
        "scene": "the ground floor of an old residential building at New Year, red couplets on doorways, shopping bags everywhere",
        "cast": ["grandma", "boy"],
        "shots": [
            {"desc": "The grandma hangs red shopping bags on both handlebar sides of the wheelchair, one after another; the boy watches with a candy in his mouth.",
             "lines": [("boy", "奶奶，这些年货能装下吗？"), ("grandma", "挂上，都挂上，两边都挂。")]},
            {"desc": "The boy climbs onto the wheelchair's footrest and sits on the seat edge; the grandma steadies him by the arm.",
             "lines": [("boy", "我也要坐！"), ("boy", "压得坏吗？")]},
            {"desc": "The grandma pats the frame, thumps it once with her fist; the wheelchair does not budge, bags swaying gently.",
             "lines": [("grandma", "一百公斤承重，压不坏。"), ("boy", "那我坐，奶奶推我，稳着呢。")]},
            {"desc": "The grandma pushes the loaded wheelchair toward the gate; the boy waves both hands, bags swinging.",
             "lines": [("grandma", "坐稳喽，扶好。"), ("boy", "走喽走喽！"), ("grandma", "爱优护轻便侠，扛造。")]},
        ],
    },
    {
        "uid": "B2_09_xiuche", "title": "修车铺", "point": "warranty_life",
        "scene": "a small street repair shop with tires and wrenches on the wall, the wheelchair parked in the middle",
        "cast": ["grandpa", "mechanic"],
        "shots": [
            {"desc": "The mechanic circles the wheelchair, wiping his hands on a rag, and sizes it up with a professional squint.",
             "lines": [("mechanic", "这车看着金贵，保几年啊？"), ("grandpa", "车架，终身。")]},
            {"desc": "The mechanic's eyes go wide; he stops wiping his hands mid-motion.",
             "lines": [("mechanic", "终身？！没逗我？")]},
            {"desc": "The grandpa taps the frame and the motor housing calmly; the mechanic leans in to listen.",
             "lines": [("grandpa", "电机保两年，售后终身。"), ("mechanic", "你们这是真敢保。")]},
            {"desc": "The mechanic chuckles and shakes his head, giving a thumbs-up; the grandpa nods, satisfied.",
             "lines": [("mechanic", "那这铺子，怕是要少个客户。"), ("grandpa", "修别的，你还有的忙。"), ("mechanic", "这我头一回听说啊。"), ("grandpa", "爱优护轻便侠。")]},
        ],
    },
    {
        "uid": "B2_10_jiaoChe", "title": "祖孙飙车", "point": "speed_6",
        "scene": "a park jogging path with trees, dappled sunlight, a small bicycle with training wheels ahead",
        "cast": ["grandma", "boy"],
        "shots": [
            {"desc": "The boy pedals his little bike ahead, looking back over his shoulder and laughing; the grandma sits on the wheelchair far behind, hands on the joystick.",
             "lines": [("boy", "奶奶，来追我呀！"), ("grandma", "那奶奶可不客气了哈。")]},
            {"desc": "The boy looks back again, grin wide — then his eyes pop as the wheelchair draws level with him fast.",
             "lines": [("boy", "哈哈追不上吧——诶？！")]},
            {"desc": "The grandma sails past, hair flying, one hand steady on the joystick, smug smile.",
             "lines": [("grandma", "快档，走着。"), ("boy", "奶奶你咋比我还快？！")]},
            {"desc": "The grandma stops ahead and turns back toward the panting boy, dusting her hands.",
             "lines": [("grandma", "慢档遛弯，快档遛孙。"), ("boy", "我使劲蹬！"), ("boy", "那我也要一台！"), ("grandma", "爱优护轻便侠。")]},
        ],
    },
]
