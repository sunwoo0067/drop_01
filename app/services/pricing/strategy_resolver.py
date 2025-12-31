import uuid
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Product, PricingStrategy, CategoryStrategyMapping, MarketListing

class StrategyResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve_strategy(
        self, 
        product_id: uuid.UUID, 
        category_code: Optional[str] = None
    ) -> Optional[PricingStrategy]:
        """
        주어진 상품과 카테고리에 대한 최적의 가격 전략을 도출합니다.
        우선순위:
        1. Product Override (Product.strategy_id)
        2. Category Mapping (CategoryStrategyMapping)
        3. Lifecycle stage 기반 기본 전략 (STEP_1=AGGRESSIVE 등)
        """
        # 1. Product Override 확인
        stmt_prod = select(Product).where(Product.id == product_id)
        product = self.db.execute(stmt_prod).scalars().first()
        
        if product and product.strategy_id:
            stmt_strategy = select(PricingStrategy).where(PricingStrategy.id == product.strategy_id)
            strategy = self.db.execute(stmt_strategy).scalars().first()
            if strategy:
                return strategy

        # 2. Category Mapping 확인
        if category_code:
            stmt_cat = select(CategoryStrategyMapping).where(CategoryStrategyMapping.category_code == category_code)
            mapping = self.db.execute(stmt_cat).scalars().first()
            if mapping:
                stmt_strategy = select(PricingStrategy).where(PricingStrategy.id == mapping.strategy_id)
                strategy = self.db.execute(stmt_strategy).scalars().first()
                if strategy:
                    return strategy

        # 3. Lifecycle Stage 기반 기본 전략 (이름 기반 조회)
        if product:
            default_name = self._get_default_strategy_name_for_stage(product.lifecycle_stage)
            if default_name:
                stmt_strategy = select(PricingStrategy).where(PricingStrategy.name == default_name)
                strategy = self.db.execute(stmt_strategy).scalars().first()
                if strategy:
                    return strategy

        return None

    def _get_default_strategy_name_for_stage(self, stage: str) -> Optional[str]:
        """라이프사이클 단계별 기본 전략 이름을 매핑합니다."""
        mapping = {
            "STEP_1": "AGGRESSIVE_GROWTH",
            "STEP_2": "MARKET_STABLE",
            "STEP_3": "PROFIT_DEFENSE"
        }
        return mapping.get(stage)
