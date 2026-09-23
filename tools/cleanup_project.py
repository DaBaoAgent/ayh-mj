"""项目清理 — 保留验收成片，删除中间过程素材/脚本/未通过成片

保留：
  · out/approved/ 下两个验收成片（T04 已验收 + T01）
  · state/jobs.db（流水线任务库）/ console.json / casting_history.json
  · 全部流水线脚本（tools/ 中非一次性探测脚本）

删除：
  · out/ 下除 approved 外的一切（老成片/中间 shots/transcripts/检查图）
  · state/frames/（抽帧检查图）、storyboard_job_*.json（过程分镜）、workflows_*.json（探测产物）
  · tools/probe_workflows*.py（一次性探测脚本）、tools/archive/（旧版脚本归档）
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
APPROVED = OUT / "approved"
STATE = ROOT / "state"
TOOLS = ROOT / "tools"

# 验收成片清单：(job目录, 归档名, storyboard存档名)
APPROVE_LIST = [
    ("gen_job_20260923_203050_696002_0", "T04_路人疑惑三连_20260923.mp4", "storyboard_T04.json"),
    ("gen_job_20260923_211932_580932_0", "T01_母子换车_20260923.mp4", "storyboard_T01.json"),
    ("gen_job_20260923_214420_385094_0", "T02_魔性循环_20260923.mp4", "storyboard_T02.json"),
    ("gen_job_20260923_220754_942374_0", "T03_反差王者_20260923.mp4", "storyboard_T03.json"),
    ("gen_job_20260923_221422_559217_0", "T04b_拆车误会_20260923.mp4", "storyboard_T04b.json"),
    ("gen_job_20260923_223542_194042_0", "T03b_中秋赶集_20260923.mp4", "storyboard_T03b.json"),
    ("gen_job_20260923_224619_868328_0", "T04c_秋分静养_20260923.mp4", "storyboard_T04c.json"),
    ("gen_job_20260923_230005_851075_0", "T01b_旧物安全感_20260923.mp4", "storyboard_T01b.json"),
    ("gen_job_20260923_231804_807115_0", "B1_机场托运_欧美版_20260923.mp4", "storyboard_B1.json"),
    ("gen_job_20260923_234330_459411_0", "B2_地铁通勤_20260923.mp4", "storyboard_B2.json"),
    ("gen_job_20260923_235047_259507_0", "B3_暴雨突袭_20260923.mp4", "storyboard_B3.json"),
]


def main(dry: bool = False) -> None:
    print("=" * 60)
    print("清理预览" if dry else "开始清理")
    print("=" * 60)

    # 1. 归档验收成片（+ 分镜元数据）
    APPROVED.mkdir(exist_ok=True)
    for job, name, sb_name in APPROVE_LIST:
        src = OUT / job / "final_sub.mp4"
        dst = APPROVED / name
        if not src.exists():
            print(f"  ✗ 缺成片: {src}（跳过归档）")
        elif dst.exists():
            print(f"  ↻ 已归档: {name}")
        else:
            if not dry:
                shutil.copy2(src, dst)
            print(f"  ✓ 归档: {name} ({src.stat().st_size / 1024 / 1024:.1f}MB)")
        # 分镜元数据（state 文件名 = storyboard_<uid>.json，uid 无 gen_ 前缀）
        uid = job.removeprefix("gen_")
        sb_src = STATE / f"storyboard_{uid}.json"
        if sb_src.exists():
            sb_dst = APPROVED / sb_name
            if not dry:
                shutil.copy2(sb_src, sb_dst)
            print(f"  ✓ 归档: {sb_name}")

    # 2. 删除 out/ 下除 approved 外的一切
    if OUT.exists():
        for item in OUT.iterdir():
            if item.name == "approved":
                continue
            if not dry:
                shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink()
            print(f"  🗑 out/{item.name}")

    # 3. state 过程文件
    deletes_state = [STATE / "frames"]
    deletes_state += list(STATE.glob("storyboard_job_*.json"))
    deletes_state += [STATE / "workflows_meta.json", STATE / "workflows_matrix.json"]
    for p in deletes_state:
        if p.exists():
            if not dry:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()
            print(f"  🗑 state/{p.name}")

    # 4. 一次性脚本
    for p in [TOOLS / "probe_workflows.py", TOOLS / "probe_workflows_v2.py",
              TOOLS / "archive"]:
        if p.exists():
            if not dry:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()
            print(f"  🗑 tools/{p.name}")

    # 5. 清点
    print()
    print("=== 保留清单 ===")
    if APPROVED.exists():
        for f in sorted(APPROVED.iterdir()):
            print(f"  ✓ out/approved/{f.name} ({f.stat().st_size / 1024 / 1024:.1f}MB)")
    print("  ✓ state/jobs.db 等流水线状态")
    print("  ✓ tools/ 流水线脚本")


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
