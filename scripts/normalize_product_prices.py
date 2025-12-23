import logging
import datetime
from sqlalchemy import select, update, func
from app.db import get_session
from app.models import Product, SupplierItemRaw
from app.services.pricing import calculate_selling_price, parse_int_price, parse_shipping_fee
from app.settings import settings
from app.session_factory import session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalize_product_prices():
    with session_factory() as session:
        # 1. 대상 상품 식별 (모든 상품 대상 신규 정책 소급 적용)
        stmt = (
            select(Product.id, Product.name, SupplierItemRaw.raw)
            .join(SupplierItemRaw, Product.supplier_item_id == SupplierItemRaw.id)
        )
        targets = session.execute(stmt).all()
        
        if not targets:
            logger.info("No products found in DB.")
            return

        logger.info(f"Retrieved {len(targets)} products for price re-normalization (New Policy).")

        try:
            margin_rate = float(settings.pricing_default_margin_rate or 0.15)
        except Exception:
            margin_rate = 0.15

        for p_id, p_name, raw_data in targets:
            data = raw_data if isinstance(raw_data, dict) else {}
            
            supply_price_val = (
                data.get("supply_price")
                or data.get("supplyPrice")
                or data.get("fixedPrice")
                or data.get("fixed_price")
                or data.get("price")
                or 0
            )
            
            cost = parse_int_price(supply_price_val)
            shipping_fee = parse_shipping_fee(data)
            selling_price = calculate_selling_price(cost, margin_rate, shipping_fee)
            
            if selling_price > 0:
                logger.info(f"Updating: {p_name} | Cost: {cost}, Ship: {shipping_fee}, Selling: {selling_price}")
                # ORM 객체 방식으로 업데이트하여 updated_at 자동 반영 시도 또는 명시적 설정
                p = session.get(Product, p_id)
                if p:
                    p.cost_price = cost
                    p.selling_price = selling_price
                    p.updated_at = datetime.datetime.now(datetime.timezone.utc)
            else:
                logger.warning(f"Could not calculate selling price for {p_name} (ID: {p_id})")

        session.commit()
        logger.info("Price normalization process completed.")

if __name__ == "__main__":
    normalize_product_prices()
