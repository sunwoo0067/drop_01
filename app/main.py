import os
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from supabase import create_client

from app.db import engine, get_session
from app.models import Base, Embedding
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
