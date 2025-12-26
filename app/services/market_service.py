import logging
import uuid
from typing import Any, Dict, Tuple
from sqlalchemy.orm import Session

from app.models import MarketAccount
from app.coupang_sync import sync_coupang_products, delete_market_listing as delete_coupang_listing
# smartstore_sync.py에 delete_market_listing이 아직 구현되지 않았을 수 있으므로 주의
try:
    from app.smartstore_sync import (
        sync_smartstore_products, 
        register_smartstore_product,
        delete_market_listing as delete_smartstore_listing
    )
except ImportError:
    sync_smartstore_products = None
    register_smartstore_product = None
    delete_smartstore_listing = None

logger = logging.getLogger(__name__)

class MarketService:
    def __init__(self, db: Session):
        self.db = db

    def sync_products(self, market_code: str, account_id: uuid.UUID, deep: bool = False) -> int:
        """마켓별 상품 동기화 실행"""
        if market_code == "COUPANG":
            return sync_coupang_products(self.db, account_id, deep=deep)
        elif market_code == "SMARTSTORE":
            if sync_smartstore_products:
                return sync_smartstore_products(self.db, account_id)
            else:
                logger.warning("SmartStore sync function not implemented.")
                return 0
        else:
            logger.error(f"Unsupported market code: {market_code}")
            return 0

    def delete_product(self, market_code: str, account_id: uuid.UUID, market_item_id: str) -> Tuple[bool, str | None]:
        """마켓별 상품 삭제 실행"""
        if market_code == "COUPANG":
            return delete_coupang_listing(self.db, account_id, market_item_id)
        elif market_code == "SMARTSTORE":
            if delete_smartstore_listing:
                return delete_smartstore_listing(self.db, account_id, market_item_id)
            else:
                logger.warning("SmartStore deletion function not found.")
                return False, "Not implemented"
        else:
            return False, f"Unsupported market: {market_code}"

    def register_product(self, market_code: str, account_id: uuid.UUID, product_id: uuid.UUID) -> Dict[str, Any]:
        """마켓별 상품 등록 실행"""
        if market_code == "COUPANG":
            from app.coupang_sync import register_product as register_coupang_product
            success, msg = register_coupang_product(self.db, account_id, product_id)
            if success:
                return {"status": "success", "message": msg or "Registered successfully"}
            else:
                return {"status": "error", "message": msg or "Registration failed"}
        elif market_code == "SMARTSTORE":
            from app.smartstore_sync import register_product as register_smartstore_product
            success, msg = register_smartstore_product(self.db, account_id, product_id)
            if success:
                return {"status": "success", "message": msg or "Registered successfully"}
            else:
                return {"status": "error", "message": msg or "Registration failed"}
        else:
            return {"status": "error", "message": f"Unsupported market: {market_code}"}
