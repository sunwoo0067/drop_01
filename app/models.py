from typing import Any
from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, Integer, Text, UniqueConstraint, ForeignKey, Float
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func



class SourceBase(DeclarativeBase):
    pass

class DropshipBase(DeclarativeBase):
    pass

class MarketBase(DeclarativeBase):
    pass



class MarketFeePolicy(MarketBase):
    __tablename__ = "market_fee_policies"
    __table_args__ = (
        UniqueConstraint("market_code", "category_id", name="uq_market_fee_policies_market_category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False) # COUPANG, SMARTSTORE
    category_id: Mapped[str | None] = mapped_column(Text, nullable=True) # Optional category-specific fee
    fee_rate: Mapped[float] = mapped_column(Float, nullable=False) # 0.12 (12%)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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


class SystemSetting(MarketBase):
    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class MarketInquiryRaw(MarketBase):
    __tablename__ = "market_inquiry_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "inquiry_id", name="uq_market_inquiry_raw_account_inquiry"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    inquiry_id: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ai_suggested_answer: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketRevenueRaw(MarketBase):
    __tablename__ = "market_revenue_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "order_id", "sale_type", name="uq_market_revenue_raw_account_order_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    sale_type: Mapped[str] = mapped_column(Text, nullable=False) # SALE, REFUND
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class MarketSettlementRaw(MarketBase):
    __tablename__ = "market_settlement_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "recognition_year_month", name="uq_market_settlement_raw_account_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    recognition_year_month: Mapped[str] = mapped_column(Text, nullable=False) # YYYY-MM
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class MarketReturnRaw(MarketBase):
    __tablename__ = "market_return_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "receipt_id", name="uq_market_return_raw_account_return"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    receipt_id: Mapped[str] = mapped_column(Text, nullable=False)  # 쿠팡 반품 접수번호
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class MarketExchangeRaw(MarketBase):
    __tablename__ = "market_exchange_raw"
    __table_args__ = (
        UniqueConstraint("market_code", "account_id", "exchange_id", name="uq_market_exchange_raw_account_exchange"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_accounts.id"), nullable=False)
    exchange_id: Mapped[str] = mapped_column(Text, nullable=False)  # 쿠팡 교환 접수번호
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
    processing_status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING") # PENDING, PROCESSING, COMPLETED, FAILED, PENDING_APPROVAL
    benchmark_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # === 3단계 전략 관련 필드 ===
    # 라이프사이클 단계
    lifecycle_stage: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="STEP_1",
        comment="STEP_1: 탐색, STEP_2: 검증, STEP_3: 스케일"
    )
    lifecycle_stage_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="단계 변경 시점"
    )

    # KPI 지표 (STEP 1 → 2 전환용)
    total_sales_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="총 판매 횟수"
    )
    total_views: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="총 조회수"
    )
    total_clicks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="총 클릭수"
    )
    ctr: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="클릭률 (clicks / views)"
    )
    conversion_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="전환율 (sales / clicks)"
    )

    # 재구매/옵션 확장 지표 (STEP 2 → 3 전환용)
    repeat_purchase_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="재구매 횟수"
    )
    option_expansion_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="옵션 확장 횟수"
    )
    customer_retention_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="고객 유지율"
    )

    # LTV (Lifetime Value) - STEP 3 진입 기준
    total_revenue: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="총 매출"
    )
    avg_customer_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="고객당 평균 가치"
    )

    # 가공 이력 관련
    last_processing_type: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="마지막 가공 유형 (NAME, OPTION, DESCRIPTION, IMAGE, DETAIL_PAGE)"
    )
    last_processing_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 가공 시점"
    )

    # AI 모델 사용 이력
    ai_model_used: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="사용된 AI 모델 (qwen3:8b, qwen3-vl:8b, etc.)"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    options: Mapped[list["ProductOption"]] = relationship("ProductOption", back_populates="product", cascade="all, delete-orphan")


class ProductOption(DropshipBase):
    __tablename__ = "product_options"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    
    option_name: Mapped[str] = mapped_column(Text, nullable=False)  # 예: 색상/사이즈
    option_value: Mapped[str] = mapped_column(Text, nullable=False) # 예: Red/XL
    
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selling_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    external_option_key: Mapped[str | None] = mapped_column(Text, nullable=True) # 공급처 옵션 키
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="options")


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
    store_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    coupang_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # === 3단계 전략 관련 필드 ===
    # 노출/클릭 지표
    view_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="노출수"
    )
    click_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="클릭수"
    )

    # 시장별 KPI 업데이트 시점
    kpi_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="KPI 마지막 업데이트 시점"
    )


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


class OrderItem(MarketBase):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    market_listing_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("market_listings.id"), nullable=True)
    product_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    external_item_id: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. Coupang orderItemId
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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


class OrchestrationEvent(DropshipBase):
    """
    AI 오케스트레이션의 기동 로그를 기록합니다.
    """
    __tablename__ = "orchestration_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    step: Mapped[str] = mapped_column(Text, nullable=False) # PLANNING, SOURCING, PROCESSING, LISTING
    status: Mapped[str] = mapped_column(Text, nullable=False) # START, IN_PROGRESS, SUCCESS, FAIL
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalesAnalytics(DropshipBase):
    """
    제품별 판매 데이터 분석 결과를 저장합니다.
    AI 기반 소싱 추천을 위한 판매 데이터 기반 분석입니다.
    """
    __tablename__ = "sales_analytics"
    __table_args__ = (
        UniqueConstraint("product_id", "period_type", "period_start", name="uq_sales_analytics_product_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    
    # 분석 기간 정보
    period_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'daily', 'weekly', 'monthly'
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # 판매 지표
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_revenue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_profit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_margin_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # 동향 지표
    order_growth_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 전 대비 성장률
    revenue_growth_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # 예측 지표
    predicted_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 다음 기간 예측 주문수
    predicted_revenue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 예측 신뢰도 0-1
    
    # 카테고리/시장 정보
    category_trend_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 카테고리 내 트렌드 점수
    market_demand_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 시장 수요 점수
    
    # AI 분석 결과
    trend_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)  # 트렌드 분석 요약
    insights: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # 주요 인사이트
    recommendations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # 추천 사항
    
    # 메타데이터
    analysis_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourcingRecommendation(DropshipBase):
    """
    AI 기반 소싱 추천 결과를 저장합니다.
    판매 데이터, 시장 트렌드, 재고 상태를 종합적으로 분석하여 소싱 추천을 제공합니다.
    """
    __tablename__ = "sourcing_recommendations"
    __table_args__ = (
        UniqueConstraint("product_id", "recommendation_date", name="uq_sourcing_recommendations_product_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    supplier_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # FK 제거 - SourceBase와 DropshipBase 분리로 인해
    
    # 추천 유형
    recommendation_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'NEW_PRODUCT', 'REORDER', 'ALTERNATIVE'
    recommendation_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # 추천 점수 (0-100)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # 점수 구성 요소
    sales_potential_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 판매 잠재력 점수
    market_trend_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 시장 트렌드 점수
    profit_margin_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 이익률 점수
    supplier_reliability_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 공급처 신뢰도 점수
    seasonal_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 시즌성 점수
    
    # 추천 수량
    recommended_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # 가격 정보
    current_supply_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommended_selling_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_margin: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # 옵션별 성과 및 추천 상세 (JSONB)
    # [ { "option_id": str, "option_name": str, "option_value": str, "recommended_quantity": int, "score": float, ... } ]
    option_recommendations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    
    # 재고/주문 정보
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stock_days_left: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 현재 재고로 며칠 버틸 수 있는지
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 재주문 시점
    
    # AI 분석 결과
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)  # 추천 사유
    risk_factors: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # 리스크 요소
    opportunity_factors: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # 기회 요소
    
    # 상태
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")  # PENDING, ACCEPTED, REJECTED, COMPLETED
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)  # 수행된 액션
    
    # 메타데이터
    model_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1.0")
    confidence_level: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 추천 신뢰도 0-1
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupplierPerformance(DropshipBase):
    """
    공급처별 성능 지표를 추적합니다.
    소싱 추천 시 공급처 신뢰도 점수 산정에 활용됩니다.
    """
    __tablename__ = "supplier_performance"
    __table_args__ = (
        UniqueConstraint("supplier_code", "period_type", "period_start", name="uq_supplier_performance_supplier_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 분석 기간
    period_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'daily', 'weekly', 'monthly'
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # 주문 관련 지표
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # 배송 관련 지표
    avg_delivery_time_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    on_time_delivery_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    late_delivery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # 품질 관련 지표
    return_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    complaint_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_product_rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # 가격 관련 지표
    avg_price_competitiveness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 시장 대비 가격 경쟁력
    
    # 종합 점수
    overall_reliability_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 0-100
    
    # 메타데이터
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProductLifecycle(DropshipBase):
    """
    상품 라이프사이클 단계 변경 이력을 추적합니다.
    """
    __tablename__ = "product_lifecycles"
    __table_args__ = (
        UniqueConstraint("product_id", "transition_sequence", name="uq_product_lifecycles_product_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False
    )
    
    # 단계 전환 정보
    transition_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="전환 순서 (1, 2, 3...)"
    )
    from_stage: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="이전 단계 (STEP_1, STEP_2, STEP_3)"
    )
    to_stage: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="새 단계 (STEP_1, STEP_2, STEP_3)"
    )
    
    # 전환 기준 KPI
    kpi_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="전환 시점의 KPI 스냅샷"
    )
    
    # 전환 사유
    transition_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="단계 전환 사유"
    )
    auto_transition: Mapped[bool] = mapped_column(
        default=False,
        comment="자동 전환 여부"
    )
    
    # 메타데이터
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class ProcessingHistory(DropshipBase):
    """
    상품 가공 이력을 추적합니다.
    가공 전/후의 성과 변화를 분석하여 자체 드랍쉬핑 모델을 구축합니다.
    """
    __tablename__ = "processing_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=False
    )
    
    # 가공 정보
    processing_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="가공 유형 (NAME, OPTION, DESCRIPTION, IMAGE, DETAIL_PAGE, FULL_BRANDING)"
    )
    processing_stage: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="가공 시점의 단계 (STEP_1, STEP_2, STEP_3)"
    )
    
    # 가공 전 데이터
    before_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="가공 전 상태 (name, description, image_urls, etc.)"
    )
    before_kpi: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="가공 전 KPI (ctr, conversion_rate, etc.)"
    )
    
    # 가공 후 데이터
    after_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="가공 후 상태"
    )
    after_kpi: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="가공 후 KPI (일정 기간 후 업데이트)"
    )
    
    # AI 처리 정보
    ai_model: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="사용된 AI 모델"
    )
    ai_processing_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="AI 처리 시간 (ms)"
    )
    ai_cost_estimate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="추정 AI 처리 비용"
    )
    
    # 성과 분석
    kpi_improvement: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="KPI 개선율 (ctr_change, conversion_change, etc.)"
    )
    roi_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="ROI 점수 (0-100)"
    )
    
    # 메타데이터
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    kpi_measured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="가공 후 KPI 측정 시점"
    )
