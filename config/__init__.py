# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


"""QwenBotQ 的配置模块，独立于 ``qwenbotq`` 包。

集中定义 ``config.yml`` 的模型与读取逻辑，供 ``qwenbotq`` 与 ``autoupdate``
等插件共用；导入本模块不会触发 ``qwenbotq`` 的加载。首次读取时会按默认值
生成缺失的 ``config.yml``，并把已存在文件中缺失的字段补全后写回。
"""

# external imports
from pydantic import BaseModel, Field

from nonebot import get_driver
from nonebot.log import logger

# internal imports
from .ai import LLMConfig
from .autoupdate import AutoUpdateConfig
from .blackjack import BlackjackConfig
from .database import DatabaseConfig
from .fileserver import FileServerConfig
from .focus import FocusOptions
from .imagesearch import ImageSearchConfig
from .loader import load_or_generate
from .lottery import LotteryConfig
from .price import PriceConfig


class Config(BaseModel):
    """The config class of QwenBotQ."""

    supermgr_ids: list[str] = Field(
        default_factory=lambda: list(get_driver().config.superusers), exclude=True
    )  # 超管列表，自动从Nonebot读取，不写入配置文件
    database: DatabaseConfig = DatabaseConfig()  # 数据库
    ai: LLMConfig | None = None  # 大模型配置
    price: PriceConfig = PriceConfig()  # 价格配置
    focus: FocusOptions | None = None  # 关注配置
    lottery: LotteryConfig = LotteryConfig()  # 抽奖配置
    blackjack: BlackjackConfig = BlackjackConfig()  # 21点配置
    imagesearch: ImageSearchConfig = ImageSearchConfig()  # 图片搜索配置
    fileserver: FileServerConfig = FileServerConfig()  # 文件服务器配置
    autoupdate: AutoUpdateConfig | None = None  # 自动更新配置


_data: dict | None = None


def get_config() -> Config:
    """Get the config of QwenBotQ."""

    return Config.model_validate(_raw_data())


def get_autoupdate_config() -> AutoUpdateConfig:
    "读取自动更新配置；未配置或配置无效时返回停用状态，不影响调用方加载"

    section = _raw_data().get("autoupdate")
    if not isinstance(section, dict):
        return AutoUpdateConfig(enable=False)

    try:
        return AutoUpdateConfig.model_validate(section)
    except ValueError as e:
        logger.warning(f"自动更新已停用：autoupdate 配置无效（{e}）")
        return AutoUpdateConfig(enable=False)


def _raw_data() -> dict:
    "首次访问时生成/补全 config.yml，之后复用同一份数据"

    global _data
    if _data is None:
        _data = load_or_generate(Config)
    return _data
