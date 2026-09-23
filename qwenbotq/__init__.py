# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

# injects urllib3
import truststore

truststore.inject_into_ssl()

"QwenBotQ 主要部分"

# standard imports
from importlib import import_module

# external imports
from nonebot import require

# internal imports
from .config_model import get_config

# constants
config = get_config()

# fixed features
require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
import_module(".fileserver", __package__)
import_module(".binding", __package__)
import_module(".usersystem", __package__)
import_module(".blackjack", __package__)
import_module(".imagesearch", __package__)
import_module(".superuser", __package__)
import_module(".imagecache", __package__)
import_module(".lognotice", __package__)

# optional features
if config.ai:
    import_module(".ai", __package__)
if config.focus:
    import_module(".bilinotice", __package__)
if config.lottery:
    import_module(".lottery", __package__)
