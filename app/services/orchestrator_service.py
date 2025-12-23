import logging
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.services.ai.service import AIService
from app.services.ai.agents.analysis_agent import AnalysisAgent
from app.services.sourcing_service import SourcingService
from app.services.processing_service import ProcessingService
from app.services.processing_service import ProcessingService
from app.services.market_service import MarketService

logger = logging.getLogger(__name__)

class OrchestratorService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.analysis_agent = AnalysisAgent(db)
        self.sourcing_service = SourcingService(db)
        self.processing_service = ProcessingService(db)
        self.market_service = MarketService(db)

    def _get_best_sellers(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """
        최근 판매량이 높은 상품 정보를 가져옵니다. (RAG용)
        """
        from app.models import OrderItem, Product, Order
        
        try:
            # PostgreSQL 기준 간소화된 쿼리
            stmt = (
                select(Product.name, func.sum(OrderItem.quantity).label("sales_count"))
                .join(OrderItem, Product.id == OrderItem.product_id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.created_at >= datetime.datetime.now() - datetime.timedelta(days=days))
                .group_by(Product.name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(limit)
            )
            results = self.db.execute(stmt).all()
            return [{"name": r[0], "sales_count": r[1]} for r in results]
        except Exception as e:
            logger.warning(f"Failed to fetch best sellers context: {e}")
            return []

    async def run_daily_cycle(self, dry_run: bool = True):
        """
        매일 실행되는 자율 운영 루프입니다.
        (Planning -> Optimization -> Sourcing -> Step1: Listing -> Step2: Premium)
        """
        logger.info(f"Starting Daily AI Orchestration Cycle (dry_run={dry_run})...")
        
        # 1. Planning: 시즌성 판단 및 전략 수립
        best_sellers = self._get_best_sellers()
        strategy = self.ai_service.plan_seasonal_strategy(context_products=best_sellers)
        logger.info(f"Today's Strategy: {strategy.get('season_name')} - {strategy.get('strategy_theme')}")
        
        # 2. Optimization: 비인기/오프시즌 상품 정리
        outdated_keywords = strategy.get('out_dated_keywords', [])
        cleanup_targets = self.analysis_agent.find_cleanup_targets(outdated_keywords)
        
        for item in cleanup_targets:
            m_code = item.get('market_code', 'COUPANG')
            if dry_run:
                logger.info(f"[DRY-RUN] Deleting {item['market_item_id']} (Reason: {item['reason']})")
            else:
                import uuid
                acc_id = uuid.UUID(item['market_account_id'])
                self.market_service.delete_product(m_code, acc_id, item['market_item_id'])

        # 3. Sourcing: 새로운 상품 소싱
        target_keywords = strategy.get('target_keywords', [])
        if target_keywords:
            for kw in target_keywords[:2]:
                if not dry_run:
                    await self.sourcing_service.execute_expanded_sourcing(kw)

        # 4. [Step 1] 가공 및 선등록 (Fast Listing: 상품명 위주)
        # PENDING 상태의 신규 상품 가공 (Status: COMPLETED)
        if not dry_run:
            processed_count = await self.processing_service.process_pending_products(limit=10)
            logger.info(f"Step 1: Processed {processed_count} new products for fast listing.")
            
            # 활성 계정 조회
            from app.models import MarketAccount, Product
            stmt_acc = select(MarketAccount).where(MarketAccount.is_active == True)
            accounts = self.db.scalars(stmt_acc).all()
            
            # 가공 완료된(COMPLETED) 최근 상품들 등록
            stmt_prod = select(Product).where(Product.processing_status == "COMPLETED").order_by(Product.updated_at.desc()).limit(10)
            products = self.db.scalars(stmt_prod).all()
            
            for p in products:
                for acc in accounts:
                    # 이미 등록된 리스팅이 있는지 체크하는 로직은 register_product 내부에 있다고 가정
                    self.market_service.register_product(acc.market_code, acc.id, p.id)

        # 5. [Step 2] 판매 상품 상세화 가공 준비 (Premium Optimization Identification)
        # 실제 판매가 발생한 상품 중 프리미엄 가공이 안 된 것들을 찾아내기만 합니다. (수동 승인 대기)
        logger.info("Step 2: Identifying best sellers for potential premium optimization (Manual Approval Required)...")
        winning_products = self.processing_service.get_winning_products_for_processing(limit=5)
        
        for wp in winning_products:
            # 수동 승인을 위해 로그에만 기록하고 자동으로 process_winning_product를 호출하지 않음
            logger.info(f"Winner identified: {wp.name} (Sales: Identified). Ready for manual premium optimization.")

        logger.info("Daily AI Orchestration Cycle Completed.")
        return strategy
