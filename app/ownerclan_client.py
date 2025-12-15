from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


@dataclass(frozen=True)
class OwnerClanToken:
    access_token: str
    expires_at: datetime | None


class OwnerClanClient:
    def __init__(self, auth_url: str, api_base_url: str, graphql_url: str, access_token: str | None = None) -> None:
        self._auth_url = auth_url
        self._api_base_url = api_base_url.rstrip("/")
        self._graphql_url = graphql_url
        self._access_token = access_token

    def with_token(self, access_token: str) -> "OwnerClanClient":
        return OwnerClanClient(
            auth_url=self._auth_url,
            api_base_url=self._api_base_url,
            graphql_url=self._graphql_url,
            access_token=access_token,
        )

    def issue_token(self, username: str, password: str, user_type: str) -> OwnerClanToken:
        payload = {
            "service": "ownerclan",
            "userType": user_type,
            "username": username,
            "password": password,
        }

        timeout = httpx.Timeout(30.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._auth_url, json=payload)

        resp.raise_for_status()

        token: str | None = None
        try:
            data = resp.json()
            if isinstance(data, dict):
                token = data.get("token")
        except Exception:
            token = None

        if not token:
            token = resp.text.strip() if resp.text else None

        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        if not token:
            raise RuntimeError("오너클랜 토큰 발급 응답에 token이 없습니다")

        return OwnerClanToken(access_token=str(token), expires_at=expires_at)

    def put(self, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._api_base_url}{path}"
        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.put(url, json=payload or {}, headers=headers)

        if not resp.content:
            return resp.status_code, {}
        try:
            data = resp.json()
        except Exception:
            return resp.status_code, {"_raw_text": resp.text}

        if isinstance(data, dict):
            return resp.status_code, data
        return resp.status_code, {"_raw": data}

    def delete(self, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._api_base_url}{path}"
        timeout = httpx.Timeout(60.0, connect=10.0)
        # DELETE requests often don't have a body, but some APIs might require it (e.g. cancel reason).
        # httpx.delete doesn't support json kwarg directly in slightly older versions, but current ones do.
        # If it's strictly a body-less delete, we use client.delete(url, headers=headers).
        # However, for OwnerClan cancel_order, we might need to send data.
        # Using client.request("DELETE", ...) is safer if we need a body.
        with httpx.Client(timeout=timeout) as client:
            if payload:
                resp = client.request("DELETE", url, json=payload, headers=headers)
            else:
                resp = client.delete(url, headers=headers)

        if not resp.content:
            return resp.status_code, {}
        try:
            data = resp.json()
        except Exception:
            return resp.status_code, {"_raw_text": resp.text}

        if isinstance(data, dict):
            return resp.status_code, data
        return resp.status_code, {"_raw": data}

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self._graphql_url, json=payload, headers=headers)

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
        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._api_base_url}{path}"
        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, params=params, headers=headers)

        if not resp.content:
            return resp.status_code, {}
        try:
            data = resp.json()
        except Exception:
            return resp.status_code, {"_raw_text": resp.text}

        if isinstance(data, dict):
            return resp.status_code, data
        return resp.status_code, {"_raw": data}

    def post(self, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._api_base_url}{path}"
        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload or {}, headers=headers)

        if not resp.content:
            return resp.status_code, {}
        try:
            data = resp.json()
        except Exception:
            return resp.status_code, {"_raw_text": resp.text}

        if isinstance(data, dict):
            return resp.status_code, data
        return resp.status_code, {"_raw": data}

    # --------------------------------------------------------------------------
    # 2. 주문 API
    # --------------------------------------------------------------------------

    def get_order(self, order_id: str) -> tuple[int, dict[str, Any]]:
        """2.1 단일 주문 정보 조회"""
        return self.get(f"/v1/order/{order_id}")

    def get_orders(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[int, dict[str, Any]]:
        """2.2 복수 주문 내역 조회"""
        params: dict[str, Any] = {"page": page, "limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if status:
            params["status"] = status

        return self.get("/v1/orders", params=params)

    def create_order(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """
        2.3 새 주문 등록
        payload 예시:
        {
            "product_code": "...",
            "quantity": 1,
            "buyer_name": "...",
            ...
        }
        """
        return self.post("/v1/order", payload)

    def create_test_order(self) -> tuple[int, dict[str, Any]]:
        """2.4 테스트 주문"""
        return self.post("/v1/order/test")

    def update_order_memo(self, order_id: str, memo: str) -> tuple[int, dict[str, Any]]:
        """2.5 주문 메모 업데이트"""
        return self.put(f"/v1/order/{order_id}/memo", payload={"memo": memo})

    def cancel_order(self, order_id: str, cancel_reason: str) -> tuple[int, dict[str, Any]]:
        """2.6 주문 취소"""
        return self.delete(f"/v1/order/{order_id}", payload={"cancel_reason": cancel_reason})

    # --------------------------------------------------------------------------
    # 3. 상품 API
    # --------------------------------------------------------------------------

    def get_product(self, item_code: str) -> tuple[int, dict[str, Any]]:
        """3.1 단일 상품 정보 조회"""
        return self.get(f"/v1/item/{item_code}")

    def get_products(
        self,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[int, dict[str, Any]]:
        """3.2 복수 상품 정보 조회"""
        params: dict[str, Any] = {"page": page, "limit": limit}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if keyword:
            params["keyword"] = keyword

        return self.get("/v1/items", params=params)

    def get_product_history(
        self,
        item_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """3.3 상품 변경 이력 조회"""
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        return self.get(f"/v1/item/{item_code}/history", params=params)

    def get_products_bulk(self, item_codes: list[str]) -> tuple[int, dict[str, Any]]:
        """3.4 여러 상품 정보 조회 (Bulk)"""
        return self.post("/v1/items/bulk", payload={"item_codes": item_codes})

    # --------------------------------------------------------------------------
    # 4. 문의 API
    # --------------------------------------------------------------------------

    def get_qna_list(
        self,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[int, dict[str, Any]]:
        """4.1 문의 목록 조회"""
        params: dict[str, Any] = {"page": page, "limit": limit}
        if status:
            params["status"] = status
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        return self.get("/v1/qna", params=params)

    def get_qna(self, qna_id: str) -> tuple[int, dict[str, Any]]:
        """4.2 단일 문의 조회"""
        return self.get(f"/v1/qna/{qna_id}")

    def answer_qna(self, qna_id: str, answer: str) -> tuple[int, dict[str, Any]]:
        """4.3 문의 답변 등록"""
        return self.post(f"/v1/qna/{qna_id}/answer", payload={"answer": answer})

    def update_qna_answer(self, qna_id: str, answer: str) -> tuple[int, dict[str, Any]]:
        """4.4 문의 답변 수정"""
        return self.put(f"/v1/qna/{qna_id}/answer", payload={"answer": answer})

    # --------------------------------------------------------------------------
    # 5. 카테고리 API
    # --------------------------------------------------------------------------

    def get_category(self, category_id: str) -> tuple[int, dict[str, Any]]:
        """5.1 단일 카테고리 정보 조회"""
        return self.get(f"/v1/category/{category_id}")

    def get_categories(
        self, parent_id: str | None = None, level: int | None = None
    ) -> tuple[int, dict[str, Any]]:
        """5.2 카테고리 목록 조회"""
        params: dict[str, Any] = {}
        if parent_id:
            params["parent_id"] = parent_id
        if level is not None:
            params["level"] = level

        return self.get("/v1/categories", params=params)
