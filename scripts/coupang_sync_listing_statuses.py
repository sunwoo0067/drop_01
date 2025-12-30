import argparse
import json
import time
from datetime import datetime
from sqlalchemy import select

from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
from app.coupang_sync import sync_market_listing_status


DEFAULT_SKIP_STATUSES = {"APPROVED", "PARTIAL_APPROVED", "DELETED"}


def main() -> None:
    parser = argparse.ArgumentParser(description="쿠팡 MarketListing 상태 동기화")
    parser.add_argument("--account-id", default=None, help="특정 쿠팡 계정 UUID")
    parser.add_argument("--limit", type=int, default=200, help="처리 상한")
    parser.add_argument("--all", action="store_true", help="승인완료도 포함")
    parser.add_argument("--sleep", type=float, default=0.1, help="요청 간 딜레이(초)")
    parser.add_argument(
        "--out",
        default=f"/tmp/coupang_sync_listing_statuses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
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

        stmt = (
            select(MarketListing)
            .where(MarketListing.market_account_id == account.id)
            .order_by(MarketListing.linked_at.desc())
        )
        if not args.all:
            stmt = stmt.where(
                (MarketListing.coupang_status.is_(None))
                | (~MarketListing.coupang_status.in_(DEFAULT_SKIP_STATUSES))
            )

        listings = session.scalars(stmt.limit(args.limit)).all()

        results = []
        for listing in listings:
            success, result = sync_market_listing_status(session, listing.id)
            results.append(
                {
                    "listingId": str(listing.id),
                    "productId": str(listing.product_id),
                    "sellerProductId": str(listing.market_item_id),
                    "success": bool(success),
                    "result": result,
                }
            )
            time.sleep(max(args.sleep, 0.0))

        payload = {
            "accountId": str(account.id),
            "accountName": account.name,
            "total": len(listings),
            "results": results,
        }

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(json.dumps({"out": args.out, "total": len(listings)}, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    main()
