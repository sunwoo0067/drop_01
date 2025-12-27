import argparse
import json
import uuid
from datetime import datetime
from sqlalchemy import select

from app.db import SessionLocal
from app.models import MarketAccount, MarketListing
from app.coupang_sync import update_product_on_coupang


DEFAULT_KEYWORDS = ["도서산간배송", "택배사만 선택", "택배사", "도서산간"]


def _extract_rejection_text(rejection_reason: dict | None) -> str | None:
    if not isinstance(rejection_reason, dict):
        return None
    for key in ("message", "reason", "rejectionReason", "detail", "context"):
        val = rejection_reason.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _matches_keywords(text: str | None, keywords: list[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="쿠팡 승인반려(택배사/도서산간) 상품의 배송사 코드 보정 후 업데이트"
    )
    parser.add_argument("--account-id", default=None, help="특정 쿠팡 계정 UUID")
    parser.add_argument("--limit", type=int, default=200, help="처리 상한")
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="반려 사유 필터 키워드(콤마 구분, 비우면 상태만 필터)",
    )
    parser.add_argument("--dry-run", action="store_true", help="업데이트 없이 대상만 출력")
    parser.add_argument(
        "--out",
        default=f"/tmp/coupang_fix_denied_delivery_company_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="결과 저장 경로",
    )
    args = parser.parse_args()

    keywords = [k.strip() for k in str(args.keywords).split(",") if k.strip()]

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

        targets = []
        for listing in listings:
            text = _extract_rejection_text(listing.rejection_reason)
            if keywords and not _matches_keywords(text, keywords):
                continue
            targets.append({
                "listingId": str(listing.id),
                "productId": listing.product_id,
                "sellerProductId": str(listing.market_item_id),
                "rejectionReasonText": text,
            })

        results = []
        for t in targets:
            if args.dry_run:
                results.append(
                    {
                        **t,
                        "productId": str(t["productId"]),
                        "updated": False,
                        "reason": "dry-run",
                    }
                )
                continue

            product_id = t["productId"]
            if isinstance(product_id, str):
                product_id = uuid.UUID(product_id)
            success, reason = update_product_on_coupang(session, account.id, product_id)
            results.append({
                **t,
                "productId": str(product_id),
                "updated": bool(success),
                "reason": reason,
            })

        payload = {
            "accountId": str(account.id),
            "accountName": account.name,
            "keywords": keywords,
            "totalDenied": len(listings),
            "matched": len(targets),
            "results": results,
        }

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(json.dumps({"out": args.out, "matched": len(targets)}, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    main()
