"""中文归一化工具：whisper 转写有时输出**繁体**，比对前必须繁转简

背景（2026-09-26 复刻片实测）：R2_haoyun_s2 逐字一致率算出 0.775、s5 算出 0.764，
看着像漏句，实际是转写输出繁体（十萬塊呢/顧客免單/還能抽一次獎/蘋果十八一台/躲開/運氣）
而期望台词是简体 → 字符比对全不匹配。加繁转简后两句都还原成 100% 命中。

用法：
    from lib.zh_norm import to_simplified
    ratio = difflib.SequenceMatcher(None, to_simplified(exp), to_simplified(got)).ratio()
"""
from __future__ import annotations

_CC = None


def to_simplified(text: str) -> str:
    """繁体 → 简体（依赖 opencc-python-reimplemented；缺包时原样返回，只影响分数不影响流程）"""
    global _CC
    if not text:
        return text
    if _CC is None:
        try:
            from opencc import OpenCC
            _CC = OpenCC("t2s")
        except Exception:
            _CC = False
    if _CC is False:
        return text
    try:
        return _CC.convert(text)
    except Exception:
        return text


def normalize_cn(text: str) -> str:
    """繁转简 + 去掉所有非中文数字字符（比对用）"""
    import re
    return re.sub(r"[^\u4e00-\u9fff0-9a-zA-Z]", "", to_simplified(text))
