import argparse
import json
from datetime import datetime
from sqlalchemy import select

from app.db import SessionLocal
from app.models import MarketAccount, MarketListing, Product


def main() -> None:
    parser = argparse.ArgumentParser(description="최근 쿠팡 승인반려 상품/사유 조회")
    parser.add_argument("--account-id", default=None, help="특정 쿠팡 계정 UUID")
    parser.add_argument("--limit", type=int, default=50, help="조회 건수")
    parser.add_argument(
        "--out",
        default=f"/tmp/coupang_recent_denied_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="결과 저장 경로",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.account_id:
            account = session.get(MarketAccount, args.account_id)
        else:
            stmt = select(MarketAccount).where(
                MarketAccount.market_code == "COUPANG",
                MarketAccount.is_active == True,
            )
            account = session.scalars(stmt).first()

        if not account:
            raise RuntimeError("활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

        denied_statuses = {"DENIED", "승인반려", "반려"}
        listings = session.scalars(
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .where(MarketListing.coupang_status.in_(denied_statuses))
            .order_by(MarketListing.linked_at.desc())
            .limit(args.limit)
        ).all()

        rows = []
        for listing in listings:
            product = session.get(Product, listing.product_id)
            rows.append(
                {
                    "listingId": str(listing.id),
                    "productId": str(listing.product_id),
                    "sellerProductId": str(listing.market_item_id),
                    "productName": (product.processed_name or product.name) if product else None,
                    "coupangStatus": listing.coupang_status,
                    "rejectionReason": listing.rejection_reason,
                }
            )

        payload = {
            "accountId": str(account.id),
            "accountName": account.name,
            "count": len(rows),
            "results": rows,
        }

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(json.dumps({"out": args.out, "count": len(rows)}, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    main()
