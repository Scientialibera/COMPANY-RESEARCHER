from __future__ import annotations

from typing import Any

def validate_sales_strategy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    revenue_class = payload.get("revenue_class")
    sales_pitch = payload.get("sales_pitch")

    valid_revenue = {
        "less_than_500_m",
        "between_500_m_and_5_b",
        "more_than_5_b",
    }
    if revenue_class not in valid_revenue:
        raise ValueError("Invalid revenue_class returned by function call.")

    if not isinstance(sales_pitch, list) or len(sales_pitch) != 5:
        raise ValueError("sales_pitch must contain exactly 5 ideas.")

    if any(not isinstance(item, str) or not item.strip() for item in sales_pitch):
        raise ValueError("Each sales_pitch item must be a non-empty string.")

    return {
        "revenue_class": revenue_class,
        "sales_pitch": sales_pitch,
    }
