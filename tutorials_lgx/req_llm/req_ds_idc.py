"""东方财富 DeepSeek 大模型调用示例（OpenAI 兼容接口）。

使用前请先安装依赖：pip install requests
并把 API Key / URL 填写到 config.json 文件中（该文件已被 .gitignore 忽略）。
"""

import json
import os

import requests

# 配置文件路径（与脚本同目录，已加入 .gitignore）
_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_providers(path: str = _CONFIG_FILE) -> list[dict]:
    """读取配置文件，返回所有可用的服务配置（支持多个 key / url）。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_provider(name: str = "") -> dict:
    """按名称获取某个服务配置，不传名称时默认取第一个。"""
    providers = load_providers()
    if name:
        for provider in providers:
            if provider.get("name") == name:
                return provider
        raise ValueError(f"未找到名为 {name!r} 的服务配置")
    if not providers:
        raise ValueError("config.json 中没有可用的服务配置")
    return providers[0]


_provider = get_provider('eastmoney_idc')

BASE_URL = _provider["url"]
MODEL = _provider.get("model", "DeepSeek-V4.1-Flash-1017")
API_KEY = _provider["key"]


def chat(prompt: str) -> str:
    """发送一条用户消息，返回模型回复文本。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.0,
    }

    headers = {
        "Authorization": API_KEY,
        "Content-Type": "application/json",
    }

    resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"]


if __name__ == "__main__":
    answer = chat("你好，请用一句话介绍一下你自己。")
    print(answer)