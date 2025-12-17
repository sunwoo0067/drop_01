from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List
import uuid

from app.db import get_session
from app.models import Product, SupplierItemRaw, SourcingCandidate
from app.schemas.product import ProductResponse
from app.settings import settings

router = APIRouter()


def _parse_int_price(value) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0

class ProductFromOwnerClanRawIn(BaseModel):
    supplierItemRawId: uuid.UUID

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
def list_products(session: Session = Depends(get_session)):
    """모든 상품 목록을 조회합니다."""
    stmt = select(Product).order_by(Product.created_at.desc())
    products = session.scalars(stmt).all()
    return products

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: uuid.UUID, session: Session = Depends(get_session)):
    """단일 상품 정보를 조회합니다."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.") # 한국어 오류 메시지
    return product


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
        cost = _parse_int_price(supply_price)
        try:
            margin_rate = float(settings.pricing_default_margin_rate or 0.0)
        except Exception:
            margin_rate = 0.0
        if margin_rate < 0:
            margin_rate = 0.0
        selling_price = int(cost * (1.0 + margin_rate))

        updated = False
        if (existing.selling_price or 0) <= 0 and selling_price > 0:
            existing.cost_price = cost
            existing.selling_price = selling_price
            updated = True
            session.flush()

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

    cost = _parse_int_price(supply_price)
    try:
        margin_rate = float(settings.pricing_default_margin_rate or 0.0)
    except Exception:
        margin_rate = 0.0
    if margin_rate < 0:
        margin_rate = 0.0
    selling_price = int(cost * (1.0 + margin_rate))

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

    return {"created": True, "productId": str(product.id)}
