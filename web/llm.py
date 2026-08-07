"""LLM 后端：OpenAI 兼容接口（DeepSeek）。

保留模块级 _S / _client / _PROVIDER：multiagent-eval 评测框架用上下文管理器
patch 这三个全局来切换后端（见 multiagent-eval/src/pipeline.py）。
"""
from __future__ import annotations
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from config import llm_settings

log = logging.getLogger("council.llm")

_S = llm_settings()
_PROVIDER = "deepseek"  # OpenAI 兼容后端标识（评测框架运行时切换时也写这个值）
_client = AsyncOpenAI(api_key=_S["api_key"], base_url=_S["base_url"])


def configured() -> bool:
    return bool(_S["api_key"])


def model_label() -> str:
    return _S["model"]


async def stream(messages: list[dict], temperature: float | None = None, model: str | None = None) -> AsyncIterator[str]:
    resp = await _client.chat.completions.create(
        model=model or _S["model"], messages=messages,
        temperature=_S["temperature"] if temperature is None else temperature,
        max_tokens=_S["max_tokens"], stream=True,
    )
    async for chunk in resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def complete(messages: list[dict], temperature: float | None = None, model: str | None = None) -> str:
    resp = await _client.chat.completions.create(
        model=model or _S["model"], messages=messages,
        temperature=0.3 if temperature is None else temperature,
        max_tokens=_S["max_tokens"],
    )
    return resp.choices[0].message.content or ""
