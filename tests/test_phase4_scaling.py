
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from app.db import SessionLocal
from app.models import (
    Product, Order, OrderItem, MarketAccount, MarketListing, 
    MarketFeePolicy, SalesAnalytics
)
from app.services.sourcing_recommendation_service import SourcingRecommendationService
from app.services.sales_analytics_service import SalesAnalyticsService

async def test_scaling_and_fees():
    db = SessionLocal()
    
    try:
        # 1. 테스트 데이터 준비
        print("Preparing test data...")
        
        # 테스트 전 전처리
        db.execute(delete(OrderItem).where(OrderItem.product_name.like("TEST_SCALING_%")))
        db.execute(delete(Order).where(Order.recipient_name == "SCALING_TESTER"))
        db.execute(delete(MarketFeePolicy).where(MarketFeePolicy.description == "TEST_POLICY"))
        db.execute(delete(MarketListing).where(MarketListing.market_item_id.like("TEST_LISTING_%")))
        db.execute(delete(Product).where(Product.name.like("TEST_SCALING_%")))
        db.execute(delete(MarketAccount).where(MarketAccount.name.in_(["TEST_CP", "TEST_SS"])))
        db.commit()

        product_id = uuid.uuid4()
        product = Product(
            id=product_id,
            name="TEST_SCALING_PRODUCT",
            cost_price=10000,
            selling_price=20000,
            status="ACTIVE",
            processing_status="APPROVED"
        )
        db.add(product)
        
        acc_cp_id = uuid.uuid4()
        acc_ss_id = uuid.uuid4()
        acc_coupang = MarketAccount(id=acc_cp_id, market_code="COUPANG", name="TEST_CP", credentials={}, is_active=True)
        acc_smartstore = MarketAccount(id=acc_ss_id, market_code="SMARTSTORE", name="TEST_SS", credentials={}, is_active=True)
        db.add(acc_coupang)
        db.add(acc_smartstore)
        
        db.commit()
        db.close()
        
        db = SessionLocal()
        
        listing_cp = MarketListing(
            product_id=product_id,
            market_account_id=acc_cp_id,
            market_item_id="TEST_LISTING_CP",
            status="APPROVED"
        )
        db.add(listing_cp)
        
        # 주문 생성 - 최근 14일 이내 5개 이상 조건 충족을 위해 10개 생성
        now = datetime.now(timezone.utc)
        for i in range(10):
            order = Order(
                id=uuid.uuid4(),
                order_number=f"TEST_ORDER_{i}",
                status="DELIVERED",
                total_amount=20000,
                recipient_name="SCALING_TESTER",
                created_at=now - timedelta(days=1)
            )
            db.add(order)
            db.flush()
            
            oi = OrderItem(
                order_id=order.id,
                product_id=product_id,
                product_name="TEST_SCALING_PRODUCT",
                quantity=1,
                unit_price=20000,
                total_price=20000
            )
            db.add(oi)
        
        db.commit()
        print("Test data prepared.")

        # 2. 다채널 확장 추천 테스트
        print("Testing get_scaling_recommendations...")
        sourcing_service = SourcingRecommendationService(db)
        recommendations = await sourcing_service.get_scaling_recommendations(limit=10)
        
        print(f"Total recommendations found: {len(recommendations)}")
        for r in recommendations:
            print(f"- Product: {r['product_name']}, Target: {r['target_market']}")
            
        target_rec = next((r for r in recommendations if r["product_id"] == str(product_id)), None)
        if not target_rec:
            # 왜 추천이 안 나왔는지 상세 분석
            print("Target recommendation NOT found. Checking criteria...")
            high_performers = db.execute(
                select(OrderItem.product_id, Product.name, func.count(OrderItem.id))
                .join(Product, OrderItem.product_id == Product.id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.created_at >= now - timedelta(days=14))
                .group_by(OrderItem.product_id, Product.name)
                .having(func.count(OrderItem.id) >= 5)
            ).all()
            print(f"High performers in DB: {high_performers}")
            
            listings = db.execute(
                select(MarketAccount.market_code)
                .join(MarketListing, MarketAccount.id == MarketListing.market_account_id)
                .where(MarketListing.product_id == product_id)
            ).scalars().all()
            print(f"Current listings for product: {listings}")
            
            raise AssertionError("Target scaling recommendation not found in results")
            
        assert target_rec["target_market"] == "SMARTSTORE", "Should recommend expanding to SMARTSTORE"
        print(f"✓ Scaling recommendation verified.")

        # 3. 정밀 수수료 정책 테스트
        print("Testing MarketFeePolicy... (SKIPPED if we failed above)")
        policy = MarketFeePolicy(
            market_code="SMARTSTORE",
            category_id=None,
            fee_rate=0.06,
            description="TEST_POLICY"
        )
        db.add(policy)
        db.commit()
        
        analytics_service = SalesAnalyticsService(db)
        fee_rate = analytics_service._get_market_fee_rate("SMARTSTORE")
        assert fee_rate == 0.06
        print("✓ MarketFeePolicy verified.")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e
    finally:
        # 청소
        print("Cleaning up...")
        db.execute(delete(OrderItem).where(OrderItem.product_name.like("TEST_SCALING_%")))
        db.execute(delete(Order).where(Order.recipient_name == "SCALING_TESTER"))
        db.execute(delete(MarketFeePolicy).where(MarketFeePolicy.description == "TEST_POLICY"))
        db.execute(delete(MarketListing).where(MarketListing.market_item_id.like("TEST_LISTING_%")))
        db.execute(delete(Product).where(Product.name.like("TEST_SCALING_%")))
        db.execute(delete(MarketAccount).where(MarketAccount.name.in_(["TEST_CP", "TEST_SS"])))
        db.commit()
        db.close()
        print("Cleanup done.")

if __name__ == "__main__":
    asyncio.run(test_scaling_and_fees())
