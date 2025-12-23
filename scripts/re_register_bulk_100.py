import asyncio
import uuid
import logging
import sys
import concurrent.futures

from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import Product, MarketAccount, MarketListing
from app.coupang_sync import register_product

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("re_register_bulk")

async def re_register_bulk(limit_count: int = 100):
    with SessionLocal() as session:
        # 1. 대상 계정 확인
        account = session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True).first()
        if not account:
            logger.error("Active Coupang account not found.")
            return
        account_id = account.id

        # 2. 등록 대상 상품 선정 (가공 완료 && 미등록)
        stmt = (
            select(Product)
            .where(Product.processing_status == "COMPLETED")
            .where(~Product.id.in_(select(MarketListing.product_id)))
            .limit(limit_count)
        )
        products = session.scalars(stmt).all()
        total_targets = len(products)
        
        if total_targets == 0:
            logger.info("No products ready for registration.")
            return

        logger.info(f"Starting registration for {total_targets} products...")

    success_count = 0
    fail_count = 0

    # 3. 등록 실행 (API 레이트 리밋을 위해 순차적으로 처리하거나 소수 스레드 사용)
    # 여기서는 안전하게 순차 처리
    for idx, product in enumerate(products, 1):
        logger.info(f"[{idx}/{total_targets}] Registering: {product.processed_name or product.name} ({product.id})")
        
        try:
            # register_product는 내부적으로 세션을 생성하거나 전달받음
            # 여기서는 별도 세션으로 실행
            with SessionLocal() as session:
                ok, err = register_product(session, account_id, product.id)
                if ok:
                    logger.info(f"  -> Success!")
                    success_count += 1
                    # 상태 업데이트 (ACTIVE로 변경 등은 register_product 내부에 있을 수 있으나 명시적 확인 필요)
                    p = session.get(Product, product.id)
                    p.status = "ACTIVE"
                    session.commit()
                else:
                    logger.error(f"  -> Failed: {err}")
                    fail_count += 1
        except Exception as e:
            logger.error(f"  -> Exception: {e}")
            fail_count += 1

    logger.info("-" * 50)
    logger.info(f"Registration Finished:")
    logger.info(f"  - Total: {total_targets}")
    logger.info(f"  - Success: {success_count}")
    logger.info(f"  - Failure: {fail_count}")
    logger.info("-" * 50)

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    asyncio.run(re_register_bulk(count))
