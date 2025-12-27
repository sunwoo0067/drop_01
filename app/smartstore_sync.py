import logging
import uuid
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from app.db import get_session
from app.session_factory import session_factory
from app.models import MarketAccount, MarketListing, Product, SupplierItemRaw
from app.smartstore_client import SmartStoreClient

logger = logging.getLogger(__name__)

_CATEGORY_KEYS = (
    "naverCategoryNo",
    "naver_category_no",
    "smartstoreCategoryNo",
    "smartstore_category_no",
    "smartstoreCategoryCode",
    "smartstore_category_code",
    "categoryNo",
    "category_no",
    "categoryId",
    "category_id",
    "cate_cd",
    "cateCd",
    "categoryCode",
    "category_code",
)


def _coerce_category_no(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _extract_category_no_from_raw(raw: dict) -> str | None:
    if not isinstance(raw, dict):
        return None
    for key in _CATEGORY_KEYS:
        if raw.get(key):
            return _coerce_category_no(raw.get(key))
    category = raw.get("category")
    if isinstance(category, dict):
        for key in _CATEGORY_KEYS:
            if category.get(key):
                return _coerce_category_no(category.get(key))
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        for key in _CATEGORY_KEYS:
            if metadata.get(key):
                return _coerce_category_no(metadata.get(key))
    return None


def _build_smartstore_payload(
    *,
    name: str,
    detail_content: str,
    sale_price: int,
    category_no: str,
    stock_quantity: int,
    detail_attribute: dict | None = None,
    image_urls: list[str] | None = None,
    origin: str | None = None,
    origin_area_code: str | None = None,
) -> dict:
    images_list = []
    for url in (image_urls or []):
        if url:
            images_list.append({"url": str(url)})
        if len(images_list) >= 10:
            break
    images = None
    if images_list:
        images = {
            "representativeImage": images_list[0],
            "optionalImages": images_list[1:],
        }
    origin_product = {
        "statusType": "SALE",
        "categoryNo": category_no,
        "leafCategoryId": category_no,
        "name": name,
        "detailContent": detail_content,
        "salePrice": sale_price,
        "stockQuantity": stock_quantity,
        "originArea": {
            "type": "IMPORT",
            "code": origin_area_code,
            "content": origin or "상세설명참조",
        },
    }
    if images:
        origin_product["images"] = images
    if detail_attribute:
        origin_product["detailAttribute"] = detail_attribute
    smartstore_channel_product = {
        "channelProductDisplayStatusType": "ON",
        "channelProductSaleStatusType": "ON",
        "channelProductType": "NORMAL",
        "channelProductName": name,
        "channelProductSalePrice": sale_price,
        "naverShoppingRegistration": False,
    }
    return {
        "originProduct": origin_product,
        "smartstoreChannelProduct": smartstore_channel_product,
    }


def _build_detail_attribute(
    *,
    raw_meta: dict | None,
    name: str,
    model_name: str | None,
    manufacturer: str | None,
    origin: str | None,
    after_service_phone: str | None,
    after_service_director: str | None,
    certification_infos: list[dict],
) -> dict:
    content = "상품상세참조"
    if isinstance(raw_meta, dict):
        notice = raw_meta.get("productNotificationInformation")
        if isinstance(notice, dict):
            category_specific = notice.get("categorySpecific")
            if isinstance(category_specific, list) and category_specific:
                content = " / ".join([str(item) for item in category_specific if item])
    manufacturer_value = manufacturer or origin or "상세설명참조"
    model_value = model_name or "상세설명참조"
    after_service_value = after_service_phone or "010-0000-0000"
    after_service_director_value = after_service_director or after_service_value
    return {
        "afterServiceInfo": {
            "afterServiceContactNumber": after_service_value,
            "afterServiceGuideContent": "문의는 판매자에게 연락 바랍니다.",
            "afterServiceTelephoneNumber": after_service_value,
        },
        "minorPurchasable": True,
        "originAreaInfo": {
            "originAreaInfoType": "IMPORT",
            "originAreaInfoContent": content,
        },
        "productCertificationInfos": certification_infos,
        "productInfoProvidedNotice": {
            "productInfoProvidedNoticeType": "ETC",
            "etc": {
                "itemName": name,
                "modelName": model_value,
                "manufacturer": manufacturer_value,
                "afterServiceDirector": after_service_director_value,
                "content": content,
            },
        },
        "sellerCodeInfo": {"sellerCode": "SKU"},
    }


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

    def _extract_category_no(self, product: Product, account: MarketAccount | None) -> str | None:
        raw_category = None
        if account:
            raw_category = (account.credentials or {}).get("default_category_no")

        raw_item = None
        if not raw_category and product.supplier_item_id:
            raw_item = self.db.get(SupplierItemRaw, product.supplier_item_id)
            raw_payload = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
            raw_category = _extract_category_no_from_raw(raw_payload)

        if not raw_category:
            raw_category = getattr(product, "processed_category", None)

        if raw_category is None:
            return None

        raw_category = str(raw_category).strip()
        if not raw_category or raw_category == "0":
            return None
        return raw_category

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
        account = self.db.get(MarketAccount, account_id)

        # 상품 정보 조회
        with session_factory() as tmp_db:
            product = tmp_db.get(Product, product_id)
            if not product:
                return {"status": "error", "message": f"Product not found: {product_id}"}

            # 네이버 API 등록 요청 준비
            name = product.processed_name or product.name or f"상품 {product.id}"
            sale_price = int(product.selling_price or 0)
            stock_quantity = int(getattr(product, "stock_quantity", 0) or 0)
            if stock_quantity <= 0:
                stock_quantity = 9999
            if sale_price > 0:
                sale_price = (sale_price // 10) * 10
            category_no = _coerce_category_no(self._extract_category_no(product, account))
            if not category_no:
                return {
                    "status": "error",
                    "message": "SmartStore categoryNo가 없습니다. 계정 credentials.default_category_no 또는 상품/원본 카테고리를 지정해 주세요.",
                }
            if sale_price <= 0:
                return {"status": "error", "message": "SmartStore salePrice가 0입니다. 판매가를 설정해 주세요."}

            raw_item = None
            raw_meta = None
            raw_payload = None
            if product.supplier_item_id:
                raw_item = tmp_db.get(SupplierItemRaw, product.supplier_item_id)
                raw_payload = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else None
                raw_meta = raw_payload.get("metadata") if isinstance(raw_payload, dict) else None

            account_creds = account.credentials if account else {}
            default_origin_area_code = (account_creds or {}).get("default_origin_area_code")
            default_after_service_phone = (account_creds or {}).get("after_service_phone")
            default_after_service_director = (account_creds or {}).get("after_service_director")
            default_certification_infos = (account_creds or {}).get("default_certification_infos")
            if not default_origin_area_code:
                return {
                    "status": "error",
                    "message": "SmartStore originArea code가 없습니다. 계정 credentials.default_origin_area_code를 설정해 주세요.",
                }
            certification_infos = []
            if isinstance(default_certification_infos, list):
                certification_infos = [c for c in default_certification_infos if isinstance(c, dict)]
            elif isinstance(default_certification_infos, dict):
                certification_infos = [default_certification_infos]
            if not certification_infos:
                return {
                    "status": "error",
                    "message": "SmartStore certification 정보가 없습니다. 계정 credentials.default_certification_infos를 설정해 주세요.",
                }

            if payload_override is not None:
                if not isinstance(payload_override, dict):
                    return {"status": "error", "message": "payload는 object 형식이어야 합니다."}
                payload = dict(payload_override)
                payload.setdefault("name", name)
                payload.setdefault("categoryNo", category_no)
            else:
                image_urls = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
                if not image_urls and isinstance(raw_payload, dict):
                    image_urls = raw_payload.get("images") if isinstance(raw_payload.get("images"), list) else []
                if image_urls:
                    uploaded_urls = self.client.upload_images(image_urls)
                    if uploaded_urls:
                        image_urls = uploaded_urls
                if not image_urls:
                    return {"status": "error", "message": "SmartStore 등록을 위해 이미지가 필요합니다."}
                payload = _build_smartstore_payload(
                    name=name,
                    detail_content=product.description or f"{name}의 상세 설명입니다.",
                    sale_price=sale_price,
                    category_no=category_no,
                    stock_quantity=stock_quantity,
                    detail_attribute=_build_detail_attribute(
                        raw_meta=raw_meta,
                        name=name,
                        model_name=(raw_payload or {}).get("model") if isinstance(raw_payload, dict) else None,
                        manufacturer=(raw_payload or {}).get("manufacturer") if isinstance(raw_payload, dict) else None,
                        origin=(raw_payload or {}).get("origin") if isinstance(raw_payload, dict) else None,
                        after_service_phone=default_after_service_phone,
                        after_service_director=default_after_service_director,
                        certification_infos=certification_infos,
                    ),
                    image_urls=image_urls,
                    origin=(raw_payload or {}).get("origin") if isinstance(raw_payload, dict) else None,
                    origin_area_code=str(default_origin_area_code),
                )

            try:
                # 네이버 상품 등록
                origin_payload = payload.get("originProduct") or {}
                detail_attribute = origin_payload.get("detailAttribute") or {}
                logger.info(
                    "SmartStore create payload keys(productId=%s, keys=%s, originKeys=%s, images=%s, originArea=%s, certificationInfos=%s)",
                    product.id,
                    list(payload.keys()),
                    list(origin_payload.keys()),
                    origin_payload.get("images"),
                    origin_payload.get("originArea"),
                    detail_attribute.get("productCertificationInfos"),
                )
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
