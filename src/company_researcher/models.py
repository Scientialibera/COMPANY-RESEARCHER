from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceStorageConfig:
    container_name: str
    company_metadata_file_name: str
    indicator_file_name: str


@dataclass(frozen=True)
class SinkStorageConfig:
    container_name: str


@dataclass(frozen=True)
class AdditionalInfoConfig:
    enabled: bool
    container_name: str


@dataclass(frozen=True)
class PromptStorageConfig:
    container_name: str


@dataclass(frozen=True)
class FunctionDefinitionStorageConfig:
    container_name: str


@dataclass(frozen=True)
class OpenAIConfig:
    endpoint: str
    deployment: str
    api_version: str
    api_key: str
    max_tokens: int
    temperature: float
    reasoning_model: bool
    reasoning_effort: str


@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt_blob_name: str
    enable_web_search: bool


@dataclass(frozen=True)
class FunctionCallConfig:
    definition_blob_name: str
    enforce_single_tool_call: bool


@dataclass(frozen=True)
class OutputConfig:
    push_to_sink: bool
    local_output_dir: str
    file_name: str
    append_utc_timestamp_to_sink_file_name: bool


@dataclass(frozen=True)
class AppConfig:
    environment: str
    log_level: str
    storage_account_name: str
    source_storage: SourceStorageConfig
    sink_storage: SinkStorageConfig
    additional_info_storage: AdditionalInfoConfig
    prompt_storage: PromptStorageConfig
    function_definition_storage: FunctionDefinitionStorageConfig
    openai: OpenAIConfig
    our_company_profile_blob_name: str
    context_fields: list[str]
    research_agent: AgentConfig
    strategy_agent: AgentConfig
    function_call: FunctionCallConfig
    output: OutputConfig


@dataclass(frozen=True)
class ProcessRequest:
    company_folder: str


@dataclass(frozen=True)
class ProcessResult:
    company_folder: str
    research_report: str
    classification_payload: dict[str, Any]
    output_uri: str
    reasoning: dict[str, list[str]] | None = None
