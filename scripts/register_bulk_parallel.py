import asyncio
import uuid
import logging
import sys
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal, dropship_engine
from app.models import Product, SourcingCandidate, SupplierItemRaw, MarketAccount
from app.coupang_sync import register_product
from app.services.name_processing import apply_market_name_rules

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("register_1000.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 동시 요청 제한 (쿠팡 API 부하 조절)
MAX_CONCURRENCY = 10
semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

async def process_single_product(c_info, account_id):
    """개별 상품 등록 프로세스 (비동기)"""
    async with semaphore:
        start_time = time.time()
        logger.info(f"시작: [{c_info['name'][:30]}...] (ID: {c_info['id']})")
        
        try:
            # 동기 DB 작업을 위해 run_in_executor 사용 고려 대신 간단히 별도 세션 사용
            # 실제 I/O가 발생하는 register_product 등은 내부적으로 동기일 수 있음
            # 여기서는 비동기 컨텍스트에서 안전하게 처리하기 위해 루프 내에서 세션 관리
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, sync_register_wrapper, c_info, account_id)
            
            elapsed = time.time() - start_time
            if result['ok']:
                logger.info(f"성공: {c_info['id']} ({elapsed:.2f}초)")
            else:
                logger.error(f"실패: {c_info['id']} - {result['error']} ({elapsed:.2f}초)")
            
            return result
        except Exception as e:
            logger.exception(f"예외 발생: {c_info['id']} - {str(e)}")
            return {"ok": False, "error": str(e), "id": c_info["id"]}

def sync_register_wrapper(c_info, account_id):
    """기존 동기 로직을 래핑하여 스레드 풀에서 실행 가능하도록 함"""
    with SessionLocal() as session:
        try:
            # 1. Raw Item 확인
            raw_item = (
                session.query(SupplierItemRaw)
                .filter(SupplierItemRaw.supplier_code == c_info["supplier_code"])
                .filter(SupplierItemRaw.item_code == c_info["item_code"])
                .first()
            )
            if not raw_item:
                return {"ok": False, "error": "Raw item not found", "id": c_info["id"]}

            # 2. Product 생성/조회
            product = (
                session.query(Product)
                .filter(Product.supplier_item_id == raw_item.id)
                .first()
            )
            if not product:
                detail_html = ""
                raw = raw_item.raw if isinstance(raw_item.raw, dict) else {}
                for key in ("detail_html", "detailHtml", "content", "description"):
                    val = raw.get(key)
                    if isinstance(val, str) and val.strip():
                        detail_html = val.strip()
                        break

                product = Product(
                    id=uuid.uuid4(),
                    supplier_item_id=raw_item.id,
                    name=c_info["name"],
                    cost_price=c_info["price"],
                    selling_price=int(c_info["price"] * 1.5),
                    status="ACTIVE",
                    processing_status="PENDING",
                    description=detail_html,
                )
                session.add(product)
                session.commit()
                session.refresh(product)

            # 3. 상품명 정규화 및 업데이트
            product.processed_name = apply_market_name_rules(product.name)
            session.commit()

            # 4. 쿠팡 등록
            ok, err = register_product(session, account_id, product.id)
            if not ok:
                return {"ok": False, "error": err, "id": c_info["id"]}

            # 5. 상태 업데이트
            session.query(SourcingCandidate).filter(
                SourcingCandidate.id == c_info["id"]
            ).update({"status": "APPROVED"})
            session.commit()
            
            return {"ok": True, "id": c_info["id"]}
        except Exception as e:
            session.rollback()
            return {"ok": False, "error": str(e), "id": c_info["id"]}

async def register_1000_parallel(target_count=1000):
    logger.info(f"1,000개 상품 대량 등록 시작 (목표: {target_count}, 병렬도: {MAX_CONCURRENCY})")
    
    # 1. 후보 선별 (다양성 로직 포함)
    query = """
        select id, supplier_code, supplier_item_id, name, supply_price
        from sourcing_candidates
        where status = 'PENDING'
        order by created_at desc
        limit 3000
    """
    with dropship_engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    
    items = []
    seen_names = set()
    for row in rows:
        name_short = row.name[:12] # 조금 더 정교한 다양성 체크
        if name_short not in seen_names:
            items.append(row)
            seen_names.add(name_short)
        if len(items) >= target_count:
            break
            
    # 부족하면 채우기
    if len(items) < target_count:
        for row in rows:
            if row not in items:
                items.append(row)
            if len(items) >= target_count:
                break
                
    candidate_data = [
        {
            "id": row.id,
            "name": row.name,
            "price": row.supply_price,
            "item_code": row.supplier_item_id,
            "supplier_code": row.supplier_code,
        }
        for row in items
    ]

    if not candidate_data:
        logger.error("등록 가능한 후보를 찾을 수 없습니다.")
        return

    logger.info(f"선별 완료: {len(candidate_data)}개 상품")

    # 2. 쿠팡 계정 로드
    with SessionLocal() as session:
        account = session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account:
            logger.error("쿠팡 계정을 찾을 수 없습니다.")
            return
        account_id = account.id

    # 3. 병렬 처리 실행
    tasks = [process_single_product(c, account_id) for c in candidate_data]
    results = await asyncio.gather(*tasks)

    # 4. 결과 요약
    success_count = sum(1 for r in results if r['ok'])
    fail_count = len(results) - success_count
    
    logger.info("=" * 50)
    logger.info("최종 작업 요약")
    logger.info(f"  - 목표: {target_count}")
    logger.info(f"  - 성공: {success_count}")
    logger.info(f"  - 실패: {fail_count}")
    logger.info("=" * 50)

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    asyncio.run(register_1000_parallel(count))
