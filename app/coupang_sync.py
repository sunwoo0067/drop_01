from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import MarketAccount, MarketListing, Product
from app.services.market.coupang.common import get_client_for_account, log_fetch
from app.services.market.coupang.registration import CoupangProductManager
from app.services.market.coupang.sync_service import CoupangSyncService

logger = logging.getLogger(__name__)

def register_product(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> tuple[bool, str | None]:
    manager = CoupangProductManager(session)
    return manager.register_product(account_id, product_id)

def update_product_on_coupang(session: Session, account_id: uuid.UUID, product_id: uuid.UUID) -> tuple[bool, str | None]:
    manager = CoupangProductManager(session)
    return manager.update_product(account_id, product_id)

def update_coupang_price(session: Session, account_id: uuid.UUID, market_item_id: str, sale_price: int) -> tuple[bool, str | None]:
    manager = CoupangProductManager(session)
    return manager.update_price(account_id, market_item_id, sale_price)

def delete_product_from_coupang(session: Session, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, str | None]:
    manager = CoupangProductManager(session)
    return manager.delete_product(account_id, seller_product_id)

def stop_product_sales(session: Session, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, str | None]:
    manager = CoupangProductManager(session)
    return manager.stop_sales(account_id, seller_product_id)

def register_products_bulk(session: Session, account_id: uuid.UUID, product_ids: list[uuid.UUID] | None = None) -> dict[str, int]:
    service = CoupangSyncService(session)
    return service.register_products_bulk(account_id, product_ids)

def sync_coupang_orders_raw(session: Session, account_id: uuid.UUID, created_at_from: str, created_at_to: str, **kwargs) -> int:
    service = CoupangSyncService(session)
    return service.sync_orders_raw(account_id, created_at_from, created_at_to, **kwargs)

def sync_coupang_returns_raw(session: Session, account_id: uuid.UUID, created_at_from: str, created_at_to: str, **kwargs) -> int:
    service = CoupangSyncService(session)
    return service.sync_returns_raw(account_id, created_at_from, created_at_to, **kwargs)

def sync_coupang_exchanges_raw(session: Session, account_id: uuid.UUID, created_at_from: str, created_at_to: str, **kwargs) -> int:
    service = CoupangSyncService(session)
    return service.sync_exchanges_raw(account_id, created_at_from, created_at_to, **kwargs)

def sync_market_listing_status(session: Session, listing_id: uuid.UUID) -> tuple[bool, str | None]:
    service = CoupangSyncService(session)
    return service.sync_market_listing_status(listing_id)

def fulfill_coupang_orders_via_ownerclan(session: Session, account_id: uuid.UUID, created_at_from: str, created_at_to: str, **kwargs) -> dict[str, Any]:
    service = CoupangSyncService(session)
    return service.fulfill_orders_via_ownerclan(account_id, created_at_from, created_at_to, **kwargs)

def sync_ownerclan_orders_to_coupang_invoices(
    session: Session,
    coupang_account_id: uuid.UUID,
    limit: int = 100,
    dry_run: bool = False,
    retry_count: int = 0
) -> dict[str, Any]:
    service = CoupangSyncService(session)
    return service.sync_ownerclan_orders_to_coupang_invoices(
        coupang_account_id=coupang_account_id,
        limit=limit,
        dry_run=dry_run,
        retry_count=retry_count
    )

def sync_coupang_inquiries(session: Session, account_id: uuid.UUID, days: int = 7) -> int:
    service = CoupangSyncService(session)
    return service.sync_inquiries(account_id, days)

def sync_coupang_settlements(session: Session, account_id: uuid.UUID) -> int:
    service = CoupangSyncService(session)
    return service.sync_settlements(account_id)

def update_product_delivery_info(session: Session, account_id: uuid.UUID, seller_product_id: str, **kwargs) -> tuple[bool, str | None]:
    manager = CoupangProductManager(session)
    # Redirect to appropriate method in manager
    return False, "Not implemented yet"
