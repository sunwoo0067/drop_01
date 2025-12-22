import asyncio
import os
import json
import uuid
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import Product, MarketListing, MarketAccount
from app.coupang_client import CoupangClient
from app.services.name_processing import apply_market_name_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.coupang_sync import register_product

async def register_real_10_refactored():
    load_dotenv()
    
    # 통합 데이터베이스 drop01 사용
    db_url = "postgresql+psycopg://sunwoo@/drop01?host=/var/run/postgresql&port=5434"
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    
    import psycopg
    source_conn = psycopg.connect("postgresql://sunwoo@/drop01?host=/var/run/postgresql&port=5434")
    raw_products = []
    with source_conn.cursor() as cur:
        # 새로운 10개 상품 시도 (OFFSET 600)
        cur.execute("SELECT id, supplier_code, item_code, raw FROM supplier_item_raw WHERE supplier_code = 'ownerclan' OFFSET 610 LIMIT 10;")
        rows = cur.fetchall()
        for r in rows:
            raw_products.append({"raw_id": r[0], "supplier": r[1], "item_code": r[2], "raw": r[3]})
    source_conn.close()

    if not raw_products:
        print("No raw products found.")
        return

    session = SessionLocal()
    try:
        account = session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account:
            print("Coupang account not found.")
            return
        account_id = account.id
        
        registered_count = 0
        for item in raw_products:
            raw = item['raw']
            item_code = item['item_code']
            raw_id = item['raw_id']
            print(f"Processing: {raw.get('name')} ({item_code})")
            
            # 1. Product 레코드 확보 또는 생성
            # Logically we should have a product ID, but here we create/update one
            product = session.query(Product).filter(Product.supplier_item_id == raw_id).first()
            if not product:
                product = Product(
                    id=uuid.uuid4(),
                    supplier_item_id=raw_id,
                    name=raw.get('name'),
                    brand=raw.get('brand', '기타'),
                    description=raw.get('content') or raw.get('description'),
                    cost_price=int(raw.get('price', 0)),
                    selling_price=(int(raw.get('price', 0) * 1.3)),
                    status="ACTIVE",
                    processing_status="COMPLETED"
                )
                session.add(product)
            
            # 정보 보강 (테스트 목적이므로 강제 업데이트)
            product.processed_name = apply_market_name_rules(raw.get('name'))
            main_image_url = raw.get('images', [""])[0]
            if main_image_url.startswith("http://"):
                main_image_url = main_image_url.replace("http://", "https://")
            
            product.processed_image_urls = [main_image_url]
            product.description = raw.get('content', "상세이미지 참조")
            
            session.commit()
            
            # 2. 중앙화된 register_product 호출
            success, error = register_product(session, account_id, product.id)
            
            if success:
                print(f"Successfully registered via service: {item_code}")
                registered_count += 1
            else:
                print(f"Failed to register {item_code}: {error}")
                
        print(f"Final total registered: {registered_count}")
        
    except Exception as e:
        print(f"Global Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(register_real_10_refactored())
