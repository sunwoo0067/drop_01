from __future__ import annotations

import logging
import uuid
from typing import Any
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
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
    
    return CoupangClient(
        access_key=creds.get("access_key", ""),
        secret_key=creds.get("secret_key", ""),
        vendor_id=creds.get("vendor_id", "")
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


def register_product(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    """
    쿠팡에 상품을 등록합니다.
    성공 시 True, 실패 시 False를 반환합니다.
    """
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        logger.error(f"쿠팡 등록을 위한 계정이 유효하지 않습니다: {account_id}")
        return False
        
    product = session.get(Product, product_id)
    if not product:
        logger.error(f"상품을 찾을 수 없습니다: {product_id}")
        return False

    try:
        client = _get_client_for_account(account)
    except Exception as e:
        logger.error(f"클라이언트 초기화 실패: {e}")
        return False

    # 1. 데이터 준비
    # 설정에 제공되지 않은 경우 센터 코드를 자동 감지합니다 (현재는 첫 번째 사용 가능한 센터 조회)
    return_center_code, outbound_center_code = _get_default_centers(client)
    if not return_center_code or not outbound_center_code:
        logger.error("반품/출고지 센터 코드를 확인할 수 없습니다.")
        return False

    # 기본 매핑
    # 1.5 카테고리 예측
    predicted_category_code = 77800 # 기본값 (기타/미분류 등)
    try:
        # 가공된 이름 명 또는 원본 이름 사용
        pred_name = product.processed_name or product.name
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
        logger.warning(f"카테고리 예측 중 오류 발생: {e}")

    payload = _map_product_to_coupang_payload(product, account, return_center_code, outbound_center_code, predicted_category_code)
    
    # 2. API 호출
    code, data = client.create_product(payload)
    _log_fetch(session, account, "create_product", payload, code, data)

    # 성공 조건: HTTP 200 이면서 body의 code가 SUCCESS
    if code != 200 or data.get("code") != "SUCCESS":
        logger.error(f"상품 생성 실패 (ID: {product.id}). HTTP: {code}, Msg: {data}")
        # 처리 상태 업데이트
        product.processing_status = "FAILED"
        session.commit()
        return False

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
    return True


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


def _get_default_centers(client: CoupangClient) -> tuple[str | None, str | None]:
    """
    첫 번째로 사용 가능한 반품지 및 출고지 센터 코드를 조회합니다.
    Returns (return_center_code, outbound_center_code)
    """
    # 출고지 (Outbound)
    rc, data = client.get_outbound_shipping_centers(page_size=1)
    outbound_code = None
    if rc == 200 and data.get("data") and data["data"].get("content"):
        outbound_code = str(data["data"]["content"][0]["outboundShippingPlaceCode"])
        
    # 반품지 (Return)
    rc, data = client.get_return_shipping_centers(page_size=1)
    return_code = None
    if rc == 200 and data.get("data") and data["data"].get("content"):
        return_code = str(data["data"]["content"][0]["returnCenterCode"])
        
    return return_code, outbound_code


def _map_product_to_coupang_payload(
    product: Product, 
    account: MarketAccount, 
    return_center_code: str, 
    outbound_center_code: str,
    predicted_category_code: int = 77800
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
                 images.append({"imageOrder": len(images), "imageType": "REPRESENTATION", "vendorPath": url})
    
    # 가공된 이미지가 없을 경우 처리 방안 필요
    # 현재는 선행 단계에서 처리되었다고 가정함.
    if not images:
        pass

    # 아이템 (옵션)
    # 현재는 단일 옵션 매핑 (Drop 01 범위)
    # 변형 상품(옵션)이 있다면 반복문 필요
    item_payload = {
        "itemName": name_to_use[:150], # 최대 150자
        "originalPrice": product.selling_price, # 할인가 적용 시 정가를 높게 설정 가능
        "salePrice": product.selling_price,
        "maximumBuyCount": 100, # 기본값
        "images": images,
        "attributes": [], # TODO: 카테고리 속성 매핑 필요 (예측된 카테고리에 따라 필수 속성이 다름)
        "contents": [
            {
                "contentsType": "HTML",
                "contentDetails": [{"content": description_html, "detailType": "TEXT"}] 
            }
        ],
        "noticeCategories": [
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제품소재", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "색상", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "치수", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조자(수입자)", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조국", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "취급시 주의사항", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "품질보증기준", "content": "상세페이지 참조"},
             {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "A/S 책임자와 전화번호", "content": "상세페이지 참조"},
        ] # 위탁판매 특성상 안전하게 '기타 재화'로 기본 설정
    }

    payload = {
        "displayCategoryCode": predicted_category_code, 
        # 예측된 카테고리 코드를 사용.
        # 주의: 일부 카테고리는 필수 속성(attributes)이 없으면 등록 실패할 수 있음.
        # 향후 predict_category 응답에 포함된 attributes 메타데이터를 활용하여 자동 매핑 고도화 필요.
        "sellerProductName": name_to_use[:100],
        "vendorId": account.credentials.get("vendor_id"),
        "displayProductName": name_to_use[:100],
        "brand": product.brand or "Detailed Page",
        "generalProductName": name_to_use, # 보통 노출명과 동일
        "productOrigin": "수입산", # 위탁판매 기본
        "deliveryMethod": "SEQUENCIAL", # 일반 배송
        "deliveryCompanyCode": "KDEXP", # 기본 택배사 (경동? 설정값 확인 필요)
        "deliveryChargeType": "FREE", # 일단 무료배송으로 시작
        "returnCenterCode": return_center_code,
        "returnCharge": 5000, # 기본 반품비
        "outboundShippingPlaceCode": outbound_center_code,
        "vendorUserId": account.credentials.get("vendor_user_id", "user"), # Wing ID
        "requested": True, # 자동 승인 요청
        "items": [item_payload]
    }
    
    return payload
