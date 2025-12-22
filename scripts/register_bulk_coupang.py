import argparse
import asyncio
import time
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import MarketAccount, Product, SourcingCandidate, SupplierItemRaw
from app.coupang_sync import register_product
from app.services.processing_service import ProcessingService


def _extract_detail_html(raw: dict) -> str:
    for key in ("detail_html", "detailHtml", "content", "description"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _ensure_candidates(session, needed: int) -> int:
    pending_count = (
        session.query(SourcingCandidate)
        .filter(SourcingCandidate.status == "PENDING")
        .count()
    )
    if pending_count >= needed:
        return 0

    required = needed - pending_count + 20
    existing = {
        row[0]
        for row in session.execute(
            select(SourcingCandidate.supplier_item_id)
            .where(SourcingCandidate.supplier_code == "ownerclan")
        ).all()
    }

    raws = session.execute(
        select(SupplierItemRaw)
        .where(SupplierItemRaw.supplier_code == "ownerclan")
        .order_by(SupplierItemRaw.fetched_at.desc())
        .limit(2000)
    ).scalars().all()

    created = 0
    for raw in raws:
        item_code = str(raw.item_code or "").strip()
        if not item_code or item_code in existing:
            continue
        data = raw.raw if isinstance(raw.raw, dict) else {}
        name = data.get("item_name") or data.get("name") or data.get("itemName") or item_code
        supply_price = data.get("supply_price") or data.get("supplyPrice") or data.get("fixedPrice") or data.get("price") or 0
        try:
            supply_price = int(float(supply_price))
        except Exception:
            supply_price = 0

        cand = SourcingCandidate(
            supplier_code="ownerclan",
            supplier_item_id=item_code,
            name=str(name),
            supply_price=supply_price,
            source_strategy="RAW_IMPORT",
            status="PENDING",
        )
        session.add(cand)
        existing.add(item_code)
        created += 1
        if created >= required:
            break

    session.commit()
    return created


async def _process_name(session, product_id: uuid.UUID) -> None:
    service = ProcessingService(session)
    await service.process_product(product_id, min_images_required=1)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=5000)
    parser.add_argument("--batch", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=2.0)
    args = parser.parse_args()

    target = max(1, int(args.target))
    batch_size = max(1, int(args.batch))
    sleep_seconds = max(0.0, float(args.sleep))

    with SessionLocal() as session:
        account = (
            session.query(MarketAccount)
            .filter(MarketAccount.market_code == "COUPANG")
            .filter(MarketAccount.is_active.is_(True))
            .first()
        )
        if not account:
            print("No active COUPANG account found")
            return 1
        account_id = account.id

    total_success = 0
    batch_index = 0

    while total_success < target:
        batch_index += 1
        with SessionLocal() as session:
            created = _ensure_candidates(session, batch_size)
            if created:
                print(f"[batch {batch_index}] created_candidates={created}")

            candidates = (
                session.query(SourcingCandidate)
                .filter(SourcingCandidate.status == "PENDING")
                .order_by(SourcingCandidate.created_at.asc())
                .limit(batch_size)
                .all()
            )

            if not candidates:
                print("No pending candidates found. Stopping.")
                break

            print(f"[batch {batch_index}] candidates={len(candidates)}")

            for cand in candidates:
                raw_item = (
                    session.query(SupplierItemRaw)
                    .filter(SupplierItemRaw.supplier_code == cand.supplier_code)
                    .filter(SupplierItemRaw.item_code == cand.supplier_item_id)
                    .first()
                )

                if not raw_item:
                    cand.status = "REJECTED"
                    session.commit()
                    print(f"skip raw_not_found candidate={cand.id}")
                    time.sleep(sleep_seconds)
                    continue

                product = (
                    session.query(Product)
                    .filter(Product.supplier_item_id == raw_item.id)
                    .first()
                )
                if not product:
                    raw = raw_item.raw if isinstance(raw_item.raw, dict) else {}
                    product = Product(
                        id=uuid.uuid4(),
                        supplier_item_id=raw_item.id,
                        name=cand.name,
                        cost_price=cand.supply_price,
                        selling_price=int(cand.supply_price * 1.5) if cand.supply_price else 0,
                        status="ACTIVE",
                        processing_status="PENDING",
                        description=_extract_detail_html(raw),
                    )
                    session.add(product)
                    session.commit()
                    session.refresh(product)

                await _process_name(session, product.id)
                session.refresh(product)

                ok, err = register_product(session, account_id, product.id)
                if ok:
                    cand.status = "APPROVED"
                    total_success += 1
                    session.commit()
                    print(f"registered {total_success}/{target} product={product.id}")
                else:
                    cand.status = "REJECTED"
                    session.commit()
                    print(f"failed product={product.id} err={err}")

                time.sleep(sleep_seconds)
                if total_success >= target:
                    break

        if total_success >= target:
            break

    print(f"done total_success={total_success}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
