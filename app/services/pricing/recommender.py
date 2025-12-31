import logging
import math
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import CostComponent, PricingRecommendation, MarketFeePolicy, MarketListing
from app.services.pricing.experiment_manager import ExperimentManager
from app.services.pricing.strategy_resolver import StrategyResolver

logger = logging.getLogger(__name__)

class PricingRecommender:
    """
    원가, 수수료, 목표 마진을 분석하여 최적의 판매 가격을 권고하는 엔진입니다.
    """
    def __init__(self, session: Session):
        self.session = session

    def recommend_for_product(self, product_id: UUID, channel: str, account_id: UUID, current_price: int) -> PricingRecommendation | None:
        """
        특정 상품 및 채널에 대한 권장 판매가를 산출합니다.
        """
        # 1. 정책 및 실험군 정보 가져오기
        exp_manager = ExperimentManager(self.session)
        policy = exp_manager.get_effective_policy(product_id, account_id)
        
        # 2. 전략 분석 (PR-13: Category Strategy)
        # 해당 마켓 리스팅 정보 조회 (카테고리 코드 추출용)
        listing = self.session.query(MarketListing).filter_by(
            product_id=product_id, 
            market_account_id=account_id
        ).first()
        
        resolver = StrategyResolver(self.session)
        strategy = resolver.resolve_strategy(product_id, category_code=listing.category_code if listing else None)
        
        # PR-14: 실험군 정책에서 전략 ID 오버라이드가 있는 경우 적용
        experiment_strategy_id = policy.get("strategy_id")
        if experiment_strategy_id:
            from app.models import PricingStrategy
            exp_strategy = self.session.get(PricingStrategy, experiment_strategy_id)
            if exp_strategy:
                strategy = exp_strategy
        
        # 3. 원가 데이터 확인
        cost = self.session.query(CostComponent).filter_by(product_id=product_id).first()
        if not cost:
            return None

        # 4. 수수료율 및 목표 마진 결정
        fee_rate = self._get_fee_policy_rate(channel)
        
        # 우선순위: 전략(Strategy) > 실험(Experiment) > 기본(PricingSettings) > 하드코딩(15%)
        target_margin = 0.15
        if strategy:
            target_margin = strategy.target_margin
        else:
            target_margin = policy.get("target_margin", 0.15)
        
        # 4. 권장 가격 산출 (역산식)
        # RP = (원가 + 배송비 + 기타) / (1 - 수수료율 - 목표마진율)
        fixed_costs = cost.supply_price + cost.shipping_cost + cost.extra_fee
        denominator = 1 - fee_rate - target_margin
        
        if denominator <= 0:
            logger.error(f"[PricingRecommender] Target margin ({target_margin}) + Fee ({fee_rate}) exceeds 100% for product {product_id}")
            return None
            
        recommended_price = int(fixed_costs / denominator)
        
        # 4. 가격 보정 (심리적 가격 또는 마켓 관례에 따라 10원 단위 올림)
        recommended_price = self._round_price(recommended_price)
        
        # 5. 권고 생성 필요성 확인
        # 현재가와 권장가 차이가 1% 미만이면 권고 생성 안함 (노이즈 방지)
        if abs(recommended_price - current_price) < (current_price * 0.01):
            return None
            
        reasons = [f"Target margin maintenance: {int(target_margin * 100)}%"]
        if recommended_price > current_price:
            reasons.append("Cost inclusion for sustainable profit")
        else:
            reasons.append("Increased price competitiveness while maintaining margin")

        # 6. 신뢰도 산출 (Dynamic Confidence)
        # 기본 0.8 / 역마진인 경우 +0.15 / 변동폭이 10% 이내인 경우 +0.05
        confidence = 0.8
        total_costs = fixed_costs + (current_price * fee_rate)
        cost_margin = (current_price - total_costs) / current_price if current_price > 0 else 0
        if cost_margin < 0:
            confidence += 0.15
        
        delta_rate = abs(recommended_price - current_price) / current_price if current_price > 0 else 0
        if delta_rate < 0.10:
            confidence += 0.05
            
        confidence = min(1.0, confidence)

        return PricingRecommendation(
            product_id=product_id,
            market_account_id=account_id,
            current_price=current_price,
            recommended_price=recommended_price,
            expected_margin=target_margin,
            confidence=confidence,
            reasons=reasons,
            status="PENDING",
            experiment_id=policy.get("experiment_id"),
            experiment_group=policy.get("experiment_group"),
            strategy_id=strategy.id if strategy else None
        )

    def _get_fee_policy_rate(self, channel: str) -> float:
        """마켓별 기본 수수료 정책 조회"""
        policy = self.session.query(MarketFeePolicy).filter_by(market_code=channel.upper()).first()
        if policy:
            return policy.fee_rate
        # 기본값: 쿠팡/네이버 평균 수준인 12% 적용
        return 0.12

    def _round_price(self, price: int) -> int:
        """이커머스 관례에 따른 가격 단위 보정 (10원 단위 올림)"""
        if price <= 0: return 0
        return math.ceil(price / 10) * 10
