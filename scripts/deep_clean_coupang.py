
import asyncio
import logging
from sqlalchemy import select
from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
from app.coupang_client import CoupangClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deep_clean_coupang")

async def deep_clean(account_name: str):
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

        logger.info(f"Starting deep clean for {account_name} (Vendor: {acc.credentials.get('vendor_id')})...")

        next_token = ""
        total_deleted = 0
        
        while True:
            logger.info(f"Fetching products (nextToken: {next_token})...")
            status, data = client.get_products(next_token=next_token if next_token else None, max_per_page=50)
            
            if status != 200:
                logger.error(f"Failed to fetch products: {status} {data}")
                break
            
            items = data.get("data", [])
            if not items:
                logger.info("No more products found.")
                break
            
            for item in items:
                spid = str(item.get("sellerProductId"))
                logger.info(f"Processing Seller Product ID: {spid} ...")
                
                # 1. 상세 정보 조회하여 vendorItemId 확보
                status_d, data_d = client.get_product(spid)
                if status_d == 200:
                    sub_items = data_d.get("items", [])
                    for sub in sub_items:
                        vid = str(sub.get("vendorItemId"))
                        logger.info(f"  Stopping sales for Vendor Item ID: {vid} ...")
                        client.stop_sales(vid)
                
                # 2. 삭제 시도
                del_status, del_resp = client.delete_product(spid)
                if del_status in (200, 204, 404):
                    logger.info(f"Successfully deleted {spid}")
                    total_deleted += 1
                else:
                    logger.warning(f"Could not delete {spid} (Status: {del_status}). It is now Stopped.")
                    total_deleted += 1 # Count as processed

            next_token = data.get("nextToken")
            if not next_token:
                break
        
        # 2. Local DB cleanup for this account
        logger.info(f"Cleaning local MarketListing records for {account_name}...")
        db.execute(
            MarketListing.__table__.delete().where(MarketListing.market_account_id == acc.id)
        )
        db.commit()
        
        logger.info(f"Deep clean finished. Total marketplace products deleted: {total_deleted}")

    except Exception as e:
        logger.error(f"Error during deep clean: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "c쿠팡"
    asyncio.run(deep_clean(name))
