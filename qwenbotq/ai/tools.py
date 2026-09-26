# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from collections.abc import Sequence, Mapping
from typing import Any

from config.ai import AgentLike

from .. import config
from ..database import Agent


async def get_sysprompt(id: str) -> Agent | AgentLike | None:
    "获取系统提示词"

    assert config.ai

    if id == "DEFAULT":
        return config.ai.default_prompts.default.model_copy()
    if id == "UNSAFE":
        return (
            config.ai.default_prompts.unsafe or config.ai.default_prompts.default
        ).model_copy(update={"unsafe": True})

    agent = await Agent.get(id)
    if agent:
        return agent
    return None


def content_to_text(content: Any) -> str:
    "把 OpenAI content（str 或 vision 内容数组）序列化为纯文本"
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    if url:
                        parts.append(f"[图片:{url}]")
        return "\n".join(parts)
    return str(content)


def tokenize(messages: Sequence[Mapping[str, Any]]) -> int:
    return sum(len(content_to_text(_["content"])) + 4 for _ in messages)


def blocked_by_unsafe(agent: Agent | AgentLike, session_id: str) -> bool:
    "unsafe 智能体仅限私聊会话（u{...}）使用，群聊会话返回 True"
    return bool(getattr(agent, "unsafe", False)) and session_id.startswith("g")
