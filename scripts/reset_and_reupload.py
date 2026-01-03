
import asyncio
import logging
import uuid
from sqlalchemy import select, delete
from app.db import SessionLocal
from app.models import MarketAccount, MarketListing, Product, ProductOption, OrderItem
from app.coupang_client import CoupangClient
from app.smartstore_client import SmartStoreClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reset_market")

async def reset_all_markets():
    db = SessionLocal()
    try:
        # 1. 활성 마켓 계정 조회
        accounts = db.execute(select(MarketAccount).where(MarketAccount.is_active == True)).scalars().all()
        logger.info(f"Found {len(accounts)} active market accounts.")

        for acc in accounts:
            logger.info(f"Processing account: {acc.name} ({acc.market_code})")
            
            # 클라이언트 초기화
            client = None
            if acc.market_code == "COUPANG":
                creds = acc.credentials or {}
                client = CoupangClient(
                    access_key=str(creds.get("access_key") or ""),
                    secret_key=str(creds.get("secret_key") or ""),
                    vendor_id=str(creds.get("vendor_id") or "")
                )
            elif acc.market_code == "SMARTSTORE":
                creds = acc.credentials or {}
                client = SmartStoreClient(
                    client_id=str(creds.get("client_id") or ""),
                    client_secret=str(creds.get("client_secret") or "")
                )

            if not client:
                logger.warning(f"No client or invalid credentials for market code: {acc.market_code}")
                continue

            # 해당 계정의 리스팅 조회
            listings = db.execute(
                select(MarketListing).where(MarketListing.market_account_id == acc.id)
            ).scalars().all()
            logger.info(f"Found {len(listings)} listings for {acc.name}")

            for listing in listings:
                try:
                    logger.info(f"Processing deletion for listing {listing.market_item_id} from {acc.market_code}...")
                    if acc.market_code == "COUPANG":
                        # 쿠팡 삭제 API (판매 중인 경우 실패할 수 있으므로 상태 변경 검토 필요)
                        status, resp = client.delete_product(listing.market_item_id)
                        if status in (200, 204, 404):
                            logger.info(f"Successfully deleted {listing.market_item_id} from Coupang.")
                        else:
                            # 삭제 실패 시 판매 중지로 변경 시도 (옵션)
                            logger.warning(f"Could not delete {listing.market_item_id}, it might be active. Forcing DB removal.")
                    
                    elif acc.market_code == "SMARTSTORE":
                        # 스마트스토어 삭제 API
                        status, resp = client.delete_product(listing.market_item_id)
                        if status in (200, 204, 404):
                            logger.info(f"Successfully deleted {listing.market_item_id} from SmartStore.")
                        else:
                            logger.warning(f"Could not delete {listing.market_item_id} from SmartStore. Forcing DB removal.")

                    # 실물 마켓 상태와 관계 없이 DB에서는 제거하여 초기화 상태 만듦
                    db.delete(listing)
                    db.commit()
                except Exception as e:
                    logger.error(f"Error processing listing {listing.market_item_id}: {e}")
                    db.rollback()

        # 2. 로컬 상품 데이터 정리 (나중에 재소싱을 위해)
        logger.info("Cleaning up local product data...")
        # 기존 상품과 연결된 주문 항목들의 관계 끊기 (또는 무시)
        # 여기서는 상품 관련 테이블만 정리
        db.execute(delete(ProductOption))
        db.execute(delete(MarketListing)) # 이미 위에서 지웠지만 한 번 더 확인
        db.execute(delete(Product))
        db.commit()
        
        logger.info("Market reset completed successfully.")

    except Exception as e:
        logger.error(f"Global reset error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(reset_all_markets())
