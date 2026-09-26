# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"""自动更新插件：探测远端改动并提醒超管，确认后拉取重启。

本插件由 ``bot.py`` 与 ``qwenbotq`` 主插件分开加载，且刻意不引用 ``qwenbotq``
包内任何模块：即使主插件导入失败，本插件仍可运行并提醒超管更新。配置读取
复用仓库根目录下独立的 ``config`` 包，与主插件共享同一份配置模型。
"""

# standard imports
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# external imports
from nonebot import get_bot, get_driver, on_command
from nonebot.adapters.onebot.v11 import PrivateMessageEvent
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule

# internal imports
from config import get_autoupdate_config

# 仓库根目录（本文件与 bot.py 同级）
_ROOT = Path(__file__).resolve().parent
# 重启时等待旧进程退出的最长秒数
_EXIT_TIMEOUT = 60.0
# 重启助手：作为独立进程启动，等待旧进程退出后再拉起机器人，参数经环境变量传入
_RELAUNCHER = r"""
import ctypes
import json
import os
import subprocess
import sys
import time

_PID = int(os.environ["AUTOUPDATE_PID"])
_CWD = os.environ["AUTOUPDATE_CWD"]
_COMMAND = json.loads(os.environ["AUTOUPDATE_CMD"])
_TIMEOUT = float(os.environ.get("AUTOUPDATE_WAIT", "60"))


def alive(target: int) -> bool:
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, target)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(code)
            ):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(target, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


_deadline = time.time() + _TIMEOUT
while time.time() < _deadline and alive(_PID):
    time.sleep(0.5)
if alive(_PID):
    sys.exit(1)
subprocess.Popen(_COMMAND, cwd=_CWD)
"""


config = get_autoupdate_config()


def _run_git(*args: str) -> str:
    "同步执行 git 命令并返回标准输出；失败时抛出 RuntimeError"

    result = subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, check=False)
    # 各平台 git 输出编码不统一，统一按 UTF-8 宽松解码，避免个别字符导致异常
    stdout = result.stdout.decode("utf-8", "replace").strip()
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} 执行失败：{stderr or stdout}")
    return stdout


async def _git(*args: str) -> str:
    "在线程中执行 git 命令，避免阻塞事件循环"

    return await asyncio.to_thread(_run_git, *args)


class Pending(NamedTuple):
    """远端待拉取的提交信息"""

    branch: str  # 跟踪的分支名
    count: int  # 远端领先本地的提交数
    summary: str  # 领先提交的摘要（最多几条）
    head: str  # 远端当前提交号，用于避免重复提醒


async def _fetch_pending() -> Pending:
    "fetch 远端并检查是否有新提交"

    branch = config.branch or await _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        raise RuntimeError("当前处于游离 HEAD 状态，跳过自动更新")

    await _git("fetch", config.remote)
    ref = f"{config.remote}/{branch}"
    # 只统计远端领先的提交数，本地领先（如已提交未推送）不应触发提醒
    count = int(await _git("rev-list", "--count", f"HEAD..{ref}"))
    summary = (
        await _git("log", "--oneline", "--no-decorate", "-n", "5", f"HEAD..{ref}")
        if count
        else ""
    )
    return Pending(branch, count, summary, await _git("rev-parse", ref))


async def _broadcast(text: str) -> bool:
    "私信所有超管；返回是否至少成功发送一条"

    try:
        bot = get_bot()
    except ValueError:
        logger.warning("自动更新提醒未发送：机器人尚未连接或存在多个连接")
        return False

    sent = False
    for sid in get_driver().config.superusers:
        try:
            await bot.send_msg(user_id=int(sid), message=text)
            sent = True
        except Exception as e:
            logger.warning(f"自动更新提醒发送失败（超管 {sid}）：{e}")
    return sent


async def _notify_pending() -> None:
    "发现未被提醒过的远端改动时私信提醒所有超管，等待超管确认后再更新"

    global _notified

    async with _lock:
        pending = await _fetch_pending()
        if not pending.count or pending.head == _notified:
            return

        commits = "\n".join(f"  {line}" for line in pending.summary.splitlines())
        text = (
            f"[自动更新] {config.remote}/{pending.branch} 领先 {pending.count} 个提交：\n"
            f"{commits}\n"
            "回复 !update 拉取并重启机器人"
        )
        # 发送失败时不记录，下个周期继续提醒
        if await _broadcast(text):
            _notified = pending.head


def _launch_command() -> list[str]:
    "构造重启命令：沿用当前解释器与原始脚本/参数，保证虚拟环境与依赖可用"

    if config.restart_command:
        return list(config.restart_command)
    # 不能用系统进程命令行来还原：虚拟环境启动器会把命令行写成基础解释器，
    # 直接照搬会丢失 venv 的 site-packages（依赖导入失败）
    return [sys.executable, *sys.argv]


def _spawn_relauncher() -> None:
    "启动独立的助手进程，待当前进程退出后按原解释器与脚本重新拉起机器人"

    env = {
        **os.environ,
        "AUTOUPDATE_PID": str(os.getpid()),
        "AUTOUPDATE_CWD": str(_ROOT),
        "AUTOUPDATE_CMD": json.dumps(_launch_command(), ensure_ascii=False),
        "AUTOUPDATE_WAIT": str(_EXIT_TIMEOUT),
    }
    subprocess.Popen(
        [sys.executable, "-c", _RELAUNCHER],
        cwd=str(_ROOT),
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )


async def _restart() -> None:
    "启动重启助手并退出当前进程，由助手在端口释放后拉起新进程"

    _spawn_relauncher()
    logger.info("自动更新：已启动重启助手，当前进程即将退出")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


# 串行化 git 操作，避免定时检查与超管确认同时拉取
_lock = asyncio.Lock()
# 已提醒过的远端提交号，同一批提交只提醒一次
_notified: str | None = None
_task: asyncio.Task[None] | None = None


async def _poll() -> None:
    "周期性检查远端更新并提醒超管"

    while True:
        # 先等待一个周期，避免启动阶段机器人尚未连接导致提醒发送失败
        await asyncio.sleep(config.interval)
        try:
            await _notify_pending()
        except Exception as e:
            logger.warning(f"自动更新检查失败：{e}")


@get_driver().on_startup
async def _start_autoupdate() -> None:
    "启动自动更新后台任务"

    global _task
    if not config.enable:
        return
    if not (_ROOT / ".git").exists():
        logger.warning("自动更新未启用：当前目录不是 git 仓库")
        return
    if not shutil.which("git"):
        logger.warning("自动更新未启用：未找到 git 命令")
        return
    _task = asyncio.create_task(_poll())
    logger.info(
        f"自动更新已启用：每 {config.interval} 秒检查 {config.remote} 远端"
        "是否有新提交，发现后私信提醒超管"
    )


@get_driver().on_shutdown
async def _stop_autoupdate() -> None:
    "取消后台任务，避免关闭时产生未结束任务的告警"

    if _task is not None:
        _task.cancel()


_private_rule = Rule(lambda event: isinstance(event, PrivateMessageEvent))

# !update：确认拉取远端改动并重启
UpdateMatcher = on_command(
    "!update",
    rule=_private_rule,
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@UpdateMatcher.handle()
async def confirm_update() -> None:
    "确认更新：快进拉取远端改动并重启机器人"

    if not config.enable:
        await UpdateMatcher.finish(
            "自动更新未启用：请在 config.yml 中配置 autoupdate 段"
        )

    try:
        async with _lock:
            pending = await _fetch_pending()
            if not pending.count:
                await UpdateMatcher.finish("已是最新，无需更新")
            logger.info(
                f"自动更新：{config.remote}/{pending.branch} 领先 "
                f"{pending.count} 个提交，开始拉取"
            )
            # 只允许快进，避免在部署机上产生合并提交或冲突
            await _git("pull", "--ff-only", config.remote, pending.branch)
    except Exception as e:
        await UpdateMatcher.finish(f"更新失败：{e}")

    logger.info("自动更新：拉取完成，准备重启")
    await UpdateMatcher.send("更新完成，正在重启机器人…")
    await _restart()
