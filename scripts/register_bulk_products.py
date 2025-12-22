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

async def register_bulk(keyword: str = None, target_count: int = 10):
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
    
    # 다양성을 위해 목표 수량의 2배를 가져옴
    fetch_limit = target_count * 2
    query += f" order by created_at desc limit {fetch_limit}"

    with dropship_engine.connect() as conn:
        rows = conn.execute(text(query), params).all()
    
    # Diversity: 이름 앞부분 10글자가 겹치지 않게 우선 선별
    items = []
    seen_names = set()
    for row in rows:
        name_short = row.name[:10]
        if name_short not in seen_names:
            items.append(row)
            seen_names.add(name_short)
        if len(items) >= target_count:
            break
    
    # 만약 다양성 필터링 후 모자라면 나머지 중복 이름이라도 채움
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
        print(f"No candidates found for keyword: {keyword}")
        return

    print(f"Starting registration for {len(candidate_data)} products...")

    # 2. 쿠팡 계정 정보 로드
    with SessionLocal() as session:
        account = session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").first()
        if not account:
            print("No Coupang account found.")
            return
        account_id = account.id
    
    registered_count = 0
    failed_count = 0
    
    for i, c_info in enumerate(candidate_data, 1):
        print(f"[{i}/{len(candidate_data)}] Processing: {c_info['name'][:30]}... ({c_info['id']})")
        try:
            with SessionLocal() as session:
                raw_item = (
                    session.query(SupplierItemRaw)
                    .filter(SupplierItemRaw.supplier_code == c_info["supplier_code"])
                    .filter(SupplierItemRaw.item_code == c_info["item_code"])
                    .first()
                )
                if not raw_item:
                    print(f"  -> Raw item not found")
                    failed_count += 1
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
                    print(f"  -> Failed: {err}")
                    failed_count += 1
                    continue

                session.query(SourcingCandidate).filter(
                    SourcingCandidate.id == c_info["id"]
                ).update({"status": "APPROVED"})
                session.commit()
                registered_count += 1
                print(f"  -> Success!")
        except Exception as e:
            print(f"  -> Exception: {e}")
            failed_count += 1

    print("-" * 50)
    print(f"Final Report:")
    print(f"  - Total Targeted: {target_count}")
    print(f"  - Successfully Registered: {registered_count}")
    print(f"  - Failed: {failed_count}")
    print("-" * 50)

if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "None" else None
    cnt = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    asyncio.run(register_bulk(kw, cnt))
