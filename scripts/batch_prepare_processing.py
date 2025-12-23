import uuid
import logging
import sys
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import SourcingCandidate, Product, SupplierItemRaw
from app.api.endpoints.sourcing import _get_or_fetch_supplier_item_raw, _create_or_get_product_from_raw_item

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("batch_prepare_processing")

def batch_prepare(limit_count: int = 1000):
    with SessionLocal() as session:
        # 1. 대상 후보군 선정 (PENDING 상태)
        stmt = (
            select(SourcingCandidate)
            .where(SourcingCandidate.status == "PENDING")
            .limit(limit_count)
        )
        candidates = session.scalars(stmt).all()
        total = len(candidates)
        
        if total == 0:
            logger.info("No pending candidates found.")
            return

        logger.info(f"Preparing {total} candidates for processing...")

        prepared_count = 0
        
        for idx, candidate in enumerate(candidates, 1):
            try:
                # APPROVED로 상태 변경 (가공 착수 의미)
                candidate.status = "APPROVED"
                
                # Raw Item 가져오기/생성
                raw_item = _get_or_fetch_supplier_item_raw(
                    session,
                    item_code=str(candidate.supplier_item_id),
                    force_fetch=False
                )
                
                if not raw_item:
                    logger.warning(f"[{idx}/{total}] Raw item not found for {candidate.supplier_item_id}")
                    continue
                
                # Product 생성 (이미 있으면 가져옴)
                product, created = _create_or_get_product_from_raw_item(session, raw_item)
                
                # 상태를 PENDING으로 설정하여 AI 가공 대기
                if product.processing_status != "COMPLETED":
                    product.processing_status = "PENDING"
                
                if idx % 50 == 0:
                    session.commit()
                    logger.info(f"Progress: {idx}/{total}")
                
                prepared_count += 1
            except Exception as e:
                logger.error(f"[{idx}/{total}] Error preparing {candidate.supplier_item_id}: {e}")
                session.rollback()

        session.commit()
        logger.info(f"Finished. Prepared {prepared_count} products for AI processing.")

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    batch_prepare(count)
