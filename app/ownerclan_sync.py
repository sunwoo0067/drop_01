from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


def get_primary_ownerclan_account(session: Session) -> SupplierAccount:
    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )

    if not account:
        raise RuntimeError("대표 오너클랜 계정이 설정되어 있지 않습니다")

    return account


def _get_ownerclan_access_token(session: Session) -> tuple[uuid.UUID, str]:
    account = get_primary_ownerclan_account(session)
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
    account_id, access_token = _get_ownerclan_access_token(session)

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    params = dict(job.params or {})
    page = int(params.get("page", 1))
    limit = int(params.get("limit", 50))
    include_details = bool(params.get("includeDetails", False))

    processed = 0

    while True:
        query_params: dict[str, Any] = {"page": page, "limit": limit}
        for k in ("start_date", "end_date", "status"):
            if params.get(k):
                query_params[k] = params[k]

        status_code, payload = client.get("/v1/orders", params=query_params)

        session.add(
            SupplierRawFetchLog(
                supplier_code="ownerclan",
                account_id=account_id,
                endpoint=f"{settings.ownerclan_api_base_url}/v1/orders",
                request_payload={"params": query_params},
                http_status=status_code,
                response_payload=payload,
                error_message=None,
            )
        )

        if status_code == 401:
            raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
        if status_code >= 400:
            raise RuntimeError(f"오너클랜 주문 목록 호출 실패: HTTP {status_code}")
        if payload.get("success") is False and payload.get("error"):
            raise RuntimeError(f"오너클랜 주문 목록 오류: {payload.get('error')}")

        data = payload.get("data") or payload
        orders = data.get("orders") or []

        for order in orders:
            order_id = (order or {}).get("order_id") or (order or {}).get("orderId")
            if not order_id:
                continue

            raw_order = order
            if include_details:
                s2, detail = client.get(f"/v1/order/{order_id}")
                session.add(
                    SupplierRawFetchLog(
                        supplier_code="ownerclan",
                        account_id=account_id,
                        endpoint=f"{settings.ownerclan_api_base_url}/v1/order/{order_id}",
                        request_payload={},
                        http_status=s2,
                        response_payload=detail,
                        error_message=None,
                    )
                )
                if s2 == 200 and detail:
                    raw_order = detail.get("data") or detail

            stmt = insert(SupplierOrderRaw).values(
                supplier_code="ownerclan",
                account_id=account_id,
                order_id=str(order_id),
                raw=_sanitize_json(raw_order),
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["supplier_code", "account_id", "order_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
            )
            session.execute(stmt)
            processed += 1

        job.progress = processed
        session.commit()

        total_pages = data.get("total_pages") or data.get("totalPages")
        has_next = data.get("has_next")
        if isinstance(total_pages, int) and page >= total_pages:
            break
        if has_next is False:
            break
        if not orders:
            break

        page += 1
        time.sleep(1.1)

    return OwnerClanJobResult(processed=processed)


def sync_ownerclan_qna_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    account_id, access_token = _get_ownerclan_access_token(session)

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    params = dict(job.params or {})
    page = int(params.get("page", 1))
    limit = int(params.get("limit", 50))
    include_details = bool(params.get("includeDetails", False))

    processed = 0

    while True:
        query_params: dict[str, Any] = {"page": page, "limit": limit}
        for k in ("start_date", "end_date", "status"):
            if params.get(k):
                query_params[k] = params[k]

        try:
            status_code, payload = client.get("/v1/qna", params=query_params)
        except Exception as e:
            session.add(
                SupplierRawFetchLog(
                    supplier_code="ownerclan",
                    account_id=account_id,
                    endpoint=f"{settings.ownerclan_api_base_url}/v1/qna",
                    request_payload={"params": query_params},
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
                endpoint=f"{settings.ownerclan_api_base_url}/v1/qna",
                request_payload={"params": query_params},
                http_status=status_code,
                response_payload=payload,
                error_message=None,
            )
        )

        session.commit()

        if status_code == 401:
            raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
        if status_code >= 400:
            raise RuntimeError(f"오너클랜 문의 목록 호출 실패: HTTP {status_code}")
        if payload.get("success") is False and payload.get("error"):
            raise RuntimeError(f"오너클랜 문의 목록 오류: {payload.get('error')}")

        data = payload.get("data") or payload
        qna_list = data.get("qna_list") or data.get("qnaList") or []

        for qna in qna_list:
            qna_id = (qna or {}).get("qna_id") or (qna or {}).get("qnaId") or (qna or {}).get("id")
            if not qna_id:
                continue

            raw_qna = qna
            if include_details:
                s2, detail = client.get(f"/v1/qna/{qna_id}")
                session.add(
                    SupplierRawFetchLog(
                        supplier_code="ownerclan",
                        account_id=account_id,
                        endpoint=f"{settings.ownerclan_api_base_url}/v1/qna/{qna_id}",
                        request_payload={},
                        http_status=s2,
                        response_payload=detail,
                        error_message=None,
                    )
                )
                if s2 == 200 and detail:
                    raw_qna = detail.get("data") or detail

            stmt = insert(SupplierQnaRaw).values(
                supplier_code="ownerclan",
                account_id=account_id,
                qna_id=str(qna_id),
                raw=_sanitize_json(raw_qna),
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["supplier_code", "account_id", "qna_id"],
                set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
            )
            session.execute(stmt)
            processed += 1

        job.progress = processed

        total_pages = data.get("total_pages") or data.get("totalPages")
        has_next = data.get("has_next")
        if isinstance(total_pages, int) and page >= total_pages:
            break
        if has_next is False:
            break
        if not qna_list:
            break

        page += 1
        time.sleep(1.1)

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
    account_id, access_token = _get_ownerclan_access_token(session)

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=access_token,
    )

    params = dict(job.params or {})
    query_params: dict[str, Any] = {}
    for k in ("parent_id", "level"):
        if params.get(k) is not None:
            query_params[k] = params[k]

    try:
        status_code, payload = client.get("/v1/categories", params=query_params or None)
    except Exception as e:
        session.add(
            SupplierRawFetchLog(
                supplier_code="ownerclan",
                account_id=account_id,
                endpoint=f"{settings.ownerclan_api_base_url}/v1/categories",
                request_payload={"params": query_params},
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
            endpoint=f"{settings.ownerclan_api_base_url}/v1/categories",
            request_payload={"params": query_params},
            http_status=status_code,
            response_payload=payload,
            error_message=None,
        )
    )

    session.commit()

    if status_code == 401:
        raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
    if status_code >= 400:
        raise RuntimeError(f"오너클랜 카테고리 목록 호출 실패: HTTP {status_code}")

    data = payload.get("data") or payload
    categories = data.get("categories") or data.get("category_list") or data.get("categoryList") or []

    processed = 0
    if isinstance(categories, list):
        for cat in categories:
            if isinstance(cat, dict):
                processed += _upsert_category_tree(session, cat)

    job.progress = processed
    session.commit()
    return OwnerClanJobResult(processed=processed)


def sync_ownerclan_items_raw(session: Session, job: SupplierSyncJob) -> OwnerClanJobResult:
    account_id, access_token = _get_ownerclan_access_token(session)

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
        page_count += 1
        after_fragment = "null" if not cursor else f'"{cursor}"'

        query = f"""
query {{
  allItems(dateFrom: {date_from_ms}, dateTo: {date_to_ms}, after: {after_fragment}, first: {first}) {{
    pageInfo {{
      hasNextPage
      endCursor
    }}
    edges {{
      cursor
      node {{
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
        category {{
          key
          name
        }}
        content
        shippingFee
        shippingType
        images(size: large)
        status
        options {{
          optionAttributes {{
            name
            value
          }}
          price
          quantity
          key
        }}
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
      }}
    }}
  }}
}}
"""

        try:
            status_code, payload = client.graphql(query)
        except Exception as e:
            session.add(
                SupplierRawFetchLog(
                    supplier_code="ownerclan",
                    account_id=account_id,
                    endpoint=settings.ownerclan_graphql_url,
                    request_payload={
                        "query": query,
                        "dateFrom": date_from_ms,
                        "dateTo": date_to_ms,
                        "after": cursor,
                        "first": first,
                    },
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
                request_payload={
                    "query": query,
                    "dateFrom": date_from_ms,
                    "dateTo": date_to_ms,
                    "after": cursor,
                    "first": first,
                },
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

        data = payload.get("data") or {}
        all_items = data.get("allItems") or {}
        page_info = all_items.get("pageInfo") or {}

        edges = all_items.get("edges") or []
        for edge in edges:
            node = (edge or {}).get("node") or {}
            item_code = node.get("itemCode") or node.get("item_code") or node.get("key")
            if not item_code:
                continue

            source_updated_at = _parse_ownerclan_datetime(node.get("updatedAt") or node.get("updated_at"))

            stmt = insert(SupplierItemRaw).values(
                supplier_code="ownerclan",
                item_code=str(item_code),
                item_key=str(node.get("key")) if node.get("key") is not None else None,
                item_id=str(node.get("id")) if node.get("id") is not None else None,
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

        if max_items > 0 and processed >= max_items:
            cursor = page_info.get("endCursor")
            upsert_sync_state(session, "items_raw", date_to_ms, cursor)
            job.progress = processed
            session.commit()
            break

        cursor = page_info.get("endCursor")
        upsert_sync_state(session, "items_raw", date_to_ms, cursor)
        job.progress = processed
        session.commit()

        if max_pages > 0 and page_count >= max_pages:
            break

        has_next = bool(page_info.get("hasNextPage"))
        if not has_next or not cursor:
            break

        time.sleep(1.1)

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
