import logging
import uuid
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from app.db import get_session
from app.session_factory import session_factory
from app.models import MarketAccount, MarketListing, Product, ProductOption, SupplierItemRaw, MarketOrderRaw, Order, OrderItem
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
    if text == "0" or not text:
        return None
    return text


def _extract_category_no_from_raw(raw: dict) -> str | None:
    if not isinstance(raw, dict):
        return None
    
    # 1. 탑색형 카테고리 정보 우선 (상세한 키들 먼저 확인)
    for key in _CATEGORY_KEYS:
        if raw.get(key):
            return _coerce_category_no(raw.get(key))
            
    # 2. 'category' 객체 내부 확인 (OwnerClan 등)
    # 여기서 'key'를 확인하되, 최상위 'key'가 상품코드인 경우를 대비해 여기서만 확인
    category = raw.get("category")
    if isinstance(category, dict):
        for key in list(_CATEGORY_KEYS) + ["key"]:
            if category.get(key):
                return _coerce_category_no(category.get(key))
                
    # 3. 'metadata' 객체 내부 확인
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        for key in list(_CATEGORY_KEYS) + ["key"]:
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
    options: list | None = None,
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

    # 기본 상품 정보 구성
    origin_product = {
        "statusType": "SALE",
        "categoryNo": category_no,
        "leafCategoryId": category_no,
        "name": name,
        "detailContent": detail_content,
        "salePrice": sale_price,
        "stockQuantity": stock_quantity,
    }

    # 옵션 정보가 있는 경우 처리
    if options:
        # 1. 옵션 그룹명 추출 (예: "색상/사이즈" -> ["색상", "사이즈"])
        # 모든 옵션이 동일한 명칭 구조를 가진다고 가정
        first_opt_name = options[0].option_name if hasattr(options[0], "option_name") else "옵션"
        group_names = [gn.strip() for gn in first_opt_name.split("/") if gn.strip()]
        
        # 2. 조합형 옵션 생성
        combinations = []
        min_opt_price = sale_price # 원가 기준 최소가 계산용
        total_stock = 0
        
        for idx, opt in enumerate(options):
            opt_val = opt.option_value if hasattr(opt, "option_value") else "단품"
            opt_vals = [v.strip() for v in opt_val.split("/") if v.strip()]
            
            # 그룹 개수와 값 개수 맞춤
            while len(opt_vals) < len(group_names):
                opt_vals.append("-")
            opt_vals = opt_vals[:len(group_names)]
            
            opt_selling_price = int(opt.selling_price or 0)
            if opt_selling_price > 0 and opt_selling_price < min_opt_price:
                min_opt_price = opt_selling_price
                
            option_stock = max(int(opt.stock_quantity or 0), 0)
            combinations.append({
                "optionName1": opt_vals[0],
                "optionName2": opt_vals[1] if len(opt_vals) > 1 else None,
                "optionName3": opt_vals[2] if len(opt_vals) > 2 else None,
                "optionName4": opt_vals[3] if len(opt_vals) > 3 else None,
                "stockQuantity": option_stock,
                "price": opt_selling_price - sale_price, # 기준가(salePrice)와의 차액
                "sellerManagerCode": opt.external_option_key or str(getattr(opt, "id", idx)),
                "usable": True
            })
            total_stock += option_stock

        # 기준가를 최소가로 조정할 경우 차액(price) 재계산 필요
        # 단, 여기서는 단순화를 위해 최초 입력된 sale_price를 기준가로 사용
        
        origin_product["optionInfo"] = {
            "optionCombinationSortType": "CREATE_DATE_DESC",
            "optionCombinationGroupNames": {
                "optionGroupName1": group_names[0],
                "optionGroupName2": group_names[1] if len(group_names) > 1 else None,
                "optionGroupName3": group_names[2] if len(group_names) > 2 else None,
                "optionGroupName4": group_names[3] if len(group_names) > 3 else None,
            },
            "optionCombinations": combinations
        }
        # 조합형 옵션 사용 시 원상품 재고는 옵션 총합으로 설정
        origin_product["stockQuantity"] = total_stock

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
    origin_area_code: str | None,
    after_service_phone: str | None,
    after_service_director: str | None,
    notice_type: str | None,
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
    resolved_notice_type = notice_type or "ETC"
    if resolved_notice_type != "ETC":
        resolved_notice_type = "ETC"
    origin_area_info = None
    if origin_area_code:
        origin_area_info = {
            "originAreaCode": origin_area_code,
            "content": origin or content,
        }
        if str(origin_area_code).startswith("02"):
            origin_area_info["importer"] = manufacturer_value
    detail_attribute = {
        "afterServiceInfo": {
            "afterServiceContactNumber": after_service_value,
            "afterServiceGuideContent": "문의는 판매자에게 연락 바랍니다.",
            "afterServiceTelephoneNumber": after_service_value,
        },
        "minorPurchasable": True,
        "productCertificationInfos": certification_infos,
        "productInfoProvidedNotice": {
            "productInfoProvidedNoticeType": resolved_notice_type,
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
    if origin_area_info:
        detail_attribute["originAreaInfo"] = origin_area_info
    return detail_attribute


def _normalize_certification_infos(
    raw_value: object,
    allowed_kind_types: set[str] | None,
) -> list[dict]:
    items: list[dict] = []
    if isinstance(raw_value, list):
        items = [item for item in raw_value if isinstance(item, dict)]
    elif isinstance(raw_value, dict):
        items = [raw_value]
    if not items:
        return []
    if not allowed_kind_types:
        return items
    filtered: list[dict] = []
    for item in items:
        kind_type = (
            item.get("certificationKindType")
            or item.get("kindType")
            or item.get("certificationType")
            or item.get("certificationKindType")
        )
        if kind_type and kind_type not in allowed_kind_types:
            continue
        if kind_type and not item.get("certificationKindType"):
            item = dict(item)
            item["certificationKindType"] = kind_type
            item.setdefault("kindType", kind_type)
        if item.get("certificationName") and not item.get("name"):
            item = dict(item)
            item["name"] = item["certificationName"]
        filtered.append(item)
    return filtered


def _pick_notice_type(notice_items: list[dict]) -> str:
    types = [
        item.get("productInfoProvidedNoticeType")
        for item in notice_items
        if isinstance(item, dict)
    ]
    if "ETC" in types:
        return "ETC"
    for value in types:
        if value:
            return value
    return "ETC"


def _extract_smartstore_order_items(raw: dict) -> list[dict]:
    if not isinstance(raw, dict):
        return []
    for key in ("productOrderList", "productOrders", "productOrder", "orderItems", "items", "orderItem"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    data = raw.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("productOrderList", "productOrders", "productOrder", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]
    return []


def _extract_smartstore_order_id(raw: dict, item: dict | None = None) -> str | None:
    candidates = []
    if isinstance(raw, dict):
        candidates.extend([
            raw.get("orderId"),
            raw.get("order_id"),
            raw.get("orderNumber"),
            raw.get("orderNo"),
            raw.get("orderSeq"),
        ])
    if isinstance(item, dict):
        candidates.extend([
            item.get("orderId"),
            item.get("order_id"),
            item.get("orderNumber"),
            item.get("orderNo"),
            item.get("orderSeq"),
            item.get("productOrderId"),
        ])
    for value in candidates:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_smartstore_product_id(raw: dict, item: dict) -> str | None:
    candidates = [
        item.get("sellerProductId"),
        item.get("productId"),
        item.get("productNo"),
        item.get("originProductNo"),
        item.get("sellerProductNo"),
        raw.get("sellerProductId"),
        raw.get("productId"),
        raw.get("productNo"),
        raw.get("originProductNo"),
    ]
    for value in candidates:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_smartstore_option_key(item: dict) -> str | None:
    candidates = [
        item.get("optionManagementCode"),
        item.get("optionCode"),
        item.get("optionId"),
        item.get("sellerProductItemId"),
        item.get("sellerItemId"),
        item.get("optionNo"),
    ]
    for value in candidates:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


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

    def _get_category_detail(self, category_no: str) -> dict | None:
        status, data = self.client.get_category(category_no)
        if status != 200:
            logger.warning(
                "SmartStore category fetch failed (categoryNo=%s, status=%s, message=%s)",
                category_no,
                status,
                data,
            )
            return None
        return data if isinstance(data, dict) else None

    def _resolve_notice_type(self, category_detail: dict | None) -> str:
        if not category_detail:
            return "ETC"
        whole_name = category_detail.get("wholeCategoryName")
        if not whole_name:
            return "ETC"
        top_name = whole_name.split(">")[0].strip()
        status, categories = self.client.list_categories()
        if status != 200 or not isinstance(categories, list):
            logger.warning("SmartStore category list fetch failed (status=%s)", status)
            return "ETC"
        top_category = next(
            (
                item
                for item in categories
                if isinstance(item, dict)
                and item.get("name") == top_name
                and item.get("last") is False
            ),
            None,
        )
        if not top_category:
            return "ETC"
        top_id = top_category.get("id")
        if not top_id:
            return "ETC"
        status, notice_items = self.client.get_product_notice_types(str(top_id))
        if status != 200 or not isinstance(notice_items, list):
            logger.warning(
                "SmartStore notice types fetch failed (categoryId=%s, status=%s)",
                top_id,
                status,
            )
            return "ETC"
        return _pick_notice_type(notice_items)

    def _resolve_certification_infos(
        self,
        *,
        category_detail: dict | None,
        raw_value: object,
    ) -> list[dict]:
        allowed_kind_types: set[str] | None = None
        kc_required = False
        if isinstance(category_detail, dict):
            exceptional = category_detail.get("exceptionalCategories") or []
            kc_required = "KC_CERTIFICATION" in exceptional
            allowed_kind_types = set()
            for info in category_detail.get("certificationInfos", []) or []:
                if not isinstance(info, dict):
                    continue
                for kind in info.get("kindTypes") or []:
                    if kind:
                        allowed_kind_types.add(kind)
        normalized = _normalize_certification_infos(raw_value, allowed_kind_types)
        if not kc_required and normalized:
            normalized = [
                item
                for item in normalized
                if (
                    item.get("certificationKindType")
                    or item.get("kindType")
                    or item.get("certificationType")
                )
                not in {"KC_CERTIFICATION", "CHILD_CERTIFICATION"}
            ]
        if normalized and isinstance(category_detail, dict):
            kc_info = None
            for info in category_detail.get("certificationInfos", []) or []:
                if not isinstance(info, dict):
                    continue
                if "KC_CERTIFICATION" in (info.get("kindTypes") or []):
                    kc_info = info
                    break
            if kc_info:
                for item in normalized:
                    if not isinstance(item, dict):
                        continue
                    if item.get("certificationInfoId"):
                        continue
                    kind_type = (
                        item.get("certificationKindType")
                        or item.get("kindType")
                        or item.get("certificationType")
                    )
                    if kind_type == "KC_CERTIFICATION":
                        item.setdefault("certificationInfoId", kc_info.get("id"))
                        item.setdefault("certificationName", kc_info.get("name"))
                        item.setdefault("name", kc_info.get("name"))
        if normalized:
            return normalized
        if not kc_required:
            return []
        fallback_info = {}
        if isinstance(category_detail, dict):
            for info in category_detail.get("certificationInfos", []) or []:
                if not isinstance(info, dict):
                    continue
                kind_types = info.get("kindTypes") or []
                if "KC_CERTIFICATION" in kind_types:
                    fallback_info = {
                        "certificationInfoId": info.get("id"),
                        "certificationName": info.get("name"),
                        "name": info.get("name"),
                        "certificationKindType": "KC_CERTIFICATION",
                        "certificationType": "KC_CERTIFICATION",
                        "certificationNumber": "상세설명참조",
                    }
                    break
        if fallback_info:
            return [fallback_info]
        return []

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

    def sync_orders(
        self,
        market_code: str,
        account_id: uuid.UUID,
        limit: int | None = None,
    ) -> Dict[str, Any]:
        """
        SmartStore 주문 raw 데이터를 기반으로 Order/OrderItem을 생성합니다.
        """
        if market_code != "SMARTSTORE":
            logger.warning(f"Unsupported market code: {market_code}")
            return {"processed": 0, "created": 0, "skipped": 0, "failed": 0, "failures": []}

        processed = 0
        created = 0
        skipped = 0
        failed = 0
        failures: list[dict[str, Any]] = []

        q = (
            self.db.query(MarketOrderRaw)
            .filter(MarketOrderRaw.market_code == "SMARTSTORE")
            .filter(MarketOrderRaw.account_id == account_id)
            .order_by(MarketOrderRaw.fetched_at.desc())
        )
        if limit and limit > 0:
            q = q.limit(limit)

        rows = q.all()
        for row in rows:
            processed += 1
            raw = row.raw if isinstance(row.raw, dict) else {}
            if not raw:
                skipped += 1
                continue

            existing_order = self.db.query(Order).filter(Order.market_order_id == row.id).one_or_none()
            if existing_order:
                skipped += 1
                continue

            order_items = _extract_smartstore_order_items(raw)
            if not order_items:
                skipped += 1
                continue

            order_id = _extract_smartstore_order_id(raw, order_items[0]) or str(row.order_id)
            if not order_id:
                failed += 1
                failures.append({"orderId": row.order_id, "reason": "주문 ID를 찾을 수 없습니다"})
                continue

            recipient_name = (raw.get("receiverName") or raw.get("recipientName") or raw.get("receiver") or "").strip()
            recipient_phone = (
                raw.get("receiverPhoneNumber")
                or raw.get("receiverMobileNumber")
                or raw.get("recipientPhone")
                or raw.get("receiverPhone")
                or ""
            )
            recipient_phone = str(recipient_phone).strip()
            addr1 = (raw.get("receiverAddress1") or raw.get("address1") or raw.get("shippingAddress1") or "").strip()
            addr2 = (raw.get("receiverAddress2") or raw.get("address2") or raw.get("shippingAddress2") or "").strip()
            zipcode = (raw.get("receiverZipCode") or raw.get("zipCode") or raw.get("postalCode") or "").strip()
            recipient_address = addr1 if not addr2 else f"{addr1} {addr2}"

            order = Order(
                market_order_id=row.id,
                order_number=f"SS-{order_id}",
                status=raw.get("orderStatus") or raw.get("status") or "PAYMENT_COMPLETED",
                recipient_name=recipient_name or None,
                recipient_phone=recipient_phone or None,
                address=recipient_address or None,
                total_amount=0,
            )
            self.db.add(order)
            self.db.flush()

            # OrderItem 생성 (중복 방지)
            self.db.query(OrderItem).filter(OrderItem.order_id == order.id).delete()

            total_amount = 0
            for item in order_items:
                product_id = _extract_smartstore_product_id(raw, item)
                if not product_id:
                    failed += 1
                    failures.append({"orderId": order_id, "reason": "상품 식별자를 찾을 수 없습니다"})
                    continue

                listing = (
                    self.db.query(MarketListing)
                    .filter(MarketListing.market_account_id == account_id)
                    .filter(MarketListing.market_item_id == str(product_id))
                    .one_or_none()
                )
                product = None
                market_listing_id = None
                if listing:
                    market_listing_id = listing.id
                    product = self.db.get(Product, listing.product_id)
                else:
                    product = (
                        self.db.query(Product)
                        .filter(Product.source == "smartstore")
                        .filter(Product.external_product_id == str(product_id))
                        .one_or_none()
                    )

                if not product:
                    skipped += 1
                    failures.append({"orderId": order_id, "reason": f"Product 매핑 실패(product_id={product_id})"})
                    continue

                option_key = _extract_smartstore_option_key(item)
                option_name = item.get("optionName") or item.get("option") or item.get("optionValue")
                option_value = item.get("optionValue") or item.get("optionName") or item.get("option")
                option_match = None
                if option_key:
                    try:
                        option_uuid = uuid.UUID(option_key) if len(option_key) == 36 else None
                    except Exception:
                        option_uuid = None
                    option_match = (
                        self.db.query(ProductOption)
                        .filter(ProductOption.product_id == product.id)
                        .filter(
                            (ProductOption.external_option_key == option_key)
                            | (ProductOption.id == option_uuid if option_uuid else False)
                        )
                        .one_or_none()
                    )
                if not option_match and option_name and option_value:
                    # 1. Exact match attempt
                    option_match = (
                        self.db.query(ProductOption)
                        .filter(ProductOption.product_id == product.id)
                        .filter(ProductOption.option_name == str(option_name))
                        .filter(ProductOption.option_value == str(option_value))
                        .one_or_none()
                    )
                    
                    # 2. Normalized match fallback (ignore spaces/special chars)
                    if not option_match:
                        import re
                        def _norm(s): return re.sub(r'[^a-zA-Z0-9가-힣]', '', str(s or ""))
                        
                        norm_name = _norm(option_name)
                        norm_value = _norm(option_value)
                        
                        all_options = self.db.query(ProductOption).filter(ProductOption.product_id == product.id).all()
                        for opt in all_options:
                            if _norm(opt.option_name) == norm_name and _norm(opt.option_value) == norm_value:
                                option_match = opt
                                break
                                
                        # 3. Value-only match fallback (if name is missing or slightly different)
                        if not option_match:
                            for opt in all_options:
                                if _norm(opt.option_value) == norm_value:
                                    option_match = opt
                                    break

                quantity = _safe_int(item.get("quantity") or item.get("orderQuantity") or item.get("itemQuantity"), 1)
                unit_price = _safe_int(
                    item.get("unitPrice")
                    or item.get("salePrice")
                    or item.get("productPrice")
                    or item.get("price"),
                    0,
                )
                total_price = _safe_int(
                    item.get("totalPaymentAmount")
                    or item.get("totalPrice")
                    or item.get("paymentAmount"),
                    unit_price * quantity,
                )
                if total_price == 0:
                    total_price = unit_price * quantity
                total_amount += total_price

                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    market_listing_id=market_listing_id,
                    product_option_id=option_match.id if option_match else None,
                    external_item_id=str(
                        item.get("productOrderId")
                        or item.get("orderItemId")
                        or item.get("sellerProductItemId")
                        or ""
                    ),
                    product_name=str(item.get("productName") or item.get("name") or product.name),
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                )
                self.db.add(order_item)

            order.total_amount = total_amount
            self.db.commit()
            created += 1

        return {
            "processed": processed,
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "failures": failures[:50],
        }

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

            # 옵션 정보 조회
            options = product.options if product.options else []
            
            # 네이버 API 등록 요청 준비
            name = product.processed_name or product.name or f"상품 {product.id}"
            sale_price = int(product.selling_price or 0)
            
            # 옵션이 있는 경우 기준가(salePrice)를 옵션 최소가로 조정 (네이버 권장/필수)
            if options:
                opt_prices = [int(opt.selling_price) for opt in options if opt.selling_price]
                if opt_prices:
                    sale_price = min(opt_prices)
                option_total_stock = sum(int(opt.stock_quantity or 0) for opt in options)
                if option_total_stock <= 0:
                    return {
                        "status": "error",
                        "message": "SmartStore 옵션 재고가 0입니다. 재고를 확인해 주세요.",
                    }
            
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

            category_detail = self._get_category_detail(category_no)
            notice_type = self._resolve_notice_type(category_detail)

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
            certification_infos = self._resolve_certification_infos(
                category_detail=category_detail,
                raw_value=default_certification_infos,
            )
            kc_required = False
            if isinstance(category_detail, dict):
                exceptional = category_detail.get("exceptionalCategories") or []
                kc_required = "KC_CERTIFICATION" in exceptional
            if kc_required and not certification_infos:
                return {
                    "status": "error",
                    "message": "SmartStore KC 인증 대상 카테고리입니다. 계정 credentials.default_certification_infos를 설정해 주세요.",
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
                        origin_area_code=str(default_origin_area_code),
                        after_service_phone=default_after_service_phone,
                        after_service_director=default_after_service_director,
                        notice_type=notice_type,
                        certification_infos=certification_infos,
                    ),
                    image_urls=image_urls,
                    options=options,
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
                    msg = response_data.get("message", "Registration failed")
                    if "invalidInputs" in response_data:
                        msg += f" (invalidInputs: {response_data['invalidInputs']})"
                    
                    logger.error(
                        "SmartStore registration failed (status=%s, message=%s, productId=%s, response=%s)",
                        status_code,
                        msg,
                        product.id,
                        response_data
                    )
                    return {
                        "status": "error",
                        "message": msg,
                        "details": response_data,
                    }

                # 성공 시 MarketListing 생성 또는 업데이트
                external_id = str(
                    response_data.get("originProductNo")
                    or response_data.get("productNo")
                    or response_data.get("data")
                )
                
                # MarketListing 객체 생성/업데이트
                listing = tmp_db.query(MarketListing).filter(
                    MarketListing.market_account_id == account_id,
                    MarketListing.product_id == product_id
                ).first()
                
                if not listing:
                    listing = MarketListing(
                        product_id=product_id,
                        market_account_id=account_id,
                        market_item_id=external_id,
                        status="ACTIVE",
                        store_url=f"https://smartstore.naver.com/{account.name}/products/{external_id}"
                    )
                    tmp_db.add(listing)
                else:
                    listing.market_item_id = external_id
                    listing.status = "ACTIVE"
                
                # 상품 상태를 LISTED로 업데이트하여 중복 등록 방지
                product.processing_status = "LISTED"
                
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


def sync_smartstore_orders(
    db: Session,
    account_id: uuid.UUID,
    limit: int | None = None,
) -> Dict[str, Any]:
    """
    네이버 주문 동기화 함수 (호환용)
    """
    sync_service = SmartStoreSync(db)
    return sync_service.sync_orders("SMARTSTORE", account_id, limit=limit)


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


def update_smartstore_price(db: Session, account_id: uuid.UUID, market_item_id: str, price: int) -> Tuple[bool, str | None]:
    """
    네이버 상품 가격을 수정합니다.
    """
    sync_service = SmartStoreSync(db)
    client = sync_service._get_client(account_id)
    if not client:
        return False, "Failed to initialize SmartStore client"

    # 스마트스토어는 1원 단위 가능하지만, 보통 10원 단위 권장
    target_price = ((price + 9) // 10) * 10

    payload = {
        "originProduct": {
            "salePrice": target_price
        }
    }

    code, data = client.update_product(market_item_id, payload)
    if code != 200:
        msg = data.get("message", "Unknown error")
        if "invalidInputs" in data:
            msg += f" ({data['invalidInputs']})"
        return False, f"가격 수정 실패: {msg}"

    # DB 업데이트
    listing = db.execute(
        select(MarketListing)
        .where(MarketListing.market_account_id == account_id)
        .where(MarketListing.market_item_id == market_item_id)
    ).scalars().first()
    
    if listing:
        product = db.get(Product, listing.product_id)
        if product:
            product.selling_price = price
            db.commit()

    return True, "가격 수정 완료"
