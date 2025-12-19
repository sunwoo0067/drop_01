import os
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List

from supabase import create_client

from app.db import dropship_engine, get_session
from app.models import DropshipBase, Embedding, SupplierAccount, SupplierSyncJob

from app.ownerclan_client import OwnerClanClient
from app.ownerclan_sync import start_background_ownerclan_job
from app.session_factory import session_factory
from app.settings import settings
from app.api.endpoints import sourcing, products, coupang, settings as settings_endpoint, suppliers as suppliers_endpoint, benchmarks, market
from app.schemas.product import ProductResponse

app = FastAPI()

app.include_router(sourcing.router, prefix="/api/sourcing", tags=["Sourcing"])
app.include_router(benchmarks.router, prefix="/api/benchmarks", tags=["Benchmarks"])
app.include_router(products.router, prefix="/api/products", tags=["Products"]) 
app.include_router(coupang.router, prefix="/api/coupang", tags=["Coupang"])
app.include_router(settings_endpoint.router, prefix="/api/settings", tags=["Settings"])
app.include_router(suppliers_endpoint.router, prefix="/api/suppliers", tags=["Suppliers"])
app.include_router(market.router, prefix="/api/market", tags=["Market"])


# Next.js(/api/products) 경로 정규화로 인해 백엔드가 /api/products → /api/products/ 로 307 redirect를 내보내면
# 브라우저가 8888 오리진으로 따라가며 CORS에 막혀 Axios가 Network Error가 날 수 있다.
# 따라서 슬래시 없는 엔드포인트를 별칭(alias)로 제공해 redirect 자체를 제거한다.
@app.get("/api/products", response_model=List[ProductResponse], include_in_schema=False)
def list_products_alias(
    session: Session = Depends(get_session),
    processing_status: str | None = Query(default=None, alias="processingStatus"),
    status: str | None = Query(default=None),
):
    return products.list_products(session=session, processing_status=processing_status, status=status)


@app.get("/api/benchmarks", include_in_schema=False)
def list_benchmarks_alias(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None),
    market_code: str | None = Query(default=None, alias="marketCode"),
    order_by: str | None = Query(default=None, alias="orderBy"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return benchmarks.list_benchmarks(
        session=session,
        q=q,
        market_code=market_code,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )


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
    # Vector extension is needed for Dropship DB (Embeddings)
    with dropship_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    
    # Auto-create tables (Legacy support, though Alembic is preferred)
    if os.getenv("DB_AUTO_CREATE_TABLES", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
        DropshipBase.metadata.create_all(bind=dropship_engine)
        # Add others if needed:
        # SourceBase.metadata.create_all(bind=source_engine)
        # MarketBase.metadata.create_all(bind=market_engine)



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

    # primary는 user_type 별로 유지합니다(seller/vendor 각각 1개씩 가능)
    session.query(SupplierAccount).filter(SupplierAccount.supplier_code == "ownerclan").filter(SupplierAccount.user_type == user_type).update({"is_primary": False})

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
