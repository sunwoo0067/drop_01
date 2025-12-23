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

import concurrent.futures

import time
import random

def delete_single_listing(listing_id, market_account_id, market_item_id, idx, total):
    logger.info(f"[{idx}/{total}] 삭제 시도: {market_item_id}")
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            with SessionLocal() as session:
                success, error_msg = delete_product_from_coupang(
                    session, 
                    market_account_id, 
                    market_item_id
                )
                
                if success:
                    logger.info(f" -> 삭제 완료 (listing_id={listing_id})")
                    return True
                
                if "429" in str(error_msg):
                    wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f" -> 429 Too Many Requests 발생. {wait_time:.2f}초 후 재시도... (시도 {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(f" -> API 삭제 실패 ({error_msg}). DB 강제 정리를 진행합니다.")
                    session.execute(delete(MarketListing).where(MarketListing.id == listing_id))
                    session.commit()
                    return True
                    
        except Exception as e:
            if "429" in str(e):
                wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f" -> 429 에러 발생. {wait_time:.2f}초 후 재시도...")
                time.sleep(wait_time)
                continue
            logger.error(f" -> 오류 발생 ({market_item_id}): {e}")
            return False

    # 모든 재시도 실패 시 DB 강제 정리
    with SessionLocal() as session:
        logger.warning(f" -> 모든 재시도 실패. DB 강제 정리를 진행합니다. ({market_item_id})")
        session.execute(delete(MarketListing).where(MarketListing.id == listing_id))
        session.commit()
    return True

def delete_all():
    with SessionLocal() as session:
        listings = session.execute(select(MarketListing)).scalars().all()
        total = len(listings)
        
        if total == 0:
            logger.info("삭제할 상품이 없습니다.")
            return

        logger.info(f"총 {total}개의 상품 삭제를 시작합니다. (멀티스레드 적용, max_workers=3)")
        
        listing_data = [
            (l.id, l.market_account_id, l.market_item_id, i, total) 
            for i, l in enumerate(listings, 1)
        ]

    success_count = 0
    fail_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(delete_single_listing, *data) for data in listing_data]
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1
            else:
                fail_count += 1
                
    logger.info(f"최종 결과 - 전체: {total}, 성공: {success_count}, 실패: {fail_count}")

if __name__ == "__main__":
    delete_all()
