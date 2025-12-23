from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, Integer, Text, UniqueConstraint, ForeignKey, Float
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func



class SourceBase(DeclarativeBase):
    pass

class DropshipBase(DeclarativeBase):
    pass

class MarketBase(DeclarativeBase):
    pass



class Embedding(DropshipBase):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)


class SupplierAccount(SourceBase):
    __tablename__ = "supplier_accounts"
    __table_args__ = (UniqueConstraint("supplier_code", "username", name="uq_supplier_accounts_supplier_username"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    user_type: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    credentials: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BenchmarkCollectJob(MarketBase):
    __tablename__ = "benchmark_collect_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    market_code: Mapped[str] = mapped_column(Text, nullable=False, default="COUPANG")
    markets: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_markets: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierSyncJob(SourceBase):
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


class SupplierSyncState(SourceBase):
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


class SupplierRawFetchLog(SourceBase):
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


class SupplierItemRaw(SourceBase):
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


class SupplierOrderRaw(SourceBase):
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


class SupplierQnaRaw(SourceBase):
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


class SupplierCategoryRaw(SourceBase):
    __tablename__ = "supplier_category_raw"
    __table_args__ = (UniqueConstraint("supplier_code", "category_id", name="uq_supplier_category_raw_supplier_category"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


# --------------------------------------------------------------------------
# Market Domain (Sales Channels)
# --------------------------------------------------------------------------

class MarketAccount(MarketBase):
    __tablename__ = "market_accounts"
    __table_args__ = (UniqueConstraint("market_code", "name", name="uq_market_accounts_code_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)  # 'COUPANG', 'SMARTSTORE'
    name: Mapped[str] = mapped_column(Text, nullable=False)  # Account Alias
    credentials: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MarketOrderRaw(MarketBase):
    __tablename__ = "market_order_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "order_id", name="uq_market_order_raw_account_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)  # Market's Order ID
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class MarketProductRaw(MarketBase):
    __tablename__ = "market_product_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "market_item_id", name="uq_market_product_raw_account_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    market_item_id: Mapped[str] = mapped_column(Text, nullable=False)  # sellerProductId
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


# --------------------------------------------------------------------------
# Core Business Domain (Unified)
# --------------------------------------------------------------------------

class Product(DropshipBase):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selling_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")  # DRAFT, ACTIVE, SUSPENDED
    # Processing Fields
    processed_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_keywords: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    processed_image_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    processing_status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING") # PENDING, PROCESSING, COMPLETED, FAILED

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MarketListing(MarketBase):
    __tablename__ = "market_listings"
    __table_args__ = (
        UniqueConstraint("market_account_id", "market_item_id", name="uq_market_listings_account_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    market_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    market_item_id: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. sellerProductId
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    coupang_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class SupplierOrder(MarketBase):
    __tablename__ = "supplier_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_order_id: Mapped[str | None] = mapped_column(Text, nullable=True) # ID assigned by supplier
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Order(MarketBase):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("market_order_raw.id"), nullable=True)
    supplier_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_orders.id"), nullable=True)
    
    order_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True) # Internal Order Number
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PAYMENT_COMPLETED")
    
    recipient_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OrderStatusHistory(MarketBase):
    __tablename__ = "order_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenchmarkProduct(MarketBase):
    __tablename__ = "benchmark_products"
    __table_args__ = (
        UniqueConstraint("market_code", "product_id", name="uq_benchmark_products_market_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    product_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    detail_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Ranking & Stats
    category_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    
    # Advanced Sourcing Fields
    review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pain_points: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True) # e.g. ["heavy", "breaks easily"]
    specs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visual_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourcingCandidate(DropshipBase):
    """
    Potential products found from suppliers (e.g. OwnerClan) that match a sourcing strategy.
    These are transient candidates before being promoted to real 'Products'.
    """
    __tablename__ = "sourcing_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    
    name: Mapped[str] = mapped_column(Text, nullable=False)
    supply_price: Mapped[int] = mapped_column(Integer, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Sourcing Analysis Data
    source_strategy: Mapped[str] = mapped_column(Text, nullable=False) # e.g. "KEYWORD", "BENCHMARK_GAP", "SPEC_MATCH"
    benchmark_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasonal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    spec_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True) # Extracted specs
    seo_keywords: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True) # High value keywords
    target_event: Mapped[str | None] = mapped_column(Text, nullable=True) # e.g. "Christmas"
    visual_analysis: Mapped[str | None] = mapped_column(Text, nullable=True) # Spatial analysis from Qwen-VL

    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    
    status: Mapped[str] = mapped_column(Text, default="PENDING") # PENDING, APPROVED, REJECTED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class APIKey(DropshipBase):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text, nullable=False) # 'gemini', 'openai'
    key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
