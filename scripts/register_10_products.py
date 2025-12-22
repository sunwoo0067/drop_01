import asyncio
import os
import json
import uuid
import logging
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from app.models import Product, SourcingCandidate, SupplierItemRaw, MarketListing, MarketAccount
from app.services.coupang_ready_service import ensure_product_ready_for_coupang
from app.coupang_client import CoupangClient
from app.services.name_processing import apply_market_name_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def register_top_10():
    load_dotenv()
    
    # DB 엔진 설정 (세션 관리를 위해 전역적으로 설정)
    dropship_engine = create_engine("postgresql+psycopg://sunwoo@/drop01_dropship?host=/var/run/postgresql&port=5434")
    market_engine = create_engine("postgresql+psycopg://sunwoo@/drop01_market?host=/var/run/postgresql&port=5434")
    
    DropshipSession = sessionmaker(bind=dropship_engine)
    MarketSession = sessionmaker(bind=market_engine)
    
    # 1. 후보 선별 (Dropship DB)
    ds_session = DropshipSession()
    try:
        candidates = ds_session.query(SourcingCandidate).filter(SourcingCandidate.status == 'PENDING').limit(10).all()
        candidate_data = [{"id": c.id, "name": c.name, "price": c.supply_price, "item_id": c.supplier_item_id} for c in candidates]
    finally:
        ds_session.close()

    if not candidate_data:
        print("No candidates found.")
        return

    # 2. 쿠팡 계정 정보 로드 (Market DB)
    mk_session = MarketSession()
    try:
        account = mk_session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account:
            print("No Coupang account found.")
            return
        creds = account.credentials
        account_id = account.id
    finally:
        mk_session.close()

    client = CoupangClient(creds['access_key'], creds['secret_key'], creds['vendor_id'])
    registered_count = 0
    
    for c_info in candidate_data:
        print(f"Processing candidate: {c_info['name']} ({c_info['id']})")
        
        # 각 상품마다 독립적인 세션 사용 (오류 시 다른 상품에 영향 없도록)
        ds_session = DropshipSession()
        mk_session = MarketSession()
        
        try:
            # Product 조회 또는 생성
            product = ds_session.query(Product).filter(Product.supplier_item_id == c_info['id']).first()
            if not product:
                product = Product(
                    id=uuid.uuid4(),
                    supplier_item_id=c_info['id'],
                    name=c_info['name'],
                    cost_price=c_info['price'],
                    selling_price=int(c_info['price'] * 1.5),
                    status="ACTIVE",
                    processing_status="PENDING"
                )
                ds_session.add(product)
                ds_session.commit()
                ds_session.refresh(product)

            # 상품 가공
            # 주의: ensure_product_ready_for_coupang 내부에서 SupplierItemRaw 조회 시 
            # product.supplier_item_id(UUID)로 조회하는데, candidate의 supplier_item_id는 'item_code'(str)일 수 있음.
            # 이 부분은 일단 서비스 로직을 믿고 진행하되 에러 핸들링 강화.
            ready_res = await ensure_product_ready_for_coupang(ds_session, str(product.id), min_images_required=1)
            if not ready_res.get("ok"):
                print(f"Failed to make product ready: {ready_res.get('reason')}")
                continue
            
            ds_session.refresh(product)
            
            # 쿠팡 페이로드
            processed_name = apply_market_name_rules(product.name)
            main_image = product.processed_image_urls[0] if product.processed_image_urls else ""
            
            payload = {
                "displayCategoryCode": 78786,
                "sellerProductName": processed_name,
                "vendorId": creds['vendor_id'],
                "saleStartedAt": "2025-12-22T00:00:00",
                "saleEndedAt": "2099-12-31T23:59:59",
                "displayProductName": processed_name,
                "brand": "기타",
                "manufacture": "기타",
                "deliveryMethod": "AGENT_DELIVERY",
                "deliveryCompanyCode": creds.get("default_delivery_company_code", "KDEXP"),
                "deliveryChargeType": "FREE",
                "deliveryCharge": 0,
                "freeShipOverAmount": 0,
                "deliveryTimeType": "NORMAL",
                "deliveryChargeOnReturn": 3000,
                "returnCenterCode": creds.get("default_return_center_code"),
                "outboundShippingPlaceCode": creds.get("default_outbound_shipping_place_code"),
                "vendorUserId": creds.get("vendor_user_id"),
                "requested": True,
                "items": [{
                    "itemName": "단일상품",
                    "originalPrice": product.selling_price,
                    "salePrice": product.selling_price,
                    "maximumBuyCount": 100,
                    "maximumBuyDays": 1,
                    "unitCount": 1,
                    "adultOnly": "EVERYONE",
                    "taxType": "TAX",
                    "parallelImported": "NOT_PARALLEL_IMPORTED",
                    "overseasPurchased": "NOT_OVERSEAS_PURCHASED",
                    "pccNeeded": False,
                    "externalVendorSku": str(product.id),
                    "barcode": "",
                    "emptyBarcode": True,
                    "emptyBarcodeReason": "NONE",
                    "modelNo": "",
                    "images": [{"imageOrder": 0, "imageType": "REPRESENTATIVE", "vendorPath": main_image}],
                    "contents": [{
                        "contentsType": "HTML",
                        "contentDetails": [{"content": f"<center><img src='{main_image}'></center>", "detailType": "TEXT"}]
                    }],
                    "attributes": [],
                    "notices": [{
                        "noticeDeclarationCode": "etc",
                        "contents": {
                            "품명 및 모델명": processed_name,
                            "법에 의한 인증·허가 등을 받았음을 확인할 수 있는 경우 그에 대한 사항": "N",
                            "제조국(원산지)": "중국/기타",
                            "제조자(수입자)": "기타",
                            "소비자상담 관련 전화번호": "010-0000-0000"
                        }
                    }],
                    "certifications": []
                }]
            }
            
            code, data = client.create_product(payload)
            if code in [200, 201]:
                seller_product_id = str(data.get("data"))
                print(f"Successfully registered: {seller_product_id}")
                
                listing = MarketListing(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    market_account_id=account_id,
                    market_item_id=seller_product_id,
                    status="ACTIVE",
                    coupang_status="IN_REVIEW"
                )
                mk_session.add(listing)
                
                # candidate 상태 업데이트
                ds_session.query(SourcingCandidate).filter(SourcingCandidate.id == c_info['id']).update({"status": "APPROVED"})
                
                ds_session.commit()
                mk_session.commit()
                registered_count += 1
            else:
                print(f"Failed to register product to Coupang: {code} {data}")
                
        except Exception as e:
            print(f"Exception while processing {c_info['id']}: {e}")
            ds_session.rollback()
            mk_session.rollback()
        finally:
            ds_session.close()
            mk_session.close()

    print(f"Final registered count: {registered_count}")

if __name__ == "__main__":
    asyncio.run(register_top_10())
