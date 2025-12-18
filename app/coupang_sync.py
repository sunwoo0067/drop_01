from __future__ import annotations

import logging
import uuid
from typing import Any
from datetime import datetime, timezone
import os

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
    SupplierOrder,
    Order,
)
from app.ownerclan_client import OwnerClanClient
from app.settings import settings

logger = logging.getLogger(__name__)


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


def sync_coupang_products(session: Session, account_id: uuid.UUID) -> int:
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


def _log_fetch(
    session: Session, 
    account: MarketAccount, 
    endpoint: str, 
    request_payload: Any, 
    status: int, 
    response_payload: Any
) -> None:
    # 기존 SupplierRawFetchLog를 재사용하거나 MarketRawFetchLog를 새로 생성해야 할까요?
    # 스키마 계획에서는 SupplierRawFetchLog만 언급되었습니다.
    # 당장은 DB 로깅을 건너뛰거나 'COUPANG' 코드로 Supplier 테이블을 재사용하는 것이 좋겠습니다.
    # SupplierRawFetchLog에는 'account_id'가 있지만 SupplierAccount를 의미할 수 있습니다.
    # 스키마를 고려할 때, MarketRawFetchLog를 추가하기 전까지는 stdout/logger에만 로깅하는 편이 낫습니다.
    pass


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

    processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    if len(processed_images) < 5:
        logger.error(
            f"쿠팡 등록을 위해서는 가공 이미지가 최소 5장 필요합니다(productId={product.id}, images={len(processed_images)})"
        )
        return False, f"쿠팡 등록을 위해서는 가공 이미지가 최소 5장 필요합니다(images={len(processed_images)})"

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"클라이언트 초기화 실패: {e}")
        return False, f"클라이언트 초기화 실패: {e}"

    # 1. 메타 데이터 준비
    return_center_code, outbound_center_code, delivery_company_code, _debug = _get_default_centers(client, account, session)
    if not return_center_code or not outbound_center_code:
        logger.error(f"기본 센터 정보 조회 실패: {_debug}")
        return False, f"기본 센터 정보 조회 실패: {_debug}"

    # 기본 매핑
    # 1.5 카테고리 예측
    predicted_category_code = 77800 # 기본값 (기타/미분류 등)
    try:
        if os.getenv("COUPANG_ENABLE_CATEGORY_PREDICTION", "0") != "1":
            raise RuntimeError("카테고리 예측 비활성화(COUPANG_ENABLE_CATEGORY_PREDICTION != 1)")

        agreed = False
        try:
            agreed_http, agreed_data = client.check_auto_category_agreed(str(account.credentials.get("vendor_id") or "").strip())
            if agreed_http == 200 and isinstance(agreed_data, dict) and agreed_data.get("code") == "SUCCESS":
                agreed = bool(agreed_data.get("data"))
            else:
                logger.warning(
                    f"카테고리 자동매칭 동의 여부 확인 실패: HTTP={agreed_http}, 응답={agreed_data}"
                )
        except Exception as e:
            logger.warning(f"카테고리 자동매칭 동의 여부 확인 중 오류 발생: {e}")

        # 가공된 이름 명 또는 원본 이름 사용
        pred_name = product.processed_name or product.name
        if not agreed:
            logger.info("카테고리 자동매칭 서비스 미동의로 예측을 건너뜁니다(기본 카테고리 사용)")
        else:
            code, pred_data = client.predict_category(pred_name)
            if code == 200 and pred_data.get("code") == "SUCCESS":
                 # 응답 구조: data -> predictedCategoryCode (문서/경험 기반 추정)
                 # 실제 응답이 {"data": {"predictedCategoryCode": "12345", ...}} 형태라고 가정
                 # 혹은 {"data": "12345"} 일 수도 있음. 가장 안전한 파싱 필요.
                 # 보통 쿠팡 응답은 `data` 필드에 결과를 담음.
                 resp_data = pred_data.get("data")
                 if isinstance(resp_data, dict) and "predictedCategoryCode" in resp_data:
                     predicted_category_code = int(resp_data["predictedCategoryCode"])
                     logger.info(f"카테고리 예측 성공: {pred_name} -> {predicted_category_code}")
                 elif isinstance(resp_data, (str, int)):
                     # 만약 data 자체가 코드라면
                     predicted_category_code = int(resp_data)
                     logger.info(f"카테고리 예측 성공 (Direct): {pred_name} -> {predicted_category_code}")
            else:
                logger.warning(f"카테고리 예측 실패: Code {code}, Msg {pred_data}")
    except Exception as e:
        logger.info(f"카테고리 예측 스킵/실패: {e}")

    notice_meta: dict[str, Any] | None = None
    try:
        meta_http, meta_data = client.get_category_meta(str(predicted_category_code))
        if meta_http == 200 and isinstance(meta_data, dict) and isinstance(meta_data.get("data"), dict):
            notice_meta = meta_data["data"]
    except Exception as e:
        logger.warning(f"카테고리 메타 조회 중 오류 발생: {e}")

    return_center_detail: dict[str, Any] | None = None
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
    except Exception as e:
        logger.warning(f"반품지 상세 조회 중 오류 발생: {e}")

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
    except Exception as e:
        logger.warning(f"오너클랜 배송비 추출 실패: {e}")

    payload = _map_product_to_coupang_payload(
        product,
        account,
        return_center_code,
        outbound_center_code,
        predicted_category_code,
        return_center_detail,
        notice_meta,
        shipping_fee,
        delivery_company_code,
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
    
    # MarketListing 생성 또는 업데이트
    stmt = insert(MarketListing).values(
        product_id=product.id,
        market_account_id=account.id,
        market_item_id=seller_product_id,
        status="ACTIVE" # 'requested' 플래그에 따라 IN_REVIEW 상태일 수도 있음
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["market_account_id", "market_item_id"],
        set_={"status": "ACTIVE", "linked_at": func.now()}
    )
    session.execute(stmt)
    
    product.processing_status = "COMPLETED"
    session.commit()
    
    logger.info(f"상품 등록 성공 (ID: {product.id}, sellerProductId: {seller_product_id})")
    return True, None


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
        if cached_return and cached_outbound and cached_delivery:
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
    delivery_company_code = "KDEXP"  # 기본값 (경동택배)
    if isinstance(outbound_data, dict):
        # v2 API Response check
        data_obj = outbound_data.get("data") if isinstance(outbound_data.get("data"), dict) else None
        content = (data_obj.get("content") if data_obj else outbound_data.get("content")) or []
        if content and isinstance(content[0], dict):
            # Typical keys: deliveryCompanyCodes (list) or usableDeliveryCompanies
            codes = content[0].get("deliveryCompanyCodes") or content[0].get("usableDeliveryCompanies")
            if isinstance(codes, list) and codes:
                first_code_entry = codes[0]
                if isinstance(first_code_entry, dict):
                    # dict 형태인 경우 (예: {'deliveryCompanyCode': '...', 'deliveryCompanyName': '...'})
                    # 문서상 여러 키 가능성 대비
                    delivery_company_code = (
                        first_code_entry.get("deliveryCompanyCode") or 
                        first_code_entry.get("code") or 
                        first_code_entry.get("id")
                    )
                else:
                    # str 형태인 경우
                    delivery_company_code = str(first_code_entry)
            
            if not delivery_company_code:
                logger.warning(f"지원 택배사 목록이 비어있거나 코드를 추출할 수 없습니다. 기본값 {delivery_company_code}를 사용합니다. (outbound_code={outbound_code})")
                delivery_company_code = "KDEXP"
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
    delivery_company_code: str = "KDEXP",
) -> dict[str, Any]:
    """
    내부 Product 모델을 쿠팡 API Payload로 매핑합니다.
    """
    
    # 가공된 이름이 있으면 사용, 없으면 원본 이름 사용
    name_to_use = product.processed_name if product.processed_name else product.name
    
    # 상세설명 (Contents)
    # 원본 텍스트라면 간단한 HTML 태그로 감쌈. 보통 공급사 데이터가 이미 HTML임.
    description_html = product.description or "<p>상세설명 없음</p>"
    
    # 이미지
    # 가공된 이미지 우선 사용
    images = []
    if product.processed_image_urls:
        # processed_image_urls는 JSONB 리스트
        img_list = product.processed_image_urls
        if isinstance(img_list, list):
            for url in img_list:
                image_type = "REPRESENTATION" if len(images) == 0 else "DETAIL"
                images.append({"imageOrder": len(images), "imageType": image_type, "vendorPath": url})
    
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

    base_price = int(product.selling_price or 0)
    ship_fee = int(shipping_fee or 0)
    if ship_fee < 0:
        ship_fee = 0
    total_price = base_price + ship_fee
    if total_price < 3000:
        total_price = 3000

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
        "contents": [
            {
                "contentsType": "HTML",
                "contentDetails": [{"content": description_html, "detailType": "TEXT"}] 
            }
        ],
        "notices": notices,
    }

    return_zip = None
    return_addr = None
    return_addr_detail = None
    return_phone = None
    return_name = None
    if isinstance(return_center_detail, dict):
        return_zip = return_center_detail.get("returnZipCode")
        return_addr = return_center_detail.get("returnAddress")
        return_addr_detail = return_center_detail.get("returnAddressDetail")
        return_phone = _normalize_phone(return_center_detail.get("companyContactNumber"))
        return_name = return_center_detail.get("shippingPlaceName")

    if not return_name:
        return_name = "반품지"

    now = datetime.now(timezone.utc)
    sale_started_at = now.strftime("%Y-%m-%dT%H:%M:%S")
    sale_ended_at = "2099-01-01T23:59:59"

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
