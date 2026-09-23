# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"价格配置模型"

from pydantic import BaseModel


class PriceConfig(BaseModel):
    daily_sign_max_coins: int = 50  # 每日签到最大获得积分数
    daily_sign_min_coins: int = 1  # 最小
