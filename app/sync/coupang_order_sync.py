from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import MarketAccount, Order, OrderItem, SyncRun
from app.services.sync_runner import SyncRunner
from app.coupang_client import CoupangClient

logger = logging.getLogger(__name__)

class CoupangOrderSync:
    """
    쿠팡 주문 증분 동기화 서비스.
    SyncRunner를 활용하여 중복 실행 방지 및 메트릭 기록을 수행함.
    """
    def __init__(self, session: Session, account: MarketAccount):
        self.session = session
        self.account = account
        self.client = self._get_client(account)
        # 계정별 고유 채널 생성
        self.runner = SyncRunner(session, vendor="coupang", channel=f"orders:{account.name}")

    def _get_client(self, account: MarketAccount) -> CoupangClient:
        creds = account.credentials
        return CoupangClient(
            access_key=creds.get("access_key"),
            secret_key=creds.get("secret_key"),
            vendor_id=creds.get("vendor_id")
        )

    def run(self):
        """동기화 실행 (SyncRunner 래퍼)"""
        self.runner.run(self._sync_logic, meta={"account_id": str(self.account.id)})

    def _sync_logic(self, sync_run: SyncRun):
        # 1. 동기화 구간 결정
        # 쿠팡 timeFrame은 최대 10분이지만, 일 단위 조회도 가능함.
        # 여기서는 안정적인 증분을 위해 ISO 포맷의 문자열 커서를 사용.
        if sync_run.cursor_before:
            try:
                # ISO 문자열 파싱 시도
                base_time = datetime.fromisoformat(sync_run.cursor_before)
                # 안정성을 위해 10분의 Overlap Window 적용
                start_time = base_time - timedelta(minutes=10)
            except ValueError:
                start_time = datetime.now(timezone.utc) - timedelta(days=1)
        else:
            # 초기 동기화는 1일 전부터
            start_time = datetime.now(timezone.utc) - timedelta(days=1)
        
        # 끝점 설정 (현재)
        end_time = datetime.now(timezone.utc)
        
        # 쿠팡 API 요구 포맷 (yyyy-MM-ddTHH:mm)
        fmt = "%Y-%m-%dT%H:%M"
        str_from = start_time.strftime(fmt)
        str_to = end_time.strftime(fmt)
        
        logger.info(f"[SYNC:COUPANG] Starting order sync for '{self.account.name}' from {str_from} to {str_to}")

        # 2. 주요 상태별 조회
        # 상태별로 루프를 도는 이유는 쿠팡 API 특성상 상태 필터가 필수인 경우가 많기 때문.
        # ACCEPT: 결제완료, INSTRUCT: 상품준비중, DEPARTURE: 배송지시, DELIVERING: 배송중, FINAL_DELIVERY: 배송완료
        target_statuses = ["ACCEPT", "INSTRUCT", "DEPARTURE", "DELIVERING", "FINAL_DELIVERY"]
        
        total_count = 0
        for status in target_statuses:
            count = self._fetch_and_process_status(sync_run, str_from, str_to, status)
            total_count += count
            
        logger.info(f"[SYNC:COUPANG] Finished order sync for '{self.account.name}'. Total processed: {total_count}")
        
        # 3. 다음 커서 저장
        sync_run.cursor_after = end_time.isoformat()

    def _fetch_and_process_status(self, sync_run: SyncRun, str_from: str, str_to: str, status: str) -> int:
        next_token = None
        processed_in_status = 0
        
        while True:
            code, data = self.client.get_order_sheets(
                created_at_from=str_from,
                created_at_to=str_to,
                status=status,
                next_token=next_token,
                search_type="timeFrame"
            )
            sync_run.api_calls += 1
            
            if code >= 400:
                logger.error(f"[SYNC:COUPANG] Failed to fetch {status} for {self.account.name}: {data}")
                self.runner.log_error(sync_run, "api", f"Status {status} fetch failed (HTTP {code})", raw=data)
                break
                
            orders = data.get("data", [])
            if not orders:
                break
                
            for raw_order in orders:
                try:
                    self._upsert_order(sync_run, raw_order)
                    processed_in_status += 1
                except Exception as e:
                    logger.exception(f"Failed to process Coupang order {raw_order.get('orderId')}")
                    self.runner.log_error(
                        sync_run, "order_processing", str(e), 
                        entity_id=str(raw_order.get("orderId")),
                        raw=raw_order
                    )
            
            next_token = data.get("nextToken")
            if not next_token:
                break
                
        return processed_in_status

    def _upsert_order(self, sync_run: SyncRun, raw: dict[str, Any]):
        vendor_order_id = str(raw.get("orderId"))
        
        # 1. 헤더(Order) Upsert
        # 상태 전이 가드: 이미 최종 상태(FINAL_DELIVERY)이거나 취소된 경우 업데이트 방지 고려 가능
        # 여기서는 단순하게 더 낮은 단계의 상태로 역행하는 것만 방지
        stmt = insert(Order).values(
            vendor_order_id=vendor_order_id,
            marketplace="COUPANG",
            status=raw.get("status"),
            recipient_name=raw.get("receiver", {}).get("name"),
            recipient_phone=raw.get("receiver", {}).get("safeNumber") or raw.get("receiver", {}).get("contactNumber"),
            address=f"{raw.get('receiver', {}).get('addr1', '')} {raw.get('receiver', {}).get('addr2', '')}".strip(),
            ordered_at=self._parse_iso_datetime(raw.get("orderedAt")),
            raw=raw,
            order_number=f"CP-{vendor_order_id}"
        ).on_conflict_do_update(
            index_elements=["vendor_order_id"],
            set_={
                "status": raw.get("status"),
                "raw": raw,
                "updated_at": datetime.now(timezone.utc)
            },
            # 배송 완료 상태에서는 업데이트를 막거나, 더 정교한 로직 필요 시 여기에 WHERE 추가
            # index_where=None, set_where=Order.status != 'FINAL_DELIVERY' 와 같이 사용 가능
            where=(Order.status != "FINAL_DELIVERY")
        ).returning(Order.id)
        
        order_uuid = self.session.execute(stmt).scalar()
        sync_run.write_count += 1
        
        # 2. 상세 아이템(OrderItem) Upsert
        items = raw.get("orderItems", [])
        for it in items:
            vendor_item_id = str(it.get("vendorItemId"))
            
            stmt_item = insert(OrderItem).values(
                order_id=order_uuid,
                vendor_item_id=vendor_item_id,
                vendor_sku=it.get("externalVendorSkuCode"),
                product_name=it.get("vendorItemName"),
                quantity=it.get("shippingCount", 1),
                unit_price=it.get("salesPrice", 0),
                total_price=it.get("orderPrice", 0),
                status=raw.get("status"),
                raw=it
            ).on_conflict_do_update(
                constraint="uq_order_items_order_vendor_item",
                set_={
                    "status": raw.get("status"),
                    "raw": it,
                    "updated_at": datetime.now(timezone.utc)
                }
            )
            
            self.session.execute(stmt_item)

    def _parse_iso_datetime(self, val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            # 쿠팡 ISO 포맷 (Z 포함 시 교체)
            dt_str = val.replace("Z", "+00:00")
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None
