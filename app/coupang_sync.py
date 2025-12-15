from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.coupang_client import CoupangClient
from app.models import MarketAccount, MarketProductRaw, SupplierRawFetchLog

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
                raw=p
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


def _log_fetch(
    session: Session, 
    account: MarketAccount, 
    endpoint: str, 
    request_payload: Any, 
    status: int, 
    response_payload: Any
) -> None:
    # Use existing SupplierRawFetchLog for simplicity, or create MarketRawFetchLog?
    # Schema plan only mentioned SupplierRawFetchLog. 
    # For now, let's skip logging to DB or reuse Supplier table with 'COUPANG' code?
    # SupplierRawFetchLog has 'account_id' but it might imply SupplierAccount.
    # Given the schemas, better to log only to stdout/logger for now unless we add MarketRawFetchLog.
    pass
