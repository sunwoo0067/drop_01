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

def calculate_selling_price(cost: int, margin_rate: float, shipping_fee: int, market_fee_rate: float = 0.13) -> int:
    safe_cost = max(0, int(cost or 0))
    safe_margin_rate = max(0.0, float(margin_rate or 0.0))
    safe_shipping_fee = max(0, int(shipping_fee or 0))
    safe_market_fee_rate = max(0.0, min(0.99, float(market_fee_rate or 0.13)))

    # 합계 = 공급가 + 마진액 + 배송비
    margin_amount = int(safe_cost * safe_margin_rate)
    base_total = safe_cost + margin_amount + safe_shipping_fee
    
    if base_total <= 0:
        return 0
        
    # 수수료 반영: 최종가격 = 합계 / (1 - 수수료율)
    final_total = base_total / (1 - safe_market_fee_rate)
    
    # 100원 단위 올림 (14,501 -> 14,600)
    return ((int(final_total) + 99) // 100) * 100
