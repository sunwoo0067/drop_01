import argparse
import time

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import MarketAccount, MarketListing, Product
from app.coupang_sync import register_product
from app.services.name_processing import apply_market_name_rules


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=2.0)
    args = parser.parse_args()

    target = max(1, int(args.count))
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

    registered = 0
    attempts = 0

    while registered < target:
        with SessionLocal() as session:
            subq = (
                select(MarketListing.product_id)
                .where(MarketListing.market_account_id == account_id)
                .subquery()
            )
            product = (
                session.query(Product)
                .filter(Product.id.notin_(select(subq.c.product_id)))
                .order_by(func.random())
                .first()
            )

            if not product:
                print("No available products to register")
                break

            product.processed_name = apply_market_name_rules(product.name)
            session.commit()

            ok, err = register_product(session, account_id, product.id)
            attempts += 1
            if ok:
                registered += 1
                print(f"registered {registered}/{target} product={product.id}")
            else:
                print(f"failed product={product.id} err={err}")

        time.sleep(sleep_seconds)

        if attempts >= target * 3:
            print("too many failures, stopping")
            break

    print(f"done registered={registered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
