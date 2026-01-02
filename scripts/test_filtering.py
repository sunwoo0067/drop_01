import uuid
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.services.sourcing_service import SourcingService
from app.models import SourcingCandidate, SupplierRawFetchLog

def test_filtering():
    with SessionLocal() as session:
        service = SourcingService(session)
        
        # Test 1: Forbidden keyword
        raw_item = {
            "item_name": "리튬 배터리 팩 2500mAh",
            "item_id": f"TEST_{uuid.uuid4()}",
            "supplier_id": "OWNERCLAN"
        }
        
        print(f"Testing forbidden item: {raw_item['item_name']}")
        service.import_from_raw([raw_item], strategy="benchmark")
        
        candidate = session.query(SourcingCandidate).filter(SourcingCandidate.supplier_item_id == raw_item["item_id"]).first()
        if candidate:
            print("❌ FAILED: Forbidden item was imported.")
        else:
            print("✅ SUCCESS: Forbidden item was filtered out.")

        # Test 2: Normal item
        raw_item_2 = {
            "item_name": "예쁜 머그컵",
            "item_id": f"TEST_{uuid.uuid4()}",
            "supplier_id": "OWNERCLAN"
        }
        print(f"Testing normal item: {raw_item_2['item_name']}")
        service.import_from_raw([raw_item_2], strategy="benchmark")
        
        candidate_2 = session.query(SourcingCandidate).filter(SourcingCandidate.supplier_item_id == raw_item_2["item_id"]).first()
        if candidate_2:
            print("✅ SUCCESS: Normal item was imported.")
            session.delete(candidate_2)
            session.commit()
        else:
            print("❌ FAILED: Normal item was filtered out.")

if __name__ == "__main__":
    test_filtering()
