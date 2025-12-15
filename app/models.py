from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(3), nullable=False)


class SupplierAccount(Base):
    __tablename__ = "supplier_accounts"
    __table_args__ = (UniqueConstraint("supplier_code", "username", name="uq_supplier_accounts_supplier_username"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    user_type: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierSyncJob(Base):
    __tablename__ = "supplier_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierSyncState(Base):
    __tablename__ = "supplier_sync_state"
    __table_args__ = (
        UniqueConstraint("supplier_code", "sync_type", "account_id", name="uq_supplier_sync_state_supplier_type_account"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    sync_type: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=lambda: uuid.UUID(int=0))
    watermark_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierRawFetchLog(Base):
    __tablename__ = "supplier_raw_fetch_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupplierItemRaw(Base):
    __tablename__ = "supplier_item_raw"
    __table_args__ = (
        UniqueConstraint("supplier_code", "item_code", name="uq_supplier_item_raw_supplier_item_code"),
        UniqueConstraint("supplier_code", "item_key", name="uq_supplier_item_raw_supplier_item_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    item_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class SupplierOrderRaw(Base):
    __tablename__ = "supplier_order_raw"
    __table_args__ = (
        UniqueConstraint("supplier_code", "account_id", "order_id", name="uq_supplier_order_raw_supplier_account_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class SupplierQnaRaw(Base):
    __tablename__ = "supplier_qna_raw"
    __table_args__ = (
        UniqueConstraint("supplier_code", "account_id", "qna_id", name="uq_supplier_qna_raw_supplier_account_qna"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qna_id: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class SupplierCategoryRaw(Base):
    __tablename__ = "supplier_category_raw"
    __table_args__ = (UniqueConstraint("supplier_code", "category_id", name="uq_supplier_category_raw_supplier_category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
