from __future__ import annotations

from typing import Any

from .compat import create_agent_compat, extract_reasoning_summaries
from ..function_calling import validate_sales_strategy_payload
from ..models import AgentConfig, OpenAIConfig


class StrategyToolCollector:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def build_tool(self) -> Any:
        def classify_revenue_and_generate_sales_pitch(
            revenue_class: str,
            sales_pitch: list[str],
        ) -> str:
            candidate = {
                "revenue_class": revenue_class,
                "sales_pitch": sales_pitch,
            }
            self.payload = validate_sales_strategy_payload(candidate)
            return "Payload captured successfully."

        return classify_revenue_and_generate_sales_pitch


async def run_strategy_agent(
    responses_client: object,
    agent_config: AgentConfig,
    openai_config: OpenAIConfig,
    system_prompt: str,
    research_report: str,
    additional_info_text: str,
    our_company_info: str,
    function_definition: dict[str, Any],
    enforce_single_tool_call: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Run strategy agent and return (payload, reasoning_summaries)."""
    collector = StrategyToolCollector()

    tools: list[Any] = [collector.build_tool()]
    if agent_config.enable_web_search:
        tools.insert(0, {"type": "web_search_preview"})

    from .factory import build_agent_chat_options

    agent = create_agent_compat(
        responses_client,
        name=agent_config.name,
        instructions=system_prompt,
        tools=tools,
        additional_chat_options=build_agent_chat_options(openai_config),
    )

    prompt = (
        "Use the research and optional additional files to create structured output.\n"
        "Call the function exactly once.\n\n"
        f"Function definition:\n{function_definition}\n\n"
        f"Our company info:\n{our_company_info}\n\n"
        f"Research report:\n{research_report}\n\n"
        f"Additional files:\n{additional_info_text}"
    )
    if enforce_single_tool_call:
        prompt += (
            "\n\nStrict requirement: call classify_revenue_and_generate_sales_pitch "
            "exactly once and do not emit final text before tool call."
        )

    result = await agent.run(prompt)
    if collector.payload is None:
        raise RuntimeError("Strategy tool was not called by the model.")
    reasoning = extract_reasoning_summaries(result) if openai_config.reasoning_model else []
    return collector.payload, reasoning
