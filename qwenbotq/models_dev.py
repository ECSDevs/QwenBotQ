# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"从 models.dev 自动补全未填充的模型元数据"

from json import dump, load
from os import makedirs
from os.path import dirname, getmtime, isfile
from time import time
from typing import Any

from httpx import AsyncClient
from nonebot.log import logger

from config.ai import LLMModelConfig, ModelsDevConfig


async def _download(url: str) -> dict:
    async with AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def load_models_dev(conf: ModelsDevConfig) -> dict:
    "加载 models.dev 数据：优先使用未过期的本地缓存，其次网络下载"
    # 本地缓存有效期内直接使用
    if (
        isfile(conf.cache_path)
        and time() - getmtime(conf.cache_path) < conf.refresh_days * 86400
    ):
        try:
            with open(conf.cache_path, encoding="utf-8") as f:
                return load(f)
        except Exception as e:
            logger.warning(f"models.dev 缓存读取失败：{e}")

    try:
        data = await _download(conf.url)
    except Exception as e:
        logger.warning(f"models.dev 下载失败，回退到本地缓存（如有）：{e}")
        if isfile(conf.cache_path):
            try:
                with open(conf.cache_path, encoding="utf-8") as f:
                    return load(f)
            except Exception as e2:
                logger.warning(f"models.dev 本地缓存读取失败：{e2}")
        return {}

    try:
        makedirs(dirname(conf.cache_path) or ".", exist_ok=True)
        with open(conf.cache_path, "w", encoding="utf-8") as f:
            dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"models.dev 缓存写入失败：{e}")
    return data


def _lookup_entry(index: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    "按 models.dev 的模型 id 查找条目：先精确匹配，再尝试带 provider 前缀的后缀匹配"
    if model_id in index:
        return index[model_id]
    matches = [k for k in index if k == model_id or k.endswith("/" + model_id)]
    if len(matches) == 1:
        return index[matches[0]]
    return None


def merge_model_metadata(
    model: LLMModelConfig, md: dict[str, Any]
) -> LLMModelConfig | None:
    "用 models.dev 的单个模型条目补全未填充字段，有改动时返回新的模型实例，否则返回 None"
    updates: dict[str, Any] = {}
    if md.get("name") and (not model.name or model.name == "Unknown"):
        updates["name"] = md.get("name")

    # 上下文与输出长度位于 limit 下（新版为 int，旧版可能嵌套 dict，两者兼容）
    limit = md.get("limit") if isinstance(md.get("limit"), dict) else None
    ctx = (limit.get("context") if limit else None) or None
    max_output = (limit.get("output") if limit else None) or None
    if isinstance(ctx, dict):
        ctx = ctx.get("context")
    if isinstance(max_output, dict):
        max_output = max_output.get("max_output")

    if model.context_length is None and ctx:
        updates["context_length"] = int(ctx)
    if model.max_tokens is None and max_output:
        updates["max_tokens"] = int(max_output)
    if not model.detail and md.get("description"):
        updates["detail"] = md.get("description")

    # 图片支持由 modalities.input 决定（默认 false 视为未填写，仅补全为 true）
    modalities = md.get("modalities")
    inputs = (
        modalities.get("input")
        if isinstance(modalities, dict) and isinstance(modalities.get("input"), list)
        else None
    )
    if not model.support_images and inputs and "image" in inputs:
        updates["support_images"] = True
    return model.model_copy(update=updates) if updates else None


async def autofill_models(
    conf: ModelsDevConfig, models: dict[str, LLMModelConfig]
) -> None:
    "遍历模型，用 models.dev 补全未填写（None/空）的元数据，不覆盖用户已设置的值"
    if not conf.enable or not models:
        return
    data = await load_models_dev(conf)
    if not data:
        return
    index = data.get("models") if isinstance(data.get("models"), dict) else data
    if not isinstance(index, dict):
        return

    hit = 0
    for name, model in models.items():
        md = _lookup_entry(index, model.model_id)
        if not md:
            continue
        updated = merge_model_metadata(model, md)
        if updated is not None:
            models[name] = updated
            hit += 1
    if hit:
        logger.info(f"已从 models.dev 补全 {hit} 个模型的元数据")
