import logging
import uuid
from typing import Any, Dict, Tuple
from sqlalchemy.orm import Session

from app.models import MarketAccount, MarketRegistrationRetry, Product

try:
    from app.smartstore_sync import (
        sync_smartstore_products, 
        register_smartstore_product,
        delete_market_listing as delete_smartstore_listing,
        update_smartstore_price
    )
    from app.coupang_sync import (
        sync_coupang_products, 
        delete_market_listing as delete_coupang_listing,
        update_coupang_price
    )
except ImportError:
    sync_smartstore_products = None
    register_smartstore_product = None
    delete_smartstore_listing = None

logger = logging.getLogger(__name__)

class MarketService:
    def __init__(self, db: Session):
        self.db = db

    def _is_doc_related_error(self, message: str | None) -> bool:
        if not message:
            return False
        text = str(message).lower()
        keywords = [
            "서류",
            "인증",
            "kc",
            "전기",
            "어린이",
            "식품",
            "의료기기",
            "방송통신",
            "적합등록",
            "시험성적서",
            "certification",
            "document",
        ]
        return any(keyword in text for keyword in keywords)

    def _enqueue_registration_retry(self, product_id: uuid.UUID, market_code: str, reason: str | None) -> None:
        existing = (
            self.db.query(MarketRegistrationRetry)
            .filter(MarketRegistrationRetry.market_code == market_code)
            .filter(MarketRegistrationRetry.product_id == product_id)
            .first()
        )
        if existing:
            existing.status = "queued"
            existing.reason = reason
        else:
            self.db.add(
                MarketRegistrationRetry(
                    market_code=market_code,
                    product_id=product_id,
                    status="queued",
                    attempts=0,
                    reason=reason,
                )
            )
        self.db.commit()

    def _register_smartstore_fallback(
        self,
        product: Product,
        reason: str | None = None,
    ) -> Dict[str, Any]:
        from app.smartstore_sync import register_smartstore_product

        account = (
            self.db.query(MarketAccount)
            .filter(MarketAccount.market_code == "SMARTSTORE")
            .filter(MarketAccount.is_active.is_(True))
            .first()
        )
        if not account:
            return {"status": "error", "message": "No active SMARTSTORE account for fallback"}

        result = register_smartstore_product(self.db, account.id, product.id)
        if result.get("status") == "success":
            result["fallbackMarket"] = "SMARTSTORE"
            result["fallbackReason"] = reason
        return result

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
            from app.services.market_targeting import is_naver_fallback_disabled

            product = self.db.get(Product, product_id)
            success, msg = register_coupang_product(self.db, account_id, product_id)
            if success:
                return {"status": "success", "message": msg or "Registered successfully"}

            skip_message = str(msg) if msg is not None else ""
            fallback_disabled = bool(product) and is_naver_fallback_disabled(self.db, product)

            if msg and skip_message.startswith("SKIPPED:"):
                if not fallback_disabled and product:
                    fallback_result = self._register_smartstore_fallback(product, reason=skip_message)
                    if fallback_result.get("status") == "success":
                        return fallback_result
                return {"status": "skipped", "message": skip_message}

            if not fallback_disabled and product and self._is_doc_related_error(skip_message):
                fallback_result = self._register_smartstore_fallback(product, reason=skip_message)
                if fallback_result.get("status") == "success":
                    return fallback_result

            if product:
                self._enqueue_registration_retry(product.id, market_code, skip_message or "Registration failed")
            return {"status": "error", "message": msg or "Registration failed"}
        elif market_code == "SMARTSTORE":
            from app.smartstore_sync import register_smartstore_product
            result = register_smartstore_product(self.db, account_id, product_id)
            if result.get("status") == "success":
                return result
            else:
                return result
        else:
            return {"status": "error", "message": f"Unsupported market: {market_code}"}

    def update_price(self, market_code: str, account_id: uuid.UUID, market_item_id: str, price: int) -> Tuple[bool, str | None]:
        """마켓별 상품 가격 수정 실행"""
        if market_code == "COUPANG":
            return update_coupang_price(self.db, account_id, market_item_id, price)
        elif market_code == "SMARTSTORE":
            if update_smartstore_price:
                return update_smartstore_price(self.db, account_id, market_item_id, price)
            else:
                logger.warning("SmartStore price update function not implemented.")
                return False, "Not implemented"
        else:
            return False, f"Unsupported market: {market_code}"
