from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models import MarketListing, Product
from app.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_COUPANG_ALLOWED_REQUIRED_DOC_TEMPLATES = [
    "유통경로확인서",
    "상표권사용동의서",
    "브랜드소명자료",
    "브랜드확인서",
]

DEFAULT_COUPANG_BLOCKED_REQUIRED_DOC_KEYWORDS = [
    "KC",
    "KC인증서",
    "전기",
    "전기안전인증",
    "어린이제품안전",
    "어린이제품안전확인",
    "식품위생법",
    "건강기능식품",
    "의료",
    "의료기기",
    "안전인증",
    "방송통신기자재",
    "적합등록",
    "시험성적서",
]
DEFAULT_COUPANG_NEVER_REQUIRED_DOC_TEMPLATES = [
    "UN 38.3 Test Report",
    "MSDS Test Report",
    "MANDATORY INGREDIENTS PIC",
]

DEFAULT_COUPANG_BLOCKED_CATEGORY_KEYWORDS = [
    "전기",
    "전자",
    "식품",
    "유아",
    "의료",
    "화장품",
]
DEFAULT_COUPANG_BLOCKED_CATEGORY_CODES = [
    "77800",
]

class SkipCoupangRegistrationError(Exception):
    """상품 등록을 정책상 건너뛰는 경우 사용."""

class CoupangDocumentPendingError(SkipCoupangRegistrationError):
    def __init__(self, reason: str, missing_templates: list[str] | None = None):
        super().__init__(reason)
        self.missing_templates = missing_templates or []

class CoupangNeverEligibleError(SkipCoupangRegistrationError):
    """쿠팡 등록을 영구적으로 제외하는 경우."""

def _get_document_library_entry(
    session: Session,
    brand: str | None,
    template_name: str | None,
) -> dict[str, Any] | None:
    from app.models import CoupangDocumentLibrary
    if not brand or not template_name:
        return None
    row = (
        session.query(CoupangDocumentLibrary)
        .filter(func.lower(CoupangDocumentLibrary.brand) == brand.strip().lower())
        .filter(func.lower(CoupangDocumentLibrary.template_name) == template_name.strip().lower())
        .filter(CoupangDocumentLibrary.is_active.is_(True))
        .first()
    )
    if not row or not row.vendor_document_path:
        return None
    return {
        "templateName": row.template_name,
        "vendorDocumentPath": row.vendor_document_path,
    }

def check_coupang_fallback_ratio(session: Session, account_id: uuid.UUID) -> bool:

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_count = session.execute(
        select(func.count(MarketListing.id))
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.linked_at >= today_start)
    ).scalar() or 0
    if total_count < 20:
        return False
    fallback_count = session.execute(
        select(func.count(MarketListing.id))
        .join(Product, MarketListing.product_id == Product.id)
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.linked_at >= today_start)
        .where(Product.coupang_fallback_used == True)
    ).scalar() or 0
    ratio = fallback_count / total_count
    logger.info(f"Coupang Fallback Ratio: {ratio:.2f} (Total: {total_count}, Fallback: {fallback_count})")
    return ratio >= settings.coupang_fallback_ratio_threshold

def check_coupang_daily_limit(session: Session, account_id: uuid.UUID) -> bool:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_count = session.execute(
        select(func.count(MarketListing.id))
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.linked_at >= today_start)
    ).scalar() or 0
    return total_count >= settings.coupang_daily_limit

def check_fallback_cooldown(session: Session, account_id: uuid.UUID, category_code: str) -> bool:
    days = settings.coupang_fallback_cooldown_days
    threshold = settings.coupang_fallback_cooldown_threshold
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    count = session.execute(
        select(func.count(MarketListing.id))
        .join(Product, MarketListing.product_id == Product.id)
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.linked_at >= start_date)
        .where(MarketListing.category_code == category_code)
        .where(Product.coupang_fallback_used == True)
    ).scalar() or 0
    if count >= threshold:
        logger.warning(f"Fallback 카테고리 {category_code} 사용량 초과 ({count} >= {threshold}). 쿨다운 진입.")
        return True
    return False

def _lookup_proven_payload_template(session: Session, category_code: int) -> tuple[dict, str] | tuple[None, None]:
    stmt_exact = (
        select(MarketListing.proven_payload, MarketListing.category_grade)
        .where(MarketListing.category_code == str(category_code))
        .where(MarketListing.category_grade == "VERIFIED_EXACT")
        .where(MarketListing.proven_payload != None)
        .order_by(MarketListing.linked_at.desc())
        .limit(1)
    )
    result = session.execute(stmt_exact).first()
    if result:
        return result[0], result[1] or "VERIFIED_EXACT"
    stmt_fallback = (
        select(MarketListing.proven_payload, MarketListing.category_grade)
        .where(MarketListing.category_code == str(category_code))
        .where(MarketListing.proven_payload != None)
        .order_by(MarketListing.linked_at.desc())
        .limit(1)
    )
    result = session.execute(stmt_fallback).first()
    if result:
        return result[0], result[1] or "FALLBACK_SAFE"
    return None, None

def _parse_env_list(env_key: str) -> list[str]:
    raw = os.getenv(env_key, "")
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]

def _normalize_tokens(values: list[str]) -> list[str]:
    return [str(v).strip().lower() for v in values if str(v).strip()]

def _match_any(text: str, keywords: list[str]) -> bool:
    target = str(text or "").lower()
    return any(keyword in target for keyword in keywords if keyword)

def _extract_required_doc_templates(notice_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(notice_meta, dict):
        return []
    docs = notice_meta.get("requiredDocumentNames")
    if not isinstance(docs, list):
        return []
    return [doc for doc in docs if isinstance(doc, dict)]

def _required_doc_applies(required_flag: str, product: Product) -> bool:
    flag = str(required_flag or "")
    if not flag:
        return False
    if flag == "OPTIONAL":
        return False
    if flag == "MANDATORY":
        return True
    if flag.startswith("MANDATORY_PARALLEL_IMPORTED"):
        return bool(getattr(product, "coupang_parallel_imported", False))
    if flag.startswith("MANDATORY_OVERSEAS_PURCHASED"):
        return bool(getattr(product, "coupang_overseas_purchased", False))
    if "BATTERY" in flag:
        name = (product.name or "").lower()
        if any(kw in name for kw in ["battery", "배터리", "리튬", "lithium"]):
            return True
        return False
    if "INGREDIENTS" in flag:
        name = (product.name or "").lower()
        if any(kw in name for kw in ["식품", "화장품", "원료", "성분", "ingredient"]):
            return True
        return False
    if flag.startswith("MANDATORY"):
        return True
    return False

def _cert_required_applies(required_flag: str, product: Product) -> bool:
    return _required_doc_applies(required_flag, product)

def score_category_safety(meta: dict[str, Any] | None, product: Product) -> tuple[int, list[str]]:
    if not isinstance(meta, dict):
        return 0, []
    reasons: list[str] = []
    score = 0
    required_docs = _extract_required_doc_templates(meta)
    required_templates: list[str] = []
    for doc in required_docs:
        required_flag = doc.get("required") or ""
        if not _required_doc_applies(str(required_flag), product):
            continue
        name = doc.get("templateName") or doc.get("documentName") or ""
        if name:
            required_templates.append(str(name))
    blocked_keywords = _parse_env_list("COUPANG_BLOCKED_REQUIRED_DOCUMENTS") or DEFAULT_COUPANG_BLOCKED_REQUIRED_DOC_KEYWORDS
    allowed_templates = _parse_env_list("COUPANG_ALLOWED_REQUIRED_DOCUMENTS") or DEFAULT_COUPANG_ALLOWED_REQUIRED_DOC_TEMPLATES
    blocked_tokens = _normalize_tokens(blocked_keywords)
    allowed_tokens = _normalize_tokens(allowed_templates)
    for name in required_templates:
        if _match_any(name, blocked_tokens):
            score -= 100
            reasons.append(f"blocked_template:{name}")
    if required_templates and not reasons:
        if all(str(name).strip().lower() in allowed_tokens for name in required_templates):
            score += 10
            reasons.append("allowed_templates_only")
    certifications = meta.get("certifications")
    if isinstance(certifications, list):
        for cert in certifications:
            if not isinstance(cert, dict):
                continue
            required_flag = cert.get("required") or ""
            if _cert_required_applies(str(required_flag), product):
                score -= 100
                cert_type = cert.get("certificationType") or cert.get("name") or "certification"
                reasons.append(f"mandatory_cert:{cert_type}")
    return score, reasons

def _needs_heavy_docs(meta: dict[str, Any] | None) -> bool:
    """
    카테고리 메타데이터를 분석하여 까다로운 구비서류(인증 등)가 필요한지 판단합니다.
    """
    if not meta:
        return False
    
    docs = meta.get("requiredDocumentNames", [])
    if not isinstance(docs, list):
        docs = []
        
    heavy_doc_keywords = ["MSDS", "UN38.3", "전기용품", "의료기기", "건강기능식품", "전파법", "어린이", "안전확인", "부적합"]
    for d in docs:
        if not isinstance(d, dict):
            continue
        if d.get("required") == "MANDATORY":
            doc_name = d.get("documentName", "")
            if any(kw in doc_name for kw in heavy_doc_keywords):
                return True
    
    # attributes(인증정보 등) 체크
    attrs = meta.get("attributes")
    if isinstance(attrs, list):
        for a in attrs:
            if not isinstance(a, dict):
                continue
            if a.get("required") == "MANDATORY":
                attr_name = a.get("attributeTypeName", "")
                if any(kw in attr_name for kw in ["인증", "KC", "어린이", "전기", "전파"]):
                    return True
    
    # certifications 체크
    certs = meta.get("certifications")
    if isinstance(certs, list):
        for c in certs:
            if not isinstance(c, dict):
                continue
            if c.get("required") in ["MANDATORY", "RECOMMEND"]:
                return True
                
    return False
