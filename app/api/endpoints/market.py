"""
마켓 상품 관리 API 엔드포인트
- 마켓에 등록된 상품 목록 조회
- MarketListing과 Product 조인하여 상품 정보 반환
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, func
import uuid

from app.db import get_session
from app.models import Product, MarketListing, MarketAccount, MarketProductRaw

router = APIRouter()



@router.get("/listings", status_code=200)
def list_market_listings(
    session: Session = Depends(get_session),
    market_code: str = Query(default="COUPANG", alias="marketCode"),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    마켓에 등록된 상품 목록을 조회합니다.
    MarketListing 테이블을 기준으로 조회합니다.
    """
    # 대상 계정 ID 목록 추출
    if account_id:
        account_ids = [account_id]
    else:
        stmt_accounts = select(MarketAccount.id).where(
            MarketAccount.market_code == market_code,
            MarketAccount.is_active == True
        )
        account_ids = session.scalars(stmt_accounts).all()
    
    if not account_ids:
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "message": f"활성 상태의 {market_code} 계정이 없습니다."
        }
    
    # 카운트 쿼리
    count_stmt = select(func.count(MarketListing.id)).where(
        MarketListing.market_account_id.in_(account_ids)
    )
    if status:
        count_stmt = count_stmt.where(MarketListing.status == status)
    total = session.scalar(count_stmt) or 0
    
    # 목록 쿼리
    stmt = (
        select(MarketListing)
        .where(MarketListing.market_account_id.in_(account_ids))
        .order_by(MarketListing.linked_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(MarketListing.status == status)
    
    listings = session.scalars(stmt).all()
    
    items = []
    for listing in listings:
        items.append({
            "id": str(listing.id),
            "productId": str(listing.product_id),
            "marketAccountId": str(listing.market_account_id),
            "marketItemId": listing.market_item_id,
            "status": listing.status,
            "linkedAt": listing.linked_at.isoformat() if listing.linked_at else None,
        })
    
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/products", status_code=200)
def list_market_products(
    session: Session = Depends(get_session),
    market_code: str = Query(default="COUPANG", alias="marketCode"),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    마켓에 등록된 상품 목록을 Product 정보와 함께 조회합니다.
    Product.status가 ACTIVE인 상품을 조회합니다.
    """
    from app.db import get_session as get_dropship_session
    from app.session_factory import session_factory
    
    # 대상 계정 ID 목록 추출
    if account_id:
        account_ids = [account_id]
    else:
        stmt_accounts = select(MarketAccount.id).where(
            MarketAccount.market_code == market_code,
            MarketAccount.is_active == True
        )
        account_ids = session.scalars(stmt_accounts).all()
    
    if not account_ids:
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }
    
    # MarketListing 조회
    stmt = (
        select(MarketListing)
        .where(MarketListing.market_account_id.in_(account_ids))
        .order_by(MarketListing.linked_at.desc())
        .offset(offset)
        .limit(limit)
    )
    listings = session.scalars(stmt).all()
    
    # Product 정보 조회 (Dropship DB에서)
    product_ids = [listing.product_id for listing in listings]
    
    items = []
    
    # Dropship DB에서 Product 정보 조회
    with session_factory() as dropship_session:
        if product_ids:
            products_stmt = select(Product).where(Product.id.in_(product_ids))
            products = dropship_session.scalars(products_stmt).all()
            product_map = {p.id: p for p in products}
        else:
            product_map = {}
        
        for listing in listings:
            product = product_map.get(listing.product_id)
            items.append({
                "id": str(listing.id),
                "productId": str(listing.product_id),
                "marketAccountId": str(listing.market_account_id),
                "marketItemId": listing.market_item_id,
                "status": listing.status,
                "coupangStatus": listing.coupang_status,
                "rejectionReason": listing.rejection_reason,
                "linkedAt": listing.linked_at.isoformat() if listing.linked_at else None,
                # Product 정보
                "name": product.name if product else None,
                "processedName": product.processed_name if product else None,
                "sellingPrice": product.selling_price if product else 0,
                "processedImageUrls": product.processed_image_urls if product else [],
                "productStatus": product.status if product else None,
                "processingStatus": product.processing_status if product else None,
            })
    
    # 총 개수
    count_stmt = select(func.count(MarketListing.id)).where(
        MarketListing.market_account_id.in_(account_ids)
    )
    total = session.scalar(count_stmt) or 0
    
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "marketCode": market_code,
        "accountIds": [str(aid) for aid in account_ids],
    }


@router.post("/products/sync", status_code=202)
def sync_market_products(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    market_code: str = Query(default="COUPANG", alias="marketCode"),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
    deep: bool = Query(default=False),
) -> dict:
    if market_code == "COUPANG":
        from app.coupang_sync import sync_coupang_products
        sync_func = sync_coupang_products
    elif market_code == "SMARTSTORE":
        from app.smartstore_sync import sync_smartstore_products
        sync_func = sync_smartstore_products
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 마켓 코드입니다: {market_code}")

    if account_id:
        accounts = session.scalars(select(MarketAccount).where(MarketAccount.id == account_id)).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == market_code, MarketAccount.is_active == True)
        ).all()
        
    if not accounts:
        raise HTTPException(status_code=400, detail=f"활성 상태의 {market_code} 계정을 찾을 수 없습니다.")

    for account in accounts:
        background_tasks.add_task(sync_func, session, account.id, deep=bool(deep))
        
    return {"status": "accepted", "message": f"{market_code} 상품 동기화({len(accounts)}개 계정)가 백그라운드에서 시작되었습니다.", "deep": bool(deep)}


@router.get("/products/raw", status_code=200)
def list_market_products_raw(
    session: Session = Depends(get_session),
    market_code: str = Query(default="COUPANG", alias="marketCode"),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    # 대상 계정 ID 목록 추출
    if account_id:
        account_ids = [account_id]
        # 해당 계정의 market_code를 가져옴
        acc = session.get(MarketAccount, account_id)
        current_market_code = acc.market_code if acc else market_code
    else:
        stmt_accounts = select(MarketAccount.id).where(
            MarketAccount.market_code == market_code,
            MarketAccount.is_active == True
        )
        account_ids = session.scalars(stmt_accounts).all()
        current_market_code = market_code
    
    if not account_ids:
        raise HTTPException(status_code=400, detail=f"활성 상태의 {market_code} 계정을 찾을 수 없습니다.")

    stmt = (
        select(MarketProductRaw)
        .where(MarketProductRaw.market_code == current_market_code)
        .where(MarketProductRaw.account_id.in_(account_ids))
        .order_by(MarketProductRaw.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.scalars(stmt).all()

    items: list[dict] = []
    for row in rows:
        raw = row.raw if isinstance(row.raw, dict) else {}
        status_name = raw.get("statusName") or raw.get("status_name")
        approval_status = raw.get("status") or status_name
        sale_status = None
        sale_started_at = raw.get("saleStartedAt") or raw.get("sale_started_at")
        sale_ended_at = raw.get("saleEndedAt") or raw.get("sale_ended_at")
        try:
            from datetime import datetime, timezone

            started = datetime.fromisoformat(str(sale_started_at)) if sale_started_at else None
            ended = datetime.fromisoformat(str(sale_ended_at)) if sale_ended_at else None
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if started and ended:
                sale_status = "ACTIVE" if started <= now <= ended else "SUSPENDED"
        except Exception:
            sale_status = None

        status_override = str(approval_status or "").strip().upper()
        if status_override == "SUSPENDED" or "판매중지" in str(status_name or ""):
            sale_status = "SUSPENDED"

        items.append(
            {
                "id": str(row.id),
                "productId": None,
                "marketAccountId": str(row.account_id),
                "marketItemId": row.market_item_id,
                "status": sale_status or approval_status,
                "coupangStatus": approval_status,
                "rejectionReason": None,
                "linkedAt": row.fetched_at.isoformat() if row.fetched_at else None,
                "name": raw.get("sellerProductName") or raw.get("seller_product_name"),
                "processedName": raw.get("sellerProductName") or raw.get("seller_product_name"),
                "sellingPrice": raw.get("salePrice") or raw.get("sale_price") or raw.get("price"),
                "processedImageUrls": [raw.get("imageUrl") or raw.get("image_url")] if raw.get("imageUrl") or raw.get("image_url") else [],
                "productStatus": None,
                "processingStatus": None,
            }
        )

    total = session.scalar(
        select(func.count(MarketProductRaw.id))
        .where(MarketProductRaw.market_code == current_market_code)
        .where(MarketProductRaw.account_id.in_(account_ids))
    ) or 0

    return {
        "items": items,
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "marketCode": current_market_code,
        "accountIds": [str(aid) for aid in account_ids],
        "source": "raw",
    }
