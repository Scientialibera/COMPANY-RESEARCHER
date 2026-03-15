from __future__ import annotations

from dataclasses import dataclass

from ..agents.factory import build_responses_client
from ..agents.research_agent import run_research_agent
from ..agents.strategy_agent import run_strategy_agent
from ..blob_storage import BlobStorageGateway
from ..context_builder import build_additional_context, build_company_context
from ..models import AppConfig, ProcessRequest, ProcessResult
from ..output_writer import build_result_payload, write_result


@dataclass
class TwoAgentWorkflow:
    config: AppConfig
    storage: BlobStorageGateway

    async def run(self, request: ProcessRequest) -> ProcessResult:
        company_data = self.storage.read_company_metadata(request.company_folder)
        additional_files = self.storage.read_additional_company_info(request.company_folder)

        company_context = build_company_context(company_data, self.config.context_fields)
        additional_context = build_additional_context(additional_files)
        research_prompt = self.storage.read_prompt(self.config.research_agent.system_prompt_blob_name)
        strategy_prompt = self.storage.read_prompt(self.config.strategy_agent.system_prompt_blob_name)
        our_company_info = self.storage.read_our_company_profile()
        function_definition = self.storage.read_function_definition(
            self.config.function_call.definition_blob_name
        )

        responses_client = build_responses_client(self.config.openai)

        # Step 1: deep-research agent.
        research_report = await run_research_agent(
            responses_client=responses_client,
            agent_config=self.config.research_agent,
            system_prompt=research_prompt,
            company_context=company_context,
        )

        # Step 2: strategy agent with function calling.
        function_payload = await run_strategy_agent(
            responses_client=responses_client,
            agent_config=self.config.strategy_agent,
            system_prompt=strategy_prompt,
            research_report=research_report,
            additional_info_text=additional_context,
            our_company_info=our_company_info,
            function_definition=function_definition,
            enforce_single_tool_call=self.config.function_call.enforce_single_tool_call,
        )

        result_json = build_result_payload(
            company_folder=request.company_folder,
            research_report=research_report,
            classification_payload=function_payload,
        )
        output_uri = write_result(
            config=self.config,
            storage=self.storage,
            company_folder=request.company_folder,
            payload_json=result_json,
        )

        return ProcessResult(
            company_folder=request.company_folder,
            research_report=research_report,
            classification_payload=function_payload,
            output_uri=output_uri,
        )
