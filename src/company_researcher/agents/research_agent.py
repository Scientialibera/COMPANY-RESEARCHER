from __future__ import annotations

from typing import Any

from .compat import create_agent_compat, extract_reasoning_summaries
from ..models import AgentConfig, OpenAIConfig


def _result_to_text(result: object) -> str:
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    return str(result)


async def run_research_agent(
    responses_client: object,
    agent_config: AgentConfig,
    openai_config: OpenAIConfig,
    system_prompt: str,
    company_context: str,
) -> tuple[str, list[str]]:
    """Run research agent and return (report_text, reasoning_summaries)."""
    tools: list[Any] = []
    if agent_config.enable_web_search:
        tools.append({"type": "web_search_preview"})

    from .factory import build_agent_chat_options

    agent = create_agent_compat(
        responses_client,
        name=agent_config.name,
        instructions=system_prompt,
        tools=tools,
        additional_chat_options=build_agent_chat_options(openai_config),
    )

    prompt = (
        "Create an in-depth company research report.\n\n"
        "Company metadata:\n"
        f"{company_context}"
    )
    result = await agent.run(prompt)
    report = _result_to_text(result)
    reasoning = extract_reasoning_summaries(result) if openai_config.reasoning_model else []
    return report, reasoning
