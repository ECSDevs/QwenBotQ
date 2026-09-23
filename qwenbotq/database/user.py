# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from datetime import datetime, date, timedelta

from pydantic import BaseModel, Field, field_validator
from beanie import Document

from .utils import noid


class Binded(BaseModel):
    "绑定用户"

    id: str
    expire: date

    @field_validator("expire", mode="before")
    @classmethod
    def expire_to_date(cls, v: datetime | date) -> date:
        "datetime转化为date"
        return v.date() if isinstance(v, datetime) else v


class User(Document):
    "用户文档"

    id: str = Field(default_factory=noid)
    coins: int = 0
    sign_expire: date = date.min
    model: str = ""
    binded: Binded | None = None

    @field_validator("sign_expire", mode="before")
    @classmethod
    def expire_to_date(cls, v: datetime | date) -> date:
        "datetime转化为date"
        return v.date() if isinstance(v, datetime) else v


async def apply_bind(a: User, b: User) -> date:
    "应用一个绑定"
    expire = date.today() + timedelta(1)
    await a.set({"binded": Binded(id=b.id, expire=expire)})
    await b.set({"binded": Binded(id=a.id, expire=expire)})
    return expire


async def get_biggest_coins() -> int:
    a = await User.find_one(sort=["-coins"])
    return a.coins if a else 0
