from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from .models import AppConfig


@dataclass
class BlobStorageGateway:
    config: AppConfig

    def _account_url(self, account_name: str) -> str:
        return f"https://{account_name}.blob.core.windows.net"

    def _client(self, account_name: str) -> BlobServiceClient:
        credential = DefaultAzureCredential()
        return BlobServiceClient(
            account_url=self._account_url(account_name),
            credential=credential,
        )

    def _read_blob_text(self, account_name: str, container_name: str, blob_name: str) -> str:
        client = self._client(account_name)
        blob = client.get_blob_client(container=container_name, blob=blob_name)
        return blob.download_blob().readall().decode("utf-8-sig")

    def read_company_metadata(self, company_folder: str) -> dict:
        blob_name = f"{company_folder}/{self.config.source_storage.company_metadata_file_name}"
        raw = self._read_blob_text(
            self.config.storage_account_name,
            self.config.source_storage.container_name,
            blob_name,
        )
        return json.loads(raw)

    def read_additional_company_info(self, company_folder: str) -> list[dict[str, str]]:
        if not self.config.additional_info_storage.enabled:
            return []

        client = self._client(self.config.storage_account_name)
        container = client.get_container_client(self.config.additional_info_storage.container_name)
        files: list[dict[str, str]] = []
        prefix = f"{company_folder}/"

        for blob in container.list_blobs(name_starts_with=prefix):
            blob_client = container.get_blob_client(blob.name)
            content = blob_client.download_blob().readall().decode("utf-8", errors="ignore")
            files.append({"blob_name": blob.name, "content": content})
        return files

    def read_our_company_profile(self) -> str:
        return self._read_blob_text(
            self.config.storage_account_name,
            self.config.additional_info_storage.container_name,
            self.config.our_company_profile_blob_name,
        )

    def read_prompt(self, blob_name: str) -> str:
        return self._read_blob_text(
            self.config.storage_account_name,
            self.config.prompt_storage.container_name,
            blob_name,
        )

    def read_function_definition(self, blob_name: str) -> dict:
        raw = self._read_blob_text(
            self.config.storage_account_name,
            self.config.function_definition_storage.container_name,
            blob_name,
        )
        return json.loads(raw)

    def upload_result_to_sink(self, blob_name: str, payload: str) -> str:
        sink = self.config.sink_storage
        client = self._client(self.config.storage_account_name)
        blob = client.get_blob_client(container=sink.container_name, blob=blob_name)
        blob.upload_blob(BytesIO(payload.encode("utf-8")), overwrite=True)
        return f"{self._account_url(self.config.storage_account_name)}/{sink.container_name}/{blob_name}"

