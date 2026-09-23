# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"21点纯逻辑模块（不依赖NoneBot/数据库，可被单元测试直接加载）"

"""
注意：本模块只允许 import Python 标准库（dataclasses、random、typing）。
禁止任何 qwenbotq 相关/相对导入，也禁止 nonebot 相关导入；否则单元测试在用
importlib 直接加载本文件时会顺带触发 qwenbotq/__init__.py 读取 config.yml。
"""

from dataclasses import dataclass, field
from random import shuffle

SUITS = "♠♥♦♣"
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")


@dataclass
class BlackjackPlayer:
    "21点玩家"

    user_id: str
    bet: int  # 当前押注（加倍后翻倍）
    hand: list[str] = field(default_factory=list)
    doubled: bool = False
    finished: bool = False  # 已停牌/爆牌/加倍结束
    busted: bool = False


def new_deck() -> list[str]:
    "生成一副52张牌并洗牌，牌形如 '♠A'、'♥10'"
    deck = [suit + rank for suit in SUITS for rank in RANKS]
    shuffle(deck)
    return deck


def card_value(card: str) -> int:
    "单牌点数：2-10照值，J/Q/K=10，A=11（A的折减由 hand_value 处理）"
    rank = card[1:]
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K"):
        return 10
    return int(rank)


def hand_value(hand: list[str]) -> int:
    "手牌最优点数：取不超过21的最大值（A 按需从11折为1），无合适值则按最小（爆牌）计"
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[1:] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(hand: list[str]) -> bool:
    "黑杰克：起手恰好2张且点数21"
    return len(hand) == 2 and hand_value(hand) == 21


def draw_card(deck: list[str]) -> str:
    "从牌堆抽一张牌；牌堆耗尽时重新洗一副新牌（不重算已发牌，仅防止越界崩溃）"
    if not deck:
        deck.extend(new_deck())
    return deck.pop()


def dealer_should_hit(hand: list[str]) -> bool:
    "庄家补牌规则：小于17继续要牌（软17也停）"
    return hand_value(hand) < 17


def play_dealer(deck: list[str], dealer_hand: list[str]) -> None:
    "庄家补牌至>=17（就地修改 dealer_hand）"
    while dealer_should_hit(dealer_hand):
        dealer_hand.append(draw_card(deck))


def compute_result(dealer_hand: list[str], player: BlackjackPlayer) -> tuple[str, int]:
    "结算单个玩家，返回 (结果标签, 应返还积分量)。押注在事件发生时就已扣除，此处只计算返还额：正常胜=2*bet；黑杰克=bet+bet*3//2；平局=bet；输/爆牌=0。"
    if player.busted:
        return "爆牌", 0
    d_bj = is_blackjack(dealer_hand)
    p_bj = is_blackjack(player.hand)
    d_bust = hand_value(dealer_hand) > 21
    if d_bj and not p_bj:
        return "庄家黑杰克", 0
    if d_bust:
        return (
            ("黑杰克", player.bet + player.bet * 3 // 2)
            if p_bj
            else ("胜", player.bet * 2)
        )
    if p_bj and d_bj:
        return "平局", player.bet
    if p_bj:
        return "黑杰克", player.bet + player.bet * 3 // 2
    pv, dv = hand_value(player.hand), hand_value(dealer_hand)
    if pv > dv:
        return "胜", player.bet * 2
    if pv < dv:
        return "输", 0
    return "平局", player.bet


def all_finished(players: list[BlackjackPlayer]) -> bool:
    return all(p.finished for p in players)
