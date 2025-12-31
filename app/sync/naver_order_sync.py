from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import MarketAccount, Order, OrderItem, SyncRun
from app.services.sync_runner import SyncRunner
from app.smartstore_client import SmartStoreClient

logger = logging.getLogger(__name__)

class NaverOrderSync:
    """
    네이버 스마트스토어 주문 증분 동기화 서비스.
    """
    def __init__(self, session: Session, account: MarketAccount):
        self.session = session
        self.account = account
        self.client = self._get_client(account)
        self.runner = SyncRunner(session, vendor="naver", channel=f"orders:{account.name}")

    def _get_client(self, account: MarketAccount) -> SmartStoreClient:
        creds = account.credentials
        return SmartStoreClient(
            client_id=creds.get("client_id"),
            client_secret=creds.get("client_secret")
        )

    def run(self):
        self.runner.run(self._sync_logic, meta={"account_id": str(self.account.id)})

    def _sync_logic(self, sync_run: SyncRun):
        # 1. 동기화 구간 결정 (ISO 8601: yyyy-MM-ddTHH:mm:ss.SSS+ZONE)
        now = datetime.now(timezone.utc)
        if sync_run.cursor_before:
            try:
                base_time = datetime.fromisoformat(sync_run.cursor_before)
                # 10분 Overlap Window
                start_time = base_time - timedelta(minutes=10)
            except ValueError:
                start_time = now - timedelta(days=1)
        else:
            start_time = now - timedelta(days=1)
            
        str_from = start_time.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")
        
        logger.info(f"[SYNC:NAVER] Starting order sync for '{self.account.name}' from {str_from}")
        
        more_sequence = None
        total_count = 0
        
        while True:
            data = self.client.get_changed_product_orders(
                last_changed_from=str_from,
                more_sequence=more_sequence
            )
            sync_run.api_calls += 1
            
            # 응답 구조 확인 (네이버 API는 보통 "data" 또는 "contents" 필드 사용)
            # last-changed-statuses는 "data" 필드에 리스트를 담음
            items = data.get("data", [])
            if not items:
                break
                
            for item in items:
                try:
                    self._upsert_product_order(sync_run, item)
                    total_count += 1
                except Exception as e:
                    logger.exception(f"Failed to process Naver product order {item.get('productOrderNo')}")
                    self.runner.log_error(
                        sync_run, "order_processing", str(e),
                        entity_id=str(item.get("productOrderNo")),
                        raw=item
                    )
            
            # 다음 페이지 여부 확인
            more = data.get("more")
            if more and more.get("moreSequence"):
                more_sequence = more.get("moreSequence")
            else:
                break
                
        logger.info(f"[SYNC:NAVER] Finished order sync for '{self.account.name}'. Total processed: {total_count}")
        sync_run.cursor_after = now.isoformat()

    def _upsert_product_order(self, sync_run: SyncRun, item: dict[str, Any]):
        # Naver last-changed-statuses 의 개별 항목은 'productOrder' 객체를 포함함
        p_order = item.get("productOrder", {})
        if not p_order:
            logger.warning(f"No productOrder data in Naver item: {item.get('productOrderNo')}")
            return

        order_id = p_order.get("orderId")
        product_order_no = str(p_order.get("productOrderNo"))
        
        # 1. 헤더(Order) Upsert
        # 네이버는 여러 productOrderNo가 하나의 orderId를 공유함.
        # recipient 정보는 productOrder 레벨에 존재함.
        stmt = insert(Order).values(
            vendor_order_id=order_id,
            marketplace="NAVER",
            status=p_order.get("productOrderStatus"), # 내부 매핑 필요 시 수행
            recipient_name=p_order.get("shippingAddress", {}).get("name"),
            recipient_phone=p_order.get("shippingAddress", {}).get("tel1") or p_order.get("shippingAddress", {}).get("tel2"),
            address=f"{p_order.get('shippingAddress', {}).get('baseAddress', '')} {p_order.get('shippingAddress', {}).get('detailedAddress', '')}".strip(),
            ordered_at=self._parse_iso(p_order.get("orderDate")),
            raw=p_order,
            order_number=f"NV-{order_id}"
        ).on_conflict_do_update(
            index_elements=["vendor_order_id"],
            set_={
                "status": p_order.get("productOrderStatus"),
                "raw": p_order,
                "updated_at": datetime.now(timezone.utc)
            },
            where=(Order.status != "FINAL_DELIVERY")
        ).returning(Order.id)
        
        order_uuid = self.session.execute(stmt).scalar()
        sync_run.write_count += 1
        
        # 2. 아이템(OrderItem) Upsert
        stmt_item = insert(OrderItem).values(
            order_id=order_uuid,
            vendor_item_id=product_order_no,
            vendor_sku=p_order.get("sellerProductCode"),
            product_name=p_order.get("productName"),
            quantity=p_order.get("quantity", 1),
            unit_price=p_order.get("unitPrice", 0),
            total_price=p_order.get("totalPaymentAmount", 0),
            status=p_order.get("productOrderStatus"),
            raw=p_order
        ).on_conflict_do_update(
            constraint="uq_order_items_order_vendor_item",
            set_={
                "status": p_order.get("productOrderStatus"),
                "raw": p_order,
                "updated_at": datetime.now(timezone.utc)
            }
        )
        self.session.execute(stmt_item)

    def _parse_iso(self, val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None
