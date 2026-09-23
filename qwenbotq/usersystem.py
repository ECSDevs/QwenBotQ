# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


"Core module of QwenBotQ"

from datetime import timedelta, date
from random import randint
from typing import Annotated
from collections.abc import Callable, Awaitable

from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import on_alconna, At, Match
from nonebot.adapters.onebot.v11 import Bot, MessageSegment, MessageEvent

from . import config
from .bot_utils import (
    require,
    get_user,
    get_nick,
    get_session_id,
    nick_getter,
    at_sender,
)
from .database import User, buy_vip
from .help import Help
from .utils import avatar

Help.append_help("""
【用户系统】
签到 — 每日签到领取积分
用户信息 [@用户] — 查看用户信息
转账给 @用户 <积分数量> — 转账积分
积分榜 — 查看积分排名前10的用户（群聊显示群内排名）
""")


user_info_cmd = Alconna("用户信息", Args["target?", At])
GetInformationMatcher = on_alconna(user_info_cmd, block=True, use_origin=True)


@GetInformationMatcher.handle()
async def get_information(
    user: Annotated[User, require()],
    target: Match[At],
    bot: Bot,
    event: MessageEvent,
):
    "用户信息"
    if target.available:
        user = await get_user(target.result.target)
    user_nick = await get_nick(get_session_id(event), user.id, bot)
    if user.binded and user.binded.expire > date.today():
        cp = await get_user(user.binded.id)
        cp_info = (
            await get_nick(get_session_id(event), cp.id, bot),
            cp.id,
            user.binded.expire.strftime("%Y/%m/%d"),
        )
    else:
        cp_info = None

    await GetInformationMatcher.finish(
        f"\n{user.id}的用户信息：\n"
        f"昵称：{user_nick}\n"
        f"积分：{user.coins}\n\t"
        + (
            f"已签到\n\t失效日期：{user.sign_expire.strftime('%Y/%m/%d')}\n"
            if user.sign_expire > date.today()
            else "未签到\n"
        )
        + f"使用模型：{user.model}\n"
        "头像："
        + MessageSegment.image(avatar(user.id))
        + "本日老公："
        + (
            f"{cp_info[0]} ({cp_info[1]})\n" f"\t失效日期：{cp_info[2]}"
            if cp_info
            else "未绑定"
        ),
        at_sender=at_sender(event),
    )


SignMatcher = on_alconna(Alconna("签到"), block=True)


@SignMatcher.handle()
async def sign(user: Annotated[User, require()], event: MessageEvent):
    "每日签到"
    if user.sign_expire <= date.today():
        coins = randint(
            config.price.daily_sign_min_coins, config.price.daily_sign_max_coins
        )
        await user.set({User.sign_expire: date.today() + timedelta(1)})
        await user.inc({User.coins: coins})
        await SignMatcher.finish(
            f"\n签到成功！本次获得{coins}个积分\n"
            f'过期时间：{user.sign_expire.strftime("%Y/%m/%d")}',
            at_sender=at_sender(event),
        )
    await SignMatcher.finish(
        "\n本日已签到！请勿重复签到！\n"
        "最近一次签到的过期时间：\n" + user.sign_expire.strftime("%Y/%m/%d"),
        at_sender=at_sender(event),
    )


transfer_cmd = Alconna("转账给", Args["target?", At]["amount?", int])
TransferMatcher = on_alconna(transfer_cmd, block=True, use_origin=True)


@TransferMatcher.handle()
async def transfer(
    user: Annotated[User, require()],
    target: Match[At],
    amount: Match[int],
    bot: Bot,
    nick_getter: Annotated[Callable[[str], Awaitable[str]], nick_getter()],
    event: MessageEvent,
):
    "转账积分"
    if not target.available or not amount.available:
        await TransferMatcher.finish(
            "\n用法：转账给 @目标用户 <积分数量>",
            at_sender=at_sender(event),
        )
    target_user = await get_user(target.result.target)
    if amount.result < 0:
        await TransferMatcher.finish(
            "\n不允许反向转账积分！", at_sender=at_sender(event)
        )
    if user.id == target_user.id:
        await TransferMatcher.finish("\n不允许给自己转账！", at_sender=at_sender(event))
    if user.coins >= amount.result:
        await target_user.inc({User.coins: amount.result})
        await user.inc({User.coins: -amount.result})
        mention_nick = await nick_getter(target_user.id)
        await TransferMatcher.finish(
            "\n成功给\n"
            f"{mention_nick} ({target_user.id})\n"
            f"转账了{amount.result}积分！",
            at_sender=at_sender(event),
        )
    await TransferMatcher.finish(
        f"\n您的积分余额不足以转账{amount.result}积分！", at_sender=at_sender(event)
    )


async def _fetch_group_members(group_id: int, bot: Bot) -> list[dict] | None:
    "获取群成员列表（失败返回 None）"
    try:
        return await bot.get_group_member_list(  # type: ignore
            group_id=group_id
        )
    except Exception:
        return None


async def _rank_nick_map(
    session_id: str,
    user_ids: list[str],
    bot: Bot,
    members: list[dict] | None = None,
) -> dict[str, str]:
    "批量获取榜单用户昵称（群聊优先使用已拉取的群成员，其余回退逐个查询）"
    nick_map: dict[str, str] = {}
    if members:
        nick_map = {
            str(m["user_id"]): m["card"] or m["nickname"]
            for m in members
            if str(m["user_id"]) in user_ids
        }
    for uid in user_ids:
        if uid not in nick_map:
            nick_map[uid] = await get_nick(session_id, uid, bot)
    return nick_map


CoinsRankMatcher = on_alconna(Alconna("积分榜"), block=True)


@CoinsRankMatcher.handle()
async def coins_rank(
    user: Annotated[User, require()],
    bot: Bot,
    event: MessageEvent,
):
    "积分榜"

    session_id = get_session_id(event)
    # 群聊时限定为群内成员计算排名（拉取失败则回退到全站）
    members: list[dict] | None = None
    member_ids: set[str] | None = None
    if session_id.startswith("g"):
        members = await _fetch_group_members(int(session_id[1:]), bot)
        if members is not None:
            member_ids = {str(m["user_id"]) for m in members}

    scope: dict | None = None
    if member_ids is not None:
        scope = {"id": {"$in": list(member_ids)}}

    top_users = await User.find(scope, sort=["-coins"], limit=10).to_list()
    ids = [u.id for u in top_users]

    real_rank = None
    if user.id not in ids:
        # 不在榜单内：用自己替换第10名，并记录实际排行（群聊内为群内排行）
        rank_filter: dict = {"coins": {"$gt": user.coins}}
        if member_ids is not None:
            rank_filter["id"] = {"$in": list(member_ids)}
        real_rank = (await User.find(rank_filter).count()) + 1
        top_users[-1] = user
        ids[-1] = user.id

    nick_map = await _rank_nick_map(session_id, ids, bot, members)

    lines = []
    for rank, u in enumerate(top_users, 1):
        mark = " [我]" if u.id == user.id else ""
        show_rank = real_rank if mark else rank
        lines.append(f"{show_rank}. {nick_map[u.id]}{mark} — {u.coins}积分")

    title = "群内积分榜 Top10" if member_ids is not None else "积分榜 Top10"
    msg = f"\n【{title}】\n" + "\n".join(lines)
    await CoinsRankMatcher.finish(msg, at_sender=at_sender(event))


set_vip_cmd = Alconna("!renewvip", Args["session_id?", str]["days?", int])
SetVipMatcher = on_alconna(set_vip_cmd, block=True)


@SetVipMatcher.handle()
async def set_vip(
    user: Annotated[User, require(superuser=True)],
    session_id: Match[str],
    days: Match[int],
    event: MessageEvent,
):
    "设置 AI VIP"

    if not session_id.available or not days.available:
        await SetVipMatcher.finish(
            "\n用法：!renewvip <会话ID> <天数>",
            at_sender=at_sender(event),
        )

    if days.result < 0:
        await SetVipMatcher.finish(
            "\n不允许设置负数的 VIP 续期！", at_sender=at_sender(event)
        )

    vip = await buy_vip(session_id.result, days.result)

    await SetVipMatcher.finish(
        f"\n已为用户 {session_id.result} 续期 VIP 到 {vip.expire.strftime('%Y/%m/%d')}",
        at_sender=at_sender(event),
    )
