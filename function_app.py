from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import azure.functions as func
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from company_researcher.config import load_app_config
from company_researcher.orchestrator import process_company_folder

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _extract_folder_from_blob_name(blob_name: str) -> str:
    parts = blob_name.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot infer company folder from blob name: {blob_name}")
    if len(parts) >= 3:
        return parts[1]
    return parts[0]


def _blob_name_from_event(subject: str, data_url: str) -> str:
    # Storage Event Grid subject format:
    # /blobServices/default/containers/<container>/blobs/<blob path>
    marker = "/blobs/"
    if marker in subject:
        return subject.split(marker, 1)[1]

    if data_url:
        parsed = urlparse(data_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return "/".join(parts[1:])
    raise ValueError("Could not determine blob name from Event Grid payload.")


def _extract_folder_from_url(folder_url: str) -> str:
    parsed = urlparse(folder_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("folder_url must include container and folder segments.")
    return parts[1]


async def _enqueue_indicator_blob(company_folder: str) -> str:
    config = load_app_config()
    normalized_folder = company_folder.strip().strip("/")
    if not normalized_folder:
        raise ValueError("company_folder cannot be empty.")

    blob_name = f"{normalized_folder}/{config.source_storage.indicator_file_name}"
    account_url = f"https://{config.storage_account_name}.blob.core.windows.net"
    payload = json.dumps(
        {
            "source": "manual-http",
            "queued_at_utc": datetime.now(tz=UTC).isoformat(),
            "company_folder": normalized_folder,
        },
        ensure_ascii=True,
    ).encode("utf-8")

    credential = DefaultAzureCredential()
    try:
        service = BlobServiceClient(account_url=account_url, credential=credential)
        async with service:
            blob = service.get_blob_client(
                container=config.source_storage.container_name,
                blob=blob_name,
            )
            await blob.upload_blob(payload, overwrite=True)
    finally:
        await credential.close()

    return f"{account_url}/{config.source_storage.container_name}/{blob_name}"


@app.function_name(name="CompanyResearchBlobTrigger")
@app.event_grid_trigger(arg_name="event")
async def company_research_blob_trigger(event: func.EventGridEvent) -> None:
    config = load_app_config()
    event_data = event.get_json() or {}
    blob_name = _blob_name_from_event(subject=event.subject or "", data_url=event_data.get("url", ""))
    company_folder = _extract_folder_from_blob_name(blob_name)
    indicator_name = blob_name.split("/")[-1]

    if indicator_name != config.source_storage.indicator_file_name:
        logging.info("Skipping non-indicator blob: %s", blob_name)
        return

    result = await process_company_folder(company_folder)
    logging.info("Processed company folder '%s' => %s", company_folder, result.output_uri)


@app.function_name(name="CompanyResearchManual")
@app.route(route="manual-process", methods=["POST"])
async def company_research_manual(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() if req.get_body() else {}
    except ValueError:
        body = {}

    company_folder = req.params.get("company_folder") or body.get("company_folder")
    folder_url = req.params.get("folder_url") or body.get("folder_url")

    if not company_folder and folder_url:
        company_folder = _extract_folder_from_url(folder_url)

    if not company_folder:
        return func.HttpResponse(
            "Provide company_folder or folder_url in query/body.",
            status_code=400,
        )

    queued_blob_uri = await _enqueue_indicator_blob(company_folder)
    payload = {
        "status": "accepted",
        "message": "Request queued. Blob trigger will process in background.",
        "company_folder": company_folder.strip().strip("/"),
        "queued_indicator_blob_uri": queued_blob_uri,
    }
    return func.HttpResponse(
        body=json.dumps(payload, indent=2, ensure_ascii=True),
        mimetype="application/json",
        status_code=202,
    )
