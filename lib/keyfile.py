"""统一 API key 文件解析

文件：D:/BaiduSyncdisk/2 @AI编程/Api Key/爱优护api.txt
格式（中文标签行 + 下一行裸 key）：
    autodl api：
    <key>
    火山方舟：
    <key>
    deepseek：
    <key>
"""
from pathlib import Path

KEY_FILE = Path("D:/BaiduSyncdisk/2 @AI编程/Api Key/爱优护api.txt")


def load_from_keyfile(label: str) -> str:
    """按标签读 key（'autodl' / '火山' / 'deepseek'）；找不到返回空串"""
    if not KEY_FILE.exists():
        return ""
    try:
        lines = [ln.strip() for ln in KEY_FILE.read_text(encoding="utf-8").splitlines()]
    except Exception:
        return ""
    for i, ln in enumerate(lines):
        if label in ln:
            for j in range(i + 1, len(lines)):
                if lines[j]:
                    return lines[j]
    return ""


if __name__ == "__main__":
    for label in ("autodl", "火山", "deepseek"):
        k = load_from_keyfile(label)
        print(f"{label}: {'✓ ' + k[:8] + '...(' + str(len(k)) + '字符)' if k else '✗ 未找到'}")
