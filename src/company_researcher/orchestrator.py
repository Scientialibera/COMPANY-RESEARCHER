from __future__ import annotations

from .blob_storage import BlobStorageGateway
from .config import load_app_config
from .models import ProcessRequest, ProcessResult
from .workflow.two_agent_workflow import TwoAgentWorkflow


async def process_company_folder(company_folder: str) -> ProcessResult:
    config = load_app_config()
    storage = BlobStorageGateway(config=config)
    workflow = TwoAgentWorkflow(config=config, storage=storage)
    request = ProcessRequest(company_folder=company_folder)
    return await workflow.run(request)
