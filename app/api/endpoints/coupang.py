from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid
from pydantic import BaseModel, Field

from app.db import get_session
from app.models import Product, MarketAccount, MarketOrderRaw, MarketListing, MarketProductRaw
from app.coupang_sync import register_product, sync_coupang_orders_raw, fulfill_coupang_orders_via_ownerclan
from app.coupang_client import CoupangClient
from sqlalchemy.dialects.postgresql import insert

router = APIRouter()

@router.post("/register/{product_id}", status_code=202)
async def register_product_endpoint(
    product_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    쿠팡 상품 등록을 트리거합니다.
    작업은 백그라운드에서 비동기로 수행됩니다.
    """
    # 쿠팡 계정 조회
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()
    
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # 백그라운드 작업 등록
    background_tasks.add_task(execute_coupang_registration, account.id, product.id)
        
    return {"status": "accepted", "message": "쿠팡 상품 등록 작업이 시작되었습니다."}

def execute_coupang_registration(account_id: uuid.UUID, product_id: uuid.UUID):
    """
    별도의 DB 세션을 사용하여 쿠팡 등록 작업을 수행합니다.
    """
    from app.session_factory import session_factory
    
    with session_factory() as session:
        success = register_product(session, account_id, product_id)
        if success:
             # 성공 로깅은 register_product 내부에서 수행됨
             pass
        else:
             # 실패 로깅도 내부 수행됨
             pass


@router.get("/orders/raw", status_code=200)
async def list_coupang_orders_raw(
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    """
    저장된 쿠팡 주문(ordersheets) raw 목록을 조회합니다(디버깅/점검용).
    """
    stmt_acct = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt_acct).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    stmt = (
        select(MarketOrderRaw)
        .where(MarketOrderRaw.market_code == "COUPANG")
        .where(MarketOrderRaw.account_id == account.id)
        .order_by(MarketOrderRaw.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.scalars(stmt).all()
    return [
        {
            "id": str(r.id),
            "orderId": r.order_id,
            "fetchedAt": r.fetched_at.isoformat() if r.fetched_at else None,
            "raw": r.raw,
        }
        for r in rows
    ]


@router.get("/products/{seller_product_id}", status_code=200)
async def get_coupang_product_detail(
    seller_product_id: str,
    session: Session = Depends(get_session),
):
    stmt_acct = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt_acct).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    creds = account.credentials or {}
    client = CoupangClient(
        access_key=creds.get("access_key", ""),
        secret_key=creds.get("secret_key", ""),
        vendor_id=creds.get("vendor_id", ""),
    )

    code, data = client.get_product(str(seller_product_id).strip())

    data_obj = data.get("data") if isinstance(data, dict) else None
    if not isinstance(data_obj, dict):
        data_obj = {}

    stmt = insert(MarketProductRaw).values(
        market_code="COUPANG",
        account_id=account.id,
        market_item_id=str(seller_product_id).strip(),
        raw=data_obj,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["market_code", "account_id", "market_item_id"],
        set_={"raw": stmt.excluded.raw, "fetched_at": stmt.excluded.fetched_at},
    )
    session.execute(stmt)

    seller_product_name = data_obj.get("sellerProductName") or data_obj.get("seller_product_name")
    items = data_obj.get("items") if isinstance(data_obj.get("items"), list) else []
    vendor_item_ids: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        vid = it.get("vendorItemId") or it.get("vendor_item_id")
        if vid is None:
            continue
        vendor_item_ids.append(str(vid))

    return {
        "httpStatus": code,
        "sellerProductId": str(seller_product_id).strip(),
        "sellerProductName": seller_product_name,
        "vendorItemIds": vendor_item_ids,
        "raw": data,
    }


class CoupangOrderSyncIn(BaseModel):
    createdAtFrom: str = Field(..., description="yyyy-MM-dd 또는 ISO-8601")
    createdAtTo: str = Field(..., description="yyyy-MM-dd 또는 ISO-8601")
    status: str | None = None
    maxPerPage: int = Field(default=100, ge=1, le=100)


@router.post("/orders/sync", status_code=202)
async def sync_orders_endpoint(
    payload: CoupangOrderSyncIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    쿠팡 발주서(주문) raw 동기화를 트리거합니다.
    """
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()

    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    background_tasks.add_task(
        execute_coupang_order_sync,
        account.id,
        payload.createdAtFrom,
        payload.createdAtTo,
        payload.status,
        payload.maxPerPage,
    )

    return {"status": "accepted", "message": "쿠팡 주문 동기화 작업이 시작되었습니다."}


def execute_coupang_order_sync(
    account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None,
    max_per_page: int,
):
    from app.session_factory import session_factory

    with session_factory() as session:
        sync_coupang_orders_raw(
            session,
            account_id=account_id,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            status=status,
            max_per_page=max_per_page,
        )


class CoupangFulfillOwnerClanIn(BaseModel):
    createdAtFrom: str = Field(..., description="yyyy-MM-dd 또는 ISO-8601")
    createdAtTo: str = Field(..., description="yyyy-MM-dd 또는 ISO-8601")
    status: str | None = None
    maxPerPage: int = Field(default=100, ge=1, le=100)
    dryRun: bool = Field(default=False)
    limit: int = Field(default=0, ge=0, le=5000)


@router.post("/orders/fulfill/ownerclan", status_code=202)
async def fulfill_orders_ownerclan_endpoint(
    payload: CoupangFulfillOwnerClanIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    쿠팡 주문(ordersheets) → 오너클랜 주문 생성(발주) 연동을 트리거합니다.
    """
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()

    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    background_tasks.add_task(
        execute_coupang_ownerclan_fulfill,
        account.id,
        payload.createdAtFrom,
        payload.createdAtTo,
        payload.status,
        payload.maxPerPage,
        payload.dryRun,
        payload.limit,
    )

    return {"status": "accepted", "message": "쿠팡→오너클랜 주문 연동 작업이 시작되었습니다."}


@router.post("/orders/fulfill/ownerclan/preview", status_code=200)
async def fulfill_orders_ownerclan_preview_endpoint(
    payload: CoupangFulfillOwnerClanIn,
):
    """
    쿠팡 주문(ordersheets) → 오너클랜 발주 매핑을 **dry-run** 으로 즉시 점검합니다.
    (실제 발주는 하지 않음)
    """
    # get_session()은 session.begin() 트랜잭션 컨텍스트 안에서 yield 하므로
    # 내부에서 commit()을 호출하는 로직(쿠팡 raw 저장 등)과 충돌할 수 있어
    # preview는 별도 세션으로 실행합니다.
    from app.session_factory import session_factory

    with session_factory() as preview_session:
        stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        account = preview_session.scalars(stmt).first()

        if not account:
            raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

        result = fulfill_coupang_orders_via_ownerclan(
            preview_session,
            coupang_account_id=account.id,
            created_at_from=payload.createdAtFrom,
            created_at_to=payload.createdAtTo,
            status=payload.status,
            max_per_page=payload.maxPerPage,
            dry_run=True,
            limit=payload.limit,
        )
        return {"dryRun": True, "result": result}


def execute_coupang_ownerclan_fulfill(
    account_id: uuid.UUID,
    created_at_from: str,
    created_at_to: str,
    status: str | None,
    max_per_page: int,
    dry_run: bool,
    limit: int,
):
    from app.session_factory import session_factory

    with session_factory() as session:
        fulfill_coupang_orders_via_ownerclan(
            session,
            coupang_account_id=account_id,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            status=status,
            max_per_page=max_per_page,
            dry_run=dry_run,
            limit=limit,
        )


class CoupangListingLinkIn(BaseModel):
    sellerProductId: str
    productId: uuid.UUID
    status: str = "ACTIVE"


@router.post("/listings/link", status_code=200)
async def link_coupang_listing(
    payload: CoupangListingLinkIn,
    session: Session = Depends(get_session),
):
    """
    쿠팡 sellerProductId ↔ 내부 Product 를 수동으로 연결합니다.
    (쿠팡 주문 → 오너클랜 발주를 위해 MarketListing 매핑이 필요)
    """
    stmt_acct = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt_acct).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    product = session.get(Product, payload.productId)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    seller_product_id = str(payload.sellerProductId).strip()
    if not seller_product_id:
        raise HTTPException(status_code=400, detail="sellerProductId가 필요합니다.")

    stmt = insert(MarketListing).values(
        product_id=product.id,
        market_account_id=account.id,
        market_item_id=seller_product_id,
        status=str(payload.status or "ACTIVE"),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["market_account_id", "market_item_id"],
        set_={"product_id": product.id, "status": str(payload.status or "ACTIVE")},
    )
    session.execute(stmt)

    row = session.execute(
        select(MarketListing).where(MarketListing.market_account_id == account.id).where(MarketListing.market_item_id == seller_product_id)
    ).scalars().first()

    return {
        "linked": True,
        "listing": {
            "id": str(row.id) if row else None,
            "productId": str(product.id),
            "marketAccountId": str(account.id),
            "sellerProductId": seller_product_id,
            "status": str(payload.status or "ACTIVE"),
        },
    }
