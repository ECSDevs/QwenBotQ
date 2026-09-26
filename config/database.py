# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"MongoDB 数据库配置模型"

from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    "数据库配置"

    uri: str = "mongodb://127.0.0.1:27017"  # 数据库地址
    name: str = "aioBot"  # 数据库名
