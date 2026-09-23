"""DeepSeek API 接口"""
import os
import json
import httpx
from typing import Generator

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

def chat(
    messages: list[dict],
    model: str = "deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    stream: bool = False,
) -> str | Generator:
    """调用 DeepSeek Chat API"""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY 未设置")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    
    with httpx.Client(timeout=120) as client:
        if stream:
            with client.stream("POST", f"{DEEPSEEK_BASE_URL}/chat/completions",
                               headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
        else:
            resp = client.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                               headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

def generate_script(topic: str, product_info: dict, style: str = "轻快科普风") -> str:
    """生成软广脚本"""
    system_prompt = f"""你是一个抖音爆款文案专家，擅长写电动轮椅软广视频脚本。

产品信息：
- 品牌：{product_info.get('brand', '爱优护')}
- 产品：{product_info.get('name', '轻便侠218电动轮椅')}
- 卖点：{', '.join(product_info.get('keywords', ['轻便', '折叠', '安全']))}

风格要求：{style}
- 口语化，像朋友聊天
- 自然植入产品，不硬广
- 适合10-20秒短视频
- 字数控制在150-300字
- 分镜提示用【】标注"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请根据这个热点话题写一个软广脚本：\n{topic}"},
    ]
    
    return chat(messages, temperature=0.8)

def analyze_trend(title: str, likes: int, comments: int) -> dict:
    """分析热点是否适合植入"""
    messages = [
        {"role": "system", "content": """你是一个内容策略专家。判断这个热点视频是否适合植入电动轮椅广告。

返回JSON格式：
{
  "match": true/false,
  "score": 0-100,
  "reason": "原因",
  "angle": "植入角度建议"
}

适合植入的场景：
1. 老年人出行、旅游
2. 残障人士生活日常
3. 家庭关爱、送礼场景
4. 产品测评、开箱
5. 出行痛点吐槽

不适合植入的场景：
1. 医疗康复（容易违规）
2. 残障权益倡导（主体人群不同）
3. 竞品硬广
4. 猎奇搞笑（调性不符）"""},
        {"role": "user", "content": f"标题：{title}\n点赞：{likes}\n评论：{comments}"},
    ]
    
    result = chat(messages, temperature=0.3)
    try:
        return json.loads(result)
    except:
        return {"match": False, "score": 0, "reason": "解析失败", "angle": ""}
