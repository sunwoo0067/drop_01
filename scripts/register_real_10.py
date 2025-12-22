import asyncio
import os
import json
import uuid
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import Product, MarketListing, MarketAccount
from app.coupang_client import CoupangClient
from app.services.name_processing import apply_market_name_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def register_real_10_final_db_fix():
    load_dotenv()
    
    market_engine = create_engine("postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434")
    MarketSession = sessionmaker(bind=market_engine)
    
    import psycopg
    source_conn = psycopg.connect("postgresql://sunwoo@/drop01_source?host=/var/run/postgresql&port=5434")
    raw_products = []
    with source_conn.cursor() as cur:
        # 배송 지옥 탈출 성공 후, 새로운 10개 상품 시도 (OFFSET 520)
        cur.execute("SELECT supplier_code, item_code, raw FROM supplier_item_raw WHERE supplier_code = 'ownerclan' OFFSET 520 LIMIT 10;")
        rows = cur.fetchall()
        for r in rows:
            raw_products.append({"supplier": r[0], "item_code": r[1], "raw": r[2]})
    source_conn.close()

    if not raw_products:
        print("No raw products found.")
        return

    mk_session = MarketSession()
    try:
        account = mk_session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        creds = account.credentials
        account_id = account.id
    finally:
        mk_session.close()

    client = CoupangClient(creds['access_key'], creds['secret_key'], creds['vendor_id'])
    
    outbound_code = 17903308
    return_code = 1001670198
    
    registered_count = 0
    for item in raw_products:
        raw = item['raw']
        item_code = item['item_code']
        print(f"Processing: {raw.get('name')} ({item_code})")
        
        try:
            processed_name = apply_market_name_rules(raw.get('name'))
            main_image_url = raw.get('images', [""])[0]
            if main_image_url.startswith("http://"):
                main_image_url = main_image_url.replace("http://", "https://")
            
            category_code = int(raw.get('metadata', {}).get('coupangCategoryCode', 78786))
            
            notices = [
                {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "품명 및 모델명", "content": "상세페이지 참조"},
                {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "인증/허가 사항", "content": "상세페이지 참조"},
                {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조국(원산지)", "content": "상세페이지 참조"},
                {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "제조자(수입자)", "content": "상세페이지 참조"},
                {"noticeCategoryName": "기타 재화", "noticeCategoryDetailName": "소비자상담 관련 전화번호", "content": "상세페이지 참조"}
            ]

            payload = {
                "displayCategoryCode": category_code,
                "sellerProductName": processed_name,
                "vendorId": creds['vendor_id'],
                "saleStartedAt": "2024-12-25T00:00:00",
                "saleEndedAt": "2099-12-31T23:59:59",
                "displayProductName": processed_name,
                "brand": "기타",
                "manufacture": "기타",
                "deliveryMethod": "SEQUENCIAL", 
                "deliveryCompanyCode": "CJGLS",
                "deliveryChargeType": "FREE",
                "deliveryCharge": 0,
                "freeShipOverAmount": 0,
                "deliveryChargeOnReturn": 5000,
                "remoteAreaDeliverable": "Y",
                "bundlePackingDelivery": 0,
                "unionDeliveryType": "NOT_UNION_DELIVERY",
                "returnCenterCode": str(return_code),
                "outboundShippingPlaceCode": outbound_code,
                "returnZipCode": "14598",
                "returnAddress": "경기도 부천시 원미구 부일로199번길 21",
                "returnAddressDetail": "401 슈가맨워크",
                "companyContactNumber": "070-4581-8906",
                "returnChargeName": "송내 반품",
                "returnCharge": 5000,
                "vendorUserId": creds.get("vendor_user_id"),
                "requested": True,
                "items": [{
                    "itemName": "단일상품",
                    "originalPrice": (int(raw.get('price', 10000) * 1.5) // 10) * 10,
                    "salePrice": (int(raw.get('price', 10000) * 1.3) // 10) * 10,
                    "maximumBuyCount": 9999,
                    "maximumBuyForPerson": 0,
                    "maximumBuyForPersonPeriod": 1,
                    "outboundShippingTimeDay": 3,
                    "unitCount": 1,
                    "adultOnly": "EVERYONE",
                    "taxType": "TAX",
                    "parallelImported": "NOT_PARALLEL_IMPORTED",
                    "overseasPurchased": "NOT_OVERSEAS_PURCHASED",
                    "externalVendorSku": item_code,
                    "emptyBarcode": True,
                    "emptyBarcodeReason": "NONE",
                    "modelNo": item_code,
                    "remoteAreaDeliverable": "Y",
                    "images": [{"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": main_image_url}],
                    "contents": [{
                        "contentsType": "HTML",
                        "contentDetails": [{"content": raw.get('content', "상세이미지 참조"), "detailType": "TEXT"}]
                    }],
                    "attributes": [
                        {"attributeTypeName": "개당 용량", "attributeValueName": "1"},
                        {"attributeTypeName": "개당 중량", "attributeValueName": "1"},
                        {"attributeTypeName": "수량", "attributeValueName": "1"}
                    ],
                    "notices": notices,
                    "certifications": []
                }]
            }

            code, data = client.create_product(payload)
            if code in [200, 201] and data.get("code") == "SUCCESS":
                seller_product_id = str(data.get("data") or data.get("sellerProductId"))
                print(f"Successfully registered: {seller_product_id}")
                
                # DB 업데이트 (MarketListing 필드 교정)
                mk_session = MarketSession()
                try:
                    new_listing = MarketListing(
                        product_id=uuid.uuid4(), # 임시 UUID (연결된 Product가 없으므로)
                        market_account_id=account_id,
                        market_item_id=seller_product_id,
                        status="ACTIVE",
                        coupang_status="APPROVED"
                    )
                    mk_session.add(new_listing)
                    mk_session.commit()
                except Exception as db_e:
                    print(f"DB update failed for {item_code}: {db_e}")
                finally:
                    mk_session.close()
                
                registered_count += 1
            else:
                print(f"Failed product {item_code}: {data.get('message')}")
                
        except Exception as e:
            print(f"Exception for {item_code}: {e}")

    print(f"Final total registered: {registered_count}")

if __name__ == "__main__":
    asyncio.run(register_real_10_final_db_fix())
