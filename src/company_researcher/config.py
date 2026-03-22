from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import (
    AdditionalInfoConfig,
    AgentConfig,
    AppConfig,
    FunctionCallConfig,
    FunctionDefinitionStorageConfig,
    OpenAIConfig,
    OutputConfig,
    PromptStorageConfig,
    SinkStorageConfig,
    SourceStorageConfig,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _resolve_path(path_value: str, project_root: Path) -> str:
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    return str((project_root / path).resolve())


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def load_app_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[2]
    config_path = os.getenv("APP_CONFIG_PATH", "config/app_config.toml")
    config_abs = Path(_resolve_path(config_path, project_root))
    raw = _load_toml(config_abs)

    storage_raw = raw["storage"]
    openai_raw = raw["openai"]
    app_raw = raw["app"]
    context_raw = raw["context"]
    agents_raw = raw["agents"]
    function_call_raw = raw["function_call"]
    output_raw = raw["output"]
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", openai_raw["endpoint"])
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", openai_raw["deployment"])
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", openai_raw["api_version"])
    api_key = os.getenv("AZURE_OPENAI_API_KEY", openai_raw["api_key"])
    push_to_sink = _parse_bool(os.getenv("OUTPUT_PUSH_TO_SINK"), output_raw["push_to_sink"])
    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME", storage_raw["account_name"])
    our_company_profile_blob_name = os.getenv(
        "OUR_COMPANY_PROFILE_BLOB_NAME",
        context_raw["our_company_profile_blob_name"],
    )

    return AppConfig(
        environment=app_raw["environment"],
        log_level=app_raw["log_level"],
        storage_account_name=storage_account_name,
        source_storage=SourceStorageConfig(
            container_name=storage_raw["source_container_name"],
            company_metadata_file_name=storage_raw["company_metadata_file_name"],
            indicator_file_name=storage_raw["indicator_file_name"],
        ),
        sink_storage=SinkStorageConfig(
            container_name=storage_raw["sink_container_name"],
        ),
        additional_info_storage=AdditionalInfoConfig(
            enabled=storage_raw["additional_company_info_enabled"],
            container_name=storage_raw["additional_container_name"],
        ),
        prompt_storage=PromptStorageConfig(
            container_name=storage_raw["prompts_container_name"],
        ),
        function_definition_storage=FunctionDefinitionStorageConfig(
            container_name=storage_raw["function_definitions_container_name"],
        ),
        openai=OpenAIConfig(
            endpoint=endpoint,
            deployment=deployment,
            api_version=api_version,
            api_key=api_key,
            max_tokens=openai_raw["max_tokens"],
            temperature=openai_raw["temperature"],
            reasoning_model=_parse_bool(
                os.getenv("AZURE_OPENAI_REASONING_MODEL"),
                openai_raw.get("reasoning_model", False),
            ),
            reasoning_effort=os.getenv(
                "AZURE_OPENAI_REASONING_EFFORT",
                openai_raw.get("reasoning_effort", "medium"),
            ),
        ),
        our_company_profile_blob_name=our_company_profile_blob_name,
        context_fields=context_raw["company_fields"],
        research_agent=AgentConfig(
            name=agents_raw["research"]["name"],
            system_prompt_blob_name=agents_raw["research"]["system_prompt_blob_name"],
            enable_web_search=agents_raw["research"]["enable_web_search"],
        ),
        strategy_agent=AgentConfig(
            name=agents_raw["strategy"]["name"],
            system_prompt_blob_name=agents_raw["strategy"]["system_prompt_blob_name"],
            enable_web_search=agents_raw["strategy"]["enable_web_search"],
        ),
        function_call=FunctionCallConfig(
            definition_blob_name=function_call_raw["definition_blob_name"],
            enforce_single_tool_call=function_call_raw["enforce_single_tool_call"],
        ),
        output=OutputConfig(
            push_to_sink=push_to_sink,
            local_output_dir=_resolve_path(output_raw["local_output_dir"], project_root),
            file_name=output_raw["file_name"],
            append_utc_timestamp_to_sink_file_name=output_raw.get(
                "append_utc_timestamp_to_sink_file_name",
                True,
            ),
        ),
    )
