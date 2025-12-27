import logging
import uuid
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from app.db import get_session
from app.session_factory import session_factory
from app.models import MarketAccount, MarketListing, Product
from app.smartstore_client import SmartStoreClient

logger = logging.getLogger(__name__)


class SmartStoreSync:
    """
    네이버(스마트스토어) 동기화 및 상품 관리 서비스
    """

    def __init__(self, db: Session):
        self.db = db
        self.client: Optional[SmartStoreClient] = None

    def _get_client(self, account_id: uuid.UUID) -> Optional[SmartStoreClient]:
        """
        네이버 클라이언트 인스턴스를 가져옵니다.
        """
        from app.smartstore_client import SmartStoreClient

        # 계정 정보 조회
        account = self.db.get(MarketAccount, account_id)
        if not account:
            logger.error(f"Naver SmartStore account not found: {account_id}")
            return None

        # 네이버 API 자격 조회
        creds = account.credentials or {}
        client_id = creds.get("client_id")
        client_secret = creds.get("client_secret")

        if not client_id or not client_secret:
            logger.error(f"Naver SmartStore credentials not configured for account {account_id}")
            return None

        return SmartStoreClient(client_id, client_secret)

    def sync_products(self, market_code: str, account_id: uuid.UUID) -> int:
        """
        네이버 상품 목록을 동기화합니다.
        """
        if market_code != "SMARTSTORE":
            logger.warning(f"Unsupported market code: {market_code}")
            return 0

        # 클라이언트 인스턴스 획득
        if not self.client:
            self.client = self._get_client(account_id)
            if not self.client:
                logger.error(f"Failed to get SmartStore client for account {account_id}")
                return 0

        try:
            # 네이버 상품 목록 조회
            status_code, products_data = self.client.get_products(page=1, size=100)

            if status_code != 200:
                logger.error(f"Failed to fetch SmartStore products: {products_data.get('message', 'Unknown error')}")
                return 0

            synced_count = 0
            products = products_data.get("products", [])

            with session_factory() as tmp_db:
                for product in products:
                    # 기존 상품 확인
                    existing_product = tmp_db.query(Product).where(
                        Product.source == "smartstore",
                        Product.external_product_id == product.get("no", "")
                    ).first()

                    if existing_product:
                        # 기존 상품이 있으면 업데이트
                        existing_product.external_product_id = product.get("no", "")
                        existing_product.smartstore_status = product.get("displaySalesStatus", "SALE")
                        existing_product.smartstore_raw_data = product
                        tmp_db.commit()
                        synced_count += 1
                    else:
                        # 새 상품 생성
                        new_product = Product(
                            source="smartstore",
                            external_product_id=product.get("no", ""),
                            name=product.get("name", ""),
                            description=product.get("detailContent", ""),
                            price=product.get("salePrice", 0),
                            category_id=product.get("categoryNo", ""),
                            status="DRAFT",
                            smartstore_status="SYNCED",
                            smartstore_raw_data=product
                        )
                        tmp_db.add(new_product)
                        synced_count += 1

            logger.info(f"SmartStore product sync completed: {synced_count} products synced")
            return synced_count

        except Exception as e:
            logger.error(f"Error syncing SmartStore products: {e}", exc_info=True)
            return 0

    def register_product(
        self,
        market_code: str,
        account_id: uuid.UUID,
        product_id: uuid.UUID,
        payload_override: dict | None = None,
    ) -> Dict[str, Any]:
        """
        네이버에 상품을 등록합니다.
        """
        if market_code != "SMARTSTORE":
            logger.error(f"Unsupported market code: {market_code}")
            return {"status": "error", "message": f"Unsupported market: {market_code}"}

        # 클라이언트 인스턴스 획득
        if not self.client:
            self.client = self._get_client(account_id)
            if not self.client:
                return {"status": "error", "message": "Failed to get SmartStore client"}

        # 상품 정보 조회
        with session_factory() as tmp_db:
            product = tmp_db.get(Product, product_id)
            if not product:
                return {"status": "error", "message": f"Product not found: {product_id}"}

            # 네이버 API 등록 요청 준비
            name = product.processed_name or product.name or f"상품 {product.id}"
            sale_price = int(product.selling_price or 0)
            category_no = str(product.category_id or "").strip()
            if not category_no or category_no == "0":
                return {"status": "error", "message": "SmartStore categoryNo가 없습니다. 유효한 카테고리를 지정해 주세요."}
            if sale_price <= 0:
                return {"status": "error", "message": "SmartStore salePrice가 0입니다. 판매가를 설정해 주세요."}

            if payload_override is not None:
                if not isinstance(payload_override, dict):
                    return {"status": "error", "message": "payload는 object 형식이어야 합니다."}
                payload = payload_override
                payload.setdefault("name", name)
            else:
                payload = {
                    "name": name,
                    "detailContent": product.description or f"{name}의 상세 설명입니다.",
                    "salePrice": sale_price,
                    "categoryNo": category_no,
                    "displaySalesStatus": "SALE",
                    "channelType": "ONLINE",
                    "detailUrl": f"https://yourstore.com/products/{product.id}",
                }

            try:
                # 네이버 상품 등록
                status_code, response_data = self.client.create_product(payload)

                if status_code not in (200, 201):
                    logger.error(
                        "SmartStore registration failed (status=%s, message=%s, productId=%s)",
                        status_code,
                        response_data.get("message", "Unknown error"),
                        product.id,
                    )
                    return {
                        "status": "error",
                        "message": response_data.get("message", "Registration failed"),
                        "details": response_data,
                    }

                # 성공 시 Product 상태 업데이트
                product.smartstore_status = "REGISTERED"
                external_id = (
                    response_data.get("originProductNo")
                    or response_data.get("productNo")
                    or response_data.get("data")
                    or product.external_product_id
                )
                if external_id:
                    product.external_product_id = str(external_id)
                product.smartstore_raw_data = response_data
                tmp_db.commit()

                logger.info(f"Successfully registered product to SmartStore: {product.name}")

                return {
                    "status": "success",
                    "message": f"{product.name}이 네이버에 등록되었습니다."
                }

            except Exception as e:
                logger.error(f"Error registering product to SmartStore: {e}", exc_info=True)
                return {"status": "error", "message": str(e)}

    def delete_market_listing(self, market_code: str, account_id: uuid.UUID, market_item_id: str) -> Tuple[bool, str | None]:
        """
        네이버 상품 삭제 (미구현)
        """
        # TODO: 네이버 API의 상품 삭제 기능 구현 필요
        logger.warning(f"SmartStore product deletion not yet implemented for market_item_id: {market_item_id}")
        return False, "Not implemented"


def sync_smartstore_products(db: Session, account_id: uuid.UUID) -> int:
    """
    네이버 상품 동기화 함수 (호환용)
    """
    sync_service = SmartStoreSync(db)
    return sync_service.sync_products("SMARTSTORE", account_id)


def register_smartstore_product(
    db: Session,
    account_id: uuid.UUID,
    product_id: uuid.UUID,
    payload_override: dict | None = None,
) -> Dict[str, Any]:
    """
    네이버 상품 등록 함수 (호환용)
    """
    sync_service = SmartStoreSync(db)
    return sync_service.register_product(
        "SMARTSTORE",
        account_id,
        product_id,
        payload_override=payload_override,
    )


def delete_smartstore_listing(db: Session, account_id: uuid.UUID, market_item_id: str) -> Tuple[bool, str | None]:
    """
    네이버 상품 삭제 함수 (호환용)
    """
    sync_service = SmartStoreSync(db)
    return sync_service.delete_market_listing("SMARTSTORE", account_id, market_item_id)
