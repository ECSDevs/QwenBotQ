# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"21点模块"

import asyncio
import time
from dataclasses import dataclass, field
from typing import Annotated

from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import on_alconna, Match
from nonebot import get_bot, get_driver
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
)
from nonebot_plugin_apscheduler import scheduler

from . import config
from .database import User
from .bot_utils import require, at_sender, get_session_id, get_nick
from .help import Help
from .blackjack_logic import (
    BlackjackPlayer,
    new_deck,
    draw_card,
    hand_value,
    is_blackjack,
    play_dealer,
    compute_result,
    all_finished,
)

Help.append_help("""
【21点】
开始游戏 21点 <押注积分> — 创建21点对局大厅并押注
加入游戏 <押注积分> — 加入当前大厅
结束匹配 — 开始正式对局（发牌）
要牌 / 停牌 — 要牌 / 停牌
加倍 — 仅初始2张牌可用，双倍押注并补一张后强制停牌
取消对局 — 大厅期间取消并全额退款
21点规则：A计1或11，JQK计10，超过21点爆牌；庄家补牌至≥17；黑杰克（起手2张21）赔1.5倍
""")


@dataclass
class BlackjackRoom:
    "21点房间"

    session_id: str
    host_id: str
    players: list[BlackjackPlayer] = field(default_factory=list)
    dealer_hand: list[str] = field(default_factory=list)
    deck: list[str] = field(default_factory=list)
    phase: str = "lobby"  # "lobby" 大厅 / "playing" 对局中
    created_at: float = 0.0
    last_action: float = 0.0


_rooms: dict[str, BlackjackRoom] = {}
_game_locks: dict[str, asyncio.Lock] = {}


def _room_lock(session_id: str) -> asyncio.Lock:
    lock = _game_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _game_locks[session_id] = lock
    return lock


def _card_text(hand: list[str]) -> str:
    "手牌文本：以空格连接牌面"
    return " ".join(hand)


def _points_text(hand: list[str]) -> str:
    "手牌与点数文本"
    return f"{_card_text(hand)}（{hand_value(hand)}点）"


async def _inc_coins(uid: str, delta: int) -> None:
    "给用户增减积分（用户不存在则忽略）"
    user = await User.get(uid)
    if user:
        await user.inc({User.coins: delta})


async def _refund_all(room: BlackjackRoom) -> None:
    "大厅取消/超时：全额退还所有玩家押注"
    for p in room.players:
        await _inc_coins(p.user_id, p.bet)


async def _build_settlement(room: BlackjackRoom, bot: Bot) -> str:
    "庄家补牌+结算，就地完成积分入账，返回结算消息文本。结算后在调用处移除房间。"
    play_dealer(room.deck, room.dealer_hand)
    lines = [f"【21点 结算】", f"庄家：{_points_text(room.dealer_hand)}"]
    for p in room.players:
        label, inc = compute_result(room.dealer_hand, p)
        await _inc_coins(p.user_id, inc)
        nick = await get_nick(room.session_id, p.user_id, bot)
        delta = inc - p.bet  # 展示盈亏
        delta_txt = f"+{delta}" if delta >= 0 else str(delta)
        lines.append(
            f"{nick}（{p.user_id}）：{_points_text(p.hand)} {label} {delta_txt}积分"
        )
    return "\n".join(lines)


async def _finish_if_ready(room: BlackjackRoom, bot: Bot) -> str | None:
    "全员行动完毕后庄家补牌结算并移除房间。返回结算消息文本；未就绪返回 None。"
    if not all_finished(room.players):
        return None
    msg = await _build_settlement(room, bot)
    del _rooms[room.session_id]
    return msg


# ============ 命令 ============

# 开始游戏
start_cmd = Alconna("开始游戏", Args["game?", str]["bet?", int])
StartMatcher = on_alconna(start_cmd, block=True)


@StartMatcher.handle()
async def start_game(
    user: Annotated[User, require()],
    game: Match[str],
    bet: Match[int],
    event: MessageEvent,
):
    "创建21点对局大厅"
    if (
        isinstance(event, GroupMessageEvent)
        and config.blackjack.groups
        and str(event.group_id) not in config.blackjack.groups
    ):
        await StartMatcher.finish("\n本群未开启21点功能。", at_sender=at_sender(event))

    if not game.available or game.result.strip() != "21点":
        await StartMatcher.finish(
            "\n用法：开始游戏 21点 <押注积分>", at_sender=at_sender(event)
        )

    if not bet.available or bet.result < config.blackjack.min_bet:
        await StartMatcher.finish(
            f"\n押注至少 {config.blackjack.min_bet} 积分。",
            at_sender=at_sender(event),
        )

    session_id = get_session_id(event)
    async with _room_lock(session_id):
        if session_id in _rooms:
            await StartMatcher.finish(
                "\n本会话已存在21点大厅或对局。", at_sender=at_sender(event)
            )
        if user.coins < bet.result:
            await StartMatcher.finish("\n积分不足。", at_sender=at_sender(event))

        await user.inc({User.coins: -bet.result})
        room = BlackjackRoom(
            session_id=session_id,
            host_id=user.id,
            players=[BlackjackPlayer(user_id=user.id, bet=bet.result)],
            dealer_hand=[],
            deck=new_deck(),
            phase="lobby",
            created_at=time.time(),
            last_action=time.time(),
        )
        _rooms[session_id] = room

        await StartMatcher.finish(
            f"\n【21点 大厅】"
            f"\n房主：{user.id}"
            f"\n押注：{bet.result} 积分"
            f"\n最低押注：{config.blackjack.min_bet} 积分"
            f"\n当前人数：{len(room.players)}"
            f"\n用「加入游戏 <押注积分>」加入，或「结束匹配」开始对局",
            at_sender=at_sender(event),
        )


# 加入游戏
join_cmd = Alconna("加入游戏", Args["bet?", int])
JoinMatcher = on_alconna(join_cmd, block=True)


@JoinMatcher.handle()
async def join_game(
    user: Annotated[User, require()],
    bet: Match[int],
    event: MessageEvent,
):
    "加入当前21点大厅"
    if not bet.available or bet.result < config.blackjack.min_bet:
        await JoinMatcher.finish(
            f"\n押注至少 {config.blackjack.min_bet} 积分。",
            at_sender=at_sender(event),
        )

    session_id = get_session_id(event)
    async with _room_lock(session_id):
        room = _rooms.get(session_id)
        if room is None or room.phase != "lobby":
            await JoinMatcher.finish(
                "\n当前没有可加入的21点大厅。", at_sender=at_sender(event)
            )
        if user.id in [p.user_id for p in room.players]:
            await JoinMatcher.finish("\n您已加入该对局。", at_sender=at_sender(event))
        if user.coins < bet.result:
            await JoinMatcher.finish("\n积分不足。", at_sender=at_sender(event))

        await user.inc({User.coins: -bet.result})
        room.players.append(BlackjackPlayer(user_id=user.id, bet=bet.result))
        room.last_action = time.time()

        await JoinMatcher.finish(
            f"\n已加入21点大厅！"
            f"\n押注：{bet.result} 积分"
            f"\n当前人数：{len(room.players)}",
            at_sender=at_sender(event),
        )


# 结束匹配
EndMatcher = on_alconna(Alconna("结束匹配"), block=True)


@EndMatcher.handle()
async def end_match(
    user: Annotated[User, require()],
    bot: Bot,
    event: MessageEvent,
):
    "开始正式对局（发牌）"
    session_id = get_session_id(event)
    async with _room_lock(session_id):
        room = _rooms.get(session_id)
        if room is None or room.phase != "lobby":
            await EndMatcher.finish(
                "\n当前没有等待匹配的21点大厅。", at_sender=at_sender(event)
            )

        # 发牌：每位玩家两张、庄家两张
        for p in room.players:
            p.hand = [draw_card(room.deck), draw_card(room.deck)]
        room.dealer_hand = [draw_card(room.deck), draw_card(room.deck)]
        room.phase = "playing"
        room.last_action = time.time()

        lines = ["【21点 对局开始】", f"庄家：{room.dealer_hand[0]} + ?"]
        for p in room.players:
            nick = await get_nick(room.session_id, p.user_id, bot)
            seg = f"{nick}（{p.user_id}）：{_points_text(p.hand)}"
            if is_blackjack(p.hand):
                seg += "（黑杰克！）"
                p.finished = True
                p.busted = False
            lines.append(seg)

        settle = await _finish_if_ready(room, bot)
        if settle is not None:
            await EndMatcher.finish(settle, at_sender=at_sender(event))
        await EndMatcher.finish("\n".join(lines), at_sender=at_sender(event))


# 取消对局
CancelMatcher = on_alconna(Alconna("取消对局"), block=True)


@CancelMatcher.handle()
async def cancel_room(
    user: Annotated[User, require()],
    event: MessageEvent,
):
    "大厅期间取消并全额退款"
    session_id = get_session_id(event)
    async with _room_lock(session_id):
        room = _rooms.get(session_id)
        if room is None or room.phase != "lobby":
            await CancelMatcher.finish(
                "\n仅大厅阶段可取消对局。", at_sender=at_sender(event)
            )
        if user.id not in [p.user_id for p in room.players]:
            await CancelMatcher.finish("\n您未参与该对局。", at_sender=at_sender(event))

        await _refund_all(room)
        del _rooms[session_id]

        await CancelMatcher.finish(
            "\n已取消对局并全额退还押注。", at_sender=at_sender(event)
        )


# 要牌
HitMatcher = on_alconna(Alconna("要牌"), block=True)


@HitMatcher.handle()
async def hit(
    user: Annotated[User, require()],
    bot: Bot,
    event: MessageEvent,
):
    "要牌"
    session_id = get_session_id(event)
    async with _room_lock(session_id):
        room = _rooms.get(session_id)
        if room is None or room.phase != "playing":
            await HitMatcher.finish(
                "\n当前没有进行中的21点对局。", at_sender=at_sender(event)
            )
        p = next((p for p in room.players if p.user_id == user.id), None)
        if p is None or p.finished:
            await HitMatcher.finish(
                "\n您不在对局中或已停牌。", at_sender=at_sender(event)
            )

        p.hand.append(draw_card(room.deck))
        room.last_action = time.time()
        pv = hand_value(p.hand)

        if pv > 21:
            p.busted = True
            p.finished = True
            await HitMatcher.send(f"\n爆牌！{pv}点", at_sender=at_sender(event))
        elif pv == 21:
            p.finished = True
            await HitMatcher.send(f"\n21点！", at_sender=at_sender(event))
        else:
            await HitMatcher.send(f"\n当前 {pv} 点", at_sender=at_sender(event))

        settle = await _finish_if_ready(room, bot)
        if settle is not None:
            await HitMatcher.finish(settle, at_sender=at_sender(event))


# 停牌
StandMatcher = on_alconna(Alconna("停牌"), block=True)


@StandMatcher.handle()
async def stand(
    user: Annotated[User, require()],
    bot: Bot,
    event: MessageEvent,
):
    "停牌"
    session_id = get_session_id(event)
    async with _room_lock(session_id):
        room = _rooms.get(session_id)
        if room is None or room.phase != "playing":
            await StandMatcher.finish(
                "\n当前没有进行中的21点对局。", at_sender=at_sender(event)
            )
        p = next((p for p in room.players if p.user_id == user.id), None)
        if p is None or p.finished:
            await StandMatcher.finish(
                "\n您不在对局中或已停牌。", at_sender=at_sender(event)
            )

        p.finished = True
        room.last_action = time.time()
        await StandMatcher.send(
            f"\n{hand_value(p.hand)}点停牌", at_sender=at_sender(event)
        )

        settle = await _finish_if_ready(room, bot)
        if settle is not None:
            await StandMatcher.finish(settle, at_sender=at_sender(event))


# 加倍
DoubleMatcher = on_alconna(Alconna("加倍"), block=True)


@DoubleMatcher.handle()
async def double(
    user: Annotated[User, require()],
    bot: Bot,
    event: MessageEvent,
):
    "双倍押注并补一张后强制停牌"
    session_id = get_session_id(event)
    async with _room_lock(session_id):
        room = _rooms.get(session_id)
        if room is None or room.phase != "playing":
            await DoubleMatcher.finish(
                "\n当前没有进行中的21点对局。", at_sender=at_sender(event)
            )
        p = next((p for p in room.players if p.user_id == user.id), None)
        if p is None:
            await DoubleMatcher.finish("\n您不在对局中。", at_sender=at_sender(event))
        if len(p.hand) != 2:
            await DoubleMatcher.finish(
                "\n仅发牌后的初始2张牌可加倍。", at_sender=at_sender(event)
            )
        if p.finished:
            await DoubleMatcher.finish("\n您已停牌。", at_sender=at_sender(event))
        if user.coins < p.bet:
            await DoubleMatcher.finish(
                "\n余额不足，无法加倍。", at_sender=at_sender(event)
            )

        old_bet = p.bet
        await user.inc({User.coins: -old_bet})
        p.bet *= 2
        p.hand.append(draw_card(room.deck))
        room.last_action = time.time()
        pv = hand_value(p.hand)
        p.finished = True
        if pv > 21:
            p.busted = True

        await DoubleMatcher.send(f"\n加倍！当前 {pv} 点", at_sender=at_sender(event))

        settle = await _finish_if_ready(room, bot)
        if settle is not None:
            await DoubleMatcher.finish(settle, at_sender=at_sender(event))


# ============ 超时清理 ============


async def sweep_expired_rooms():
    "大厅超时退款、对局超时强制停牌并自动结算"
    now = time.time()
    for session_id in list(_rooms.keys()):
        timeout = config.blackjack.lobby_timeout
        async with _room_lock(session_id):
            room = _rooms.get(session_id)  # 锁内重新取，避免与 handler 竞态
            if room is None:
                continue
            if room.phase == "lobby" and now - room.created_at > timeout:
                await _refund_all(room)
                del _rooms[session_id]
                logger.info(f"21点大厅超时取消：{session_id}")
            elif room.phase == "playing" and now - room.last_action > timeout:
                for p in room.players:
                    if not p.finished:
                        p.finished = True  # 强制停牌
                        p.busted = hand_value(p.hand) > 21
                try:
                    bot = get_bot()
                    msg = await _build_settlement(room, bot)
                    del _rooms[session_id]
                    if session_id.startswith("g"):
                        await bot.send_msg(group_id=int(session_id[1:]), message=msg)
                    else:
                        await bot.send_private_msg(
                            user_id=int(session_id[1:]), message=msg
                        )
                    logger.info(f"21点对局超时强制结算：{session_id}")
                except Exception:
                    logger.warning(f"21点对局超时结算发送失败：{session_id}")


@get_driver().on_startup
async def register_blackjack_sweeper():
    "注册21点超时清理任务"
    scheduler.add_job(
        sweep_expired_rooms,
        "interval",
        minutes=1,
        id="blackjack_room_sweeper",
        replace_existing=True,
    )
    logger.info("已注册21点大厅/对局超时清理任务")
