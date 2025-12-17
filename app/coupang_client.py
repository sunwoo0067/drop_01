from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx


class CoupangClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        vendor_id: str,
        base_url: str = "https://api-gateway.coupang.com",
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._vendor_id = vendor_id
        self._base_url = base_url.rstrip("/")

    def _build_authorization(self, method: str, path: str, query: str = "") -> str:
        """
        Coupang OpenAPI 인증 헤더(CEA) 생성.

        Authorization: CEA algorithm=HmacSHA256, access-key=..., signed-date=yyMMdd'T'HHmmss'Z', signature=...
        서명 문자열: {signed_date}{method}{path}{query_string}
        """
        signed_date = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        message = f"{signed_date}{method}{path}{query}"

        signature = hmac.new(
            self._secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return (
            "CEA algorithm=HmacSHA256, "
            f"access-key={self._access_key}, "
            f"signed-date={signed_date}, "
            f"signature={signature}"
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        # Canonical query string 생성
        query_string = ""
        if params:
            # 키 기준으로 파라미터 정렬
            sorted_params = sorted(params.items())
            # 값 정의: URL 인코딩
            query_string = urllib.parse.urlencode(sorted_params)

        authorization_header = self._build_authorization(method, path, query_string)
        
        url = f"{self._base_url}{path}"
        if query_string:
            url += f"?{query_string}"

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": authorization_header,
            "X-Requested-By": self._vendor_id,
        }

        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            try:
                if method == "GET":
                    resp = client.get(url, headers=headers)
                elif method == "POST":
                    resp = client.post(url, json=payload, headers=headers)
                elif method == "PUT":
                    resp = client.put(url, json=payload, headers=headers)
                elif method == "DELETE":
                    resp = client.delete(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported method: {method}")
            except httpx.RequestError as e:
                # Network error, etc.
                return 500, {"code": "INTERNAL_ERROR", "message": str(e)}

        if not resp.content:
            return resp.status_code, {}
            
        try:
            data = resp.json()
        except Exception:
            return resp.status_code, {"_raw_text": resp.text}

        if isinstance(data, dict):
            return resp.status_code, data
        
        return resp.status_code, {"_raw": data}

    def get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        return self._request("POST", path, payload=payload)

    def put(self, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        return self._request("PUT", path, payload=payload)

    def delete(self, path: str) -> tuple[int, dict[str, Any]]:
        return self._request("DELETE", path)

    # --------------------------------------------------------------------------
    # 1. 카테고리 API (Category API)
    # --------------------------------------------------------------------------

    def get_category_meta(self, category_code: str) -> tuple[int, dict[str, Any]]:
        """카테고리 메타정보 조회"""
        return self.get(f"/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{category_code}")

    def predict_category(self, product_name: str, attributes: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        """카테고리 추천 (예측)"""
        # 참고: 구체적인 엔드포인트 구현에 따라 달라질 수 있음. 명시적인 문서가 없다면 일반적인 v1 구조를 가정.
        # 문서는 보통 /v2/providers/seller_api/apis/api/v1/marketplace/seller-products/recommend-categories 를 가리킴
        payload = {"productName": product_name}
        if attributes:
            payload["attributes"] = attributes
        return self.post("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/recommend-categories", payload)

    # --------------------------------------------------------------------------
    # 2. 상품 API (Product API)
    # --------------------------------------------------------------------------

    def create_product(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """상품 생성"""
        return self.post("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products", payload)

    def update_product(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """상품 수정 (승인 필요)"""
        return self.put("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products", payload)
    
    def approve_product(self, seller_product_id: str) -> tuple[int, dict[str, Any]]:
        """상품 승인 요청"""
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}/approvals")

    def get_product(self, seller_product_id: str) -> tuple[int, dict[str, Any]]:
        """상품 조회 (단건)"""
        return self.get(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}")
    
    def delete_product(self, seller_product_id: str) -> tuple[int, dict[str, Any]]:
        """상품 삭제"""
        return self.delete(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}")

    def get_products(
        self,
        vendor_id: str | None = None,
        next_token: str | None = None,
        max_per_page: int = 20,
        status: str | None = None,
        seller_product_name: str | None = None,
        created_at: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """상품 목록 페이징 조회"""
        params: dict[str, Any] = {
            "vendorId": vendor_id or self._vendor_id,
            "maxPerPage": max_per_page
        }
        if next_token:
            params["nextToken"] = next_token
        if status:
            params["status"] = status
        if seller_product_name:
            params["sellerProductName"] = seller_product_name
        if created_at:
            params["createdAt"] = created_at
            
        return self.get("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products", params)

    def update_stock(self, vendor_item_id: str, quantity: int) -> tuple[int, dict[str, Any]]:
        """상품 아이템별 수량 변경"""
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/quantities/{quantity}")

    def update_price(self, vendor_item_id: str, price: int, force: bool = False) -> tuple[int, dict[str, Any]]:
        """상품 아이템별 가격 변경"""
        return self._update_price_internal(vendor_item_id, price, force) 
        # 참고: 쿠팡 API는 가격을 경로 파라미터로 사용하지만 문서는 .../prices/{price} 엔드 포인트와 
        # 쿼리 스트링 파라미터를 명시합니다. _request에서 PUT 요청 시 params 처리가 되는지 확인이 필요합니다.
        # _request 로직은 params가 있으면 쿼리 스트링을 생성하므로 정상 동작합니다.
        # 즉, return self._request("PUT", path, params=params) 형태가 되어야 합니다.

    def _update_price_internal(self, vendor_item_id: str, price: int, force: bool = False) -> tuple[int, dict[str, Any]]:
         path = f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/prices/{price}"
         params = {"forceSalePriceUpdate": "true"} if force else {}
         # PUT 요청에서도 URL 파라미터를 확실히 붙이기 위해 저수준 _request 사용
         return self._request("PUT", path, params=params)

    def stop_sales(self, vendor_item_id: str) -> tuple[int, dict[str, Any]]:
        """상품 아이템별 판매 중지"""
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/sales/stop")

    def resume_sales(self, vendor_item_id: str) -> tuple[int, dict[str, Any]]:
        """상품 아이템별 판매 재개"""
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/sales/resume")

    # --------------------------------------------------------------------------
    # 3. 주문/배송 API (Order/Delivery API)
    # --------------------------------------------------------------------------

    def get_order_sheets(
        self, 
        created_at_from: str, 
        created_at_to: str, 
        status: str | None = None,
        next_token: str | None = None,
        max_per_page: int = 20,
        search_type: str = "timeFrame",
    ) -> tuple[int, dict[str, Any]]:
        """발주서 목록 조회"""
        if not status:
            # 쿠팡 ordersheets(timeFrame) API는 status가 필수인 경우가 많습니다.
            raise ValueError("status is required for get_order_sheets (e.g. ACCEPT, INSTRUCT)")

        # 쿠팡 ordersheets(timeFrame)는 ISO-8601(+09:00) 형태를 요구하는 경우가 많습니다.
        # 예: 2025-07-29T00:00+09:00 ~ 2025-07-29T23:59+09:00 (초 단위 없이 분까지만)
        def _normalize(value: str, is_to: bool) -> str:
            s = (value or "").strip()
            if "T" in s:
                return s
            # yyyy-MM-dd → yyyy-MM-ddT00:00+09:00 / yyyy-MM-ddT23:59+09:00
            return f"{s}T23:59+09:00" if is_to else f"{s}T00:00+09:00"

        params: dict[str, Any] = {
            "createdAtFrom": _normalize(created_at_from, is_to=False),
            "createdAtTo": _normalize(created_at_to, is_to=True),
            "searchType": search_type,
            "status": status,
            "maxPerPage": max_per_page,
        }
        if next_token:
            params["nextToken"] = next_token
            
        # timeFrame(분단위) 목록 조회는 v5로 제공되는 경우가 많지만,
        # 환경에 따라 v4로 동작하는 경우도 있어 5xx 시 fallback 합니다.
        path_v5 = f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/ordersheets"
        code, data = self.get(path_v5, params)
        if code >= 500:
            path_v4 = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/ordersheets"
            return self.get(path_v4, params)
        return code, data

    def get_order_detail(self, order_sheet_id: str) -> tuple[int, dict[str, Any]]:
        """발주서(주문) 단건 조회 (orderSheetId 기준)"""
        # 공식 문서에서 보편적으로 사용되는 단건 조회 패턴.
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/ordersheets/{order_sheet_id}")

    def stop_delivery(self, invoice_no: str) -> tuple[int, dict[str, Any]]:
        """배송 중지 요청 (송장 번호 기준) - '출고 중지' 개념과 매핑됨"""
        # 참고: 문서에서 정확한 엔드포인트가 필요함. 다른 영역의 로직을 볼 때 receiptId 기준일 것으로 추정됨.
        # delivery_api.md 문서가 별도의 엔드포인트를 명시한다면 그것을 사용해야 함.
        # 일반적으로 /v2/providers/openapi/apis/api/v1/vendors/{vendorId}/orders/{orderId}/cancel 등과 유사함.
        # 정확한 문서 내용 없이 프롬프트만으로는 구현이 불확실하므로 일단 비워둠.
        # 현재는 README/Product에 명시된 "발주서 조회, 송장 업로드, 취소 처리" 중 
        # 'register_invoice'(송장 등록) 구현에 집중함.
        pass

    def upload_invoices(self, order_sheet_invoice_apply_dtos: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        """
        송장 업로드(배송지시) - docs/api_docs/coupang/delivery_api.md 기준(v4).

        Body 예시:
        {
          "vendorId": "...",
          "orderSheetInvoiceApplyDtos": [
            {
              "shipmentBoxId": 123,
              "orderId": 456,
              "deliveryCompanyCode": "KDEXP",
              "invoiceNumber": "0000",
              "vendorItemId": 789,
              "splitShipping": false,
              "preSplitShipped": false,
              "estimatedShippingDate": ""
            }
          ]
        }
        """
        payload = {"vendorId": self._vendor_id, "orderSheetInvoiceApplyDtos": order_sheet_invoice_apply_dtos}
        return self.post(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/orders/invoices", payload)

    # --------------------------------------------------------------------------
    # 4. 반품/교환 API (Return/Exchange API)
    # --------------------------------------------------------------------------

    def get_return_requests(self, created_at_from: str, created_at_to: str, status: str | None = None) -> tuple[int, dict[str, Any]]:
        """반품 요청 목록 조회"""
        params: dict[str, Any] = {
            "createdAtFrom": created_at_from,
            "createdAtTo": created_at_to,
            "vendorId": self._vendor_id
        }
        if status:
            params["status"] = status
        return self.get(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/return-requests", params)

    def approve_return(self, receipt_id: str) -> tuple[int, dict[str, Any]]:
        """반품 승인 (물품 수령 확인 후)"""
        # PUT /v2/providers/openapi/apis/api/v1/vendors/{vendorId}/return-requests/{receiptId}/approval
        return self.put(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/return-requests/{receipt_id}/approval")

    # --------------------------------------------------------------------------
    # 5. CS API
    # --------------------------------------------------------------------------

    def get_inquiries(
        self, 
        inquiry_start_at: str, 
        inquiry_end_at: str, 
        status: str | None = None,
        page_token: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """상품 문의 조회"""
        params: dict[str, Any] = {
            "inquiryStartAt": inquiry_start_at,
            "inquiryEndAt": inquiry_end_at,
            "vendorId": self._vendor_id
        }
        if status:
            params["status"] = status
        if page_token:
            params["pageToken"] = page_token
            
        return self.get(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/online-inquiries", params)

    def answer_inquiry(self, inquiry_id: str, content: str) -> tuple[int, dict[str, Any]]:
        """문의 답변"""
        payload = {
             "vendorId": self._vendor_id,
             "inquiryId": inquiry_id,
             "content": content
        }
        return self.post(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/online-inquiries/{inquiry_id}/replies", payload)

    # --------------------------------------------------------------------------
    # 6. 물류센터 API (Logistics API)
    # --------------------------------------------------------------------------

    def create_outbound_shipping_center(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """출고지 생성"""
        return self.post(f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/outboundShippingCenters", payload)

    def get_outbound_shipping_centers(
        self, 
        page_num: int = 1, 
        page_size: int = 50, 
        place_codes: str | None = None, 
        place_names: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """출고지 조회"""
        params: dict[str, Any] = {
            "pageNum": page_num,
            "pageSize": page_size
        }
        if place_codes:
            params["placeCodes"] = place_codes
        if place_names:
            params["placeNames"] = place_names
            
        return self.get("/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound", params)

    def update_outbound_shipping_center(self, outbound_shipping_place_code: int, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """출고지 수정"""
        return self.put(f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/outboundShippingCenters/{outbound_shipping_place_code}", payload)

    def create_return_shipping_center(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """반품지 생성"""
        return self.post(f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/returnShippingCenters", payload)

    def get_return_shipping_centers(self, page_num: int = 1, page_size: int = 50) -> tuple[int, dict[str, Any]]:
        """반품지 목록 조회"""
        params = {
            "pageNum": page_num,
            "pageSize": page_size
        }
        return self.get(f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/returnShippingCenters", params)

    def update_return_shipping_center(self, return_center_code: int, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """반품지 수정"""
        return self.put(f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/returnShippingCenters/{return_center_code}", payload)

    def get_return_shipping_center_by_code(self, return_center_codes: str) -> tuple[int, dict[str, Any]]:
        """반품지 단건(복수) 조회 (센터코드 기준)"""
        params = {"returnCenterCodes": return_center_codes}
        return self.get("/v2/providers/openapi/apis/api/v3/return/shipping-places/center-code", params)

    # --------------------------------------------------------------------------
    # 7. 교환 API (Exchange API)
    # --------------------------------------------------------------------------

    def get_exchange_requests(
        self,
        created_at_from: str,
        created_at_to: str,
        status: str | None = None,
        next_token: str | None = None,
        max_per_page: int = 50
    ) -> tuple[int, dict[str, Any]]:
        """교환요청 목록조회"""
        params: dict[str, Any] = {
            "createdAtFrom": created_at_from,
            "createdAtTo": created_at_to
        }
        if status:
            params["status"] = status
        if next_token:
            params["nextToken"] = next_token
        if max_per_page:
            params["maxPerPage"] = max_per_page
            
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests", params)

    def confirm_exchange_item(self, receipt_id: str) -> tuple[int, dict[str, Any]]:
        """교환상품 입고 확인처리"""
        return self.put(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests/{receipt_id}/confirmation")

    def reject_exchange_request(self, receipt_id: str, reason: str) -> tuple[int, dict[str, Any]]:
        """교환요청 거부 처리"""
        payload = {"rejectReason": reason}
        return self.put(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests/{receipt_id}/rejection", payload)

    def upload_exchange_invoice(self, receipt_id: str, delivery_company_code: str, invoice_number: str) -> tuple[int, dict[str, Any]]:
        """교환상품 송장 업로드 처리"""
        payload = {
            "deliveryCompanyCode": delivery_company_code,
            "invoiceNumber": invoice_number
        }
        return self.put(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests/{receipt_id}/invoice", payload)

    # --------------------------------------------------------------------------
    # 8. 쿠폰/캐시백 API (Coupon API)
    # --------------------------------------------------------------------------
    
    def get_coupon_budget(self) -> tuple[int, dict[str, Any]]:
        """예산현황 조회"""
        return self.get(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/coupons/budgets")

    def create_instant_discount_coupon(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """즉시할인쿠폰 생성"""
        return self.post(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/coupons/instant-discounts", payload)

    def delete_instant_discount_coupon(self, coupon_id: str) -> tuple[int, dict[str, Any]]:
        """즉시할인쿠폰 파기"""
        return self.delete(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/coupons/instant-discounts/{coupon_id}")
        
    def create_downloadable_coupon(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """다운로드쿠폰 생성"""
        return self.post(f"/v2/providers/openapi/apis/api/v1/vendors/{self._vendor_id}/coupons/downloadable", payload)

    # --------------------------------------------------------------------------
    # 9. 정산 API (Settlement API)
    # --------------------------------------------------------------------------

    def get_sales_history(
        self,
        date_from: str,
        date_to: str,
        next_token: str | None = None,
        max_per_page: int = 50
    ) -> tuple[int, dict[str, Any]]:
        """매출내역 조회"""
        params: dict[str, Any] = {
            "recognitionDateFrom": date_from,
            "recognitionDateTo": date_to,
            "maxPerPage": max_per_page
        }
        if next_token:
            params["nextToken"] = next_token
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/settlements/sales", params)

    def get_payment_history(
        self,
        date_from: str,
        date_to: str,
        next_token: str | None = None,
        max_per_page: int = 50
    ) -> tuple[int, dict[str, Any]]:
        """지급내역 조회"""
        params: dict[str, Any] = {
            "paymentDateFrom": date_from,
            "paymentDateTo": date_to,
            "maxPerPage": max_per_page
        }
        if next_token:
            params["nextToken"] = next_token
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/settlements/payments", params)

    # --------------------------------------------------------------------------
    # 10. 로켓그로스 API (Rocket Growth API)
    # --------------------------------------------------------------------------

    def get_rocket_growth_orders(
        self,
        created_at_from: str,
        created_at_to: str,
        status: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """로켓그로스 주문 목록 조회"""
        params: dict[str, Any] = {
             "vendorId": self._vendor_id,
             "createdAtFrom": created_at_from,
             "createdAtTo": created_at_to
        }
        if status:
            params["status"] = status
        return self.get("/v2/providers/rocket_growth_api/apis/api/v1/orders", params)

    def get_rocket_inventory(self, vendor_item_id: str | None = None) -> tuple[int, dict[str, Any]]:
        """로켓창고 재고 조회"""
        params: dict[str, Any] = {"vendorId": self._vendor_id}
        if vendor_item_id:
            params["vendorItemId"] = vendor_item_id
        return self.get("/v2/providers/rocket_growth_api/apis/api/v1/inventory", params)

    def get_rocket_products(
        self,
        next_token: str | None = None,
        max_per_page: int = 50
    ) -> tuple[int, dict[str, Any]]:
        """로켓그로스 상품 목록 조회"""
        params: dict[str, Any] = {
            "vendorId": self._vendor_id,
            "maxPerPage": max_per_page
        }
        if next_token:
            params["nextToken"] = next_token
        return self.get("/v2/providers/rocket_growth_api/apis/api/v1/products", params)

    def create_rocket_product(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
         """로켓그로스 상품 생성"""
         return self.post("/v2/providers/rocket_growth_api/apis/api/v1/products", payload)

    def update_rocket_product(self, seller_product_id: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """로켓그로스 상품 수정"""
        return self.put(f"/v2/providers/rocket_growth_api/apis/api/v1/products/{seller_product_id}", payload)

    def get_rocket_product(self, seller_product_id: str) -> tuple[int, dict[str, Any]]:
        """로켓그로스 상품 조회"""
        return self.get(f"/v2/providers/rocket_growth_api/apis/api/v1/products/{seller_product_id}")
