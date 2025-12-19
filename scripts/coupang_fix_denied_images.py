import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

import httpx
from sqlalchemy import select

# 프로젝트 루트를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.session_factory import session_factory
from app.models import MarketAccount, MarketListing


DEFAULT_IMAGE_KEYWORDS = [
    "기타이미지",
    "DETAIL",
    "10M",
    "500&500",
    "5000*5000",
    "500x500",
    "5000x5000",
    "이미지",
]


def _safe_str(v: object | None) -> str:
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def _extract_rejection_text(rejection_reason: dict | None) -> str:
    if not isinstance(rejection_reason, dict):
        return ""

    for k in ("reason", "comment", "message"):
        vv = rejection_reason.get(k)
        if isinstance(vv, str) and vv.strip():
            return vv.strip()

    return ""


def _is_image_denied_reason(rejection_reason: dict | None, keywords: list[str]) -> bool:
    text = _extract_rejection_text(rejection_reason)
    if not text:
        return False
    return any(k in text for k in keywords)


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


def _get_active_coupang_account_id(session) -> str:
    acct = session.scalars(
        select(MarketAccount)
        .where(MarketAccount.market_code == "COUPANG")
        .where(MarketAccount.is_active == True)
    ).first()
    if not acct:
        raise RuntimeError("활성 상태의 쿠팡 계정을 찾을 수 없습니다.")
    return acct.id


def _select_targets(
    session,
    account_id,
    limit: int,
    include_deleted: bool,
    keywords: list[str],
    only_product_ids: set[str] | None,
) -> list[dict]:
    listings = session.scalars(
        select(MarketListing)
        .where(MarketListing.market_account_id == account_id)
        .order_by(MarketListing.linked_at.desc())
        .limit(5000)
    ).all()

    latest_by_product: dict[str, MarketListing] = {}
    for l in listings:
        pid = str(l.product_id)
        if pid not in latest_by_product:
            latest_by_product[pid] = l

    targets: list[dict] = []
    for pid, l in latest_by_product.items():
        if only_product_ids is not None and pid not in only_product_ids:
            continue

        st = _normalize_status(l.coupang_status)
        if st is None:
            continue

        if st == "DELETED" and not include_deleted:
            continue

        if st == "DENIED":
            if not _is_image_denied_reason(l.rejection_reason, keywords):
                continue

        if st not in {"DENIED", "DELETED"}:
            continue

        targets.append(
            {
                "productId": pid,
                "sellerProductId": _safe_str(l.market_item_id) or None,
                "coupangStatus": st,
                "rejectionReason": l.rejection_reason,
            }
        )

        if len(targets) >= int(limit):
            break

    return targets


def _http_json(resp: httpx.Response) -> dict:
    try:
        return resp.json() if resp.content else {}
    except Exception:
        return {"_raw": resp.text}


def _post_process(client: httpx.Client, base_url: str, product_id: str, min_images_required: int) -> dict:
    r = client.post(
        f"{base_url}/api/products/{product_id}/process",
        json={"minImagesRequired": int(min_images_required), "forceFetchOwnerClan": True},
    )
    return {"httpStatus": r.status_code, "body": _http_json(r)}


def _poll_product_processed(
    client: httpx.Client,
    base_url: str,
    product_id: str,
    timeout_sec: int,
    interval_sec: float,
) -> dict:
    deadline = time.time() + float(timeout_sec)
    last_status = None

    while time.time() < deadline:
        r = client.get(f"{base_url}/api/products/{product_id}")
        body = _http_json(r)
        st = body.get("processing_status") if isinstance(body, dict) else None

        if st != last_status:
            last_status = st

        if st in {"COMPLETED", "FAILED"}:
            return {"httpStatus": r.status_code, "body": body}

        time.sleep(float(interval_sec))

    return {"httpStatus": 408, "body": {"message": "processing timeout"}}


def _put_update_coupang(client: httpx.Client, base_url: str, product_id: str) -> dict:
    r = client.put(f"{base_url}/api/coupang/products/{product_id}")
    return {"httpStatus": r.status_code, "body": _http_json(r)}


def _post_sync_status(client: httpx.Client, base_url: str, product_id: str) -> dict:
    r = client.post(f"{base_url}/api/coupang/sync-status/{product_id}")
    body = _http_json(r)

    st = None
    if isinstance(body, dict):
        st = _normalize_status(body.get("coupangStatus"))
        body["coupangStatus"] = st

    return {"httpStatus": r.status_code, "body": body}


def _poll_coupang_status(
    client: httpx.Client,
    base_url: str,
    product_id: str,
    timeout_sec: int,
    interval_sec: float,
) -> dict:
    deadline = time.time() + float(timeout_sec)
    last = None

    while time.time() < deadline:
        out = _post_sync_status(client, base_url, product_id)
        body = out.get("body") if isinstance(out, dict) else None
        st = body.get("coupangStatus") if isinstance(body, dict) else None

        if st != last:
            last = st

        if st in {"APPROVED", "PARTIAL_APPROVED"}:
            return {"final": out, "ok": True}

        if st in {"DENIED", "DELETED"}:
            return {"final": out, "ok": False}

        time.sleep(float(interval_sec))

    return {"final": {"httpStatus": 408, "body": {"coupangStatus": None, "message": "sync timeout"}}, "ok": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="쿠팡 이미지 규격 반려(DENIED) 상품 자동 재가공/업데이트 스크립트")
    parser.add_argument("--base-url", default="http://127.0.0.1:8888", help="백엔드 Base URL")
    parser.add_argument("--limit", type=int, default=50, help="최대 처리 대상 수")
    parser.add_argument("--include-deleted", action="store_true", help="DELETED 상태도 포함")
    parser.add_argument("--min-images", type=int, default=5, help="가공 이미지 최소 수")
    parser.add_argument("--dry-run", action="store_true", help="대상만 출력하고 실행하지 않음")
    parser.add_argument("--product-ids", default="", help="처리할 productId 콤마 구분 목록")
    parser.add_argument("--keywords", default=",".join(DEFAULT_IMAGE_KEYWORDS), help="이미지 반려 키워드(콤마 구분)")
    parser.add_argument("--process-timeout", type=int, default=240, help="가공 완료 대기 타임아웃(초)")
    parser.add_argument("--process-interval", type=float, default=3.0, help="가공 폴링 간격(초)")
    parser.add_argument("--sync-timeout", type=int, default=180, help="상태 동기화 폴링 타임아웃(초)")
    parser.add_argument("--sync-interval", type=float, default=10.0, help="상태 동기화 폴링 간격(초)")
    parser.add_argument(
        "--out",
        default=f"/tmp/coupang_fix_denied_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="결과 JSON 저장 경로",
    )

    args = parser.parse_args()

    keywords = [k.strip() for k in _safe_str(args.keywords).split(",") if k.strip()]
    only_product_ids = None
    if _safe_str(args.product_ids).strip():
        only_product_ids = {p.strip() for p in _safe_str(args.product_ids).split(",") if p.strip()}

    with session_factory() as session:
        account_id = _get_active_coupang_account_id(session)
        targets = _select_targets(
            session=session,
            account_id=account_id,
            limit=int(args.limit),
            include_deleted=bool(args.include_deleted),
            keywords=keywords,
            only_product_ids=only_product_ids,
        )

    print(json.dumps({"targetsCount": len(targets), "targets": targets[:50]}, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("dry-run 모드: 실행을 건너뜁니다.")
        return 0

    result = {
        "startedAt": datetime.now().isoformat(),
        "baseUrl": str(args.base_url),
        "targetsCount": len(targets),
        "items": [],
    }

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for i, t in enumerate(targets, start=1):
            pid = _safe_str(t.get("productId"))
            print(f"[{i}/{len(targets)}] productId={pid} 시작", flush=True)

            item = {
                "productId": pid,
                "sellerProductId": t.get("sellerProductId"),
                "before": {"coupangStatus": t.get("coupangStatus"), "rejectionReason": t.get("rejectionReason")},
                "steps": {},
            }

            try:
                item["steps"]["processTrigger"] = _post_process(client, args.base_url, pid, int(args.min_images))
                item["steps"]["processResult"] = _poll_product_processed(
                    client,
                    args.base_url,
                    pid,
                    timeout_sec=int(args.process_timeout),
                    interval_sec=float(args.process_interval),
                )
                item["steps"]["update"] = _put_update_coupang(client, args.base_url, pid)
                item["steps"]["syncPoll"] = _poll_coupang_status(
                    client,
                    args.base_url,
                    pid,
                    timeout_sec=int(args.sync_timeout),
                    interval_sec=float(args.sync_interval),
                )
            except Exception as e:
                item["error"] = _safe_str(e)

            result["items"].append(item)

            final_status = None
            try:
                final = item.get("steps", {}).get("syncPoll", {}).get("final", {})
                body = final.get("body") if isinstance(final, dict) else None
                final_status = body.get("coupangStatus") if isinstance(body, dict) else None
            except Exception:
                final_status = None

            print(f"  - finalStatus={final_status}", flush=True)

            time.sleep(1.5)

    result["finishedAt"] = datetime.now().isoformat()

    try:
        counts = Counter(
            [
                (it.get("steps", {}).get("syncPoll", {}).get("final", {}).get("body", {}) or {}).get("coupangStatus")
                for it in result.get("items", [])
            ]
        )
        result["countsByCoupangStatus"] = dict(counts)
    except Exception:
        result["countsByCoupangStatus"] = {}

    out_path = str(args.out)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"결과 저장 완료: {out_path}")
    print(json.dumps({"countsByCoupangStatus": result.get("countsByCoupangStatus")}, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
