# Copyright (c) 2026 originalFactor
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

"大模型配置模型"

from pydantic import BaseModel


class AgentLike(BaseModel):
    prompt: str
    temperature: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    max_tokens: int | None = None
    thinking: bool = False
    unsafe: bool = False


class LLMApiConfig(BaseModel):
    "LLM API"

    base: str
    token: str


class LLMModelConfig(BaseModel):
    "LLM Model"

    api_id: str
    model_id: str
    name: str = "Unknown"
    context_length: int | None = None
    max_tokens: int | None = None
    detail: str = ""
    support_images: bool = False  # 是否支持图片输入（可从 models.dev 自动补全）


class BoChaAPIConfig(BaseModel):
    "博查API配置"

    endpoint: str = "https://api.bocha.cn/v1/web-search"
    token: str


class LLMToolsConfig(BaseModel):
    "LLM Tools"

    bocha: BoChaAPIConfig | None = None


class DefaultPromptsConfig(BaseModel):
    "默认提示词配置"

    default: AgentLike = AgentLike(
        prompt="你是我的人工智能助手，请根据我的要求提供帮助。"
    )
    unsafe: AgentLike | None = None


class ModelsDevConfig(BaseModel):
    "models.dev 自动补全配置"

    enable: bool = True  # 是否启用自动补全
    url: str = "https://models.dev/models.json"  # 数据源地址
    cache_path: str = "downloads/models_dev.json"  # 本地缓存路径
    refresh_days: int = 7  # 缓存有效期（天）


class LLMConfig(BaseModel):
    "大模型配置"

    apis: dict[str, LLMApiConfig]
    models: dict[str, LLMModelConfig]
    default_prompts: DefaultPromptsConfig = DefaultPromptsConfig()
    tools: LLMToolsConfig = LLMToolsConfig()
    summarize_threshold: float = 0.8  # 上下文累计 token 达到该比例阈值时自动总结
    models_dev: ModelsDevConfig = ModelsDevConfig()  # models.dev 自动补全
