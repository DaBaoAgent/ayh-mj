"""高风险镜头 5s 预筛（通用版：任意 one-take spec 都能用）

为什么：15s 正式片 = ¥0.9 + 10-20 分钟；同内容 5s = ¥0.3 + 2-4 分钟。
对「没拍过的画面类型」（新道具细节、多人同框口型、特殊运镜、品牌字）先花 1/3 的钱和时间验证，
过了再跑 15s 正式片 —— 把「事后重跑整条」变成「事前筛掉废方案」。

原理：从 spec 的 prompt 里按 `[Shot N, a to b seconds]` 切出指定镜，把时间轴改成 0-5s，其余原样保留
（CAST/硬约束/收尾声明都跟着，保证快测与正式片同口径）。

用法：
  # ① 生成 5s 预筛 spec（抽第 3 镜）
  .venv/Scripts/python.exe tools/prescreen.py build state/onetake_prompt_job_<uid>.json --shot 3
  # ② 提交并等下载（可多条）
  .venv/Scripts/python.exe tools/prescreen.py run <uid>_shot3 [<uid>_shot1 ...] --jobs 3
  # ③ 抽帧 + 视觉判读
  .venv/Scripts/python.exe tools/prescreen.py judge <uid>_shot3 --ask "转盘指针是否停在正上方那格？"

产物：state/prescreen_job_<uid>_shotN.json → out/gen_<uid>_shotN/onetake.mp4 → 判读图与结论落 references/prescreen/
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv/Scripts/python.exe")
GEN = str(ROOT / "s4_generate/gen_one_take.py")
OUTROOT = ROOT / "references/prescreen"
SHOT_RE = re.compile(r"\[Shot (\d+), ([0-9.]+) to ([0-9.]+) seconds\]")


def split_prompt(prompt: str) -> tuple[str, list[str], str]:
    """拆成 (前导段, [每镜文本], 收尾段)。收尾段=最后一镜之后的内容（soundscape/Hard constraints）"""
    marks = list(SHOT_RE.finditer(prompt))
    if not marks:
        raise SystemExit("✗ 提示词里找不到 `[Shot N, a to b seconds]` 结构，无法抽镜")
    pre = prompt[:marks[0].start()]
    shots = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(prompt)
        shots.append(prompt[m.start():end])
    tail = ""
    if len(marks) >= 1:
        last = shots[-1]
        cut = last.find("\n\n")
        while cut != -1:
            nxt = last[cut + 2:cut + 22].lstrip()
            if not nxt.startswith("[Shot"):
                tail = last[cut:].strip()
                shots[-1] = last[:cut].strip()
                break
            cut = last.find("\n\n", cut + 2)
    return pre, shots, tail


def build(spec_path: Path, shot_no: int, seconds: int = 5) -> Path:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    pre, shots, tail = split_prompt(spec["prompt"])
    if not 1 <= shot_no <= len(shots):
        raise SystemExit(f"✗ 该片只有 {len(shots)} 镜，取不到第 {shot_no} 镜")
    one = SHOT_RE.sub(lambda m: f"[Shot 1, 0 to {seconds} seconds]", shots[shot_no - 1], count=1)
    one = one.replace("Hard cut.", "").replace("Hard cut", "").strip()
    new = {
        **spec,
        "job_uid": f"{spec['job_uid']}_shot{shot_no}",
        "duration": seconds,
        "prompt": "\n\n".join([pre, one, tail] if tail else [pre, one]),
        "prescreen_of": spec["job_uid"],
        "prescreen_shot": shot_no,
    }
    p = ROOT / f"state/prescreen_job_{new['job_uid']}.json"
    p.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ 预筛 spec：{p.name}（{spec['job_uid']} 第 {shot_no} 镜 → {seconds}s，{len(new['ref_images'])} 图 "
          f"{len(new.get('ref_audios') or [])} 音，预估 ¥{0.3:.1f}）")
    return p


def run(uids: list[str], jobs: int = 3) -> None:
    queue = [u for u in uids if not (ROOT / f"out/gen_{u}/onetake.mp4").exists()]
    if not queue:
        print("没有待跑预筛")
        return
    print(f"▶ 预筛排队 {len(queue)} 条（并发 {jobs}）：{', '.join(queue)}")
    running: dict[str, tuple[subprocess.Popen, float]] = {}
    done: list[tuple[str, bool, float]] = []
    t0 = time.time()
    while queue or running:
        while queue and len(running) < jobs:
            uid = queue.pop(0)
            d = ROOT / f"out/gen_{uid}"
            d.mkdir(parents=True, exist_ok=True)
            log = open(d / "gen.log", "w", encoding="utf-8")  # noqa: SIM115
            p = subprocess.Popen([PY, GEN, str(ROOT / f"state/prescreen_job_{uid}.json")],
                                 stdout=log, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace")
            running[uid] = (p, time.time())
            print(f"  ⏬ {uid} 提交（{len(running)}/{jobs} 在跑）", flush=True)
        time.sleep(10)
        for uid in list(running):
            p, started = running[uid]
            if p.poll() is None:
                continue
            ok = (ROOT / f"out/gen_{uid}/onetake.mp4").exists()
            done.append((uid, ok, time.time() - started))
            print(f"  {'✅' if ok else '❌'} {uid} {done[-1][2] / 60:.1f} 分钟", flush=True)
            running.pop(uid)
    print(f"\n=== 预筛汇总（{(time.time() - t0) / 60:.1f} 分钟）===")
    for uid, ok, el in done:
        print(f"  {'✅' if ok else '❌'} {uid}  {el / 60:.1f} 分钟")


def judge(uids: list[str], ask: str | None) -> None:
    OUTROOT.mkdir(parents=True, exist_ok=True)
    q = ask or "逐项回答：① 画面里有几个人；② 说话的人是谁、嘴在动吗；③ 画面里最关键的那个道具/细节状态如何；④ 有没有畸形（多手多脚、面孔扭曲）。每条一句话。"
    for uid in uids:
        vid = ROOT / f"out/gen_{uid}/onetake.mp4"
        if not vid.exists():
            print(f"[{uid}] 缺片")
            continue
        card = OUTROOT / f"{uid}_card.png"
        ts = ",".join(f"{0.3 + 0.5 * i:.1f}" for i in range(10))
        subprocess.run([PY, str(ROOT / "tools/frames_card.py"), str(vid), "--ts", ts, "--out", str(card)],
                       capture_output=True, text=True, encoding="utf-8")
        md = OUTROOT / f"{uid}.md"
        subprocess.run([PY, str(ROOT / "scripts/ask_img_full.py"), str(card), q, "--out", str(md)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        txt = " ".join(md.read_text(encoding="utf-8").split())[:600] if md.exists() else "(判读失败)"
        print(f"\n[{uid}]\n  {txt}")


def main() -> None:
    ap = argparse.ArgumentParser(description="5s 高风险镜头预筛")
    ap.add_argument("cmd", choices=["build", "run", "judge"])
    ap.add_argument("target", nargs="*", help="build: spec 路径；run/judge: <uid>_shotN")
    ap.add_argument("--shot", type=int, default=1, help="抽第几镜（1 起）")
    ap.add_argument("--seconds", type=int, default=5)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--ask", default=None, help="judge 的判读问题（按你的验收点写）")
    a = ap.parse_args()
    if a.cmd == "build":
        if not a.target:
            raise SystemExit("用法：prescreen.py build <spec.json> --shot 3")
        build(Path(a.target[0]), a.shot, a.seconds)
    elif a.cmd == "run":
        run(a.target, a.jobs)
    else:
        judge(a.target, a.ask)


if __name__ == "__main__":
    main()
