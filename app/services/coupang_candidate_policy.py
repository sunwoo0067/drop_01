from __future__ import annotations

import os
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Product
from app.services.market_targeting import resolve_supplier_category_name


DEFAULT_COUPANG_NEVER_KEYWORDS = [
    "battery",
    "lithium",
    "충전",
    "전지",
    "리튬",
    "액상",
    "용액",
    "젤",
    "스프레이",
    "화학",
    "세정",
    "향료",
    "방향제",
    "성분",
    "원료",
    "msds",
    "안전자료",
    "어린이",
    "유아",
    "baby",
    "kids",
]

DEFAULT_COUPANG_CANDIDATE_KEYWORDS = [
    "의류",
    "패션",
    "침구",
    "패브릭",
    "인테리어소품",
    "문구",
    "사무용품",
    "생활잡화",
]


def _parse_env_list(env_key: str) -> list[str]:
    raw = os.getenv(env_key, "")
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _normalize_tokens(values: Iterable[str]) -> list[str]:
    return [str(v).strip().lower() for v in values if str(v).strip()]


def _match_any(text: str, keywords: list[str]) -> bool:
    target = str(text or "").lower()
    return any(keyword in target for keyword in keywords if keyword)


def decide_coupang_eligibility(session: Session, product: Product) -> tuple[str, list[str]]:
    never_keywords = _parse_env_list("COUPANG_NEVER_KEYWORDS") or DEFAULT_COUPANG_NEVER_KEYWORDS
    candidate_keywords = _parse_env_list("COUPANG_CANDIDATE_KEYWORDS") or DEFAULT_COUPANG_CANDIDATE_KEYWORDS

    never_tokens = _normalize_tokens(never_keywords)
    candidate_tokens = _normalize_tokens(candidate_keywords)

    texts: list[str] = []
    for value in (product.processed_name, product.name, product.description):
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())

    category_name = resolve_supplier_category_name(session, product)
    if isinstance(category_name, str) and category_name.strip():
        texts.append(category_name.strip())

    for text in texts:
        if _match_any(text, never_tokens):
            return "NEVER", ["keyword_never"]

    for text in texts:
        if _match_any(text, candidate_tokens):
            return "CANDIDATE", ["keyword_candidate"]

    return "UNKNOWN", []
