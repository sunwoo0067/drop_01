import asyncio
import uuid
import logging
import sys

from sqlalchemy import text

from app.db import SessionLocal, dropship_engine
from app.models import Product, SourcingCandidate, SupplierItemRaw, MarketAccount
from app.coupang_sync import register_product
from app.services.name_processing import apply_market_name_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def register_top_10(keyword: str = None):
    # 1. 후보 선별
    keyword_pattern = f"%{keyword}%" if keyword else None
    query = """
        select id, supplier_code, supplier_item_id, name, supply_price
        from sourcing_candidates
        where status = :status
    """
    params = {"status": "PENDING"}
    if keyword:
        query += " and name like :keyword_pattern"
        params["keyword_pattern"] = keyword_pattern
    
    query += " order by created_at desc limit 20"

    with dropship_engine.connect() as conn:
        rows = conn.execute(text(query), params).all()
    # Diversity: pick first 10, but try to avoid duplicates if possible
    items = []
    seen_names = set()
    for row in rows:
        name_short = row.name[:10] # simple heuristic
        if name_short not in seen_names:
            items.append(row)
            seen_names.add(name_short)
        if len(items) >= 10:
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
        print("No candidates found.")
        return

    # 2. 쿠팡 계정 정보 로드
    with SessionLocal() as session:
        account = session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account:
            print("No Coupang account found.")
            return
        account_id = account.id
    registered_count = 0
    
    for c_info in candidate_data:
        print(f"Processing candidate: {c_info['name']} ({c_info['id']})")
        try:
            with SessionLocal() as session:
                raw_item = (
                    session.query(SupplierItemRaw)
                    .filter(SupplierItemRaw.supplier_code == c_info["supplier_code"])
                    .filter(SupplierItemRaw.item_code == c_info["item_code"])
                    .first()
                )
                if not raw_item:
                    print(f"Raw item not found for candidate {c_info['id']}")
                    continue

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
                    print(f"Failed to register product: {err}")
                    continue

                session.query(SourcingCandidate).filter(
                    SourcingCandidate.id == c_info["id"]
                ).update({"status": "APPROVED"})
                session.commit()
                registered_count += 1
        except Exception as e:
            print(f"Exception while processing {c_info['id']}: {e}")

    print(f"Final registered count: {registered_count}")

if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(register_top_10(kw))
