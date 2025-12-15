from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
import uuid

from app.db import get_session
from app.models import Product
from app.schemas.product import ProductResponse

router = APIRouter()

@router.get("/", response_model=List[ProductResponse])
def list_products(session: Session = Depends(get_session)):
    """List all products with their processing status."""
    stmt = select(Product).order_by(Product.created_at.desc())
    products = session.scalars(stmt).all()
    return products

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: uuid.UUID, session: Session = Depends(get_session)):
    """Get a single product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.") # Korean Error Message
    return product
