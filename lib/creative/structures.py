"""StorySpec 结构骨架库（Phase 5 §结构多样性要求）。

计划要求"至少支持 10 种不同 StorySpec，而不是全部套 4×8"。这 10 个骨架就是
Planner 的候选母版：每种骨架自带镜头结构 / 叙事弧 / 台词模式 / 音轨模式 /
镜头语言 / 角色槽位组合 / 产品角色 / 冲突强度 / 视觉潜力 / 制作成本系数。

骨架只描述**结构**，不写死内容——内容由 CreativeDNA 的其余字段（卖点/角度/热点）填充。
"""
from __future__ import annotations

# 成本系数：0 便宜（少镜头、无对白、少角色），1 贵（多镜头、多角色、多转场）
STORY_STRUCTURES: tuple[dict, ...] = (
    {
        "id": "S_duo_conflict", "name": "双人对撞短剧",
        "shot_pattern": "四镜双人对撞", "shots": 4,
        "narrative_arc": "打脸反转", "dialogue_mode": "双人对白", "audio_mode": "现场同期声",
        "camera_language": "固定机位中景", "cast_pattern": "@elder_male+@mid_male",
        "product_role": "解题工具", "conflict_type": "质疑能力", "visual_motif": "坡道爬升",
        "visual_potential": 0.7, "conflict_strength": 0.95, "generation_cost": 0.6,
        "hook_types": ("冲突质问", "反差打脸", "痛点共鸣"),
        "directions": "两句一回合的短剧节奏：质疑 → 现场演示 → 打脸 → 收口卖点。",
    },
    {
        "id": "S_solo_vlog", "name": "单人Vlog/生活流",
        "shot_pattern": "五镜生活流", "shots": 5,
        "narrative_arc": "日常纪实", "dialogue_mode": "画外音旁白", "audio_mode": "旁白+BGM",
        "camera_language": "手持跟拍", "cast_pattern": "@elder_male",
        "product_role": "配角道具", "conflict_type": "无冲突氛围向", "visual_motif": "折叠收放",
        "visual_potential": 0.55, "conflict_strength": 0.25, "generation_cost": 0.35,
        "hook_types": ("身份代入", "痛点共鸣", "视觉奇观"),
        "directions": "一天的生活切片，产品自然出现三次以内，靠真实感而不是戏剧性。",
    },
    {
        "id": "S_street_interview", "name": "街访/伪纪录",
        "shot_pattern": "手持街访", "shots": 4,
        "narrative_arc": "误会解除", "dialogue_mode": "街访问答", "audio_mode": "现场同期声",
        "camera_language": "手持跟拍", "cast_pattern": "@neighbor_any+@mid_male",
        "product_role": "实验对象", "conflict_type": "陌生人误解", "visual_motif": "单手提起",
        "visual_potential": 0.5, "conflict_strength": 0.6, "generation_cost": 0.55,
        "hook_types": ("悬念设问", "身份代入", "反差打脸"),
        "directions": "手持采访体，路人先猜错，再被实测结果纠正；真实感就是钩子。",
    },
    {
        "id": "S_suspense_reveal", "name": "悬念揭晓",
        "shot_pattern": "悬念三段式", "shots": 4,
        "narrative_arc": "悬念揭晓", "dialogue_mode": "字幕驱动", "audio_mode": "BGM+音效",
        "camera_language": "近景特写", "cast_pattern": "@mid_female+@elder_female",
        "product_role": "惊喜礼物", "conflict_type": "家人反对", "visual_motif": "雨夜灯光",
        "visual_potential": 0.75, "conflict_strength": 0.7, "generation_cost": 0.5,
        "hook_types": ("悬念设问", "神秘物件", "视觉奇观"),
        "directions": "前 3 秒只给神秘局部，逐层拉远，结尾揭晓产品与用途。",
    },
    {
        "id": "S_magic_loop", "name": "魔性动作循环",
        "shot_pattern": "三镜魔性循环", "shots": 3,
        "narrative_arc": "重复强化", "dialogue_mode": "无对白", "audio_mode": "纯音效",
        "camera_language": "固定机位中景", "cast_pattern": "@elder_male",
        "product_role": "解题工具", "conflict_type": "无冲突氛围向", "visual_motif": "折叠收放",
        "visual_potential": 0.85, "conflict_strength": 0.2, "generation_cost": 0.25,
        "hook_types": ("视觉奇观", "夸张数字", "痛点共鸣"),
        "directions": "同一动作往返重复两次 + 同动作三次，靠节奏与音效洗脑，几乎零台词。",
    },
    {
        "id": "S_product_test", "name": "产品实验/对比",
        "shot_pattern": "实验对比双线", "shots": 4,
        "narrative_arc": "对比实验", "dialogue_mode": "单人口播", "audio_mode": "人声+字幕",
        "camera_language": "低角度仰拍", "cast_pattern": "@mid_male+@young_male",
        "product_role": "对比主角", "conflict_type": "价格攀比", "visual_motif": "坡道爬升",
        "visual_potential": 0.7, "conflict_strength": 0.75, "generation_cost": 0.65,
        "hook_types": ("夸张数字", "反差打脸", "悬念设问"),
        "directions": "左右分屏式对比：贵的翻车、便宜的稳过；数据字幕压屏。",
    },
    {
        "id": "S_pov_first", "name": "POV 第一人称",
        "shot_pattern": "POV主观视角", "shots": 4,
        "narrative_arc": "情感递进", "dialogue_mode": "单人口播", "audio_mode": "旁白+BGM",
        "camera_language": "第一人称POV", "cast_pattern": "@mid_female",
        "product_role": "解题工具", "conflict_type": "身体不便", "visual_motif": "遥控轨迹",
        "visual_potential": 0.65, "conflict_strength": 0.55, "generation_cost": 0.4,
        "hook_types": ("身份代入", "痛点共鸣", "悬念设问"),
        "directions": "镜头就是用户的眼睛：出门、进电梯、过坎，手感与视角一致。",
    },
    {
        "id": "S_silent_slapstick", "name": "无对白肢体喜剧",
        "shot_pattern": "无对白肢体三段", "shots": 3,
        "narrative_arc": "误会解除", "dialogue_mode": "无对白", "audio_mode": "纯音效",
        "camera_language": "俯拍全景", "cast_pattern": "@elder_male+@young_male",
        "product_role": "惊喜礼物", "conflict_type": "质疑能力", "visual_motif": "单手提起",
        "visual_potential": 0.8, "conflict_strength": 0.6, "generation_cost": 0.3,
        "hook_types": ("视觉奇观", "反差打脸", "夸张数字"),
        "directions": "纯肢体三段：搬不动 → 一按折叠 → 单手拎走；靠表情与音效讲完全部。",
    },
    {
        "id": "S_emotional_story", "name": "情感故事",
        "shot_pattern": "五镜情感递进", "shots": 5,
        "narrative_arc": "先抑后扬", "dialogue_mode": "双人对白", "audio_mode": "人声+字幕",
        "camera_language": "侧移横移", "cast_pattern": "@elder_female+@mid_male",
        "product_role": "惊喜礼物", "conflict_type": "家人反对", "visual_motif": "老照片对比",
        "visual_potential": 0.6, "conflict_strength": 0.5, "generation_cost": 0.7,
        "hook_types": ("痛点共鸣", "身份代入", "悬念设问"),
        "directions": "亲情视角：老人将就 → 儿女看在眼里 → 礼物落地 → 收在笑容上。",
    },
    {
        "id": "S_comment_reply", "name": "评论区续集/回应型",
        "shot_pattern": "评论区回应式", "shots": 4,
        "narrative_arc": "误会解除", "dialogue_mode": "字幕驱动", "audio_mode": "BGM+音效",
        "camera_language": "近景特写", "cast_pattern": "@elder_male+@young_female",
        "product_role": "实验对象", "conflict_type": "陌生人误解", "visual_motif": "轮圈细节",
        "visual_potential": 0.6, "conflict_strength": 0.65, "generation_cost": 0.45,
        "hook_types": ("冲突质问", "神秘物件", "悬念设问"),
        "directions": "首帧直接贴一条质疑评论，正片就是现场回应并给出证据。",
    },
)

_INDEX = {s["id"]: s for s in STORY_STRUCTURES}


def structure_ids() -> tuple[str, ...]:
    return tuple(s["id"] for s in STORY_STRUCTURES)


def structure_by_id(structure_id: str) -> dict:
    return _INDEX[structure_id]
