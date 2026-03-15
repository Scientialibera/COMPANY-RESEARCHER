from __future__ import annotations

from .compat import create_agent_compat
from ..models import AgentConfig


def _result_to_text(result: object) -> str:
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    return str(result)


async def run_research_agent(
    responses_client: object,
    agent_config: AgentConfig,
    system_prompt: str,
    company_context: str,
) -> str:
    tools = []
    if agent_config.enable_web_search:
        tools.append({"type": "web_search_preview"})

    agent = create_agent_compat(
        responses_client,
        name=agent_config.name,
        instructions=system_prompt,
        tools=tools,
    )

    prompt = (
        "Create an in-depth company research report.\n\n"
        "Company metadata:\n"
        f"{company_context}"
    )
    result = await agent.run(prompt)
    return _result_to_text(result)
