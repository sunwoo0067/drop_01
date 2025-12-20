import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

from sqlalchemy import select

# 프로젝트 루트를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.session_factory import session_factory
from app.models import MarketAccount, MarketListing


def _safe_str(v: object | None) -> str:
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def _extract_rejection_text(rejection_reason: dict | None) -> str | None:
    if not isinstance(rejection_reason, dict):
        return None

    for k in ("reason", "comment", "message"):
        v = rejection_reason.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def _normalize_status(status: object | None) -> str | None:
    if status is None:
        return None

    s = _safe_str(status).strip()
    if not s:
        return None

    su = s.upper()
    if su == "APPROVAL_REQUESTED":
        return "APPROVING"

    if su in {
        "DENIED",
        "DELETED",
        "IN_REVIEW",
        "SAVED",
        "APPROVING",
        "APPROVED",
        "PARTIAL_APPROVED",
    }:
        return su

    if s in {"승인반려", "반려"}:
        return "DENIED"
    if s in {"임시저장", "임시저장중"}:
        return "SAVED"
    if s == "승인대기중":
        return "APPROVING"
    if s == "심사중":
        return "IN_REVIEW"
    if s == "승인완료":
        return "APPROVED"
    if s == "부분승인완료":
        return "PARTIAL_APPROVED"
    if "삭제" in s or s == "상품삭제":
        return "DELETED"

    return s


def main() -> int:
    parser = argparse.ArgumentParser(description="쿠팡 상태 리포트(최신 MarketListing 기준)")
    parser.add_argument("--scan-limit", type=int, default=5000, help="MarketListing 조회 최대 건수")
    parser.add_argument("--sample-limit", type=int, default=20, help="비정상 상태 샘플 출력 건수")
    parser.add_argument(
        "--out",
        default=f"/tmp/coupang_status_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="결과 JSON 저장 경로",
    )
    args = parser.parse_args()

    with session_factory() as session:
        acct = session.scalars(
            select(MarketAccount)
            .where(MarketAccount.market_code == "COUPANG")
            .where(MarketAccount.is_active == True)
        ).first()
        if not acct:
            raise RuntimeError("활성 상태의 쿠팡 계정을 찾을 수 없습니다.")

        listings = session.scalars(
            select(MarketListing)
            .where(MarketListing.market_account_id == acct.id)
            .order_by(MarketListing.linked_at.desc())
            .limit(int(args.scan_limit))
        ).all()

        latest_by_product: dict[str, MarketListing] = {}
        for l in listings:
            pid = _safe_str(l.product_id)
            if pid and pid not in latest_by_product:
                latest_by_product[pid] = l

        rows = []
        for pid, l in latest_by_product.items():
            rows.append(
                {
                    "productId": pid,
                    "sellerProductId": _safe_str(l.market_item_id) or None,
                    "coupangStatus": _normalize_status(l.coupang_status),
                    "linkedAt": l.linked_at.isoformat() if l.linked_at else None,
                    "rejectionReasonText": _extract_rejection_text(l.rejection_reason),
                }
            )

    counts = Counter([r.get("coupangStatus") for r in rows])

    non_ok = []
    for r in rows:
        st = r.get("coupangStatus")
        if st not in {"APPROVED", "PARTIAL_APPROVED"}:
            non_ok.append(r)

    result = {
        "generatedAt": datetime.now().isoformat(),
        "latestCount": len(rows),
        "countsByCoupangStatus": dict(counts),
        "sampleNonApproved": non_ok[: int(args.sample_limit)],
    }

    out_path = str(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
