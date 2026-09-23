# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

import asyncio
import io
import os

from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11.message import MessageSegment
from PIL import Image, ImageDraw, ImageFont

from .bot_utils import at_sender

# 渲染所用的中文字体候选（按优先级），找不到时会退化到 PIL 默认字体
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑（Windows）
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",  # 黑体（Windows）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # 文泉驿微米黑（Linux）
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # 文泉驿正黑（Linux）
)

_TITLE_SIZE = 26
_BODY_SIZE = 18
_MARGIN = 24
_MAX_WIDTH = 900  # 正文最大像素宽度，超宽自动换行
_TITLE_COLOR = (31, 111, 179)  # 深蓝
_BODY_COLOR = (60, 60, 60)
_BG_COLOR = (255, 255, 255)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
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
