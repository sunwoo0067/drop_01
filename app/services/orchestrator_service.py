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

from app.models import OrchestrationEvent

logger = logging.getLogger(__name__)

class OrchestratorService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.analysis_agent = AnalysisAgent(db)
        self.sourcing_service = SourcingService(db)
        self.processing_service = ProcessingService(db)
        self.market_service = MarketService(db)

    def _record_event(self, step: str, status: str, message: str = None, details: dict = None):
        """
        오케스트레이션 이벤트를 DB에 기록합니다.
        """
        try:
            event = OrchestrationEvent(
                step=step,
                status=status,
                message=message,
                details=details
            )
            self.db.add(event)
            self.db.commit()
            logger.debug(f"Event recorded: {step} - {status} - {message}")
        except Exception as e:
            logger.error(f"Failed to record event: {e}")
            self.db.rollback()

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
        self._record_event("PLANNING", "START", "전략 수립을 시작합니다.", {"dry_run": dry_run})
        
        # 1. Planning: 시즌성 판단 및 전략 수립
        best_sellers = self._get_best_sellers()
        strategy = self.ai_service.plan_seasonal_strategy(context_products=best_sellers)
        season_name = strategy.get('season_name')
        theme = strategy.get('strategy_theme')
        logger.info(f"Today's Strategy: {season_name} - {theme}")
        self._record_event("PLANNING", "SUCCESS", f"전략 수립 완료: {season_name} ({theme})", strategy)
        
        # 2. Optimization: 비인기/오프시즌 상품 정리
        self._record_event("OPTIMIZATION", "START", "비인기 상품 정리를 시작합니다.")
        outdated_keywords = strategy.get('out_dated_keywords', [])
        cleanup_targets = self.analysis_agent.find_cleanup_targets(outdated_keywords)
        
        cleanup_count = 0
        for item in cleanup_targets:
            m_code = item.get('market_code', 'COUPANG')
            reason = item.get('reason', '비인기')
            if dry_run:
                logger.info(f"[DRY-RUN] Deleting {item['market_item_id']} (Reason: {reason})")
                self._record_event("OPTIMIZATION", "IN_PROGRESS", f"[테스트] {m_code} 상품 삭제 예정: {item['market_item_id']} ({reason})")
            else:
                import uuid
                try:
                    acc_id = uuid.UUID(item['market_account_id'])
                    self._record_event("OPTIMIZATION", "IN_PROGRESS", f"{m_code} 상품 삭제 중: {item['market_item_id']}")
                    self.market_service.delete_product(m_code, acc_id, item['market_item_id'])
                    cleanup_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete product {item['market_item_id']}: {e}")
                    self._record_event("OPTIMIZATION", "FAIL", f"상품 삭제 실패: {item['market_item_id']}")

        self._record_event("OPTIMIZATION", "SUCCESS", f"상품 정리 완료 ({cleanup_count}개 삭제)")

        # 2.5 Supplier Sync: 공급사 전체 상품 수집 (백그라운드)
        if not dry_run:
            self._record_event("SOURCING", "IN_PROGRESS", "공급사(오너클랜) 전체 기간 상품 수집을 백그라운드에서 시작합니다.")
            await self.sourcing_service.trigger_full_supplier_sync()
            
            # 이전 수집분에서 미가공된 데이터들 후보군으로 가져오기
            imported_count = self.sourcing_service.import_from_raw(limit=5000)
            if imported_count > 0:
                self._record_event("SOURCING", "IN_PROGRESS", f"기존 수집 데이터 {imported_count}건을 소싱 후보로 전환했습니다.")


        # 3. Sourcing: 새로운 상품 소싱
        target_keywords = strategy.get('target_keywords', [])
        if target_keywords:
            self._record_event("SOURCING", "START", f"상품 소싱을 시작합니다. (키워드: {', '.join(target_keywords[:5])})")
            for kw in target_keywords[:30]: # 모든 도출된 키워드 활용 (최대 30개)
                self._record_event("SOURCING", "IN_PROGRESS", f"키워드 분석 및 소싱 중: {kw}")
                if not dry_run:
                    try:
                        # 확장 소싱 시 각 키워드당 더 많은 상품을 가져오도록 시도
                        await self.sourcing_service.execute_expanded_sourcing(kw)
                        self._record_event("SOURCING", "IN_PROGRESS", f"키워드 '{kw}' 소싱 완료")
                    except Exception as e:
                        logger.error(f"Sourcing failed for keyword {kw}: {e}")
                        self._record_event("SOURCING", "FAIL", f"키워드 '{kw}' 소싱 실패: {str(e)[:50]}")
                else:
                    self._record_event("SOURCING", "IN_PROGRESS", f"[테스트] 키워드 '{kw}' 소싱 시뮬레이션 완료")
            self._record_event("SOURCING", "SUCCESS", "전체 상품 소싱 프로세스 완료")
        else:
            self._record_event("SOURCING", "SUCCESS", "소싱할 키워드가 없습니다.")

        # 4. [Step 1] 가공 및 선등록 (Fast Listing: 상품명 위주)
        if not dry_run:
            self._record_event("LISTING", "START", "신규 상품 대량 가공 및 마켓 등록을 시작합니다.")
            processed_count = await self.processing_service.process_pending_products(limit=15000) # 대량 가공 (최대 1.5만건)
            logger.info(f"Step 1: Processed {processed_count} new products for fast listing.")
            
            # 활성 계정 조회
            from app.models import MarketAccount, Product
            stmt_acc = select(MarketAccount).where(MarketAccount.is_active == True)
            accounts = self.db.scalars(stmt_acc).all()
            
            # 가공 완료된(COMPLETED) 최근 상품들 등록 (계정당 5000개 목표 기준, 총 15000개 시도)
            stmt_prod = select(Product).where(Product.processing_status == "COMPLETED").order_by(Product.updated_at.desc()).limit(15000)
            products = self.db.scalars(stmt_prod).all()
            
            listing_count = 0
            for i, p in enumerate(products):
                self._record_event("LISTING", "IN_PROGRESS", f"상품 전역 분산 등록 준비: {p.name[:20]}...")
                
                # 모든 계정을 통틀어 단 하나의 계정만 선택 (전역 Round-Robin)
                target_acc = accounts[i % len(accounts)]
                market_code = target_acc.market_code
                
                try:
                    self._record_event("LISTING", "IN_PROGRESS", f"전역 할당: {market_code} 계정({target_acc.name})")
                    res = self.market_service.register_product(market_code, target_acc.id, p.id)
                    
                    if res.get("status") == "success":
                        listing_count += 1
                        self._record_event("LISTING", "IN_PROGRESS", f"등록 성공: {p.name[:15]} ({target_acc.name})")
                    else:
                        error_msg = res.get("message", "알 수 없는 오류")
                        logger.error(f"Listing failed for product {p.id} on {market_code}: {error_msg}")
                        self._record_event("LISTING", "FAIL", f"등록 실패 ({target_acc.name}): {error_msg[:50]}")
                except Exception as e:
                    logger.error(f"Exception during listing for product {p.id} on {target_acc.name}: {e}")
                    self._record_event("LISTING", "FAIL", f"시스템 오류 ({target_acc.name}): {str(e)[:50]}")
            
            self._record_event("LISTING", "SUCCESS", f"가공 {processed_count}건, 전역 분산 등록 {listing_count}건 완료")
        else:
            self._record_event("LISTING", "SUCCESS", "Dry-run 모드이므로 등록을 건너뜁니다.")

        # 5. [Step 2] 판매 상품 상세화 가공 준비
        self._record_event("PREMIUM", "START", "프리미엄 최적화 대상 상품을 선별합니다.")
        winning_products = self.processing_service.get_winning_products_for_processing(limit=5)
        
        for wp in winning_products:
            logger.info(f"Winner identified: {wp.name} (Sales: Identified). Ready for manual premium optimization.")

        self._record_event("PREMIUM", "SUCCESS", f"최적화 대상 {len(winning_products)}건 선별 완료 (수동 승인 대기)")

        logger.info("Daily AI Orchestration Cycle Completed.")
        self._record_event("COMPLETE", "SUCCESS", "데일리 오케스트레이션 사이클이 모두 완료되었습니다.")
        return strategy
