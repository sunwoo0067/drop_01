from __future__ import annotations

import logging
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, insert, delete, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import (
    MarketAccount, MarketOrderRaw, Order, SupplierOrder, SupplierAccount,
    SupplierRawFetchLog, MarketListing, MarketProductRaw, Product, ProductOption, OrderItem,
    MarketInquiryRaw, MarketRevenueRaw, MarketSettlementRaw
)
from app.coupang_client import CoupangClient
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.market.coupang.common import get_client_for_account, log_fetch, log_registration_skip

logger = logging.getLogger(__name__)

def get_default_centers(client: CoupangClient, account: MarketAccount | None = None, session: Session | None = None) -> tuple[str | None, str | None, str | None, str]:
    if account is not None and isinstance(account.credentials, dict):
        cr = account.credentials
        if cr.get("default_return_center_code") and cr.get("default_outbound_shipping_place_code") and cr.get("default_delivery_company_code") == "CJGLS":
            return str(cr["default_return_center_code"]), str(cr["default_outbound_shipping_place_code"]), str(cr["default_delivery_company_code"]), "cached"
    
    def _extract_msg(rc: int, data: dict[str, Any]) -> str:
        code = data.get("code") if isinstance(data, dict) else None
        msg = (data.get("message") or data.get("msg")) if isinstance(data, dict) else None
        return f"http={rc}, code={code}, message={msg}"

    def _extract_first_code(data: dict[str, Any], keys: list[str]) -> str | None:
        if not isinstance(data, dict): return None
        data_obj = data.get("data") if isinstance(data.get("data"), dict) else None
        content = (data_obj.get("content") if data_obj else data.get("content")) or []
        if content and isinstance(content[0], dict):
            for k in keys:
                v = content[0].get(k)
                if v is not None: return str(v)
        return None

    def _extract_delivery_codes(entries: object) -> list[str]:
        if not isinstance(entries, list): return []
        codes = []
        for entry in entries:
            code = (entry.get("deliveryCompanyCode") or entry.get("deliveryCode") or entry.get("code") or entry.get("id")) if isinstance(entry, dict) else str(entry)
            if isinstance(code, str) and code.strip(): codes.append(code.strip())
        return codes

    out_rc, out_data = client.get_outbound_shipping_centers(page_size=10)
    out_code, del_code = None, "CJGLS"
    if isinstance(out_data, dict):
        data_obj = out_data.get("data") if isinstance(out_data.get("data"), dict) else None
        content = (data_obj.get("content") if data_obj else out_data.get("content")) or []
        if content:
            best = None
            for c in content:
                if not isinstance(c, dict) or not c.get("usable"): continue
                c_code = c.get("outboundShippingPlaceCode") or c.get("shippingPlaceCode") or c.get("placeCode")
                if not c_code: continue
                r_infos, d_codes = c.get("remoteInfos") or [], (c.get("deliveryCompanyCodes") or c.get("usableDeliveryCompanies") or [])
                rc_codes, dc_codes = _extract_delivery_codes(r_infos), _extract_delivery_codes(d_codes)
                has_cj_r, has_cj = "CJGLS" in rc_codes, "CJGLS" in dc_codes
                d_c = "CJGLS" if has_cj_r or has_cj else (rc_codes[0] if rc_codes else (dc_codes[0] if dc_codes else None))
                score = (10 if r_infos else 0) + (5 if has_cj_r else (3 if has_cj else 0))
                if best is None or score > best["score"]:
                    best = {"code": str(c_code), "delivery_code": d_c, "codes": dc_codes, "score": score}
                    if score >= 15: break
            if best:
                out_code = best["code"]
                del_code = best["delivery_code"] or (best["codes"][0] if best["codes"] else "CJGLS")

    ret_rc, ret_data = client.get_return_shipping_centers(page_size=10)
    ret_code = _extract_first_code(ret_data, ["returnCenterCode", "return_center_code"])
    debug = f"outbound({_extract_msg(out_rc, out_data)}), return({_extract_msg(ret_rc, ret_data)})"
    if ret_code and out_code and account is not None and session is not None:
        try:
            creds = dict(account.credentials)
            creds.update({"default_return_center_code": str(ret_code), "default_outbound_shipping_place_code": str(out_code), "default_delivery_company_code": del_code})
            account.credentials = creds
            session.commit()
        except: pass
    return ret_code, out_code, del_code, debug

class CoupangSyncService:
    def __init__(self, session: Session):
        self.session = session

    def sync_orders_raw(self, account_id: uuid.UUID, created_at_from: str, created_at_to: str, status: str | None = None, max_per_page: int = 50) -> int:
        account = self.session.get(MarketAccount, account_id)
        if not account or not account.is_active: return 0
        client = get_client_for_account(account)
        total, statuses, now = 0, ([status] if status else ["ACCEPT", "INSTRUCT"]), datetime.now(timezone.utc)
        for st in statuses:
            next_token = None
            while True:
                code, data = client.get_order_sheets(created_at_from=created_at_from, created_at_to=created_at_to, status=st, next_token=next_token, max_per_page=max_per_page)
                if code != 200: break
                content = data.get("data")
                if isinstance(content, dict): content = content.get("content")
                if not isinstance(content, list) or not content: break
                for row in content:
                    o_id = row.get("orderId") or row.get("shipmentBoxId") or row.get("id")
                    if not o_id: continue
                    row_store = dict(row)
                    row_store["_queryStatus"] = st
                    stmt = pg_insert(MarketOrderRaw).values(market_code="COUPANG", account_id=account.id, order_id=str(o_id), raw=row_store, fetched_at=now).on_conflict_do_update(index_elements=["market_code", "account_id", "order_id"], set_={"raw": row_store, "fetched_at": now})
                    self.session.execute(stmt)
                    total += 1
                self.session.commit()
                next_token = data.get("nextToken") or (data.get("data") or {}).get("nextToken")
                if not next_token: break
        return total

    def sync_returns_raw(self, account_id: uuid.UUID, created_at_from: str, created_at_to: str, cancel_type: str = "RETURN") -> int:
        account = self.session.get(MarketAccount, account_id)
        if not account or not account.is_active: return 0
        client = get_client_for_account(account)
        code, data = client.get_return_requests(created_at_from=created_at_from, created_at_to=created_at_to, cancel_type=cancel_type)
        if code != 200: return 0
        content = data.get("data")
        if not isinstance(content, list) or not content: return 0
        total, now = 0, datetime.now(timezone.utc)
        for row in content:
            r_id = row.get("receiptId")
            if not r_id: continue
            row_store = dict(row)
            row_store.update({"_cancelType": cancel_type, "_fetchType": "RETURN_REQUEST"})
            store_id = f"{'RET' if cancel_type == 'RETURN' else 'CAN'}-{r_id}"
            stmt = pg_insert(MarketOrderRaw).values(market_code="COUPANG", account_id=account.id, order_id=str(store_id), raw=row_store, fetched_at=now).on_conflict_do_update(index_elements=["market_code", "account_id", "order_id"], set_={"raw": row_store, "fetched_at": now})
            self.session.execute(stmt)
            total += 1
        self.session.commit()
        return total

    def sync_exchanges_raw(self, account_id: uuid.UUID, created_at_from: str, created_at_to: str, status: str | None = None) -> int:
        account = self.session.get(MarketAccount, account_id)
        if not account or not account.is_active: return 0
        client = get_client_for_account(account)
        code, data = client.get_exchange_requests(created_at_from=created_at_from, created_at_to=created_at_to, status=status)
        if code != 200: return 0
        content = data.get("data")
        if not isinstance(content, list) or not content: return 0
        total, now = 0, datetime.now(timezone.utc)
        for row in content:
            e_id = row.get("exchangeId")
            if not e_id: continue
            row_store = dict(row)
            row_store["_fetchType"] = "EXCHANGE_REQUEST"
            stmt = pg_insert(MarketOrderRaw).values(market_code="COUPANG", account_id=account.id, order_id=f"EXC-{e_id}", raw=row_store, fetched_at=now).on_conflict_do_update(index_elements=["market_code", "account_id", "order_id"], set_={"raw": row_store, "fetched_at": now})
            self.session.execute(stmt)
            total += 1
        self.session.commit()
        return total

    def sync_market_listing_status(self, listing_id: uuid.UUID) -> tuple[bool, str | None]:
        listing = self.session.get(MarketListing, listing_id)
        if not listing or not listing.market_account_id: return False, "Listing not found"
        account = self.session.get(MarketAccount, listing.market_account_id)
        if not account: return False, "Account not found"
        try:
            client = get_client_for_account(account)
            code, data = client.get_product(listing.market_item_id)
            if code != 200: return False, f"HTTP {code}"
            data_obj = data.get("data")
            if not data_obj: return False, "No data"
            sr = data_obj.get("status")
            sm = {"DENIED": "DENIED", "승인반려": "DENIED", "반려": "DENIED", "DELETED": "DELETED", "상품삭제": "DELETED", "APPROVAL_REQUESTED": "APPROVING", "승인대기중": "APPROVING", "IN_REVIEW": "IN_REVIEW", "심사중": "IN_REVIEW", "SAVED": "SAVED", "임시저장": "SAVED", "APPROVED": "APPROVED", "승인완료": "APPROVED", "PARTIAL_APPROVED": "PARTIAL_APPROVED", "부분승인완료": "PARTIAL_APPROVED"}
            sn = sm.get(sr.upper() if sr else "", sr.upper() if sr else None)
            listing.coupang_status = sn
            if sn == "DENIED":
                rh = data_obj.get("approvalStatusHistory")
                r = None
                if rh and isinstance(rh, list):
                    d = next((h for h in rh if h.get("statusName") in ("DENIED", "승인반려", "반려")), None)
                    if d: r = d
                if not r:
                    ex = data_obj.get("extraInfoMessage")
                    r = {"message": ex} if ex else {"message": "Unknown denial"}
                listing.rejection_reason = r
            else: listing.rejection_reason = None
            self.session.commit()
            return True, sn
        except Exception as e:
            self.session.rollback()
            return False, str(e)

    def register_products_bulk(self, account_id: uuid.UUID, product_ids: list[uuid.UUID] | None = None) -> dict[str, int]:
        account = self.session.get(MarketAccount, account_id)
        if not account: return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        from app.services.market.coupang.registration import CoupangProductManager
        manager = CoupangProductManager(self.session)
        stmt = select(Product).where(Product.status == "DRAFT").where(Product.processing_status == "COMPLETED")
        if product_ids: stmt = stmt.where(Product.id.in_(product_ids))
        products = self.session.scalars(stmt).all()
        res = {"total": len(products), "success": 0, "failed": 0, "skipped": 0}
        for p in products:
            ok, reason = manager.register_product(account.id, p.id)
            if ok:
                res["success"] += 1
                p.status = "ACTIVE"
            elif reason and reason.startswith("SKIPPED:"): res["skipped"] += 1
            else: res["failed"] += 1
            self.session.commit()
        return res

    def sync_inquiries(self, account_id: uuid.UUID, days: int = 7) -> int:
        account = self.session.get(MarketAccount, account_id)
        if not account or not account.is_active: return 0
        client = get_client_for_account(account)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        code, data = client.get_inquiries(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if code != 200: return 0
        content = data.get("data") or []
        total = 0
        for row in content:
            iq_id = row.get("inquiryId")
            if not iq_id: continue
            stmt = pg_insert(MarketInquiryRaw).values(market_code="COUPANG", account_id=account.id, inquiry_id=str(iq_id), raw=row, fetched_at=end).on_conflict_do_update(index_elements=["market_code", "account_id", "inquiry_id"], set_={"raw": row, "fetched_at": end})
            self.session.execute(stmt)
            total += 1
        self.session.commit()
        return total

    def sync_settlements(self, account_id: uuid.UUID) -> int:
        account = self.session.get(MarketAccount, account_id)
        if not account: return 0
        client = get_client_for_account(account)
        now = datetime.now(timezone.utc)
        target = (now - timedelta(days=30)).strftime("%Y-%m")
        code, data = client.get_settlements(target)
        if code != 200: return 0
        items = data.get("data") or []
        if not isinstance(items, list): items = [items]
        total = 0
        for item in items:
            stmt = pg_insert(MarketSettlementRaw).values(market_code="COUPANG", account_id=account.id, recognition_year_month=target, raw=item, fetched_at=now).on_conflict_do_update(index_elements=["market_code", "account_id", "recognition_year_month"], set_={"raw": item, "fetched_at": now})
            self.session.execute(stmt)
            total += 1
        self.session.commit()
        return total

    def fulfill_orders_via_ownerclan(
        self,
        account_id: uuid.UUID,
        created_at_from: str,
        created_at_to: str,
        status: str | None = None,
        max_per_page: int = 100,
        dry_run: bool = False,
        limit: int = 0,
    ) -> dict[str, Any]:
        """
        쿠팡 주문 정보를 바탕으로 오너클랜에 실제 발주를 진행합니다.
        """
        processed, succeeded, skipped, failed = 0, 0, 0, 0
        failures, skipped_details = [], []

        # 1) 최신 주문 원본 데이터 동기화
        self.sync_orders_raw(account_id, created_at_from, created_at_to, status=status, max_per_page=max_per_page)

        account = self.session.get(MarketAccount, account_id)
        owner_acc = self.session.query(SupplierAccount).filter(
            SupplierAccount.supplier_code == "ownerclan",
            SupplierAccount.user_type == "seller",
            SupplierAccount.is_primary == True
        ).one_or_none()
        
        if not account or not owner_acc:
            return {"error": "계정 정보를 찾을 수 없습니다."}

        owner_client = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            access_token=owner_acc.access_token
        )

        rows = (
            self.session.query(MarketOrderRaw)
            .filter(MarketOrderRaw.market_code == "COUPANG")
            .filter(MarketOrderRaw.account_id == account_id)
            .order_by(MarketOrderRaw.fetched_at.desc())
            .all()
        )

        for row in rows:
            if limit > 0 and processed >= limit:
                break

            processed += 1
            raw = row.raw
            order_id = row.order_id
            
            # 중복 체크
            existing_order = self.session.query(Order).filter(Order.market_order_id == row.id).first()
            if existing_order and existing_order.supplier_order_id:
                skipped += 1
                skipped_details.append(f"Order {order_id} already fulfilled.")
                continue

            try:
                # 주문 아이템 파싱 및 매칭
                items = raw.get("orderItems", [])
                if not items:
                    skipped += 1
                    continue

                order_items_to_create = []
                for item in items:
                    v_item_id = str(item.get("vendorItemId"))
                    listing = self.session.query(MarketListing).filter(
                        MarketListing.market_account_id == account_id,
                        MarketListing.market_item_id == str(item.get("sellerProductId"))
                    ).first()
                    
                    if not listing:
                        raise ValueError(f"No listing found for sellerProductId {item.get('sellerProductId')}")
                    
                    product = self.session.get(Product, listing.product_id)
                    p_code = product.supplier_product_code if product else None
                    if not p_code:
                        raise ValueError(f"Supplier product code missing for product {product.id}")

                    # 오너클랜 주문 생성 요청 준비
                    receiver = raw.get("receiver", {})
                    addr = receiver.get("address", "")
                    addr_detail = receiver.get("addressDetail", "")
                    
                    phone = receiver.get("contactNumber", "")
                    safe_phone = "".join(filter(str.isdigit, phone))
                    
                    order_payload = {
                        "p_code": p_code,
                        "p_option": item.get("sellerItemCode") or "",
                        "order_count": item.get("shippingCount", 1),
                        "receiver_name": receiver.get("name"),
                        "receiver_tel": safe_phone,
                        "receiver_zip": receiver.get("postCode"),
                        "receiver_addr": f"{addr} {addr_detail}".strip(),
                        "order_memo": item.get("deliveryMessage", ""),
                    }

                    if dry_run:
                        logger.info(f"[DRY-RUN] Would fulfill {order_id} via OwnerClan: {order_payload}")
                        continue

                    # 오너클랜 발주 API 호출
                    ok, res = owner_client.create_order(order_payload)
                    if not ok:
                        raise ValueError(f"OwnerClan API Error: {res}")
                    
                    supplier_order_id = res.get("order_id")
                    
                    # DB 기록
                    supplier_order = SupplierOrder(
                        supplier_code="ownerclan",
                        supplier_order_id=str(supplier_order_id),
                        status="PENDING"
                    )
                    self.session.add(supplier_order)
                    self.session.flush()

                    if not existing_order:
                        existing_order = Order(
                            market_order_id=row.id,
                            supplier_order_id=supplier_order.id,
                            status="PENDING",
                            order_at=datetime.now(timezone.utc)
                        )
                        self.session.add(existing_order)
                        self.session.flush()

                    order_item = OrderItem(
                        order_id=existing_order.id,
                        product_id=product.id,
                        market_order_item_id=str(item.get("orderItemId")),
                        quantity=item.get("shippingCount", 1),
                        unit_price=item.get("salesPrice", 0),
                        status="ACCEPTED"
                    )
                    self.session.add(order_item)
                
                self.session.commit()
                succeeded += 1
            except Exception as e:
                self.session.rollback()
                failed += 1
                failures.append(f"{order_id}: {str(e)}")
                logger.error(f"주문 처리 실패 ({order_id}): {e}")

        return {
            "processed": processed,
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "failures": failures[:50],
            "skippedDetails": skipped_details[:50]
        }

    def sync_ownerclan_orders_to_coupang_invoices(
        self,
        coupang_account_id: uuid.UUID,
        limit: int = 100,
        dry_run: bool = False,
        retry_count: int = 0,
    ) -> dict[str, int]:
        """
        오너클랜 주문의 송장 정보를 쿠팡에 반영합니다.
        """
        account = self.session.get(MarketAccount, coupang_account_id)
        if not account or not account.is_active:
            return {"processed": 0, "succeeded": 0, "failed": 0}

        client = get_client_for_account(account)

        # 1. 대상 주문 식별: Order <-> SupplierOrder(OwnerClan) 조인
        stmt = (
            select(Order, SupplierOrder, SupplierOrderRaw, MarketOrderRaw)
            .join(SupplierOrder, Order.supplier_order_id == SupplierOrder.id)
            .join(SupplierOrderRaw, (SupplierOrderRaw.order_id == SupplierOrder.supplier_order_id) & (SupplierOrderRaw.supplier_code == 'ownerclan'))
            .join(MarketOrderRaw, Order.market_order_id == MarketOrderRaw.id)
            .where(MarketOrderRaw.account_id == coupang_account_id)
            .where(SupplierOrder.status.in_(['PENDING', 'ACCEPTED']))
            .order_by(SupplierOrder.created_at.desc())
            .limit(limit)
        )
        
        rows = self.session.execute(stmt).all()
        
        processed = 0
        succeeded = 0
        failed = 0
        
        for order, s_order, s_raw, m_raw in rows:
            processed += 1
            s_data = s_raw.raw or {}
            m_data = m_raw.raw or {}
            
            # --- 2. 송장 확인 ---
            products = s_data.get("products") or []
            if not products:
                continue
                
            first_p = products[0]
            tracking = first_p.get("trackingNumber")
            ship_code = first_p.get("shippingCompanyCode") or "CJGLS"
            
            if not tracking:
                continue
                
            # --- 3. 쿠팡 업로드 ---
            coupang_order_id = m_raw.order_id
            m_items = m_data.get("orderItems") or []
            
            invoice_list = []
            for item in m_items:
                v_item_id = item.get("vendorItemId")
                if v_item_id:
                    invoice_list.append({
                        "orderId": int(coupang_order_id),
                        "vendorItemId": int(v_item_id),
                        "deliveryCompanyCode": str(ship_code),
                        "invoiceNumber": str(tracking),
                    })
            
            if not invoice_list:
                continue
                
            if dry_run:
                logger.info(f"[DRY-RUN] Would sync invoice for Order {coupang_order_id}: {tracking}")
                succeeded += 1
                continue
                
            try:
                code, resp = client.upload_invoices(invoice_list)
                if code < 300:
                    s_order.status = "SHIPPED"
                    order.status = "SHIPPED"
                    succeeded += 1
                else:
                    failed += 1
                    logger.error(f"Failed to upload invoice for {coupang_order_id}: {resp}")
            except Exception as e:
                failed += 1
                logger.error(f"Error syncing invoice for {coupang_order_id}: {e}")
                
        self.session.commit()
        return {"processed": processed, "succeeded": succeeded, "failed": failed}
