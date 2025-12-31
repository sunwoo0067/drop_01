import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Product, CostComponent, ProfitSnapshot, MarketFeePolicy

logger = logging.getLogger(__name__)

class ProfitGuard:
    """
    상품의 원가, 수수료, 배송비를 기반으로 실시간 수익성을 분석하고 역마진을 감지하는 엔진입니다.
    """
    def __init__(self, session: Session):
        self.session = session

    def analyze_product(self, product_id: UUID, channel: str, current_price: int) -> ProfitSnapshot:
        """
        특정 채널의 현재 판매 가격을 기준으로 수익성을 분석합니다.
        
        Args:
            product_id: 분석 대상 상품 ID
            channel: 판매 채널 (COUPANG, NAVER 등)
            current_price: 현재 판매가
        """
        # 1. 원가 정보 조회
        cost = self.session.query(CostComponent).filter_by(product_id=product_id).first()
        if not cost:
            logger.warning(f"[ProfitGuard] No cost component found for product {product_id}")
            return self._create_empty_snapshot(product_id, channel, current_price, "MISSING_COST")

        # 2. 수수료율 결정 (정책 우선)
        fee_rate = self._get_fee_rate(channel, product_id, cost.platform_fee_rate)
        
        # 3. 수익 및 마진 계산
        # Profit = 판매가 - (공급가 + 배송비 + 수수료 + 기타비용)
        platform_fee = int(current_price * fee_rate)
        total_expense = cost.supply_price + cost.shipping_cost + platform_fee + cost.extra_fee
        profit = current_price - total_expense
        
        margin_rate = (profit / current_price) if current_price > 0 else 0.0
        
        # 4. 위험 감지 로직
        reason_codes = []
        is_risk = False
        
        # 임계값 설정 (향후 설정값으로 분리 가능)
        MIN_MARGIN_THRESHOLD = 0.05 # 5% 미만 시 경고
        
        if profit < 0:
            is_risk = True
            reason_codes.append("NEGATIVE_PROFIT")
        elif margin_rate < MIN_MARGIN_THRESHOLD:
            is_risk = True
            reason_codes.append("LOW_MARGIN")
            
        snapshot = ProfitSnapshot(
            product_id=product_id,
            channel=channel,
            current_price=current_price,
            estimated_profit=profit,
            margin_rate=margin_rate,
            is_risk=is_risk,
            reason_codes=reason_codes
        )
        
        return snapshot

    def save_snapshot(self, snapshot: ProfitSnapshot):
        """분석 결과를 DB에 저장합니다."""
        self.session.add(snapshot)
        self.session.commit()

    def _get_fee_rate(self, channel: str, product_id: UUID, default_rate: float) -> float:
        """
        채널 및 카테고리에 맞는 수수료 정책을 조회합니다.
        추후 카테고리별 상세 정책 연동이 필요합니다.
        """
        # TODO: Category-based fee lookup
        policy = self.session.query(MarketFeePolicy).filter_by(market_code=channel.upper()).first()
        if policy:
            return policy.fee_rate
        return default_rate

    def _create_empty_snapshot(self, product_id: UUID, channel: str, current_price: int, reason: str) -> ProfitSnapshot:
        """원가 정보 부족 등 분석 불능 시 빈 스냅샷 생성"""
        return ProfitSnapshot(
            product_id=product_id,
            channel=channel,
            current_price=current_price,
            estimated_profit=0,
            margin_rate=0.0,
            is_risk=True,
            reason_codes=[reason]
        )
