import asyncio
import logging
import uuid
from sqlalchemy import select, func
from app.db import get_session
from app.models import Product, Order, OrderItem
from app.services.orchestrator_service import OrchestratorService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def verify_pipeline():
    session_gen = get_session()
    session = next(session_gen)
    orchestrator = OrchestratorService(session)

    logger.info("--- Phase 1: Preparation ---")
    # 1. 판매 데이터 시뮬레이션 (최근 가공 완료된 상품 하나를 판매된 것으로 간주)
    stmt_prod = select(Product).where(Product.processing_status == "COMPLETED").limit(1)
    target_product = session.scalars(stmt_prod).first()
    
    if target_product:
        logger.info(f"Simulating sale for product: {target_product.name}")
        # 주문 데이터 생성
        new_order = Order(
            id=uuid.uuid4(),
            order_number=f"TEST-{uuid.uuid4().hex[:8]}",
            status="DELIVERED",
            total_amount=target_product.selling_price
        )
        session.add(new_order)
        session.flush()
        
        new_item = OrderItem(
            id=uuid.uuid4(),
            order_id=new_order.id,
            product_id=target_product.id,
            product_name=target_product.name,
            quantity=1,
            unit_price=target_product.selling_price,
            total_price=target_product.selling_price
        )
        session.add(new_item)
        session.commit()
    else:
        logger.warning("No COMPLETED products found for sale simulation.")

    logger.info("--- Phase 2: Running Orchestration Cycle (Should NOT auto-trigger) ---")
    await orchestrator.run_daily_cycle(dry_run=False)
    
    session.refresh(target_product)
    if target_product.processing_status == "COMPLETED":
        logger.info("CONFIRMED: Orchestrator did NOT automatically trigger premium processing.")
    
    logger.info("--- Phase 3: Manual Trigger via API (Logic Simulation) ---")
    # API 엔드포인트에서 수행하는 백그라운드 태스크 로직 시뮬레이션
    from app.services.processing_service import ProcessingService
    service = ProcessingService(session)
    await service.process_winning_product(target_product.id)
    
    session.refresh(target_product)
    logger.info(f"Product '{target_product.name}' status after manual trigger: {target_product.processing_status}")
    
    if target_product.processing_status in ("PENDING_APPROVAL", "PROCESSING"):
        logger.info("VERIFICATION SUCCESS: Manual premium processing works.")
    else:
        logger.warning(f"Unexpected status: {target_product.processing_status}")

if __name__ == "__main__":
    asyncio.run(verify_pipeline())
