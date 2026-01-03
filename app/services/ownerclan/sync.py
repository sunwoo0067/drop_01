from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    SupplierCategoryRaw,
    SupplierItemRaw,
    SupplierOrderRaw,
    SupplierQnaRaw,
    SupplierRawFetchLog,
    SupplierSyncJob,
)
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.ownerclan.core import (
    OwnerClanJobResult,
    _parse_ownerclan_datetime,
    _sanitize_json,
    _get_ownerclan_access_token,
    get_sync_state,
    upsert_sync_state,
)

logger = logging.getLogger(__name__)

def sync_ownerclan_orders_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """오너클랜 주문 원본 데이터 동기화."""
    account_id, access_token = _get_ownerclan_access_token(session, user_type="seller")
    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    params = dict(job.params or {})
    order_key = params.get("orderKey")
    order_keys = params.get("orderKeys")
    if order_key and not order_keys:
        order_keys = [order_key]

    order_query = """
query ($key: String!) {
  order(key: $key) {
    key
    id
    products {
      quantity
      price
      shippingType
      itemKey
      itemOptionInfo {
        optionAttributes {
          name
          value
        }
        price
      }
      trackingNumber
      shippingCompanyCode
      shippedDate
      additionalAttributes {
        key
        value
      }
      taxFree
    }
    status
    shippingInfo {
      sender {
        name
        phoneNumber
        email
      }
      recipient {
        name
        phoneNumber
        destinationAddress {
          addr1
          addr2
          postalCode
        }
      }
      shippingFee
    }
    createdAt
    updatedAt
    note
    ordererNote
    sellerNote
    isBeingMediated
    adjustments {
      reason
      price
      taxFree
    }
    transactions {
      key
      id
      kind
      status
      amount {
        currency
        value
      }
      createdAt
      updatedAt
      closedAt
      note
    }
  }
}
"""

    all_orders_query = """
query {
  allOrders {
    edges {
      node {
        key
        id
        products {
          quantity
          price
          shippingType
          itemKey
          itemOptionInfo {
            optionAttributes {
              name
              value
            }
            price
          }
          trackingNumber
          shippingCompanyName
          shippedDate
          additionalAttributes {
            key
            value
          }
          taxFree
        }
        status
        shippingInfo {
          sender {
            name
            phoneNumber
            email
          }
          recipient {
            name
            phoneNumber
            destinationAddress {
              addr1
              addr2
              postalCode
            }
          }
          shippingFee
        }
        createdAt
        updatedAt
        note
        ordererNote
        sellerNote
        isBeingMediated
        adjustments {
          reason
          price
          taxFree
        }
        transactions {
          key
          id
          kind
          status
          amount {
            currency
            value
          }
          createdAt
          updatedAt
          closedAt
          note
        }
      }
    }
  }
}
"""

    def _upsert_order(order_id: str, raw_order: dict) -> None:
        stmt = insert(SupplierOrderRaw).values(
            supplier_code="ownerclan",
            account_id=account_id,
            order_id=order_id,
            raw=_sanitize_json(raw_order),
            fetched_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["supplier_code", "account_id", "order_id"],
            set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
        )
        session.execute(stmt)

    processed = 0

    if isinstance(order_keys, list) and order_keys:
        for ok in order_keys:
            if not ok:
                continue

            try:
                status_code, payload = client.graphql(order_query, variables={"key": str(ok)})
            except Exception as e:
                session.add(
                    SupplierRawFetchLog(
                        supplier_code="ownerclan",
                        account_id=account_id,
                        endpoint=settings.ownerclan_graphql_url,
                        request_payload={"query": order_query, "variables": {"key": str(ok)}},
                        http_status=None,
                        response_payload=None,
                        error_message=str(e),
                    )
                )
                session.commit()
                raise

            session.add(
                SupplierRawFetchLog(
                    supplier_code="ownerclan",
                    account_id=account_id,
                    endpoint=settings.ownerclan_graphql_url,
                    request_payload={"query": order_query, "variables": {"key": str(ok)}},
                    http_status=status_code,
                    response_payload=_sanitize_json(payload),
                    error_message=None,
                )
            )
            session.commit()

            if status_code == 401:
                raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
            if status_code >= 400:
                raise RuntimeError(f"오너클랜 GraphQL 호출 실패: HTTP {status_code}")
            if payload.get("errors"):
                raise RuntimeError(f"오너클랜 GraphQL 오류: {payload.get('errors')}")

            order_node = (payload.get("data") or {}).get("order")
            if not order_node:
                continue

            _upsert_order(str(ok), order_node)
            processed += 1
            job.progress = processed
            session.commit()
            time.sleep(1.1)

        return OwnerClanJobResult(processed=processed)

    try:
        status_code, payload = client.graphql(all_orders_query)
    except Exception as e:
        session.add(
            SupplierRawFetchLog(
                supplier_code="ownerclan",
                account_id=account_id,
                endpoint=settings.ownerclan_graphql_url,
                request_payload={"query": all_orders_query},
                http_status=None,
                response_payload=None,
                error_message=str(e),
            )
        )
        session.commit()
        raise

    session.add(
        SupplierRawFetchLog(
            supplier_code="ownerclan",
            account_id=account_id,
            endpoint=settings.ownerclan_graphql_url,
            request_payload={"query": all_orders_query},
            http_status=status_code,
            response_payload=_sanitize_json(payload),
            error_message=None,
        )
    )
    session.commit()

    if status_code == 401:
        raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
    if status_code >= 400:
        raise RuntimeError(f"오너클랜 GraphQL 호출 실패: HTTP {status_code}")
    if payload.get("errors"):
        raise RuntimeError(f"오너클랜 GraphQL 오류: {payload.get('errors')}")

    edges = (((payload.get("data") or {}).get("allOrders") or {}).get("edges") or [])
    for edge in edges:
        node = (edge or {}).get("node") or {}
        ok = node.get("key")
        if not ok:
            continue
        _upsert_order(str(ok), node)
        processed += 1

    job.progress = processed
    session.commit()
    return OwnerClanJobResult(processed=processed)

def sync_ownerclan_qna_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """오너클랜 Q&A 원본 데이터 동기화."""
    requested_user_type = str((job.params or {}).get("userType") or "seller").strip().lower()
    if requested_user_type not in ("seller", "vendor", "supplier"):
        requested_user_type = "seller"

    account_id, access_token = _get_ownerclan_access_token(session, user_type=requested_user_type)
    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    params = dict(job.params or {})
    qna_keys = params.get("qnaKeys") or ([params.get("qnaKey")] if params.get("qnaKey") else [])

    single_query = """
query SellerQnaArticle($key: ID!) {
  sellerQnaArticle(key: $key) {
    key, id, type, isSecret, title, content, files, relatedItemKey, relatedOrderKey, recipientName, createdAt, comments,
    subArticles { key, id, type, isSecret, title, content, files, relatedItemKey, relatedOrderKey, recipientName, createdAt, comments }
  }
}
"""
    list_query = """
query AllSellerQnaArticles {
  allSellerQnaArticles {
    pageInfo { hasNextPage, hasPreviousPage, startCursor, endCursor }
    edges { cursor, node { key, id, type, isSecret, title, content, files, relatedItemKey, relatedOrderKey, recipientName, createdAt, comments,
        subArticles { key, id, type, isSecret, title, content, files, relatedItemKey, relatedOrderKey, recipientName, createdAt, comments }
    } }
  }
}
"""
    vendor_list_query = """
query AllVendorQnaArticles {
  allVendorQnaArticles {
    pageInfo { hasNextPage, hasPreviousPage, startCursor, endCursor }
    edges { cursor, node { key, id, type, title, content, files, relatedItemKey, relatedOrderKey, createdAt, updatedAt, authorType, authorKey, repliedAt, reply, repliedByKey, replierType } }
  }
}
"""

    processed = 0
    if qna_keys:
        for qk in qna_keys:
            if not qk: continue
            try:
                status_code, payload = client.graphql(single_query, variables={"key": str(qk)})
                # Log and handle error (similar to sync_orders)
                # ... (restoring full logic)
                session.add(SupplierRawFetchLog(supplier_code="ownerclan", account_id=account_id, endpoint=settings.ownerclan_graphql_url, request_payload={"query": single_query, "variables": {"key": str(qk)}}, http_status=status_code, response_payload=_sanitize_json(payload), error_message=None))
                session.commit()
                node = (payload.get("data") or {}).get("sellerQnaArticle")
                if node:
                    qna_id = node.get("key") or str(qk)
                    stmt = insert(SupplierQnaRaw).values(supplier_code="ownerclan", account_id=account_id, qna_id=str(qna_id), raw=_sanitize_json(node), fetched_at=datetime.now(timezone.utc))
                    stmt = stmt.on_conflict_do_update(index_elements=["supplier_code", "account_id", "qna_id"], set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at})
                    session.execute(stmt)
                    processed += 1
                    job.progress = processed
                    session.commit()
                    time.sleep(1.1)
            except Exception as e:
                logger.error(f"QNA 싱글 수집 실패: {e}")
                raise
        return OwnerClanJobResult(processed=processed)

    # Bulk sync logic
    try:
        status_code, payload = client.graphql(vendor_list_query if requested_user_type in ("vendor", "supplier") else list_query)
        if status_code == 200:
            data_root = payload.get("data") or {}
            edges = ((data_root.get("allVendorQnaArticles") or data_root.get("allSellerQnaArticles") or {}).get("edges") or [])
            for edge in edges:
                node = (edge or {}).get("node") or {}
                qna_id = node.get("key")
                if qna_id:
                    stmt = insert(SupplierQnaRaw).values(supplier_code="ownerclan", account_id=account_id, qna_id=str(qna_id), raw=_sanitize_json(node), fetched_at=datetime.now(timezone.utc))
                    stmt = stmt.on_conflict_do_update(index_elements=["supplier_code", "account_id", "qna_id"], set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at})
                    session.execute(stmt)
                    processed += 1
            job.progress = processed
            session.commit()
    except Exception as e:
        logger.error(f"QNA 벌크 수집 실패: {e}")
        raise
    return OwnerClanJobResult(processed=processed)

def _upsert_category_tree(session: Session, node: dict[str, Any]) -> int:
    category_id = node.get("category_id") or node.get("categoryId") or node.get("key")
    if not category_id:
        return 0

    stmt = insert(SupplierCategoryRaw).values(
        supplier_code="ownerclan",
        category_id=str(category_id),
        raw=_sanitize_json(node),
        fetched_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["supplier_code", "category_id"],
        set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
    )
    session.execute(stmt)

    count = 1
    for child in node.get("children") or []:
        if isinstance(child, dict):
            count += _upsert_category_tree(session, child)
    return count

def sync_ownerclan_categories_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """오너클랜 카테고리 원본 데이터 동기화."""
    account_id, access_token = _get_ownerclan_access_token(session, user_type="seller")
    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    params = dict(job.params or {})
    first = int(params.get("first", 200))
    max_pages = int(params.get("maxPages", 0))
    max_items = int(params.get("maxItems", 0))
    after = params.get("after")
    page_count = 0
    processed = 0

    query = """
query ($first: Int!, $after: String) {
  allCategories(first: $first, after: $after) {
    pageInfo { hasNextPage, endCursor }
    edges { cursor, node { id, key, name, fullName, parent { key } } }
  }
}
"""
    cursor = after
    while True:
        page_count += 1
        variables = {"first": first, "after": cursor} if cursor else {"first": first, "after": None}
        status_code, payload = client.graphql(query, variables=variables)
        
        if status_code != 200:
            raise RuntimeError(f"OwnerClan category graphql fail: {status_code}")
            
        conn = ((payload.get("data") or {}).get("allCategories") or {})
        page_info = conn.get("pageInfo") or {}
        edges = conn.get("edges") or []

        for edge in edges:
            node = (edge or {}).get("node") or {}
            category_id = node.get("key") or node.get("id")
            if not category_id: continue

            stmt = insert(SupplierCategoryRaw).values(supplier_code="ownerclan", category_id=str(category_id), raw=_sanitize_json(node), fetched_at=datetime.now(timezone.utc))
            stmt = stmt.on_conflict_do_update(index_elements=["supplier_code", "category_id"], set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at})
            session.execute(stmt)
            processed += 1
            if max_items > 0 and processed >= max_items: break

        cursor = page_info.get("endCursor")
        job.progress = processed
        session.commit()

        if (max_items > 0 and processed >= max_items) or (max_pages > 0 and page_count >= max_pages) or not (page_info.get("hasNextPage") and cursor):
            break
        time.sleep(1.1)

    return OwnerClanJobResult(processed=processed)

def sync_ownerclan_items_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    """오너클랜 상품 원본 데이터 동기화 (Legacy 경로)."""
    account_id, access_token = _get_ownerclan_access_token(session, user_type="seller")
    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    now_ms = int(time.time() * 1000)
    max_window_ms = 60 * 60 * 24 * 179 * 1000
    state = get_sync_state(session, "items_raw")
    overlap_ms = 30 * 60 * 1000
    
    date_preset = str(job.params.get("datePreset") or "").strip().lower()
    preset_days_map = {"1d": 1, "3d": 3, "7d": 7, "30d": 30, "all": 179}
    preset_days = preset_days_map.get(date_preset)

    if preset_days is not None:
        date_to_ms = now_ms
        date_from_ms = max(0, date_to_ms - (preset_days * 24 * 60 * 60 * 1000))
        after = job.params.get("after")
    else:
        date_from_ms = int(job.params.get("dateFrom", 0))
        if date_from_ms == 0 and state and hasattr(state, 'watermark_ms') and state.watermark_ms:
             # Legacy SupplierSyncState might have watermark_ms vs last_watermark
            pass 
        date_to_ms = int(job.params.get("dateTo", now_ms))
        after = job.params.get("after")

    processed = 0
    cursor = after

    while True:
        keys_batch = []
        last_page_info = {}
        for _ in range(50):
            after_fragment = "null" if not cursor else f'"{cursor}"'
            list_query = f"query {{ allItems(dateFrom: {date_from_ms}, dateTo: {date_to_ms}, after: {after_fragment}, first: 100) {{ pageInfo {{ hasNextPage, endCursor }}, edges {{ node {{ key, updatedAt }} }} }} }}"
            status_code, payload = client.graphql(list_query)
            if status_code != 200: break
            data = payload["data"]["allItems"]
            edges = data.get("edges") or []
            for edge in edges:
                node = edge.get("node")
                if node and node.get("key"): keys_batch.append(node["key"])
            last_page_info = data.get("pageInfo") or {}
            cursor = last_page_info.get("endCursor")
            if not last_page_info.get("hasNextPage") or not cursor: break
            time.sleep(0.5)

        if not keys_batch: break

        detail_query = "query ($keys: [ID!]!) { itemsByKeys(keys: $keys) { createdAt, updatedAt, key, name, model, production, origin, id, price, pricePolicy, fixedPrice, searchKeywords, category { key, name }, content, shippingFee, shippingType, images(size: large), status, options { optionAttributes { name, value }, price, quantity, key }, taxFree, adultOnly, returnable, noReturnReason, guaranteedShippingPeriod, openmarketSellable, boxQuantity, attributes, closingTime, metadata } }"
        status_code, detail_payload = client.graphql(detail_query, variables={"keys": keys_batch})
        if status_code == 200:
            nodes = detail_payload["data"].get("itemsByKeys") or []
            for node in nodes:
                item_code = node.get("key")
                if not item_code: continue
                detail_html = node.get("detail_html") or node.get("content")
                if isinstance(detail_html, str): node["detail_html"] = normalize_ownerclan_html(detail_html)
                source_updated_at = _parse_ownerclan_datetime(node.get("updatedAt"))
                stmt = insert(SupplierItemRaw).values(supplier_code="ownerclan", item_code=str(item_code), item_key=str(node.get("key")), item_id=str(node.get("id")), source_updated_at=source_updated_at, raw=_sanitize_json(node), fetched_at=datetime.now(timezone.utc))
                stmt = stmt.on_conflict_do_update(index_elements=["supplier_code", "item_code"], set_={"item_key": stmt.excluded.item_key, "item_id": stmt.excluded.item_id, "raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at})
                session.execute(stmt)
                processed += 1

        upsert_sync_state(session, "items_raw", date_to_ms, cursor)
        job.progress = processed
        session.commit()
        if not (last_page_info.get("hasNextPage") and cursor): break
        time.sleep(1.0)

    return OwnerClanJobResult(processed=processed)
