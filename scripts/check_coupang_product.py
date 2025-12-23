import os
import json
import asyncio
from dotenv import load_dotenv
from app.coupang_client import CoupangClient

async def check_product():
    load_dotenv()
    
    # .env에서 마켓 계정 정보 읽기 (임시로 첫 번째 혹은 명시된 계정 사용)
    # 실제로는 DB에서 market_account 정보를 가져와야 하지만, 빠른 확인을 위해 .env와 DB를 활용
    
    access_key = os.getenv("COUPANG_ACCESS_KEY")
    secret_key = os.getenv("COUPANG_SECRET_KEY")
    vendor_id = os.getenv("COUPANG_VENDOR_ID")
    
    # 만약 .env에 없으면 DB에서 직접 가져오기 시도 (여기서는 우선 client 초기화 로직 확인)
    # market_listings 테이블에서 확인한 market_account_id: a7fbd9b3-758f-4060-858c-581f32ff1d7c
    
    # 임시 자격 증명 (DB 조회를 통해 가져오는 것이 정확함)
    import psycopg
    conn = psycopg.connect("postgresql://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434")
    with conn.cursor() as cur:
        cur.execute("SELECT credentials FROM market_accounts WHERE id = 'a7fbd9b3-758f-4060-858c-581f32ff1d7c'")
        row = cur.fetchone()
        if row:
            creds = row[0]
            access_key = creds.get("access_key")
            secret_key = creds.get("secret_key")
            vendor_id = creds.get("vendor_id")

    if not all([access_key, secret_key, vendor_id]):
        print("Error: Missing Coupang credentials.")
        return

    client = CoupangClient(access_key, secret_key, vendor_id)
    
    import sys
    seller_product_id = sys.argv[1] if len(sys.argv) > 1 else "15934785975"
    print(f"Fetching product {seller_product_id}...")
    
    code, data = client.get_product(seller_product_id)
    
    if code == 200:
        print("Successfully fetched product from Coupang:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Failed to fetch product. Code: {code}")
        print(data)

if __name__ == "__main__":
    asyncio.run(check_product())
