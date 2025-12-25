import asyncio
import uuid
from sqlalchemy import select
from app.session_factory import session_factory
from app.models import MarketAccount, Product
from app.smartstore_sync import register_smartstore_product

async def test_naver_registration():
    with session_factory() as session:
        # 1. 네이버 계정 찾기
        acc = session.execute(
            select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE", MarketAccount.is_active == True)
        ).scalars().first()
        
        if not acc:
            print("활성 네이버 계정을 찾을 수 없습니다.")
            return

        # 2. 특정 테스트 상품 사용 (이미지가 있는 상품)
        product_id = "97885b3d-5d36-43c1-996d-04b0e54f1398"
        product = session.get(Product, product_id)
        
        if not product:
            print(f"상품 {product_id}를 찾을 수 없습니다. 최근 상품으로 대체합니다.")
            product = session.execute(
                select(Product).order_by(Product.created_at.desc())
            ).scalars().first()
        
        if not product:
            print("등록할 상품이 없습니다.")
            return

        print(f"네이버 계정 {acc.name}에 상품 {product.name} 등록 테스트 시작...")
        result = register_smartstore_product(session, acc.id, product.id)
        print(f"결과: {result}")

if __name__ == "__main__":
    asyncio.run(test_naver_registration())
