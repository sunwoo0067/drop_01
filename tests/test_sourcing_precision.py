
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from typing import List

from app.models import DropshipBase, Product, ProductOption, Order, OrderItem, SourcingRecommendation
from app.services.sourcing_recommendation_service import SourcingRecommendationService
from app.services.sales_analytics_service import SalesAnalyticsService

from app.db import SessionLocal
from app.models import Product, ProductOption, Order, OrderItem, SourcingRecommendation, SalesAnalytics
from app.services.sourcing_recommendation_service import SourcingRecommendationService

async def test_precision_sourcing():
    # 1. DB 세션 준비 (실제 DB 사용)
    db = SessionLocal()
    
    created_ids = []
    
    try:
        # 2. 테스트 데이터 생성
        product_id = uuid.uuid4()
        
        # 기존에 혹시 있을지 모를 분석 데이터 미리 정리 (안정성 위함)
        db.query(SalesAnalytics).filter_by(product_id=product_id).delete()
        
        product = Product(
            id=product_id,
            name=f"테스트 프리미엄 패딩_{uuid.uuid4().hex[:4]}",
            cost_price=50000,
            selling_price=120000,
            status="ACTIVE"
        )
        db.add(product)
        created_ids.append((Product, product_id))
        
        # 고마진 옵션 (화이트)
        opt_white_id = uuid.uuid4()
        opt_white = ProductOption(
            id=opt_white_id,
            product_id=product_id,
            option_name="색상",
            option_value="화이트",
            cost_price=45000,
            selling_price=120000,
            stock_quantity=5
        )
        
        # 저마진 옵션 (블랙)
        opt_black_id = uuid.uuid4()
        opt_black = ProductOption(
            id=opt_black_id,
            product_id=product_id,
            option_name="색상",
            option_value="블랙",
            cost_price=60000,
            selling_price=120000,
            stock_quantity=10
        )
        db.add_all([opt_white, opt_black])
        created_ids.append((ProductOption, opt_white_id))
        created_ids.append((ProductOption, opt_black_id))
        
        # 3. 판매 데이터 생성 (최근 7일)
        order_date = datetime.now(timezone.utc) - timedelta(days=1)
        
        for i in range(5):
            order_id = uuid.uuid4()
            oi_id = uuid.uuid4()
            order = Order(id=order_id, order_number=f"TEST-W-{i}-{uuid.uuid4().hex[:4]}", status="COMPLETED", total_amount=120000, created_at=order_date)
            db.add(order)
            oi = OrderItem(id=oi_id, order_id=order_id, product_id=product_id, product_option_id=opt_white_id, 
                           product_name="패딩-화이트", quantity=1, unit_price=120000, total_price=120000)
            db.add(oi)
            created_ids.append((Order, order_id))
            created_ids.append((OrderItem, oi_id))
            
        for i in range(1):
            order_id = uuid.uuid4()
            oi_id = uuid.uuid4()
            order = Order(id=order_id, order_number=f"TEST-B-{i}-{uuid.uuid4().hex[:4]}", status="COMPLETED", total_amount=120000, created_at=order_date)
            db.add(order)
            oi = OrderItem(id=oi_id, order_id=order_id, product_id=product_id, product_option_id=opt_black_id, 
                           product_name="패딩-블랙", quantity=1, unit_price=120000, total_price=120000)
            db.add(oi)
            created_ids.append((Order, order_id))
            created_ids.append((OrderItem, oi_id))
            
        db.commit()
        
        # 4. 소싱 추천 실행
        service = SourcingRecommendationService(db)
        print("\n--- Generating Precision Recommendation ---")
        recommendation = await service.generate_product_recommendation(product_id, recommendation_type="REORDER")
        created_ids.append((SourcingRecommendation, recommendation.id))
        
        # 생성된 분석 데이터 추적 (클린업용)
        analytics = db.query(SalesAnalytics).filter_by(product_id=product_id).all()
        for a in analytics:
            created_ids.append((SalesAnalytics, a.id))

        # 5. 결과 검증
        print(f"Product: {product.name}")
        print(f"Overall Score: {recommendation.overall_score:.2f}")
        print(f"Reasoning: {recommendation.reasoning}")
        
        print("\n--- Option Recommendations ---")
        if recommendation.option_recommendations:
            for opt_rec in recommendation.option_recommendations:
                print(f"Option: {opt_rec['option_name']} - {opt_rec['option_value']}")
                print(f"  Score: {opt_rec['score']:.2f}")
                print(f"  Recommended Qty: {opt_rec['recommended_quantity']}")
                print(f"  Margin Rate: {opt_rec['avg_margin_rate']:.1%}")
                print(f"  Sales Qty: {opt_rec['total_quantity']}")
        else:
            print("No option recommendations found!")

        assert len(recommendation.option_recommendations) >= 2, "Should have recommendations for at least 2 options"
        
        white_rec = next(o for o in recommendation.option_recommendations if o['option_value'] == "화이트")
        black_rec = next(o for o in recommendation.option_recommendations if o['option_value'] == "블랙")
        
        print(f"\nWhite Score: {white_rec['score']:.2f} vs Black Score: {black_rec['score']:.2f}")
        assert white_rec['score'] > black_rec['score'], "White option should have higher score"
        
        print("\n✅ Precision Sourcing Test PASSED!")
        
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 클린업 (자식 테이블부터 명시적 삭제)
        print("\nCleaning up test data...")
        try:
            # 1. SourcingRecommendation 삭제
            for model, cid in created_ids:
                if model == SourcingRecommendation:
                    obj = db.get(model, cid)
                    if obj: db.delete(obj)
            db.flush()
            
            # 2. SalesAnalytics 삭제 (Product의 자식)
            for model, cid in created_ids:
                if model == SalesAnalytics:
                    obj = db.get(model, cid)
                    if obj: db.delete(obj)
            db.flush()
            
            # 3. OrderItem 삭제
            for model, cid in created_ids:
                if model == OrderItem:
                    obj = db.get(model, cid)
                    if obj: db.delete(obj)
            db.flush()
            
            # 4. Order 삭제
            for model, cid in created_ids:
                if model == Order:
                    obj = db.get(model, cid)
                    if obj: db.delete(obj)
            db.flush()
            
            # 5. ProductOption 및 Product 삭제
            # ProductOption부터 삭제
            for model, cid in created_ids:
                if model == ProductOption:
                    obj = db.get(model, cid)
                    if obj: db.delete(obj)
            db.flush()
            
            for model, cid in created_ids:
                if model == Product:
                    obj = db.get(model, cid)
                    if obj: db.delete(obj)
            
            db.commit()
            print("Cleanup successful.")
        except Exception as e:
            print(f"Cleanup failed: {e}")
            db.rollback()
        db.close()

if __name__ == "__main__":
    asyncio.run(test_precision_sourcing())
