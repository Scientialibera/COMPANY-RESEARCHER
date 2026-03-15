from __future__ import annotations

import json


def build_company_context(company_payload: dict, selected_fields: list[str]) -> str:
    selected = {field: company_payload.get(field) for field in selected_fields}
    return json.dumps(selected, indent=2, ensure_ascii=True)


def build_additional_context(files: list[dict[str, str]]) -> str:
    if not files:
        return "No additional company files provided."

    parts: list[str] = []
    for item in files:
        parts.append(f"File: {item['blob_name']}\n{item['content']}")
    return "\n\n".join(parts)
