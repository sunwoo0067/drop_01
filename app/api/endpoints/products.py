from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List
import uuid

from app.db import get_session
from app.models import Product
from app.schemas.product import ProductResponse

router = APIRouter()

@router.get("/stats")
def get_product_stats(session: Session = Depends(get_session)):
    """상품 통계를 조회합니다."""
    total = session.scalar(select(func.count(Product.id))) or 0
    pending = session.scalar(select(func.count(Product.id)).where(Product.processing_status != "COMPLETED")) or 0
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
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.") # Korean Error Message
    return product
