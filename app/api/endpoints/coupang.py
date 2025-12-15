from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.db import get_session
from app.models import Product, MarketAccount
from app.coupang_sync import register_product

router = APIRouter()

@router.post("/register/{product_id}")
async def register_product_endpoint(
    product_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Trigger registration of a product to Coupang.
    Uses the first available Coupang account.
    """
    # Find a coupay account
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
    account = session.scalars(stmt).first()
    
    if not account:
        raise HTTPException(status_code=400, detail="No active Coupang account found")

    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Run synchronously for now to return immediate result, or background?
    # Frontend expects immediate result or we return "accepted".
    # Implementation plan said "background task"? 
    # Let's run it in background to avoid timeout, but update status.
    # Actually register_product is synchronous and might take a few seconds.
    # Let's run synchronous for simple feedback loop first.
    
    success = register_product(session, account.id, product.id)
    if not success:
        raise HTTPException(status_code=500, detail="Registration failed (check logs)")
        
    return {"status": "success", "message": "Product registered successfully"}
