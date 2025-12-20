from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.db import get_session
from app.models import BenchmarkCollectJob

router = APIRouter()
logger = logging.getLogger(__name__)

async def status_event_generator(request: Request, session_factory):
    """
    Generates SSE events for benchmark job status updates.
    """
    last_ids_status = {} # To track changes and avoid redundant sends

    while True:
        if await request.is_disconnected():
            break

        try:
            # Use a fresh session for each check to avoid stale data
            with session_factory() as session:
                # Fetch active or recently finished jobs (last 5 minutes)
                active_jobs = session.query(BenchmarkCollectJob).filter(
                    (BenchmarkCollectJob.status.in_(["queued", "running"])) |
                    (BenchmarkCollectJob.finished_at >= datetime.now(timezone.utc).replace(second=0, microsecond=0))
                ).order_by(BenchmarkCollectJob.created_at.desc()).limit(20).all()

                for job in active_jobs:
                    job_key = str(job.id)
                    job_data = {
                        "id": str(job.id),
                        "status": job.status,
                        "market_code": job.market_code,
                        "processed_count": job.processed_count,
                        "total_count": job.total_count,
                        "progress": job.progress,
                        "last_error": job.last_error,
                        "finished_at": job.finished_at.isoformat() if job.finished_at else None
                    }
                    
                    status_json = json.dumps(job_data)
                    if last_ids_status.get(job_key) != status_json:
                        yield f"data: {status_json}\n\n"
                        last_ids_status[job_key] = status_json

        except Exception as e:
            logger.error(f"Error in SSE status generator: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        await asyncio.sleep(2) # Poll every 2 seconds on server side

@router.get("/jobs/stream")
async def stream_job_status(request: Request):
    from app.session_factory import session_factory
    return StreamingResponse(
        status_event_generator(request, session_factory),
        media_type="text/event-stream"
    )
