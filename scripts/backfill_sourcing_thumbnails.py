import argparse

from sqlalchemy import and_, select

from app.models import SourcingCandidate, SupplierItemRaw
from app.session_factory import session_factory


def _extract_thumbnail(raw: dict | None) -> str | None:
    if not isinstance(raw, dict):
        return None
    images = raw.get("images")
    if isinstance(images, list) and images:
        return images[0]
    if isinstance(images, str):
        candidate = images.strip()
        if candidate.startswith(("http://", "https://")):
            return candidate
    return None


def main(batch_size: int, max_batches: int | None, commit: bool) -> None:
    total_scanned = 0
    total_updated = 0
    batches = 0

    if not commit and max_batches is None:
        max_batches = 1

    with session_factory() as session:
        while True:
            stmt = (
                select(SourcingCandidate, SupplierItemRaw)
                .join(
                    SupplierItemRaw,
                    and_(
                        SupplierItemRaw.supplier_code == "ownerclan",
                        SupplierItemRaw.item_code == SourcingCandidate.supplier_item_id,
                    ),
                )
                .where(SourcingCandidate.supplier_code == "ownerclan")
                .where(SourcingCandidate.thumbnail_url.is_(None))
                .limit(batch_size)
            )
            rows = session.execute(stmt).all()
            if not rows:
                break

            batch_updated = 0
            for candidate, raw in rows:
                thumbnail_url = _extract_thumbnail(raw.raw if hasattr(raw, "raw") else None)
                if thumbnail_url:
                    candidate.thumbnail_url = thumbnail_url
                    batch_updated += 1

            total_scanned += len(rows)
            total_updated += batch_updated
            batches += 1

            if commit:
                session.commit()
            else:
                session.rollback()

            if max_batches and batches >= max_batches:
                break

    print(f"scanned={total_scanned} updated={total_updated} batches={batches} commit={commit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill thumbnail_url for sourcing candidates.")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    main(args.batch_size, args.max_batches, args.commit)
