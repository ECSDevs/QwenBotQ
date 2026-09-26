# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


"机器人启动文件"

from sys import stdout, platform
from os import environ
import asyncio
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.log import logger_id, default_filter

# 修复 AIODNS 错误
if platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 作为服务运行时不重复输出时间
if environ.get("RUNNING_AS_SERVICE", "no") == "yes":
    nonebot.logger.remove(logger_id)
    _ = nonebot.logger.add(
        stdout,
        level=0,
        diagnose=True,
        format="[<lvl>{level}</lvl>] <c><u>{name}</u></c> | {message}",
        filter=default_filter,
    )

nonebot.init(reboot_load_command=False)

driver = nonebot.get_driver()
driver.register_adapter(OnebotV11Adapter)

if __name__ == "__main__":
    # 自动更新插件与主插件分开加载，主插件导入失败时仍能自动拉取修复并重启
    nonebot.load_plugin("autoupdate")
    nonebot.load_plugin("qwenbotq")
    nonebot.run()
