import logging
import datetime
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.services.ai.service import AIService
from app.services.ai.agents.sourcing_agent import SourcingAgent
from app.services.ai.agents.processing_agent import ProcessingAgent
from app.services.sourcing_service import SourcingService
from app.services.processing_service import ProcessingService
from app.services.market_service import MarketService
from app.services.ai.exceptions import (
    DatabaseError,
    WorkflowError,
    wrap_exception
)
from app.services.lifecycle_scheduler import get_lifecycle_scheduler

from app.models import OrchestrationEvent, Product, MarketAccount, SupplierItemRaw, SourcingCandidate, SystemSetting, OrderItem, Order

logger = logging.getLogger(__name__)

class OrchestratorService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.sourcing_agent = SourcingAgent(db)
        self.processing_agent = ProcessingAgent(db)
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
            wrapped_error = wrap_exception(
                e,
                DatabaseError,
                table_name="orchestration_events",
                operation="insert",
                recoverable=True
            )
            logger.error(f"Failed to record event: {wrapped_error}")
            self.db.rollback()

    def _get_best_sellers(self, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
        """
        최근 판매량이 높은 상품 정보를 가져옵니다. (RAG용)
        """
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
            wrapped_error = wrap_exception(
                e,
                DatabaseError,
                table_name="products",
                operation="select",
                recoverable=True
            )
            logger.warning(f"Failed to fetch best sellers context: {wrapped_error}")
            return []

    async def run_daily_cycle(self, dry_run: bool = True):
        """
        매일 실행되는 자율 운영 루프입니다.
        (Planning -> Optimization -> Sourcing -> Step1: Listing -> Step2: Premium)
        """
        try:
            logger.info(f"Starting Daily AI Orchestration Cycle (dry_run={dry_run})...")
            self._record_event("PLANNING", "START", "전략 수립을 시작합니다.", {"dry_run": dry_run})
            
            # 0. 설정 로드
            setting = self.db.query(SystemSetting).filter_by(key="orchestrator").one_or_none()
            config = setting.value if setting else {
                "listing_limit": 15000,
                "sourcing_keyword_limit": 30,
                "sourcing_import_limit": 15000,
                "initial_processing_batch": 100,
                "processing_batch_size": 50,
                "listing_concurrency": 5,
                "listing_batch_limit": 100,
                "backfill_approve_enabled": True,
                "backfill_approve_limit": 2000,
                "continuous_mode": False,
            }
            
            listing_limit = config.get("listing_limit", 15000)
            keyword_limit = config.get("sourcing_keyword_limit", 30)
            sourcing_import_limit = config.get("sourcing_import_limit", 15000)
            initial_processing_batch = config.get("initial_processing_batch", 100)
            processing_batch_size = config.get("processing_batch_size", 50)
            listing_concurrency = config.get("listing_concurrency", 5)
            listing_batch_limit = config.get("listing_batch_limit", 100)
            backfill_approve_enabled = config.get("backfill_approve_enabled", True)
            backfill_approve_limit = config.get("backfill_approve_limit", 2000)
            continuous_mode = config.get("continuous_mode", False)

            # 1. Planning: 시즌성 판단 및 전략 수립
            best_sellers = self._get_best_sellers()
            strategy = await self.ai_service.plan_seasonal_strategy(context_products=best_sellers)
            season_name = strategy.get('season_name')
            theme = strategy.get('strategy_theme')
            logger.info(f"Today's Strategy: {season_name} - {theme} (Listing Limit: {listing_limit}, Keyword Limit: {keyword_limit})")
            self._record_event("PLANNING", "SUCCESS", f"전략 수립 완료: {season_name} ({theme}) [Limit: {listing_limit}]", strategy)
            
            # 2. Optimization: 비인기/오프시즌 상품 정리
            self._record_event("OPTIMIZATION", "START", "비인기 상품 정리를 시작합니다.")
            outdated_keywords = strategy.get('out_dated_keywords', [])
            # SourcingAgent를 사용하여 비인기 상품 정리
            cleanup_targets = self.sourcing_agent.find_cleanup_targets(outdated_keywords)
            
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
                imported_count = await asyncio.to_thread(
                    self.sourcing_service.import_from_raw,
                    limit=int(sourcing_import_limit),
                )
                if imported_count > 0:
                    self._record_event("SOURCING", "IN_PROGRESS", f"기존 수집 데이터 {imported_count}건을 소싱 후보로 전환했습니다.")

                # [병렬화/최적화] 워커 유무와 상관없이 가공 및 등록 워커를 여기서 미리 조기 가동
                # 그래야 키워드 소싱이 오래 걸려도 기존 데이터 가공이 즉시 시작됨
                logger.info("Early Triggering Continuous Processing & Listing in background...")
                asyncio.create_task(self.run_continuous_processing())
                if continuous_mode:
                    asyncio.create_task(self.run_continuous_listing())

            # 3. Sourcing: 새로운 상품 소싱
            target_keywords = strategy.get('target_keywords', [])
            if target_keywords:
                self._record_event("SOURCING", "START", f"상품 소싱을 시작합니다. (키워드: {', '.join(target_keywords[:5])})")
                for kw in target_keywords[:keyword_limit]: # 설정된 키워드 한도 활용
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
                self._record_event("SOURCING", "SUCCESS", "전체 키워드 기반 소싱 프로세스 완료")
            else:
                self._record_event("SOURCING", "SUCCESS", "소싱할 신규 키워드가 없어 기존 데이터를 활용합니다.")
                
            # [추가] 목표 수량 대비 부족할 경우 백필 승인 (Backfill Approval)
            # 키워드 소싱 여부와 관계없이 실행되어야 함
            candidates_to_approve = []
            if not dry_run and backfill_approve_enabled:
                stmt_approved = select(Product).where(Product.created_at >= select(func.current_date()))
                today_count = self.db.execute(select(func.count()).select_from(stmt_approved)).scalar() or 0
                
                if today_count < listing_limit:
                    shortfall = min(listing_limit - today_count, int(backfill_approve_limit))
                    self._record_event("SOURCING", "IN_PROGRESS", f"목표 수량 대비 {shortfall}건 부족하여 추가 승인을 진행합니다.")
                    
                    stmt_pending = (
                        select(SourcingCandidate)
                        .where(SourcingCandidate.status == "PENDING")
                        .order_by(SourcingCandidate.final_score.desc())
                        .limit(shortfall)
                    )
                    candidates_to_approve = self.db.scalars(stmt_pending).all()
                    
                    for candidate in candidates_to_approve:
                        try:
                            await self.sourcing_service.approve_candidate(candidate.id)
                        except Exception as e:
                            logger.error(f"Backfill approval failed for {candidate.id}: {e}")
                    
                    if candidates_to_approve:
                        self._record_event("SOURCING", "SUCCESS", f"추가 {len(candidates_to_approve)}건 승인 완료")

            # [이동됨] 워커 트리거는 위에서 이미 수행됨

            # 4. [Step 1] 가공 및 선등록 (Fast Listing: 상품명 위주)
            if not dry_run:
                self._record_event("LISTING", "START", f"신규 상품 대량 가공 및 마켓 등록을 시작합니다. (Target: {listing_limit})")
                
                # [최적화] 메인 루프에서 listing_limit 전체를 한 번에 가공하면 너무 오래 블로킹됨
                # 초기 부팅을 위해 작은 배치(예: 100건)만 블로킹 방식으로 처리하고, 나머지는 백그라운드 워커에 위임
                processed_count = await self.processing_service.process_pending_products(
                    limit=int(initial_processing_batch),
                )
                logger.info(f"Step 1: Processed initial batch of {processed_count} products. Remaining {listing_limit - processed_count} left for background worker.")
                
                # 활성 계정 조회
                from app.session_factory import session_factory
                from app.services.market_targeting import decide_target_market_for_product
                stmt_acc = select(MarketAccount).where(MarketAccount.is_active == True)
                accounts = self.db.scalars(stmt_acc).all()
                
                if not accounts:
                    logger.warning("No active market accounts found. Skipping listing step.")
                    self._record_event("LISTING", "SUCCESS", "활성 마켓 계정이 없어 등록 작업을 건너뛰었습니다.")
                    return strategy
                
                # 가공 완료된(COMPLETED) 최근 상품들 등록 (설정된 한도 적용)
                stmt_prod = select(Product).where(Product.processing_status == "COMPLETED").order_by(Product.updated_at.desc()).limit(listing_limit)
                products = self.db.scalars(stmt_prod).all()
                
                accounts_by_market: dict[str, list[MarketAccount]] = {}
                for acc in accounts:
                    accounts_by_market.setdefault(acc.market_code, []).append(acc)

                # 병렬 등록을 위한 세마포어 (마켓 API 부하 조절)
                register_sem = asyncio.Semaphore(int(listing_concurrency)) # 마켓별 동시성 제한
                
                async def _register_task(idx, p_id):
                    async with register_sem:
                        # 각 테스크마다 독립된 DB 세션 사용
                        with session_factory() as tmp_db:
                            from app.services.market_service import MarketService
                            m_service = MarketService(tmp_db)
                            
                            try:
                                # Product 객체를 새로운 세션에서 다시 가져오기
                                p = tmp_db.get(Product, p_id)
                                if not p: return False

                                target_market, reason = decide_target_market_for_product(tmp_db, p)
                                target_accounts = accounts_by_market.get(target_market, [])
                                if not target_accounts:
                                    if target_market != "SMARTSTORE" and accounts_by_market.get("SMARTSTORE"):
                                        logger.info(
                                            "No %s accounts; fallback to SMARTSTORE (product=%s, reason=%s)",
                                            target_market,
                                            p.id,
                                            reason,
                                        )
                                        target_market = "SMARTSTORE"
                                        target_accounts = accounts_by_market.get("SMARTSTORE", [])
                                    else:
                                        logger.warning(
                                            "No target accounts for %s (product=%s, reason=%s)",
                                            target_market,
                                            p.id,
                                            reason,
                                        )
                                        return False

                                target_acc = target_accounts[idx % len(target_accounts)]
                                res = m_service.register_product(target_market, target_acc.id, p.id)
                                return res.get("status") == "success"
                            except Exception as e:
                                logger.error(f"Async listing failed for product {p_id}: {e}")
                                return False

                tasks = [_register_task(i, p.id) for i, p in enumerate(products)]
                results = await asyncio.gather(*tasks)
                listing_count = sum(1 for r in results if r)
                
                self._record_event("LISTING", "SUCCESS", f"가공 {processed_count}건, 전역 분산 등록 {listing_count}건 완료")
            else:
                self._record_event("LISTING", "SUCCESS", "Dry-run 모드이므로 등록을 건너뜁니다.")

            # 5. [Step 2] 판매 상품 상세화 가공 준비
            self._record_event("PREMIUM", "START", "프리미엄 최적화 대상 상품을 선별합니다.")
            winning_products = self.processing_service.get_winning_products_for_processing(limit=5)
            
            for wp in winning_products:
                logger.info(f"Auto-triggering premium content processing for winner: {wp.name}")
                # 프리미엄 가공 실행 (AI 이미지 생성 등)
                await self.processing_service.process_winning_product(wp.id)

            self._record_event("PREMIUM", "SUCCESS", f"최적화 대상 {len(winning_products)}건 자동 가공 및 승인 대기 처리 완료")

            # 6. [Analysis] 기존 상품 재주문 자동 스캔 및 추천 생성
            if not dry_run:
                self._record_event("REORDER_ANALYSIS", "START", "판매 중인 상품의 재주문 필요 여부를 스캔합니다.")
                from app.services.sourcing_recommendation_service import SourcingRecommendationService
                rec_service = SourcingRecommendationService(self.db)
                # 최근 판매 상품 위주 30건 스캔
                reorder_recs = await rec_service.generate_bulk_recommendations(limit=30, recommendation_type="REORDER")
                self._record_event("REORDER_ANALYSIS", "SUCCESS", f"재주문 분석 완료 ({len(reorder_recs)}건의 추천 생성/갱신)")
            else:
                self._record_event("REORDER_ANALYSIS", "SUCCESS", "Dry-run 모드이므로 재주문 분석을 건너뜁니다.")

            logger.info("Daily AI Orchestration Cycle Completed.")
            
            # [라이프사이클 자동 전환] STEP 1 → 2, STEP 2 → 3 전환 체크 및 자동 전환 수행
            logger.info("Starting Lifecycle Transition Check...")
            lifecycle_scheduler = get_lifecycle_scheduler()
            # 실제 전환 수행 (dry_run=False)
            lifecycle_results = await lifecycle_scheduler.check_and_transition_all(dry_run=dry_run, auto_transition=True)
            logger.info(f"Lifecycle Transition Check Complete: "
                       f"STEP1→2 {lifecycle_results['step1_to_step2']['transitioned']}건, "
                       f"STEP2→3 {lifecycle_results['step2_to_step3']['transitioned']}건")
            
            self._record_event("COMPLETE", "SUCCESS", "데일리 오케스트레이션 사이클이 모두 완료되었습니다.", {
                "lifecycle_transitions": lifecycle_results
            })
            
            # [지속 모드] 활성화 시 백그라운드 독립 실행 (이미 앞에서 실행했다면 중복 실행 방지 로직 필요할 수 있으나 상태 기반이므로 안전)
            if not dry_run and continuous_mode:
                # 이미 Sourcing 단계에서 실행되었을 것이나, 확실히 하기 위해 한 번 더 체크 가능
                pass
            
            return strategy
        except Exception as e:
            wrapped_error = wrap_exception(
                e,
                WorkflowError,
                workflow_name="daily_cycle",
                step="run_daily_cycle"
            )
            logger.error(f"Daily AI Orchestration Cycle failed: {wrapped_error}")
            self._record_event("COMPLETE", "FAIL", f"데일리 오케스트레이션 실패: {str(e)[:50]}")
            return None

    async def run_continuous_processing(self):
        """
        [병력화] PENDING 상태인 상품을 지속적으로 찾아 AI 가공을 수행합니다.
        독립된 세션을 사용하여 비동기 실행 안정성 확보.
        """
        try:
            logger.info("Starting Continuous Processing Worker...")
            from app.session_factory import session_factory
            
            while True:
                try:
                    with session_factory() as db:
                        # 설정 확인
                        setting = db.query(SystemSetting).filter_by(key="orchestrator").one_or_none()
                        processing_batch_size = 50
                        if setting and setting.value:
                            processing_batch_size = setting.value.get("processing_batch_size", 50)
                        
                        # 가공 대기 상품 조회
                        stmt = (
                            select(Product.id)
                            .where(Product.processing_status == "PENDING")
                            .limit(int(processing_batch_size))
                        )
                        p_ids = db.scalars(stmt).all()
                        
                        if not p_ids:
                            logger.debug("No more products to process. Worker sleeping...")
                            await asyncio.sleep(20)
                            continue
                        
                        # 가공 서비스 인스턴스를 루프 내에서 새로 생성 (세션 바인딩)
                        from app.services.processing_service import ProcessingService
                        ps = ProcessingService(db)
                        processed_count = await ps.process_pending_products(limit=int(processing_batch_size))
                        logger.info(f"Continuous Processing: Batch processed {processed_count} products.")
                except Exception as e:
                    wrapped_error = wrap_exception(
                        e,
                        DatabaseError,
                        table_name="products",
                        operation="select",
                        recoverable=True
                    )
                    logger.error(f"Error in Continuous Processing Worker: {wrapped_error}")
                    await asyncio.sleep(5)
                
                await asyncio.sleep(2)
        except Exception as e:
            wrapped_error = wrap_exception(
                e,
                WorkflowError,
                workflow_name="continuous_processing",
                step="run_continuous_processing"
            )
            logger.error(f"Continuous Processing Worker failed: {wrapped_error}")

    async def run_continuous_listing(self):
        """
        [지속 모드/병렬화] 가공 완료(COMPLETED) 상태인 상품을 지속적으로 찾아 등록합니다.
        """
        logger.info("Starting Continuous Listing Mode...")
        self._record_event("CONTINUOUS", "START", "지속 등록 모드를 시작합니다.")
        from app.session_factory import session_factory
        
        while True:
            try:
                with session_factory() as db:
                    # 설정 확인 (중간에 꺼질 수도 있으므로)
                    setting = db.query(SystemSetting).filter_by(key="orchestrator").one_or_none()
                    if not setting or not setting.value.get("continuous_mode"):
                        logger.info("Continuous mode disabled. Stopping.")
                        break
                    listing_batch_limit = setting.value.get("listing_batch_limit", 100)
                    listing_concurrency = setting.value.get("listing_concurrency", 5)

                    # 활성 계정 조회
                    stmt_acc = select(MarketAccount).where(MarketAccount.is_active == True)
                    accounts = db.scalars(stmt_acc).all()
                    if not accounts:
                        logger.warning("No active market accounts. Continuous listing waiting...")
                        await asyncio.sleep(60)
                        continue
                    
                    # 미등록 상품 조회 (배치 단위로 처리)
                    stmt_prod = (
                        select(Product)
                        .where(Product.processing_status == "COMPLETED")
                        .limit(int(listing_batch_limit))
                    )
                    products = db.scalars(stmt_prod).all()
                    
                    if not products:
                        logger.debug("No more products to list. Continuous mode waiting.")
                        await asyncio.sleep(30)
                        continue

                    # 병렬 등록
                    register_sem = asyncio.Semaphore(int(listing_concurrency))
                    
                    async def _task(idx, p_id):
                        async with register_sem:
                            with session_factory() as tmp_db:
                                from app.services.market_service import MarketService
                                m_service = MarketService(tmp_db)
                                target_acc = accounts[idx % len(accounts)]
                                try:
                                    res = m_service.register_product(target_acc.market_code, target_acc.id, p_id)
                                    return res.get("status") == "success"
                                except: return False

                    tasks = [_task(i, p.id) for i, p in enumerate(products)]
                    await asyncio.gather(*tasks)
                    
                    logger.info(f"Continuous Listing: Batch of {len(products)} processed.")
            except Exception as e:
                logger.error(f"Error in Continuous Listing Worker: {e}")
                await asyncio.sleep(10)
            
            await asyncio.sleep(2) # API 부하 방지
