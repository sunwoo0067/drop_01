import os
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, SupplierItemRaw, CoupangBrandPolicy


DEFAULT_COUPANG_CATEGORY_ALLOW_KEYWORDS = [
    "의류",
    "패션잡화",
    "침구",
    "패브릭",
    "인테리어소품",
    "문구",
    "사무용품",
    "생활잡화",
    "캠핑용품",
]

DEFAULT_COUPANG_CATEGORY_DENY_KEYWORDS = [
    "전기용품",
    "전자기기",
    "가전",
    "식품",
    "건강식품",
    "유아",
    "아동",
    "의료",
    "의료기기",
    "화장품",
    "미용기기",
    "배터리",
    "충전기",
]


def _parse_env_list(env_key: str) -> list[str]:
    raw = os.getenv(env_key, "")
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    target = _normalize_text(text)
    return any(_normalize_text(keyword) in target for keyword in keywords if keyword)


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"y", "yes", "true", "1"}:
            return True
        if token in {"n", "no", "false", "0"}:
            return False
    return False


def resolve_trade_flags_from_raw(raw: dict[str, Any] | None) -> tuple[bool, bool]:
    if not isinstance(raw, dict):
        return False, False

    parallel_keys = [
        "parallelImported",
        "parallel_imported",
        "is_parallel_imported",
        "parallelImportedYn",
    ]
    overseas_keys = [
        "overseasPurchased",
        "overseas_purchased",
        "is_overseas_purchased",
        "overseasPurchasedYn",
    ]

    parallel_imported = False
    overseas_purchased = False

    for key in parallel_keys:
        if key in raw:
            parallel_imported = _parse_bool(raw.get(key))
            break

    for key in overseas_keys:
        if key in raw:
            overseas_purchased = _parse_bool(raw.get(key))
            break

    return parallel_imported, overseas_purchased


def resolve_supplier_category_name(session: Session, product: Product) -> str | None:
    if hasattr(product, "processed_category") and product.processed_category:
        return str(product.processed_category)
    if getattr(product, "category_path", None):
        return str(product.category_path)
    if getattr(product, "category_name", None):
        return str(product.category_name)

    if not product.supplier_item_id:
        return None

    raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
    if not raw_item or not isinstance(raw_item.raw, dict):
        return None

    raw: dict[str, Any] = raw_item.raw
    category = raw.get("category")
    if isinstance(category, str) and category.strip():
        return category.strip()
    if isinstance(category, dict):
        name = category.get("name") or category.get("categoryName")
        if isinstance(name, str) and name.strip():
            return name.strip()

    for key in ("category_name", "categoryName", "category_path", "categoryPath"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _is_unknown_category(category_name: str | None) -> bool:
    if not category_name:
        return True
    normalized = str(category_name).strip().lower()
    if not normalized:
        return True
    unknown_tokens = {"unknown", "n/a", "na", "none", "-", "null"}
    return normalized in unknown_tokens


def decide_target_market_by_category(category_name: str | None) -> tuple[str, str]:
    if _is_unknown_category(category_name):
        allow_prediction = os.getenv("COUPANG_PREDICT_ON_UNKNOWN", "1") == "1"
        if allow_prediction:
            return "COUPANG", "category_unknown_predict"
        return "SMARTSTORE", "no_category"

    allow_keywords = _parse_env_list("COUPANG_CATEGORY_ALLOW_KEYWORDS")
    deny_keywords = _parse_env_list("COUPANG_CATEGORY_DENY_KEYWORDS")

    if not allow_keywords:
        allow_keywords = DEFAULT_COUPANG_CATEGORY_ALLOW_KEYWORDS
    if not deny_keywords:
        deny_keywords = DEFAULT_COUPANG_CATEGORY_DENY_KEYWORDS

    if _contains_any(category_name, deny_keywords):
        return "SMARTSTORE", f"category_denied:{category_name}"

    if allow_keywords and not _contains_any(category_name, allow_keywords):
        return "SMARTSTORE", f"category_not_allowed:{category_name}"

    return "COUPANG", f"category_allowed:{category_name}"


def decide_target_market_for_product(session: Session, product: Product) -> tuple[str, str]:
    category_name = resolve_supplier_category_name(session, product)
    return decide_target_market_by_category(category_name)


def is_naver_fallback_disabled(session: Session, product: Product) -> bool:
    if getattr(product, "naver_fallback_disabled", False):
        return True
    brand = (product.brand or "").strip()
    if not brand:
        return False
    policy = (
        session.query(CoupangBrandPolicy)
        .filter(func.lower(CoupangBrandPolicy.brand) == brand.lower())
        .filter(CoupangBrandPolicy.is_active.is_(True))
        .first()
    )
    if policy and policy.naver_fallback_disabled:
        return True
    return False
