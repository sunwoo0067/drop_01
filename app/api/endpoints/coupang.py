from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
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


def _tag_reason(reason: str | None) -> str | None:
    if reason is None:
        return None

    r = str(reason)
    if not r:
        return r

    if r.startswith("["):
        return r

    low = r.lower()

    if "supplier_item_id" in low and ("없" in r or "none" in low):
        return f"[BLOCKED] {r}"
    if "자동 보정 실패" in r or "autofix" in low:
        return f"[AUTOFIX] {r}"
    if "가공/이미지" in r or "images=" in low or "images=" in r:
        return f"[IMAGE] {r}"
    if "최소 설정 가격은 3000" in r or "3000원" in r and "최소" in r and "가격" in r:
        return f"[PRICE_MIN] {r}"
    if (
        "필수 속성" in r
        or "필수속성" in r
        or "required attribute" in low
        or "attributes" in low
        or "attribute" in low
        or "옵션 속성" in r
    ):
        return f"[ATTR_REQUIRED] {r}"
    if (
        "카테고리" in r
        or "displaycategorycode" in low
        or "category" in low
        or "categorycode" in low
    ):
        return f"[CATEGORY] {r}"
    if (
        "상품정보" in r
        or "제공고시" in r
        or "고시" in r
        or "notices" in low
        or "notice" in low
        or "noticecategory" in low
    ):
        return f"[NOTICE] {r}"
    if "반품" in r and "센터" in r or "출고" in r and "센터" in r or "센터 코드" in r:
        return f"[CENTER] {r}"
    if "invalid signature" in low or "unauthorized" in low or "http=401" in low or " 401" in low:
        return f"[AUTH] {r}"

    return f"[UNKNOWN] {r}"


def _get_images_count(product: Product) -> int:
    imgs = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    return len(imgs)


class ProductBulkRegisterRequest(BaseModel):
    productIds: list[uuid.UUID] | None = None


@router.post("/register/bulk", status_code=202)
async def register_products_bulk_endpoint(
    payload: ProductBulkRegisterRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    auto_fix: bool = Query(default=False, alias="autoFix"),
    force_fetch_ownerclan: bool = Query(default=True, alias="forceFetchOwnerClan"),
    augment_images: bool = Query(default=True, alias="augmentImages"),
    wait: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Triggers bulk registration of products to Coupang.
    If productIds provided, only registers those.
    Otherwise, registers all ready products (DRAFT + COMPLETED processing).
    """
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()
    
    if not account:
        raise HTTPException(status_code=400, detail="Active Coupang account not found.")

    if payload.productIds and not auto_fix and not wait:
        products = session.scalars(select(Product).where(Product.id.in_(payload.productIds))).all()
        missing: list[dict] = []
        for p in products:
            if _get_images_count(p) < 5:
                missing.append(
                    {
                        "productId": str(p.id),
                        "processingStatus": p.processing_status,
                        "imagesCount": _get_images_count(p),
                    }
                )
        if missing:
            raise HTTPException(
                status_code=409,
                detail={"message": "쿠팡 등록을 위해서는 가공 완료 및 이미지 5장이 필요합니다", "items": missing[:50]},
            )

    if wait:
        # 동기 실행(운영용). bulk는 시간이 걸릴 수 있으므로 limit을 반드시 사용합니다.
        from app.services.coupang_ready_service import ensure_product_ready_for_coupang

        if payload.productIds:
            stmt = select(Product).where(Product.id.in_(payload.productIds))
        else:
            stmt = select(Product).where(Product.status == "DRAFT")
        stmt = stmt.order_by(Product.updated_at.desc()).limit(int(limit))
        products = session.scalars(stmt).all()

        total = 0
        ready_ok = 0
        registered_ok = 0
        registered_fail = 0
        blocked = 0

        registered_ok_ids: list[str] = []
        registered_fail_ids: list[str] = []
        registered_fail_items: list[dict] = []
        blocked_ids: list[str] = []

        for p in products:
            total += 1

            if not p.supplier_item_id:
                blocked += 1
                blocked_ids.append(str(p.id))
                continue

            if auto_fix:
                ready = ensure_product_ready_for_coupang(
                    session,
                    str(p.id),
                    min_images_required=5,
                    force_fetch_ownerclan=bool(force_fetch_ownerclan),
                    augment_images=bool(augment_images),
                )
                if not ready.get("ok"):
                    registered_fail += 1
                    registered_fail_ids.append(str(p.id))
                    raw_reason = "자동 보정 실패"
                    registered_fail_items.append(
                        {
                            "productId": str(p.id),
                            "reason": _tag_reason(raw_reason),
                            "reasonRaw": raw_reason,
                            "ready": ready,
                        }
                    )
                    continue

            if _get_images_count(p) < 5:
                registered_fail += 1
                registered_fail_ids.append(str(p.id))
                raw_reason = f"가공/이미지 조건 미달(processingStatus={p.processing_status}, images={_get_images_count(p)})"
                registered_fail_items.append(
                    {
                        "productId": str(p.id),
                        "reason": _tag_reason(raw_reason),
                        "reasonRaw": raw_reason,
                    }
                )
                continue

            ready_ok += 1
            ok, reason = register_product(session, account.id, p.id)
            if ok:
                p.status = "ACTIVE"
                session.commit()
                registered_ok += 1
                registered_ok_ids.append(str(p.id))
            else:
                registered_fail += 1
                registered_fail_ids.append(str(p.id))
                raw_reason = reason or "쿠팡 등록 실패"
                registered_fail_items.append(
                    {
                        "productId": str(p.id),
                        "reason": _tag_reason(raw_reason),
                        "reasonRaw": raw_reason,
                    }
                )

        return {
            "status": "completed",
            "autoFix": bool(auto_fix),
            "limit": int(limit),
            "summary": {
                "total": total,
                "readyOk": ready_ok,
                "registeredOk": registered_ok,
                "registeredFail": registered_fail,
                "blocked": blocked,
                "registeredOkIds": registered_ok_ids[:200],
                "registeredFailIds": registered_fail_ids[:200],
                "registeredFailItems": registered_fail_items[:200],
                "blockedIds": blocked_ids[:200],
            },
        }

    background_tasks.add_task(
        execute_bulk_coupang_registration,
        account.id,
        payload.productIds,
        bool(auto_fix),
        bool(force_fetch_ownerclan),
        bool(augment_images),
    )

    return {
        "status": "accepted",
        "message": "Bulk registration started.",
        "autoFix": bool(auto_fix),
    }


@router.get("/register/bulk/preview", status_code=200)
async def preview_register_products_bulk(
    session: Session = Depends(get_session),
    product_ids: list[uuid.UUID] | None = Query(default=None, alias="productIds"),
    limit: int = Query(default=50, ge=1, le=200),
):
    stmt = select(Product).where(Product.status == "DRAFT").order_by(Product.updated_at.desc()).limit(int(limit))
    if product_ids:
        stmt = stmt.where(Product.id.in_(product_ids))
    products = session.scalars(stmt).all()

    ready: list[dict] = []
    needs_fix: list[dict] = []
    blocked: list[dict] = []

    for p in products:
        images_count = _get_images_count(p)
        base = {
            "productId": str(p.id),
            "supplierItemId": str(p.supplier_item_id) if p.supplier_item_id else None,
            "processingStatus": p.processing_status,
            "imagesCount": images_count,
        }

        if not p.supplier_item_id:
            blocked.append({**base, "reason": "supplier_item_id 없음"})
            continue

        if p.processing_status == "COMPLETED" and images_count >= 5:
            ready.append(base)
        else:
            needs_fix.append(base)

    return {
        "limit": int(limit),
        "counts": {
            "ready": len(ready),
            "needsFix": len(needs_fix),
            "blocked": len(blocked),
        },
        "ready": ready[:200],
        "needsFix": needs_fix[:200],
        "blocked": blocked[:200],
    }


@router.post("/register/{product_id}", status_code=202)
async def register_product_endpoint(
    product_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    auto_fix: bool = Query(default=False, alias="autoFix"),
    wait: bool = Query(default=False),
    force_fetch_ownerclan: bool = Query(default=True, alias="forceFetchOwnerClan"),
    augment_images: bool = Query(default=True, alias="augmentImages"),
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

    if auto_fix:
        from app.services.coupang_ready_service import ensure_product_ready_for_coupang

        ready = ensure_product_ready_for_coupang(
            session,
            str(product.id),
            min_images_required=5,
            force_fetch_ownerclan=bool(force_fetch_ownerclan),
            augment_images=bool(augment_images),
        )

        if not ready.get("ok"):
            raise HTTPException(
                status_code=409,
                detail={"message": "쿠팡 등록을 위한 자동 보정에 실패했습니다", "ready": ready},
            )

        if wait:
            success, reason = register_product(session, account.id, product.id)
            if success:
                product.status = "ACTIVE"
                session.commit()
            return {
                "status": "completed",
                "success": bool(success),
                "reason": _tag_reason(reason),
                "reasonRaw": (str(reason) if reason is not None else None),
                "ready": ready,
            }

        background_tasks.add_task(
            execute_coupang_registration,
            account.id,
            product.id,
            True,
            bool(force_fetch_ownerclan),
            bool(augment_images),
        )
        return {"status": "accepted", "message": "쿠팡 상품 등록 작업이 시작되었습니다.", "autoFix": True}

    processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    if product.processing_status != "COMPLETED" or len(processed_images) < 5:
        raise HTTPException(
            status_code=409,
            detail=f"쿠팡 등록을 위해서는 가공 완료 및 이미지 5장이 필요합니다(processingStatus={product.processing_status}, images={len(processed_images)})",
        )

    background_tasks.add_task(execute_coupang_registration, account.id, product.id, False, False, False)
    return {"status": "accepted", "message": "쿠팡 상품 등록 작업이 시작되었습니다."}


@router.put("/products/{product_id}", status_code=200)
def update_coupang_product_endpoint(
    product_id: uuid.UUID,
    session: Session = Depends(get_session),
):
    """
    내부 Product 정보를 기반으로 쿠팡에 이미 등록된 상품을 업데이트합니다.
    """
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    from app.coupang_sync import update_product_on_coupang
    success, reason = update_product_on_coupang(session, account.id, product_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=f"수정 실패: {reason}")
    
    return {"status": "success", "message": "상품 정보가 업데이트되었습니다."}


@router.delete("/products/{seller_product_id}", status_code=200)
def delete_coupang_product_endpoint(
    seller_product_id: str,
    session: Session = Depends(get_session),
):
    """
    쿠팡에서 상품을 삭제합니다. (모든 아이템 판매중지 후 삭제)
    """
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    from app.coupang_sync import delete_product_from_coupang
    success, reason = delete_product_from_coupang(session, account.id, seller_product_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=f"삭제 실패: {reason}")
    
    return {"status": "success", "message": "상품이 쿠팡에서 삭제되었습니다."}


def execute_bulk_coupang_registration(
    account_id: uuid.UUID,
    product_ids: list[uuid.UUID] | None,
    auto_fix: bool,
    force_fetch_ownerclan: bool,
    augment_images: bool,
):
    from app.session_factory import session_factory
    from app.coupang_sync import register_products_bulk
    from app.services.coupang_ready_service import ensure_product_ready_for_coupang
    
    with session_factory() as session:
        if not auto_fix:
            register_products_bulk(session, account_id, product_ids)
            return

        stmt = select(Product).where(Product.status == "DRAFT")
        if product_ids:
            stmt = stmt.where(Product.id.in_(product_ids))
        products = session.scalars(stmt).all()

        total = 0
        ready_ok = 0
        registered_ok = 0
        registered_fail = 0

        for p in products:
            total += 1
            ready = ensure_product_ready_for_coupang(
                session,
                str(p.id),
                min_images_required=5,
                force_fetch_ownerclan=bool(force_fetch_ownerclan),
                augment_images=bool(augment_images),
            )
            if not ready.get("ok"):
                continue

            ready_ok += 1
            ok, _reason = register_product(session, account_id, p.id)
            if ok:
                p.status = "ACTIVE"
                session.commit()
                registered_ok += 1
            else:
                registered_fail += 1

        import logging

        logging.getLogger(__name__).info(
            "쿠팡 벌크 자동등록 요약(total=%s, readyOk=%s, registeredOk=%s, registeredFail=%s)",
            total,
            ready_ok,
            registered_ok,
            registered_fail,
        )


def execute_coupang_registration(
    account_id: uuid.UUID,
    product_id: uuid.UUID,
    auto_fix: bool,
    force_fetch_ownerclan: bool,
    augment_images: bool,
):
    """
    별도의 DB 세션을 사용하여 쿠팡 등록 작업을 수행합니다.
    """
    from app.session_factory import session_factory
    from app.services.coupang_ready_service import ensure_product_ready_for_coupang
    
    with session_factory() as session:
        if auto_fix:
            ready = ensure_product_ready_for_coupang(
                session,
                str(product_id),
                min_images_required=5,
                force_fetch_ownerclan=bool(force_fetch_ownerclan),
                augment_images=bool(augment_images),
            )
            if not ready.get("ok"):
                return

        success, _reason = register_product(session, account_id, product_id)
        if success:
            p = session.get(Product, product_id)
            if p and p.status == "DRAFT":
                p.status = "ACTIVE"
                session.commit()
        else:
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
        access_key=str(creds.get("access_key", "") or "").strip(),
        secret_key=str(creds.get("secret_key", "") or "").strip(),
        vendor_id=str(creds.get("vendor_id", "") or "").strip(),
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


@router.get("/centers", status_code=200)
async def list_coupang_centers(
    session: Session = Depends(get_session),
    page_size: int = Query(default=10, ge=10, le=50, alias="pageSize"),
):
    stmt_acct = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt_acct).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    creds = account.credentials or {}
    client = CoupangClient(
        access_key=str(creds.get("access_key", "") or "").strip(),
        secret_key=str(creds.get("secret_key", "") or "").strip(),
        vendor_id=str(creds.get("vendor_id", "") or "").strip(),
    )

    outbound_status, outbound_data = client.get_outbound_shipping_centers(page_size=int(page_size))
    return_status, return_data = client.get_return_shipping_centers(page_size=int(page_size))

    def _extract_list(data: dict) -> list[dict]:
        if not isinstance(data, dict):
            return []
        data_obj = data.get("data") if isinstance(data.get("data"), dict) else None
        if isinstance(data_obj, dict):
            content = data_obj.get("content")
            if isinstance(content, list):
                return [it for it in content if isinstance(it, dict)]
        content2 = data.get("content")
        if isinstance(content2, list):
            return [it for it in content2 if isinstance(it, dict)]
        return []

    outbound_items = _extract_list(outbound_data)
    return_items = _extract_list(return_data)

    outbound_codes: list[str] = []
    for it in outbound_items:
        v = it.get("outboundShippingPlaceCode") or it.get("outbound_shipping_place_code") or it.get("placeCode")
        if v is None:
            continue
        outbound_codes.append(str(v))

    return_codes: list[str] = []
    for it in return_items:
        v = it.get("returnCenterCode") or it.get("return_center_code")
        if v is None:
            continue
        return_codes.append(str(v))

    return {
        "outbound": {
            "httpStatus": outbound_status,
            "codes": outbound_codes[:50],
            "count": len(outbound_items),
            "raw": outbound_data,
        },
        "return": {
            "httpStatus": return_status,
            "codes": return_codes[:50],
            "count": len(return_items),
            "raw": return_data,
        },
    }


class CoupangOrderSyncIn(BaseModel):
    createdAtFrom: str = Field(..., description="yyyy-MM-dd 또는 ISO-8601")
    createdAtTo: str = Field(..., description="yyyy-MM-dd 또는 ISO-8601")
    status: str | None = None
    maxPerPage: int = Field(default=100, ge=1, le=100)


class CoupangCredentialsUpdateIn(BaseModel):
    accessKey: str | None = None
    secretKey: str | None = None
    vendorId: str | None = None
    vendorUserId: str | None = None


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


@router.post("/account/credentials", status_code=200)
async def update_coupang_credentials(
    payload: CoupangCredentialsUpdateIn,
    session: Session = Depends(get_session),
):
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()
    if not account:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    creds = account.credentials or {}
    if not isinstance(creds, dict):
        creds = {}

    def _clean(v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    access_key = _clean(payload.accessKey)
    secret_key = _clean(payload.secretKey)
    vendor_id = _clean(payload.vendorId)
    vendor_user_id = _clean(payload.vendorUserId)

    if access_key is not None:
        creds["access_key"] = access_key
    if secret_key is not None:
        creds["secret_key"] = secret_key
    if vendor_id is not None:
        creds["vendor_id"] = vendor_id
    if vendor_user_id is not None:
        creds["vendor_user_id"] = vendor_user_id

    account.credentials = creds
    session.commit()

    def _mask(v: object) -> str | None:
        if v is None:
            return None
        s = str(v)
        if not s:
            return ""
        if len(s) <= 6:
            return "***"
        return f"{s[:3]}***{s[-2:]}"

    saved = account.credentials or {}
    return {
        "status": "updated",
        "accountId": str(account.id),
        "isActive": bool(account.is_active),
        "credentials": {
            "access_key": _mask(saved.get("access_key")),
            "secret_key": _mask(saved.get("secret_key")),
            "vendor_id": _mask(saved.get("vendor_id")),
            "vendor_user_id": _mask(saved.get("vendor_user_id")),
        },
    }


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
