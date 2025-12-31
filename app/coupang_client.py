from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx


def _normalize_coupang_error_message(status_code: int, data: dict[str, Any]) -> str:
    """
    쿠팡 API 에러 메시지를 사용자 친화적으로 변환합니다.
    
    Args:
        status_code: HTTP 상태 코드
        data: API 응답 데이터
    
    Returns:
        정규화된 에러 메시지
    """
    if not isinstance(data, dict):
        return f"HTTP {status_code}: 알 수 없는 오류"
    
    code = data.get("code", "")
    message = data.get("message", "")
    details = data.get("details", "")
    
    # 에러 코드별 메시지 정규화
    error_messages = {
        400: "요청 파라미터 오류",
        401: "인증 오류",
        403: "권한 없음",
        404: "리소스를 찾을 수 없음",
        429: "요청 한도 초과 (잠시 후 재시도 필요)",
        500: "서버 오류 (잠시 후 재시도 필요)",
        503: "서비스 일시 중단 (잠시 후 재시도 필요)",
    }
    
    base_message = error_messages.get(status_code, f"HTTP {status_code} 오류")
    
    # 쿠팡 API 특정 에러 메시지 처리
    if message:
        # 한글 메시지가 있으면 그대로 사용
        message_text = message if isinstance(message, str) else str(message)
        if any(ord(c) >= 0xAC00 and ord(c) <= 0xD7A3 for c in message_text):
            return f"{base_message}: {message_text}"
        # 영문 메시지는 번역 시도
        message_lower = message_text.lower()
        
        # 일반적인 에러 메시지 매핑
        error_mapping = {
            "invalid signature": "인증 서명 오류",
            "unauthorized": "인증 실패",
            "not found": "리소스를 찾을 수 없음",
            "bad request": "잘못된 요청",
            "too many requests": "요청 한도 초과",
            "internal server error": "서버 내부 오류",
            "service unavailable": "서비스 일시 중단",
        }
        
        for eng_msg, kor_msg in error_mapping.items():
            if eng_msg in message_lower:
                return f"{base_message}: {kor_msg}"
        
        return f"{base_message}: {message_text}"
    
    if details:
        return f"{base_message}: {details}"
    
    if code and code != "SUCCESS":
        return f"{base_message}: {code}"
    
    return base_message


class CoupangClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        vendor_id: str,
        base_url: str = "https://api-gateway.coupang.com",
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._vendor_id = vendor_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout or httpx.Timeout(60.0, connect=10.0)

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
        signed_query = ""
        alt_signed_query = ""
        if params:
            # 키 기준으로 파라미터 정렬
            sorted_params = sorted(params.items())
            # 값 정의: URL 인코딩
            query_string = urllib.parse.urlencode(sorted_params)
            signed_query = f"?{query_string}" if query_string else ""
            alt_signed_query = query_string

        authorization_header = self._build_authorization(method, path, signed_query)
        
        url = f"{self._base_url}{path}"
        if query_string:
            url += f"?{query_string}"

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": authorization_header,
            "X-Requested-By": self._vendor_id,
        }

        def _do_request(h: dict[str, str]) -> httpx.Response:
            with httpx.Client(timeout=self._timeout) as client:
                if method == "GET":
                    return client.get(url, headers=h)
                if method == "POST":
                    return client.post(url, json=payload, headers=h)
                if method == "PUT":
                    return client.put(url, json=payload, headers=h)
                if method == "DELETE":
                    return client.delete(url, headers=h)
                raise ValueError(f"Unsupported method: {method}")

        try:
            resp = _do_request(headers)
        except httpx.RequestError as e:
            return 500, {"code": "INTERNAL_ERROR", "message": str(e)}

        # Invalid signature 대응(안전한 GET에 한해 1회 재시도)
        if method == "GET" and resp.status_code == 401:
            try:
                data0 = resp.json() if resp.content else {}
            except Exception:
                data0 = {"_raw_text": resp.text}
            msg0 = (data0.get("message") if isinstance(data0, dict) else None) or ""
            if "Invalid signature" in str(msg0) and alt_signed_query:
                alt_auth = self._build_authorization(method, path, alt_signed_query)
                alt_headers = dict(headers)
                alt_headers["Authorization"] = alt_auth
                try:
                    resp = _do_request(alt_headers)
                except httpx.RequestError as e:
                    return 500, {"code": "INTERNAL_ERROR", "message": str(e)}

        if not resp.content:
            if resp.status_code >= 400:
                return resp.status_code, {
                    "code": "EMPTY_RESPONSE",
                    "message": _normalize_coupang_error_message(resp.status_code, {}),
                }
            return resp.status_code, {}
            
        try:
            data = resp.json()
        except Exception:
            return resp.status_code, {
                "code": "PARSE_ERROR",
                "message": _normalize_coupang_error_message(resp.status_code, {}),
                "_raw_text": resp.text[:500],  # 최대 500자만 저장
            }

        if isinstance(data, dict):
            # 에러 응답인 경우 메시지 정규화
            if resp.status_code >= 400 or data.get("code") not in ("SUCCESS", None):
                normalized_msg = _normalize_coupang_error_message(resp.status_code, data)
                data["_normalized_message"] = normalized_msg
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

    def check_auto_category_agreed(self, vendor_id: str | None = None) -> tuple[int, dict[str, Any]]:
        """카테고리 자동매칭 서비스 동의 여부 확인"""
        vid = (vendor_id or self._vendor_id).strip()
        return self.get(
            f"/v2/providers/seller_api/apis/api/v1/marketplace/vendors/{vid}/check-auto-category-agreed"
        )

    def get_category_meta(self, category_code: str) -> tuple[int, dict[str, Any]]:
        """
        카테고리 메타정보 통합 조회

        노출 카테고리코드를 이용하여 해당 카테고리에 속한 고시정보, 옵션, 구비서류, 인증정보 목록 등을 조회합니다.
        상품 생성 시, 쿠팡에서 규정하고 있는 각 카테고리의 메타 정보와 일치하는 항목으로 상품 생성 전문을 구성해야 합니다.

        Returns (상태코드, 데이터):
            data는 dict 형태로 다음 필드 포함:
            - isAllowSingleItem: 단일상품 등록 가능 여부 (bool)
            - attributes: 카테고리 옵션목록 (구매옵션/검색옵션) (list)
            - noticeCategories: 상품고시정보목록 (list)
            - requiredDocumentNames: 구비서류목록 (list)
            - certifications: 상품 인증 정보 (list)
            - allowedOfferConditions: 허용된 상품 상태 (list)

        참고:
            2024년 10월 10일부터 필수 구매옵션 입력 시 데이터 형식에 맞게 입력해야 정상적으로 상품등록이 가능합니다.
            자유 구매옵션 구성을 할 경우 노출에 제한이 됩니다.
        """
        return self.get(f"/v2/providers/seller_api/apis/api/v1/marketplace/meta/category-related-metas/display-category-codes/{category_code}")

    def upload_image_by_url(self, image_url: str) -> tuple[int, dict[str, Any]]:
        """이미지 업로드 (URL 방식) - OpenAPI v2 기준"""
        payload = {"originPath": image_url}
        # 공식 가이드와 환경에 따라 경로가 상이할 수 있으므로, 가장 가능성 높은 v2 경로 사용
        return self.post("/v2/providers/openapi/apis/api/v1/images/upload", payload)

    def predict_category(self, product_name: str, attributes: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        """카테고리 추천 (예측)"""
        payload = {"productName": product_name}
        if attributes:
            payload["attributes"] = attributes
        code, data = self.post("/v2/providers/openapi/apis/api/v1/categorization/predict", payload)
        if code < 400:
            return code, data

        # Fallback for legacy endpoints if openapi is unavailable
        legacy_code, legacy_data = self.post(
            "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/recommend-categories",
            payload,
        )
        return legacy_code, legacy_data

    # --------------------------------------------------------------------------
    # 2. 상품 API (Product API)
    # --------------------------------------------------------------------------

    def create_product(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """상품 생성"""
        return self.post("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products", payload)

    def update_product(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """상품 수정 (승인 필요)"""
        return self.put("/v2/providers/seller_api/apis/api/v1/marketplace/seller-products", payload)

    def update_product_partial(self, seller_product_id: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """
        상품 수정 (승인 불필요)
        
        배송 및 반품지 관련 정보를 별도의 승인 절차 없이 빠르게 수정할 수 있습니다.
        
        수정 가능한 속성:
        - deliveryMethod: 배송방법
        - deliveryCompanyCode: 택배사 코드
        - deliveryChargeType: 배송비종류
        - deliveryCharge: 기본배송비
        - freeShipOverAmount: 무료배송을 위한 조건 금액
        - deliveryChargeOnReturn: 초도반품배송비
        - remoteAreaDeliverable: 도서산간 배송여부
        - unionDeliveryType: 묶음 배송여부
        - returnCenterCode: 반품지센터코드
        - returnChargeName: 반품지명
        - companyContactNumber: 반품지연락처
        - returnZipCode: 반품지우편번호
        - returnAddress: 반품지주소
        - returnAddressDetail: 반품지주소상세
        - returnCharge: 반품배송비
        - outboundShippingPlaceCode: 출고지주소코드
        - outboundShippingTimeDay: 기준출고일(일)
        - pccNeeded: PCC(개인통관부호) 필수/비필수 여부
        - extraInfoMessage: 주문제작 안내 메시지
        
        제한사항:
        - '임시저장중', '승인대기중' 상태의 상품은 수정할 수 없습니다.
        - 모든 항목은 선택적(Optional)이며, 원하는 항목만 입력하여 수정 가능합니다.
        """
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}/partial", payload)
    
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
    
    def get_inflow_status(self, vendor_id: str | None = None) -> tuple[int, dict[str, Any]]:
        """
        상품 등록 현황 조회
        
        Returns:
            - vendorId: 판매자 ID
            - restricted: 상품 생성 불가 여부 (true: 생성불가, false: 생성가능)
            - registeredCount: 등록된 상품수 (삭제 상품 제외)
            - permittedCount: 생성 가능한 최대 상품수 (null로 표시될 경우 제한없음)
        """
        vid = (vendor_id or self._vendor_id).strip()
        return self.get(
            "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/inflow-status",
            {"vendorId": vid},
        )
    
    def get_products_by_time_frame(
        self,
        created_at_from: str,
        created_at_to: str,
        vendor_id: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """
        상품 목록 구간 조회 (생성일시 기준, 최대 10분 조회 가능)
        
        Args:
            created_at_from: 생성 시작일시 (yyyy-MM-ddTHH:mm:ss)
            created_at_to: 생성 종료일시 (yyyy-MM-ddTHH:mm:ss)
            vendor_id: 판매자 ID (선택사항)
        
        Returns:
            생성일시 기준의 상품 목록
        """
        vid = (vendor_id or self._vendor_id).strip()
        return self.get(
            "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/time-frame",
            {
                "vendorId": vid,
                "createdAtFrom": created_at_from,
                "createdAtTo": created_at_to,
            },
        )
    
    def get_product_status_history(
        self,
        seller_product_id: str,
        next_token: str | None = None,
        max_per_page: int = 10
    ) -> tuple[int, dict[str, Any]]:
        """
        상품 상태변경 이력 조회
        
        Args:
            seller_product_id: 등록상품ID
            next_token: 다음 페이지 토큰 (선택사항)
            max_per_page: 페이지당 건수 (기본값: 10)
        
        Returns:
            상태변경 이력 목록
            
            상태값:
            - 심사중, 임시저장, 승인대기중, 승인완료, 부분승인완료, 승인반려, 상품삭제
            
            createdBy:
            - '쿠팡 셀러 시스템'일 경우 '쿠팡 셀러 시스템'이 자동으로 처리된 것
        """
        params: dict[str, Any] = {"maxPerPage": max_per_page}
        if next_token:
            params["nextToken"] = next_token
        
        return self.get(
            f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{seller_product_id}/histories",
            params
        )
    
    def get_products_by_external_sku(
        self,
        external_vendor_sku_code: str,
        vendor_id: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """
        상품 요약 정보 조회 (externalVendorSku로 조회)
        
        Args:
            external_vendor_sku_code: 판매자 상품코드 (업체상품코드)
            vendor_id: 판매자 ID (선택사항)
        
        Returns:
            externalVendorSku로 매칭되는 상품 목록
            
        주의:
            - 셀러 서버 에러 발생 시 API가 일시적으로 불가능할 수 있음
            - 정상시간 이후 재시도 권장
        """
        vid = (vendor_id or self._vendor_id).strip()
        return self.get(
            f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/external-vendor-sku-codes/{external_vendor_sku_code}"
        )
    
    def get_vendor_item_inventory(self, vendor_item_id: str) -> tuple[int, dict[str, Any]]:
        """
        상품 아이템별 재고수량, 판매가격, 판매상태를 조회한다.
        
        Returns:
            - sellerItemId: 옵션아이디
            - amountInStock: 옵션잔여수량
            - salePrice: 옵션판매가격
            - onSale: 옵션판매상태 (true/false)
        """
        return self.get(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/inventories")
    
    def update_stock(self, vendor_item_id: str, quantity: int) -> tuple[int, dict[str, Any]]:
        """상품 아이템별 수량 변경"""
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/quantities/{quantity}")
    
    def update_original_price(self, vendor_item_id: str, original_price: int) -> tuple[int, dict[str, Any]]:
        """
        상품 아이템별 할인율 기준가격 (originalPrice) 변경
        
        할인율 기준가는 할인율(%)표시를 위한 할인전 금액으로,
        판매가격과 동일하게 입력 시 '쿠팡가'(saleprice)로 노출됩니다.
        
        Args:
            vendor_item_id: 옵션ID (vendorItemId)
            original_price: 할인율 기준가 (최소 10원 단위)
        
        Returns:
            - code: HTTP 상태코드
            - data: 응답 데이터
            
        주의:
            - 이 기능은 승인 완료된 상품에서만 사용 가능합니다.
            - 삭제된 상품의 originalPrice는 변경 불가능합니다.
            - 10원 단위로 입력 가능합니다 (1원 단위 입력 불가).
        """
        return self.put(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/original-prices/{original_price}")
    
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
    
    def activate_auto_generated_option(self, vendor_item_id: str) -> tuple[int, dict[str, Any]]:
        """
        자동생성옵션 활성화 (개별 옵션상품 단위)
        
        판매자님이 등록한 상품에 대해 자동생성옵션을 활성화한다면,
        조건에 맞는 옵션이 자동생성 됩니다.
        
        Args:
            vendor_item_id: 옵션ID (vendorItemId)
                벤더아이템에 부여되는 고유 번호
        
        Returns:
            - code: HTTP 상태코드
            - data: 응답 데이터
                - code: 결과코드 (SUCCESS, PROCESSING, FAILED)
                - message: 결과 메시지 (FAILED일 경우 원인 포함)
                - data: "success" 또는 null
        
        참고:
            - 이 기능은 승인 완료된 상품에서만 사용 가능합니다.
            - 자동생성옵션은 쿠팡 시스템이 자동으로 생성합니다.
        """
        return self.post(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/auto-generated/opt-in")
    
    def deactivate_auto_generated_option(self, vendor_item_id: str) -> tuple[int, dict[str, Any]]:
        """
        자동생성옵션 비활성화 (개별 옵션상품 단위)
        
        더 이상 옵션이 자동 생성되지 않습니다.
        이미 자동 생성된 옵션을 더 이상 판매하고 싶지 않을 때 사용합니다.
        판매 중지를 설정하시면 됩니다.
        
        Args:
            vendor_item_id: 옵션ID (vendorItemId)
                벤더아이템에 부여되는 고유 번호
        
        Returns:
            - code: HTTP 상태코드
            - data: 응답 데이터
                - code: 결과코드 (SUCCESS, PROCESSING, FAILED)
                - message: 결과 메시지
                - data: "success" 또는 null
        
        참고:
            - 이미 자동 생성된 옵션은 삭제되지 않습니다.
            - 더 이상 옵션이 생성되지 않습니다.
        """
        return self.post(f"/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendor_item_id}/auto-generated/opt-out")
    
    def activate_auto_generated_options_all(self) -> tuple[int, dict[str, Any]]:
        """
        자동생성옵션 활성화 (전체 상품 단위)
        
        판매자님이 등록한 모든 상품에 대해 자동생성옵션을 활성화한다면,
        조건에 맞는 옵션이 자동생성 됩니다.
        
        Returns:
            - code: HTTP 상태코드
            - data: 응답 데이터
                - code: 결과코드 (SUCCESS, PROCESSING, FAILED)
                - message: 결과 메시지
                - data: "success" 또는 null
        
        참고:
            - 이 기능은 vendorId가 필요합니다.
        """
        return self.post(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller/auto-generated/opt-in")
    
    def deactivate_auto_generated_options_all(self) -> tuple[int, dict[str, Any]]:
        """
        자동생성옵션 비활성화 (전체 상품 단위)
        
        판매자님이 기존 등록 상품에 대해 자동생성옵션을 비활성화 요청한다면,
        더 이상 옵션이 자동생성되지 않습니다.
        이미 자동생성된 옵션을 더 이상 판매하고 싶지 않을 때 사용합니다.
        판매 중지를 설정하시면 됩니다.
        
        Returns:
            - code: HTTP 상태코드
            - data: 응답 데이터
                - code: 결과코드 (SUCCESS, PROCESSING, FAILED)
                - message: 결과 메시지
                - data: "success" 또는 null
        
        참고:
            - 이 기능은 vendorId가 필요합니다.
            - 이미 자동 생성된 옵션은 삭제되지 않습니다.
        """
        return self.post(f"/v2/providers/seller_api/apis/api/v1/marketplace/seller/auto-generated/opt-out")
    
    # --------------------------------------------------------------------------
    # 3. 주문/배송 API (Order/Delivery API)
    # --------------------------------------------------------------------------

    def get_order_sheets(
        self, 
        created_at_from: str, 
        created_at_to: str, 
        status: str | None = None,
        next_token: str | None = None,
        max_per_page: int = 50,
        search_type: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        발주서 목록 조회
        
        Args:
            created_at_from: 검색 시작일시 (Daily: yyyy-MM-dd, Minute: yyyy-MM-ddTHH:mm)
            created_at_to: 검색 종료일시 (Daily: yyyy-MM-dd, Minute: yyyy-MM-ddTHH:mm)
            status: 발주서 상태 (ACCEPT, INSTRUCT, DEPARTURE, DELIVERING, FINAL_DELIVERY, NONE_TRACKING)
            next_token: 다음 페이지 조회를 위한 토큰
            max_per_page: 페이지당 건수 (기본 50, 최대 50)
            search_type: 'timeFrame'이면 분 단위 전체 조회, 그 외(None 등)는 일 단위 페이징 조회
        """
        if not status:
            raise ValueError("status is required for get_order_sheets (e.g. ACCEPT, INSTRUCT)")

        def _normalize(value: str, is_to: bool, search_mode: str | None) -> str:
            val = (value or "").strip()
            # 이미 타임존이 포함되어 있으면 그대로 사용
            if "+" in val or "%2B" in val:
                return val
            
            if search_mode == "timeFrame" or "T" in val:
                # 분 단위 조회 전문 (ISO-8601)
                if "T" not in val:
                    val = f"{val}T23:59" if is_to else f"{val}T00:00"
                return f"{val}+09:00"
            else:
                # 일 단위 조회 전문 (yyyy-MM-dd)
                return f"{val}+09:00"

        params: dict[str, Any] = {
            "createdAtFrom": _normalize(created_at_from, False, search_type),
            "createdAtTo": _normalize(created_at_to, True, search_type),
            "status": status,
            "maxPerPage": max_per_page,
        }
        if search_type:
            params["searchType"] = search_type
            
        if next_token:
            params["nextToken"] = next_token
            
        path_v5 = f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/ordersheets"
        code, data = self.get(path_v5, params)
        
        # 5xx 에러 시 하위 버전(v4) fallback (필요 시)
        if code >= 500:
            path_v4 = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/ordersheets"
            return self.get(path_v4, params)
        
        return code, data

    def get_order_sheets_by_shipment_box_id(self, shipment_box_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        발주서 단건 조회 (shipmentBoxId 기준) - v5
        
        Args:
            shipment_box_id: 배송번호(묶음배송번호)
        """
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/ordersheets/{shipment_box_id}"
        return self.get(path)

    def get_order_sheets_by_order_id(self, order_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        발주서 단건 조회 (orderId 기준) - v5
        
        Args:
            order_id: 주문번호
        """
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/{order_id}/ordersheets"
        return self.get(path)

    def get_order_detail(self, order_sheet_id: str) -> tuple[int, dict[str, Any]]:
        """
        발주서(주문) 단건 조회 (Legacy - v4)
        최신 연동은 get_order_sheets_by_shipment_box_id(v5) 사용 권장
        """
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/ordersheets/{order_sheet_id}")

    def get_order_history(self, shipment_box_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        배송상태 변경 히스토리 조회 - v5
        
        Args:
            shipment_box_id: 묶음배송번호
        """
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/ordersheets/{shipment_box_id}/history"
        return self.get(path)

    def acknowledge_orders(self, shipment_box_ids: list[int | str]) -> tuple[int, dict[str, Any]]:
        """
        상품준비중 처리 (결제완료 -> 상품준비중) - v4
        
        Args:
            shipment_box_ids: 상품준비중 상태로 변경할 묶음배송번호 목록 (최대 50개)
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/ordersheets/acknowledgement"
        payload = {
            "vendorId": self._vendor_id,
            "shipmentBoxIds": shipment_box_ids
        }
        return self.put(path, payload)

    def upload_invoices(self, invoice_list: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        """
        송장업로드 처리 - v4
        
        Args:
            invoice_list: [{
                "shipmentBoxId": int,
                "orderId": int,
                "vendorItemId": int,
                "deliveryCompanyCode": str,
                "invoiceNumber": str,
                "splitShipping": bool,
                "preSplitShipped": bool,
                "estimatedShippingDate": str
            }]
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/orders/invoices"
        payload = {
            "vendorId": self._vendor_id,
            "orderSheetInvoiceApplyDtos": invoice_list
        }
        return self.post(path, payload)

    def update_invoices(self, invoice_list: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        """
        송장업데이트 처리 - v4 (수정)
        
        Args:
            invoice_list: [{
                "shipmentBoxId": int,
                "orderId": int,
                "vendorItemId": int,
                "deliveryCompanyCode": str,
                "invoiceNumber": str,
                "splitShipping": bool,
                "preSplitShipped": bool,
                "estimatedShippingDate": str
            }]
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/orders/updateInvoices"
        payload = {
            "vendorId": self._vendor_id,
            "orderSheetInvoiceApplyDtos": invoice_list
        }
        return self.post(path, payload)

    def complete_stop_shipment(self, receipt_id: int | str, cancel_count: int) -> tuple[int, dict[str, Any]]:
        """
        출고중지완료 처리 - v4
        고객 취소 요청에 대해 아직 발송하지 않았을 때 사용.
        
        Args:
            receipt_id: 반품 접수 ID
            cancel_count: 출고중지할 수량
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/returnRequests/{receipt_id}/stoppedShipment"
        payload = {
            "vendorId": self._vendor_id,
            "receiptId": int(receipt_id),
            "cancel_count": cancel_count
        }
        return self.put(path, payload)

    def ship_anyway(self, receipt_id: int | str, delivery_company_code: str, invoice_number: str) -> tuple[int, dict[str, Any]]:
        """
        이미출고 처리 - v4
        고객 취소 요청에도 불구하고 이미 상품을 발송했을 때 사용.
        
        Args:
            receipt_id: 반품 접수 ID
            delivery_company_code: 택배사 코드
            invoice_number: 송장번호
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/returnRequests/{receipt_id}/completedShipment"
        payload = {
            "vendorId": self._vendor_id,
            "receiptId": int(receipt_id),
            "deliveryCompanyCode": delivery_company_code,
            "invoiceNumber": invoice_number
        }
        return self.put(path, payload)

    def cancel_order(
        self, 
        order_id: int | str, 
        vendor_item_ids: list[int], 
        receipt_counts: list[int], 
        user_id: str,
        big_cancel_code: str = "CANERR",
        middle_cancel_code: str = "CCTTER"
    ) -> tuple[int, dict[str, Any]]:
        """
        주문 상품 취소 처리 - v5
        결제완료/상품준비중 상태의 상품을 판매자가 직접 취소(품절 등)할 때 사용.
        판매자 점수 하락에 유의 필요.
        
        Args:
            order_id: 주문 번호
            vendor_item_ids: 취소할 옵션 ID 목록
            receipt_counts: 취소할 수량 목록 (vendor_item_ids와 1:1 매칭)
            user_id: 쿠팡 Wing 로그인 ID
            big_cancel_code: 대분류 사유 (기본 CANERR)
            middle_cancel_code: 중분류 사유 (기본 CCTTER - 재고문제)
        """
        path = f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/orders/{order_id}/cancel"
        payload = {
            "orderId": int(order_id),
            "vendorItemIds": vendor_item_ids,
            "receiptCounts": receipt_counts,
            "bigCancelCode": big_cancel_code,
            "middleCancelCode": middle_cancel_code,
            "userId": user_id,
            "vendorId": self._vendor_id
        }
        return self.post(path, payload)

    def complete_long_term_undelivery(self, shipment_box_id: int | str, invoice_number: str) -> tuple[int, dict[str, Any]]:
        """
        장기미배송 배송완료 처리 - v4
        송장 등록 후 1개월 경과했으나 배송 추적이 안 되는 건을 강제 배송완료 처리.
        
        Args:
            shipment_box_id: 묶음배송번호
            invoice_number: 송장번호
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/completeLongTermUndelivery"
        payload = {
            "shipmentBoxId": int(shipment_box_id),
            "invoiceNumber": invoice_number
        }
        return self.post(path, payload)

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

    def get_return_requests(
        self,
        created_at_from: str,
        created_at_to: str,
        status: str | None = None,
        search_type: str = "timeFrame",
        cancel_type: str = "RETURN",
        next_token: str | None = None,
        max_per_page: int = 50,
        order_id: int | str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        반품 / 취소 요청 목록 조회 - v6
        
        Args:
            created_at_from: 검색 시작일 (searchType=timeFrame일 경우 yyyy-MM-ddTHH:mm)
            created_at_to: 검색 종료일 (searchType=timeFrame일 경우 yyyy-MM-ddTHH:mm)
            status: 반품상태 (RU: 출고중지요청, UC: 반품접수, CC: 반품완료, PR: 쿠팡확인요청)
            search_type: "timeFrame" (분단위) 또는 None (일단위)
            cancel_type: "RETURN" (반품) 또는 "CANCEL" (취소)
            next_token: 다음 페이지 토큰
            max_per_page: 페이지당 건수 (기본 50)
            order_id: 주문번호 (status 제외 시 필수)
        """
        params: dict[str, Any] = {
            "createdAtFrom": created_at_from,
            "createdAtTo": created_at_to,
            "searchType": search_type,
            "cancelType": cancel_type,
            "maxPerPage": max_per_page
        }
        if status:
            params["status"] = status
        if next_token:
            params["nextToken"] = next_token
        if order_id:
            params["orderId"] = order_id
            
        return self.get(f"/v2/providers/openapi/apis/api/v6/vendors/{self._vendor_id}/returnRequests", params)

    def get_return_request(self, receipt_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        반품요청 단건 조회 - v6
        
        Args:
            receipt_id: 반품접수번호
        """
        return self.get(f"/v2/providers/openapi/apis/api/v6/vendors/{self._vendor_id}/returnRequests/{receipt_id}")

    def confirm_return_receipt(self, receipt_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        반품상품 입고 확인처리 - v4
        
        Args:
            receipt_id: 취소(반품)접수번호
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/returnRequests/{receipt_id}/receiveConfirmation"
        payload = {
            "vendorId": self._vendor_id,
            "receiptId": int(receipt_id)
        }
        return self.put(path, payload)

    def approve_return_request(self, receipt_id: int | str, cancel_count: int) -> tuple[int, dict[str, Any]]:
        """
        반품요청 승인 처리 - v4
        
        Args:
            receipt_id: 반품접수번호
            cancel_count: 반품접수 수량
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/returnRequests/{receipt_id}/approval"
        payload = {
            "vendorId": self._vendor_id,
            "receiptId": int(receipt_id),
            "cancelCount": cancel_count
        }
        return self.put(path, payload)

    def get_return_withdraw_requests(
        self,
        date_from: str,
        date_to: str,
        page_index: int = 1,
        size_per_page: int = 10
    ) -> tuple[int, dict[str, Any]]:
        """
        반품철회 이력 기간별 조회 - v4
        
        Args:
            date_from: 조회 시작일 (yyyy-MM-dd)
            date_to: 조회 종료일 (yyyy-MM-dd)
            page_index: 페이지 인덱스 (기본 1)
            size_per_page: 페이지당 건수 (기본 10, 최대 100)
        """
        params = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "pageIndex": page_index,
            "sizePerPage": size_per_page
        }
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/returnWithdrawRequests", params)

    def get_return_withdraw_list(self, cancel_ids: list[int]) -> tuple[int, dict[str, Any]]:
        """
        반품철회 이력 접수번호로 조회 - v4
        
        Args:
            cancel_ids: 취소(반품)접수번호 목록 (최대 50개)
        """
        payload = {"cancelIds": cancel_ids}
        return self.post(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/returnWithdrawList", payload)

    def create_manual_return_invoice(
        self,
        receipt_id: int | str,
        return_exchange_delivery_type: str,
        delivery_company_code: str,
        invoice_number: str,
        reg_number: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        """
        회수 송장 수동 등록 - v4
        
        Args:
            receipt_id: 반품 또는 교환 접수 ID
            return_exchange_delivery_type: RETURN or EXCHANGE
            delivery_company_code: 택배사 코드
            invoice_number: 운송장번호
            reg_number: 택배사 회수번호 (선택)
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/return-exchange-invoices/manual"
        payload = {
            "receiptId": int(receipt_id),
            "returnExchangeDeliveryType": return_exchange_delivery_type,
            "deliveryCompanyCode": delivery_company_code,
            "invoiceNumber": invoice_number
        }
        if reg_number:
            payload["regNumber"] = reg_number
            
        return self.post(path, payload)

    def get_exchange_requests(
        self,
        created_at_from: str,
        created_at_to: str,
        status: str | None = None,
        order_id: int | str | None = None,
        next_token: str | None = None,
        max_per_page: int = 10
    ) -> tuple[int, dict[str, Any]]:
        """
        교환 요청 목록 조회 - v4
        
        Args:
            created_at_from: 검색 시작일 (yyyy-MM-ddTHH:mm:ss)
            created_at_to: 검색 종료일 (yyyy-MM-ddTHH:mm:ss)
            status: 교환진행상태 (RECEIPT, PROGRESS, SUCCESS, REJECT, CANCEL)
            order_id: 주문번호
            next_token: 다음 페이지 토큰
            max_per_page: 최대 조회 요청 값 (기본 10)
        """
        params: dict[str, Any] = {
            "createdAtFrom": created_at_from,
            "createdAtTo": created_at_to,
            "maxPerPage": max_per_page
        }
        if status:
            params["status"] = status
        if order_id:
            params["orderId"] = order_id
        if next_token:
            params["nextToken"] = next_token
            
        return self.get(f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests", params)

    def confirm_exchange_receipt(self, exchange_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        교환요청 상품 입고 확인처리 - v4
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests/{exchange_id}/receiveConfirmation"
        payload = {
            "exchangeId": int(exchange_id),
            "vendorId": self._vendor_id
        }
        return self.put(path, payload)

    def reject_exchange_request(self, exchange_id: int | str, reject_code: str) -> tuple[int, dict[str, Any]]:
        """
        교환요청 거부 처리 - v4
        
        Args:
            exchange_id: 교환 접수번호
            reject_code: 거절원인코드 (SOLDOUT, WITHDRAW)
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests/{exchange_id}/rejection"
        payload = {
            "exchangeId": str(exchange_id), # 문서 예제에 문자열로 되어 있는 경우도 있어 유연하게 처리
            "exchangeRejectCode": reject_code,
            "vendorId": self._vendor_id
        }
        return self.put(path, payload)

    def upload_exchange_invoice(
        self,
        exchange_id: int | str,
        shipment_box_id: int | str,
        delivery_company_code: str,
        invoice_number: str
    ) -> tuple[int, dict[str, Any]]:
        """
        교환상품 송장 업로드 처리 - v4
        """
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self._vendor_id}/exchangeRequests/{exchange_id}/invoices"
        # 문서에 따르면 리스트 형태의 페이로드
        payload = [
            {
                "exchangeId": str(exchange_id),
                "vendorId": self._vendor_id,
                "shipmentBoxId": str(shipment_box_id),
                "goodsDeliveryCode": delivery_company_code,
                "invoiceNumber": invoice_number
            }
        ]
        return self.post(path, payload)

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
        params: dict[str, Any] = {}
        if place_codes or place_names:
            if place_codes:
                params["placeCodes"] = place_codes
            if place_names:
                params["placeNames"] = place_names
        else:
            params["pageNum"] = page_num
            params["pageSize"] = page_size

        # 문서 기준 기본 경로(v2) 우선 사용, 필요 시 v5로 fallback.
        code, data = self.get("/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound", params)
        msg = (data.get("message") if isinstance(data, dict) else None) or ""
        if code == 404 and ("No matched http method" in msg or "PRECONDITION" in str(data.get("code"))):
            params2: dict[str, Any] = {}
            if place_codes or place_names:
                if place_codes:
                    params2["placeCodes"] = place_codes
                if place_names:
                    params2["placeNames"] = place_names
            else:
                params2["pageNum"] = page_num
                params2["pageSize"] = page_size
            return self.get(f"/v2/providers/openapi/apis/api/v5/vendors/{self._vendor_id}/outboundShippingCenters", params2)

        return code, data

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

    # --------------------------------------------------------------------------
    # 7. 배송비 정책 API (Shipping Policy API)
    # --------------------------------------------------------------------------

    def get_shipping_policies(self, vendor_id: str | None = None) -> tuple[int, dict[str, Any]]:
        """배송비 정책 목록 조회"""
        vid = (vendor_id or self._vendor_id).strip()
        return self.get(f"/v2/providers/marketplace_openapi/apis/api/v1/vendor/shipping-policies/{vid}")

    def create_shipping_policy(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """배송비 정책 생성"""
        return self.post("/v2/providers/marketplace_openapi/apis/api/v1/vendor/shipping-policies", payload)



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

    # --------------------------------------------------------------------------
    # 4. 고객문의 API (Customer Service API)
    # --------------------------------------------------------------------------

    def get_customer_inquiries(
        self,
        answered_type: str = "ALL",
        inquiry_start_at: str | None = None,
        inquiry_end_at: str | None = None,
        page_num: int = 1,
        page_size: int = 10,
        vendor_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        상품별 고객문의 조회
        
        Args:
            answered_type: 답변 상태 (ALL, ANSWERED, NOANSWER)
            inquiry_start_at: 조회시작일 (yyyy-MM-dd)
            inquiry_end_at: 조회종료일 (yyyy-MM-dd)
            page_num: 현재 페이지
            page_size: 페이지 크기 (최대 50)
            vendor_id: 판매자 ID (선택사항)
            
        최대 조회 기간은 7일까지 설정 가능합니다.
        """
        vid = (vendor_id or self._vendor_id).strip()
        params: dict[str, Any] = {
            "vendorId": vid,
            "answeredType": answered_type,
            "pageNum": page_num,
            "pageSize": page_size,
        }
        if inquiry_start_at:
            params["inquiryStartAt"] = inquiry_start_at
        if inquiry_end_at:
            params["inquiryEndAt"] = inquiry_end_at
            
        return self.get(f"/v2/providers/openapi/apis/api/v5/vendors/{vid}/onlineInquiries", params)

    def reply_to_customer_inquiry(
        self,
        inquiry_id: int | str,
        content: str,
        reply_by: str,
        vendor_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        상품별 고객문의 답변
        
        Args:
            inquiry_id: 질문 ID
            content: 답변 내용 (줄바꿈은 \\n 사용)
            reply_by: 응답자 셀러포탈(WING) 아이디
            vendor_id: 판매자 ID (선택사항)
        """
        vid = (vendor_id or self._vendor_id).strip()
        payload = {
            "content": content,
            "vendorId": vid,
            "replyBy": reply_by,
        }
        return self.post(f"/v2/providers/openapi/apis/api/v4/vendors/{vid}/onlineInquiries/{inquiry_id}/replies", payload)

    def get_call_center_inquiries(
        self,
        partner_counseling_status: str = "NONE",
        inquiry_start_at: str | None = None,
        inquiry_end_at: str | None = None,
        order_id: int | str | None = None,
        vendor_item_id: str | None = None,
        page_num: int = 1,
        page_size: int = 10,
        vendor_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        쿠팡 고객센터 문의 조회
        
        Args:
            partner_counseling_status: 문의 상태 (NONE, ANSWER, NO_ANSWER, TRANSFER)
            inquiry_start_at: 조회시작일 (yyyy-MM-dd)
            inquiry_end_at: 조회종료일 (yyyy-MM-dd)
            order_id: 주문번호
            vendor_item_id: 옵션 ID
            page_num: 현재 페이지
            page_size: 페이지 크기 (최대 30)
            vendor_id: 판매자 ID (선택사항)
            
        조회 기간은 최대 7일까지 설정 가능합니다.
        """
        vid = (vendor_id or self._vendor_id).strip()
        params: dict[str, Any] = {
            "vendorId": vid,
            "partnerCounselingStatus": partner_counseling_status,
            "pageNum": page_num,
            "pageSize": page_size,
        }
        if inquiry_start_at:
            params["inquiryStartAt"] = inquiry_start_at
        if inquiry_end_at:
            params["inquiryEndAt"] = inquiry_end_at
        if order_id:
            params["orderId"] = order_id
        if vendor_item_id:
            params["vendorItemId"] = vendor_item_id
            
        return self.get(f"/v2/providers/openapi/apis/api/v5/vendors/{vid}/callCenterInquiries", params)

    def get_call_center_inquiry(self, inquiry_id: int | str) -> tuple[int, dict[str, Any]]:
        """
        쿠팡 고객센터 문의 단건 조회
        
        Args:
            inquiry_id: 상담번호 (질문 ID)
        """
        return self.get(f"/v2/providers/openapi/apis/api/v5/vendors/callCenterInquiries/{inquiry_id}")

    def reply_to_call_center_inquiry(
        self,
        inquiry_id: int | str,
        content: str,
        reply_by: str,
        parent_answer_id: int | str,
        vendor_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        쿠팡 고객센터 문의 답변
        
        Args:
            inquiry_id: 상담번호 (질문 ID)
            content: 답변 내용 (2~1000자, 줄바꿈은 \\n 사용)
            reply_by: 실사용자ID(쿠팡 Wing ID)
            parent_answer_id: 부모이관글 ID (answerId)
            vendor_id: 판매자 ID (선택사항)
        """
        vid = (vendor_id or self._vendor_id).strip()
        payload = {
            "vendorId": vid,
            "inquiryId": str(inquiry_id),
            "content": content,
            "replyBy": reply_by,
            "parentAnswerId": parent_answer_id,
        }
        return self.post(f"/v2/providers/openapi/apis/api/v4/vendors/{vid}/callCenterInquiries/{inquiry_id}/replies", payload)

    def confirm_call_center_inquiry(
        self,
        inquiry_id: int | str,
        confirm_by: str,
        vendor_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        쿠팡 고객센터 문의 확인 (미확인 상태:TRANSFER 일 때 사용)
        
        Args:
            inquiry_id: 상담번호 (질문 ID)
            confirm_by: 실사용자ID(쿠팡 Wing ID)
            vendor_id: 판매자 ID (선택사항)
        """
        vid = (vendor_id or self._vendor_id).strip()
        payload = {
            "confirmBy": confirm_by,
        }
        return self.post(f"/v2/providers/openapi/apis/api/v4/vendors/{vid}/callCenterInquiries/{inquiry_id}/confirms", payload)

    # --------------------------------------------------------------------------
    # 5. 정산 API (Settlement API)
    # --------------------------------------------------------------------------

    def get_revenue_history(
        self,
        recognition_date_from: str,
        recognition_date_to: str,
        token: str = "",
        max_per_page: int = 50,
        vendor_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """
        매출내역 조회
        
        Args:
            recognition_date_from: 매출인식 시작일 (yyyy-MM-dd)
            recognition_date_to: 매출인식 종료일 (yyyy-MM-dd)
            token: 다음 페이지 조회를 위한 토큰 (첫 페이지는 "")
            max_per_page: 페이지당 건수 (최대 50)
            vendor_id: 판매자 ID (선택사항)
            
        최대 31일 이내 범위로 조회 가능하며, 전일 날짜까지만 조회할 수 있습니다.
        """
        vid = (vendor_id or self._vendor_id).strip()
        params: dict[str, Any] = {
            "vendorId": vid,
            "recognitionDateFrom": recognition_date_from,
            "recognitionDateTo": recognition_date_to,
            "token": token,
            "maxPerPage": max_per_page,
        }
        return self.get("/v2/providers/openapi/apis/api/v1/revenue-history", params)

    def get_settlement_histories(
        self,
        revenue_recognition_year_month: str,
    ) -> tuple[int, dict[str, Any]]:
        """
        지급내역 조회
        
        Args:
            revenue_recognition_year_month: 매출인식월 (yyyy-MM)
        """
        params = {"revenueRecognitionYearMonth": revenue_recognition_year_month}
        return self.get("/v2/providers/marketplace_openapi/apis/api/v1/settlement-histories", params)

    # --------------------------------------------------------------------------
    # 5. CS/문의 API (Customer Inquiry/QnA API)
    # --------------------------------------------------------------------------

    def get_customer_inquiries(
        self,
        vendor_id: str | None = None,
        answered: bool | None = None,
        inquiry_id: str | None = None,
        next_token: str | None = None,
        max_per_page: int = 50,
        days: int = 7
    ) -> tuple[int, dict[str, Any]]:
        """
        고객 문의 목록 조회
        
        Args:
            answered: 답변 여부 필터 (None: 전체, True: 답변됨, False: 미답변)
            inquiry_id: 특정 문의 ID 조회
            days: 최근 N일간의 문의 조회 (기본 7일)
        """
        vid = (vendor_id or self._vendor_id).strip()
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{vid}/customer-inquiries"
        
        params: dict[str, Any] = {
            "maxPerPage": max_per_page
        }
        
        if answered is not None:
            params["answered"] = "TRUE" if answered else "FALSE"
        if inquiry_id:
            params["inquiryId"] = inquiry_id
            
        # next_token이 있으면 추가
        if next_token:
            params["nextToken"] = next_token
            
        return self.get(path, params)

    def get_customer_inquiry(self, inquiry_id: str, vendor_id: str | None = None) -> tuple[int, dict[str, Any]]:
        """고객 문의 단건 상세 조회"""
        vid = (vendor_id or self._vendor_id).strip()
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{vid}/customer-inquiries/{inquiry_id}"
        return self.get(path)

    def answer_customer_inquiry(self, inquiry_id: str, content: str, vendor_id: str | None = None) -> tuple[int, dict[str, Any]]:
        """
        고객 문의 답변 등록
        
        Args:
            inquiry_id: 문의 ID
            content: 답변 내용
        """
        vid = (vendor_id or self._vendor_id).strip()
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{vid}/customer-inquiries/{inquiry_id}/replies"
        payload = {
            "replyText": content
        }
        return self.post(path, payload)
