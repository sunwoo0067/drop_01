from __future__ import annotations

import logging
import re
import uuid
from typing import Any
from datetime import datetime, timezone
import os
import time

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.coupang_client import CoupangClient
from app.models import (
    MarketAccount,
    MarketOrderRaw,
    MarketProductRaw,
    SupplierRawFetchLog,
    Product,
    MarketListing,
    SupplierAccount,
    SupplierItemRaw,
    SupplierOrderRaw,
    SupplierOrder,
    Order,
    OrderStatusHistory,
)
from app.ownerclan_client import OwnerClanClient
from app.ownerclan_sync import get_primary_ownerclan_account
from app.services.detail_html_checks import find_forbidden_tags
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.coupang_ready_service import collect_image_urls_from_raw
from app.settings import settings

logger = logging.getLogger(__name__)


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
    return True


def _get_original_image_urls(session: Session, product: Product) -> list[str]:
    if product.supplier_item_id:
        raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
        raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
        return collect_image_urls_from_raw(raw)

    return []


def _normalize_detail_html_for_coupang(html: str) -> str:
    s = str(html or "")
    if not s:
        return s

    # Coupang requires HTTPS for all content
    s = s.replace("http://", "https://")
    s = s.replace("https://image1.coupangcdn.com/", "https://image1.coupangcdn.com/")
    
    # Remove hidden control characters often found in source data
    s = normalize_ownerclan_html(s)
    
    # Further cleanup for any absolute URLs that might still be HTTP (if any)
    # (Though the global replace usually handles it, being explicit for known CDN)
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
            if deep:
                detail_code, detail_data = client.get_product(seller_product_id)
                _log_fetch(session, account, f"get_product/{seller_product_id}", {}, detail_code, detail_data)
                detail_obj = detail_data.get("data") if isinstance(detail_data, dict) else None
                if detail_code == 200 and isinstance(detail_obj, dict):
                    p = detail_obj
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
                code, resp = client.cancel_order(
                    order_id=coupang_order_id,
                    vendor_item_ids=vendor_item_ids,
                    receipt_counts=receipt_counts,
                    user_id=user_id,
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
        # Fetch page
        code, data = client.get_products(
            next_token=next_token,
            max_per_page=50  # Max allowed by Coupang
        )
        
        # Log fetch attempt (optional but good for debugging)
        _log_fetch(session, account, "get_products", {"nextToken": next_token}, code, data)
        
        if code != 200:
            logger.error(f"Failed to fetch products for {account.name}: {data}")
            break
            
        products = data.get("data", [])
        if not products:
            break
            
        # Upsert Raw Data
        for p in products:
            seller_product_id = str(p.get("sellerProductId"))
            stmt = insert(MarketProductRaw).values(
                market_code="COUPANG",
                account_id=account.id,
                market_item_id=seller_product_id,
                raw=p,
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market_code", "account_id", "market_item_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at}
            )
            session.execute(stmt)
            
        session.commit()
        total_processed += len(products)
        
        next_token = data.get("nextToken")
        if not next_token:
            break
            
    logger.info(f"Finished product sync for {account.name}. Total: {total_processed}")
    return total_processed


def sync_coupang_orders_raw(
    session: Session,
    account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None = None,
    max_per_page: int = 100,
) -> int:
    """
    쿠팡 발주서(주문) 목록을 조회하여 MarketOrderRaw에 저장합니다.

    - created_at_from / created_at_to: 쿠팡 API 규격(yyyy-MM-dd)
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

    total_processed = 0

    # status가 없으면 신규 처리 대상 중심으로 2개 상태를 조회
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
                )
            except Exception as e:
                logger.error(f"Failed to fetch ordersheets for {account.name}: {e}")
                break

            if code != 200:
                logger.error(f"Failed to fetch ordersheets for {account.name}: HTTP {code} {data}")
                break

            if isinstance(data, dict) and data.get("code") not in (None, "SUCCESS", 200, "200"):
                logger.error(f"Failed to fetch ordersheets for {account.name}: {data}")
                break

            # 응답 구조 방어: top-level nextToken / data.nextToken 모두 지원
            root = (data or {}).get("data") if isinstance(data, dict) else None
            if not isinstance(root, dict):
                root = {}

            content = root.get("content")
            if content is None and isinstance((data or {}).get("data"), list):
                content = (data or {}).get("data")
            if not isinstance(content, list) or not content:
                break

            now = datetime.now(timezone.utc)
            for row in content:
                if not isinstance(row, dict):
                    continue
                order_id = row.get("orderSheetId") or row.get("orderId") or row.get("shipmentBoxId") or row.get("id")
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

            next_token = None
            if isinstance(data, dict):
                next_token = data.get("nextToken") or root.get("nextToken")
            if not next_token:
                break

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
        if status_name == "DENIED" and isinstance(history, list) and history:
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
            else:
                first = history[0] if history else None
                listing.rejection_reason = first if isinstance(first, dict) else None
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

    original_images = _get_original_image_urls(session, product)
    payload_images = original_images
    if not payload_images:
        processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
        payload_images = processed_images

    if len(payload_images) > 9:
        payload_images = payload_images[:9]
    if len(payload_images) < 1:
        if _name_only_processing():
            logger.warning(
                "이미지 없이 등록을 시도합니다(name_only). productId=%s",
                product.id,
            )
        else:
            logger.error(
                f"쿠팡 등록을 위해서는 이미지가 최소 1장 필요합니다(productId={product.id}, images={len(payload_images)})"
            )
            return False, f"쿠팡 등록을 위해서는 이미지가 최소 1장 필요합니다(images={len(payload_images)})"

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"클라이언트 초기화 실패: {e}")
        return False, f"클라이언트 초기화 실패: {e}"

    # 1. 메타 데이터 준비
    meta_result = _get_coupang_product_metadata(session, client, account, product)
    if not meta_result["ok"]:
        return False, meta_result["error"]

    payload = _map_product_to_coupang_payload(
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
    
    # 2. API 호출
    code, data = client.create_product(payload)
    _log_fetch(session, account, "create_product", payload, code, data)

    # 성공 조건: HTTP 200 이면서 body의 code가 SUCCESS
    if code != 200 or data.get("code") != "SUCCESS":
        logger.error(f"상품 생성 실패 (ID: {product.id}). HTTP: {code}, Msg: {data}")
        msg = None
        if isinstance(data, dict):
            msg = data.get("message")
        msg_s = str(msg) if msg is not None else ""
        msg_s = msg_s.replace("\n", " ")
        return False, f"상품 생성 실패(HTTP={code}, code={data.get('code')}, message={msg_s[:300]})"

    # 3. 성공 처리
    # data['data']에 sellerProductId (등록상품ID)가 포함됨
    seller_product_id = str(data.get("data"))

    # 등록 직후 쿠팡이 내려주는 vendor_inventory 기반 이미지 경로로 상세(contents)를 한 번 더 보강합니다.
    # (내부 저장 포맷/렌더링 이슈 회피 목적)
    if not _preserve_detail_html(product):
        try:
            for _ in range(10):
                p_code, p_data = client.get_product(seller_product_id)
                data_obj2 = p_data.get("data") if isinstance(p_data, dict) else None
                if p_code != 200 or not isinstance(data_obj2, dict):
                    time.sleep(0.5)
                    continue

                items2 = data_obj2.get("items") if isinstance(data_obj2.get("items"), list) else []
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
    
    # MarketListing 생성 또는 업데이트
    stmt = insert(MarketListing).values(
        product_id=product.id,
        market_account_id=account.id,
        market_item_id=seller_product_id,
        status="ACTIVE", 
        coupang_status="IN_REVIEW" # 등록 직후 보통 심사 중
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["market_account_id", "market_item_id"],
        set_={"status": "ACTIVE", "linked_at": func.now(), "coupang_status": "IN_REVIEW"}
    )
    session.execute(stmt)
    
    product.processing_status = "COMPLETED"
    session.commit()
    
    logger.info(f"상품 등록 성공 (ID: {product.id}, sellerProductId: {seller_product_id})")
    return True, None


def delete_product_from_coupang(session: Session, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, str | None]:
    """
    쿠팡에서 상품을 삭제합니다. 
    먼저 모든 아이템을 판매중지 처리한 후 삭제를 시도합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account:
        return False, "계정을 찾을 수 없습니다"
    
    try:
        client = _get_client_for_account(account)
        
        # 1. 현재 상품 정보 조회하여 vendorItemIds 확보
        code, data = client.get_product(seller_product_id)
        if code != 200:
            return False, f"상품 조회 실패: {data.get('message', '알 수 없는 오류')}"
        
        items = data.get("data", {}).get("items", [])
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
            return False, f"삭제 실패: {data.get('message', '알 수 없는 오류')}"
            
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
        payload = _map_product_to_coupang_payload(
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
        
        # 업데이트 API 규격에 맞춰 sellerProductId 및 requested 추가
        payload["sellerProductId"] = int(listing.market_item_id)
        payload["requested"] = True

        # 기존 vendorItemId 및 가격/이미지 맵핑 유지/보정
        if payload.get("items") and current_items and isinstance(current_items[0], dict):
            target_item = payload["items"][0]
            current_item = current_items[0]

            if "vendorItemId" in current_item:
                target_item["vendorItemId"] = current_item["vendorItemId"]

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

        ok, _reason = register_product(session, account.id, p.id)
        if ok:
            success += 1
            # Update status to ACTIVE after successful registration
            p.status = "ACTIVE" 
            session.commit()
        else:
            failed += 1
            
    logger.info(f"Bulk registration finished. Total: {total}, Success: {success}, Failed: {failed}")
    return {"total": total, "success": success, "failed": failed}


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
            existing_order.supplier_order_id = supplier_order.id
            existing_order.order_number = existing_order.order_number or order_number
            existing_order.recipient_name = existing_order.recipient_name or recipient_name
            existing_order.recipient_phone = existing_order.recipient_phone or recipient_phone
            existing_order.address = existing_order.address or recipient_address
        else:
            session.add(
                Order(
                    market_order_id=row.id,
                    supplier_order_id=supplier_order.id,
                    order_number=order_number,
                    status="PAYMENT_COMPLETED",
                    recipient_name=recipient_name,
                    recipient_phone=recipient_phone,
                    address=recipient_address,
                    total_amount=0,
                )
            )

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

    # 출고지 (Outbound) 및 택배사 (Delivery Company)
    outbound_rc, outbound_data = client.get_outbound_shipping_centers(page_size=10)
    outbound_code = _extract_first_code(outbound_data, ["outboundShippingPlaceCode", "outbound_shipping_place_code", "shippingPlaceCode", "placeCode"])
    
    # 택배사 코드 추출
    delivery_company_code = "CJGLS"  # 기본값 (CJ대한통운, 기본 배송지 이슈 방지)
    if isinstance(outbound_data, dict):
        # v2 API Response check
        data_obj = outbound_data.get("data") if isinstance(outbound_data.get("data"), dict) else None
        content = (data_obj.get("content") if data_obj else outbound_data.get("content")) or []
        if content and isinstance(content[0], dict):
            # Typical keys: deliveryCompanyCodes (list) or usableDeliveryCompanies
            codes = content[0].get("deliveryCompanyCodes") or content[0].get("usableDeliveryCompanies")
            if isinstance(codes, list) and codes:
                # CJGLS가 목록에 있으면 우선 선택 (사용자 요청)
                found_cj = False
                for entry in codes:
                    c = ""
                    if isinstance(entry, dict):
                        c = entry.get("deliveryCompanyCode") or entry.get("code") or entry.get("id") or ""
                    else:
                        c = str(entry)
                    
                    if c == "CJGLS":
                        delivery_company_code = "CJGLS"
                        found_cj = True
                        break
                
                if not found_cj:
                    first_code_entry = codes[0]
                    if isinstance(first_code_entry, dict):
                        delivery_company_code = (
                            first_code_entry.get("deliveryCompanyCode") or 
                            first_code_entry.get("code") or 
                            first_code_entry.get("id")
                        )
                    else:
                        delivery_company_code = str(first_code_entry)
            
            if not delivery_company_code:
                logger.warning(f"지원 택배사 목록이 비어있거나 코드를 추출할 수 없습니다. 기본값 CJGLS를 사용합니다. (outbound_code={outbound_code})")
                delivery_company_code = "CJGLS"
        else:
            logger.warning(f"출고지 정보에 택배사 데이터가 없습니다. 기본값 {delivery_company_code}를 사용합니다. (outbound_code={outbound_code})")
    
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
    """
    
    # 가공된 이름이 있으면 사용, 없으면 원본 이름 사용
    name_to_use = product.processed_name if product.processed_name else product.name
    
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
    
    # 가공된 이미지가 없을 경우 처리 방안 필요
    # 현재는 선행 단계에서 처리되었다고 가정함.
    if not images:
        pass

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
                            "content": "상세페이지 참조",
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

    # Return Center Fallbacks
    return_zip = (return_center_detail.get("returnZipCode") if return_center_detail else None) or "14598"
    return_addr = (return_center_detail.get("returnAddress") if return_center_detail else None) or "경기도 부천시 원미구 부일로199번길 21"
    return_addr_detail = (return_center_detail.get("returnAddressDetail") if return_center_detail else None) or "401 슈가맨워크"
    return_phone = _normalize_phone((return_center_detail.get("companyContactNumber") if return_center_detail else None) or "070-4581-8906")
    return_name = (return_center_detail.get("shippingPlaceName") if return_center_detail else None) or "기본 반품지"

    # DB의 selling_price는 이미 (원가+마진+배송비)/(1-수수료)가 계산된 최종 소비자가임 (100원 단위 올림)
    total_price = int(product.selling_price or 0)
    
    # 100원 단위 올림 재확인 (혹시 모를 구버전 데이터 대비)
    if total_price < 3000:
        total_price = 3000
    total_price = ((total_price + 99) // 100) * 100

    item_payload = {
        "itemName": name_to_use[:150], # 최대 150자
        "originalPrice": total_price, # 무료배송 정책: 배송비를 상품가에 포함
        "salePrice": total_price,
        "maximumBuyCount": 9999,
        "maximumBuyForPerson": 0,
        "maximumBuyForPersonPeriod": 1,
        "outboundShippingTimeDay": 3,
        "taxType": "TAX",
        "adultOnly": "EVERYONE",
        "parallelImported": "NOT_PARALLEL_IMPORTED",
        "overseasPurchased": "NOT_OVERSEAS_PURCHASED",
        "pccNeeded": False,
        "unitCount": 1,
        "images": images,
        "attributes": [], # TODO: 카테고리 속성 매핑 필요 (예측된 카테고리에 따라 필수 속성이 다름)
        "contents": (
            contents_blocks + [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}]
        ) if contents_blocks else [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}],
        "notices": notices,
    }

    now = datetime.now(timezone.utc)
    sale_started_at = now.strftime("%Y-%m-%dT%H:%M:%S")
    sale_ended_at = "2099-12-31T23:59:59"

    payload = {
        "displayCategoryCode": predicted_category_code, 
        # 예측된 카테고리 코드를 사용.
        # 주의: 일부 카테고리는 필수 속성(attributes)이 없으면 등록 실패할 수 있음.
        # 향후 predict_category 응답에 포함된 attributes 메타데이터를 활용하여 자동 매핑 고도화 필요.
        "sellerProductName": name_to_use[:100],
        "vendorId": str(account.credentials.get("vendor_id") or "").strip(),
        "saleStartedAt": sale_started_at,
        "saleEndedAt": sale_ended_at,
        "displayProductName": name_to_use[:100],
        "brand": product.brand or "Detailed Page",
        "generalProductName": name_to_use, # 보통 노출명과 동일
        "productOrigin": "수입산", # 위탁판매 기본
        "deliveryMethod": "SEQUENCIAL", # 일반 배송
        "deliveryCompanyCode": delivery_company_code,
        "deliveryChargeType": "FREE", # 일단 무료배송으로 시작
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
        "returnCharge": 5000, # 기본 반품비
        "deliveryChargeOnReturn": 5000,
        "outboundShippingPlaceCode": outbound_center_code,
        "vendorUserId": account.credentials.get("vendor_user_id", "user"), # Wing ID
        "requested": True, # 자동 승인 요청
        "items": [item_payload]
    }
    
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
    try:
        if os.getenv("COUPANG_ENABLE_CATEGORY_PREDICTION", "0") == "1":
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
                if code == 200 and pred_data.get("code") == "SUCCESS":
                    resp_data = pred_data.get("data")
                    if isinstance(resp_data, dict) and "predictedCategoryCode" in resp_data:
                        predicted_category_code = int(resp_data["predictedCategoryCode"])
                    elif isinstance(resp_data, (str, int)):
                        predicted_category_code = int(resp_data)
    except Exception as e:
        logger.info(f"카테고리 예측 스킵/실패: {e}")

    # 공시 메타
    notice_meta = None
    try:
        meta_http, meta_data = client.get_category_meta(str(predicted_category_code))
        if meta_http == 200 and isinstance(meta_data, dict) and isinstance(meta_data.get("data"), dict):
            notice_meta = meta_data["data"]
    except Exception:
        pass

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
