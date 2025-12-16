import argparse
import os
import sys

from sqlalchemy import func, or_, select

sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.models import BenchmarkProduct


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--market-code", dest="marketCode", type=str, default="")
    parser.add_argument("--raw-html-max", dest="rawHtmlMax", type=int, default=50000)
    parser.add_argument("--trim-detail-html", dest="trimDetailHtml", action="store_true")
    parser.add_argument("--detail-html-max", dest="detailHtmlMax", type=int, default=200000)
    parser.add_argument("--no-preserve-updated-at", dest="noPreserveUpdatedAt", action="store_true")
    args = parser.parse_args()

    preserveUpdatedAt = not bool(args.noPreserveUpdatedAt)

    cleanupConds = [
        func.length(BenchmarkProduct.raw_data["raw_html"].astext) > int(args.rawHtmlMax),
        BenchmarkProduct.raw_data.has_key("detail_html"),
        BenchmarkProduct.raw_data.has_key("image_urls"),
    ]
    if args.trimDetailHtml:
        cleanupConds.append(func.length(BenchmarkProduct.detail_html) > int(args.detailHtmlMax))

    stmt = select(BenchmarkProduct).where(or_(*cleanupConds)).order_by(BenchmarkProduct.updated_at.desc())
    if args.marketCode:
        stmt = stmt.where(BenchmarkProduct.market_code == str(args.marketCode).strip())
    if int(args.limit) > 0:
        stmt = stmt.limit(int(args.limit))

    totalRows = 0
    changedRows = 0
    trimmedRawHtmlRows = 0
    trimmedDetailHtmlRows = 0
    removedDupKeysRows = 0

    with SessionLocal() as session:
        rows = session.scalars(stmt).yield_per(100)
        for row in rows:
            totalRows += 1

            rawData = row.raw_data if isinstance(row.raw_data, dict) else {}
            newRawData = dict(rawData)

            changed = False

            hadDupKey = False
            if "detail_html" in newRawData:
                newRawData.pop("detail_html", None)
                hadDupKey = True
                changed = True
            if "image_urls" in newRawData:
                newRawData.pop("image_urls", None)
                hadDupKey = True
                changed = True
            if hadDupKey:
                removedDupKeysRows += 1

            rawHtmlVal = newRawData.get("raw_html")
            if isinstance(rawHtmlVal, str) and len(rawHtmlVal) > int(args.rawHtmlMax):
                newRawData["raw_html"] = rawHtmlVal[: int(args.rawHtmlMax)]
                trimmedRawHtmlRows += 1
                changed = True

            newDetailHtml = row.detail_html
            if args.trimDetailHtml and isinstance(newDetailHtml, str) and len(newDetailHtml) > int(args.detailHtmlMax):
                newDetailHtml = newDetailHtml[: int(args.detailHtmlMax)]
                trimmedDetailHtmlRows += 1
                changed = True

            if not changed:
                continue

            changedRows += 1

            currentRawHtmlLen = len(rawHtmlVal) if isinstance(rawHtmlVal, str) else 0
            afterRawHtmlLen = len(newRawData.get("raw_html")) if isinstance(newRawData.get("raw_html"), str) else 0
            currentDetailHtmlLen = len(row.detail_html) if isinstance(row.detail_html, str) else 0
            afterDetailHtmlLen = len(newDetailHtml) if isinstance(newDetailHtml, str) else 0

            print(
                f"id={row.id} market={row.market_code} productId={row.product_id} "
                f"raw_html:{currentRawHtmlLen}->{afterRawHtmlLen} detail_html:{currentDetailHtmlLen}->{afterDetailHtmlLen} apply={bool(args.apply)}"
            )

            if not args.apply:
                continue

            prevUpdatedAt = row.updated_at
            row.raw_data = newRawData
            if args.trimDetailHtml:
                row.detail_html = newDetailHtml
            if preserveUpdatedAt and prevUpdatedAt is not None:
                row.updated_at = prevUpdatedAt

            if changedRows % 200 == 0:
                session.commit()
                session.expire_all()

        if args.apply:
            session.commit()

    print(
        f"totalMatched={totalRows} changed={changedRows} "
        f"trimmedRawHtmlRows={trimmedRawHtmlRows} trimmedDetailHtmlRows={trimmedDetailHtmlRows} removedDupKeysRows={removedDupKeysRows}"
    )

    if args.apply:
        print("적용 완료")
    else:
        print("dry-run 완료(--apply를 주면 반영됩니다)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
