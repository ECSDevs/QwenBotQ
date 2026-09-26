# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from pydantic import BaseModel


class ImageSearchConfig(BaseModel):
    """The config class of image search."""

    exhentai_cookies: str | None = None
