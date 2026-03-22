from __future__ import annotations

from typing import Any

from agent_framework import TextReasoningContent


def create_agent_compat(
    responses_client: object,
    *,
    additional_chat_options: dict[str, Any] | None = None,
    **kwargs: Any,
) -> object:
    if additional_chat_options:
        kwargs["additional_chat_options"] = additional_chat_options

    create_agent = getattr(responses_client, "create_agent", None)
    if callable(create_agent):
        return create_agent(**kwargs)

    as_agent = getattr(responses_client, "as_agent", None)
    if callable(as_agent):
        return as_agent(**kwargs)

    raise AttributeError("Responses client does not expose create_agent or as_agent.")


def extract_reasoning_summaries(result: object) -> list[str]:
    """Extract reasoning summary texts from an AgentRunResponse."""
    summaries: list[str] = []
    messages = getattr(result, "messages", None) or []
    for msg in messages:
        for content in (getattr(msg, "contents", None) or []):
            if isinstance(content, TextReasoningContent) and content.text:
                summaries.append(content.text)
    return summaries
