from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import time
import logging
from app.settings import settings

logger = logging.getLogger(__name__)


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

    def _call_via_proxy(self, method: str, url: str, payload: dict | None = None, params: dict | None = None) -> tuple[int, dict]:
        """Calls the OwnerClan API via Supabase Edge Function proxy."""
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        sef_url = f"{settings.supabase_url}/functions/v1/fetch-proxy"
        sef_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.supabase_service_role_key}"
        }

        # Construct full URL for proxy if needed, or send separately
        # Our SEF implementation expects { method, url, headers, body }
        proxy_payload = {
            "method": method,
            "url": url if not params else f"{url}?{httpx.QueryParams(params)}",
            "headers": headers,
            "body": payload
        }

        timeout = httpx.Timeout(300.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(sef_url, json=proxy_payload, headers=sef_headers)
        
        resp.raise_for_status()
        data = resp.json()
        status_code = data.get("status", 500)
        proxy_data = data.get("data")
        if proxy_data is None:
            proxy_data = {}
        if status_code != 200:
            logger.warning(f"Proxy request failed: {method} {url} -> status={status_code}, data={data}")
        return status_code, proxy_data


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
        url = f"{self._api_base_url}{path}"
        if settings.ownerclan_use_sef_proxy:
            return self._call_via_proxy("PUT", url, payload=payload)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        timeout = httpx.Timeout(60.0, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            resp = client.put(url, json=payload or {}, headers=headers)


        if resp.status_code == 403 and not settings.ownerclan_use_sef_proxy:
            logger.warning("OwnerClan GraphQL returned 403. Retrying via proxy.")
            return self._call_via_proxy("POST", self._graphql_url, payload=payload)

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
        url = f"{self._api_base_url}{path}"
        if settings.ownerclan_use_sef_proxy:
            return self._call_via_proxy("DELETE", url, payload=payload)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

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
        url = self._graphql_url
        if settings.ownerclan_use_sef_proxy:
            return self._call_via_proxy("POST", url, payload={"query": query, "variables": variables})

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        # OwnerClan GraphQL can be slow/heavy (large payloads). Increase read timeout and retry on transient timeouts.
        timeout = httpx.Timeout(300.0, connect=10.0)
        retryable_statuses = {429, 500, 502, 503, 504}
        last_exc: Exception | None = None
        resp: httpx.Response | None = None
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(self._graphql_url, json=payload, headers=headers)

                if resp.status_code in retryable_statuses and attempt < (max_attempts - 1):
                    time.sleep(1.0 * (2**attempt))
                    continue

                last_exc = None
                break
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.TransportError) as e:
                last_exc = e
                if attempt >= (max_attempts - 1):
                    raise
                time.sleep(1.0 * (2**attempt))

        if resp is None:
            raise last_exc or RuntimeError("OwnerClan GraphQL request failed")

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
        url = f"{self._api_base_url}{path}"
        if settings.ownerclan_use_sef_proxy:
            return self._call_via_proxy("GET", url, params=params)

        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

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
        url = f"{self._api_base_url}{path}"
        if settings.ownerclan_use_sef_proxy:
            return self._call_via_proxy("POST", url, payload=payload)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

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
        # 1. Try REST API first
        status, data = self.get(f"/v1/item/{item_code}")
        if status == 200:
            return status, data
            
        # 2. Fallback to GraphQL
        logger.info(f"OwnerClan REST get_product failed for {item_code}. Falling back to GraphQL.")
        query = """
        query ($key: ID!) {
          item(key: $key) {
            key
            id
            name
            price
            fixedPrice
            images
            content
            options {
              key
              price
              quantity
              optionAttributes {
                name
                value
              }
            }
          }
        }
        """
        variables = {"key": item_code}
        gql_status, gql_data = self.graphql(query, variables=variables)
        
        if gql_status != 200:
            return gql_status, gql_data
            
        item_node = gql_data.get("data", {}).get("item")
        if not item_node:
            return 404, {"message": "Product not found in both REST and GraphQL"}
            
        # Convert GraphQL response to a format compatible with our needs
        # We wrap it in a 'data' key to match what some callers expect
        compatible_data = {
            "data": {
                "item_code": item_node.get("key"),
                "name": item_node.get("name"),
                "supply_price": item_node.get("price"),
                "price": item_node.get("fixedPrice"),
                "images": item_node.get("images") or [],
                "detail_html": item_node.get("content"),
                "options": item_node.get("options") or []
            }
        }
        return 200, compatible_data

    def get_products(
        self,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[int, dict[str, Any]]:
        """
        3.2 복수 상품 정보 조회
        
        REST API를 먼저 시도하고, 404 발생 시 GraphQL로 대체합니다.
        """
        # 1. Try REST API first
        params: dict[str, Any] = {"page": page, "limit": limit}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if keyword:
            params["keyword"] = keyword

        rest_status, rest_data = self.get("/v1/items", params=params)
        logger.info(f"OwnerClan REST API Status: {rest_status} (keyword={keyword})")
        
        # If REST API works, return directly
        if rest_status == 200:
            return rest_status, rest_data
        
        # 2. Fallback to GraphQL
        return self._get_products_via_graphql(
            search=keyword,
            category=category,
            status=status,
            page=page,
            limit=limit,
        )

    def _get_products_via_graphql(
        self,
        search: str | None = None,
        category: str | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[int, dict[str, Any]]:
        """GraphQL을 통한 상품 검색 (REST API 대체용)"""
        safe_page = max(1, int(page))
        safe_limit = max(1, int(limit))
        fetch_limit = safe_limit * safe_page

        query = """
        query ($first: Int!, $search: String, $category: String) {
          allItems(first: $first, search: $search, category: $category) {
            edges {
              node {
                key
                id
                name
                model
                price
                fixedPrice
                images
                status
                content
                category {
                  id
                  name
                }
              }
            }
            pageInfo {
              hasNextPage
            }
          }
        }
        """

        variables = {
            "first": fetch_limit,
            "search": search,
            "category": category,
        }

        gql_status, gql_data = self.graphql(query, variables=variables)
        
        if gql_status != 200:
            return gql_status, gql_data
        
        # Convert GraphQL response to REST-compatible format
        data_part = gql_data.get("data")
        if not data_part:
            logger.warning("GraphQL response contains no data (or errors): %s", gql_data)
            return 200, {"items": [], "_source": "graphql", "_raw": gql_data}
            
        all_items = data_part.get("allItems")
        if not all_items:
            logger.warning("GraphQL response data has no allItems: %s", gql_data)
            return 200, {"items": [], "_source": "graphql", "_raw": gql_data}

        edges = all_items.get("edges", [])
        items = []
        for edge in edges:
            node = edge.get("node", {})
            items.append({
                "item_code": node.get("key"),
                "item_id": node.get("id"),
                "name": node.get("name"),
                "item_name": node.get("name"),  # alias for compatibility
                "model": node.get("model"),
                "price": node.get("fixedPrice"),
                "fixedPrice": node.get("fixedPrice"),
                "supply_price": node.get("price"),
                "selling_price": node.get("fixedPrice"),
                "images": node.get("images") or [],
                "status": node.get("status"),
                "content": node.get("content"),
                "category": node.get("category", {}).get("name") if node.get("category") else None,
            })

        if status:
            items = [item for item in items if item.get("status") == status]

        if safe_page > 1 or fetch_limit != safe_limit:
            start_idx = (safe_page - 1) * safe_limit
            end_idx = start_idx + safe_limit
            items = items[start_idx:end_idx]

        return 200, {"items": items, "_source": "graphql"}

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
