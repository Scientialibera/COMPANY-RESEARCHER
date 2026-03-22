from __future__ import annotations

from typing import Any

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

from ..models import OpenAIConfig


def build_responses_client(config: OpenAIConfig) -> AzureOpenAIResponsesClient:
    kwargs: dict[str, Any] = {
        "endpoint": config.endpoint,
        "deployment_name": config.deployment,
    }
    if config.api_version.strip():
        kwargs["api_version"] = config.api_version

    if config.api_key.strip():
        kwargs["api_key"] = config.api_key.strip()
    else:
        kwargs["credential"] = DefaultAzureCredential()

    return AzureOpenAIResponsesClient(**kwargs)


def build_agent_chat_options(config: OpenAIConfig) -> dict[str, Any]:
    """Build additional_chat_options appropriate for the model type.

    Reasoning models (GPT-5-mini, o-series) do not accept temperature or
    max_tokens; they use reasoning.effort and reasoning.summary instead.
    """
    if not config.reasoning_model:
        return {}

    return {
        "reasoning": {
            "effort": config.reasoning_effort,
            "summary": "auto",
        },
    }
