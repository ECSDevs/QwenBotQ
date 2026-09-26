# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

from pydantic import BaseModel


class FileServerConfig(BaseModel):
    """The config class of the global file server."""

    file_server_port: int = 9080  # 本地绑定端口
    remote_host: str = "172.17.0.1"  # OneBot 端可访问的主机
    remote_port: int | None = None  # 远程端口，默认同 file_server_port
