# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

# injects urllib3
import truststore

truststore.inject_into_ssl()

"""QwenBotQ 主要部分：核心配置与功能加载。

每个功能都作为独立的 NoneBot 子插件（标识符 ``qwenbotq:<功能名>``）加载：
单个功能导入失败时只会记录该功能的错误并跳过，其余功能继续正常工作。
"""

# external imports
from nonebot import load_plugin
from nonebot.log import logger

# internal imports
from config import get_config

# constants
config = get_config()

# 第三方插件依赖：与功能一样独立加载，缺失或加载失败时只影响真正用到它的功能
load_plugin("nonebot_plugin_alconna")
load_plugin("nonebot_plugin_apscheduler")


def get_features() -> list[str]:
    "本次启动需要加载的功能列表（固定功能 + 配置中已启用的可选功能）"

    features = [
        "fileserver",
        "binding",
        "usersystem",
        "blackjack",
        "imagesearch",
        "superuser",
        "imagecache",
        "lognotice",
    ]

    if config.ai:
        features.append("ai")
    if config.focus:
        features.append("bilinotice")
    if config.lottery:
        features.append("lottery")

    return features


def load_features() -> list[str]:
    "逐个加载功能子插件，返回加载失败的功能名"

    features = get_features()
    failed = [name for name in features if load_plugin(f"{__package__}.{name}") is None]

    if failed:
        logger.warning(
            f"以下功能加载失败，已跳过（其余功能不受影响）：{'、'.join(failed)}"
        )
    else:
        logger.info(f"QwenBotQ 全部 {len(features)} 个功能已加载")

    return failed


load_features()
