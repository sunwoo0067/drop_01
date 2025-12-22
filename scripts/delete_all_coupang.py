import sys
import os
import uuid
import logging
from sqlalchemy import select, delete

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import MarketListing
from app.coupang_sync import delete_product_from_coupang

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("delete_all_coupang")

def delete_all():
    with SessionLocal() as session:
        listings = session.execute(select(MarketListing)).scalars().all()
        total = len(listings)
        
        if total == 0:
            logger.info("삭제할 상품이 없습니다.")
            return

        logger.info(f"총 {total}개의 상품 삭제를 시작합니다.")
        
        success_count = 0
        fail_count = 0
        
        for idx, listing in enumerate(listings, 1):
            logger.info(f"[{idx}/{total}] 삭제 시도: {listing.market_item_id}")
            
            try:
                # 1단계: API 삭제 시도 (판매중지 포함)
                success, error_msg = delete_product_from_coupang(
                    session, 
                    listing.market_account_id, 
                    listing.market_item_id
                )
                
                # API 삭제 실패 시 (특히 상태 오류 등), 로컬 DB라도 강제 정리
                if not success:
                    logger.warning(f" -> API 삭제 실패 ({error_msg}). DB 강제 정리를 진행합니다.")
                    session.execute(delete(MarketListing).where(MarketListing.id == listing.id))
                    session.commit()
                
                success_count += 1
                logger.info(f" -> 삭제 완료 (listing_id={listing.id})")
                
            except Exception as e:
                logger.error(f" -> 오류 발생 ({listing.market_item_id}): {e}")
                fail_count += 1
                
        logger.info(f"최종 결과 - 전체: {total}, 성공: {success_count}, 실패: {fail_count}")

if __name__ == "__main__":
    delete_all()
