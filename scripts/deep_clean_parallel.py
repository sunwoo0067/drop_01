
import asyncio
import logging
import sys
from sqlalchemy import select
from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
from app.coupang_client import CoupangClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("deep_clean_parallel")

# API 속도 제한을 고려하여 동시성 제어 (동시 15개 상품 처리)
SEMAPHORE = asyncio.Semaphore(15)

stats = {
    "total_fetched": 0,
    "stop_sales_success": 0,
    "stop_sales_failure": 0,
    "delete_success": 0,
    "delete_failure": 0,
}

async def process_product(client: CoupangClient, item: dict):
    spid = str(item.get("sellerProductId"))
    async with SEMAPHORE:
        try:
            # 1. 상세 정보 조회하여 vendorItemId 확보
            status_d, data_d = client.get_product(spid)
            if status_d == 200:
                # Coupang API returns product detail under "data" key
                product_data = data_d.get("data", {})
                sub_items = product_data.get("items", [])
                
                if not sub_items:
                    logger.info(f"[{spid}] No sub-items found in product data.")
                
                for sub in sub_items:
                    vid = str(sub.get("vendorItemId"))
                    logger.info(f"[{spid}] Stopping sales for Vendor Item ID: {vid}")
                    s_status, s_data = client.stop_sales(vid)
                    if s_status in (200, 204):
                        stats["stop_sales_success"] += 1
                        logger.info(f"[{spid}] Successfully stopped sales for {vid}")
                    else:
                        logger.warning(f"[{spid}] Failed to stop sales for {vid}: {s_status} {s_data}")
                        stats["stop_sales_failure"] += 1
            else:
                logger.warning(f"[{spid}] Failed to get product details (Status: {status_d}). Raw: {data_d}")

            # 2. 삭제 시도
            del_status, del_resp = client.delete_product(spid)
            if del_status in (200, 204, 404):
                logger.info(f"[{spid}] Successfully deleted.")
                stats["delete_success"] += 1
                return True
            else:
                # 400 에러는 보통 이미 승인된 상품이라 삭제가 불가한 경우 (판매중지만 가능)
                logger.warning(f"[{spid}] Could not delete (Status: {del_status}). Response: {del_resp}")
                stats["delete_failure"] += 1
                return False
        except Exception as e:
            logger.error(f"[{spid}] Unexpected Error: {e}")
            return False

async def deep_clean_parallel(account_name: str):
    db = SessionLocal()
    try:
        acc = db.execute(select(MarketAccount).where(MarketAccount.name == account_name)).scalar_one_or_none()
        if not acc:
            logger.error(f"Account {account_name} not found.")
            return

        creds = acc.credentials or {}
        client = CoupangClient(
            access_key=str(creds.get("access_key") or ""),
            secret_key=str(creds.get("secret_key") or ""),
            vendor_id=str(creds.get("vendor_id") or "")
        )

        logger.info(f"Starting PARALLEL deep clean for {account_name} (Vendor: {acc.credentials.get('vendor_id')})...")

        next_token = ""
        
        while True:
            logger.info(f"Fetching batch (nextToken: {next_token})...")
            status, data = client.get_products(next_token=next_token if next_token else None, max_per_page=100)
            
            if status != 200:
                logger.error(f"Failed to fetch products: {status} {data}")
                break
            
            items = data.get("data", [])
            if not items:
                logger.info("No more products found.")
                break
            
            stats["total_fetched"] += len(items)
            
            tasks = [process_product(client, item) for item in items]
            await asyncio.gather(*tasks)
            
            logger.info(f"--- Stats so far: {stats} ---")

            next_token = data.get("nextToken")
            if not next_token:
                break
            
            await asyncio.sleep(0.5)
        
        # Local DB cleanup
        logger.info(f"Cleaning local MarketListing records for {account_name}...")
        db.execute(
            MarketListing.__table__.delete().where(MarketListing.market_account_id == acc.id)
        )
        db.commit()
        
        logger.info(f"Deep clean finished. Final Stats: {stats}")

    except Exception as e:
        logger.error(f"Error during deep clean: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "c쿠팡"
    asyncio.run(deep_clean_parallel(name))
