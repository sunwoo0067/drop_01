from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.db import get_session
from app.models import Product, MarketAccount
from app.coupang_sync import register_product

router = APIRouter()

@router.post("/register/{product_id}", status_code=202)
async def register_product_endpoint(
    product_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
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

    # 백그라운드 작업 등록
    background_tasks.add_task(execute_coupang_registration, account.id, product.id)
        
    return {"status": "accepted", "message": "쿠팡 상품 등록 작업이 시작되었습니다."}

def execute_coupang_registration(account_id: uuid.UUID, product_id: uuid.UUID):
    """
    별도의 DB 세션을 사용하여 쿠팡 등록 작업을 수행합니다.
    """
    from app.session_factory import session_factory
    
    with session_factory() as session:
        success = register_product(session, account_id, product_id)
        if success:
             # 성공 로깅은 register_product 내부에서 수행됨
             pass
        else:
             # 실패 로깅도 내부 수행됨
             pass
