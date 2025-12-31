import logging
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.models import PricingRecommendation, PriceChangeLog, MarketAccount, ProfitSnapshot, PricingSettings, MarketListing
from app.services.pricing.experiment_manager import ExperimentManager
from app.services.pricing.strategy_resolver import StrategyResolver
from app.services.pricing.autonomy_guard import AutonomyGuard

logger = logging.getLogger(__name__)

class PriceEnforcer:
    """
    권고된 가격을 실제 마켓 API를 통해 반영하고 이력을 관리하는 엔진입니다.
    안전장치(Guardrails)를 통해 운영 리스크를 최소화합니다.
    """
    def __init__(self, session: Session):
        self.session = session

    async def process_recommendations(self, mode: str = "SHADOW", max_items: int = 10):
        """
        대기 중인 권고 사항들을 배치로 처리합니다.
        
        Args:
            mode: SHADOW (시뮬레이션), ENFORCE (실제 반영), ENFORCE_LITE (역마진만 반영)
            max_items: 1회 처리 최대 건수
        """
        pending_recs = self.session.query(PricingRecommendation).filter_by(
            status="PENDING"
        ).limit(max_items).all()
        
        logger.info(f"[PriceEnforcer] Processing {len(pending_recs)} pending recommendations in {mode} mode.")
        
        count = 0
        for rec in pending_recs:
            try:
                await self.enforce(rec, mode=mode)
                count += 1
            except Exception as e:
                logger.error(f"Failed to enforce recommendation {rec.id}: {e}")
                
        return count

    async def enforce(self, recommendation: PricingRecommendation, mode: str = "SHADOW"):
        """
        단건 권고 사항을 마켓에 반영합니다.
        """
        # 0. 정책 및 실험군 정보 가져오기
        exp_manager = ExperimentManager(self.session)
        policy = exp_manager.get_effective_policy(recommendation.product_id, recommendation.market_account_id)
        
        # 'AUTO' 모드인 경우 정책의 기본 설정을 따름
        active_mode = mode
        if mode == "AUTO":
            active_mode = policy.get("auto_mode", "SHADOW")

        # 1. 전략 및 안전장치 검증 (Safety Guardrails)
        # 우선순위: 추천 생성 시 사용된 전략(strategy_id) > 실시간 Resolver
        strategy = None
        if hasattr(recommendation, "strategy_id") and recommendation.strategy_id:
            from app.models import PricingStrategy
            strategy = self.session.get(PricingStrategy, recommendation.strategy_id)

        if not strategy:
            listing = self.session.query(MarketListing).filter_by(
                product_id=recommendation.product_id, 
                market_account_id=recommendation.market_account_id
            ).first()
            
            resolver = StrategyResolver(self.session)
            strategy = resolver.resolve_strategy(recommendation.product_id, category_code=listing.category_code if listing else None)

        is_safe, reason = self._check_safety(recommendation, strategy)
        if not is_safe:
            logger.warning(f"[PriceEnforcer] Safety check failed for recommendation {recommendation.id}: {reason}")
            recommendation.status = "REJECTED"
            recommendation.reasons = (recommendation.reasons or []) + [f"Safety Rejection: {reason}"]
            self.session.commit()
            return

        if active_mode == "SHADOW":
            logger.info(f"[PriceEnforcer:SHADOW] Product {recommendation.product_id}: {recommendation.current_price} -> {recommendation.recommended_price}")
            return

        # 2. 자율성 가드 (Autonomy Guard) 검사
        if active_mode in ["ENFORCE_LITE", "ENFORCE_AUTO"]:
            from app.models import Product, MarketAccount
            product = self.session.get(Product, recommendation.product_id)
            account = self.session.get(MarketAccount, recommendation.market_account_id)
            
            listing = self.session.query(MarketListing).filter_by(
                product_id=recommendation.product_id, 
                market_account_id=recommendation.market_account_id
            ).first()

            metadata = {
                "vendor": account.market_code if account else "UNKNOWN",
                "channel": account.market_code if account else "UNKNOWN",
                "category_code": listing.category_code if listing else None,
                "strategy_id": recommendation.strategy_id,
                "lifecycle_stage": product.lifecycle_stage if product else "STEP_1"
            }
            logger.info(f"[PriceEnforcer] Metadata for Autonomy Check: {metadata}")

            guard = AutonomyGuard(self.session)
            if not guard.check_autonomy(recommendation, metadata):
                logger.info(f"[PriceEnforcer] Autonomy check returned False for recommendation {recommendation.id}")
                return

        # 3. 추가 보호 장치 (자동 모드인 경우에만 적용)
        if active_mode in ["ENFORCE_LITE", "ENFORCE_AUTO"]:
            # 쿨다운 확인
            is_cool, cooldown_reason = self._check_cooldown(recommendation, policy)
            if not is_cool:
                logger.warning(f"[PriceEnforcer] Cooldown active for {recommendation.product_id}: {cooldown_reason}")
                return

            # 스로틀링 확인
            is_throttled, throttle_reason = self._check_throttling(recommendation.market_account_id, policy)
            if is_throttled:
                logger.warning(f"[PriceEnforcer] Throttled for account {recommendation.market_account_id}: {throttle_reason}")
                return

        # 2. 실제 마켓 반영 (Phase 3 상세 구현 대상)
        # TODO: MarketAccount별 Client (Coupang/SmartStore) 로드 및 update_price 호출
        success, error_msg = await self._apply_to_market_api(recommendation)
        
        # 3. 이력 기록 및 상태 업데이트
        log = PriceChangeLog(
            product_id=recommendation.product_id,
            market_account_id=recommendation.market_account_id,
            old_price=recommendation.current_price,
            new_price=recommendation.recommended_price,
            source="AUTO_ENFORCE",
            recommendation_id=recommendation.id,
            status="SUCCESS" if success else "FAIL",
            error_msg=error_msg
        )
        self.session.add(log)
        
        if success:
            recommendation.status = "APPLIED"
        else:
            recommendation.status = "FAIL"
            
        self.session.commit()

    def _check_safety(self, rec: PricingRecommendation, strategy: Optional[Any] = None) -> tuple[bool, str | None]:
        """
        급격한 가격 변동이나 비상식적인 가격 설정을 차단합니다.
        """
        from app.models import PricingStrategy

        if rec.current_price <= 0:
            return False, "Invalid current price"
            
        delta_rate = abs(rec.recommended_price - rec.current_price) / rec.current_price
        
        # 1. 변동폭 제한 (기본 20%, 전략에 따라 오버라이드)
        max_delta = 0.20
        if strategy and isinstance(strategy, PricingStrategy):
            max_delta = strategy.max_price_delta

        if delta_rate > max_delta:
            return False, f"Price delta too high ({int(delta_rate*100)}% > {int(max_delta*100)}%)"
            
        # 2. 절대액 제한 (예: 10만원 이상 급격한 변동 차단)
        if abs(rec.recommended_price - rec.current_price) > 100000:
            return False, "Price delta exceeds absolute limit (100,000 KRW)"
            
        # 3. 최저가 보호 (전략의 min_margin_gate를 활용할 수도 있으나 여기서는 절대 가격 기준)
        if rec.recommended_price < 1000:
            return False, "Recommended price below minimum gate (1,000 KRW)"
            
        return True, None

    async def _apply_to_market_api(self, rec: PricingRecommendation) -> tuple[bool, str | None]:
        """
        실제 마켓 API를 호출하여 가격을 수정합니다.
        """
        logger.info(f"[PriceEnforcer:ENFORCE] Calling Market API for product {rec.product_id} to set price {rec.recommended_price}")
        # Phase 3 이후 실제 API 연동 로직 추가 예정
        return True, None

    def _get_settings(self, account_id: UUID) -> PricingSettings | None:
        """계정별 자동화 설정을 조회합니다."""
        return self.session.query(PricingSettings).filter_by(market_account_id=account_id).first()

    def _check_throttling(self, account_id: UUID, policy: dict) -> tuple[bool, str | None]:
        """시간당 최대 변경 횟수를 초과했는지 확인합니다."""
        limit = policy.get("max_changes_per_hour", 50)
        
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        count = self.session.query(func.count(PriceChangeLog.id)).filter(
            PriceChangeLog.market_account_id == account_id,
            PriceChangeLog.status == "SUCCESS",
            PriceChangeLog.created_at >= one_hour_ago
        ).scalar()
        
        if count >= limit:
            return True, f"Hourly limit reached ({count} >= {limit})"
        return False, None

    def _check_cooldown(self, rec: PricingRecommendation, policy: dict) -> tuple[bool, str | None]:
        """동일 상품에 대해 최근 가격 변경이 있었는지 확인합니다."""
        cooldown = policy.get("cooldown_hours", 24)
        
        cooldown_ago = datetime.now(timezone.utc) - timedelta(hours=cooldown)
        last_log = self.session.query(PriceChangeLog).filter(
            PriceChangeLog.product_id == rec.product_id,
            PriceChangeLog.market_account_id == rec.market_account_id,
            PriceChangeLog.status == "SUCCESS",
            PriceChangeLog.created_at >= cooldown_ago
        ).order_by(desc(PriceChangeLog.created_at)).first()
        
        if last_log:
            return False, f"Recent change at {last_log.created_at} (Cooldown: {cooldown}h)"
        return True, None

    def _is_negative_profit(self, product_id: UUID) -> bool:
        """가장 최근의 수익 분석 결과가 역마진인지 확인합니다."""
        snapshot = self.session.query(ProfitSnapshot).filter_by(
            product_id=product_id
        ).order_by(desc(ProfitSnapshot.created_at)).first()
        
        if snapshot and snapshot.estimated_profit < 0:
            return True
        return False
