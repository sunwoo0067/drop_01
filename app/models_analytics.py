from datetime import datetime
import uuid
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, ForeignKey, Float
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.models import DropshipBase

class ProductDim(DropshipBase):
    """
    상품 분석을 위한 Dimension 테이블 (Denormalized)
    """
    __tablename__ = "product_dim"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    base_supply_price: Mapped[int] = mapped_column(Integer, default=0)
    
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class OrdersFact(DropshipBase):
    """
    주문/손익 분석을 위한 Fact 테이블
    """
    __tablename__ = "orders_fact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    channel: Mapped[str] = mapped_column(Text, nullable=False) # COUPANG, NAVER
    
    sell_price: Mapped[int] = mapped_column(Integer, nullable=False)
    supply_price: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping_cost: Mapped[int] = mapped_column(Integer, default=0)
    platform_fee: Mapped[int] = mapped_column(Integer, default=0)
    
    profit: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_rate: Mapped[float] = mapped_column(Float, nullable=False)
    
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ProfitSnapshotFact(DropshipBase):
    """
    상품 수익성 트렌드 분석을 위한 Fact 테이블
    """
    __tablename__ = "profit_snapshot_fact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    profit: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_rate: Mapped[float] = mapped_column(Float, nullable=False)
    
    is_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PricingRecoFact(DropshipBase):
    """
    가격 권고 성과 및 시뮬레이션을 위한 Fact 테이블
    """
    __tablename__ = "pricing_reco_fact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    
    current_price: Mapped[int] = mapped_column(Integer, nullable=False)
    recommended_price: Mapped[int] = mapped_column(Integer, nullable=False)
    
    expected_profit_delta: Mapped[int] = mapped_column(Integer, nullable=False) # 권고가 적용 시 예상 이익 증분
    status: Mapped[str] = mapped_column(Text, nullable=False) # PENDING, APPLIED, REJECTED
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class AnalyticsSyncState(DropshipBase):
    """
    분석 데이터 동기화 상태(증분 적재 시점)를 저장합니다.
    """
    __tablename__ = "analytics_sync_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_type: Mapped[str] = mapped_column(Text, unique=True, nullable=False) # e.g. "orders", "snapshots", "recommendations"
    last_sync_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
