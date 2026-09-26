# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"抽奖配置模型"

from pydantic import BaseModel


class LotteryConfig(BaseModel):
    groups: list[str] = []  # 开启抽奖的群号列表
    ticket_price: int = 200  # 每注价格
    reward_per_match: int = 200  # 每匹配一位的奖励
