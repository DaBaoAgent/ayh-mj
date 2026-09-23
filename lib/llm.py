"""DeepSeek API 接口

模型名（2026-09 实测）：本账号 DeepSeek API 只认 `deepseek-flash` / `deepseek-v4-pro`
密钥来源优先级：环境变量 → hermes .env 文件
"""
import json
import os
from pathlib import Path

import httpx

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"


def _load_key() -> str:
    """加载 API Key：统一key文件优先 → 环境变量 → hermes .env（2026-09-23 文件为权威源）"""
    try:
        from lib.keyfile import load_from_keyfile
        k = load_from_keyfile("deepseek")
        if k:
            return k
    except Exception:
        pass

    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key

    env_file = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


DEEPSEEK_API_KEY = _load_key()


def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    stream: bool = False,
) -> str:
    """调用 DeepSeek Chat API"""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未设置（环境变量或 hermes .env 都没有）")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    # 直连 api.deepseek.com（trust_env=False 真正禁用环境变量代理——此前 proxy=None
    # 仍会走 HTTPS_PROXY，代理抖动时返回空响应导致"无法解析 JSON"）
    with httpx.Client(timeout=120, trust_env=False) as client:
        resp = client.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                           headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON（去 markdown 包裹 + 截断修复）"""
    text = text.strip()
    # 去 markdown 代码块
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    text = text.strip()
    # 直解
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 找最外层 {...}
    start = text.find("{")
    end = text.rfind("}")
    candidate = text[start:end + 1] if (start >= 0 and end > start) else text[start:]

    def _repair(s: str) -> str:
        """修复常见截断：悬空 key / 未闭合字符串 / 未闭合括号（栈序闭合）"""
        import re as _re
        s = s.rstrip()
        # 悬空 key（`"key":` 结尾）→ 删掉整个 key 段（含前面逗号）
        s = _re.sub(r',?\s*"[^"]*"\s*:\s*$', '', s)
        s = s.rstrip()
        # 扫描字符串状态与括号栈
        stack: list[str] = []
        in_str = False
        escaped = False
        for ch in s:
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch in "[{":
                    stack.append(ch)
                elif ch in "]}" and stack:
                    stack.pop()
        # 未闭合字符串 → 补引号
        if in_str:
            s += '"'
        # 悬空逗号/冒号 → 去掉
        s = s.rstrip()
        while s.endswith((",", ":")):
            s = s[:-1].rstrip()
        # 括号栈逆序闭合
        for op in reversed(stack):
            s += "]" if op == "[" else "}"
        return s

    for attempt in (candidate, _repair(candidate)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"无法解析 JSON（前80字: {text[:80]}）")


def chat_json(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
    max_tokens: int = 3000,
    retries: int = 2,
) -> dict:
    """调用 API 并要求返回 JSON（截断自动重试 + 容错解析）"""
    last_err = None
    for attempt in range(retries + 1):
        mt = max_tokens * (2 ** attempt)  # 每次翻倍
        text = chat(messages, model=model, temperature=temperature, max_tokens=mt)
        try:
            return _extract_json(text)
        except ValueError as e:
            last_err = e
            if attempt < retries:
                continue
    raise ValueError(f"chat_json 失败（{retries + 1} 次尝试）: {last_err}")


def generate_script(topic: str, product_info: dict, style: str = "轻快科普风") -> str:
    """生成软广脚本（简版，完整版见 s2_copy/gen_script.py）"""
    system_prompt = f"""你是一个抖音爆款文案专家，擅长写电动轮椅软广视频脚本。

产品信息：
- 品牌：{product_info.get('brand', '爱优护')}
- 产品：{product_info.get('name', '轻便侠218电动轮椅')}
- 卖点：{', '.join(product_info.get('keywords', ['轻便', '折叠', '安全']))}

风格要求：{style}
- 口语化，像朋友聊天
- 自然植入产品，不硬广
- 适合10-20秒短视频
- 字数控制在150-300字"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请根据这个热点话题写一个软广脚本：\n{topic}"},
    ]

    return chat(messages, temperature=0.8)
