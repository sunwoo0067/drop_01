from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
import asyncio
import uuid
from pydantic import BaseModel, Field

import re
from datetime import datetime, timezone

from app.db import get_session
from app.models import Product, MarketAccount, MarketOrderRaw, MarketListing, MarketProductRaw, SupplierRawFetchLog
from app.services.order_sync_retry import get_coupang_client_from_account, retry_coupang_failures
from app.coupang_sync import (
    register_product,
    sync_coupang_orders_raw,
    fulfill_coupang_orders_via_ownerclan,
    sync_ownerclan_orders_to_coupang_invoices,
    sync_market_listing_status,
)
from app.coupang_client import CoupangClient
from sqlalchemy.dialects.postgresql import insert

router = APIRouter()


def _is_skipped_reason(reason: str | None) -> bool:
    return bool(reason) and str(reason).startswith("SKIPPED:")


def _to_https_url(url: str) -> str:
    s = str(url or "").strip()
    if not s:
        return s
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("http://"):
        return "https://" + s[len("http://") :]
    return s


def _extract_coupang_image_url(image_obj: dict) -> str | None:
    if not isinstance(image_obj, dict):
        return None

    def _build_coupang_cdn_url(path: str) -> str:
        s = str(path or "").strip()
        if not s:
            return s
        if s.startswith("http://") or s.startswith("https://") or s.startswith("//"):
            return _to_https_url(s)
        s = s.lstrip("/")
        if s.startswith("image/"):
            return "https://image1.coupangcdn.com/" + s
        return "https://image1.coupangcdn.com/image/" + s

    vendor_path = image_obj.get("vendorPath")
    if isinstance(vendor_path, str) and vendor_path.strip():
        vp = vendor_path.strip()
        if vp.startswith("http://") or vp.startswith("https://") or vp.startswith("//"):
            return _to_https_url(vp)
        if "/" in vp:
            return _build_coupang_cdn_url(vp)

    cdn_path = image_obj.get("cdnPath")
    if isinstance(cdn_path, str) and cdn_path.strip():
        return _build_coupang_cdn_url(cdn_path.strip())

    return None


def _build_detail_html_from_urls(urls: list[str]) -> str:
    safe_urls: list[str] = []
    seen: set[str] = set()
    for u in urls:
        su = _to_https_url(u)
        if not su or su in seen:
            continue
        seen.add(su)
        safe_urls.append(su)
        if len(safe_urls) >= 20:
            break

    parts: list[str] = ["<center>"]
    for u in safe_urls:
        parts.append(f'<img src="{u}"> <br>')

    parts.append("</center> <br>")
    parts.append(
        '<p style="font-size: 12px; color: #777777; display: block; margin: 20px 0;">'
        '본 제품을 구매하시면 원활한 배송을 위해 꼭 필요한 고객님의 개인정보를 (성함, 주소, 전화번호 등)  '
        '택배사 및 제 3업체에서 이용하는 것에 동의하시는 것으로 간주됩니다.<br>'
        '개인정보는 배송 외의 용도로는 절대 사용되지 않으니 안심하시기 바랍니다. 안전하게 배송해 드리겠습니다.'
        '</p>'
    )

    html = " ".join(parts).strip()
    return html[:200000]


def _build_contents_image_blocks(urls: list[str]) -> list[dict]:
    safe_urls: list[str] = []
    seen: set[str] = set()
    for u in urls:
        su = _to_https_url(u)
        if not su or su in seen:
            continue
        seen.add(su)
        safe_urls.append(su)
        if len(safe_urls) >= 20:
            break

    if not safe_urls:
        return []

    return [
        {
            "contentsType": "IMAGE_NO_SPACE",
            "contentDetails": [{"content": u, "detailType": "IMAGE"} for u in safe_urls],
        },
        {
            "contentsType": "TEXT",
            "contentDetails": [
                {
                    "content": "본 제품을 구매하시면 원활한 배송을 위해 꼭 필요한 고객님의 개인정보를 (성함, 주소, 전화번호 등) 택배사 및 제 3업체에서 이용하는 것에 동의하시는 것으로 간주됩니다. 개인정보는 배송 외의 용도로는 절대 사용되지 않으니 안심하시기 바랍니다. 안전하게 배송해 드리겠습니다.",
                    "detailType": "TEXT",
                }
            ],
        },
    ]


class FixCoupangContentsIn(BaseModel):
    productId: uuid.UUID | None = None
    useCoupangImagesOnly: bool = Field(default=True)
    requestApproval: bool = Field(default=True)
    useImageBlocks: bool = Field(default=True)


class OwnerClanInvoiceSyncIn(BaseModel):
    limit: int = Field(default=0, ge=0, le=500)
    dryRun: bool = Field(default=False)
    retryCount: int = Field(default=0, ge=0, le=3)


class OrderSyncFailureOut(BaseModel):
    id: uuid.UUID
    endpoint: str
    httpStatus: int | None = None
    errorMessage: str | None = None
    fetchedAt: datetime | None = None
    requestPayload: dict | None = None
    responsePayload: dict | None = None


class OrderSyncRetryIn(BaseModel):
    ids: list[uuid.UUID]
    retryCount: int = Field(default=0, ge=0, le=3)


class OrderSyncReportOut(BaseModel):
    total: int
    succeeded: int
    failed: int
    byEndpoint: dict[str, dict[str, int]]
    topErrors: list[dict[str, object]]


class OrderMappingIssueOut(BaseModel):
    orderId: str
    reason: str
    sellerProductId: str | None = None


class OrderMappingIssueReportOut(BaseModel):
    total: int
    counts: dict[str, int]
    samples: list[OrderMappingIssueOut]


class SchedulerStateOut(BaseModel):
    name: str
    status: str
    updatedAt: str
    meta: dict | None = None


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


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_seller_product_id(raw: dict) -> str | None:
    if not isinstance(raw, dict):
        return None
    seller_product_id = raw.get("sellerProductId") or raw.get("seller_product_id")
    if seller_product_id:
        return str(seller_product_id)
    order_items = raw.get("orderItems") if isinstance(raw.get("orderItems"), list) else []
    if order_items and isinstance(order_items[0], dict):
        seller_product_id = order_items[0].get("sellerProductId") or order_items[0].get("seller_product_id")
        if seller_product_id:
            return str(seller_product_id)
    return None


def _read_scheduler_state() -> dict:
    try:
        from app.services.sync_scheduler_state import read_scheduler_state
        return read_scheduler_state()
    except Exception:
        return {}


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
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    Triggers bulk registration of products to Coupang.
    If productIds provided, only registers those.
    Otherwise, registers all ready products (DRAFT + COMPLETED processing).
    """
    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        ).all()
    
    if not accounts:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    if payload.productIds and not auto_fix and not wait:
        products = session.scalars(select(Product).where(Product.id.in_(payload.productIds))).all()
        missing: list[dict] = []
        for p in products:
            if _get_images_count(p) < 1:
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
                detail={"message": "쿠팡 등록을 위해서는 가공 완료 및 이미지 1장이 필요합니다", "items": missing[:50]},
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
        registered_skip = 0
        blocked = 0

        registered_ok_ids: list[str] = []
        registered_fail_ids: list[str] = []
        registered_fail_items: list[dict] = []
        blocked_ids: list[str] = []
        skipped_reasons: list[dict] = []

        for account in accounts:
            for p in products:
                total += 1

                if not p.supplier_item_id:
                    blocked += 1
                    blocked_ids.append(str(p.id))
                    continue

                if auto_fix:
                    ready = await ensure_product_ready_for_coupang(
                        session,
                        str(p.id),
                        min_images_required=1,
                        force_fetch_ownerclan=bool(force_fetch_ownerclan),
                        augment_images=bool(augment_images),
                    )
                    if not ready.get("ok"):
                        registered_fail += 1
                        registered_fail_ids.append(str(p.id))
                        raw_reason = f"[{account.name}] 자동 보정 실패"
                        registered_fail_items.append(
                            {
                                "productId": str(p.id),
                                "accountId": str(account.id),
                                "accountName": account.name,
                                "reason": _tag_reason(raw_reason),
                                "reasonRaw": raw_reason,
                                "ready": ready,
                            }
                        )
                        continue

                if _get_images_count(p) < 1:
                    registered_fail += 1
                    registered_fail_ids.append(str(p.id))
                    raw_reason = f"[{account.name}] 가공/이미지 조건 미달(processingStatus={p.processing_status}, images={_get_images_count(p)})"
                    registered_fail_items.append(
                        {
                            "productId": str(p.id),
                            "accountId": str(account.id),
                            "accountName": account.name,
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
                    if _is_skipped_reason(reason):
                        blocked += 1
                        blocked_ids.append(str(p.id))
                        raw_reason = f"[{account.name}] " + str(reason)
                        skipped_item = {
                            "productId": str(p.id),
                            "accountId": str(account.id),
                            "accountName": account.name,
                            "reason": _tag_reason(raw_reason),
                            "reasonRaw": raw_reason,
                        }
                        registered_fail_items.append(
                            {
                                "productId": str(p.id),
                                "accountId": str(account.id),
                                "accountName": account.name,
                                "reason": _tag_reason(raw_reason),
                                "reasonRaw": raw_reason,
                            }
                        )
                        skipped_reasons.append(skipped_item)
                    else:
                        registered_fail += 1
                        registered_fail_ids.append(str(p.id))
                        raw_reason = f"[{account.name}] " + (reason or "쿠팡 등록 실패")
                        registered_fail_items.append(
                            {
                                "productId": str(p.id),
                                "accountId": str(account.id),
                                "accountName": account.name,
                                "reason": _tag_reason(raw_reason),
                                "reasonRaw": raw_reason,
                            }
                        )

        return {
            "status": "completed",
            "autoFix": bool(auto_fix),
            "limit": int(limit),
            "accounts": [account.name for account in accounts],
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
                "skippedReasons": skipped_reasons[:200],
            },
        }

    for account in accounts:
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
        "message": f"Bulk registration started for {len(accounts)} accounts.",
        "autoFix": bool(auto_fix),
        "accountIds": [str(a.id) for a in accounts],
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

        if p.processing_status == "COMPLETED" and images_count >= 1:
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
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    쿠팡 상품 등록을 트리거합니다.
    작업은 백그라운드에서 비동기로 수행됩니다.
    """
    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        ).all()
    
    if not accounts:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    if auto_fix:
        from app.services.coupang_ready_service import ensure_product_ready_for_coupang

        ready = await ensure_product_ready_for_coupang(
            session,
            str(product.id),
            min_images_required=1,
            force_fetch_ownerclan=bool(force_fetch_ownerclan),
            augment_images=bool(augment_images),
        )

        if not ready.get("ok"):
            raise HTTPException(
                status_code=409,
                detail={"message": "쿠팡 등록을 위한 자동 보정에 실패했습니다", "ready": ready},
            )

        if wait:
            results = []
            for account in accounts:
                success, reason = register_product(session, account.id, product.id)
                skipped = _is_skipped_reason(reason)
                if success:
                    product.status = "ACTIVE"
                    session.commit()
                results.append({
                    "accountId": str(account.id),
                    "accountName": account.name,
                    "success": bool(success),
                    "skipped": bool(skipped),
                    "reason": _tag_reason(reason),
                    "reasonRaw": (str(reason) if reason is not None else None),
                })
            return {
                "status": "completed",
                "results": results,
                "ready": ready,
            }

        for account in accounts:
            background_tasks.add_task(
                execute_coupang_registration,
                account.id,
                product.id,
                True,
                bool(force_fetch_ownerclan),
                bool(augment_images),
            )
        return {"status": "accepted", "message": f"쿠팡 상품 등록 작업이 {len(accounts)}개 계정에 대해 시작되었습니다.", "autoFix": True}

    processed_images = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    if product.processing_status != "COMPLETED" or len(processed_images) < 1:
        raise HTTPException(
            status_code=409,
            detail=f"쿠팡 등록을 위해서는 가공 완료 및 이미지 1장이 필요합니다(processingStatus={product.processing_status}, images={len(processed_images)})",
        )

    for account in accounts:
        background_tasks.add_task(execute_coupang_registration, account.id, product.id, False, False, False)
    return {"status": "accepted", "message": f"쿠팡 상품 등록 작업이 {len(accounts)}개 계정에 대해 시작되었습니다."}


@router.post("/sync-status/{product_id}", status_code=200)
async def sync_coupang_status_endpoint(
    product_id: uuid.UUID,
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    특정 상품의 쿠팡 마켓 상태를 명시적으로 동기화합니다.
    """
    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        ).all()
    
    if not accounts:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    acc_ids = [a.id for a in accounts]

    stmt = (
        select(MarketListing)
        .where(MarketListing.product_id == product_id)
        .where(MarketListing.market_account_id.in_(acc_ids))
        .order_by(MarketListing.linked_at.desc())
    )
    listings = session.scalars(stmt).all()
    if not listings:
        raise HTTPException(status_code=404, detail="마켓 등록 정보를 찾을 수 없습니다.")

    sync_results = []
    for listing in listings:
        previous_rejection_reason = listing.rejection_reason
        success, result = sync_market_listing_status(session, listing.id)
        
        try:
            session.refresh(listing)
        except Exception:
            pass

        sync_results.append({
            "accountId": str(listing.market_account_id),
            "coupangStatus": result if success else f"Error: {result}",
            "sellerProductId": str(listing.market_item_id),
            "previousRejectionReason": previous_rejection_reason,
            "rejectionReason": listing.rejection_reason,
        })

    return {
        "status": "success",
        "results": sync_results
    }


@router.put("/products/{product_id}", status_code=200)
def update_coupang_product_endpoint(
    product_id: uuid.UUID,
    session: Session = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    내부 Product 정보를 기반으로 쿠팡에 이미 등록된 상품을 업데이트합니다.
    """
    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        # 해당 상품이 등록된 모든 활성 계정을 찾음
        stmt_accounts = (
            select(MarketAccount)
            .join(MarketListing, MarketListing.market_account_id == MarketAccount.id)
            .where(MarketListing.product_id == product_id)
            .where(MarketAccount.is_active == True)
        )
        accounts = session.scalars(stmt_accounts).all()

    if not accounts:
        raise HTTPException(status_code=400, detail="해당 상품이 등록된 활성 쿠팡 계정을 찾을 수 없습니다.")

    from app.coupang_sync import update_product_on_coupang
    
    results = []
    for account in accounts:
        success, reason = update_product_on_coupang(session, account.id, product_id)
        results.append({
            "accountId": str(account.id),
            "accountName": account.name,
            "success": success,
            "reason": reason
        })
    
    return {"status": "success", "results": results}


@router.delete("/products/{seller_product_id}", status_code=200)
def delete_coupang_product_endpoint(
    seller_product_id: str,
    session: Session = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    쿠팡에서 상품을 삭제합니다. (모든 아이템 판매중지 후 삭제)
    """
    if account_id:
        target_account_id = account_id
    else:
        # seller_product_id로 해당 계정을 찾음
        listing = session.scalars(select(MarketListing).where(MarketListing.market_item_id == seller_product_id)).first()
        if listing:
            target_account_id = listing.market_account_id
        else:
            # 리스팅 정보가 없으면 모든 활성 계정에서 시도 (첫 번째 계정 우선)
            stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
            account = session.scalars(stmt).first()
            if not account:
                raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")
            target_account_id = account.id

    from app.coupang_sync import delete_product_from_coupang
    success, reason = delete_product_from_coupang(session, target_account_id, seller_product_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=f"삭제 실패: {reason}")
    
    return {"status": "success", "message": "상품이 쿠팡에서 삭제되었습니다.", "accountId": str(target_account_id)}


@router.post("/products/{seller_product_id}/stop-sales", status_code=200)
def stop_coupang_product_sales_endpoint(
    seller_product_id: str,
    session: Session = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    쿠팡 상품 판매를 중지합니다.
    """
    if account_id:
        target_account_id = account_id
    else:
        listing = session.scalars(select(MarketListing).where(MarketListing.market_item_id == seller_product_id)).first()
        if listing:
            target_account_id = listing.market_account_id
        else:
            stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
            account = session.scalars(stmt).first()
            if not account:
                raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")
            target_account_id = account.id

    from app.coupang_sync import stop_product_sales
    success, payload = stop_product_sales(session, target_account_id, seller_product_id)
    if not success:
        raise HTTPException(status_code=400, detail=payload or {"message": "판매중지 실패"})
    return {"status": "success", "result": payload, "accountId": str(target_account_id)}


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
            ready = asyncio.run(
                ensure_product_ready_for_coupang(
                    session,
                    str(p.id),
                    min_images_required=1,
                    force_fetch_ownerclan=bool(force_fetch_ownerclan),
                    augment_images=bool(augment_images),
                )
            )
            if not ready.get("ok"):
                continue

            ready_ok += 1
            ok, reason = register_product(session, account_id, p.id)
            if ok:
                p.status = "ACTIVE"
                session.commit()
                registered_ok += 1
            else:
                if _is_skipped_reason(reason):
                    registered_skip += 1
                else:
                    registered_fail += 1

        import logging

        logging.getLogger(__name__).info(
            "쿠팡 벌크 자동등록 요약(total=%s, readyOk=%s, registeredOk=%s, registeredFail=%s, registeredSkip=%s)",
            total,
            ready_ok,
            registered_ok,
            registered_fail,
            registered_skip,
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
            ready = asyncio.run(
                ensure_product_ready_for_coupang(
                    session,
                    str(product_id),
                    min_images_required=1,
                    force_fetch_ownerclan=bool(force_fetch_ownerclan),
                    augment_images=bool(augment_images),
                )
            )
            if not ready.get("ok"):
                return

        success, reason = register_product(session, account_id, product_id)
        if success:
            p = session.get(Product, product_id)
            if p and p.status == "DRAFT":
                p.status = "ACTIVE"
                session.commit()
        elif _is_skipped_reason(reason):
            pass


@router.get("/orders/raw", status_code=200)
async def list_coupang_orders_raw(
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    """
    저장된 쿠팡 주문(ordersheets) raw 목록을 조회합니다(디버깅/점검용).
    """
    if account_id:
        account_ids = [account_id]
    else:
        stmt_acct = select(MarketAccount.id).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        account_ids = session.scalars(stmt_acct).all()
    
    if not account_ids:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    stmt = (
        select(MarketOrderRaw)
        .where(MarketOrderRaw.market_code == "COUPANG")
        .where(MarketOrderRaw.account_id.in_(account_ids))
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
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    listing = session.scalars(select(MarketListing).where(MarketListing.market_item_id == seller_product_id)).first()
    if account_id:
        account = session.get(MarketAccount, account_id)
    else:
        # seller_product_id로 해당 계정을 찾음
        if listing:
            account = session.get(MarketAccount, listing.market_account_id)
        else:
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
        "rejectionReason": listing.rejection_reason if listing else None,
        "raw": data,
    }


@router.post("/products/{seller_product_id}/fix-contents", status_code=200)
async def fix_coupang_product_contents(
    seller_product_id: str,
    payload: FixCoupangContentsIn,
    session: Session = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    if account_id:
        account = session.get(MarketAccount, account_id)
    else:
        # seller_product_id로 해당 계정을 찾음
        listing = session.scalars(select(MarketListing).where(MarketListing.market_item_id == seller_product_id)).first()
        if listing:
            account = session.get(MarketAccount, listing.market_account_id)
        else:
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
    if code != 200 or not isinstance(data, dict) or data.get("code") != "SUCCESS":
        raise HTTPException(status_code=400, detail={"message": "쿠팡 상품 조회 실패", "httpStatus": code, "raw": data})

    data_obj = data.get("data") if isinstance(data, dict) else None
    if not isinstance(data_obj, dict):
        raise HTTPException(status_code=400, detail="쿠팡 상품 조회 응답(data)이 비정상입니다")

    items = data_obj.get("items") if isinstance(data_obj.get("items"), list) else []
    if not items or not isinstance(items[0], dict):
        raise HTTPException(status_code=400, detail="쿠팡 상품 조회 응답(items)이 비정상입니다")

    urls: list[str] = []

    if bool(payload.useCoupangImagesOnly):
        for item in items:
            if not isinstance(item, dict):
                continue
            imgs = item.get("images") if isinstance(item.get("images"), list) else []
            for it in imgs:
                if not isinstance(it, dict):
                    continue
                u = _extract_coupang_image_url(it)
                if isinstance(u, str) and u.strip():
                    urls.append(u.strip())
                if len(urls) >= 20:
                    break
            if len(urls) >= 20:
                break

    if not urls:
        listing = session.scalars(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.market_item_id == str(seller_product_id).strip())
        ).first()

        product: Product | None = None
        if listing:
            product = session.get(Product, listing.product_id)
        elif payload.productId:
            product = session.get(Product, payload.productId)

        processed = product.processed_image_urls if product and isinstance(product.processed_image_urls, list) else []
        for u in processed[:20]:
            if isinstance(u, str) and u.strip():
                urls.append(u.strip())

    if not urls:
        text = ""

        for item in items:
            if not isinstance(item, dict):
                continue
            existing_contents = item.get("contents") if isinstance(item.get("contents"), list) else []
            if not existing_contents or not isinstance(existing_contents[0], dict):
                continue
            cds = (
                existing_contents[0].get("contentDetails")
                if isinstance(existing_contents[0].get("contentDetails"), list)
                else []
            )
            if cds and isinstance(cds[0], dict) and isinstance(cds[0].get("content"), str):
                text = cds[0]["content"]
                if text:
                    break

        if text:
            fixed = re.sub(r"http://", "https://", text)
            html = fixed[:200000]
        else:
            raise HTTPException(status_code=400, detail="수정할 상세 이미지/콘텐츠를 찾지 못했습니다")
    else:
        html = _build_detail_html_from_urls(urls)

    new_contents: list[dict]
    if bool(payload.useImageBlocks) and urls:
        new_contents = _build_contents_image_blocks(urls)
    else:
        new_contents = [
            {
                "contentsType": "TEXT",
                "contentDetails": [
                    {
                        "content": html,
                        "detailType": "TEXT",
                    }
                ],
            }
        ]

    for item in items:
        if isinstance(item, dict):
            item["contents"] = new_contents

    update_payload = data_obj
    update_payload["sellerProductId"] = data_obj.get("sellerProductId") or int(str(seller_product_id).strip())
    update_payload["requested"] = True

    update_code, update_data = client.update_product(update_payload)

    approval_code: int | None = None
    approval_data: dict | None = None
    if update_code == 200 and isinstance(update_data, dict) and update_data.get("code") == "SUCCESS" and bool(payload.requestApproval):
        final_status = str((data_obj.get("statusName") or data_obj.get("status") or "") ).strip()
        for _ in range(20):
            if final_status in {"SAVED", "임시저장"}:
                break
            try:
                _c2, d2 = client.get_product(str(seller_product_id).strip())
                dobj2 = d2.get("data") if isinstance(d2, dict) else None
                if isinstance(dobj2, dict):
                    final_status = str((dobj2.get("statusName") or dobj2.get("status") or "") ).strip()
            except Exception:
                pass
            await asyncio.sleep(1.0)

        if final_status in {"SAVED", "임시저장"}:
            for _ in range(5):
                try:
                    approval_code, approval_data = client.approve_product(str(seller_product_id).strip())
                except Exception as e:
                    approval_code, approval_data = 500, {"code": "INTERNAL_ERROR", "message": str(e)}

                msg = (approval_data.get("message") if isinstance(approval_data, dict) else None) or ""
                if approval_code == 200 and isinstance(approval_data, dict) and approval_data.get("code") == "SUCCESS":
                    break
                if "임시저장" in str(msg) and "만" in str(msg):
                    await asyncio.sleep(1.0)
                    continue
                break

    return {
        "sellerProductId": str(seller_product_id).strip(),
        "httpStatus": update_code,
        "raw": update_data,
        "approval": {
            "httpStatus": approval_code,
            "raw": approval_data,
        },
        "contentsLength": len(html),
        "imageCount": len(urls),
        "usedUrls": urls[:20],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/centers", status_code=200)
async def list_coupang_centers(
    session: Session = Depends(get_session),
    page_size: int = Query(default=10, ge=10, le=50, alias="pageSize"),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    if account_id:
        account = session.get(MarketAccount, account_id)
    else:
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
    account_id = getattr(payload, "accountId", None) # payload에 accountId가 있다면 사용 (스키마엔 없으나 유연성 위해)
    
    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        ).all()

    if not accounts:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    for account in accounts:
        background_tasks.add_task(
            execute_coupang_order_sync,
            account.id,
            payload.createdAtFrom,
            payload.createdAtTo,
            payload.status,
            payload.maxPerPage,
        )

    return {"status": "accepted", "message": f"쿠팡 주문 동기화 작업이 {len(accounts)}개 계정에 대해 시작되었습니다."}


@router.post("/account/credentials", status_code=200)
async def update_coupang_credentials(
    payload: CoupangCredentialsUpdateIn,
    session: Session = Depends(get_session),
    account_id: uuid.UUID | None = Query(default=None, alias="accountId"),
):
    if account_id:
        account = session.get(MarketAccount, account_id)
    else:
        stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        account = session.scalars(stmt).first()
    
    if not account:
        raise HTTPException(status_code=400, detail="대상 쿠팡 계정을 찾을 수 없습니다.")

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
    account_id = getattr(payload, "accountId", None)

    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        ).all()

    if not accounts:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    for account in accounts:
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

    return {"status": "accepted", "message": f"쿠팡→오너클랜 주문 연동 작업이 {len(accounts)}개 계정에 대해 시작되었습니다."}


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
        account_id = getattr(payload, "accountId", None)
        if account_id:
            account = preview_session.get(MarketAccount, account_id)
        else:
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


def execute_ownerclan_invoice_sync(
    account_id: uuid.UUID,
    limit: int,
    dry_run: bool,
    retry_count: int,
):
    from app.session_factory import session_factory

    with session_factory() as session:
        sync_ownerclan_orders_to_coupang_invoices(
            session,
            coupang_account_id=account_id,
            limit=limit,
            dry_run=dry_run,
            retry_count=retry_count,
        )


@router.post("/orders/sync-ownerclan-invoices", status_code=202)
async def sync_ownerclan_invoices_endpoint(
    payload: OwnerClanInvoiceSyncIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    오너클랜 주문 송장/취소 정보를 쿠팡에 반영합니다.
    """
    account_id = getattr(payload, "accountId", None)

    if account_id:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.id == account_id, MarketAccount.is_active == True)
        ).all()
    else:
        accounts = session.scalars(
            select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        ).all()

    if not accounts:
        raise HTTPException(status_code=400, detail="활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

    for account in accounts:
        background_tasks.add_task(
            execute_ownerclan_invoice_sync,
            account.id,
            payload.limit,
            payload.dryRun,
            payload.retryCount,
        )

    return {"status": "accepted", "message": f"오너클랜 송장/취소 → 쿠팡 반영 작업이 {len(accounts)}개 계정에 대해 시작되었습니다."}


@router.get("/orders/sync-failures", status_code=200, response_model=list[OrderSyncFailureOut])
def list_order_sync_failures(
    session: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    endpoints = ["coupang/upload_invoices", "coupang/cancel_order"]
    stmt = (
        select(SupplierRawFetchLog)
        .where(SupplierRawFetchLog.supplier_code == "coupang")
        .where(SupplierRawFetchLog.endpoint.in_(endpoints))
        .where(or_(SupplierRawFetchLog.error_message.is_not(None), SupplierRawFetchLog.http_status >= 300))
        .order_by(SupplierRawFetchLog.fetched_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.scalars(stmt).all()
    return [
        OrderSyncFailureOut(
            id=r.id,
            endpoint=r.endpoint,
            httpStatus=r.http_status,
            errorMessage=r.error_message,
            fetchedAt=r.fetched_at,
            requestPayload=r.request_payload if isinstance(r.request_payload, dict) else None,
            responsePayload=r.response_payload if isinstance(r.response_payload, dict) else None,
        )
        for r in rows
    ]


@router.post("/orders/sync-failures/retry", status_code=200)
def retry_order_sync_failures(
    payload: OrderSyncRetryIn,
    session: Session = Depends(get_session),
):
    return retry_coupang_failures(session, payload.ids, payload.retryCount)


@router.get("/orders/sync-report", status_code=200, response_model=OrderSyncReportOut)
def get_order_sync_report(
    session: Session = Depends(get_session),
    fromTs: str | None = Query(default=None),
    toTs: str | None = Query(default=None),
):
    endpoints = ["coupang/upload_invoices", "coupang/cancel_order"]
    stmt = (
        select(SupplierRawFetchLog)
        .where(SupplierRawFetchLog.supplier_code == "coupang")
        .where(SupplierRawFetchLog.endpoint.in_(endpoints))
        .order_by(SupplierRawFetchLog.fetched_at.desc())
    )

    start_dt = _parse_iso_dt(fromTs)
    end_dt = _parse_iso_dt(toTs)
    if start_dt:
        stmt = stmt.where(SupplierRawFetchLog.fetched_at >= start_dt)
    if end_dt:
        stmt = stmt.where(SupplierRawFetchLog.fetched_at <= end_dt)

    rows = session.scalars(stmt).all()

    total = len(rows)
    succeeded = 0
    failed = 0
    by_endpoint: dict[str, dict[str, int]] = {}
    error_counts: dict[str, int] = {}

    for row in rows:
        endpoint = row.endpoint or "unknown"
        entry = by_endpoint.setdefault(endpoint, {"succeeded": 0, "failed": 0})
        ok = (row.http_status or 0) < 300 and row.error_message is None
        if ok:
            succeeded += 1
            entry["succeeded"] += 1
        else:
            failed += 1
            entry["failed"] += 1
            key = row.error_message or "unknown_error"
            error_counts[key] = error_counts.get(key, 0) + 1

    top_errors = [
        {"error": k, "count": v}
        for k, v in sorted(error_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "byEndpoint": by_endpoint,
        "topErrors": top_errors,
    }


@router.get("/orders/mapping-issues", status_code=200, response_model=OrderMappingIssueReportOut)
def get_order_mapping_issues(
    session: Session = Depends(get_session),
    limit: int = Query(default=200, ge=1, le=1000),
):
    stmt = (
        select(MarketOrderRaw)
        .where(MarketOrderRaw.market_code == "COUPANG")
        .order_by(MarketOrderRaw.fetched_at.desc())
        .limit(limit)
    )
    rows = session.scalars(stmt).all()

    counts: dict[str, int] = {}
    samples: list[OrderMappingIssueOut] = []

    for row in rows:
        raw = row.raw if isinstance(row.raw, dict) else {}
        order_id = str(row.order_id)
        seller_product_id = _extract_seller_product_id(raw)

        def _add_issue(reason: str):
            counts[reason] = counts.get(reason, 0) + 1
            if len(samples) < 50:
                samples.append(
                    OrderMappingIssueOut(
                        orderId=order_id,
                        reason=reason,
                        sellerProductId=seller_product_id,
                    )
                )

        if not seller_product_id:
            _add_issue("missing_seller_product_id")
            continue

        listing = (
            session.query(MarketListing)
            .filter(MarketListing.market_item_id == str(seller_product_id))
            .first()
        )
        if not listing:
            _add_issue("missing_market_listing")
            continue

        product = session.get(Product, listing.product_id)
        if not product:
            _add_issue("missing_product")
            continue

        if not product.supplier_item_id:
            _add_issue("missing_supplier_item_id")

        order = session.query(Order).filter(Order.market_order_id == row.id).one_or_none()
        if not order:
            _add_issue("missing_order_link")
            continue

        if order.supplier_order_id is None:
            _add_issue("missing_supplier_order_link")

    return {"total": len(rows), "counts": counts, "samples": samples}


@router.get("/orders/scheduler-state", status_code=200, response_model=list[SchedulerStateOut])
def get_scheduler_state():
    state = _read_scheduler_state()
    results: list[SchedulerStateOut] = []
    for name, payload in state.items():
        if not isinstance(payload, dict):
            continue
        results.append(
            SchedulerStateOut(
                name=str(name),
                status=str(payload.get("status") or "unknown"),
                updatedAt=str(payload.get("updated_at") or ""),
                meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else None,
            )
        )
    return results


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
