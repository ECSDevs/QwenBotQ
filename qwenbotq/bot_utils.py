# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


"""
供主体使用的Bot实用函数
"""

import asyncio
from typing import Annotated, Any
from collections.abc import Callable, Awaitable

from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    Message,
    GroupMessageEvent,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.event import Event
from nonebot.adapters.onebot.v11.bot import send as ob_send

from . import config
from .database import User


async def get_user(_id: str):
    "获取用户"
    user = await User.get(_id)
    if not user:
        user = User(id=_id)
        await user.insert()
    return user


def require(
    cost_coins: int = 0,
    only_check: bool = False,
    superuser: bool = False,
) -> User:
    "用于获取发送用户的权限函数，可指定最小权限等级以及消耗积分数量"

    async def _require(event: MessageEvent, matcher: Matcher, bot: Bot):
        user = await get_user(event.get_user_id())

        if superuser and not user.id in config.supermgr_ids:
            await matcher.finish("\n您没有权限使用此功能！", at_sender=at_sender(event))

        if cost_coins:
            if user.coins < cost_coins:
                await matcher.finish(
                    f"\n您的积分不足，至少需要{cost_coins}。",
                    at_sender=at_sender(event),
                )
            if not only_check:
                await user.inc({User.coins: -cost_coins})
                await matcher.send(
                    f"\n您已被扣除所需的{cost_coins}点积分！",
                    at_sender=at_sender(event),
                )
                await asyncio.sleep(1)
        return user

    return Depends(_require, validate=True)


def reply_segment(id: int) -> Message:
    return Message(MessageSegment.reply(id))


def at_sender(event: MessageEvent) -> bool:
    "私聊不进行 @，仅在群聊中 @ 发送者"
    return event.message_type != "private"


def _strip_leading_newline(
    message: str | Message | MessageSegment,
) -> str | Message | MessageSegment:
    "移除消息开头的空行（没有 @ 垫底时，开头的 \\n 会显示为多余空行）"
    if isinstance(message, str):
        return message.lstrip("\n")
    if isinstance(message, MessageSegment):
        if message.type == "text":
            return MessageSegment.text(message.data.get("text", "").lstrip("\n"))
        return message
    for i, seg in enumerate(message):
        if seg.type == "text":
            text = seg.data.get("text", "")
            stripped = text.lstrip("\n")
            if stripped != text:
                if stripped:
                    seg.data["text"] = stripped
                else:
                    del message[i]
            break
    return message


async def _send(
    bot: Bot,
    event: Event,
    message: str | Message | MessageSegment,
    at_sender: bool = False,
    reply_message: bool = False,
    **params: Any,
) -> Any:
    "适配器发送钩子：有 @ 才带 \\n，无 @（私聊）去掉开头的 \\n"
    if not (at_sender and getattr(event, "message_type", None) != "private"):
        message = _strip_leading_newline(message)
    return await ob_send(
        bot, event, message, at_sender=at_sender, reply_message=reply_message, **params
    )


Bot.send_handler = _send  # pyright: ignore[reportAttributeAccessIssue]  # monkey-patch 适配器发送，统一处理 @ 与开头的 \n


def get_session_id(event: MessageEvent) -> str:
    "获取会话ID"
    if isinstance(event, GroupMessageEvent):
        return f"g{event.group_id}"
    return f"u{event.user_id}"


def is_group_admin_or_owner(event: MessageEvent) -> bool:
    "群聊中是否为群管/群主（私聊恒为 False）"
    if not isinstance(event, GroupMessageEvent):
        return False
    return bool(event.sender.role in ("owner", "admin"))


session_id_depends = Depends(get_session_id, validate=True)


async def get_nick(session_id: str, user_id: str, bot: Bot) -> str:
    "获取昵称"
    if session_id.startswith("g"):
        group_id = int(session_id[1:])
        try:
            member_info = await bot.get_group_member_info(
                group_id=group_id, user_id=int(user_id)
            )
            return member_info["card"] or member_info["nickname"]
        except:
            pass
    user_info = await bot.get_stranger_info(user_id=int(user_id))
    return user_info["nickname"]


nick_getter_type = Callable[[str], Awaitable[str]]


def nick_getter() -> nick_getter_type:
    async def _nick_getter(
        session_id: Annotated[str, session_id_depends],
        bot: Bot,
    ) -> nick_getter_type:
        async def _get_nick(user_id: str) -> str:
            return await get_nick(session_id, user_id, bot)

        return _get_nick

    return Depends(_nick_getter, validate=True)
