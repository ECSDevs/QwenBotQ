# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import asyncio
import functools
import io
import os
import shutil
import subprocess

from nonebot import on_command
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11.message import MessageSegment
from PIL import Image, ImageDraw, ImageFont

from .bot_utils import at_sender

# 渲染所用的中文字体候选（按优先级），均不存在时借助 fontconfig 查找，最后退化为 PIL 默认字体
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑（Windows）
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体（Windows）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Debian/Ubuntu
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",  # Arch
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",  # Fedora
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # 文泉驿微米黑（Linux）
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # 文泉驿正黑（Linux）
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # droid fallback
)

# fontconfig 只返回文件名（不带目录）时的兜底搜索目录
_FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
)

_TITLE_SIZE = 26
_BODY_SIZE = 18
_MARGIN = 24
_MAX_WIDTH = 900  # 正文最大像素宽度，超宽自动换行
_TITLE_COLOR = (31, 111, 179)  # 深蓝
_BODY_COLOR = (60, 60, 60)
_BG_COLOR = (255, 255, 255)


def _normalize_font_path(path: str) -> str | None:
    """把 fontconfig 给出的字体路径规范为真实存在的绝对路径。"""
    if not path:
        return None
    if os.path.isfile(path):
        return path
    if os.path.isabs(path):
        return None
    # 少数环境下 fontconfig 仅返回文件名，按文件名到标准字体目录中查找
    name = os.path.basename(path)
    for root in _FONT_DIRS:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            if name in filenames:
                return os.path.join(dirpath, name)
    return None


def _find_fontconfig_font() -> str | None:
    """通过 fontconfig 查询系统中实际支持中文的字体文件（Linux/macOS）。"""
    if not shutil.which("fc-match"):
        return None
    try:
        # 不带 family 前缀，让 fontconfig 直接按语言挑选；带 sans-serif 时可能命中不含中文字形的字体
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=zh"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _normalize_font_path(out.stdout.strip())


@functools.lru_cache(maxsize=1)
def _resolve_font_path() -> str | None:
    """定位可用的中文字体文件；进程内只解析一次，避免每次渲染都调用 fontconfig。"""
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            logger.info(f"帮助图片渲染字体：{path}")
            return path
    path = _find_fontconfig_font()
    if path:
        logger.info(f"帮助图片渲染字体：{path}")
        return path
    logger.warning(
        "未找到可用的中文字体，帮助图片中的中文可能显示为乱码/方框；"
        "请安装 CJK 字体（如 Debian/Ubuntu 的 fonts-noto-cjk 或 fonts-wqy-microhei）后重启"
    )
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _resolve_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            logger.warning(f"字体 {path} 加载失败，回退到 PIL 默认字体")
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 旧版 Pillow 不支持 size 参数
        return ImageFont.load_default()


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按像素宽度逐字换行，保留空行。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        line = ""
        for ch in raw:
            if font.getlength(line + ch) <= max_width:
                line += ch
            else:
                lines.append(line)
                line = ch
        lines.append(line)
    return lines


def _render_help_image(text: str) -> bytes:
    """把帮助文本绘制为 PNG 图片并返回字节流。"""
    title_font = _load_font(_TITLE_SIZE)
    body_font = _load_font(_BODY_SIZE)

    lines = text.strip("\n").split("\n")
    wrapped: list[str] = []
    for raw in lines:
        wrapped.extend(_wrap_lines(raw, body_font, _MAX_WIDTH))

    body_line_h = round(_BODY_SIZE * 1.7)
    title_line_h = _TITLE_SIZE * 2
    has_title = bool(wrapped and wrapped[0])
    # 去掉被当作标题的首行，其余按正文排版
    body = wrapped[1:] if has_title else wrapped

    body_width = max((round(body_font.getlength(l)) for l in body), default=0)
    title_width = round(title_font.getlength(wrapped[0])) if has_title else 0
    width = max(title_width, body_width) + _MARGIN * 2

    height = (
        _MARGIN + (title_line_h if has_title else 0) + body_line_h * len(body) + _MARGIN
    )

    img = Image.new("RGB", (max(width, 1), max(height, 1)), _BG_COLOR)
    draw = ImageDraw.Draw(img)
    y = _MARGIN
    if has_title:
        draw.text((_MARGIN, y), wrapped[0], font=title_font, fill=_TITLE_COLOR)
        y += title_line_h
    for line in body:
        if line:
            draw.text((_MARGIN, y), line, font=body_font, fill=_BODY_COLOR)
        y += body_line_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Help:
    msg: str = "QwenBotQ 命令列表"
    superuser_msg: str = ""  # 仅供超管私聊查看的命令 section

    @classmethod
    def get_help(cls, with_superuser: bool = False) -> str:
        if with_superuser and cls.superuser_msg:
            return cls.msg + cls.superuser_msg
        return cls.msg

    @classmethod
    def append_help(cls, msg: str) -> None:
        cls.msg += f"{msg}"

    @classmethod
    def append_superuser_help(cls, msg: str) -> None:
        cls.superuser_msg += f"{msg}"


HelpMatcher = on_command("帮助", block=True)


@HelpMatcher.handle()
async def show_help(bot: Bot, event: MessageEvent):
    # 仅在超管私聊时展示超管 section
    show_superuser = isinstance(event, PrivateMessageEvent) and await SUPERUSER(
        bot, event
    )
    data = await asyncio.to_thread(_render_help_image, Help.get_help(show_superuser))
    await HelpMatcher.finish(MessageSegment.image(data), at_sender=at_sender(event))
