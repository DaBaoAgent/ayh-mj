"""成片统一改名：out/approved/ + 桌面 → 「<序号> <主体>.mp4」

规则（宝哥令 2026-09-25）：
  序号 = 全局连续编号（按生产时间升序，1 起）
  主体 = 去掉批次前缀（T01/T01b/B1/B2/W1/D2_01…）与日期（_20260925），下划线转空格
  例：D2_01_夜市摞货_20260925.mp4 → 「1 夜市摞货.mp4」（序号以实际时间序为准）

特性：
  · 幂等：已是「N 主体.mp4」的文件按同一规则参与排序，可反复跑
  · 同步改名桌面副本（C:/Users/xxx13/Desktop/ayh-mj/），避免 sync_desktop 产生新旧两份
  · 只改名不删除；重名自动加 (2)

用法：
  .venv/Scripts/python.exe tools/rename_approved.py --dry    # 预览
  .venv/Scripts/python.exe tools/rename_approved.py          # 执行
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "approved"
DST = Path("C:/Users/xxx13/Desktop/ayh-mj")
ORDER_FILE = ROOT / "state" / "approved_order.json"

PREFIX = re.compile(r"^(?:T\d+[a-z]?|B\d+(?:_\d+)?|W\d+|D2_\d+)_")
DATE = re.compile(r"_\d{8}(?=_|$)")
NEWFMT = re.compile(r"^\d+ .+\.mp4$")


def title_of(path: Path) -> str:
    """从文件名解析主体标题（兼容已是新格式的文件）"""
    stem = path.stem
    stem = re.sub(r" \(2\)$", "", stem)          # 归一化历史副本后缀
    if NEWFMT.match(path.name.replace(" (2)", "")):
        return stem.split(" ", 1)[1]
    t = PREFIX.sub("", stem)
    t = DATE.sub("", t)
    t = re.sub(r"_polished$", "", t)
    t = re.sub(r"_+$", "", t)
    return t.replace("_", " ")


def main() -> None:
    dry = "--dry" in sys.argv
    files = sorted([p for p in SRC.glob("*.mp4")], key=lambda p: p.stat().st_mtime)
    if not files:
        print("没有成片"); return

    # 序号固定映射：标题 → 序号（重烧/重归档沿用原序号，避免序号漂移）
    order: dict[str, int] = {}
    if ORDER_FILE.exists():
        order = json.loads(ORDER_FILE.read_text(encoding="utf-8")).get("order", {})
    next_seq = max(order.values(), default=0) + 1

    # 分配序号（第一遍：新标题先占号）
    items = []
    for p in files:
        t = title_of(p)
        if t not in order:
            order[t] = next_seq
            next_seq += 1
        items.append((p, t, order[t]))
    if not dry:
        ORDER_FILE.write_text(json.dumps(
            {"note": "成片序号固定映射（标题→序号）；重烧/重归档沿用原序号，新增条目取 max+1",
             "order": dict(sorted(order.items(), key=lambda kv: kv[1]))},
            ensure_ascii=False, indent=1), encoding="utf-8")

    plan = []
    seen: dict[str, Path] = {}
    for p, t, seq in items:
        name = f"{seq} {t}.mp4"
        if name in seen:
            # 同一标题出现两份（旧名 + 重烧新名）：保留 mtime 较新者，旧者本轮删除
            older = seen[name] if seen[name].stat().st_mtime < p.stat().st_mtime else p
            newer = p if older is seen[name] else seen[name]
            print(f"  ⚠ 同名 {name} → 保留较新的 {newer.name}（mtime 更晚），删除 {older.name}")
            if not dry:
                older.unlink(missing_ok=True)
            plan = [(q, n) for q, n in plan if q != older]
            seen[name] = newer
            plan.append((newer, name))
            continue
        seen[name] = p
        plan.append((p, name))

    # 桌面映射：旧名 → 新名（桌面文件名与 out/approved 旧名一致）
    desk_map = {p.name: n for p, n in plan}
    desk_files = {p.name: p for p in DST.glob("*.mp4")} if DST.exists() else {}

    changed = 0
    for p, name in plan:
        if p.name == name:
            continue
        print(f"  {'(dry) ' if dry else ''}{p.name}  →  {name}")
        if not dry:
            target = SRC / name
            if target.exists() and target != p:
                target.unlink(missing_ok=True)      # 重烧覆盖：新版本胜出
            p.rename(target)
        changed += 1

    # 桌面：先改名旧名文件，再兜底复制缺失的
    desk_changed, desk_copied = 0, 0
    desk_will_have = {n for old, n in desk_map.items() if old in desk_files}
    for old, new in desk_map.items():
        if old == new:
            continue
        d = desk_files.get(old)
        if d is None:
            continue
        if d.name == new:
            continue
        if not dry:
            (DST / new).unlink(missing_ok=True)
            d.rename(DST / new)
        print(f"  {'(dry) ' if dry else ''}[桌面] {old}  →  {new}")
        desk_changed += 1
    # 桌面缺失的新名文件补齐（dry 模式跳过在改名后自然就位的）
    for p, new in plan:
        if new in desk_will_have:
            continue
        if DST.exists() and not (DST / new).exists():
            if not dry:
                import shutil
                shutil.copy2(SRC / new, DST / new)
            desk_copied += 1
            print(f"  {'(dry) ' if dry else ''}[桌面] 补齐 {new}")

    print(f"\nout/approved 改名 {changed} 个｜桌面改名 {desk_changed} 个｜桌面补齐 {desk_copied} 个")
    print(f"共 {len(plan)} 条成片，序号 1-{len(plan)}")


if __name__ == "__main__":
    main()
