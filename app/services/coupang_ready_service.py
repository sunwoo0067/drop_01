import ipaddress
import logging
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models import Product, SupplierAccount, SupplierItemRaw
from app.settings import settings

logger = logging.getLogger(__name__)


def _is_ip_disallowed(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except Exception:
        return True

    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return True
    if addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        return True
    return False


def _resolve_hostname_ips(hostname: str) -> list[str]:
    ips: list[str] = []
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return []

    for info in infos:
        try:
            sockaddr = info[4]
            ip = sockaddr[0]
            if ip and ip not in ips:
                ips.append(ip)
        except Exception:
            continue

    return ips


def is_safe_public_http_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    if host in ("localhost", "127.0.0.1", "::1"):
        return False

    ips = _resolve_hostname_ips(host)
    if not ips:
        return False

    for ip in ips:
        if _is_ip_disallowed(ip):
            return False

    return True


def is_image_url(url: str) -> bool:
    u = (url or "").lower()
    return any(ext in u for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"])


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


def extract_detail_url_from_raw(raw: dict) -> str | None:
    if not isinstance(raw, dict):
        return None

    key_candidates = [
        "detail_url",
        "detailUrl",
        "detailPageUrl",
        "detail_page_url",
        "productUrl",
        "product_url",
        "url",
        "link",
        "itemUrl",
        "item_url",
    ]

    for k in key_candidates:
        v = raw.get(k)
        if isinstance(v, str) and v.strip().startswith(("http://", "https://")):
            return v.strip()

    for k in list(raw.keys()):
        try:
            ks = str(k).lower()
        except Exception:
            continue

        if "detail" in ks and "url" in ks:
            v = raw.get(k)
            if isinstance(v, str) and v.strip().startswith(("http://", "https://")):
                return v.strip()

    return None


def _score_detail_url_candidate(path: str, url: str) -> float:
    if not url or not url.startswith(("http://", "https://")):
        return -1.0

    u = url.lower()
    p = (path or "").lower()

    if is_image_url(u):
        return -1.0

    score = 0.0

    if any(x in u for x in ["detail", "product", "goods", "item", "view", "catalog"]):
        score += 3.0

    if any(x in p for x in ["detail", "product", "goods", "item"]):
        score += 2.0

    if any(x in p for x in ["iframe", "content", "html", "page", "link", "url"]):
        score += 1.0

    if any(x in u for x in ["cdn", "static", "image", "img"]):
        score -= 0.5

    if len(u) > 60:
        score += 0.5

    return score


def find_best_detail_url_from_raw(raw: dict) -> str | None:
    urls: list[tuple[str, str]] = []
    _collect_string_urls(raw, "", urls)

    best_url: str | None = None
    best_score = -1.0

    for path, url in urls:
        s = _score_detail_url_candidate(path, url)
        if s > best_score:
            best_score = s
            best_url = url

    return best_url


def collect_image_urls_from_raw(raw: dict) -> list[str]:
    urls: list[tuple[str, str]] = []
    _collect_string_urls(raw, "", urls)

    candidates: list[str] = []
    seen: set[str] = set()
    for path, url in urls:
        if not url:
            continue
        if not is_image_url(url):
            continue
        if not is_safe_public_http_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        candidates.append(url)
        if len(candidates) >= 20:
            break

    return candidates


def refresh_ownerclan_raw_if_needed(session: Session, product: Product) -> bool:
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


def augment_product_images_best_effort(session: Session, product: Product, raw: dict, target_count: int) -> bool:
    existing = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    before_count = len(existing)
    if before_count >= int(target_count):
        return False

    html_url = find_best_detail_url_from_raw(raw) or extract_detail_url_from_raw(raw)

    if html_url and is_safe_public_http_url(html_url) and not is_image_url(html_url):
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

    image_urls = collect_image_urls_from_raw(raw)
    if not image_urls:
        if html_url and is_safe_public_http_url(html_url) and is_image_url(html_url):
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
    if product.processed_name and len(merged) >= int(target_count):
        product.processing_status = "COMPLETED"
    session.commit()

    return len(merged) > before_count


async def ensure_product_ready_for_coupang(
    session: Session,
    product_id: str,
    min_images_required: int = 5,
    force_fetch_ownerclan: bool = True,
    augment_images: bool = True,
) -> dict:
    product = session.get(Product, product_id)
    if not product:
        return {"ok": False, "reason": "상품을 찾을 수 없습니다"}

    refreshed = False
    augmented = False
    processed = False

    if force_fetch_ownerclan:
        try:
            refreshed = refresh_ownerclan_raw_if_needed(session, product)
        except Exception as e:
            logger.error(f"오너클랜 raw 갱신 실패(productId={product.id}): {e}")

    images0 = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    needs_processing = product.processing_status != "COMPLETED" or len(images0) < int(min_images_required)

    if needs_processing:
        try:
            from app.services.processing_service import ProcessingService

            service = ProcessingService(session)
            await service.process_product(product.id, min_images_required=int(min_images_required))
            processed = True
        except Exception as e:
            logger.error(f"상품 가공 실패(productId={product.id}): {e}")

    session.refresh(product)

    images1 = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    if augment_images and (product.processing_status != "COMPLETED" or len(images1) < int(min_images_required)):
        raw_item = session.get(SupplierItemRaw, product.supplier_item_id) if product.supplier_item_id else None
        raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
        try:
            augmented = augment_product_images_best_effort(session, product, raw, target_count=int(min_images_required))
        except Exception as e:
            logger.error(f"이미지 보강 실패(productId={product.id}): {e}")

    session.refresh(product)
    images2 = product.processed_image_urls if isinstance(product.processed_image_urls, list) else []
    ok = product.processing_status == "COMPLETED" and len(images2) >= int(min_images_required)

    return {
        "ok": ok,
        "productId": str(product.id),
        "processingStatus": product.processing_status,
        "imagesCount": len(images2),
        "minImagesRequired": int(min_images_required),
        "refreshedRaw": bool(refreshed),
        "processed": bool(processed),
        "augmentedImages": bool(augmented),
    }
