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
    "세정제",
    "락스",
    "소독",
    "향료",
    "향",
    "방향제",
    "화장품",
    "에센스",
    "크림",
    "오일",
    "성분",
    "원료",
    "msds",
    "안전자료",
    "어린이",
    "유아",
    "아동",
    "키즈",
    "베이비",
    "주니어",
    "baby",
    "kids",
    "junior",
]

DEFAULT_COUPANG_CANDIDATE_KEYWORDS = [
    "의류",
    "원피스",
    "니트",
    "티셔츠",
    "셔츠",
    "블라우스",
    "가디건",
    "자켓",
    "코트",
    "슬랙스",
    "팬츠",
    "스커트",
    "레깅스",
    "트레이닝",
    "후드",
    "맨투맨",
    "침구",
    "패브릭",
    "이불",
    "베개",
    "쿠션",
    "쿠션커버",
    "커튼",
    "러그",
    "담요",
    "패드",
]

DEFAULT_COUPANG_CANDIDATE_EXCLUDE_KEYWORDS = [
    "모자",
    "양말",
    "장갑",
    "머플러",
    "스카프",
    "벨트",
    "에코백",
    "가방",
    "파우치",
    "전동",
    "드릴",
    "임팩",
    "그라인더",
    "톱",
    "절단",
    "샌더",
    "공구",
    "툴",
    "툴백",
    "툴케이스",
    "공구함",
    "공구가방",
    "홀스터",
    "요가",
    "필라테스",
    "매트",
    "폼롤러",
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
    candidate_exclude_keywords = (
        _parse_env_list("COUPANG_CANDIDATE_EXCLUDE_KEYWORDS") or DEFAULT_COUPANG_CANDIDATE_EXCLUDE_KEYWORDS
    )

    never_tokens = _normalize_tokens(never_keywords)
    candidate_tokens = _normalize_tokens(candidate_keywords)
    candidate_exclude_tokens = _normalize_tokens(candidate_exclude_keywords)

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
        if _match_any(text, candidate_exclude_tokens):
            return "UNKNOWN", ["keyword_candidate_exclude"]

    for text in texts:
        if _match_any(text, candidate_tokens):
            return "CANDIDATE", ["keyword_candidate"]

    return "UNKNOWN", []
