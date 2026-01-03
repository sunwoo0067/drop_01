from __future__ import annotations

import logging
import uuid
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Tuple

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.models import (
    Product, MarketAccount, MarketListing, CoupangCategoryMetaCache,
    ProductOption, OrderItem
)
from app.settings import settings
from app.services.market.coupang.common import log_fetch, log_registration_skip, get_client_for_account
from app.services.market.coupang.policy import (
    SkipCoupangRegistrationError, CoupangDocumentPendingError, CoupangNeverEligibleError,
    _lookup_proven_payload_template, _extract_required_doc_templates, _required_doc_applies,
    _get_document_library_entry
)
from app.services.market.coupang.html_utils import normalize_detail_html_for_coupang
from app.services.market.coupang.image_utils import get_original_image_urls

logger = logging.getLogger(__name__)

def preserve_detail_html(product: Product | None = None) -> bool:
    if product is None: return False
    if product.processing_status in ("PENDING", "PROCESSING"): return False
    return True

class CoupangProductManager:
    def __init__(self, session: Session):
        self.session = session

    def register_product(self, account_id: uuid.UUID, product_id: uuid.UUID) -> tuple[bool, str | None]:
        account = self.session.get(MarketAccount, account_id)
        product = self.session.get(Product, product_id)
        if not account or not product: return False, "Invalid account or product"
        if getattr(product, "coupang_eligibility", "") == "NEVER": return False, "SKIPPED: NEVER"

        images = get_original_image_urls(self.session, product) or product.processed_image_urls or []
        images = list(dict.fromkeys([u.strip() for u in images if isinstance(u, str) and u.strip()]))[:9]
        if not images: return False, "SKIPPED: No images"

        try:
            client = get_client_for_account(account)
            meta = self._get_metadata(client, account, product)
            payload = self._map_payload(product, account, **meta, image_urls=images)
            code, data = client.create_product(payload)
            log_fetch(self.session, account, "create_product", payload, code, data)
            if code != 200 or data.get("code") != "SUCCESS": return False, f"Failed: {data.get('message')}"
            
            seller_id = str(data.get("data"))
            stmt = insert(MarketListing).values(
                product_id=product.id, market_account_id=account.id, market_item_id=seller_id,
                status="ACTIVE", coupang_status="IN_REVIEW", category_code=str(meta["predicted_category_code"]),
                category_grade="VERIFIED_EXACT" if product.coupang_category_source == "PREDICTED" else "FALLBACK_SAFE"
            ).on_conflict_do_update(index_elements=["market_account_id", "market_item_id"], set_={"status": "ACTIVE", "linked_at": func.now(), "coupang_status": "IN_REVIEW"})
            self.session.execute(stmt)
            product.processing_status = "LISTED"
            product.coupang_doc_pending = False
            self.session.commit()
            return True, None
        except Exception as e:
            self.session.rollback()
            return False, str(e)

    def _get_metadata(self, client: Any, account: MarketAccount, product: Product) -> dict[str, Any]:
        """
        쿠팡 상품 등록/수정에 필요한 메타데이터 정보를 준비합니다.
        """
        from app.services.market.coupang.sync_service import get_default_centers
        from app.services.market.coupang.policy import (
            check_coupang_daily_limit, check_coupang_fallback_ratio, check_fallback_cooldown,
            score_category_safety, _needs_heavy_docs
        )

        return_center_code, outbound_center_code, delivery_company_code, _debug = get_default_centers(client, account, self.session)
        if not return_center_code or not outbound_center_code:
            raise SkipCoupangRegistrationError(f"기본 센터 정보 조회 실패: {_debug}")

        # 카테고리 예측 및 선정 로직
        predicted_category_code = 77800
        predicted_from_ai = False
        category_name = None
        try:
            from app.services.market_targeting import resolve_supplier_category_name
            category_name = resolve_supplier_category_name(self.session, product)
        except Exception:
            category_name = None

        def _is_unknown_category(name: str | None) -> bool:
            if not name: return True
            normalized = str(name).strip().lower()
            return not normalized or normalized in {"unknown", "n/a", "na", "none", "-", "null"}

        allow_prediction = os.getenv("COUPANG_ENABLE_CATEGORY_PREDICTION", "1") == "1"
        if _is_unknown_category(category_name) and os.getenv("COUPANG_PREDICT_ON_UNKNOWN", "1") == "1":
            allow_prediction = True

        try:
            if allow_prediction:
                pred_name = product.processed_name or product.name
                code, pred_data = client.predict_category(pred_name)
                if code == 200 and isinstance(pred_data, dict):
                    resp_data = pred_data.get("data")
                    if resp_data:
                        if isinstance(resp_data, dict):
                            predicted_category_code = int(resp_data.get("predictedCategoryCode") or resp_data.get("predictedCategoryId") or predicted_category_code)
                            predicted_from_ai = True
                        elif isinstance(resp_data, (str, int)):
                            predicted_category_code = int(resp_data)
                            predicted_from_ai = True
        except Exception as e:
            logger.info(f"카테고리 예측 스킵/실패: {e}")

        if _is_unknown_category(category_name) and allow_prediction and not predicted_from_ai:
            raise SkipCoupangRegistrationError("카테고리 예측 실패(unknown)")

        # 공시 메타 조회
        notice_meta = self._fetch_category_meta(client, predicted_category_code)
        
        # 안전성 및 Fallback 체크
        unsafe_predicted = False
        if predicted_from_ai:
            safety_score, _ = score_category_safety(notice_meta, product)
            unsafe_predicted = safety_score < 0

        _, grade = _lookup_proven_payload_template(self.session, predicted_category_code)
        product.coupang_category_source = "PREDICTED"
        product.coupang_fallback_used = False

        if grade != "VERIFIED_EXACT" and (_needs_heavy_docs(notice_meta) or unsafe_predicted):
            if settings.coupang_stability_mode:
                raise SkipCoupangRegistrationError(f"안정 모드로 인해 위험 카테고리 등록 제한됨: {predicted_category_code}")
            
            if check_coupang_fallback_ratio(self.session, account.id):
                raise SkipCoupangRegistrationError(f"Fallback 등록 비율 제한 초과: {predicted_category_code}")

            fallback_raw = settings.coupang_fallback_category_codes
            fallback_codes = [int(s.strip()) for s in fallback_raw.split(",") if s.strip().isdigit()]

            for f_code in fallback_codes:
                if f_code == predicted_category_code: continue
                if check_fallback_cooldown(self.session, account.id, str(f_code)): continue
                
                f_meta = self._fetch_category_meta(client, f_code)
                if not _needs_heavy_docs(f_meta):
                    predicted_category_code = f_code
                    notice_meta = f_meta
                    product.coupang_category_source = "FALLBACK_SAFE"
                    product.coupang_fallback_used = True
                    break
            else:
                if _needs_heavy_docs(notice_meta) or unsafe_predicted:
                    raise SkipCoupangRegistrationError(f"위험 카테고리 및 대체 카테고리 없음: {predicted_category_code}")

        if check_coupang_daily_limit(self.session, account.id):
            raise SkipCoupangRegistrationError(f"쿠팡 일일 등록 제한 초과 ({settings.coupang_daily_limit}건)")

        return {
            "predicted_category_code": predicted_category_code,
            "notice_meta": notice_meta,
            "return_center_code": return_center_code,
            "outbound_center_code": outbound_center_code,
            "delivery_company_code": delivery_company_code,
            "return_center_detail": {}, 
            "shipping_fee": 0,
        }

    def _fetch_category_meta(self, client: Any, code: int) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        cached = self.session.query(CoupangCategoryMetaCache).filter(CoupangCategoryMetaCache.category_code == str(code)).first()
        if cached and cached.expires_at and cached.expires_at > now: return cached.meta
        rc, data = client.get_category_meta(str(code))
        if rc == 200 and isinstance(data, dict) and data.get("data"):
            meta = data["data"]
            exp = now + timedelta(hours=24)
            if cached: cached.meta, cached.fetched_at, cached.expires_at = meta, now, exp
            else: self.session.add(CoupangCategoryMetaCache(category_code=str(code), meta=meta, fetched_at=now, expires_at=exp))
            self.session.commit()
            return meta
        return cached.meta if cached else None

    def _map_payload(
        self,
        product: Product,
        account: MarketAccount, 
        return_center_code: str, 
        outbound_center_code: str,
        predicted_category_code: int = 77800,
        return_center_detail: dict[str, Any] | None = None,
        notice_meta: dict[str, Any] | None = None,
        shipping_fee: int = 0,
        delivery_company_code: str = "CJGLS",
        image_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        내부 Product 모델을 쿠팡 API Payload로 매핑합니다.
        """
        from app.services.market.coupang.html_utils import (
            normalize_detail_html_for_coupang, detail_html_has_images, find_forbidden_tags
        )
        from app.services.market.coupang.image_utils import build_contents_image_blocks

        name_to_use = product.processed_name if product.processed_name else product.name
        template, grade = _lookup_proven_payload_template(self.session, predicted_category_code)
        template_attrs = {}
        template_notices = {}
        if template:
            t_items = template.get("items", [])
            if t_items and isinstance(t_items[0], dict):
                for a in t_items[0].get("attributes", []):
                    template_attrs[a.get("attributeTypeName")] = a.get("attributeValueName")
                for n in t_items[0].get("notices", []):
                    template_notices[n.get("noticeCategoryDetailName")] = n.get("content")

        processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
        payload_images = image_urls if image_urls else processed_images
        
        raw_desc = product.description or "<p>상세설명 없음</p>"
        if preserve_detail_html(product):
            description_html = str(raw_desc)[:200000]
        else:
            description_html = normalize_detail_html_for_coupang(str(raw_desc)[:200000])
        
        forbidden = find_forbidden_tags(description_html)
        if forbidden: logger.warning(f"상세페이지 금지 태그 감지: {product.id}, {forbidden}")
        
        contents_blocks = []
        if payload_images and (not preserve_detail_html(product)) and not detail_html_has_images(description_html):
            contents_blocks = build_contents_image_blocks(payload_images)
        
        images_payload = []
        if payload_images:
            for i, url in enumerate(payload_images[:10]):
                img_type = "REPRESENTATION" if i == 0 else "DETAIL"
                images_payload.append({"imageOrder": i, "imageType": img_type, "vendorPath": url})

        def _normalize_phone(value: object) -> str | None:
            if value is None: return None
            s = str(value).strip()
            if not s: return None
            if s.startswith("+82"): s = "0" + s[3:]
            digits = "".join([c for c in s if c.isdigit()])
            if not digits: return None
            if len(digits) == 11: return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
            if len(digits) == 10: return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
            return digits

        # notices mapping
        notices = []
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("noticeCategories"), list):
            cats = [c for c in notice_meta["noticeCategories"] if isinstance(c, dict)]
            selected = next((c for c in cats if c.get("noticeCategoryName") == "기타 재화"), cats[0] if cats else None)
            if selected and isinstance(selected.get("noticeCategoryDetailNames"), list):
                for d in selected["noticeCategoryDetailNames"]:
                    if d.get("required") == "MANDATORY":
                        dn = d.get("noticeCategoryDetailName")
                        notices.append({
                            "noticeCategoryName": selected.get("noticeCategoryName"),
                            "noticeCategoryDetailName": dn,
                            "content": template_notices.get(dn, "상세페이지 참조")
                        })
        if not notices:
            notices = [{"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": d, "content": "상세페이지 참조"} for d in ["품명 및 모델명", "인증/허가 사항", "제조국(원산지)", "제조자(수입자)", "소비자상담 관련 전화번호"]]

        # attributes mapping
        item_attributes = []
        if isinstance(notice_meta, dict) and isinstance(notice_meta.get("attributes"), list):
            for attr in notice_meta["attributes"]:
                if attr.get("required") == "MANDATORY" and attr.get("exposed") == "EXPOSED":
                    a_type = attr.get("attributeTypeName")
                    a_val = template_attrs.get(a_type, "1개" if "수량" in a_type else "상세페이지 참조")
                    item_attributes.append({"attributeTypeName": a_type, "attributeValueName": a_val, "exposed": "EXPOSED"})

        # Required Documents
        required_documents = []
        docs_templates = _extract_required_doc_templates(notice_meta)
        for dt in docs_templates:
            if _required_doc_applies(dt.get("required", ""), product):
                entry = _get_document_library_entry(self.session, product.brand, dt.get("templateName"))
                if entry: required_documents.append(entry)
                else: raise CoupangDocumentPendingError(f"필수 구비서류 미보유: {dt.get('templateName')}")

        items_payload = []
        options = product.options if product.options else []
        if not options:
            price = max(3000, ((int(product.selling_price or 0) + 99) // 100) * 100)
            items_payload.append({
                "itemName": name_to_use[:150], "originalPrice": price, "salePrice": price,
                "maximumBuyCount": 9999, "outboundShippingTimeDay": 3, "taxType": "TAX", "adultOnly": "EVERYONE",
                "parallelImported": "PARALLEL_IMPORTED" if product.coupang_parallel_imported else "NOT_PARALLEL_IMPORTED",
                "overseasPurchased": "OVERSEAS_PURCHASED" if product.coupang_overseas_purchased else "NOT_OVERSEAS_PURCHASED",
                "pccNeeded": bool(product.coupang_overseas_purchased), "unitCount": 1, "images": images_payload,
                "attributes": item_attributes, "contents": (contents_blocks + [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}] if contents_blocks else [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}]),
                "notices": notices, "offerCondition": "NEW"
            })
        else:
            seen_keys = set()
            for opt in options:
                opt_val = str(opt.option_value or "단품")
                if opt_val in seen_keys: continue
                seen_keys.add(opt_val)
                price = max(3000, ((int(opt.selling_price or 0) + 99) // 100) * 100)
                specific_attrs = [a.copy() for a in item_attributes]
                for a in specific_attrs:
                    if any(k in a.get("attributeTypeName", "").lower() for k in ["색상", "컬러", "color", "사이즈", "size", "규격"]):
                        a["attributeValueName"] = opt_val
                items_payload.append({
                    "itemName": f"{name_to_use} {opt_val}"[:150], "originalPrice": price, "salePrice": price,
                    "maximumBuyCount": 9999, "outboundShippingTimeDay": 3, "taxType": "TAX", "adultOnly": "EVERYONE",
                    "parallelImported": "PARALLEL_IMPORTED" if product.coupang_parallel_imported else "NOT_PARALLEL_IMPORTED",
                    "overseasPurchased": "OVERSEAS_PURCHASED" if product.coupang_overseas_purchased else "NOT_OVERSEAS_PURCHASED",
                    "pccNeeded": bool(product.coupang_overseas_purchased), "unitCount": 1, "images": images_payload,
                    "attributes": specific_attrs, "contents": (contents_blocks + [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}] if contents_blocks else [{"contentsType": "HTML", "contentDetails": [{"content": description_html, "detailType": "TEXT"}]}]),
                    "notices": notices, "offerCondition": "NEW", "sellerItemCode": opt.external_option_key or str(opt.id)
                })

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        v_id = str(account.credentials.get("vendor_id") or "").strip()
        payload = {
            "displayCategoryCode": predicted_category_code, "sellerProductName": name_to_use[:100],
            "vendorId": v_id, "saleStartedAt": now_str, "saleEndedAt": "2099-12-31T23:59:59",
            "displayProductName": name_to_use[:100], "brand": product.brand or "Detailed Page",
            "generalProductName": name_to_use, "productOrigin": "수입산", "deliveryMethod": "SEQUENCIAL",
            "deliveryCompanyCode": delivery_company_code, "deliveryChargeType": "FREE", "deliveryCharge": 0,
            "freeShipOverAmount": 0, "remoteAreaDeliverable": "Y", "returnCenterCode": return_center_code,
            "returnChargeName": (return_center_detail or {}).get("shippingPlaceName", "기본 반품지"),
            "companyContactNumber": _normalize_phone((return_center_detail or {}).get("companyContactNumber", "070-4581-8906")),
            "returnZipCode": (return_center_detail or {}).get("returnZipCode", "14598"),
            "returnAddress": (return_center_detail or {}).get("returnAddress", "경기도 부천시 원미구 부일로199번길 21"),
            "returnAddressDetail": (return_center_detail or {}).get("returnAddressDetail", "401 슈가맨워크"),
            "returnCharge": 5000, "deliveryChargeOnReturn": 5000, "outboundShippingPlaceCode": outbound_center_code,
            "vendorUserId": account.credentials.get("vendor_user_id", "user"), "requested": True, "items": items_payload
        }
        if required_documents: payload["requiredDocuments"] = required_documents
        return payload

    def delete_product(self, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, str | None]:
        account = self.session.get(MarketAccount, account_id)
        if not account: return False, "Account not found"
        client = get_client_for_account(account)
        code, data = client.delete_product(seller_product_id)
        return (True, None) if code == 200 and data.get("code") == "SUCCESS" else (False, data.get("message"))

    def stop_sales(self, account_id: uuid.UUID, seller_product_id: str) -> tuple[bool, str | None]:
        account = self.session.get(MarketAccount, account_id)
        if not account: return False, "Account not found"
        client = get_client_for_account(account)
        code, data = client.get_product(seller_product_id)
        if code != 200: return False, "Lookup failed"
        payload = data.get("data")
        for i in payload.get("items", []): i["saleStatus"] = "STOP_OUT_OF_STOCK"
        code, res = client.update_product(payload)
        return (True, None) if code == 200 and res.get("code") == "SUCCESS" else (False, res.get("message"))

    def update_price(self, account_id: uuid.UUID, market_item_id: str, price: int) -> tuple[bool, str | None]:
        account = self.session.get(MarketAccount, account_id)
        if not account: return False, "Account not found"
        client = get_client_for_account(account)
        code, data = client.get_product(market_item_id)
        if code != 200: return False, "Lookup failed"
        payload = data.get("data")
        for i in payload.get("items", []): i["salePrice"] = price
        code, res = client.update_product(payload)
        return (True, None) if code == 200 and res.get("code") == "SUCCESS" else (False, res.get("message"))

    def update_product(self, account_id: uuid.UUID, product_id: uuid.UUID) -> tuple[bool, str | None]:
        """
        쿠팡에 등록된 상품 정보를 최신 데이터로 동기화(업데이트)합니다.
        """
        account = self.session.get(MarketAccount, account_id)
        product = self.session.get(Product, product_id)
        if not account or not product:
            return False, "계정 또는 상품을 찾을 수 없습니다"
        
        listing = self.session.execute(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.product_id == product.id)
            .order_by(MarketListing.linked_at.desc())
        ).scalars().first()
        
        if not listing:
            return False, "등록된 리스팅 정보를 찾을 수 없습니다"
            
        try:
            client = get_client_for_account(account)
            code, current_data = client.get_product(listing.market_item_id)
            if code != 200: return False, f"조회 실패: {current_data.get('message')}"
            
            curr_obj = current_data.get("data")
            if not isinstance(curr_obj, dict): return False, "Invalid response"
            curr_items = curr_obj.get("items") or []

            meta = self._get_metadata(client, account, product)
            from app.services.market.coupang.image_utils import extract_coupang_image_url
            
            payload = self._map_payload(
                product, account,
                image_urls=get_original_image_urls(self.session, product),
                **meta
            )
            payload["sellerProductId"] = int(listing.market_item_id)
            payload["requested"] = True

            # Existing IDs mapping for update
            if payload.get("items") and curr_items and isinstance(curr_items[0], dict):
                target = payload["items"][0]
                source = curr_items[0]
                if "vendorItemId" in source: target["vendorItemId"] = source["vendorItemId"]
                if "sellerProductItemId" in source: target["sellerProductItemId"] = source["sellerProductItemId"]
                
                # Original price safety
                e_orig = int(source.get("originalPrice") or 0)
                n_sale = int(target.get("salePrice") or 0)
                target["originalPrice"] = max(e_orig, n_sale)

                # Fallback to existing images if needed
                if not target.get("images"):
                    fb_imgs = []
                    for idx, im in enumerate(source.get("images") or []):
                        url = extract_coupang_image_url(im)
                        if url:
                            fb_imgs.append({"imageOrder": idx, "imageType": "REPRESENTATION" if idx==0 else "DETAIL", "vendorPath": url})
                    if fb_imgs: target["images"] = fb_imgs

            code, data = client.update_product(payload)
            log_fetch(self.session, account, "update_product", payload, code, data)
            
            if code == 200 and data.get("code") == "SUCCESS":
                listing.coupang_status = "IN_REVIEW" 
                self.session.commit()
                return True, None
            return False, f"실패: {data.get('message')}"
        except Exception as e:
            self.session.rollback()
            return False, str(e)
