import argparse
import os
import sys
import asyncio

sys.path.append(os.getcwd())

from app.db import SessionLocal
from app.embedding_service import EmbeddingService
from app.models import Embedding


async def _apply_backfill(
    base_url: str,
    model: str,
    start_id: int,
    end_id: int | None,
    batch_size: int,
    commit_every: int,
    sleep_seconds: float,
) -> int:
    service = EmbeddingService(base_url=base_url, model=model)

    total_scanned = 0
    total_candidate = 0
    total_updated = 0
    total_failed = 0

    last_id = int(start_id)

    with SessionLocal() as session:
        while True:
            q = session.query(Embedding).filter(Embedding.id > last_id)
            if end_id is not None:
                q = q.filter(Embedding.id <= int(end_id))

            rows = q.order_by(Embedding.id.asc()).limit(int(batch_size)).all()
            if not rows:
                break

            for row in rows:
                last_id = int(row.id)
                total_scanned += 1

                emb = row.embedding
                if isinstance(emb, list) and len(emb) == 768:
                    continue

                total_candidate += 1

                text = (row.content or "").strip()
                if not text:
                    total_failed += 1
                    continue

                new_emb = await service.generate_embedding(text)
                if not isinstance(new_emb, list) or len(new_emb) != 768:
                    total_failed += 1
                    continue

                row.embedding = new_emb
                total_updated += 1

                if commit_every > 0 and total_updated % int(commit_every) == 0:
                    session.commit()
                    session.expire_all()

                if sleep_seconds > 0:
                    await asyncio.sleep(float(sleep_seconds))

        session.commit()

    print(
        f"scanned={total_scanned} candidates={total_candidate} updated={total_updated} failed={total_failed} last_id={last_id}"
    )

    return 0 if total_failed == 0 else 2


def _dry_run(start_id: int, end_id: int | None, batch_size: int) -> int:
    total_scanned = 0
    total_candidate = 0
    last_id = int(start_id)

    with SessionLocal() as session:
        while True:
            q = session.query(Embedding).filter(Embedding.id > last_id)
            if end_id is not None:
                q = q.filter(Embedding.id <= int(end_id))

            rows = q.order_by(Embedding.id.asc()).limit(int(batch_size)).all()
            if not rows:
                break

            for row in rows:
                last_id = int(row.id)
                total_scanned += 1
                emb = row.embedding
                if isinstance(emb, list) and len(emb) == 768:
                    continue
                total_candidate += 1

    print(f"dry_run scanned={total_scanned} candidates={total_candidate} last_id={last_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")

    parser.add_argument("--base-url", dest="baseUrl", type=str, default=os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--model", type=str, default=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"))

    parser.add_argument("--start-id", dest="startId", type=int, default=0)
    parser.add_argument("--end-id", dest="endId", type=int, default=None)
    parser.add_argument("--batch-size", dest="batchSize", type=int, default=200)
    parser.add_argument("--commit-every", dest="commitEvery", type=int, default=50)
    parser.add_argument("--sleep", dest="sleepSeconds", type=float, default=0.0)

    args = parser.parse_args()

    if not args.apply:
        print("dry-run 모드입니다(--apply를 주면 DB에 반영됩니다)")
        return _dry_run(args.startId, args.endId, args.batchSize)

    print(
        "apply 모드입니다. embeddings.embedding(768) 백필을 수행합니다. "
        "(DB_URL/EMBEDDING_BASE_URL/EMBEDDING_MODEL 환경변수 설정을 확인하세요)"
    )

    return asyncio.run(
        _apply_backfill(
            base_url=str(args.baseUrl),
            model=str(args.model),
            start_id=int(args.startId),
            end_id=int(args.endId) if args.endId is not None else None,
            batch_size=int(args.batchSize),
            commit_every=int(args.commitEvery),
            sleep_seconds=float(args.sleepSeconds),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
