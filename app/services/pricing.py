from __future__ import annotations

from typing import Any


def parse_int_price(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def parse_shipping_fee(raw: dict | None) -> int:
    if not raw or not isinstance(raw, dict):
        return 0
    value = raw.get("shippingFee")
    if value is None:
        value = raw.get("shipping_fee")
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        digits = "".join(c for c in value.strip() if c.isdigit())
        if digits:
            return int(digits)
    return 0


def calculate_selling_price(cost: int, margin_rate: float, shipping_fee: int) -> int:
    safe_cost = max(0, int(cost or 0))
    safe_margin_rate = max(0.0, float(margin_rate or 0.0))
    safe_shipping_fee = max(0, int(shipping_fee or 0))

    margin_amount = int(safe_cost * safe_margin_rate)
    total = safe_cost + margin_amount + safe_shipping_fee
    if total <= 0:
        return 0
    return ((total + 99) // 100) * 100
