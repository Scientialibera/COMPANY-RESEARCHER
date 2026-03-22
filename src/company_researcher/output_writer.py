from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .blob_storage import BlobStorageGateway
from .models import AppConfig


def _timestamped_file_name(file_name: str) -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    base_path = Path(file_name)
    if base_path.suffix:
        return f"{base_path.stem}_{stamp}{base_path.suffix}"
    return f"{file_name}_{stamp}"


def build_result_payload(
    company_folder: str,
    research_report: str,
    classification_payload: dict[str, Any],
    reasoning: dict[str, list[str]] | None = None,
) -> str:
    document: dict[str, Any] = {
        "company_folder": company_folder,
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "research_report": research_report,
        "function_result": classification_payload,
    }
    if reasoning is not None:
        document["reasoning"] = reasoning
    return json.dumps(document, indent=2, ensure_ascii=True)


def write_result(
    config: AppConfig,
    storage: BlobStorageGateway,
    company_folder: str,
    payload_json: str,
) -> str:
    file_name = config.output.file_name
    if config.output.push_to_sink and config.output.append_utc_timestamp_to_sink_file_name:
        file_name = _timestamped_file_name(file_name)
    blob_name = f"{company_folder}/{file_name}"

    if config.output.push_to_sink:
        return storage.upload_result_to_sink(blob_name, payload_json)

    output_dir = Path(config.output.local_output_dir) / company_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / file_name
    output_file.write_text(payload_json, encoding="utf-8")
    return str(output_file)
