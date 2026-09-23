# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from collections.abc import Sequence, Callable, Awaitable

from motor.motor_asyncio import AsyncIOMotorClient
from nonebot.log import logger
from nonebot import get_driver
from beanie import Document, init_beanie

from .. import config


class Mongo:
    "nonebot_plugin_mongodb 修复内嵌版"

    _client: AsyncIOMotorClient | None = None

    @classmethod
    def client(cls) -> AsyncIOMotorClient:
        "MongoDB 客户端"
        if not cls._client:
            try:
                logger.info("正在初始化MongoDB客户端...")
                cls._client = AsyncIOMotorClient(config.database.uri)
            except Exception as e:
                raise RuntimeError("MongoDB客户端初始化失败") from e
        return cls._client

    @classmethod
    async def register_models(cls, document_models: Sequence[type[Document]]) -> None:
        "注册模型"
        database = getattr(cls.client(), config.database.name)
        await init_beanie(database, document_models=document_models)


require_inject: list[Callable[[], None | Awaitable[None]]] = []

from . import (
    subscribe,
    user,
    vip,
    agents,
    lottery,
    recalloffset,
    recallsess,
    sessionagent,
    sessioncontext,
    searchstate,
)


@get_driver().on_startup
async def initialize_database():
    "初始化数据库"

    # 引擎初始化

    document_models = Document.__subclasses__()
    if not document_models:
        raise RuntimeError("没有有效的文档子类")

    # 检查重复模型
    document_names: dict[str, str] = {}
    for cls in document_models:
        cls_path = f"{cls.__module__}.{cls.__name__}"
        cls_name = cls.__name__.lower()
        if cls_name in document_names:
            clashed_cls_path = document_names[cls_name]
            raise RuntimeError(
                f"重复的文档子类: {cls_name} 来自 {cls_path} 和 {clashed_cls_path}"
            )
        else:
            document_names[cls_name] = cls_path

    logger.debug(
        "正在初始化MongoDB文档:\n"
        + "\n".join(
            [
                f"{cls_name} (来自 {cls_path})"
                for cls_name, cls_path in document_names.items()
            ]
        )
    )

    await Mongo.register_models(document_models)

    for func in require_inject:
        r = func()
        if isinstance(r, Awaitable):
            await r


@get_driver().on_shutdown
async def close_database():
    "关闭数据库连接"
    if Mongo._client:
        Mongo._client.close()
        logger.info("MongoDB客户端已关闭")
