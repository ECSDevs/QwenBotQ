# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"自动更新配置模型"

from pydantic import BaseModel, Field


class AutoUpdateConfig(BaseModel):
    "自动更新配置"

    enable: bool = True  # 是否启用自动更新
    interval: int = Field(default=300, ge=10)  # 检查间隔（秒），最小 10 秒
    remote: str = "origin"  # 远端名
    branch: str | None = None  # 跟踪分支，不填则使用当前分支
    restart_command: list[str] | None = None  # 重启命令，不填则沿用当前启动命令
