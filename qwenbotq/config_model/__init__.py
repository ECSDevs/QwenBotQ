# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


"The config module of QwenBotQ."

from pydantic import BaseModel
from yaml import safe_load

from nonebot import get_driver

from .ai import LLMConfig
from .database import DatabaseConfig
from .focus import FocusOptions
from .price import PriceConfig
from .lottery import LotteryConfig
from .blackjack import BlackjackConfig
from .imagesearch import ImageSearchConfig
from .fileserver import FileServerConfig


class Config(BaseModel):
    """The config class of QwenBotQ."""

    supermgr_ids: list[str] = list(
        get_driver().config.superusers
    )  # 超管列表，自动从Nonebot读取
    database: DatabaseConfig = DatabaseConfig()  # 数据库
    ai: LLMConfig | None = None  # 大模型配置
    price: PriceConfig = PriceConfig()  # 价格配置
    focus: FocusOptions | None = None  # 关注配置
    lottery: LotteryConfig = LotteryConfig()  # 抽奖配置
    blackjack: BlackjackConfig = BlackjackConfig()  # 21点配置
    imagesearch: ImageSearchConfig = ImageSearchConfig()  # 图片搜索配置
    fileserver: FileServerConfig = FileServerConfig()  # 文件服务器配置


def get_config() -> Config:
    """Get the config of QwenBotQ."""

    with open("config.yml", encoding="utf-8") as f:
        data = safe_load(f)
    return Config.model_validate(data)
