from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    SupplierAccount,
    SupplierCategoryRaw,
    SupplierItemRaw,
    SupplierOrderRaw,
    SupplierQnaRaw,
    SupplierRawFetchLog,
    SupplierSyncJob,
    SupplierSyncState,
)
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.detail_html_normalizer import normalize_ownerclan_html


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OwnerClanJobResult:
    processed: int


def _parse_ownerclan_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    return None


def _sanitize_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    return value


def get_primary_ownerclan_account(session: Session, user_type: str = "seller") -> SupplierAccount:
    user_type = (user_type or "seller").strip().lower()

    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == user_type)
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )

    if account:
        return account

    # fallback: primary가 아니더라도 active 계정이 있으면 사용
    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == user_type)
        .filter(SupplierAccount.is_active.is_(True))
        .order_by(SupplierAccount.updated_at.desc())
        .first()
    )

    if not account:
        raise RuntimeError(f"오너클랜 {user_type} 계정이 설정되어 있지 않습니다")

    return account


def _get_ownerclan_access_token(session: Session, user_type: str = "seller") -> tuple[uuid.UUID, str]:
    account = get_primary_ownerclan_account(session, user_type=user_type)
    return account.id, account.access_token


def upsert_sync_state(session: Session, sync_type: str, watermark_ms: int | None, cursor: str | None) -> None:
    nil_account_id = uuid.UUID(int=0)
    stmt = insert(SupplierSyncState).values(
        supplier_code="ownerclan",
        sync_type=sync_type,
        account_id=nil_account_id,
        watermark_ms=watermark_ms,
        cursor=cursor,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["supplier_code", "sync_type", "account_id"],
        set_={
            "watermark_ms": watermark_ms,
            "cursor": cursor,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    session.execute(stmt)


def get_sync_state(session: Session, sync_type: str) -> SupplierSyncState | None:
    nil_account_id = uuid.UUID(int=0)
    return (
        session.query(SupplierSyncState)
        .filter(SupplierSyncState.supplier_code == "ownerclan")
        .filter(SupplierSyncState.sync_type == sync_type)
        .filter(SupplierSyncState.account_id == nil_account_id)
        .one_or_none()
    )


def run_ownerclan_job(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    if job.job_type == "ownerclan_items_raw":
        return sync_ownerclan_items_raw(session, job)

    if job.job_type == "ownerclan_orders_raw":
        return sync_ownerclan_orders_raw(session, job)

    if job.job_type == "ownerclan_qna_raw":
        return sync_ownerclan_qna_raw(session, job)

    if job.job_type == "ownerclan_categories_raw":
        return sync_ownerclan_categories_raw(session, job)

    raise RuntimeError(f"지원하지 않는 job_type 입니다: {job.job_type}")


def sync_ownerclan_orders_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
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
    qna_key = params.get("qnaKey")
    qna_keys = params.get("qnaKeys")
    if qna_key and not qna_keys:
        qna_keys = [qna_key]

    single_query = """
query SellerQnaArticle($key: ID!) {
  sellerQnaArticle(key: $key) {
    key
    id
    type
    isSecret
    title
    content
    files
    relatedItemKey
    relatedOrderKey
    recipientName
    createdAt
    comments
    subArticles {
      key
      id
      type
      isSecret
      title
      content
      files
      relatedItemKey
      relatedOrderKey
      recipientName
      createdAt
      comments
    }
  }
}
"""

    list_query = """
query AllSellerQnaArticles {
  allSellerQnaArticles {
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }
    edges {
      cursor
      node {
        key
        id
        type
        isSecret
        title
        content
        files
        relatedItemKey
        relatedOrderKey
        recipientName
        createdAt
        comments
        subArticles {
          key
          id
          type
          isSecret
          title
          content
          files
          relatedItemKey
          relatedOrderKey
          recipientName
          createdAt
          comments
        }
      }
    }
  }
}
"""

    vendor_list_query = """
query AllVendorQnaArticles {
  allVendorQnaArticles {
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }
    edges {
      cursor
      node {
        key
        id
        type
        title
        content
        files
        relatedItemKey
        relatedOrderKey
        createdAt
        updatedAt
        authorType
        authorKey
        repliedAt
        reply
        repliedByKey
        replierType
      }
    }
  }
}
""".strip()

    processed = 0

    if isinstance(qna_keys, list) and qna_keys:
        for qk in qna_keys:
            if not qk:
                continue

            try:
                status_code, payload = client.graphql(single_query, variables={"key": str(qk)})
            except Exception as e:
                session.add(
                    SupplierRawFetchLog(
                        supplier_code="ownerclan",
                        account_id=account_id,
                        endpoint=settings.ownerclan_graphql_url,
                        request_payload={"query": single_query, "variables": {"key": str(qk)}},
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
                    request_payload={"query": single_query, "variables": {"key": str(qk)}},
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

            node = (payload.get("data") or {}).get("sellerQnaArticle")
            if not node:
                continue

            qna_id = node.get("key") or str(qk)
            stmt = insert(SupplierQnaRaw).values(
                supplier_code="ownerclan",
                account_id=account_id,
                qna_id=str(qna_id),
                raw=_sanitize_json(node),
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["supplier_code", "account_id", "qna_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
            )
            session.execute(stmt)
            processed += 1
            job.progress = processed
            session.commit()
            time.sleep(1.1)

        return OwnerClanJobResult(processed=processed)

    try:
        status_code, payload = client.graphql(vendor_list_query if requested_user_type in ("vendor", "supplier") else list_query)
    except Exception as e:
        session.add(
            SupplierRawFetchLog(
                supplier_code="ownerclan",
                account_id=account_id,
                endpoint=settings.ownerclan_graphql_url,
                request_payload={"query": vendor_list_query if requested_user_type in ("vendor", "supplier") else list_query},
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
            request_payload={"query": vendor_list_query if requested_user_type in ("vendor", "supplier") else list_query},
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

    data_root = payload.get("data") or {}
    if requested_user_type in ("vendor", "supplier"):
        edges = (((data_root.get("allVendorQnaArticles") or {}).get("edges") or []) )
    else:
        edges = (((data_root.get("allSellerQnaArticles") or {}).get("edges") or []) )
    for edge in edges:
        node = (edge or {}).get("node") or {}
        qna_id = node.get("key")
        if not qna_id:
            continue
        stmt = insert(SupplierQnaRaw).values(
            supplier_code="ownerclan",
            account_id=account_id,
            qna_id=str(qna_id),
            raw=_sanitize_json(node),
            fetched_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["supplier_code", "account_id", "qna_id"],
            set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
        )
        session.execute(stmt)
        processed += 1

    job.progress = processed
    session.commit()
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

    # NOTE: OwnerClan REST categories endpoint returns 404, but GraphQL provides allCategories/category.
    query = """
query ($first: Int!, $after: String) {
  allCategories(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      cursor
      node {
        id
        key
        name
        fullName
        parent { key }
      }
    }
  }
}
""".strip()

    cursor = after
    while True:
        page_count += 1
        variables = {"first": first, "after": cursor} if cursor else {"first": first, "after": None}

        try:
            status_code, payload = client.graphql(query, variables=variables)
        except Exception as e:
            session.add(
                SupplierRawFetchLog(
                    supplier_code="ownerclan",
                    account_id=account_id,
                    endpoint=settings.ownerclan_graphql_url,
                    request_payload={"query": query, "variables": variables},
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
                request_payload={"query": query, "variables": variables},
                http_status=status_code,
                response_payload=_sanitize_json(payload),
                error_message=None,
            )
        )
        session.commit()

        if status_code == 401:
            raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
        if status_code >= 400:
            raise RuntimeError(f"오너클랜 카테고리(GraphQL) 호출 실패: HTTP {status_code}")
        if payload.get("errors"):
            raise RuntimeError(f"오너클랜 카테고리(GraphQL) 오류: {payload.get('errors')}")

        conn = ((payload.get("data") or {}).get("allCategories") or {})
        page_info = conn.get("pageInfo") or {}
        edges = conn.get("edges") or []

        for edge in edges:
            node = (edge or {}).get("node") or {}
            category_id = node.get("key") or node.get("id")
            if not category_id:
                continue

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
            processed += 1

            if max_items > 0 and processed >= max_items:
                break

        cursor = page_info.get("endCursor")
        job.progress = processed
        session.commit()

        if max_items > 0 and processed >= max_items:
            break
        if max_pages > 0 and page_count >= max_pages:
            break

        has_next = bool(page_info.get("hasNextPage"))
        if not has_next or not cursor:
            break

        time.sleep(1.1)

    return OwnerClanJobResult(processed=processed)


def sync_ownerclan_items_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
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
    preset_days_map = {
        "1d": 1,
        "3d": 3,
        "7d": 7,
        "30d": 30,
        "all": 179,
    }
    preset_days = preset_days_map.get(date_preset)

    if preset_days is not None:
        date_to_ms = now_ms
        date_from_ms = max(0, date_to_ms - (preset_days * 24 * 60 * 60 * 1000))
        after = job.params.get("after")
    else:
        date_from_ms = int(job.params.get("dateFrom", 0))
        if date_from_ms == 0 and state and state.watermark_ms:
            date_from_ms = max(0, int(state.watermark_ms) - overlap_ms)

        date_to_ms = int(job.params.get("dateTo", now_ms))

        if date_from_ms == 0:
            date_from_ms = max(0, date_to_ms - max_window_ms)

        if date_to_ms - date_from_ms > max_window_ms:
            date_from_ms = max(0, date_to_ms - max_window_ms)

        after = job.params.get("after")
        if not after and state and state.cursor:
            after = state.cursor

    first = int(job.params.get("first", 100))

    max_items = int(job.params.get("maxItems", 0))
    max_pages = int(job.params.get("maxPages", 0))
    page_count = 0

    processed = 0
    cursor = after

    while True:
        # --- 1단계: 상품 키 목록 수집 (최대 5,000개) ---
        keys_batch = []
        last_page_info = {}
        
        # 100개씩 최대 50번 호출하여 5,000개 확보 시도 (서버 부하 분산)
        for _ in range(50):
            page_count += 1
            after_fragment = "null" if not cursor else f'"{cursor}"'
            
            # 키와 업데이트 시간만 가져오는 라이트 쿼리
            list_query = f"""
query {{
  allItems(dateFrom: {date_from_ms}, dateTo: {date_to_ms}, after: {after_fragment}, first: 100) {{
    pageInfo {{
      hasNextPage
      endCursor
    }}
    edges {{
      node {{
        key
        updatedAt
      }}
    }}
  }}
}}
"""
            try:
                # API 호출 및 로깅
                status_code, payload = client.graphql(list_query)
                session.add(SupplierRawFetchLog(
                    supplier_code="ownerclan",
                    account_id=account_id,
                    endpoint=f"{settings.ownerclan_graphql_url} (allItems_batch)",
                    request_payload={"query": list_query, "after": cursor},
                    http_status=status_code,
                    response_payload=_sanitize_json(payload) if status_code == 200 else None,
                    error_message=None if status_code == 200 else f"HTTP {status_code}"
                ))
            except Exception as e:
                logger.error(f"오너클랜 목록 수집 중 오류: {e}")
                break # 다음 배치 시도 또는 종료
            
            if status_code != 200 or not payload.get("data"):
                break
                
            data = payload["data"]["allItems"]
            edges = data.get("edges") or []
            for edge in edges:
                node = edge.get("node")
                if node and node.get("key"):
                    keys_batch.append(node["key"])
            
            last_page_info = data.get("pageInfo") or {}
            cursor = last_page_info.get("endCursor")
            
            if not last_page_info.get("hasNextPage") or not cursor:
                break
            
            # API 제한 준수를 위한 미세 대기
            time.sleep(0.5)

        if not keys_batch:
            break

        # --- 2단계: 수집된 키들에 대한 상세 정보 일괄 조회 ---
        detail_query = """
query ($keys: [ID!]!) {
  itemsByKeys(keys: $keys) {
    createdAt
    updatedAt
    key
    name
    model
    production
    origin
    id
    price
    pricePolicy
    fixedPrice
    searchKeywords
    category {
      key
      name
    }
    content
    shippingFee
    shippingType
    images(size: large)
    status
    options {
      optionAttributes {
        name
        value
      }
      price
      quantity
      key
    }
    taxFree
    adultOnly
    returnable
    noReturnReason
    guaranteedShippingPeriod
    openmarketSellable
    boxQuantity
    attributes
    closingTime
    metadata
  }
}
"""
        try:
            status_code, detail_payload = client.graphql(detail_query, variables={"keys": keys_batch})
            session.add(SupplierRawFetchLog(
                supplier_code="ownerclan",
                account_id=account_id,
                endpoint=f"{settings.ownerclan_graphql_url} (itemsByKeys_bulk)",
                request_payload={"query": "itemsByKeys", "key_count": len(keys_batch)},
                http_status=status_code,
                response_payload=None, # 상세 정보는 너무 크므로 로깅 생략 또는 요약
                error_message=None if status_code == 200 else f"HTTP {status_code}"
            ))
        except Exception as e:
            logger.error(f"오너클랜 상세 정보 일괄 수집 중 오류: {e}")
            continue # 다음 배치 시도

        if status_code == 200 and detail_payload.get("data"):
            nodes = detail_payload["data"].get("itemsByKeys") or []
            for node in nodes:
                item_code = node.get("key")
                if not item_code:
                    continue
                
                # HTML 정규화
                detail_html = node.get("detail_html") or node.get("content")
                if isinstance(detail_html, str) and detail_html.strip():
                    node["detail_html"] = normalize_ownerclan_html(detail_html)
                
                source_updated_at = _parse_ownerclan_datetime(node.get("updatedAt"))

                stmt = insert(SupplierItemRaw).values(
                    supplier_code="ownerclan",
                    item_code=str(item_code),
                    item_key=str(node.get("key")),
                    item_id=str(node.get("id")),
                    source_updated_at=source_updated_at,
                    raw=_sanitize_json(node),
                    fetched_at=datetime.now(timezone.utc),
                )

                stmt = stmt.on_conflict_do_update(
                    index_elements=["supplier_code", "item_code"],
                    set_={
                        "item_key": stmt.excluded.item_key,
                        "item_id": stmt.excluded.item_id,
                        "raw": stmt.excluded.raw,
                        "fetched_at": stmt.excluded.fetched_at,
                    },
                )
                session.execute(stmt)
                processed += 1

                if max_items > 0 and processed >= max_items:
                    break

        # 상태 업데이트 및 커밋
        upsert_sync_state(session, "items_raw", date_to_ms, cursor)
        job.progress = processed
        session.commit()

        if (max_items > 0 and processed >= max_items) or \
           (max_pages > 0 and page_count >= max_pages) or \
           not (last_page_info.get("hasNextPage") and cursor):
            break

        time.sleep(1.0) # 배치 간 대기


    return OwnerClanJobResult(processed=processed)


def start_background_ownerclan_job(session_factory: Any, job_id: uuid.UUID) -> None:
    def _run() -> None:
        for _ in range(200):
            with session_factory() as session:
                job = session.get(SupplierSyncJob, job_id)
                if job:
                    job.status = "running"
                    job.started_at = datetime.now(timezone.utc)
                    session.commit()
                    break
            time.sleep(0.1)
        else:
            return

        try:
            with session_factory() as session:
                job = session.get(SupplierSyncJob, job_id)
                if not job:
                    return
                run_ownerclan_job(session, job)
                job.status = "succeeded"
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
                
            # Trigger Sourcing Candidate Conversion (Best Effort)
            try:
                with session_factory() as session:
                    from app.services.sourcing_service import SourcingService
                    service = SourcingService(session)
                    service.import_from_raw(limit=2000)
            except Exception as cvt_e:
                logger.warning(f"Raw 데이터를 소싱 후보로 변환하는 중 오류가 발생했습니다: {cvt_e}")

        except Exception as e:
            with session_factory() as session:
                job = session.get(SupplierSyncJob, job_id)
                if not job:
                    return
                job.status = "failed"
                job.last_error = str(e)
                job.finished_at = datetime.now(timezone.utc)
                session.commit()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
