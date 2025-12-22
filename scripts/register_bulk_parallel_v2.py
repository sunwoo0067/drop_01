import asyncio
import uuid
import logging
import sys
import time
import random

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
        logging.FileHandler("register_1000_v2.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 동시 요청 제한 (안정성을 위해 10 -> 5로 하향 보정)
MAX_CONCURRENCY = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

async def process_single_product_with_retry(c_info, account_id, max_retries=3):
    """429 에러 시 재시도 로직이 포함된 개별 상품 등록 프로세스"""
    async with semaphore:
        for attempt in range(max_retries + 1):
            start_time = time.time()
            if attempt > 0:
                # 429 회피를 위한 지터(Jitter) 포함 백오프
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"재시도 {attempt}/{max_retries}: {c_info['id']} ({wait_time:.1f}초 대기)")
                await asyncio.sleep(wait_time)
            
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, sync_register_wrapper, c_info, account_id)
                
                elapsed = time.time() - start_time
                if result['ok']:
                    logger.info(f"성공: {c_info['id']} (시도: {attempt+1}, {elapsed:.2f}초)")
                    return result
                else:
                    # 429 에러인 경우 재시도 대상으로 간주
                    if "429" in str(result['error']):
                        continue
                    
                    logger.error(f"실패: {c_info['id']} - {result['error']} ({elapsed:.2f}초)")
                    return result
                    
            except Exception as e:
                logger.exception(f"예외 발생: {c_info['id']} - {str(e)}")
                if attempt == max_retries:
                    return {"ok": False, "error": str(e), "id": c_info["id"]}
                continue
                
        return {"ok": False, "error": "Max retries exceeded (likely 429)", "id": c_info["id"]}

def sync_register_wrapper(c_info, account_id):
    """기존 동기 로직을 래핑하여 스레드 풀에서 실행 가능하도록 함"""
    with SessionLocal() as session:
        try:
            raw_item = (
                session.query(SupplierItemRaw)
                .filter(SupplierItemRaw.supplier_code == c_info["supplier_code"])
                .filter(SupplierItemRaw.item_code == c_info["item_code"])
                .first()
            )
            if not raw_item:
                return {"ok": False, "error": "Raw item not found", "id": c_info["id"]}

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

            product.processed_name = apply_market_name_rules(product.name)
            session.commit()

            ok, err = register_product(session, account_id, product.id)
            if not ok:
                return {"ok": False, "error": err, "id": c_info["id"]}

            session.query(SourcingCandidate).filter(
                SourcingCandidate.id == c_info["id"]
            ).update({"status": "APPROVED"})
            session.commit()
            
            return {"ok": True, "id": c_info["id"]}
        except Exception as e:
            session.rollback()
            return {"ok": False, "error": str(e), "id": c_info["id"]}

async def register_1000_parallel_v2(target_count=1000):
    logger.info(f"V2: 1,000개 상품 대량 등록 시작 (목표: {target_count}, 병렬도: {MAX_CONCURRENCY})")
    
    # 1. 후보 선별 (충분한 풀을 확보)
    query = """
        select id, supplier_code, supplier_item_id, name, supply_price
        from sourcing_candidates
        where status = 'PENDING'
        order by created_at desc
        limit 5000
    """
    with dropship_engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    
    items = []
    seen_names = set()
    for row in rows:
        name_short = row.name[:12]
        if name_short not in seen_names:
            items.append(row)
            seen_names.add(name_short)
        if len(items) >= target_count:
            break
            
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

    # 3. 비동기 테스크 실행
    tasks = [process_single_product_with_retry(c, account_id) for c in candidate_data]
    results = await asyncio.gather(*tasks)

    # 4. 결과 요약
    success_count = sum(1 for r in results if r['ok'])
    fail_count = len(results) - success_count
    
    logger.info("=" * 50)
    logger.info("최종 작업 요약 (V2)")
    logger.info(f"  - 목표: {target_count}")
    logger.info(f"  - 성공: {success_count}")
    logger.info(f"  - 실패: {fail_count}")
    logger.info("=" * 50)

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    asyncio.run(register_1000_parallel_v2(count))
