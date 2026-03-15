from __future__ import annotations

from typing import Any


def create_agent_compat(responses_client: object, **kwargs: Any) -> object:
    create_agent = getattr(responses_client, "create_agent", None)
    if callable(create_agent):
        return create_agent(**kwargs)

    as_agent = getattr(responses_client, "as_agent", None)
    if callable(as_agent):
        return as_agent(**kwargs)

    raise AttributeError("Responses client does not expose create_agent or as_agent.")
