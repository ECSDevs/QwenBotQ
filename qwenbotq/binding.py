# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


"绑定相关"

from random import choice, randint
from datetime import date
from typing import Annotated

from nonebot_plugin_alconna import on_alconna
from arclet.alconna import Alconna
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Bot,
    MessageSegment,
)

from .database import User, apply_bind, get_biggest_coins
from .bot_utils import (
    require,
    get_user,
    get_nick,
    get_session_id,
    at_sender,
)
from .help import Help
from .utils import avatar

Help.append_help("""
【绑定系统】
今日老公 — 随机绑定今日老公
""")


WifeMatcher = on_alconna(Alconna("今日老公"), block=True)


@WifeMatcher.handle()
async def wife(user: Annotated[User, require()], event: GroupMessageEvent, bot: Bot):
    "群友老公"
    if user.binded and user.binded.expire > date.today():
        cp_user = await get_user(user.binded.id)
        expire = user.binded.expire
        if not (cp_user.binded and cp_user.binded.id == user.id):
            await WifeMatcher.finish(
                "\n您的绑定数据有误，请联系管理员！", at_sender=at_sender(event)
            )
    else:
        members = await bot.get_group_member_list(group_id=event.group_id)
        biggest = await get_biggest_coins()
        while True:
            x = choice(members)
            cp_user = await get_user(str(x["user_id"]))
            power = randint(0, biggest)
            if (
                (cp_user.id == user.id)
                or (cp_user.binded and cp_user.binded.expire > date.today())
                or (cp_user.coins > power)
            ):
                members.remove(x)
                power += 0.2
                continue
            break
        expire = await apply_bind(user, cp_user)
    cp_nick = await get_nick(get_session_id(event), cp_user.id, bot)
    await WifeMatcher.finish(
        "\n你今天的老公是："
        + MessageSegment.image(avatar(cp_user.id))
        + f"{cp_nick} ({cp_user.id})\n"
        f'过期时间：{expire.strftime("%Y/%m/%d")}\n'
        "\n今日关系已绑定，要好好珍惜哦！",
        at_sender=at_sender(event),
    )
