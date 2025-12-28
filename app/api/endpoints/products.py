from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, delete
from typing import List
import uuid
from urllib.parse import urlparse
import ipaddress
import socket
import logging
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone

from app.db import get_session
from app.models import MarketListing, Product, SupplierAccount, SupplierItemRaw, SourcingCandidate
from app.schemas.product import MarketListingResponse, ProductResponse
from app.settings import settings
from app.services.detail_html_checks import find_forbidden_tags
from app.services.image_validation_report import parse_validation_failures_from_logs
from app.services.image_validation_log import parse_validation_failures
from pathlib import Path
from app.services.pricing import calculate_selling_price, parse_int_price, parse_shipping_fee

router = APIRouter()

logger = logging.getLogger(__name__)


class ProductFromOwnerClanRawIn(BaseModel):
    supplierItemRawId: uuid.UUID


class ProductProcessIn(BaseModel):
    minImagesRequired: int = Field(default=1, ge=1, le=20)
    forceFetchOwnerClan: bool = False


class ProductAugmentImagesFromDetailUrlIn(BaseModel):
    detailUrl: str | None = None
    targetCount: int = Field(default=5, ge=1, le=20)


class ProductProcessFailedIn(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    minImagesRequired: int = Field(default=1, ge=1, le=20)
    forceFetchOwnerClan: bool = True
    augmentImages: bool = True


class ProductHtmlWarningsIn(BaseModel):
    productIds: list[uuid.UUID]


class ProductHtmlWarningOut(BaseModel):
    productId: uuid.UUID
    tags: list[str]


class ImageValidationReportOut(BaseModel):
    counts: dict[str, int]


class ImageValidationFailureOut(BaseModel):
    url: str
    reason: str
    size: str
    width: str
    height: str


def _build_product_responses(session: Session, products: list[Product]) -> list[ProductResponse]:
    if not products:
        return []

    product_ids = [p.id for p in products]
    listings = session.scalars(
        select(MarketListing).where(MarketListing.product_id.in_(product_ids))
    ).all()

    listings_by_product: dict[uuid.UUID, list[MarketListingResponse]] = {}
    for row in listings:
        listings_by_product.setdefault(row.product_id, []).append(
            MarketListingResponse.model_validate(row, from_attributes=True)
        )

    out: list[ProductResponse] = []
    for p in products:
        out.append(
            ProductResponse(
                id=p.id,
                name=p.name,
                processed_name=p.processed_name,
                brand=p.brand,
                selling_price=p.selling_price,
                processing_status=p.processing_status,
                processed_image_urls=p.processed_image_urls,
                processed_keywords=p.processed_keywords,
                status=p.status,
                created_at=p.created_at,
                market_listings=listings_by_product.get(p.id, []),
            )
        )

    return out

@router.get("/stats")
def get_product_stats(
    session: Session = Depends(get_session),
    supplier_code: str = Query(default="ownerclan", alias="supplierCode"),
):
    """상품 통계를 조회합니다."""
    # 대시보드 "전체"는 수집된 Raw 데이터 기준으로 집계합니다.
    total = (
        session.scalar(
            select(func.count(SupplierItemRaw.id)).where(SupplierItemRaw.supplier_code == supplier_code)
        )
        or 0
    )
    
    # "가공 대기"는 소싱 후보(PENDING) 기준으로 집계합니다.
    pending = (
        session.scalar(
            select(func.count(SourcingCandidate.id))
            .where(SourcingCandidate.supplier_code == supplier_code)
            .where(SourcingCandidate.status == "PENDING")
        )
        or 0
    )
    
    completed = session.scalar(select(func.count(Product.id)).where(Product.processing_status == "COMPLETED")) or 0
    
    return {
        "total": total,
        "pending": pending,
        "completed": completed
    }

@router.get("/", response_model=List[ProductResponse])
def list_products(
    session: Session = Depends(get_session),
    processing_status: str | None = Query(default=None, alias="processingStatus"),
    status: str | None = Query(default=None),
):
    """모든 상품 목록을 조회합니다."""
    stmt = select(Product)

    if processing_status:
        stmt = stmt.where(Product.processing_status == processing_status)

    if status:
        stmt = stmt.where(Product.status == status)

    stmt = stmt.order_by(Product.created_at.desc())
    products = session.scalars(stmt).all()
    return _build_product_responses(session, products)

@router.get("/image-validation-report", status_code=200, response_model=ImageValidationReportOut)
def get_image_validation_report():
    log_path = Path("api.log")
    if not log_path.exists():
        return ImageValidationReportOut(counts={})

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    counts = parse_validation_failures_from_logs(lines)
    return ImageValidationReportOut(counts=counts)


@router.get("/image-validation-failures", status_code=200, response_model=list[ImageValidationFailureOut])
def get_image_validation_failures(limit: int = Query(default=100, ge=1, le=500)):
    log_path = Path("api.log")
    if not log_path.exists():
        return []

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    failures = parse_validation_failures(lines)
    return failures[:limit]



@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: uuid.UUID, session: Session = Depends(get_session)):
    """단일 상품 정보를 조회합니다."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.") # 한국어 오류 메시지
    items = _build_product_responses(session, [product])
    return items[0]


@router.post("/from-ownerclan-raw", status_code=200)
def create_product_from_ownerclan_raw(payload: ProductFromOwnerClanRawIn, session: Session = Depends(get_session)):
    raw_item = session.get(SupplierItemRaw, payload.supplierItemRawId)
    if not raw_item or raw_item.supplier_code != "ownerclan":
        raise HTTPException(status_code=404, detail="오너클랜 raw item을 찾을 수 없습니다.")

    existing = session.scalars(select(Product).where(Product.supplier_item_id == raw_item.id)).first()
    if existing:
        data = raw_item.raw if isinstance(raw_item.raw, dict) else {}
        supply_price = (
            data.get("supply_price")
            or data.get("supplyPrice")
            or data.get("fixedPrice")
            or data.get("fixed_price")
            or data.get("price")
            or 0
        )
        cost = parse_int_price(supply_price)
        shipping_fee = parse_shipping_fee(data)
        try:
            margin_rate = float(settings.pricing_default_margin_rate or 0.0)
        except Exception:
            margin_rate = 0.0
        if margin_rate < 0:
            margin_rate = 0.0
        selling_price = calculate_selling_price(
            cost, 
            margin_rate, 
            shipping_fee, 
            market_fee_rate=float(settings.pricing_market_fee_rate or 0.13)
        )

        updated = False
        if (existing.selling_price or 0) <= 0 and selling_price > 0:
            existing.cost_price = cost
            existing.selling_price = selling_price
            updated = True
            session.flush()

        if updated:
            session.commit()

        return {"created": False, "updated": updated, "productId": str(existing.id)}

    data = raw_item.raw if isinstance(raw_item.raw, dict) else {}
    item_name = data.get("item_name") or data.get("name") or "Untitled"
    supply_price = (
        data.get("supply_price")
        or data.get("supplyPrice")
        or data.get("fixedPrice")
        or data.get("fixed_price")
        or data.get("price")
        or 0
    )
    brand_name = data.get("brand") or data.get("brand_name")
    description = data.get("description") or data.get("content")

    cost = parse_int_price(supply_price)
    shipping_fee = parse_shipping_fee(data)
    try:
        margin_rate = float(settings.pricing_default_margin_rate or 0.0)
    except Exception:
        margin_rate = 0.0
    if margin_rate < 0:
        margin_rate = 0.0
    selling_price = calculate_selling_price(
        cost, 
        margin_rate, 
        shipping_fee, 
        market_fee_rate=float(settings.pricing_market_fee_rate or 0.13)
    )

    product = Product(
        supplier_item_id=raw_item.id,
        name=str(item_name),
        brand=str(brand_name) if brand_name is not None else None,
        description=str(description) if description is not None else None,
        cost_price=cost,
        selling_price=selling_price,
        status="DRAFT",
    )
    session.add(product)
    session.flush()

    session.commit()

    return {"created": True, "productId": str(product.id)}


@router.post("/html-warnings", status_code=200, response_model=list[ProductHtmlWarningOut])
def get_product_html_warnings(
    payload: ProductHtmlWarningsIn,
    session: Session = Depends(get_session),
):
    if not payload.productIds:
        return []
    products = session.scalars(select(Product).where(Product.id.in_(payload.productIds))).all()
    results: list[ProductHtmlWarningOut] = []
    for product in products:
        tags = find_forbidden_tags(product.description)
        results.append(ProductHtmlWarningOut(productId=product.id, tags=tags))
    return results


def _refresh_ownerclan_raw_if_needed(session: Session, product: Product) -> bool:
    if not product or not product.supplier_item_id:
        return False

    raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
    if not raw_item or raw_item.supplier_code != "ownerclan":
        return False

    item_code = str(raw_item.item_code or "").strip()
    if not item_code:
        return False

    owner = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )
    if not owner or not owner.access_token:
        return False

    from app.ownerclan_client import OwnerClanClient

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=owner.access_token,
    )

    status_code, data = client.get_product(item_code)
    if status_code >= 400:
        return False

    now = datetime.now(timezone.utc)
    raw_payload = (data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data) or {}
    if not isinstance(raw_payload, dict):
        return False

    stmt = insert(SupplierItemRaw).values(
        supplier_code="ownerclan",
        item_code=item_code,
        item_key=str(raw_payload.get("key")) if raw_payload.get("key") is not None else None,
        item_id=str(raw_payload.get("id")) if raw_payload.get("id") is not None else None,
        fetched_at=now,
        raw=raw_payload,
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
    session.flush()
    return True


async def _execute_product_processing(product_id: uuid.UUID, min_images_required: int, force_fetch_ownerclan: bool) -> None:
    import traceback
    from app.session_factory import session_factory
    from app.services.processing_service import ProcessingService

    try:
        with session_factory() as processing_session:
            product = processing_session.get(Product, product_id)
            if not product:
                return

            if force_fetch_ownerclan:
                _refresh_ownerclan_raw_if_needed(processing_session, product)

            service = ProcessingService(processing_session)
            await service.process_product(product_id, min_images_required=min_images_required)
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in executing product processing for {product_id}:\n{error_trace}")
        # Product.processing_status = "FAILED"는 ProcessingService.process_product 내부에서 처리됨


def _execute_product_processing_bg(product_id: uuid.UUID, min_images_required: int, force_fetch_ownerclan: bool) -> None:
    import asyncio

    asyncio.run(
        _execute_product_processing(
            product_id,
            int(min_images_required),
            bool(force_fetch_ownerclan),
        )
    )


async def _execute_pending_product_processing(limit: int, min_images_required: int) -> None:
    import traceback
    from app.session_factory import session_factory
    from app.services.processing_service import ProcessingService

    try:
        with session_factory() as processing_session:
            service = ProcessingService(processing_session)
            await service.process_pending_products(limit=limit, min_images_required=min_images_required)
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in executing pending product processing (limit={limit}):\n{error_trace}")


def _execute_pending_product_processing_bg(limit: int, min_images_required: int) -> None:
    import asyncio

    asyncio.run(_execute_pending_product_processing(int(limit), int(min_images_required)))


def _augment_product_images_best_effort(session: Session, product: Product, raw: dict, target_count: int) -> bool:
    existing = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    before_count = len(existing)
    if before_count >= int(target_count):
        return False

    html_url = _find_best_detail_url_from_raw(raw) or _extract_detail_url_from_raw(raw)
    if html_url and _is_safe_public_http_url(html_url) and not _is_image_url(html_url):
        import httpx
        from app.services.image_processing import image_processing_service

        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(str(html_url), headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code < 400:
                html = resp.text or ""
            else:
                html = ""
        except Exception:
            html = ""

        if html:
            extracted = image_processing_service.extract_images_from_html(html, limit=50)
            new_urls = image_processing_service.process_and_upload_images(
                image_urls=extracted,
                detail_html="",
                product_id=str(product.id),
            )
            merged: list[str] = []
            seen: set[str] = set()
            for u in (existing + (new_urls or [])):
                if not u:
                    continue
                su = str(u)
                if su in seen:
                    continue
                seen.add(su)
                merged.append(su)
                if len(merged) >= 20:
                    break
            product.processed_image_urls = merged
            if product.processed_name and len(merged) >= int(target_count):
                product.processing_status = "COMPLETED"
            session.commit()
            existing = merged

    if len(existing) >= int(target_count):
        return True

    from app.services.image_processing import image_processing_service

    image_urls = _collect_image_urls_from_raw(raw)
    if not image_urls:
        if html_url and _is_safe_public_http_url(html_url) and _is_image_url(html_url):
            image_urls = [html_url]
        else:
            return False

    new_urls = image_processing_service.process_and_upload_images(
        image_urls=image_urls,
        detail_html="",
        product_id=str(product.id),
    )

    merged: list[str] = []
    seen: set[str] = set()
    for u in (existing + (new_urls or [])):
        if not u:
            continue
        su = str(u)
        if su in seen:
            continue
        seen.add(su)
        merged.append(su)
        if len(merged) >= 20:
            break

    product.processed_image_urls = merged
    if len(merged) >= int(target_count):
        if not product.processed_name:
            product.processed_name = product.name
        product.processing_status = "COMPLETED"
    session.commit()
    return len(merged) > before_count


async def _run_failed_product_processing(
    session: Session,
    limit: int,
    min_images_required: int,
    force_fetch_ownerclan: bool,
    augment_images: bool,
) -> dict:
    from app.services.processing_service import ProcessingService

    processed = 0
    refreshed = 0
    augmented = 0
    completed = 0
    failed = 0

    processed_ids: list[str] = []
    completed_ids: list[str] = []
    failed_ids: list[str] = []
    refreshed_ids: list[str] = []
    augmented_ids: list[str] = []

    stmt = select(Product).order_by(Product.updated_at.desc()).limit(int(limit))
    products = session.scalars(stmt).all()

    for p in products:
        imgs0 = p.processed_image_urls if isinstance(p.processed_image_urls, list) else []
        needs_fix = (
            p.processing_status == "FAILED"
            or len(imgs0) < int(min_images_required)
        )
        if not needs_fix:
            continue

        processed += 1
        processed_ids.append(str(p.id))

        if force_fetch_ownerclan:
            if _refresh_ownerclan_raw_if_needed(session, p):
                refreshed += 1
                refreshed_ids.append(str(p.id))

        service = ProcessingService(session)
        await service.process_product(p.id, min_images_required=int(min_images_required))

        session.refresh(p)
        imgs = p.processed_image_urls if isinstance(p.processed_image_urls, list) else []

        if augment_images and (p.processing_status != "COMPLETED" or len(imgs) < int(min_images_required)):
            raw_item = session.get(SupplierItemRaw, p.supplier_item_id) if p.supplier_item_id else None
            raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
            if _augment_product_images_best_effort(session, p, raw, target_count=int(min_images_required)):
                augmented += 1
                augmented_ids.append(str(p.id))

        session.refresh(p)
        imgs = p.processed_image_urls if isinstance(p.processed_image_urls, list) else []
        if p.processing_status == "COMPLETED" and len(imgs) >= int(min_images_required):
            completed += 1
            completed_ids.append(str(p.id))
        else:
            failed += 1
            failed_ids.append(str(p.id))

    return {
        "processed": processed,
        "refreshedRaw": refreshed,
        "augmentedImages": augmented,
        "completed": completed,
        "failed": failed,
        "minImagesRequired": int(min_images_required),
        "processedIds": processed_ids[:200],
        "completedIds": completed_ids[:200],
        "failedIds": failed_ids[:200],
        "refreshedIds": refreshed_ids[:200],
        "augmentedIds": augmented_ids[:200],
    }


async def _execute_failed_product_processing(limit: int, min_images_required: int, force_fetch_ownerclan: bool, augment_images: bool) -> None:
    import traceback
    from app.session_factory import session_factory

    try:
        with session_factory() as session:
            summary = await _run_failed_product_processing(
                session,
                limit=limit,
                min_images_required=min_images_required,
                force_fetch_ownerclan=force_fetch_ownerclan,
                augment_images=augment_images,
            )
            logger.info(
                "failed 제품 재가공 요약(processed=%s, refreshedRaw=%s, augmentedImages=%s, completed=%s, failed=%s, minImagesRequired=%s)",
                summary.get("processed"),
                summary.get("refreshedRaw"),
                summary.get("augmentedImages"),
                summary.get("completed"),
                summary.get("failed"),
                summary.get("minImagesRequired"),
            )
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in executing failed product processing (limit={limit}):\n{error_trace}")


def _is_safe_public_http_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    host_lower = host.lower()
    if host_lower in ("localhost",) or host_lower.endswith(".local"):
        return False

    try:
        ip = ipaddress.ip_address(host_lower)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        try:
            infos = socket.getaddrinfo(host_lower, None)
            for info in infos:
                ip_str = info[4][0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
        except Exception:
            return False

    return True


def _extract_detail_url_from_raw(raw: dict) -> str | None:
    if not isinstance(raw, dict):
        return None

    candidates: list[str | None] = [
        raw.get("detailUrl"),
        raw.get("detail_url"),
        raw.get("productUrl"),
        raw.get("product_url"),
        raw.get("itemUrl"),
        raw.get("item_url"),
        raw.get("url"),
        raw.get("link"),
        raw.get("linkUrl"),
    ]

    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else None
    if isinstance(metadata, dict):
        candidates.extend(
            [
                metadata.get("detailUrl"),
                metadata.get("detail_url"),
                metadata.get("url"),
                metadata.get("productUrl"),
                metadata.get("product_url"),
            ]
        )

    for c in candidates:
        if not c:
            continue
        s = str(c).strip()
        if s:
            return s
    return None


def _collect_image_urls_from_raw(raw: dict) -> list[str]:
    urls: list[tuple[str, str]] = []
    _collect_string_urls(raw, "", urls)

    image_urls: list[str] = []
    seen: set[str] = set()
    for path, url in urls:
        if not _is_image_url(url):
            continue
        if not _is_safe_public_http_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        image_urls.append(url)
        if len(image_urls) >= 50:
            break
    return image_urls


def _execute_augment_images_from_image_urls(product_id: uuid.UUID, image_urls: list[str], target_count: int) -> None:
    import traceback
    from app.session_factory import session_factory
    from app.services.image_processing import image_processing_service

    try:
        with session_factory() as session:
            product = session.get(Product, product_id)
            if not product:
                return

            existing = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
            if len(existing) >= int(target_count):
                return

            new_urls = image_processing_service.process_and_upload_images(
                image_urls=image_urls,
                detail_html="",
                product_id=str(product.id),
            )

            merged: list[str] = []
            seen: set[str] = set()
            for u in (existing + (new_urls or [])):
                if not u:
                    continue
                su = str(u)
                if su in seen:
                    continue
                seen.add(su)
                merged.append(su)
                if len(merged) >= 20:
                    break

            product.processed_image_urls = merged
            if product.processed_name and len(merged) >= int(target_count):
                product.processing_status = "COMPLETED"
            session.commit()
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in augment_images_from_image_urls for {product_id}:\n{error_trace}")


def _collect_string_urls(value: object, path: str, out: list[tuple[str, str]], depth: int = 0, max_depth: int = 6) -> None:
    if depth > max_depth:
        return

    if isinstance(value, dict):
        for k, v in value.items():
            k_str = str(k)
            _collect_string_urls(v, f"{path}.{k_str}" if path else k_str, out, depth + 1, max_depth)
        return

    if isinstance(value, list):
        for i, v in enumerate(value[:50]):
            _collect_string_urls(v, f"{path}[{i}]", out, depth + 1, max_depth)
        return

    if isinstance(value, str):
        s = value.strip()
        if s.startswith("http://") or s.startswith("https://"):
            out.append((path, s))


def _is_image_url(url: str) -> bool:
    u = (url or "").lower()
    return any(ext in u for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"]) 


def _score_detail_url(path: str, url: str) -> int:
    p = (path or "").lower()
    u = (url or "").lower()

    score = 0
    if any(tok in p for tok in ["detail", "product", "item", "link", "url", "href", "page"]):
        score += 30
    if any(tok in u for tok in ["detail", "product", "item", "goods", "view", "page"]):
        score += 20

    if _is_image_url(u):
        score -= 100

    if any(tok in p for tok in ["thumb", "thumbnail", "image", "img"]):
        score -= 20

    parsed = urlparse(u)
    if parsed.query:
        score += 3

    if parsed.hostname:
        if parsed.hostname.endswith("ownerclan.com"):
            score += 10

    return score


def _find_best_detail_url_from_raw(raw: dict) -> str | None:
    urls: list[tuple[str, str]] = []
    _collect_string_urls(raw, "", urls)

    if not urls:
        return None

    scored: list[tuple[int, str, str]] = []
    for path, url in urls:
        if _is_image_url(url):
            continue
        score = _score_detail_url(path, url)
        scored.append((score, path, url))

    scored.sort(key=lambda x: x[0], reverse=True)

    for score, path, url in scored[:30]:
        if score < 0:
            continue
        if _is_safe_public_http_url(url):
            return url

    for score, path, url in scored[:30]:
        if _is_safe_public_http_url(url):
            return url

    return None


def _execute_augment_images_from_detail_url(product_id: uuid.UUID, detail_url: str, target_count: int) -> None:
    import traceback
    from app.session_factory import session_factory
    import httpx
    from app.services.image_processing import image_processing_service

    try:
        with session_factory() as session:
            product = session.get(Product, product_id)
            if not product:
                return

            existing = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
            if len(existing) >= int(target_count):
                return

            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    resp = client.get(
                        str(detail_url),
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                if resp.status_code >= 400:
                    return
                html = resp.text or ""
            except Exception:
                return

            extracted = image_processing_service.extract_images_from_html(html, limit=50)
            if not extracted:
                return

            new_urls = image_processing_service.process_and_upload_images(
                image_urls=extracted,
                detail_html="",
                product_id=str(product.id),
            )

            merged: list[str] = []
            seen: set[str] = set()
            for u in (existing + (new_urls or [])):
                if not u:
                    continue
                su = str(u)
                if su in seen:
                    continue
                seen.add(su)
                merged.append(su)
                if len(merged) >= 20:
                    break

            product.processed_image_urls = merged
            if product.processed_name and len(merged) >= int(target_count):
                product.processing_status = "COMPLETED"
            session.commit()
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in augment_images_from_detail_url for {product_id}:\n{error_trace}")


@router.post("/{product_id}/process", status_code=202)
def trigger_process_product(
    product_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: ProductProcessIn | None = None,
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    if payload is None:
        payload = ProductProcessIn()

    product.processing_status = "PROCESSING"
    session.commit()

    background_tasks.add_task(
        _execute_product_processing_bg,
        product.id,
        int(payload.minImagesRequired),
        bool(payload.forceFetchOwnerClan),
    )

    return {"status": "accepted", "productId": str(product.id), "minImagesRequired": int(payload.minImagesRequired)}


@router.post("/{product_id}/premium-optimize", status_code=202)
def trigger_premium_optimize_product(
    product_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    판매된 상품에 대해 프리미엄 가공(이미지 분석 및 상세페이지 고도화)을 수동으로 트리거합니다.
    """
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # 상태를 PROCESSING으로 변경하여 중복 작업 방지
    product.processing_status = "PROCESSING"
    session.commit()

    async def _run_premium_optimize():
        from app.services.processing_service import ProcessingService
        from app.session_factory import session_factory
        try:
            with session_factory() as processing_session:
                service = ProcessingService(processing_session)
                await service.process_winning_product(product_id)
        except Exception as e:
            logger.error(f"Error in premium optimization for {product_id}: {e}")
            with session_factory() as error_session:
                prod = error_session.get(Product, product_id)
                if prod:
                    prod.processing_status = "FAILED"
                    error_session.commit()

    background_tasks.add_task(_run_premium_optimize)

    return {"status": "accepted", "productId": str(product_id)}


@router.post("/process/pending", status_code=202)
def trigger_process_pending_products(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=10, ge=1, le=200),
    min_images_required: int = Query(default=3, ge=1, le=20, alias="minImagesRequired"),
):
    background_tasks.add_task(_execute_pending_product_processing_bg, int(limit), int(min_images_required))

    return {"status": "accepted", "limit": int(limit), "minImagesRequired": int(min_images_required)}


@router.post("/process/failed", status_code=202)
async def trigger_process_failed_products(
    payload: ProductProcessFailedIn,
    background_tasks: BackgroundTasks,
    wait: bool = Query(default=False),
):
    if wait:
        from app.session_factory import session_factory

        with session_factory() as session:
            summary = await _run_failed_product_processing(
                session,
                limit=int(payload.limit),
                min_images_required=int(payload.minImagesRequired),
                force_fetch_ownerclan=bool(payload.forceFetchOwnerClan),
                augment_images=bool(payload.augmentImages),
            )
            return {"status": "completed", "summary": summary}

    background_tasks.add_task(
        _execute_failed_product_processing_bg,
        int(payload.limit),
        int(payload.minImagesRequired),
        bool(payload.forceFetchOwnerClan),
        bool(payload.augmentImages),
    )

    return {
        "status": "accepted",
        "limit": int(payload.limit),
        "minImagesRequired": int(payload.minImagesRequired),
        "forceFetchOwnerClan": bool(payload.forceFetchOwnerClan),
        "augmentImages": bool(payload.augmentImages),
        "wait": False,
    }


@router.post("/registration/pending/clear", status_code=200)
def clear_registration_pending(
    session: Session = Depends(get_session),
) -> dict:
    """
    등록 대기(DRAFT + COMPLETED) 상품을 일괄 삭제합니다.
    """
    ids = session.scalars(
        select(Product.id).where(
            Product.status == "DRAFT",
            Product.processing_status == "COMPLETED",
        )
    ).all()

    if not ids:
        return {"deletedProducts": 0, "deletedListings": 0}

    deleted_listings = session.execute(
        delete(MarketListing).where(MarketListing.product_id.in_(ids))
    ).rowcount or 0
    deleted_products = session.execute(
        delete(Product).where(Product.id.in_(ids))
    ).rowcount or 0
    session.commit()

    return {"deletedProducts": int(deleted_products), "deletedListings": int(deleted_listings)}


def _execute_failed_product_processing_bg(limit: int, min_images_required: int, force_fetch_ownerclan: bool, augment_images: bool) -> None:
    import asyncio

    asyncio.run(
        _execute_failed_product_processing(
            int(limit),
            int(min_images_required),
            bool(force_fetch_ownerclan),
            bool(augment_images),
        )
    )


@router.get("/process/failed/preview", status_code=200)
def preview_process_failed_products(
    session: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=500),
    min_images_required: int = Query(default=5, ge=1, le=20, alias="minImagesRequired"),
):
    stmt = select(Product).order_by(Product.updated_at.desc()).limit(int(limit))
    rows = session.scalars(stmt).all()

    result: list[dict] = []
    for p in rows:
        imgs = p.processed_image_urls if isinstance(p.processed_image_urls, list) else []
        needs_fix = p.processing_status == "FAILED" or len(imgs) < int(min_images_required)
        if not needs_fix:
            continue
        result.append(
            {
                "productId": str(p.id),
                "supplierItemId": str(p.supplier_item_id) if p.supplier_item_id else None,
                "processingStatus": p.processing_status,
                "imagesCount": len(imgs),
                "minImagesRequired": int(min_images_required),
                "updatedAt": p.updated_at.isoformat() if p.updated_at else None,
            }
        )

    return result


@router.post("/{product_id}/images/augment-from-detail-url", status_code=202)
def augment_images_from_detail_url(
    product_id: uuid.UUID,
    payload: ProductAugmentImagesFromDetailUrlIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    raw_item = session.get(SupplierItemRaw, product.supplier_item_id) if product.supplier_item_id else None
    raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}

    detail_url = str(payload.detailUrl).strip() if payload.detailUrl else None

    if detail_url:
        if not _is_safe_public_http_url(detail_url):
            raise HTTPException(status_code=400, detail="허용되지 않는 상세페이지 URL 입니다.")

        if _is_image_url(detail_url):
            background_tasks.add_task(
                _execute_augment_images_from_image_urls,
                product.id,
                [detail_url],
                int(payload.targetCount),
            )
            
            return {
                "status": "accepted",
                "productId": str(product.id),
                "detailUrl": detail_url,
                "targetCount": int(payload.targetCount),
            }

        background_tasks.add_task(
            _execute_augment_images_from_detail_url,
            product.id,
            detail_url,
            int(payload.targetCount),
        )

        return {
            "status": "accepted",
            "productId": str(product.id),
            "detailUrl": detail_url,
            "targetCount": int(payload.targetCount),
        }

    html_url = _find_best_detail_url_from_raw(raw) or _extract_detail_url_from_raw(raw)
    if html_url and _is_safe_public_http_url(html_url):
        if _is_image_url(html_url):
            image_urls = _collect_image_urls_from_raw(raw)
            if not image_urls:
                image_urls = [html_url]

            background_tasks.add_task(
                _execute_augment_images_from_image_urls,
                product.id,
                image_urls,
                int(payload.targetCount),
            )

            return {
                "status": "accepted",
                "productId": str(product.id),
                "detailUrl": html_url,
                "targetCount": int(payload.targetCount),
                "source": "raw_detail_image_url",
                "candidateImages": len(image_urls),
            }

        background_tasks.add_task(
            _execute_augment_images_from_detail_url,
            product.id,
            html_url,
            int(payload.targetCount),
        )

        return {
            "status": "accepted",
            "productId": str(product.id),
            "detailUrl": html_url,
            "targetCount": int(payload.targetCount),
        }

    image_urls = _collect_image_urls_from_raw(raw)
    if not image_urls:
        raise HTTPException(status_code=400, detail="원본 데이터에서 상세페이지/이미지 URL을 찾을 수 없습니다.")

    background_tasks.add_task(
        _execute_augment_images_from_image_urls,
        product.id,
        image_urls,
        int(payload.targetCount),
    )

    return {
        "status": "accepted",
        "productId": str(product.id),
        "detailUrl": None,
        "targetCount": int(payload.targetCount),
        "source": "raw_image_urls",
        "candidateImages": len(image_urls),
    }
