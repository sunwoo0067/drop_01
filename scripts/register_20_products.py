
import asyncio
import uuid
import logging
from sqlalchemy import select
from app.session_factory import session_factory
from app.models import SourcingCandidate, Product, MarketAccount
from app.api.endpoints.sourcing import _get_or_fetch_supplier_item_raw, _create_or_get_product_from_raw_item, _execute_post_promote_actions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    with session_factory() as session:
        # 1. Get 20 pending candidates
        stmt = select(SourcingCandidate).where(SourcingCandidate.status == "PENDING").limit(5)
        candidates = session.scalars(stmt).all()
        
        if not candidates:
            logger.info("No pending candidates found.")
            return

        logger.info(f"Selected {len(candidates)} candidates for registration.")

        # 2. Find Coupang account
        account = session.execute(
            select(MarketAccount)
            .where(MarketAccount.market_code == "COUPANG")
            .where(MarketAccount.is_active == True)
        ).scalars().first()
        
        if not account:
            logger.error("No active Coupang account found.")
            return

        for cand in candidates:
            try:
                # Update status to APPROVED
                cand.status = "APPROVED"
                session.commit()
                
                logger.info(f"Promoting candidate: {cand.name} ({cand.supplier_item_id})")
                
                # Fetch raw data
                raw_item = _get_or_fetch_supplier_item_raw(
                    session,
                    item_code=str(cand.supplier_item_id),
                    force_fetch=False
                )
                
                if not raw_item:
                    logger.warning(f"Raw item not found for {cand.supplier_item_id}")
                    continue
                
                # Create Product
                product, created = _create_or_get_product_from_raw_item(session, raw_item)
                session.commit()
                
                logger.info(f"Product {'created' if created else 'already exists'}: {product.id}")
                
                # Trigger process and register
                # We use the async version directly since we are in a main async loop
                await _execute_post_promote_actions(
                    product_id=product.id,
                    auto_register_coupang=True,
                    min_images_required=5
                )
                
                logger.info(f"Successfully triggered registration for {product.id}")
                
            except Exception as e:
                logger.error(f"Failed to process candidate {cand.id}: {e}", exc_info=True)
                session.rollback()

if __name__ == "__main__":
    asyncio.run(main())
