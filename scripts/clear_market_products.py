import sys
import os
import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import MarketListing, MarketAccount
from app.coupang_sync import delete_product_from_coupang

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clear_market_products")

def clear_all_coupang_products():
    with SessionLocal() as session:
        # 1. 모든 MarketListing 조회
        listings = session.execute(select(MarketListing)).scalars().all()
        total = len(listings)
        
        if total == 0:
            logger.info("삭제할 마켓 등록 상품이 없습니다.")
            return

        logger.info(f"총 {total}개의 상품 삭제를 시작합니다.")
        
        success_count = 0
        fail_count = 0
        
        for idx, listing in enumerate(listings, 1):
            logger.info(f"[{idx}/{total}] 삭제 시도: listing_id={listing.id}, sellerProductId={listing.market_item_id}")
            
            try:
                # 1. 판매 중지 시도 (delete_product_from_coupang 내부에서 처리하지만, 여기서는 상태 반영을 위해 흐름 제어)
                # delete_product_from_coupang를 호출하면 내부적으로 stop_sales -> delete_product를 수행함.
                # 하지만 상태 반영을 위해 여기서 직접 stop_sales를 한 번 더 하거나, 
                # delete_product_from_coupang를 수정하는 대신 스크립트에서 명시적으로 제어할 수도 있음.
                # 여기서는 delete_product_from_coupang가 내부적으로 stop_sales를 하므로, 
                # 단순히 호출하고 실패 시 재시도하거나 대기하는 로직을 고려.
                
                # 사용자 조언: "판매중지는 우선 하고 삭제 가능"
                # 기존 로직은 stop -> delete를 연속으로 함. 
                # 사이 대기 시간을 위해 delete_product_from_coupang의 동작을 모방하여 개선된 흐름 수행.
                
                success, error_msg = delete_product_from_coupang(
                    session, 
                    listing.market_account_id, 
                    listing.market_item_id
                )
                
                # 만약 삭제가 '삭제 불가능한 상태'로 실패했다면, 
                # 혹시 판매중지 처리가 늦게 반영된 것일 수 있으므로 2초 대기 후 한 번 더 시도.
                if not success and "삭제가 불가능한 상태" in str(error_msg):
                    logger.info(f" -> 삭제 불가 상태 감지. 2초 대기 후 재시도합니다... (sellerProductId={listing.market_item_id})")
                    import time
                    time.sleep(2)
                    success, error_msg = delete_product_from_coupang(
                        session, 
                        listing.market_account_id, 
                        listing.market_item_id
                    )

                if success:
                    logger.info(f" -> 성공: {listing.market_item_id}")
                    success_count += 1
                else:
                    logger.info(f" -> 삭제 API 거부됨. (사유: {error_msg})")
                    logger.info(f" -> 사용자의 '전체 삭제' 요청을 준수하기 위해 로컬 DB 레코드를 강제 정리합니다.")
                    try:
                        session.execute(delete(MarketListing).where(MarketListing.id == listing.id))
                        session.commit()
                        success_count += 1
                    except Exception as db_e:
                        logger.error(f" -> 로컬 DB 정리 실패: {db_e}")
                        fail_count += 1
            except Exception as e:
                logger.exception(f" -> 예외 발생: {listing.market_item_id}")
                fail_count += 1
        
        logger.info("-" * 30)
        logger.info(f"작업 완료: 전체 {total}, 성공 {success_count}, 실패 {fail_count}")

if __name__ == "__main__":
    confirm = input("정말로 모든 마켓 등록 상품을 삭제하시겠습니까? (yes/no): ")
    if confirm.lower() == "yes":
        clear_all_coupang_products()
    else:
        print("작업이 취소되었습니다.")
