from __future__ import annotations

import logging
import re
import uuid
from typing import Any
from datetime import datetime, timedelta, timezone
import os
import time

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.coupang_client import CoupangClient
from app.models import (
    SupplierOrder,
    Order,
    OrderItem,
    OrderStatusHistory,
    MarketInquiryRaw,
    MarketRevenueRaw,
    MarketSettlementRaw,
    MarketReturnRaw,
    MarketExchangeRaw,
    Product,
    ProductOption,
    MarketAccount,
    CoupangDocumentLibrary,
    SupplierItemRaw,
    MarketOrderRaw,
    MarketProductRaw,
    SupplierRawFetchLog,
    MarketListing,
    CoupangCategoryMetaCache,
)
from app.ownerclan_client import OwnerClanClient
from app.ownerclan_sync import get_primary_ownerclan_account
from app.services.detail_html_checks import find_forbidden_tags, strip_forbidden_tags
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.coupang_ready_service import collect_image_urls_from_raw
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


def check_coupang_fallback_ratio(session: Session, account_id: uuid.UUID) -> bool:
    """
    오늘 쿠팡에 등록된 상품 중 Fallback 카테고리를 사용한 비율이 임계치를 넘었는지 확인합니다.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 총 등록 수
    total_count = session.execute(
        select(func.count(MarketListing.id))
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.linked_at >= today_start)
    ).scalar() or 0
    
    if total_count < 20: # 최소 20건 이상일 때부터 비율 체크 (운영 초기 안정성 확보)
        return False
        
    # Fallback 사용 수
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
    """
    오늘 쿠팡에 등록된 상품 총합이 일일 제한을 넘었는지 확인합니다.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_count = session.execute(
        select(func.count(MarketListing.id))
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.linked_at >= today_start)
    ).scalar() or 0
    
    return total_count >= settings.coupang_daily_limit


def check_fallback_cooldown(session: Session, account_id: uuid.UUID, category_code: str) -> bool:
    """
    최근 N일간 특정 우회 카테고리가 임계치 이상 사용되었는지 확인합니다.
    """
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
    """
    동일 카테고리에서 성공한 적이 있는 페이로드 템플릿을 조회합니다.
    VERIFIED_EXACT 등급을 우선하며, 없으면 FALLBACK_SAFE를 반환합니다.
    """
    # 1. VERIFIED_EXACT 우선 조회
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
    
    # 2. 없으면 FALLBACK_SAFE 조회
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
        # 배터리 관련 서류는 상품명에 배터리 키워드가 있을 때만 필수인 것으로 간주 (사전 필터링에서 이미 걸러졌어야 함)
        name = (product.name or "").lower()
        if any(kw in name for kw in ["battery", "배터리", "리튬", "lithium"]):
            return True
        return False
    if "INGREDIENTS" in flag:
        # 성분/원료 관련 서류는 관련 키워드가 있을 때만 필수
        name = (product.name or "").lower()
        if any(kw in name for kw in ["식품", "화장품", "원료", "성분", "ingredient"]):
            return True
        return False
    if flag.startswith("MANDATORY"):
        return True
    return False


def _cert_required_applies(required_flag: str, product: Product) -> bool:
    return _required_doc_applies(required_flag, product)


def _score_category_safety(meta: dict[str, Any] | None, product: Product) -> tuple[int, list[str]]:
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


def _get_document_library_entry(
    session: Session,
    brand: str | None,
    template_name: str | None,
) -> dict[str, Any] | None:
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

def _preserve_detail_html(product: Product | None = None) -> bool:
    """
    상품의 상태에 따라 상세페이지 HTML 보존 여부를 결정합니다.
    - 신규 가공 중(PENDING, PROCESSING)인 경우: 정규화/이미지 보강을 위해 False 반환 (변환 필요)
    - 이미 완료되었거나 등록된 경우: 기존 레이아웃 유지를 위해 True 반환
    """
    if product is None:
        return False
    
    # 신규 등록을 위한 가공 단계에서는 정규화 로직을 태웁니다.
    if product.processing_status in ("PENDING", "PROCESSING"):
        return False
        
    return True


def _name_only_processing() -> bool:
    return settings.product_processing_name_only


def _get_original_image_urls(session: Session, product: Product) -> list[str]:
    if product.supplier_item_id:
        raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
        raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
        return collect_image_urls_from_raw(raw)

    return []


def _normalize_detail_html_for_coupang(html: str) -> str:
    """
    쿠팡 상세페이지 HTML을 정규화합니다.
    - 모든 http:// 주소를 https://로 변환 (쿠팡 제약 사항)
    - 오너클랜 원본 데이터의 제어 문자 제거
    """
    s = str(html or "")
    if not s:
        return s

    # Coupang requires HTTPS for all content
    s = s.replace("http://", "https://")
    
    # Remove hidden control characters often found in source data
    s = normalize_ownerclan_html(s)
    
    # Strip forbidden tags (script, iframe, etc.)
    s = strip_forbidden_tags(s)
    
    return s


def _build_coupang_detail_html_from_processed_images(urls: list[str]) -> str:
    safe_urls: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        s = u.strip()
        if not s:
            continue
        s = _normalize_detail_html_for_coupang(s)
        if s in seen:
            continue
        seen.add(s)
        safe_urls.append(s)
        if len(safe_urls) >= 20:
            break

    parts: list[str] = []
    for u in safe_urls:
        parts.append(f'<img src="{u}" style="max-width:100%;height:auto;"> <br>')

    parts.append(
        '<p style="font-size: 12px; color: #777777; display: block; margin: 20px 0;">'
        '본 제품을 구매하시면 원활한 배송을 위해 꼭 필요한 고객님의 개인정보를 (성함, 주소, 전화번호 등)  '
        '택배사 및 제 3업체에서 이용하는 것에 동의하시는 것으로 간주됩니다.<br>'
        '개인정보는 배송 외의 용도로는 절대 사용되지 않으니 안심하시기 바랍니다. 안전하게 배송해 드리겠습니다.'
        '</p>'
    )

    out = " ".join(parts).strip()
    return out[:200000]


def _build_contents_image_blocks(urls: list[str]) -> list[dict[str, Any]]:
    safe_urls: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        s = u.strip()
        if not s:
            continue
        s = _normalize_detail_html_for_coupang(s)
        if s in seen:
            continue
        seen.add(s)
        safe_urls.append(s)
        if len(safe_urls) >= 20:
            break

    if not safe_urls:
        return []

    return [
        {
            "contentsType": "IMAGE_NO_SPACE",
            "contentDetails": [{"content": u, "detailType": "IMAGE"} for u in safe_urls],
        }
    ]


def _detail_html_has_images(html: str) -> bool:
    if not html:
        return False
    return re.search(r"<img\b", html, re.IGNORECASE) is not None


def _extract_coupang_image_url(image_obj: dict[str, Any]) -> str | None:
    if not isinstance(image_obj, dict):
        return None

    def _build_coupang_cdn_url(path: str) -> str:
        s = str(path or "").strip()
        if not s:
            return s
        if s.startswith("http://") or s.startswith("https://") or s.startswith("//"):
            return _normalize_detail_html_for_coupang(s)
        s = s.lstrip("/")
        if s.startswith("image/"):
            return "https://image1.coupangcdn.com/" + s
        return "https://image1.coupangcdn.com/image/" + s

    vendor_path = image_obj.get("vendorPath")
    if isinstance(vendor_path, str) and vendor_path.strip():
        vp = vendor_path.strip()
        if vp.startswith("http://") or vp.startswith("https://") or vp.startswith("//"):
            return _normalize_detail_html_for_coupang(vp)
        if "/" in vp:
            return _build_coupang_cdn_url(vp)

    cdn_path = image_obj.get("cdnPath")
    if isinstance(cdn_path, str) and cdn_path.strip():
        return _build_coupang_cdn_url(cdn_path.strip())

    return None


def _get_client_for_account(account: MarketAccount) -> CoupangClient:
    creds = account.credentials
    if not creds:
        raise ValueError(f"Account {account.name} has no credentials")
    
    access_key = str(creds.get("access_key", "") or "").strip()
    secret_key = str(creds.get("secret_key", "") or "").strip()
    vendor_id = str(creds.get("vendor_id", "") or "").strip()

    return CoupangClient(
        access_key=access_key,
        secret_key=secret_key,
        vendor_id=vendor_id,
    )


def sync_coupang_products(session: Session, account_id: uuid.UUID, deep: bool = False) -> int:
    """
    Syncs products for a specific Coupang account.
    Returns the number of products processed.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        logger.error(f"MarketAccount {account_id} not found")
        return 0

    if account.market_code != "COUPANG":
        logger.error(f"Account {account.name} is not a Coupang account")
        return 0

    if not account.is_active:
        logger.info(f"Account {account.name} is inactive, skipping sync")
        return 0

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"Failed to initialize client for {account.name}: {e}")
        return 0

    logger.info(f"Starting product sync for {account.name} ({account.market_code})")

    total_processed = 0
    next_token = None

    while True:
        code, data = client.get_products(
            next_token=next_token,
            max_per_page=50,
        )
        _log_fetch(session, account, "get_products", {"nextToken": next_token}, code, data)

        if code != 200:
            logger.error(f"Failed to fetch products for {account.name}: {data}")
            break

        products = data.get("data", []) if isinstance(data, dict) else []
        if not products:
            break

        for p in products:
            if not isinstance(p, dict):
                continue
            seller_product_id = str(p.get("sellerProductId"))
            status_name = str(p.get("statusName") or "")
            
            if deep:
                detail_code, detail_data = client.get_product(seller_product_id)
                _log_fetch(session, account, f"get_product/{seller_product_id}", {}, detail_code, detail_data)
                detail_obj = detail_data.get("data") if isinstance(detail_data, dict) else None
                if detail_code == 200 and isinstance(detail_obj, dict):
                    p = detail_obj
                    status_name = str(p.get("statusName") or "")

            # MarketProductRaw 저장 (기존 로직 유지)
            existing_row = session.execute(
                select(MarketProductRaw)
                .where(MarketProductRaw.market_code == "COUPANG")
                .where(MarketProductRaw.account_id == account.id)
                .where(MarketProductRaw.market_item_id == seller_product_id)
            ).scalars().first()
            
            if existing_row and isinstance(existing_row.raw, dict):
                existing_status = (existing_row.raw.get("status") or "").strip().upper()
                existing_name = str(existing_row.raw.get("statusName") or "")
                if existing_status == "SUSPENDED" or "판매중지" in existing_name:
                    p = {**p, "status": "SUSPENDED", "statusName": "판매중지"}

            stmt = insert(MarketProductRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                market_item_id=seller_product_id,
                raw=p,
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "market_item_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
            )
            session.execute(stmt)

            # MarketListing 상태 연동 및 반려 사유 기록
            listing = session.execute(
                select(MarketListing)
                .where(MarketListing.market_account_id == account.id)
                .where(MarketListing.market_item_id == seller_product_id)
            ).scalars().first()
            
            if listing:
                # 상태 정규화
                normalized_status = None
                s_upper = status_name.upper()
                if "반려" in status_name or s_upper == "DENIED":
                    normalized_status = "DENIED"
                elif "승인완료" in status_name or s_upper == "APPROVED":
                    normalized_status = "ACTIVE"
                elif "심사중" in status_name or s_upper == "IN_REVIEW":
                    normalized_status = "IN_REVIEW"
                elif "승인대기" in status_name or s_upper == "APPROVING":
                    normalized_status = "APPROVING"
                
                if normalized_status:
                    listing.coupang_status = status_name # 원본 상태명 저장
                    if normalized_status == "ACTIVE":
                        listing.status = "ACTIVE"
                    elif normalized_status == "DENIED":
                        listing.status = "DENIED"
                    
                # 승인 반려 시 상세 사유 동기화 (deep이 아니더라도 반려 시에는 상세 조회 수행)
                if "반려" in status_name or s_upper == "DENIED":
                    # 이미 사유가 기록되어 있고 상태가 같다면 중복 조회 방지 (선택 사항)
                    sync_market_listing_status(session, listing.id)

        session.commit()
        total_processed += len(products)

        next_token = data.get("nextToken") if isinstance(data, dict) else None
        if not next_token:
            break

    logger.info(f"Finished product sync for {account.name}. Total: {total_processed}")
    return total_processed


def delete_market_listing(session: Session, account_id: uuid.UUID, market_item_id: str) -> tuple[bool, str | None]:
    """
    쿠팡 마켓에서 상품을 삭제하고 DB 상태를 업데이트합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, "계정을 찾을 수 없습니다"

    listing = (
        session.query(MarketListing)
        .filter(MarketListing.market_account_id == account_id)
        .filter(MarketListing.market_item_id == market_item_id)
        .first()
    )

    try:
        client = _get_client_for_account(account)
        code, data = client.delete_product(market_item_id)
        _log_fetch(session, account, f"delete_product/{market_item_id}", {}, code, data)

        if code == 200:
            if listing:
                listing.status = "DELETED"
                listing.coupang_status = "DELETED"
                session.commit()
            return True, None
        else:
            # 삭제 실패 시 판매 중지라도 시도
            logger.info(f"Deletion failed for {market_item_id} (Code: {code}), attempting to stop sales instead.")
            return stop_sales_on_coupang(session, account_id, market_item_id)
    except Exception as e:
        logger.error(f"Error deleting product {market_item_id}: {e}")
        return False, str(e)


def stop_sales_on_coupang(session: Session, account_id: uuid.UUID, market_item_id: str) -> tuple[bool, str | None]:
    """
    쿠팡 상품의 모든 아이템에 대해 판매 중지 처리를 수행합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, "계정을 찾을 수 없습니다"

    listing = (
        session.query(MarketListing)
        .filter(MarketListing.market_account_id == account_id)
        .filter(MarketListing.market_item_id == market_item_id)
        .first()
    )

    try:
        client = _get_client_for_account(account)
        # 먼저 상품 정보를 조회하여 vendorItemId 확보
        code, data = client.get_product(market_item_id)
        if code != 200:
            return False, f"조회 실패: {data.get('message')}"

        items = data.get("data", {}).get("items", [])
        success_count = 0
        for item in items:
            v_id = str(item.get("vendorItemId"))
            s_code, s_data = client.stop_sales(v_id)
            if s_code == 200:
                success_count += 1
            _log_fetch(session, account, f"stop_sales/{v_id}", {}, s_code, s_data)

        if success_count > 0:
            if listing:
                listing.status = "SUSPENDED"
                listing.coupang_status = "STOP_SALES"
                session.commit()
            return True, None
        
        return False, "판매 중지 처리된 아이템이 없습니다"
    except Exception as e:
        logger.error(f"Error stopping sales for {market_item_id}: {e}")
        return False, str(e)

def _extract_tracking_from_ownerclan_raw(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    if not isinstance(raw, dict):
        return None, None

    tracking_no = raw.get("trackingNumber") or raw.get("tracking_number")
    shipping_code = raw.get("shippingCompanyCode") or raw.get("shipping_company_code")
    if tracking_no:
        return str(tracking_no).strip(), str(shipping_code).strip() if shipping_code else None

    products = raw.get("products")
    if not isinstance(products, list) or not products:
        return None, None

    for item in products:
        if not isinstance(item, dict):
            continue
        tracking_no = item.get("trackingNumber") or item.get("tracking_number")
        shipping_code = item.get("shippingCompanyCode") or item.get("shipping_company_code")
        if tracking_no:
            return str(tracking_no).strip(), str(shipping_code).strip() if shipping_code else None

    return None, None


def _extract_coupang_order_id(raw: dict[str, Any]) -> str | None:
    if not isinstance(raw, dict):
        return None

    order_id = raw.get("orderId") or raw.get("order_id")
    if order_id:
        return str(order_id).strip()

    order_items = raw.get("orderItems") if isinstance(raw.get("orderItems"), list) else []
    for item in order_items:
        if not isinstance(item, dict):
            continue
        order_id = item.get("orderId") or item.get("order_id")
        if order_id:
            return str(order_id).strip()

    order_sheet_id = raw.get("orderSheetId") or raw.get("shipmentBoxId") or raw.get("order_sheet_id")
    if order_sheet_id:
        return str(order_sheet_id).strip()

    return None


def _already_uploaded_invoice(
    session: Session,
    account_id: uuid.UUID,
    order_id: str,
    invoice_number: str,
) -> bool:
    if not order_id or not invoice_number:
        return False

    stmt = (
        select(SupplierRawFetchLog)
        .where(SupplierRawFetchLog.supplier_code == "coupang")
        .where(SupplierRawFetchLog.account_id == account_id)
        .where(SupplierRawFetchLog.endpoint == "coupang/upload_invoices")
        .order_by(SupplierRawFetchLog.fetched_at.desc())
        .limit(200)
    )
    logs = session.scalars(stmt).all()
    for log in logs:
        payload = log.request_payload if isinstance(log.request_payload, dict) else {}
        if payload.get("orderId") == order_id and payload.get("invoiceNumber") == invoice_number:
            return True
    return False


def _already_canceled_order(
    session: Session,
    account_id: uuid.UUID,
    order_id: str,
) -> bool:
    if not order_id:
        return False

    stmt = (
        select(SupplierRawFetchLog)
        .where(SupplierRawFetchLog.supplier_code == "coupang")
        .where(SupplierRawFetchLog.account_id == account_id)
        .where(SupplierRawFetchLog.endpoint == "coupang/cancel_order")
        .order_by(SupplierRawFetchLog.fetched_at.desc())
        .limit(200)
    )
    logs = session.scalars(stmt).all()
    for log in logs:
        payload = log.request_payload if isinstance(log.request_payload, dict) else {}
        if payload.get("orderId") == order_id:
            return True
    return False


def _ownerclan_status_is_cancel(status: object) -> bool:
    if status is None:
        return False
    s = str(status).strip().lower()
    if not s:
        return False
    return "cancel" in s or "취소" in s


def _record_order_status_change(
    session: Session,
    order: Order,
    new_status: str,
    source: str,
    note: str | None = None,
) -> bool:
    old_status = order.status
    if old_status == new_status:
        return False
    order.status = new_status
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status=new_status,
            source=source,
            note=note,
        )
    )
    return True


def _map_ownerclan_status_to_order_status(status: object) -> str | None:
    """
    OwnerClan → Internal Order.status mapping (keyword-based).
    - CANCELLED: 취소, cancel
    - SHIPPED: 배송완료, delivered, 완료
    - SHIPPING: 배송중, shipped, 송장, 출고
    - READY: 상품준비, 준비중, processing
    - PAYMENT_COMPLETED: 결제완료, paid
    """
    if status is None:
        return None
    s = str(status).strip().lower()
    if not s:
        return None

    direct_map = {
        "결제완료": "PAYMENT_COMPLETED",
        "payment_completed": "PAYMENT_COMPLETED",
        "paid": "PAYMENT_COMPLETED",
        "상품준비": "READY",
        "상품준비중": "READY",
        "배송준비중": "READY",
        "processing": "READY",
        "배송중": "SHIPPING",
        "출고": "SHIPPING",
        "송장": "SHIPPING",
        "shipped": "SHIPPING",
        "배송완료": "SHIPPED",
        "구매확정": "SHIPPED",
        "delivered": "SHIPPED",
        "취소": "CANCELLED",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "cancel": "CANCELLED",
        "환불": "CANCELLED",
        "반품": "CANCELLED",
        "refund": "CANCELLED",
        "returned": "CANCELLED",
    }
    if s in direct_map:
        return direct_map[s]

    if "cancel" in s or "취소" in s:
        return "CANCELLED"
    if "배송완료" in s or "delivered" in s or s in {"완료", "배송완료"}:
        return "SHIPPED"
    if "배송중" in s or "shipped" in s or "송장" in s or "출고" in s:
        return "SHIPPING"
    if "상품준비" in s or "준비중" in s or "processing" in s:
        return "READY"
    if "결제" in s or "paid" in s:
        return "PAYMENT_COMPLETED"
    return None


def _extract_cancel_items_from_coupang_raw(raw: dict[str, Any]) -> tuple[list[int], list[int]]:
    vendor_item_ids: list[int] = []
    receipt_counts: list[int] = []
    order_items = raw.get("orderItems") if isinstance(raw.get("orderItems"), list) else []
    for item in order_items:
        if not isinstance(item, dict):
            continue
        vendor_item_id = item.get("vendorItemId") or item.get("vendor_item_id")
        if vendor_item_id is None:
            continue
        try:
            vendor_item_id_int = int(vendor_item_id)
        except Exception:
            continue
        count = (
            item.get("shippingCount")
            or item.get("orderCount")
            or item.get("quantity")
            or 1
        )
        try:
            count_int = max(1, int(count))
        except Exception:
            count_int = 1
        vendor_item_ids.append(vendor_item_id_int)
        receipt_counts.append(count_int)
    return vendor_item_ids, receipt_counts


def sync_ownerclan_orders_to_coupang_invoices(
    session: Session,
    coupang_account_id: uuid.UUID,
    limit: int = 0,
    dry_run: bool = False,
    retry_count: int = 0,
) -> dict[str, Any]:
    """
    오너클랜 주문(배송/송장/취소) → 쿠팡 송장 업로드 및 취소(양방향 동기화).
    - SupplierOrderRaw(오너클랜)에서 trackingNumber 추출
    - Order/SupplierOrder 매핑으로 쿠팡 주문을 찾아 송장 업로드
    """
    processed = 0
    succeeded = 0
    skipped = 0
    failed = 0
    failures: list[dict[str, Any]] = []

    coupang_account = session.get(MarketAccount, coupang_account_id)
    if not coupang_account or coupang_account.market_code != "COUPANG":
        raise RuntimeError("쿠팡 계정을 찾을 수 없습니다")

    if not coupang_account.is_active:
        return {"processed": 0, "succeeded": 0, "skipped": 0, "failed": 0, "failures": []}

    owner_account = get_primary_ownerclan_account(session, user_type="seller")

    try:
        client = _get_client_for_account(coupang_account)
    except Exception as e:
        raise RuntimeError(f"쿠팡 클라이언트 초기화 실패: {e}")

    default_delivery_company = None
    if isinstance(coupang_account.credentials, dict):
        default_delivery_company = coupang_account.credentials.get("default_delivery_company_code")
    if not default_delivery_company:
        _rc, _oc, default_delivery_company, _debug = _get_default_centers(client, coupang_account, session)
    if not default_delivery_company:
        default_delivery_company = "KDEXP"

    q = (
        session.query(SupplierOrderRaw)
        .filter(SupplierOrderRaw.supplier_code == "ownerclan")
        .filter(SupplierOrderRaw.account_id == owner_account.id)
        .order_by(SupplierOrderRaw.fetched_at.desc())
    )
    if limit and limit > 0:
        q = q.limit(limit)

    rows = q.all()
    retry_count = max(0, int(retry_count or 0))

    def _should_retry(resp: dict[str, Any]) -> bool:
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, dict):
            response_code = data.get("responseCode")
            if response_code in {1, 99}:
                return True
            response_list = data.get("responseList")
            if isinstance(response_list, list):
                for item in response_list:
                    if isinstance(item, dict) and item.get("retryRequired") is True:
                        return True
        return False

    def _is_invoice_success(code: int, resp: dict[str, Any]) -> bool:
        if code >= 300:
            return False
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, dict):
            response_code = data.get("responseCode")
            if response_code not in (0, None):
                return False
            response_list = data.get("responseList")
            if isinstance(response_list, list):
                for item in response_list:
                    if isinstance(item, dict) and item.get("succeed") is False:
                        return False
        return True

    def _is_cancel_success(code: int, resp: dict[str, Any]) -> bool:
        if code >= 300:
            return False
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, dict):
            failed_items = data.get("failedItemIds")
            if isinstance(failed_items, list) and failed_items:
                return False
        return True

    for row in rows:
        processed += 1
        raw = row.raw if isinstance(row.raw, dict) else {}
        order_status = raw.get("status") or raw.get("order_status")
        mapped_status = _map_ownerclan_status_to_order_status(order_status)
        is_cancel = _ownerclan_status_is_cancel(order_status)
        tracking_no, shipping_code = _extract_tracking_from_ownerclan_raw(raw)
        if not tracking_no and not is_cancel:
            skipped += 1
            continue

        supplier_order = (
            session.query(SupplierOrder)
            .filter(SupplierOrder.supplier_code == "ownerclan")
            .filter(SupplierOrder.supplier_order_id == row.order_id)
            .one_or_none()
        )
        if not supplier_order:
            alt_id = raw.get("id") or raw.get("key")
            if alt_id:
                supplier_order = (
                    session.query(SupplierOrder)
                    .filter(SupplierOrder.supplier_code == "ownerclan")
                    .filter(SupplierOrder.supplier_order_id == str(alt_id))
                    .one_or_none()
                )
        if not supplier_order:
            skipped += 1
            continue

        order = session.query(Order).filter(Order.supplier_order_id == supplier_order.id).one_or_none()
        if not order or not order.market_order_id:
            skipped += 1
            continue

        if mapped_status:
            try:
                if _record_order_status_change(session, order, mapped_status, "ownerclan_status_map"):
                    session.commit()
            except Exception:
                session.rollback()

        market_raw = session.get(MarketOrderRaw, order.market_order_id)
        market_raw_data = market_raw.raw if market_raw and isinstance(market_raw.raw, dict) else {}
        coupang_order_id = _extract_coupang_order_id(market_raw_data)
        if not coupang_order_id:
            failed += 1
            failures.append({"ownerclanOrderId": row.order_id, "reason": "쿠팡 orderId를 찾을 수 없습니다"})
            continue

        invoice_number = tracking_no
        delivery_company_code = shipping_code or default_delivery_company

        if is_cancel:
            if _already_canceled_order(session, coupang_account_id, coupang_order_id):
                skipped += 1
                continue
            vendor_item_ids, receipt_counts = _extract_cancel_items_from_coupang_raw(market_raw_data)
            if not vendor_item_ids:
                failed += 1
                failures.append({"ownerclanOrderId": row.order_id, "reason": "쿠팡 취소용 vendorItemId를 찾을 수 없습니다"})
                continue
            user_id = None
            if isinstance(coupang_account.credentials, dict):
                user_id = coupang_account.credentials.get("vendor_user_id")
            if not user_id:
                failed += 1
                failures.append({"ownerclanOrderId": row.order_id, "reason": "쿠팡 취소용 vendor_user_id가 없습니다"})
                continue

            payload = {
                "orderId": coupang_order_id,
                "vendorItemIds": vendor_item_ids,
                "receiptCounts": receipt_counts,
                "bigCancelCode": "CANERR",
                "middleCancelCode": "CCPNER",
                "vendorId": coupang_account.credentials.get("vendor_id") if isinstance(coupang_account.credentials, dict) else None,
                "userId": user_id,
            }

            if dry_run:
                skipped += 1
                continue
            attempts = 0
            ok = False
            code = 0
            resp: dict[str, Any] | None = None
            while attempts <= retry_count:
                attempts += 1
                # CoupangClient의 통일된 cancel_order 메서드 사용
                code, resp = client.cancel_order(
                    order_id=coupang_order_id,
                    vendor_item_ids=vendor_item_ids,
                    receipt_counts=receipt_counts,
                    user_id=user_id,
                    middle_cancel_code="CCPNER",  # 주소지 등 제휴사 오류/취소
                )
                resp = resp if isinstance(resp, dict) else {"_raw": resp}
                ok = _is_cancel_success(code, resp)
                session.add(
                    SupplierRawFetchLog(
                        supplier_code="coupang",
                        account_id=coupang_account_id,
                        endpoint="coupang/cancel_order",
                        request_payload={**payload, "attempt": attempts},
                        http_status=code,
                        response_payload=resp,
                        error_message=None if ok else "cancel_order failed",
                    )
                )
                session.commit()
                if ok or not _should_retry(resp):
                    break
                time.sleep(min(8, 2 ** (attempts - 1)))

            if not ok:
                failed += 1
                failures.append(
                    {
                        "ownerclanOrderId": row.order_id,
                        "reason": f"쿠팡 주문 취소 실패: HTTP {code}",
                        "response": resp,
                    }
                )
                continue

            if ok:
                try:
                    if _record_order_status_change(session, order, "CANCELLED", "ownerclan_cancel"):
                        session.commit()
                except Exception:
                    session.rollback()
                succeeded += 1
            continue

        if _already_uploaded_invoice(session, coupang_account_id, coupang_order_id, invoice_number):
            skipped += 1
            continue

        payload = {
            "orderId": coupang_order_id,
            "deliveryCompanyCode": delivery_company_code,
            "invoiceNumber": invoice_number,
        }

        if dry_run:
            skipped += 1
            continue
        attempts = 0
        ok = False
        code = 0
        resp: dict[str, Any] | None = None
        while attempts <= retry_count:
            attempts += 1
            code, resp = client.upload_invoices([payload])
            resp = resp if isinstance(resp, dict) else {"_raw": resp}
            ok = _is_invoice_success(code, resp)
            session.add(
                SupplierRawFetchLog(
                    supplier_code="coupang",
                    account_id=coupang_account_id,
                    endpoint="coupang/upload_invoices",
                    request_payload={**payload, "attempt": attempts},
                    http_status=code,
                    response_payload=resp,
                    error_message=None if ok else "upload_invoices failed",
                )
            )
            session.commit()
            if ok or not _should_retry(resp):
                break
            time.sleep(min(8, 2 ** (attempts - 1)))

        if not ok:
            failed += 1
            failures.append(
                {
                    "ownerclanOrderId": row.order_id,
                    "reason": f"쿠팡 송장 업로드 실패: HTTP {code}",
                    "response": resp,
                }
            )
            continue

        if ok:
            try:
                if _record_order_status_change(session, order, "SHIPPING", "ownerclan_invoice"):
                    session.commit()
            except Exception:
                session.rollback()
            succeeded += 1

    return {
        "processed": processed,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "failures": failures[:50],
    }
        


def sync_coupang_orders_raw(
    session: Session,
    account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None = None,
    max_per_page: int = 50,
) -> int:
    """
    쿠팡 발주서(주문) 목록을 조회하여 MarketOrderRaw에 저장합니다.

    - created_at_from / created_at_to: yyyy-MM-dd 또는 ISO-8601
    - status: 쿠팡 주문 상태 필터(옵션)
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        logger.error(f"MarketAccount {account_id} not found")
        return 0

    if account.market_code != "COUPANG":
        logger.error(f"Account {account.name} is not a Coupang account")
        return 0

    if not account.is_active:
        logger.info(f"Account {account.name} is inactive, skipping order sync")
        return 0

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"Failed to initialize client for {account.name}: {e}")
        return 0

    # 기간에 따라 search_type 결정 (24시간 이내면 timeFrame 권장)
    search_type = None
    try:
        def _parse_dt(s: str) -> datetime:
            s_clean = s.split("+")[0].split("Z")[0].strip()
            if "T" in s_clean:
                formats = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
                for f in formats:
                    try:
                        return datetime.strptime(s_clean, f)
                    except ValueError:
                        continue
            return datetime.strptime(s_clean, "%Y-%m-%d")

        dt_from = _parse_dt(created_at_from)
        dt_to = _parse_dt(created_at_to)
        duration_hours = (dt_to - dt_from).total_seconds() / 3600
        if duration_hours <= 24:
            search_type = "timeFrame"
    except Exception:
        # 파싱 실패 시 기본값(Daily) 사용
        pass

    total_processed = 0
    statuses = [status] if status else ["ACCEPT", "INSTRUCT"]

    for st in statuses:
        next_token: str | None = None
        while True:
            try:
                code, data = client.get_order_sheets(
                    created_at_from=created_at_from,
                    created_at_to=created_at_to,
                    status=st,
                    next_token=next_token,
                    max_per_page=max_per_page,
                    search_type=search_type,
                )
            except Exception as e:
                logger.error(f"Failed to fetch ordersheets for {account.name}: {e}")
                break

            if code != 200:
                logger.error(f"Failed to fetch ordersheets for {account.name}: HTTP {code} {data}")
                break

            if not isinstance(data, dict):
                break

            if data.get("code") not in (None, "SUCCESS", 200, "200"):
                logger.error(f"Failed to fetch ordersheets for {account.name} (API Error): {data}")
                break

            # 데이터 추출 (배열 형태)
            content = data.get("data")
            if not isinstance(content, list):
                # 하위 구조(content) 확인 (일부 버전 대응)
                if isinstance(content, dict):
                    content = content.get("content")
            
            if not isinstance(content, list) or not content:
                break

            now = datetime.now(timezone.utc)
            for row in content:
                if not isinstance(row, dict):
                    continue
                
                # orderId 식별 (shipmentBoxId 가 필수로 존재하는 경우가 많음)
                order_id = row.get("orderId") or row.get("shipmentBoxId") or row.get("orderSheetId") or row.get("id")
                if order_id is None:
                    continue

                # 상태별 조회 결과를 구분하기 위해 raw에 status를 주입(추적용)
                row_to_store = dict(row)
                row_to_store.setdefault("_queryStatus", st)

                stmt = insert(MarketOrderRaw).values(
                    market_code="COUPANG",
                    account_id=account.id,
                    order_id=str(order_id),
                    raw=row_to_store,
                    fetched_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["market_code", "account_id", "order_id"],
                    set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
                )
                session.execute(stmt)
                total_processed += 1

            session.commit()

            # nextToken 추출
            next_token = data.get("nextToken")
            if not next_token and isinstance(data.get("data"), dict):
                next_token = data["data"].get("nextToken")
            
            if not next_token:
                break

    return total_processed


def sync_coupang_returns_raw(
    session: Session,
    account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None = None,
    cancel_type: str = "RETURN",
    search_type: str = "timeFrame",
) -> int:
    """
    쿠팡 반품/취소 요청 목록을 조회하여 수집합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0

    if not account.is_active:
        return 0

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"Failed to initialize client for {account.name}: {e}")
        return 0

    # 반품 요청 조회 (v6 기반)
    code, data = client.get_return_requests(
        created_at_from=created_at_from,
        created_at_to=created_at_to,
        status=status,
        search_type=search_type,
        cancel_type=cancel_type,
    )
    
    _log_fetch(session, account, "get_return_requests", {
        "from": created_at_from, 
        "to": created_at_to,
        "cancelType": cancel_type,
        "searchType": search_type
    }, code, data)

    if code != 200:
        logger.error(f"Failed to fetch return requests: {code} {data}")
        return 0

    content = data.get("data")
    if not isinstance(content, list) or not content:
        return 0

    total_processed = 0
    now = datetime.now(timezone.utc)
    for row in content:
        if not isinstance(row, dict):
            continue
        
        # 반품/취소는 receiptId가 고유 식별자
        receipt_id = row.get("receiptId")
        if receipt_id is None:
            continue

        # MarketOrderRaw에 저장 (prefix 'R-' 또는 'C-'를 붙여서 주문과 구분할 수도 있지만, 
        # 일단은 원본 그대로 저장하되 raw 데이터에 정보를 남김)
        # order_id 필드에 receiptId 저장
        store_id = f"RET-{receipt_id}" if cancel_type == "RETURN" else f"CAN-{receipt_id}"
        
        row_to_store = dict(row)
        row_to_store["_cancelType"] = cancel_type
        row_to_store["_fetchType"] = "RETURN_REQUEST"

        stmt = insert(MarketOrderRaw).values(
            market_code="COUPANG",
            account_id=account.id,
            order_id=str(store_id),
            raw=row_to_store,
            fetched_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["market_code", "account_id", "order_id"],
            set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
        )
        session.execute(stmt)
        total_processed += 1

    session.commit()
    return total_processed


def sync_coupang_exchanges_raw(
    session: Session,
    account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None = None,
) -> int:
    """
    쿠팡 교환 요청 목록을 조회하여 수집합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0

    if not account.is_active:
        return 0

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"Failed to initialize client for {account.name}: {e}")
        return 0

    # 교환 요청 조회 (v4 기반)
    code, data = client.get_exchange_requests(
        created_at_from=created_at_from,
        created_at_to=created_at_to,
        status=status,
    )
    
    _log_fetch(session, account, "get_exchange_requests", {
        "from": created_at_from, 
        "to": created_at_to
    }, code, data)

    if code != 200:
        logger.error(f"Failed to fetch exchange requests: {code} {data}")
        return 0

    content = data.get("data")
    if not isinstance(content, list) or not content:
        return 0

    total_processed = 0
    now = datetime.now(timezone.utc)
    for row in content:
        if not isinstance(row, dict):
            continue
        
        # 교환은 exchangeId가 고유 식별자
        exchange_id = row.get("exchangeId")
        if exchange_id is None:
            continue

        store_id = f"EXC-{exchange_id}"
        
        row_to_store = dict(row)
        row_to_store["_fetchType"] = "EXCHANGE_REQUEST"

        stmt = insert(MarketOrderRaw).values(
            market_code="COUPANG",
            account_id=account.id,
            order_id=str(store_id),
            raw=row_to_store,
            fetched_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["market_code", "account_id", "order_id"],
            set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
        )
        session.execute(stmt)
        total_processed += 1

    session.commit()
    return total_processed


def _log_fetch(session: Session, account: MarketAccount, endpoint: str, payload: dict, code: int, data: dict):
    """
    API 통신 결과를 SupplierRawFetchLog 테이블에 기록합니다.
    트랜잭션 롤백 시 로그가 소실되지 않도록 새 세션을 사용합니다.
    """
    def _mask_value(value: object) -> str:
        s = str(value or "")
        if len(s) <= 2:
            return "*" * len(s)
        return f"{'*' * (len(s) - 2)}{s[-2:]}"

    def _sanitize_payload(value: object) -> object:
        if isinstance(value, dict):
            out: dict[str, object] = {}
            for k, v in value.items():
                key = str(k)
                if key in {"vendorId", "vendorUserId"}:
                    out[key] = _mask_value(v)
                    continue
                if key == "content" and isinstance(v, str) and len(v) > 2000:
                    out[key] = v[:2000] + "..."
                    continue
                out[key] = _sanitize_payload(v)
            return out
        if isinstance(value, list):
            return [_sanitize_payload(v) for v in value]
        return value

    safe_payload = payload if isinstance(payload, dict) else {"_raw": payload}
    if endpoint in {"create_product", "update_product_after_create(contents)"}:
        safe_payload = _sanitize_payload(safe_payload)
    try:
        from app.db import SessionLocal
        with SessionLocal() as log_session:
            log = SupplierRawFetchLog(
                supplier_code="COUPANG", # 마켓 로그도 일단 여기 기록
                account_id=account.id,
                endpoint=endpoint,
                request_payload=safe_payload,
                http_status=code,
                response_payload=data if isinstance(data, dict) else {"_raw": data},
                error_message=data.get("message") if isinstance(data, dict) else None,
                fetched_at=datetime.now(timezone.utc)
            )
            log_session.add(log)
            log_session.commit()
    except Exception as e:
        logger.warning(f"API 로그 기록 실패: {e}")


def _log_registration_skip(
    session: Session,
    account: MarketAccount,
    product_id: uuid.UUID,
    reason: str,
    category_code: int | None = None,
) -> None:
    payload = {
        "productId": str(product_id),
        "reason": reason,
    }
    if category_code is not None:
        payload["categoryCode"] = int(category_code)
    _log_fetch(session, account, "register_product_skipped", payload, 0, {"code": "SKIPPED", "message": reason})

    try:
        from app.db import SessionLocal
        with SessionLocal() as log_session:
            listing = (
                log_session.query(MarketListing)
                .filter(MarketListing.market_account_id == account.id)
                .filter(MarketListing.product_id == product_id)
                .first()
            )
            if listing:
                listing.rejection_reason = {
                    "message": reason,
                    "context": "registration_skip",
                }
                log_session.commit()
    except Exception as e:
        logger.warning(f"스킵 사유 저장 실패: {e}")


def sync_market_listing_status(session: Session, listing_id: uuid.UUID) -> tuple[bool, str | None]:
    """
    쿠팡 API를 통해 MarketListing의 최신 상태를 동기화하고 반려 사유가 있다면 저장합니다.
    """
    listing = session.get(MarketListing, listing_id)
    if not listing:
        return False, "MarketListing not found"

    account = session.get(MarketAccount, listing.market_account_id)
    if not account:
        return False, "MarketAccount not found"

    try:
        client = _get_client_for_account(account)
        code, data = client.get_product(listing.market_item_id)
        
        if code != 200:
            return False, f"쿠팡 상품 조회 실패: {data.get('message', '알 수 없는 오류')}"

        data_obj = data.get("data", {})
        raw_status_name = data_obj.get("statusName")

        status_name = None
        try:
            s = str(raw_status_name or "").strip()
            su = s.upper()

            if su == "DENIED" or s in {"승인반려", "반려"}:
                status_name = "DENIED"
            elif su == "DELETED" or "삭제" in s or s == "상품삭제":
                status_name = "DELETED"
            elif su == "APPROVAL_REQUESTED":
                status_name = "APPROVING"
            elif su in {"IN_REVIEW", "SAVED", "APPROVING", "APPROVED", "PARTIAL_APPROVED"}:
                status_name = su
            elif s == "심사중":
                status_name = "IN_REVIEW"
            elif s in {"임시저장", "임시저장중"}:
                status_name = "SAVED"
            elif s == "승인대기중":
                status_name = "APPROVING"
            elif s == "승인완료":
                status_name = "APPROVED"
            elif s == "부분승인완료":
                status_name = "PARTIAL_APPROVED"
            elif su:
                status_name = su
            else:
                status_name = None
        except Exception:
            status_name = None
        
        # 상태 업데이트
        listing.coupang_status = status_name
        
        # 반려 사유 확인 (approvalStatusHistory)
        history = data_obj.get("approvalStatusHistory")
        if status_name == "DENIED":
            reason_found = False
            if isinstance(history, list) and history:
                denied_history = next(
                    (
                        h
                        for h in history
                        if isinstance(h, dict) and (h.get("statusName") in {"DENIED", "승인반려", "반려"})
                    ),
                    None,
                )
                if isinstance(denied_history, dict):
                    listing.rejection_reason = denied_history
                    reason_found = True
            
            if not reason_found:
                # history에 없을 경우 top-level 필드 확인
                extra_msg = data_obj.get("extraInfoMessage")
                if extra_msg:
                    listing.rejection_reason = {"message": extra_msg, "context": "extraInfoMessage"}
                else:
                    listing.rejection_reason = {"message": "반려 사유가 표시되지 않았습니다. (쿠팡 파트너 센터 확인 필요)", "context": "unknown"}
        elif status_name != "DENIED":
            listing.rejection_reason = None

        session.commit()
        return True, status_name

    except Exception as e:
        session.rollback()
        logger.error(f"상태 동기화 중 예외 발생: {e}")
        return False, str(e)


def register_product(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> tuple[bool, str | None]:
    """
    쿠팡에 상품을 등록합니다.
    성공 시 True, 실패 시 False를 반환합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        logger.error(f"쿠팡 등록을 위한 계정이 유효하지 않습니다: {account_id}")
        return False, "쿠팡 등록을 위한 계정이 유효하지 않습니다"
        
    product = session.get(Product, product_id)
    if not product:
        logger.error(f"상품을 찾을 수 없습니다: {product_id}")
        return False, "상품을 찾을 수 없습니다"
    if getattr(product, "coupang_eligibility", "") == "NEVER":
        reason = "SKIPPED: coupang_eligibility=NEVER"
        _log_registration_skip(session, account, product.id, reason, None)
        return False, reason
    if product.coupang_doc_pending and (product.coupang_doc_pending_reason or "").startswith("NEVER:"):
        reason = f"SKIPPED: {product.coupang_doc_pending_reason}"
        _log_registration_skip(session, account, product.id, reason, None)
        return False, reason

    original_images = _get_original_image_urls(session, product)
    payload_images = original_images
    if not payload_images:
        processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
        payload_images = processed_images
    payload_images = [
        url.strip()
        for url in payload_images
        if isinstance(url, str) and url.strip()
    ]
    payload_images = list(dict.fromkeys(payload_images))

    if len(payload_images) > 9:
        payload_images = payload_images[:9]
    if len(payload_images) < 1:
        logger.warning(
            "쿠팡 등록 스킵: 이미지 없음(productId=%s, name_only=%s)",
            product.id,
            _name_only_processing(),
        )
        return False, "SKIPPED: 쿠팡 등록을 위해서는 이미지가 최소 1장 필요합니다"

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"클라이언트 초기화 실패: {e}")
        return False, f"클라이언트 초기화 실패: {e}"

    # 1. 메타 데이터 준비
    try:
        meta_result = _get_coupang_product_metadata(session, client, account, product)
    except SkipCoupangRegistrationError as e:
        reason = f"SKIPPED: {e}"
        logger.info(f"상품 등록 스킵: {e}")
        _log_registration_skip(
            session,
            account,
            product.id,
            reason,
            None,
        )
        return False, reason

    if not meta_result["ok"]:
        return False, meta_result["error"]

    try:
        payload = _map_product_to_coupang_payload(
            session,
            product,
            account,
            meta_result["return_center_code"],
            meta_result["outbound_center_code"],
            meta_result["predicted_category_code"],
            meta_result["return_center_detail"],
            meta_result["notice_meta"],
            meta_result["shipping_fee"],
            meta_result["delivery_company_code"],
            image_urls=payload_images,
        )
    except CoupangNeverEligibleError as e:
        reason = f"SKIPPED: {e}"
        logger.info(f"상품 등록 스킵: {e}")
        product.coupang_doc_pending = True
        product.coupang_doc_pending_reason = str(e)
        product.coupang_eligibility = "NEVER"
        session.commit()
        _log_registration_skip(
            session,
            account,
            product.id,
            reason,
            meta_result.get("predicted_category_code"),
        )
        return False, reason
    except CoupangDocumentPendingError as e:
        reason = f"SKIPPED: {e}"
        logger.info(f"상품 등록 스킵: {e}")
        product.coupang_doc_pending = True
        product.coupang_doc_pending_reason = str(e)
        session.commit()
        _log_registration_skip(
            session,
            account,
            product.id,
            reason,
            meta_result.get("predicted_category_code"),
        )
        return False, reason
    except SkipCoupangRegistrationError as e:
        reason = f"SKIPPED: {e}"
        logger.info(f"상품 등록 스킵: {e}")
        _log_registration_skip(
            session,
            account,
            product.id,
            reason,
            meta_result.get("predicted_category_code"),
        )
        return False, reason
    except ValueError as e:
        logger.error(f"상품 등록 사전검증 실패: {e}")
        return False, str(e)
    
    # 2. API 호출 (429 대응을 위한 재시도 로직 포함)
    max_retries = 3
    retry_delay = 2
    code = 0
    data = {}
    
    for attempt in range(max_retries + 1):
        try:
            code, data = client.create_product(payload)
            _log_fetch(session, account, "create_product", payload, code, data)
            
            # 성공 조건
            if code == 200 and data.get("code") == "SUCCESS":
                break
                
            # 429 (Too Many Requests) 대응: 지수 백오프
            if code == 429:
                if attempt < max_retries:
                    logger.warning(f"Coupang API 429 detected for product {product.id}. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
            
            # 그 외의 에러는 기회를 소진하지 않고 바로 실패 처리 (단, Coupang 점검 등 특정 상황 제외)
            break
        except Exception as e:
            logger.error(f"Exception during create_product for {product.id}: {e}")
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            break

    # 최종 결과 확인
    if code != 200 or data.get("code") != "SUCCESS":
        logger.error(f"상품 생성 최종 실패 (ID: {product.id}). HTTP: {code}, Msg: {data}")
        msg = None
        if isinstance(data, dict):
            msg = data.get("message")
        msg_s = str(msg) if msg is not None else ""
        msg_s = msg_s.replace("\n", " ")
        from app.services.analytics.feedback_loop import CoupangFeedbackLoopService
        CoupangFeedbackLoopService.report_registration_result(session, product.id, "FAILURE", f"HTTP={code}, code={data.get('code')}, message={msg_s[:300]}")
        return False, f"상품 생성 실패(HTTP={code}, code={data.get('code')}, message={msg_s[:300]})"

    # 3. 성공 처리
    # data['data']에 sellerProductId (등록상품ID)가 포함됨
    seller_product_id = str(data.get("data"))
    
    from app.services.analytics.feedback_loop import CoupangFeedbackLoopService
    CoupangFeedbackLoopService.report_registration_result(session, product.id, "SUCCESS")

    # 등록 직후 쿠팡이 내려주는 vendor_inventory 기반 이미지 경로로 상세(contents)를 한 번 더 보강합니다.
    # (내부 저장 포맷/렌더링 이슈 회피 목적)
    # 상품 조회 API 응답에서 items[].vendorItemId는 상품 승인완료 시에 값이 표시됨
    # 임시저장 상태일 경우 null이므로 최대 10회 재시도
    if not _preserve_detail_html(product):
        try:
            for _ in range(10):
                p_code, p_data = client.get_product(seller_product_id)
                data_obj2 = p_data.get("data") if isinstance(p_data, dict) else None
                if p_code != 200 or not isinstance(data_obj2, dict):
                    time.sleep(0.5)
                    continue

                items2 = data_obj2.get("items") if isinstance(data_obj2.get("items"), list) else []
                # vendorItemId가 아직 없으면 재시도 (승인 대기 중일 가능성)
                if items2 and isinstance(items2[0], dict):
                    if not items2[0].get("vendorItemId"):
                        time.sleep(2.0)
                        continue

                urls: list[str] = []
                for it in items2:
                    if not isinstance(it, dict):
                        continue
                    imgs = it.get("images") if isinstance(it.get("images"), list) else []
                    for im in imgs:
                        if not isinstance(im, dict):
                            continue
                        u = _extract_coupang_image_url(im)
                        if isinstance(u, str) and u.strip():
                            urls.append(u.strip())
                        if len(urls) >= 20:
                            break
                    if len(urls) >= 20:
                        break

                if urls:
                    new_image_blocks = [
                        {
                            "contentsType": "IMAGE_NO_SPACE",
                            "contentDetails": [{"content": u, "detailType": "IMAGE"} for u in urls],
                        }
                    ]
                    if new_image_blocks:
                        for it in items2:
                            if isinstance(it, dict):
                                # 기존 컨텐츠 블록 중 HTML, TEXT 블록은 유지하고 이미지 블록만 교체합니다.
                                existing_contents = it.get("contents", [])
                                if not isinstance(existing_contents, list):
                                    existing_contents = []
                                
                                preserved = []
                                html_has_images = False
                                for c in existing_contents:
                                    c_type = c.get("contentsType")
                                    if c_type == "HTML":
                                        # 쿠팡 변환 과정에서 http:// 주소가 생길 수 있으므로 다시 한번 https로 정규화
                                        details = c.get("contentDetails", [])
                                        for d in details:
                                            if d.get("detailType") == "TEXT" and "content" in d:
                                                d["content"] = _normalize_detail_html_for_coupang(d["content"])
                                                if _detail_html_has_images(d["content"]):
                                                    html_has_images = True
                                        preserved.append(c)
                                    elif c_type == "TEXT":
                                        # 중복 방지: _build_contents_image_blocks에서 삭제했으므로 기존 텍스트 블록은 유지
                                        preserved.append(c)
                                
                                # HTML에 이미지가 있으면 레이아웃 유지를 위해 이미지 블록은 생략
                                if html_has_images:
                                    it["contents"] = preserved
                                else:
                                    # 원본 HTML/TEXT를 먼저 보여주고, 그 뒤에 보강된 이미지 블록을 배치 (레이아웃 상단 우선)
                                    it["contents"] = preserved + new_image_blocks

                        update_payload = data_obj2
                        update_payload["sellerProductId"] = data_obj2.get("sellerProductId") or int(seller_product_id)
                        update_payload["requested"] = True
                        u_code, u_data = client.update_product(update_payload)
                        _log_fetch(session, account, "update_product_after_create(contents)", update_payload, u_code, u_data)
                    break

                # 이미지가 아직 없으면 대기 후 재시도
                time.sleep(2.0)
        except Exception as e:
            logger.warning(f"등록 직후 상세(contents) 보강 실패: {e}")
    
    logger.info(f"쿠팡 API 등록 성공, DB 영속화 시작 (ID: {product.id}, sellerProductId: {seller_product_id})")
    # MarketListing 생성 또는 업데이트
    stmt = insert(MarketListing).values(
        product_id=product.id,
        market_account_id=account.id,
        market_item_id=seller_product_id,
        status="ACTIVE", 
        coupang_status="IN_REVIEW", # 등록 직후 보통 심사 중
        proven_payload=payload,
        category_code=str(meta_result.get("predicted_category_code")),
        category_grade="VERIFIED_EXACT" if product.coupang_category_source == "PREDICTED" else "FALLBACK_SAFE"
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["market_account_id", "market_item_id"],
        set_={
            "status": "ACTIVE", 
            "linked_at": func.now(), 
            "coupang_status": "IN_REVIEW",
            "proven_payload": payload,
            "category_code": str(meta_result.get("predicted_category_code")),
            "category_grade": "VERIFIED_EXACT" if product.coupang_category_source == "PREDICTED" else "FALLBACK_SAFE"
        }
    )
    session.execute(stmt)
    
    product.processing_status = "LISTED"
    product.coupang_doc_pending = False
    product.coupang_doc_pending_reason = None
    session.commit()
    
    logger.info(f"상품 등록 성공 (ID: {product.id}, sellerProductId: {seller_product_id})")
    return True, None


def delete_product_from_coupang(session: Session, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, str | None]:
    """
    쿠팡에서 상품을 삭제합니다.
    
    쿠팡 API 문서 요구사항:
    - 상품이 '승인대기중' 상태가 아니며
    - 상품에 포함된 옵션(아이템)이 모두 판매중지된 경우에만 삭제 가능
    
    삭제 순서:
    1. 모든 아이템 판매중지 처리 (승인대기중 상태의 경우 필수)
    2. 상품 삭제 API 호출
    3. DB에서 MarketListing 삭제
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, "계정을 찾을 수 없습니다"
    
    try:
        client = _get_client_for_account(account)
        
        # 1. 현재 상품 정보 조회하여 vendorItemIds 및 상태 확보
        code, data = client.get_product(seller_product_id)
        if code != 200:
            return False, f"상품 조회 실패: {data.get('message', '알 수 없는 오류')}"
        
        # 상품 상태 확인 (쿠팡 API 요구사항)
        current_data = data.get("data", {})
        status_name = current_data.get("statusName", "")
        
        # 승인대기중 상태인 경우, 모든 옵션이 판매중지되어야 삭제 가능
        if status_name == "승인대기중":
            logger.info(f"승인대기중 상품 삭제 시도 (sellerProductId={seller_product_id}, status={status_name})")
        
        # 임시저장/승인완료/승인반려 상태에서도 판매중지 처리 후 삭제 (안전한 처리)
        if status_name in ["임시저장", "승인완료", "승인반려"]:
            logger.info(f"상품 삭제 시도 (sellerProductId={seller_product_id}, status={status_name})")
            for item in items:
                vendor_item_id = item.get("vendorItemId")
                if vendor_item_id:
                    # 판매 중지 시도 (이미 중지된 경우 무시될 수 있음)
                    client.stop_sales(str(vendor_item_id))
        
        # 2. 삭제 시도
        code, data = client.delete_product(seller_product_id)
        _log_fetch(session, account, f"delete_product/{seller_product_id}", {}, code, data)
        
        if code == 200 and data.get("code") == "SUCCESS":
            # MarketListing 삭제 처리
            from sqlalchemy import delete
            session.execute(
                delete(MarketListing)
                .where(MarketListing.market_account_id == account.id)
                .where(MarketListing.market_item_id == seller_product_id)
            ) # TODO: DELETE stmt
            session.commit()
            return True, None
        else:
            # 쿠팡 API 오류 메시지 확인
            error_msg = data.get("message", "알 수 없는 오류")
            # "업체상품[***]이 없거나 삭제 불가능한 상태입니다." 메시지는
            # 이미 승인대기중이거나 판매중지가 완료되지 않은 경우 발생
            logger.error(f"상품 삭제 실패: {error_msg}")
            return False, f"삭제 실패: {error_msg}"
            
    except Exception as e:
        session.rollback()
        logger.error(f"쿠팡 상품 삭제 중 예외 발생: {e}")
        return False, str(e)


def stop_product_sales(session: Session, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, dict | None]:
    """
    쿠팡 상품의 판매를 중지합니다. (모든 vendorItemId에 대해 stop_sales 호출)
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, {"message": "계정을 찾을 수 없습니다"}

    try:
        client = _get_client_for_account(account)
        code, data = client.get_product(seller_product_id)
        if code != 200:
            return False, {"message": f"상품 조회 실패: {data.get('message', '알 수 없는 오류')}"}

        items = data.get("data", {}).get("items", [])
        results: list[dict] = []
        stopped = 0
        for item in items:
            vendor_item_id = item.get("vendorItemId")
            if not vendor_item_id:
                continue
            stop_code, stop_data = client.stop_sales(str(vendor_item_id))
            results.append(
                {
                    "vendorItemId": str(vendor_item_id),
                    "httpStatus": int(stop_code),
                    "raw": stop_data if isinstance(stop_data, dict) else {"_raw": stop_data},
                }
            )
            if stop_code == 200:
                stopped += 1

        if stopped == 0 and results:
            return False, {"message": "판매중지 실패", "results": results}

        raw_row = session.execute(
            select(MarketProductRaw)
            .where(MarketProductRaw.market_code == "COUPANG")
            .where(MarketProductRaw.account_id == account.id)
            .where(MarketProductRaw.market_item_id == str(seller_product_id))
        ).scalars().first()
        if raw_row:
            raw_payload = raw_row.raw if isinstance(raw_row.raw, dict) else {}
            raw_payload = {**raw_payload, "status": "SUSPENDED", "statusName": "판매중지"}
            raw_row.raw = raw_payload
            session.commit()

        listing = session.execute(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.market_item_id == str(seller_product_id))
        ).scalars().first()
        if listing:
            listing.status = "SUSPENDED"
            session.commit()

        return True, {"stopped": stopped, "results": results}

    except Exception as e:
        session.rollback()
        logger.error(f"쿠팡 판매중지 중 예외 발생: {e}")
        return False, {"message": str(e)}

def update_coupang_price(session: Session, account_id: uuid.UUID, market_item_id: str, price: int) -> Tuple[bool, str | None]:
    """
    쿠팡 상품 가격을 수정합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, "MarketAccount not found"
    
    client = _get_client_for_account(account)
    
    # 1. 상품 상세 정보 조회하여 vendorItemId 목록 획득
    code, data = client.get_product(market_item_id)
    if code != 200:
        return False, f"상품 조회 실패: {data.get('message', 'Unknown error')}"
        
    items = data.get("data", {}).get("items", [])
    if not items:
        return False, "상품 아이템(옵션)을 찾을 수 없습니다"
        
    success_count = 0
    errors = []
    
    # 2. 모든 아이템(옵션)에 대해 가격 업데이트 수행
    for item in items:
        vendor_item_id = str(item.get("vendorItemId"))
        # 쿠팡은 10원 단위 절사 권장
        target_price = ((price + 9) // 10) * 10
        
        # originalPrice 먼저 업데이트 (salePrice보다 작으면 오류 날 수 있음)
        client.update_original_price(vendor_item_id, target_price)
        
        # salePrice 업데이트
        u_code, u_data = client.update_price(vendor_item_id, target_price, force=True)
        if u_code == 200:
            success_count += 1
        else:
            msg = u_data.get("message", "Unknown error")
            errors.append(f"{vendor_item_id}: {msg}")
            
    if success_count == 0:
        return False, f"가격 수정 실패: {', '.join(errors)}"
        
    # 3. DB 업데이트 (MarketListing 및 Product)
    listing = session.execute(
        select(MarketListing)
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.market_item_id == market_item_id)
    ).scalars().first()
    
    if listing:
        product = session.get(Product, listing.product_id)
        if product:
            product.selling_price = price
            session.commit()
            
    if success_count < len(items):
        return True, f"일부 옵션 수정 완료 ({success_count}/{len(items)}). 오류: {', '.join(errors)}"
        
    return True, "가격 수정 완료"


def update_product_on_coupang(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> tuple[bool, str | None]:
    """
    쿠팡에 등록된 상품 정보를 내부 Product 기준으로 업데이트합니다.
    """
    account = session.get(MarketAccount, account_id)
    product = session.get(Product, product_id)
    if not account or not product:
        return False, "계정 또는 상품을 찾을 수 없습니다"
    
    listing = (
        session.execute(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.product_id == product.id)
            .order_by(MarketListing.linked_at.desc())
        )
        .scalars()
        .first()
    )
    
    if not listing:
        return False, "쿠팡에 등록된 리스팅 정보를 찾을 수 없습니다(먼저 등록 필요)"
        
    try:
        client = _get_client_for_account(account)

        # 최신 쿠팡 상품 상태를 조회하여 vendorItemId/기존 이미지 등을 확보
        code, current_data = client.get_product(listing.market_item_id)
        if code != 200:
            return False, f"쿠팡 상품 정보 조회 실패: {current_data.get('message')}"
        current_data_obj = current_data.get("data") if isinstance(current_data, dict) else None
        if not isinstance(current_data_obj, dict):
            return False, "쿠팡 상품 정보 조회 응답(data)이 비정상입니다"
        current_items = current_data_obj.get("items") if isinstance(current_data_obj.get("items"), list) else []

        # 1. 메타 데이터 준비 (등록 시와 동일한 수준으로 최신 정보 확보)
        meta_result = _get_coupang_product_metadata(session, client, account, product)
        if not meta_result["ok"]:
            return False, meta_result["error"]

        # 2. 페이로드 생성 (Full Sync 방식: 내부 매핑 함수 활용)
        try:
            payload = _map_product_to_coupang_payload(
                session,
                product,
                account,
                meta_result["return_center_code"],
                meta_result["outbound_center_code"],
                meta_result["predicted_category_code"],
                meta_result["return_center_detail"],
                meta_result["notice_meta"],
                meta_result["shipping_fee"],
                meta_result["delivery_company_code"],
                image_urls=_get_original_image_urls(session, product),
            )
        except SkipCoupangRegistrationError as e:
            reason = f"SKIPPED: {e}"
            logger.info(f"상품 업데이트 스킵: {e}")
            _log_registration_skip(
                session,
                account,
                product.id,
                reason,
                meta_result.get("predicted_category_code"),
            )
            return False, reason
        except ValueError as e:
            logger.error(f"상품 업데이트 사전검증 실패: {e}")
            return False, str(e)
        
        # 업데이트 API 규격에 맞춰 sellerProductId 및 requested 추가
        # 쿠팡 API 문서: 상품 수정 시 sellerProductId와 sellerProductItemId 필수
        # - 기존 옵션 수정: sellerProductItemId와 vendorItemId 삽입
        # - 옵션 삭제: items 배열에서 제거 후 sellerProductItemId만 유지
        # - 옵션 추가: sellerProductItemId 미입력하여 items 배열 추가
        payload["sellerProductId"] = int(listing.market_item_id)
        payload["requested"] = True

        # 기존 vendorItemId 및 가격/이미지 맵핑 유지/보정
        # 주의: 승인 완료된 상품의 판매가격, 재고수량, 판매상태는 update_product가 아닌
        # 별도 API(옵션별 가격/수량/판매여부 변경)를 통해 변경 필요
        if payload.get("items") and current_items and isinstance(current_items[0], dict):
            target_item = payload["items"][0]
            current_item = current_items[0]

            # 기존 옵션 수정을 위한 sellerProductItemId 및 vendorItemId 유지
            # 쿠팡 API: 기존 옵션 수정시 sellerProductItemId와 vendorItemId 필수
            # sellerProductItemId: 상품 조회 API를 통해 확인 가능
            # vendorItemId: 임시저장 상태일 경우 null, 승인완료 시 값 표시
            if "vendorItemId" in current_item:
                target_item["vendorItemId"] = current_item["vendorItemId"]
            if "sellerProductItemId" in current_item:
                target_item["sellerProductItemId"] = current_item["sellerProductItemId"]

            # [BUG FIX] 가격 동기화: salePrice가 existing originalPrice보다 크면 originalPrice 상향
            existing_original = int(current_item.get("originalPrice") or 0)
            new_sale = int(target_item.get("salePrice") or 0)
            if new_sale > existing_original:
                target_item["originalPrice"] = new_sale
            else:
                target_item["originalPrice"] = existing_original

            # 로컬 가공 이미지가 없으면 기존 쿠팡 이미지를 활용
            if not target_item.get("images"):
                coupang_urls: list[str] = []
                imgs = current_item.get("images") if isinstance(current_item.get("images"), list) else []
                for im in imgs:
                    if not isinstance(im, dict):
                        continue
                    url = _extract_coupang_image_url(im)
                    if url:
                        coupang_urls.append(url)
                fallback_images: list[dict[str, Any]] = []
                for idx, url in enumerate(coupang_urls[:10]):
                    image_type = "REPRESENTATION" if idx == 0 else "DETAIL"
                    fallback_images.append(
                        {
                            "imageOrder": idx,
                            "imageType": image_type,
                            "vendorPath": url,
                        }
                    )
                if fallback_images:
                    target_item["images"] = fallback_images

        code, data = client.update_product(payload)
        _log_fetch(session, account, "update_product", payload, code, data)
        
        if code == 200 and data.get("code") == "SUCCESS":
            # 업데이트 후 상태 동기화 트리거 (비동기로 하면 좋으나 여기서는 단순하게 처리)
            listing.coupang_status = "IN_REVIEW" 
            session.commit()
            return True, None
        else:
            return False, f"업데이트 실패: {data.get('message', '알 수 없는 오류')}"
            
    except Exception as e:
        session.rollback()
        logger.error(f"쿠팡 상품 업데이트 중 예외 발생: {e}")
        return False, str(e)


def update_product_delivery_info(
    session: Session,
    account_id: uuid.UUID,
    product_id: uuid.UUID,
    delivery_charge: int | None = None,
    delivery_charge_type: str | None = None,
    delivery_company_code: str | None = None,
    return_center_code: str | None = None,
    outbound_shipping_place_code: str | None = None,
    outbound_shipping_time_day: int | None = None,
    return_charge: int | None = None,
    delivery_charge_on_return: int | None = None,
    free_ship_over_amount: int | None = None,
) -> tuple[bool, str | None]:
    """
    쿠팡에 등록된 상품의 배송 및 반품지 정보만 승인 없이 빠르게 업데이트합니다.
    
    이 함수는 쿠팡의 '상품 수정(승인불필요/partial)' API를 사용합니다.
    승인 절차 없이 배송/반품지 관련 정보만 빠르게 수정할 수 있습니다.
    
    Args:
        session: DB 세션
        account_id: 마켓 계정 ID
        product_id: 상품 ID
        delivery_charge: 기본배송비 (유료배송 또는 조건부 무료배송 시)
        delivery_charge_type: 배송비종류 (FREE, NOT_FREE, CHARGE_RECEIVED, CONDITIONAL_FREE)
        delivery_company_code: 택배사 코드
        return_center_code: 반품지 센터 코드
        outbound_shipping_place_code: 출고지 주소 코드
        outbound_shipping_time_day: 기준출고일(일)
        return_charge: 반품배송비
        delivery_charge_on_return: 초도반품배송비
        free_ship_over_amount: 무료배송을 위한 조건 금액
    
    Returns:
        (성공 여부, 에러 메시지)
    
    Note:
        - '임시저장중', '승인대기중' 상태의 상품은 수정할 수 없습니다.
        - 모든 매개변수는 선택적(Optional)이며, 원하는 항목만 입력하여 수정 가능합니다.
    """
    account = session.get(MarketAccount, account_id)
    product = session.get(Product, product_id)
    if not account or not product:
        return False, "계정 또는 상품을 찾을 수 없습니다"
    
    listing = (
        session.execute(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.product_id == product.id)
            .order_by(MarketListing.linked_at.desc())
        )
        .scalars()
        .first()
    )
    
    if not listing:
        return False, "쿠팡에 등록된 리스팅 정보를 찾을 수 없습니다"
    
    try:
        client = _get_client_for_account(account)
        
        # 상품 상태 확인 (임시저장중, 승인대기중 상태는 수정 불가)
        code, current_data = client.get_product(listing.market_item_id)
        if code != 200:
            return False, f"쿠팡 상품 정보 조회 실패: {current_data.get('message')}"
        
        status_name = current_data.get("data", {}).get("statusName", "")
        if status_name in ["임시저장중", "승인대기중", "생성이 진행중"]:
            return False, f"현재 상태 '{status_name}'에서는 수정할 수 없습니다. 승인완료 후 가능합니다."
        
        # partial 업데이트 페이로드 생성
        payload: dict[str, Any] = {
            "sellerProductId": int(listing.market_item_id)
        }
        
        # 선택적 매개변수만 페이로드에 추가
        if delivery_charge is not None:
            payload["deliveryCharge"] = delivery_charge
        if delivery_charge_type is not None:
            payload["deliveryChargeType"] = delivery_charge_type
        if delivery_company_code is not None:
            payload["deliveryCompanyCode"] = delivery_company_code
        if return_center_code is not None:
            payload["returnCenterCode"] = return_center_code
        if outbound_shipping_place_code is not None:
            payload["outboundShippingPlaceCode"] = int(outbound_shipping_place_code)
        if outbound_shipping_time_day is not None:
            payload["outboundShippingTimeDay"] = outbound_shipping_time_day
        if return_charge is not None:
            payload["returnCharge"] = return_charge
        if delivery_charge_on_return is not None:
            payload["deliveryChargeOnReturn"] = delivery_charge_on_return
        if free_ship_over_amount is not None:
            payload["freeShipOverAmount"] = free_ship_over_amount
        
        # partial 업데이트 API 호출
        code, data = client.update_product_partial(listing.market_item_id, payload)
        _log_fetch(session, account, "update_product_partial", payload, code, data)
        
        if code == 200 and data.get("code") == "SUCCESS":
            logger.info(f"배송/반품지 정보 업데이트 성공 (productId={product.id}, sellerProductId={listing.market_item_id})")
            return True, None
        else:
            return False, f"배송/반품지 정보 업데이트 실패: {data.get('message', '알 수 없는 오류')}"
            
    except Exception as e:
        session.rollback()
        logger.error(f"쿠팡 배송/반품지 정보 업데이트 중 예외 발생: {e}")
        return False, str(e)


def register_products_bulk(session: Session, account_id: uuid.UUID, product_ids: list[uuid.UUID] | None = None) -> dict[str, int]:
    """
    Register multiple products to Coupang.
    If product_ids is None, processes all candidates (DRAFT status + COMPLETED processing).
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        logger.error(f"Invalid account for bulk registration: {account_id}")
        return {"total": 0, "success": 0, "failed": 0}

    # Select candidates
    stmt = select(Product).where(Product.status == "DRAFT").where(Product.processing_status == "COMPLETED")
    
    if product_ids:
        stmt = stmt.where(Product.id.in_(product_ids))
        
    products = session.scalars(stmt).all()
    
    total = len(products)
    success = 0
    failed = 0
    skipped = 0
    
    logger.info(f"Starting bulk registration for {total} products on account {account.name}")
    
    for p in products:
        # Check if already listed (defensive)
        listing = session.execute(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.product_id == p.id)
        ).scalars().first()
        
        if listing:
            logger.info(f"Product {p.id} already linked to {listing.market_item_id}, skipping.")
            # Optionally update status to ACTIVE if stuck in DRAFT
            if p.status == "DRAFT":
                p.status = "ACTIVE"
                session.commit()
            continue

        ok, reason = register_product(session, account.id, p.id)
        if ok:
            success += 1
            # Update status to ACTIVE after successful registration
            p.status = "ACTIVE" 
            session.commit()
        else:
            if reason and str(reason).startswith("SKIPPED:"):
                skipped += 1
            else:
                failed += 1
            
    logger.info(f"Bulk registration finished. Total: {total}, Success: {success}, Failed: {failed}, Skipped: {skipped}")
    return {"total": total, "success": success, "failed": failed, "skipped": skipped}


def fulfill_coupang_orders_via_ownerclan(
    session: Session,
    coupang_account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None = None,
    max_per_page: int = 100,
    dry_run: bool = False,
    limit: int = 0,
) -> dict[str, Any]:
    """
    쿠팡 발주서(주문) → 오너클랜 주문 생성(발주) 연동.

    - 1) 쿠팡 ordersheets(raw) 수집(업서트)
    - 2) MarketListing(sellerProductId) → Product → SupplierItemRaw.item_code 매핑
    - 3) OwnerClan POST /v1/order 호출
    - 4) Order/ SupplierOrder 레코드로 연결
    """
    processed = 0
    succeeded = 0
    skipped = 0
    failed = 0
    failures: list[dict[str, Any]] = []
    skipped_details: list[dict[str, Any]] = []

    # 1) 최신 쿠팡 주문 raw 수집
    sync_coupang_orders_raw(
        session,
        account_id=coupang_account_id,
        created_at_from=created_at_from,
        created_at_to=created_at_to,
        status=status,
        max_per_page=max_per_page,
    )

    coupang_account = session.get(MarketAccount, coupang_account_id)
    if not coupang_account:
        raise RuntimeError("쿠팡 계정을 찾을 수 없습니다")

    # 오너클랜 대표 계정 토큰 로드(판매사)
    owner = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )
    if not owner:
        raise RuntimeError("오너클랜(seller) 대표 계정이 설정되어 있지 않습니다")

    owner_client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=owner.access_token,
    )

    # 2) 수집된 MarketOrderRaw 기준 처리
    q = (
        session.query(MarketOrderRaw)
        .filter(MarketOrderRaw.market_code == "COUPANG")
        .filter(MarketOrderRaw.account_id == coupang_account_id)
        .order_by(MarketOrderRaw.fetched_at.desc())
    )
    if limit and limit > 0:
        q = q.limit(limit)

    rows = q.all()
    for row in rows:
        processed += 1
        raw = row.raw or {}
        if not isinstance(raw, dict):
            skipped += 1
            continue

        # 이미 내부 Order가 생성/연동되었는지 확인
        existing_order = session.query(Order).filter(Order.market_order_id == row.id).one_or_none()
        if existing_order and existing_order.supplier_order_id is not None:
            skipped += 1
            continue

        order_sheet_id = str(raw.get("orderSheetId") or raw.get("order_id") or raw.get("shipmentBoxId") or row.order_id)
        order_number = f"CP-{order_sheet_id}"

        # 쿠팡 발주서 row에서 상품 식별자 추출
        # - ordersheets(timeFrame) 응답은 sellerProductId가 orderItems[*] 안에 들어있습니다.
        seller_product_id = raw.get("sellerProductId") or raw.get("seller_product_id")
        order_items = raw.get("orderItems") if isinstance(raw.get("orderItems"), list) else []
        first_item = order_items[0] if order_items and isinstance(order_items[0], dict) else {}
        if seller_product_id is None and isinstance(first_item, dict):
            seller_product_id = first_item.get("sellerProductId") or first_item.get("seller_product_id")
        if seller_product_id is None:
            failed += 1
            failures.append({"orderSheetId": order_sheet_id, "reason": "sellerProductId를 찾을 수 없습니다"})
            continue

        listing = (
            session.query(MarketListing)
            .filter(MarketListing.market_account_id == coupang_account_id)
            .filter(MarketListing.market_item_id == str(seller_product_id))
            .one_or_none()
        )
        if not listing:
            skipped += 1
            skipped_details.append(
                {
                    "orderSheetId": order_sheet_id,
                    "reason": f"MarketListing 없음(sellerProductId={seller_product_id})",
                    "sellerProductName": (first_item.get("sellerProductName") if isinstance(first_item, dict) else None) or raw.get("sellerProductName"),
                }
            )
            continue

        product = session.get(Product, listing.product_id)
        if not product or not product.supplier_item_id:
            failed += 1
            failures.append({"orderSheetId": order_sheet_id, "reason": "Product 또는 supplier_item_id 매핑이 없습니다"})
            continue

        supplier_item = session.get(SupplierItemRaw, product.supplier_item_id)
        product_code = (supplier_item.item_code if supplier_item else None) or (supplier_item.item_key if supplier_item else None)
        if not product_code:
            failed += 1
            failures.append({"orderSheetId": order_sheet_id, "reason": "오너클랜 product_code(item_code)가 없습니다"})
            continue

        quantity = (
            raw.get("orderCount")
            or raw.get("quantity")
            or (first_item.get("shippingCount") if isinstance(first_item, dict) else None)
            or 1
        )
        try:
            quantity_int = max(1, int(quantity))
        except Exception:
            quantity_int = 1

        receiver = raw.get("receiver") if isinstance(raw.get("receiver"), dict) else {}
        recipient_name = (raw.get("receiverName") or raw.get("recipientName") or receiver.get("name") or "").strip()
        recipient_phone = (
            raw.get("receiverPhoneNumber")
            or raw.get("receiverMobileNumber")
            or raw.get("recipientPhone")
            or receiver.get("safeNumber")
            or ""
        ).strip()
        addr1 = (raw.get("receiverAddress1") or raw.get("address1") or raw.get("shippingAddress1") or receiver.get("addr1") or "").strip()
        addr2 = (raw.get("receiverAddress2") or raw.get("address2") or raw.get("shippingAddress2") or receiver.get("addr2") or "").strip()
        zipcode = (raw.get("receiverZipCode") or raw.get("zipCode") or raw.get("postalCode") or receiver.get("postCode") or "").strip()

        if not recipient_name or not recipient_phone or not addr1 or not zipcode:
            failed += 1
            failures.append({"orderSheetId": order_sheet_id, "reason": "수령인/연락처/주소/우편번호 필수값이 부족합니다"})
            continue

        recipient_address = addr1 if not addr2 else f"{addr1} {addr2}"
        delivery_message = (raw.get("deliveryMessage") or raw.get("shippingNote") or "").strip() or None

        payload = {
            "product_code": str(product_code),
            "quantity": quantity_int,
            "buyer_name": recipient_name,
            "buyer_phone": recipient_phone,
            "recipient_name": recipient_name,
            "recipient_phone": recipient_phone,
            "recipient_address": recipient_address,
            "recipient_zipcode": zipcode,
            "delivery_message": delivery_message,
            "order_memo": f"Coupang orderSheetId={order_sheet_id}",
        }

        if dry_run:
            skipped += 1
            continue

        status_code, resp = owner_client.create_order(payload)
        # 최소 성공 판정(문서의 success=true 또는 공통 포맷 code=SUCCESS)
        ok = status_code < 300 and (
            (isinstance(resp, dict) and resp.get("success") is True)
            or (isinstance(resp, dict) and resp.get("code") == "SUCCESS")
        )
        supplier_order_id_str = None
        if isinstance(resp, dict):
            supplier_order_id_str = resp.get("order_id") or (resp.get("data") or {}).get("order_id") if isinstance(resp.get("data"), dict) else None
            if supplier_order_id_str is None and isinstance(resp.get("data"), (str, int)):
                supplier_order_id_str = str(resp.get("data"))

        if not ok or not supplier_order_id_str:
            failed += 1
            failures.append({"orderSheetId": order_sheet_id, "reason": f"오너클랜 주문 생성 실패: HTTP {status_code}", "response": resp})
            session.add(
                SupplierRawFetchLog(
                    supplier_code="ownerclan",
                    account_id=owner.id,
                    endpoint=f"{settings.ownerclan_api_base_url}/v1/order",
                    request_payload=payload,
                    http_status=status_code,
                    response_payload=resp if isinstance(resp, dict) else {"_raw": resp},
                    error_message=None if ok else "create_order failed",
                )
            )
            session.commit()
            continue

        # SupplierOrder / Order 연결 저장
        supplier_order = SupplierOrder(supplier_code="ownerclan", supplier_order_id=str(supplier_order_id_str), status="PENDING")
        session.add(supplier_order)
        session.flush()

        if existing_order:
            order = existing_order
            order.supplier_order_id = supplier_order.id
            order.order_number = order.order_number or order_number
            order.recipient_name = order.recipient_name or recipient_name
            order.recipient_phone = order.recipient_phone or recipient_phone
            order.address = order.address or recipient_address
        else:
            order = Order(
                market_order_id=row.id,
                supplier_order_id=supplier_order.id,
                order_number=order_number,
                status="PAYMENT_COMPLETED",
                recipient_name=recipient_name,
                recipient_phone=recipient_phone,
                address=recipient_address,
                total_amount=0,
            )
            session.add(order)
            session.flush()

        # OrderItem 생성 및 옵션 매칭
        # 기존 OrderItem 삭제 (중복 방지)
        session.query(OrderItem).filter(OrderItem.order_id == order.id).delete()
        
        total_order_amount = 0
        for item in order_items:
            if not isinstance(item, dict): continue
            
            # 쿠팡 sellerItemId(sellerItemCode)를 이용해 ProductOption 식별
            # 쿠팡 API orderItems 내의 sellerItemId 필드 확인
            seller_item_code = str(item.get("sellerItemId") or item.get("externalVendorSkuCode") or "")
            
            # 매칭 시도 1: sellerItemCode 직접 매칭
            # 매칭 시도 2: option.id (UUID string) 매칭
            opt = None
            if seller_item_code:
                opt = session.query(ProductOption).filter(
                    ProductOption.product_id == product.id,
                    (ProductOption.external_option_key == seller_item_code) | (ProductOption.id == uuid.UUID(seller_item_code) if len(seller_item_code) == 36 else False)
                ).first()
            
            qty = int(item.get("shippingCount") or item.get("quantity") or 1)
            unit_price = int(item.get("orderPrice") or item.get("unit_price") or 0)
            item_total_price = unit_price * qty
            total_order_amount += item_total_price
            
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                market_listing_id=listing.id,
                product_option_id=opt.id if opt else None,
                external_item_id=str(item.get("orderItemId") or ""),
                product_name=str(item.get("sellerProductName") or product.name),
                quantity=qty,
                unit_price=unit_price,
                total_price=item_total_price
            )
            session.add(order_item)
            
        order.total_amount = total_order_amount

        session.add(
            SupplierRawFetchLog(
                supplier_code="ownerclan",
                account_id=owner.id,
                endpoint=f"{settings.ownerclan_api_base_url}/v1/order",
                request_payload=payload,
                http_status=status_code,
                response_payload=resp if isinstance(resp, dict) else {"_raw": resp},
                error_message=None,
            )
        )
        session.commit()
        succeeded += 1

    return {
        "processed": processed,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "failures": failures[:50],
        "skippedDetails": skipped_details[:50],
    }


def _get_default_centers(client: CoupangClient, account: MarketAccount | None = None, session: Session | None = None) -> tuple[str | None, str | None, str | None, str]:
    """
    첫 번째로 사용 가능한 반품지, 출고지 센터 코드 및 해당 출고지의 기본 택배사 코드를 조회합니다.
    Returns (return_center_code, outbound_center_code, delivery_company_code, debug_msg)
    """
    if account is not None and isinstance(account.credentials, dict):
        cached_return = account.credentials.get("default_return_center_code")
        cached_outbound = account.credentials.get("default_outbound_shipping_place_code")
        cached_delivery = account.credentials.get("default_delivery_company_code")
        if cached_return and cached_outbound and cached_delivery == "CJGLS":
            return str(cached_return), str(cached_outbound), str(cached_delivery), "cached(사용)"

    def _extract_msg(rc: int, data: dict[str, Any]) -> str:
        code = None
        msg = None
        if isinstance(data, dict):
            code = data.get("code")
            msg = data.get("message") or data.get("msg")
        return f"http={rc}, code={code}, message={msg}"

    def _extract_first_code(data: dict[str, Any], keys: list[str]) -> str | None:
        if not isinstance(data, dict):
            return None

        data_obj = data.get("data") if isinstance(data.get("data"), dict) else None
        if isinstance(data_obj, dict):
            content = data_obj.get("content") if isinstance(data_obj.get("content"), list) else None
            if content and isinstance(content[0], dict):
                for k in keys:
                    v = content[0].get(k)
                    if v is not None:
                        return str(v)

        content2 = data.get("content") if isinstance(data.get("content"), list) else None
        if content2 and isinstance(content2[0], dict):
            for k in keys:
                v = content2[0].get(k)
                if v is not None:
                    return str(v)

        return None

    def _extract_delivery_codes(entries: object) -> list[str]:
        if not isinstance(entries, list):
            return []
        codes: list[str] = []
        for entry in entries:
            code = None
            if isinstance(entry, dict):
                code = (
                    entry.get("deliveryCompanyCode")
                    or entry.get("deliveryCode")
                    or entry.get("code")
                    or entry.get("id")
                )
            else:
                code = str(entry)
            if isinstance(code, str) and code.strip():
                codes.append(code.strip())
        return codes

    # 출고지 (Outbound) 및 택배사 (Delivery Company)
    outbound_rc, outbound_data = client.get_outbound_shipping_centers(page_size=10)
    
    outbound_code = None
    delivery_company_code = "CJGLS"  # 기본값
    
    if isinstance(outbound_data, dict):
        # v2/v5 API Response 구조에 맞춰 content 목록 추출
        data_obj = outbound_data.get("data") if isinstance(outbound_data.get("data"), dict) else None
        content = (data_obj.get("content") if data_obj else outbound_data.get("content")) or []
        
        if content:
            best_center = None
            
            # 우선순위 기준 루프
            # 1. usable=True AND remoteInfos 존재 AND CJGLS 지원
            # 2. usable=True AND remoteInfos 존재
            # 3. usable=True AND CJGLS 지원
            # 4. usable=True
            
            for c in content:
                if not isinstance(c, dict) or not c.get("usable"):
                    continue
                
                c_code = c.get("outboundShippingPlaceCode") or c.get("shippingPlaceCode") or c.get("placeCode")
                if not c_code:
                    continue
                
                remote_infos = c.get("remoteInfos") or []
                codes = c.get("deliveryCompanyCodes") or c.get("usableDeliveryCompanies") or []

                remote_codes = _extract_delivery_codes(remote_infos)
                delivery_codes = _extract_delivery_codes(codes)
                has_cj_remote = "CJGLS" in remote_codes
                has_cj = "CJGLS" in delivery_codes

                if has_cj_remote:
                    delivery_code = "CJGLS"
                elif has_cj:
                    delivery_code = "CJGLS"
                elif remote_codes:
                    delivery_code = remote_codes[0]
                elif delivery_codes:
                    delivery_code = delivery_codes[0]
                else:
                    delivery_code = None
                
                # 강점 점수 계산 (단순화된 방식)
                score = 0
                if remote_infos:
                    score += 10
                if has_cj_remote:
                    score += 5
                elif has_cj:
                    score += 3
                
                if best_center is None or score > best_center["score"]:
                    best_center = {
                        "code": str(c_code),
                        "delivery_code": delivery_code,
                        "codes": delivery_codes,
                        "score": score
                    }
                    if score >= 15: # CJGLS와 remoteInfos 모두 있으면 베스트
                        break
            
            if best_center:
                outbound_code = best_center["code"]
                if best_center["delivery_code"]:
                    delivery_company_code = best_center["delivery_code"]
                elif best_center["codes"]:
                    delivery_company_code = best_center["codes"][0]
            
            if not outbound_code and content:
                # fallback: 어쩔 수 없이 첫 번째 코드라도 선택
                outbound_code = _extract_first_code(outbound_data, ["outboundShippingPlaceCode", "outbound_shipping_place_code", "shippingPlaceCode", "placeCode"])
                logger.warning(f"적절한 출고지를 찾지 못해 첫 번째 코드를 선택합니다: {outbound_code}")
        else:
            logger.warning(f"출고지 정보가 없습니다. (HTTP {outbound_rc})")
            delivery_company_code = "CJGLS"
    
    if not delivery_company_code:
        delivery_company_code = "CJGLS"
    
    outbound_debug = _extract_msg(outbound_rc, outbound_data)
        
    # 반품지 (Return)
    return_rc, return_data = client.get_return_shipping_centers(page_size=10)
    return_code = _extract_first_code(return_data, ["returnCenterCode", "return_center_code"])
    return_debug = _extract_msg(return_rc, return_data)
        
    debug = f"outbound({outbound_debug}), return({return_debug})"

    if return_code and outbound_code and account is not None and session is not None and isinstance(account.credentials, dict):
        try:
            creds = dict(account.credentials)
            creds["default_return_center_code"] = str(return_code)
            creds["default_outbound_shipping_place_code"] = str(outbound_code)
            creds["default_delivery_company_code"] = delivery_company_code
            account.credentials = creds
            session.commit()
        except Exception as e:
            logger.warning(f"센터 코드 캐시 저장 실패: {e}")

    return return_code, outbound_code, delivery_company_code, debug


def _map_product_to_coupang_payload(
    session: Session,
    product: Product,
    account: MarketAccount, 
    return_center_code: str, 
    outbound_center_code: str,
    predicted_category_code: int = 77800,
    return_center_detail: dict[str, Any] | None = None,
    notice_meta: dict[str, Any] | None = None,
    shipping_fee: int = 0,
    delivery_company_code: str = "CJGLS",
    image_urls: list[str] | None = None,
) -> dict[str, Any]:
    """
    내부 Product 모델을 쿠팡 API Payload로 매핑합니다.
    
    쿠팡 상품 생성 API 요구사항 (2024년 10월 10일 이후):
    - 필수 구매옵션(attributes)이 MANDATORY인 경우 반드시 입력 필요
    - 데이터 형식이 유효한 값/단위로 정확하게 입력 필요
    - 인증(certifications), 구비서류(requiredDocuments) 처리 필요
    """
    
    # 가공된 이름이 있으면 사용, 없으면 원본 이름 사용
    name_to_use = product.processed_name if product.processed_name else product.name
    
    # === [Option B] 템플릿 참조 로직 ===
    template, grade = _lookup_proven_payload_template(session, predicted_category_code)
    template_attrs = {}
    template_notices = {}
    if template:
        # sellerProductId 등 상품별 고유 필드를 제외한 페이로드 정보 추출
        t_items = template.get("items", [])
        if t_items and isinstance(t_items[0], dict):
            for a in t_items[0].get("attributes", []):
                template_attrs[a.get("attributeTypeName")] = a.get("attributeValueName")
            for n in t_items[0].get("notices", []):
                template_notices[n.get("noticeCategoryDetailName")] = n.get("content")
        logger.info("성공 전력이 있는 페이로드 템플릿(%d개 속성)을 참조합니다.", len(template_attrs))
    
    processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    payload_images = image_urls if isinstance(image_urls, list) and image_urls else processed_images
    
    # 상세페이지는 원본 HTML 유지 (신규 가공 시에만 정규화 적용)
    raw_desc = product.description or "<p>상세설명 없음</p>"
    if _preserve_detail_html(product):
        description_html = str(raw_desc)[:200000]
    else:
        description_html = _normalize_detail_html_for_coupang(str(raw_desc)[:200000])
    forbidden = find_forbidden_tags(description_html)
    if forbidden:
        logger.warning(
            "상세페이지 금지 태그 감지(productId=%s, tags=%s)",
            product.id,
            ",".join(forbidden),
        )
    
    contents_blocks = []
    if payload_images and (not _preserve_detail_html(product)) and not _detail_html_has_images(description_html):
        contents_blocks = _build_contents_image_blocks(payload_images)
    
    # 이미지
    # 가공된 이미지 우선 사용
    images = []
    if payload_images:
        img_list = payload_images
        if isinstance(img_list, list):
            for url in img_list:
                image_type = "REPRESENTATION" if len(images) == 0 else "DETAIL"
                images.append({"imageOrder": len(images), "imageType": image_type, "vendorPath": url})
                if len(images) >= 9:
                    break
    
    # 아이템 (옵션)
    # 현재는 단일 옵션 매핑 (Drop 01 범위)
    # 변형 상품(옵션)이 있다면 반복문 필요
    def _normalize_phone(value: object) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None

        if s.startswith("+82"):
            s = "0" + s[3:]

        digits = "".join([c for c in s if c.isdigit()])
        if not digits:
            return None

        if len(digits) == 11:
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        return digits

    # 상품고시정보(notices) 처리
    notices: list[dict[str, Any]] = []
    try:
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("noticeCategories"), list):
            cats = [c for c in notice_meta["noticeCategories"] if isinstance(c, dict)]
            selected = None
            for c in cats:
                if c.get("noticeCategoryName") == "기타 재화":
                    selected = c
                    break
            if not selected and cats:
                selected = cats[0]
            if selected and isinstance(selected.get("noticeCategoryDetailNames"), list):
                for d in selected["noticeCategoryDetailNames"]:
                    if not isinstance(d, dict):
                        continue
                    if d.get("required") != "MANDATORY":
                        continue
                    dn = d.get("noticeCategoryDetailName")
                    if not dn:
                        continue
                    notices.append(
                        {
                            "noticeCategoryName": selected.get("noticeCategoryName"),
                            "noticeCategoryDetailName": dn,
                            "content": template_notices.get(dn, "상세페이지 참조"),
                        }
                    )
    except Exception:
        notices = []
    
    if not notices:
        # Fallback to standard "기타 재화" notices
        notice_cat = "기타 재화"
        details = ["품명 및 모델명", "인증/허가 사항", "제조국(원산지)", "제조자(수입자)", "소비자상담 관련 전화번호"]
        notices = [
            {"noticeCategoryName": notice_cat, "noticeCategoryDetailName": d, "content": "상세페이지 참조"}
            for d in details
        ]

    # 필수 attributes 처리 (2024년 10월 10일 규정 준수)
    item_attributes: list[dict[str, Any]] = []
    mandatory_attrs_missing = []
    try:
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("attributes"), list):
            attrs = [a for a in notice_meta["attributes"] if isinstance(a, dict)]
            # 필수이고 구매옵션(EXPOSED)인 항목만 처리
            mandatory_attrs = [a for a in attrs if a.get("required") == "MANDATORY" and a.get("exposed") == "EXPOSED"]
            
            for attr in mandatory_attrs:
                attr_type = attr.get("attributeTypeName")
                if not attr_type:
                    continue
                
                # 데이터 형식에 따른 기본값 설정
                data_type = attr.get("dataType", "STRING")
                basic_unit = attr.get("basicUnit", "")
                
                # 템플릿에 값이 있으면 우선 사용, 없으면 기본값 설정
                attr_value = template_attrs.get(attr_type)
                if not attr_value:
                    if data_type == "NUMBER":
                        if "수량" in attr_type or "qty" in attr_type.lower():
                            attr_value = "1개"
                            if basic_unit and basic_unit != "없음":
                                attr_value = f"1{basic_unit}"
                        elif "무게" in attr_type or "중량" in attr_type or "weight" in attr_type.lower():
                            attr_value = "1g"
                            if basic_unit and basic_unit != "없음":
                                attr_value = f"1{basic_unit}"
                        elif "용량" in attr_type or "volume" in attr_type.lower():
                            attr_value = "1ml"
                            if basic_unit and basic_unit != "없음":
                                attr_value = f"1{basic_unit}"
                        else:
                            attr_value = "1"
                    else:
                        # STRING 타입 필수 속성은 일단 홀더로 두고, 옵션 매핑 단계에서 실제 값으로 변환 시도
                        attr_value = "상세페이지 참조"
                
                # 필수 옵션에 추가
                item_attributes.append({
                    "attributeTypeName": attr_type,
                    "attributeValueName": attr_value,
                    "exposed": "EXPOSED"
                })
            
            # 필수 속성이 있는 경우 로깅
            if mandatory_attrs:
                logger.info(f"필수 구매옵션 {len(mandatory_attrs)}개 처리됨 (카테고리: {predicted_category_code})")
                mandatory_attrs_missing = [
                    a.get("attributeTypeName") for a in mandatory_attrs 
                    if not any(it.get("attributeTypeName") == a.get("attributeTypeName") for it in item_attributes)
                ]
    except Exception as e:
        logger.warning(f"attributes 처리 중 오류 발생: {e}")

    # 검색필터 옵션 추가 (선택사항)
    try:
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("attributes"), list):
            attrs = [a for a in notice_meta["attributes"] if isinstance(a, dict)]
            # 검색필터(NONE)인 항목 중 선택적인 항목 추가
            filter_attrs = [a for a in attrs if a.get("exposed") == "NONE" and a.get("required") in ["OPTIONAL", "RECOMMEND"]]
            
            # 공통 검색필터 (예: 피부타입, 성별 등)
            common_filters = ["피부타입", "성별", "사용자연령대", "사용부위"]
            for attr in filter_attrs:
                attr_type = attr.get("attributeTypeName")
                if attr_type in common_filters:
                    item_attributes.append({
                        "attributeTypeName": attr_type,
                        "attributeValueName": "모두",
                        "exposed": "NONE"
                    })
                    break
    except Exception as e:
        logger.warning(f"검색필터 처리 중 오류 발생: {e}")

    # 인증정보(certifications) 처리
    item_certifications: list[dict[str, Any]] = []
    try:
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("certifications"), list):
            certs = [c for c in notice_meta["certifications"] if isinstance(c, dict)]

            # 필수/추천 인증 확인
            mandatory_certs = [c for c in certs if c.get("required") in ["MANDATORY", "RECOMMEND"]]

            if mandatory_certs:
                cert_names = []
                for cert in mandatory_certs:
                    name = cert.get("name") or cert.get("certificationTypeName") or cert.get("certificationType")
                    if name:
                        cert_names.append(str(name))
                cert_label = ", ".join(cert_names) if cert_names else "미상"
                raise SkipCoupangRegistrationError(f"필수/추천 인증 정보 필요: {cert_label}")
    except SkipCoupangRegistrationError:
        raise
    except Exception as e:
        logger.warning(f"certifications 처리 중 오류 발생: {e}")

    # 구비서류(requiredDocuments) 처리
    required_documents: list[dict[str, Any]] = []
    try:
        docs = _extract_required_doc_templates(notice_meta)
        if docs:
            allowed_templates = _parse_env_list("COUPANG_ALLOWED_REQUIRED_DOCUMENTS") or DEFAULT_COUPANG_ALLOWED_REQUIRED_DOC_TEMPLATES
            blocked_keywords = _parse_env_list("COUPANG_BLOCKED_REQUIRED_DOCUMENTS") or DEFAULT_COUPANG_BLOCKED_REQUIRED_DOC_KEYWORDS
            never_templates = _parse_env_list("COUPANG_NEVER_REQUIRED_DOCUMENTS") or DEFAULT_COUPANG_NEVER_REQUIRED_DOC_TEMPLATES
            allowed_tokens = _normalize_tokens(allowed_templates)
            blocked_tokens = _normalize_tokens(blocked_keywords)
            never_tokens = _normalize_tokens(never_templates)

            required_templates: list[str] = []
            for doc in docs:
                required_flag = doc.get("required") or ""
                if not _required_doc_applies(str(required_flag), product):
                    continue
                name = doc.get("templateName") or doc.get("documentName") or ""
                if name:
                    required_templates.append(str(name))

            blocked_templates: list[str] = []
            for name in required_templates:
                if _match_any(name, blocked_tokens):
                    blocked_templates.append(name)
                elif allowed_tokens and not _match_any(name, allowed_tokens):
                    blocked_templates.append(name)

            never_hits = [name for name in required_templates if _match_any(name, never_tokens)]
            if never_hits:
                never_label = ", ".join(never_hits)
                raise CoupangNeverEligibleError(f"NEVER: 구비서류 템플릿 포함 ({never_label})")

            if blocked_templates:
                blocked_label = ", ".join(blocked_templates)
                raise SkipCoupangRegistrationError(f"필수 구비서류 금지 템플릿: {blocked_label}")

            missing_templates: list[str] = []
            for name in required_templates:
                entry = _get_document_library_entry(session, product.brand, name)
                if entry:
                    required_documents.append(entry)
                else:
                    missing_templates.append(name)

            if missing_templates:
                missing_label = ", ".join(missing_templates)
                raise CoupangDocumentPendingError(
                    f"필수 구비서류 미보유: {missing_label}",
                    missing_templates=missing_templates,
                )
    except SkipCoupangRegistrationError:
        raise
    except Exception as e:
        logger.warning(f"requiredDocuments 처리 중 오류 발생: {e}")

    # allowedOfferConditions 검증
    offer_condition = "NEW"
    try:
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("allowedOfferConditions"), list):
            allowed_conditions = notice_meta["allowedOfferConditions"]
            if "NEW" not in allowed_conditions:
                logger.warning(f"NEW 상태가 허용되지 않는 카테고리입니다. 허용 상태: {allowed_conditions}")
    except Exception as e:
        logger.warning(f"allowedOfferConditions 확인 중 오류 발생: {e}")

    # Return Center Fallbacks
    return_zip = (return_center_detail.get("returnZipCode") if return_center_detail else None) or "14598"
    return_addr = (return_center_detail.get("returnAddress") if return_center_detail else None) or "경기도 부천시 원미구 부일로199번길 21"
    return_addr_detail = (return_center_detail.get("returnAddressDetail") if return_center_detail else None) or "401 슈가맨워크"
    return_phone = _normalize_phone((return_center_detail.get("companyContactNumber") if return_center_detail else None) or "070-4581-8906")
    return_name = (return_center_detail.get("shippingPlaceName") if return_center_detail else None) or "기본 반품지"

    # 아이템 (옵션) 목록 구성
    items_payload = []
    parallel_imported = "PARALLEL_IMPORTED" if product.coupang_parallel_imported else "NOT_PARALLEL_IMPORTED"
    overseas_purchased = "OVERSEAS_PURCHASED" if product.coupang_overseas_purchased else "NOT_OVERSEAS_PURCHASED"
    pcc_needed = bool(product.coupang_overseas_purchased)
    
    # DB에 옵션이 있으면 사용, 없으면 단일 아이템으로 처리
    options = product.options if product.options else []
    
    if not options:
        # Fallback: 옵션 정보가 없는 경우 기존 로직대로 단일 아이템 생성
        total_price = int(product.selling_price or 0)
        if total_price < 3000: total_price = 3000
        total_price = ((total_price + 99) // 100) * 100
        
        items_payload.append({
            "itemName": name_to_use[:150],
            "originalPrice": total_price,
            "salePrice": total_price,
            "maximumBuyCount": 9999,
            "maximumBuyForPerson": 0,
            "maximumBuyForPersonPeriod": 1,
            "outboundShippingTimeDay": 3,
            "taxType": "TAX",
            "adultOnly": "EVERYONE",
            "parallelImported": parallel_imported,
            "overseasPurchased": overseas_purchased,
            "pccNeeded": pcc_needed,
            "unitCount": 1,
            "images": images,
            "attributes": item_attributes,
            "certifications": item_certifications,
            "contents": (
                contents_blocks + [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}]
            ) if contents_blocks else [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}],
            "notices": notices,
            "offerCondition": offer_condition,
        })
    else:
        seen_option_keys: set[str] = set()
        for opt in options:
            # 옵션별 가격 계산
            opt_price = int(opt.selling_price or 0)
            if opt_price < 3000: opt_price = 3000
            opt_price = ((opt_price + 99) // 100) * 100
            
            # 옵션명을 상품명과 조합 (쿠팡 권장: [상품명] [옵션값])
            opt_name = str(opt.option_name or "").strip()
            opt_val = str(opt.option_value or "").strip() or "단품"
            option_key = f"{opt_name.lower()}::{opt_val.lower()}"
            if option_key in seen_option_keys:
                logger.warning(
                    "중복 옵션값 감지로 옵션을 건너뜁니다(productId=%s, option=%s/%s)",
                    product.id,
                    opt_name,
                    opt_val,
                )
                continue
            seen_option_keys.add(option_key)

            full_item_name = f"{name_to_use} {opt_val}" if opt_val != "단품" else name_to_use
            
            # [개선] 옵션별 유니크 속성 매핑
            # 카테고리 필수 속성 중 옵션명과 매칭되는 항목이 있으면 해당 옵션값을 속성값으로 사용
            # 이를 통해 '중복된 옵션값이 있습니다' 에러 방지 (Coupang은 itemName뿐만 아니라 attributes의 유니크성도 체크함)
            specific_attributes = [attr.copy() for attr in item_attributes]
            opt_name_low = opt_name.lower()
            
            # [개선] 옵션별 유니크 속성 매핑 로직 강화
            # 1. 기존 속성 중 색상/사이즈와 유사한 것을 찾아 먼저 업데이트 시도
            updated_existing = False
            for attr in specific_attributes:
                attr_type_low = attr.get("attributeTypeName", "").lower()
                is_color_attr = any(k in attr_type_low for k in ["색상", "컬러", "color", "종류", "타입", "type"])
                is_size_attr = any(k in attr_type_low for k in ["사이즈", "size", "규격", "용량"])
                
                # 옵션 그룹명(opt_name)이 속성명과 매칭되거나, 
                # 옵션명이 매우 일반적인 경우(option, 옵션 등) 첫 번째 색상/사이즈 속성에 할당
                is_generic_opt = opt_name_low in ["", "option", "옵션", "선택", "종류", "구분"]
                
                match_color = (is_color_attr and ("색상" in opt_name_low or is_generic_opt))
                match_size = (is_size_attr and ("사이즈" in opt_name_low or is_generic_opt))
                
                if match_color or match_size:
                    attr["attributeValueName"] = opt_val
                    updated_existing = True
                    # 컬러/사이즈 하나만 업데이트해도 일단 중복은 피할 수 있으나, 
                    # 여러 속성이 있을 경우를 위해 break는 일단 보류하거나 필요시 조정
            
            # 2. 만약 업데이트된 것이 없다면, 필수/노출 속성 외에 OPTIONAL 속성에서 매칭되는 것 탐색
            if not updated_existing and notice_meta and isinstance(notice_meta.get("attributes"), list):
                for candidate in notice_meta["attributes"]:
                    if not isinstance(candidate, dict): continue
                    c_type = candidate.get("attributeTypeName", "")
                    c_type_low = c_type.lower()
                    
                    is_c_color = any(k in c_type_low for k in ["색상", "컬러", "color"])
                    is_c_size = any(k in c_type_low for k in ["사이즈", "size", "규격"])
                    
                    is_generic_opt = opt_name_low in ["", "option", "옵션", "선택", "종류", "구분"]
                    
                    if (is_c_color and ("색상" in opt_name_low or is_generic_opt)) or \
                       (is_c_size and ("사이즈" in opt_name_low or is_generic_opt)):
                        # 중복 추가 방지: 이미 specific_attributes 에 해당 c_type 이 있는지 확인
                        if not any(a.get("attributeTypeName") == c_type for a in specific_attributes):
                            specific_attributes.append({
                                "attributeTypeName": c_type,
                                "attributeValueName": opt_val,
                                "exposed": "EXPOSED"
                            })
                            updated_existing = True
                            break
            
            # 3. 여전히 업데이트된 속성이 없는데 옵션이 여러개라면 Coupang API 제약(중복 아이템 불허) 대응을 위해 강제 추가
            if not updated_existing and len(options) > 1:
                # 이미 '색상' 속성이 있는지 확인
                color_attr = next((a for a in specific_attributes if a.get("attributeTypeName") == "색상"), None)
                if color_attr:
                    color_attr["attributeValueName"] = opt_val
                else:
                    specific_attributes.append({
                        "attributeTypeName": "색상",
                        "attributeValueName": opt_val,
                        "exposed": "EXPOSED"
                    })

            items_payload.append({
                "itemName": full_item_name[:150],
                "originalPrice": opt_price,
                "salePrice": opt_price,
                "maximumBuyCount": 9999,
                "maximumBuyForPerson": 0,
                "maximumBuyForPersonPeriod": 1,
                "outboundShippingTimeDay": 3,
                "taxType": "TAX",
                "adultOnly": "EVERYONE",
                "parallelImported": parallel_imported,
                "overseasPurchased": overseas_purchased,
                "pccNeeded": pcc_needed,
                "unitCount": 1,
                "images": images,
                "attributes": specific_attributes, 
                "certifications": item_certifications,
                "contents": (
                    contents_blocks + [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}]
                ) if contents_blocks else [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}],
                "notices": notices,
                "offerCondition": offer_condition,
                "sellerItemCode": opt.external_option_key or str(opt.id)
            })

    now = datetime.now(timezone.utc)
    sale_started_at = now.strftime("%Y-%m-%dT%H:%M:%S")
    sale_ended_at = "2099-12-31T23:59:59"

    payload = {
        "displayCategoryCode": predicted_category_code, 
        "sellerProductName": name_to_use[:100],
        "vendorId": str(account.credentials.get("vendor_id") or "").strip(),
        "saleStartedAt": sale_started_at,
        "saleEndedAt": sale_ended_at,
        "displayProductName": name_to_use[:100],
        "brand": product.brand or "Detailed Page",
        "generalProductName": name_to_use,
        "productOrigin": "수입산",
        "deliveryMethod": "SEQUENCIAL",
        "deliveryCompanyCode": delivery_company_code,
        "deliveryChargeType": "FREE",
        "deliveryCharge": 0,
        "freeShipOverAmount": 0,
        "unionDeliveryType": "NOT_UNION_DELIVERY",
        "remoteAreaDeliverable": "Y",
        "returnCenterCode": return_center_code,
        "returnChargeName": return_name,
        "companyContactNumber": return_phone,
        "returnZipCode": return_zip,
        "returnAddress": return_addr,
        "returnAddressDetail": return_addr_detail,
        "returnCharge": 5000,
        "deliveryChargeOnReturn": 5000,
        "outboundShippingPlaceCode": outbound_center_code,
        "vendorUserId": account.credentials.get("vendor_user_id", "user"),
        "requested": True,
        "items": items_payload
    }
    
    if required_documents:
        payload["requiredDocuments"] = required_documents
    
    return payload

def _get_coupang_product_metadata(
    session: Session, 
    client: Any, 
    account: MarketAccount, 
    product: Product
) -> dict[str, Any]:
    """
    상품 등록 및 업데이트 시 공통으로 필요한 메타데이터(센터, 카테고리, 배송비 등)를 조회합니다.
    """
    return_center_code, outbound_center_code, delivery_company_code, _debug = _get_default_centers(client, account, session)
    if not return_center_code or not outbound_center_code:
        return {"ok": False, "error": f"기본 센터 정보 조회 실패: {_debug}"}

    # 카테고리 예측
    predicted_category_code = 77800
    predicted_from_ai = False
    category_name = None
    try:
        from app.services.market_targeting import resolve_supplier_category_name
        category_name = resolve_supplier_category_name(session, product)
    except Exception:
        category_name = None

    def _is_unknown_category(name: str | None) -> bool:
        if not name:
            return True
        normalized = str(name).strip().lower()
        if not normalized:
            return True
        return normalized in {"unknown", "n/a", "na", "none", "-", "null"}

    allow_prediction = os.getenv("COUPANG_ENABLE_CATEGORY_PREDICTION", "0") == "1"
    if _is_unknown_category(category_name) and os.getenv("COUPANG_PREDICT_ON_UNKNOWN", "1") == "1":
        allow_prediction = True
    try:
        if allow_prediction:
            agreed = False
            try:
                agreed_http, agreed_data = client.check_auto_category_agreed(str(account.credentials.get("vendor_id") or "").strip())
                if agreed_http == 200 and isinstance(agreed_data, dict) and agreed_data.get("code") == "SUCCESS":
                    agreed = bool(agreed_data.get("data"))
            except Exception:
                pass

            if agreed:
                pred_name = product.processed_name or product.name
                code, pred_data = client.predict_category(pred_name)
                if code == 200 and isinstance(pred_data, dict):
                    resp_code = pred_data.get("code")
                    resp_data = pred_data.get("data")
                    if resp_code in ("SUCCESS", 200, None) and resp_data is not None:
                        if isinstance(resp_data, dict) and "predictedCategoryCode" in resp_data:
                            predicted_category_code = int(resp_data["predictedCategoryCode"])
                            predicted_from_ai = True
                        elif isinstance(resp_data, dict) and "predictedCategoryId" in resp_data:
                            predicted_category_code = int(resp_data["predictedCategoryId"])
                            predicted_from_ai = True
                        elif isinstance(resp_data, (str, int)):
                            predicted_category_code = int(resp_data)
                            predicted_from_ai = True
                    if predicted_from_ai:
                        logger.info(
                            "쿠팡 카테고리 예측 결과: product=%s name=%s predicted=%s",
                            product.id,
                            (product.processed_name or product.name)[:80],
                            predicted_category_code,
                        )
    except Exception as e:
        logger.info(f"카테고리 예측 스킵/실패: {e}")

    if _is_unknown_category(category_name) and allow_prediction and not predicted_from_ai:
        raise SkipCoupangRegistrationError("카테고리 예측 실패(unknown)")

    allowed_category_codes = _parse_env_list("COUPANG_ALLOWED_CATEGORY_CODES")
    blocked_category_codes = (
        _parse_env_list("COUPANG_BLOCKED_CATEGORY_CODES")
        or DEFAULT_COUPANG_BLOCKED_CATEGORY_CODES
    )
    if blocked_category_codes and str(predicted_category_code) in blocked_category_codes:
        raise SkipCoupangRegistrationError(f"쿠팡 금지 카테고리 코드: {predicted_category_code}")
    if allowed_category_codes and str(predicted_category_code) not in allowed_category_codes:
        raise SkipCoupangRegistrationError(f"쿠팡 허용 카테고리 외: {predicted_category_code}")

    # 공시 메타
    def _fetch_category_meta(category_code: int) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        ttl_hours = 24
        try:
            ttl_hours = int(os.getenv("COUPANG_CATEGORY_META_TTL_HOURS", "24"))
        except Exception:
            ttl_hours = 24

        cached = (
            session.query(CoupangCategoryMetaCache)
            .filter(CoupangCategoryMetaCache.category_code == str(category_code))
            .first()
        )
        if cached and cached.expires_at and cached.expires_at > now:
            if isinstance(cached.meta, dict):
                return cached.meta

        meta_data_obj: dict[str, Any] | None = None
        try:
            meta_http, meta_data = client.get_category_meta(str(category_code))
            if meta_http == 200 and isinstance(meta_data, dict) and isinstance(meta_data.get("data"), dict):
                meta_data_obj = meta_data["data"]
        except Exception:
            meta_data_obj = None

        if meta_data_obj is not None:
            expires_at = now + timedelta(hours=max(1, ttl_hours))
            if cached:
                cached.meta = meta_data_obj
                cached.fetched_at = now
                cached.expires_at = expires_at
            else:
                session.add(
                    CoupangCategoryMetaCache(
                        category_code=str(category_code),
                        meta=meta_data_obj,
                        fetched_at=now,
                        expires_at=expires_at,
                    )
                )
            session.commit()
            return meta_data_obj

        if cached and isinstance(cached.meta, dict):
            return cached.meta
        return None

    def _has_mandatory_required_docs(meta: dict[str, Any] | None, product: Product) -> bool:
        if not isinstance(meta, dict):
            return False
        docs = meta.get("requiredDocumentNames")
        if not isinstance(docs, list):
            return False
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            required = doc.get("required") or ""
            if _required_doc_applies(str(required), product):
                return True
        return False

    # 상위 N개 또는 리스트 형태의 응답 처리 가능 여부 확인 (Coupang API 응답 구조에 따라 다름)
    # 현재는 단일 코드로 처리 중이므로, predicted_category_code가 구비서류를 요구할 경우 fallback으로 순차적으로 넘어가는 로직 강화
    
    notice_meta = _fetch_category_meta(predicted_category_code)
    
    # 구비서류 요건 체크 및 안전성 검색
    def _needs_heavy_docs(meta: dict[str, Any] | None) -> bool:
        if not meta: return False
        docs = meta.get("requiredDocumentNames")
        if not isinstance(docs, list): docs = []
        
        heavy_doc_keywords = ["MSDS", "UN38.3", "전기용품", "의료기기", "건강기능식품", "전파법", "어린이", "안전확인", "부적합"]
        for d in docs:
            if not isinstance(d, dict): continue
            if d.get("required") == "MANDATORY":
                doc_name = d.get("documentName", "")
                if any(kw in doc_name for kw in heavy_doc_keywords):
                    return True
        
        # attributes(인증정보 등) 체크 추가
        attrs = meta.get("attributes")
        if isinstance(attrs, list):
            for a in attrs:
                if not isinstance(a, dict): continue
                if a.get("required") == "MANDATORY":
                    attr_name = a.get("attributeTypeName", "")
                    if any(kw in attr_name for kw in ["인증", "KC", "어린이", "전기", "전파"]):
                        return True
        
        # certifications 체크 추가 (MANDATORY 또는 RECOMMEND)
        certs = meta.get("certifications")
        if isinstance(certs, list):
            for c in certs:
                if not isinstance(c, dict): continue
                if c.get("required") in ["MANDATORY", "RECOMMEND"]:
                    return True
        return False

    unsafe_predicted = False
    safety_reasons: list[str] = []
    if predicted_from_ai:
        safety_score, safety_reasons = _score_category_safety(notice_meta, product)
        unsafe_predicted = safety_score < 0
        
    # 카테고리 선정 및 운영 제한 체크
    if check_coupang_daily_limit(session, account.id):
        raise SkipCoupangRegistrationError(f"쿠팡 일일 등록 제한 초과 ({settings.coupang_daily_limit}건)")

    # 0. Sourcing Policy Enforcement (Option C)
    if product.sourcing_policy:
        sp = product.sourcing_policy
        if sp.get("action") == "skip_coupang" and settings.coupang_sourcing_policy_mode == "enforce":
            logger.info("소싱 정책(BLOCK)에 따라 쿠팡 등록을 건너뜁니다. (Score: %s)", sp.get("score"))
            raise SkipCoupangRegistrationError(f"소싱 정책에 따른 차단: {sp.get('grade')} (Score: {sp.get('score')})")

    # 1. 먼저 예측된 카테고리에 대해 검증된 템플릿(VERIFIED_EXACT)이 있는지 확인
    # 만약 검증된 템플릿이 있다면 위험 체크를 우회하여 시도합니다.
    _, grade = _lookup_proven_payload_template(session, predicted_category_code)
    
    product.coupang_category_source = "PREDICTED"
    product.coupang_fallback_used = False
    
    # 2. 검증된 템플릿이 없고 위험 요인이 발견되면 Fallback 시도
    if grade != "VERIFIED_EXACT" and (_needs_heavy_docs(notice_meta) or unsafe_predicted):
        # 안정 모드(Stability Mode)인 경우 Fallback 비허용
        if settings.coupang_stability_mode:
            logger.info("안정 모드(Stability Mode) 활성화로 인해 위험 카테고리 Fallback을 시도하지 않습니다.")
            raise SkipCoupangRegistrationError(f"안정 모드로 인해 위험 카테고리 등록 제한됨: {predicted_category_code}")

        # Fallback 비중 체크
        if check_coupang_fallback_ratio(session, account.id):
            logger.warning("쿠팡 Fallback 비율 임계치 초과로 우회 등록을 중단합니다. (ratio >= %.2f)", settings.coupang_fallback_ratio_threshold)
            raise SkipCoupangRegistrationError(f"Fallback 등록 비율 제한 초과로 인해 중단됨: {predicted_category_code}")

        fallback_raw = (
            settings.coupang_fallback_category_codes
        )
        fallback_codes: list[int] = []
        for part in fallback_raw.split(","):
            s = part.strip()
            if s:
                try: fallback_codes.append(int(s))
                except ValueError: continue

        for fallback_code in fallback_codes:
            if fallback_code == predicted_category_code:
                continue
            
            # 쿨다운 체크: 특정 우회 카테고리 남용 방지
            if check_fallback_cooldown(session, account.id, str(fallback_code)):
                continue

            fallback_meta = _fetch_category_meta(fallback_code)
            if not _needs_heavy_docs(fallback_meta):
                logger.info(
                    "쿠팡 카테고리 구비서류 요구(또는 위험)로 안전한 대체 카테고리 사용: %s -> %s",
                    predicted_category_code,
                    fallback_code,
                )
                predicted_category_code = fallback_code
                notice_meta = fallback_meta
                unsafe_predicted = False # 새로운 카테고리는 안전하다고 가정 (또는 추가 체크 가능)
                product.coupang_category_source = "FALLBACK_SAFE"
                product.coupang_fallback_used = True
                break
        else:
            if _needs_heavy_docs(notice_meta) or unsafe_predicted:
                logger.warning(
                    "쿠팡 카테고리 구비서류 필요 또는 위험 판정: %s",
                    predicted_category_code,
                )
                # 만약 autoFix가 켜져 있어도 서류가 없으면 등록 불가
                raise SkipCoupangRegistrationError(
                    f"증빙 서류(MSDS 등)가 필요한 카테고리입니다: {predicted_category_code}"
                )

    if isinstance(notice_meta, dict):
        category_name = notice_meta.get("displayCategoryName") or notice_meta.get("name") or ""
        blocked_keywords = _parse_env_list("COUPANG_BLOCKED_CATEGORY_KEYWORDS") or DEFAULT_COUPANG_BLOCKED_CATEGORY_KEYWORDS
        if _match_any(category_name, _normalize_tokens(blocked_keywords)):
            raise SkipCoupangRegistrationError(f"쿠팡 금지 카테고리 키워드: {category_name}")

    # 반품지 상세
    return_center_detail = None
    try:
        _rc, _rd = client.get_return_shipping_center_by_code(str(return_center_code))
        if _rc == 200 and isinstance(_rd, dict) and isinstance(_rd.get("data"), list) and _rd["data"]:
            item0 = _rd["data"][0] if isinstance(_rd["data"][0], dict) else {}
            addr0 = None
            addrs = item0.get("placeAddresses")
            if isinstance(addrs, list) and addrs and isinstance(addrs[0], dict):
                addr0 = addrs[0]
            return_center_detail = {
                "shippingPlaceName": item0.get("shippingPlaceName"),
                "returnZipCode": (addr0.get("returnZipCode") if isinstance(addr0, dict) else None),
                "returnAddress": (addr0.get("returnAddress") if isinstance(addr0, dict) else None),
                "returnAddressDetail": (addr0.get("returnAddressDetail") if isinstance(addr0, dict) else None),
                "companyContactNumber": (addr0.get("companyContactNumber") if isinstance(addr0, dict) else None),
            }
    except Exception:
        pass

    # 배송비
    shipping_fee = 0
    try:
        if product.supplier_item_id:
            raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
            raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
            v = raw.get("shippingFee")
            if isinstance(v, (int, float)):
                shipping_fee = int(v)
            elif isinstance(v, str):
                s = "".join([c for c in v.strip() if c.isdigit()])
                if s:
                    shipping_fee = int(s)
    except Exception:
        pass

    return {
        "ok": True,
        "return_center_code": return_center_code,
        "outbound_center_code": outbound_center_code,
        "delivery_company_code": delivery_company_code,
        "predicted_category_code": predicted_category_code,
        "notice_meta": notice_meta,
        "return_center_detail": return_center_detail,
        "shipping_fee": shipping_fee,
    }


def sync_coupang_inquiries(session: Session, account_id: uuid.UUID, days: int = 7) -> int:
    """
    쿠팡 고객문의(상품/고객센터) 동기화
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0
    client = _get_client_for_account(account)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=min(days, 7))  # 쿠팡 API 7일 제한
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    total = 0
    # 1. 상품별 온라인 문의
    for page in range(1, 10):
        code, data = client.get_customer_inquiries(
            inquiry_start_at=start_str,
            inquiry_end_at=end_str,
            page_num=page,
            page_size=50
        )
        _log_fetch(session, account, "get_customer_inquiries", {"page": page}, code, data)
        if code != 200: break
        
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items: break

        for item in items:
            inquiry_id = str(item.get("inquiryId"))
            stmt = insert(MarketInquiryRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                inquiry_id=inquiry_id,
                raw=item,
                fetched_at=datetime.now(timezone.utc)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "inquiry_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            total += 1
        session.commit()
    
    # 2. 고객센터 이관 문의
    for page in range(1, 10):
        code, data = client.get_call_center_inquiries(
            inquiry_start_at=start_str,
            inquiry_end_at=end_str,
            page_num=page,
            page_size=30
        )
        _log_fetch(session, account, "get_call_center_inquiries", {"page": page}, code, data)
        if code != 200: break
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items: break

        for item in items:
            inquiry_id = str(item.get("inquiryId"))
            stmt = insert(MarketInquiryRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                inquiry_id=inquiry_id,
                raw=item,
                fetched_at=datetime.now(timezone.utc)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "inquiry_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            total += 1
        session.commit()

    return total


def sync_coupang_revenue(session: Session, account_id: uuid.UUID, days: int = 30) -> int:
    """
    쿠팡 매출내역 동기화
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0
    client = _get_client_for_account(account)

    end_date = datetime.now(timezone.utc) - timedelta(days=1)  # 전일까지만 조회 가능
    start_date = end_date - timedelta(days=min(days, 31))  # 최대 31일
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    total = 0
    token = ""
    while True:
        code, data = client.get_revenue_history(
            recognition_date_from=start_str,
            recognition_date_to=end_str,
            token=token,
            max_per_page=50
        )
        _log_fetch(session, account, "get_revenue_history", {"token": token}, code, data)
        if code != 200: break
        
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items: break

        for item in items:
            order_id = str(item.get("orderId"))
            sale_type = str(item.get("saleType", "SALE"))
            stmt = insert(MarketRevenueRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                order_id=order_id,
                sale_type=sale_type,
                raw=item,
                fetched_at=datetime.now(timezone.utc)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "order_id", "sale_type"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            total += 1
        session.commit()
        
        token = data.get("nextToken") if isinstance(data, dict) else ""
        if not token: break

    return total


def sync_coupang_settlements(session: Session, account_id: uuid.UUID) -> int:
    """
    쿠팡 지급내역 동기화 (최근 3개월)
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0
    client = _get_client_for_account(account)

    now = datetime.now(timezone.utc)
    total = 0
    # 최근 3개월치 조회
    for i in range(3):
        target_month = (now - timedelta(days=i*30)).strftime("%Y-%m")
        code, data = client.get_settlement_histories(target_month)
        _log_fetch(session, account, "get_settlement_histories", {"month": target_month}, code, data)
        if code != 200: continue
        
        # 지급내역은 리스트 형태로 오거나 단건일 수 있음 (문서 확인 필요하나 보통 data에 리스트)
        items = data.get("data", []) if isinstance(data, dict) else []
        if not isinstance(items, list): items = [items]

        for item in items:
            stmt = insert(MarketSettlementRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                recognition_year_month=target_month,
                raw=item,
                fetched_at=datetime.now(timezone.utc)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "recognition_year_month"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            total += 1
        session.commit()

    return total


def sync_coupang_returns(session: Session, account_id: uuid.UUID, days: int = 30) -> int:
    """
    쿠팡 반품요청 동기화
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0
    client = _get_client_for_account(account)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # v6 API: yyyy-MM-ddTHH:mm
    start_str = start_date.strftime("%Y-%m-%dT%H:%M")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M")

    total = 0
    next_token = None
    while True:
        code, data = client.get_return_requests(
            created_at_from=start_str,
            created_at_to=end_str,
            next_token=next_token,
            max_per_page=50
        )
        _log_fetch(session, account, "get_return_requests", {"nextToken": next_token}, code, data)
        if code != 200: break
        
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items: break

        for item in items:
            receipt_id = str(item.get("receiptId"))
            stmt = insert(MarketReturnRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                receipt_id=receipt_id,
                raw=item,
                fetched_at=datetime.now(timezone.utc)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "receipt_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            total += 1
        session.commit()
        
        next_token = data.get("nextToken") if isinstance(data, dict) else None
        if not next_token: break

    return total


def sync_coupang_exchanges(session: Session, account_id: uuid.UUID, days: int = 30) -> int:
    """
    쿠팡 교환요청 동기화
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        return 0
    client = _get_client_for_account(account)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # v4 API: yyyy-MM-ddTHH:mm:ss
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")

    total = 0
    next_token = None
    while True:
        code, data = client.get_exchange_requests(
            created_at_from=start_str,
            created_at_to=end_str,
            next_token=next_token,
            max_per_page=50
        )
        _log_fetch(session, account, "get_exchange_requests", {"nextToken": next_token}, code, data)
        if code != 200: break
        
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items: break

        for item in items:
            exchange_id = str(item.get("exchangeId"))
            stmt = insert(MarketExchangeRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                exchange_id=exchange_id,
                raw=item,
                fetched_at=datetime.now(timezone.utc)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "exchange_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            total += 1
        session.commit()
        
        next_token = data.get("nextToken") if isinstance(data, dict) else None
        if not next_token: break

    return total
