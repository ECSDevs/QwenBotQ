# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"21点配置模型"

from pydantic import BaseModel, field_validator


class BlackjackConfig(BaseModel):
    groups: list[str] = []  # 开启21点的群号列表，空列表=所有会话开放（私聊不受此限制）
    min_bet: int = 10  # 最低押注积分
    lobby_timeout: int = 300  # 大厅超时/对局无行动超时（秒）

    @field_validator("min_bet")
    def validate_min_bet(cls, v):
        if v < 1:
            raise ValueError("min_bet 必须大于等于 1")
        return v

    @field_validator("lobby_timeout")
    def validate_timeout(cls, v):
        if v < 1:
            raise ValueError("lobby_timeout 必须大于等于 1")
        return v
