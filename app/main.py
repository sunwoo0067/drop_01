import os
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from supabase import create_client

from app.db import engine, get_session
from app.models import Base, Embedding, SupplierAccount, SupplierSyncJob
from app.ownerclan_client import OwnerClanClient
from app.ownerclan_sync import start_background_ownerclan_job
from app.session_factory import session_factory
from app.settings import settings

app = FastAPI()


class EmbeddingIn(BaseModel):
    content: str
    embedding: list[float]

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, v: list[float]) -> list[float]:
        if len(v) != 3:
            raise ValueError("embedding 길이는 3이어야 합니다")
        return v


@app.on_event("startup")
def on_startup() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/db/ping")
def db_ping(session: Session = Depends(get_session)) -> dict:
    value = session.execute(text("SELECT 1")).scalar_one()
    return {"ok": value == 1}


@app.post("/embeddings")
def create_embedding(payload: EmbeddingIn, session: Session = Depends(get_session)) -> dict:
    row = Embedding(content=payload.content, embedding=payload.embedding)
    session.add(row)
    session.flush()
    return {"id": row.id}


class OwnerClanPrimaryAccountIn(BaseModel):
    user_type: str = "seller"
    username: str = ""
    password: str = ""


class OwnerClanSyncRequestIn(BaseModel):
    params: dict = Field(default_factory=dict)


@app.post("/images")
async def upload_image(file: UploadFile = File(...)) -> dict:
    if not settings.supabase_service_role_key:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY가 설정되어 있지 않습니다")

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다")

    data = await file.read()
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext:
        if content_type == "image/jpeg":
            ext = ".jpg"
        elif content_type == "image/png":
            ext = ".png"
        elif content_type == "image/webp":
            ext = ".webp"
        elif content_type == "image/gif":
            ext = ".gif"

    object_path = f"uploads/{uuid.uuid4().hex}{ext}"

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = supabase.storage.from_(settings.supabase_bucket).upload(
        object_path,
        data,
        file_options={"content-type": content_type, "upsert": False},
    )

    if getattr(result, "error", None):
        raise HTTPException(status_code=500, detail=f"이미지 업로드 실패: {result.error}")

    public_url = f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_bucket}/{object_path}"
    return {"bucket": settings.supabase_bucket, "path": object_path, "publicUrl": public_url}


@app.post("/ownerclan/accounts/primary")
def set_ownerclan_primary_account(payload: OwnerClanPrimaryAccountIn, session: Session = Depends(get_session)) -> dict:
    user_type = payload.user_type or settings.ownerclan_primary_user_type
    username = payload.username or settings.ownerclan_primary_username
    password = payload.password or settings.ownerclan_primary_password

    if not username or not password:
        raise HTTPException(status_code=400, detail="오너클랜 대표계정이 설정되어 있지 않습니다(.env OWNERCLAN_PRIMARY_USERNAME/PASSWORD)")

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
    )

    try:
        token = client.issue_token(username=username, password=password, user_type=user_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"오너클랜 토큰 발급 실패: {e}")

    session.query(SupplierAccount).filter(SupplierAccount.supplier_code == "ownerclan").update({"is_primary": False})

    existing = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.username == username)
        .one_or_none()
    )

    if existing:
        existing.user_type = user_type
        existing.access_token = token.access_token
        existing.token_expires_at = token.expires_at
        existing.is_primary = True
        existing.is_active = True
        account = existing
    else:
        account = SupplierAccount(
            supplier_code="ownerclan",
            user_type=user_type,
            username=username,
            access_token=token.access_token,
            token_expires_at=token.expires_at,
            is_primary=True,
            is_active=True,
        )
        session.add(account)
        session.flush()

    return {"accountId": str(account.id), "tokenExpiresAt": token.expires_at.isoformat() if token.expires_at else None}


def _enqueue_ownerclan_job(job_type: str, params: dict, session: Session) -> dict:
    job = SupplierSyncJob(supplier_code="ownerclan", job_type=job_type, status="queued", params=params)
    session.add(job)
    session.flush()
    return {"jobId": str(job.id)}


@app.post("/sync/ownerclan/items")
def sync_ownerclan_items(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    result = _enqueue_ownerclan_job("ownerclan_items_raw", payload.params, session)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(result["jobId"]))
    return result


@app.post("/sync/ownerclan/orders")
def sync_ownerclan_orders(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    result = _enqueue_ownerclan_job("ownerclan_orders_raw", payload.params, session)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(result["jobId"]))
    return result


@app.post("/sync/ownerclan/qna")
def sync_ownerclan_qna(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    result = _enqueue_ownerclan_job("ownerclan_qna_raw", payload.params, session)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(result["jobId"]))
    return result


@app.post("/sync/ownerclan/categories")
def sync_ownerclan_categories(
    payload: OwnerClanSyncRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    result = _enqueue_ownerclan_job("ownerclan_categories_raw", payload.params, session)
    background_tasks.add_task(start_background_ownerclan_job, session_factory, uuid.UUID(result["jobId"]))
    return result


@app.get("/sync/jobs/{job_id}")
def get_sync_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    job = session.get(SupplierSyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job을 찾을 수 없습니다")

    return {
        "id": str(job.id),
        "supplierCode": job.supplier_code,
        "jobType": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "lastError": job.last_error,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
    }
