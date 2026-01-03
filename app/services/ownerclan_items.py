from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Product, SupplierAccount, SupplierItemRaw
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.market_targeting import resolve_trade_flags_from_raw
from app.services.pricing import calculate_selling_price, parse_int_price, parse_shipping_fee

logger = logging.getLogger(__name__)


class OwnerClanItemError(RuntimeError):
    def __init__(self, code: str, status_code: int = 400, meta: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.meta = meta or {}


def normalize_ownerclan_item_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        payload = data

    if isinstance(payload, dict):
        detail_html = payload.get("detail_html") or payload.get("detailHtml")
        if isinstance(detail_html, str) and detail_html.strip():
            payload = {**payload, "detail_html": normalize_ownerclan_html(detail_html)}
        else:
            content = payload.get("content") or payload.get("description")
            if isinstance(content, str) and content.strip():
                payload = {**payload, "detail_html": normalize_ownerclan_html(content)}

    return payload


def _get_primary_ownerclan_account(session: Session) -> SupplierAccount | None:
    return (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )


def _upsert_ownerclan_raw_item(
    session: Session,
    item_code: str,
    raw_payload: dict,
    fetched_at: datetime,
) -> None:
    stmt = insert(SupplierItemRaw).values(
        supplier_code="ownerclan",
        item_code=item_code,
        item_key=str(raw_payload.get("key")) if raw_payload.get("key") is not None else None,
        item_id=str(raw_payload.get("id")) if raw_payload.get("id") is not None else None,
        fetched_at=fetched_at,
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


def get_or_fetch_ownerclan_item_raw(
    session: Session,
    item_code: str,
    force_fetch: bool,
) -> SupplierItemRaw | None:
    item_code_norm = str(item_code or "").strip()
    if not item_code_norm:
        return None

    raw_item = (
        session.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .where(SupplierItemRaw.item_code == item_code_norm)
        )
        .scalars()
        .first()
    )
    if raw_item and not force_fetch:
        return raw_item

    owner = _get_primary_ownerclan_account(session)
    if not owner or not owner.access_token:
        raise OwnerClanItemError("missing_primary_account", status_code=400)

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
        access_token=owner.access_token,
    )
    status_code, data = client.get_product(item_code_norm)
    if status_code >= 400:
        raise OwnerClanItemError("fetch_failed", status_code=400, meta={"http_status": status_code})

    raw_payload = normalize_ownerclan_item_payload(data)
    now = datetime.now(timezone.utc)
    _upsert_ownerclan_raw_item(session, item_code_norm, raw_payload, now)

    return (
        session.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .where(SupplierItemRaw.item_code == item_code_norm)
        )
        .scalars()
        .first()
    )


def _compute_pricing_from_raw(raw: dict) -> tuple[int, int, int]:
    supply_price = (
        raw.get("supply_price")
        or raw.get("supplyPrice")
        or raw.get("fixedPrice")
        or raw.get("fixed_price")
        or raw.get("price")
        or 0
    )
    cost = parse_int_price(supply_price)
    shipping_fee = parse_shipping_fee(raw)
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
        market_fee_rate=float(settings.pricing_market_fee_rate or 0.13),
    )
    return cost, shipping_fee, selling_price


def create_or_get_product_from_raw_item(
    session: Session,
    raw_item: SupplierItemRaw,
    update_existing_pricing: bool = False,
) -> tuple[Product, bool, bool]:
    existing = (
        session.execute(select(Product).where(Product.supplier_item_id == raw_item.id))
        .scalars()
        .first()
    )
    if existing:
        updated = False
        if update_existing_pricing:
            raw = raw_item.raw if isinstance(raw_item.raw, dict) else {}
            cost, _shipping_fee, selling_price = _compute_pricing_from_raw(raw)
            if (existing.selling_price or 0) <= 0 and selling_price > 0:
                existing.cost_price = cost
                existing.selling_price = selling_price
                updated = True
                session.flush()
        return existing, False, updated

    data = raw_item.raw if isinstance(raw_item.raw, dict) else {}
    item_name = data.get("item_name") or data.get("name") or data.get("itemName") or "Untitled"
    brand_name = data.get("brand") or data.get("brand_name")
    description = data.get("description") or data.get("content")

    cost, _shipping_fee, selling_price = _compute_pricing_from_raw(data)

    parallel_imported, overseas_purchased = resolve_trade_flags_from_raw(raw_item.raw if raw_item else None)

    product = Product(
        supplier_item_id=raw_item.id,
        name=str(item_name),
        brand=str(brand_name) if brand_name is not None else None,
        description=str(description) if description is not None else None,
        cost_price=cost,
        selling_price=selling_price,
        status="DRAFT",
        coupang_parallel_imported=parallel_imported,
        coupang_overseas_purchased=overseas_purchased,
    )
    session.add(product)
    session.flush()
    return product, True, False


def refresh_ownerclan_raw_if_needed(session: Session, product: Product) -> bool:
    if not product or not product.supplier_item_id:
        return False

    raw_item = session.get(SupplierItemRaw, product.supplier_item_id)
    if not raw_item or raw_item.supplier_code != "ownerclan":
        return False

    item_code = str(raw_item.item_code or "").strip()
    if not item_code:
        return False

    owner = _get_primary_ownerclan_account(session)
    if not owner or not owner.access_token:
        return False

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

    _upsert_ownerclan_raw_item(session, item_code, raw_payload, now)
    return True
