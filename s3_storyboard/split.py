"""智能分镜 v3 — 短剧级专业分镜（4-6镜快切 + 全程对白 + 开场冲突）

每镜产出（专业分镜结构，参照 drama-skills/BigBanana 方法论）：
  · purpose: 叙事目的（"开场冲突钩子"等）
  · shot_size / camera: 景别 + 机位运镜（专业镜头语言）
  · start_state / end_state: 起点/终点画面
  · speaker / narration: 说话人 + 台词（单人说话，口型最稳）
  · sound_design: 声音设计（对白+具体音效）
  · scene_prompt: H3 官方三段式提示词（含 <d> 台词）
  · product_ref: 产品图引用

用法：
    python s3_storyboard/split.py --uid job_xxx
    python s3_storyboard/split.py --top 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.llm import chat_json
from lib.state import connect, list_jobs, update_job

# 产品白底图库（用于 H3 参考图）
PRODUCT_REFS = {
    "正侧": "正侧-3-无阴影.png",
    "正侧带背包": "正侧-3-无阴影-带头枕-背包.png",
    "45度": "45度-加水杯-无阴影.png",
    "45度带头枕": "45度-加水杯-无阴影-带头枕.png",
    "折叠": "折叠-无阴影.png",
    "后躺": "后躺_Main_0045.jpg",
    "后躺老外": "后躺老外.png",
    "轻便侠5517": "轻便侠-5517x5517-无阴影.jpg",
}

SYSTEM_PROMPT = """你是短剧分镜导演。把一个软广脚本拆解成 4-6 个专业分镜镜头，用于 AI 视频生成（H3 原生对白模式）。

产品：爱优护轻便侠218电动轮椅（一键自动折叠、13.8公斤、轻便稳）

【硬性结构（违反=不合格）】
1. 镜头数 4-6 个，每镜时长 2.5-4 秒（快切节奏，总时长 12-16 秒）
2. **第1镜必须是冲突/对抗开场**（钩子）——直接进入矛盾（质问/反驳/顶嘴），不铺垫不寒暄
   钩子类型可选：冲突质问/数字冲击/悬念/反常识/痛点直击/对比反差/路人疑惑
3. **全程对白**：每一镜都必须有人说话（禁止静音镜头，旁白也算）
4. **每镜只有一个人说话**（口型最稳）；两人对话时轮流分到不同镜头；画外音可写"画外"
5. 相邻镜头景别必须不同（极近特写/近景/中景/全景轮换）
6. 至少 1 镜展示产品动作（折叠/拎起/放后备箱，用低角度仰拍显质感）

【每镜必须输出字段】
- seq: 镜号（从1开始）
- duration: 时长秒（2.5-4）
- purpose: 叙事目的（一句话，如"开场冲突钩子：儿子质问"）
- shot_size: 景别（极近特写/近景/中景/全景）
- camera: 机位+运镜（如"手持感微晃，手部特写快速上摇到面部" / "固定近景浅景深" / "低角度仰拍轻微推近"）
- start_state: 起点画面
- end_state: 终点画面
- speaker: 说话人（S1=儿子/S2=母亲/画外）
- narration: 台词（纯文字）
- sound_design: 声音设计（对白+**具体**音效，如"刹车金属松垮声"/"折叠咔哒声"；禁止"环境音"这种笼统词）
- scene_prompt: H3 提示词（格式见下）
- product_ref: 产品图引用（从可选列表选）

【scene_prompt 格式（H3 官方三段式，严格要求）】
第一段开头 fixed 为 "integrated_multimodal_description: [Shot N] "，之后写：
- 风格+镜头语言（英文）：景别/机位/运镜/光线/场景（如 "Live-action documentary drama, urgent handheld camera feel, close-up tilting up to a tense face"）
- 人物：编号 (S1)/(S2) + 外貌服装"keep their exact faces, hairstyles and clothing from the reference images"
- 台词逐字包在 <d>[Chinese] 台词</d> 里（<d> 外面只写动作和语气；句尾声明 "Only the speaker speaks; nobody else moves their mouth.")
- 产品声明："The wheelchair keeps its exact frame shape, color and brand lettering from the reference images."

第二段 "overall_soundscape: " + 具体音效（英文）
第三段 "non_diegetic_music: N/A"
第四段 "Hard constraints: render no watermarks, subtitles, captions, floating text, letters, numbers, stickers, price tags, platform logos, UI elements or QR codes anywhere in frame; keep the product's own brand lettering exactly as in the reference image; no background music."

【台词规则（最高优先）】
- 每镜台词字数 ≤ 时长 × 4.5（3秒≤13字、4秒≤18字）
- 全文台词合计 ≥ 总时长的 85%（全程有声，不被静音段稀释）
- 禁止阿拉伯数字（218→二一八、13.8→十三点八）；禁止英文夹带
- 口语化（像真人吵架/聊天），开场要有对抗性
- 禁止改写、漏词、加词、重复、抢话

【场景设定】
- 中国城市小区实景（灰色地砖/绿树/秋日午后自然光）
- 人物设定：S1=45岁儿子（黑夹克/牛仔裤），S2=68岁母亲（酒红抓绒衣，坐轮椅）

参考图可选（product_ref 字段必须从这里选；不出现产品用空字符串 ""）：
- "正侧" / "正侧带背包" / "45度" / "45度带头枕" / "折叠" / "后躺" / "后躺老外" / "轻便侠5517"

返回严格 JSON（不要 markdown 代码块）：
{
  "shots": [
    {
      "seq": 1,
      "duration": 3,
      "purpose": "开场冲突钩子：儿子急停质问",
      "shot_size": "近景",
      "camera": "手持感微晃，手抓扶手特写快速上摇到儿子面部",
      "start_state": "儿子的手抓住轮椅扶手",
      "end_state": "儿子俯身质问，母亲瞪眼回看",
      "speaker": "S1",
      "narration": "台词文字",
      "sound_design": "对白+刹车金属松垮声",
      "scene_prompt": "integrated_multimodal_description: [Shot 1] ...<d>[Chinese] 台词</d>...\\n\\noverall_soundscape: ...\\n\\nnon_diegetic_music: N/A\\n\\nHard constraints: ...",
      "product_ref": "正侧"
    }
  ],
  "total_duration": 15,
  "opening_hook": "开场冲突一句话说明"
}"""


def split_script(script: str, trend_title: str = "") -> dict:
    """把脚本拆成分镜（v3 专业结构）"""
    user_msg = f"""话题背景：{trend_title}

口播脚本：
{script}

请拆解专业分镜（4-6镜快切、全程对白、开场冲突）。总时长控制在 12-16 秒。"""

    data = chat_json([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ], temperature=0.5, max_tokens=4000)

    # 校验与修复
    shots = data.get("shots", [])
    warnings = []
    for shot in shots:
        # product_ref 合法性
        if shot.get("product_ref") and shot["product_ref"] not in PRODUCT_REFS:
            warnings.append(f"镜{shot.get('seq')}: product_ref 非法已置空")
            shot["product_ref"] = ""
        # 字数/时长
        dur = shot.get("duration", 3)
        narr_len = len(shot.get("narration", ""))
        if narr_len > dur * 4.5 + 1:
            warnings.append(f"镜{shot.get('seq')}: 台词{narr_len}字超{dur}秒容量({dur * 4.5:.0f}字)")

    # 相邻景别检查
    for i in range(1, len(shots)):
        if shots[i].get("shot_size") == shots[i - 1].get("shot_size"):
            warnings.append(f"镜{shots[i].get('seq')}: 与上一镜景别相同({shots[i].get('shot_size')})")

    # 开场冲突检查
    first_purpose = shots[0].get("purpose", "") if shots else ""
    if not any(k in first_purpose for k in ("冲突", "钩子", "对抗", "质问", "反驳")):
        warnings.append("第1镜 purpose 未见冲突标记（请人工确认开场强度）")

    data["shots"] = shots
    data["shots_count"] = len(shots)
    data["warnings"] = warnings
    data.setdefault("total_duration", sum(s.get("duration", 3) for s in shots))
    return data


def process_job(uid: str) -> dict:
    """处理单个任务的分镜"""
    from lib.state import get_job
    job = get_job(uid)
    if not job:
        raise ValueError(f"任务不存在: {uid}")
    if not job.get("script"):
        raise ValueError(f"任务 {uid} 没有文案")

    trend_title = ""
    if job.get("trend_id"):
        with connect() as conn:
            row = conn.execute("SELECT title FROM trends WHERE id = ?",
                               (job["trend_id"],)).fetchone()
            if row:
                trend_title = row["title"]

    print(f"  🎬 分镜: {uid}（{job.get('script_word_count', '?')}字）", flush=True)
    storyboard = split_script(job["script"], trend_title)

    update_job(uid, status="storyboard",
               storyboard=json.dumps(storyboard, ensure_ascii=False))
    print(f"      ✓ {storyboard['shots_count']} 镜 / {storyboard['total_duration']}秒 / "
          f"开场: {storyboard.get('opening_hook', '')[:30]}", flush=True)
    for shot in storyboard["shots"]:
        ref = f"[{shot['product_ref']}]" if shot.get("product_ref") else ""
        print(f"        {shot['seq']}. {shot['duration']}s {shot.get('shot_size', '')} "
              f"{shot.get('speaker', '')} {ref} {shot.get('narration', '')[:24]}", flush=True)
    for w in storyboard.get("warnings", []):
        print(f"        ⚠ {w}", flush=True)
    return storyboard


def run(top: int = 3, uid: str = None) -> dict:
    """批量分镜"""
    if uid:
        uids = [uid]
    else:
        jobs = [j for j in list_jobs("copy", limit=top * 2) if j.get("script")]
        uids = [j["uid"] for j in jobs[:top]]

    if not uids:
        print("✓ 没有待分镜的任务（先跑 s2_copy/gen_script.py）", flush=True)
        return {"processed": 0}

    print(f"🎬 专业分镜 {len(uids)} 个任务", flush=True)
    processed = 0

    for u in uids:
        try:
            process_job(u)
            processed += 1
        except Exception as e:
            print(f"      ✗ {u} 失败: {str(e)[:80]}", flush=True)
        time.sleep(0.5)

    print(f"\n✓ 分镜完成 {processed}/{len(uids)}", flush=True)
    return {"processed": processed}


def main() -> int:
    parser = argparse.ArgumentParser(description="智能分镜 v3（专业版）")
    parser.add_argument("--uid", help="指定任务UID")
    parser.add_argument("--top", type=int, default=3, help="批量数量")
    args = parser.parse_args()

    result = run(top=args.top, uid=args.uid)
    return 0 if result["processed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
