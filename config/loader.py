# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"""config.yml 的读取、默认值生成与缺失项补全。

配置文件固定位于仓库根目录（本包的上一级），不随运行目录变化。启动时
文件不存在会按默认值生成，已存在则只把缺失的字段补全为默认值后写回，
用户已填写的取值不会被覆盖；读写都走 ruamel.yaml 的 round-trip 模式，
补全是在读入的对象上就地追加，因此原有注释、引号与排版都会保留。
"""

# standard imports
from copy import deepcopy
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin

# external imports
from pydantic import BaseModel
from pydantic_core import PydanticUndefined
from ruamel.yaml import YAML

from nonebot.log import logger

# 仓库根目录与配置文件路径
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yml"

# 字段没有默认值时的内部标记
_UNSET = object()

# round-trip 模式：保留注释；保留引号（避免 "12345" 之类的字符串被当成数字）
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def load_or_generate(model: type[BaseModel]) -> dict:
    "读取 config.yml；缺失时按默认值生成，已存在时补全缺失字段并写回"

    if not CONFIG_PATH.exists():
        data = defaults_for(model)
        _write(data)
        logger.info(f"未找到 {CONFIG_PATH.name}，已生成默认配置：{CONFIG_PATH}")
        return data

    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = _yaml.load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{CONFIG_PATH.name} 顶层必须是键值映射")

    if fill_missing(model, data):
        _write(data)
        logger.info(f"已为 {CONFIG_PATH.name} 补全缺失的默认配置项")
    return data


def defaults_for(model: type[BaseModel]) -> dict:
    "按模型默认值构造完整的配置字典（跳过不写入文件的字段）"

    result: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if field.exclude:
            continue
        value = _default_value(field)
        if value is not _UNSET:
            result[name] = value
    return result


def fill_missing(model: type[BaseModel], data: dict) -> bool:
    "就地为 data 补全模型中缺失的字段；返回是否有改动"

    changed = False
    for name, field in model.model_fields.items():
        if field.exclude:
            continue
        if name not in data:
            value = _default_value(field)
            if value is not _UNSET:
                data[name] = value
                changed = True
            continue
        if _fill_value(field, data[name]):
            changed = True
    return changed


def _write(data: dict) -> None:
    "写回配置文件；写入失败只记录告警，不阻断启动"

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            _yaml.dump(data, f)
    except OSError as e:
        logger.warning(f"配置写回失败（{e}），本次仅使用内存中的配置")


def _default_value(field) -> Any:
    "字段的默认值；没有默认值时返回 _UNSET"

    default = field.get_default(call_default_factory=True)
    if isinstance(default, BaseModel):
        return default.model_dump()
    if default is not PydanticUndefined:
        return deepcopy(default)

    model, nullable = _model_type(field.annotation)
    if model is None:
        return _UNSET
    return None if nullable else defaults_for(model)


def _fill_value(field, value: Any) -> bool:
    "就地为已存在字段内部的缺失项补全；返回是否有改动"

    if get_origin(field.annotation) is dict and isinstance(value, dict):
        model, _ = _model_type(get_args(field.annotation)[-1])
        if model is None:
            return False
        changed = False
        for item in value.values():
            if isinstance(item, dict) and fill_missing(model, item):
                changed = True
        return changed

    model, _ = _model_type(field.annotation)
    if model is not None and isinstance(value, dict):
        return fill_missing(model, value)
    return False


def _model_type(annotation: Any) -> tuple[type[BaseModel] | None, bool]:
    "注解为（可空的）配置模型时返回其类型与是否可空"

    origin = get_origin(annotation)
    if origin is None:
        candidates, nullable = [annotation], False
    elif origin in (Union, UnionType):
        args = get_args(annotation)
        candidates = [a for a in args if a is not type(None)]
        nullable = type(None) in args
    else:
        return None, False

    for candidate in candidates:
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate, nullable
    return None, False
