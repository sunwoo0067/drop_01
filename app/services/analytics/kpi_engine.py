import logging
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from app.models_analytics import OrdersFact, ProfitSnapshotFact, PricingRecoFact, ProductDim

logger = logging.getLogger(__name__)

class KPIEngine:
    """
    데이터 레이크(Fact/Dim)를 기반으로 비즈니스 핵심 지표를 산출하는 엔진입니다.
    """
    def __init__(self, session: Session):
        self.session = session

    def get_margin_trend(self, days: int = 30) -> list[dict]:
        """일자별 평균 마진율 추이를 반환합니다."""
        start_date = datetime.now() - timedelta(days=days)
        
        results = self.session.query(
            func.date(OrdersFact.ordered_at).label("date"),
            func.avg(OrdersFact.margin_rate).label("avg_margin"),
            func.sum(OrdersFact.profit).label("total_profit"),
            func.count(OrdersFact.id).label("order_count")
        ).filter(
            OrdersFact.ordered_at >= start_date
        ).group_by(
            func.date(OrdersFact.ordered_at)
        ).order_by(
            func.date(OrdersFact.ordered_at)
        ).all()
        
        return [
            {
                "date": str(r.date),
                "avg_margin": float(r.avg_margin) if r.avg_margin else 0,
                "total_profit": int(r.total_profit) if r.total_profit else 0,
                "order_count": int(r.order_count)
            }
            for r in results
        ]

    def get_what_if_simulation(self, product_id: UUID = None) -> dict:
        """
        'What-if' 시뮬레이션: 현재 PENDING 상태인 가격 권고를 적용했을 때의 기대 효과를 산출합니다.
        """
        query = self.session.query(PricingRecoFact).filter_by(status="PENDING")
        if product_id:
            query = query.filter_by(product_id=product_id)
            
        recos = query.all()
        
        current_total_profit = 0 # 이 권고 대상 상품들의 현재 기대 이익 합
        simulated_total_profit = 0 # 권고가 적용 시 기대 이익 합
        
        for r in recos:
            # 최근 스냅샷에서 현재 이익 가져오기
            snapshot = self.session.query(ProfitSnapshotFact).filter_by(
                product_id=r.product_id
            ).order_by(ProfitSnapshotFact.snapshot_at.desc()).first()
            
            if snapshot:
                current_total_profit += snapshot.profit
                
                # 시뮬레이션 이익 계산: (추천가 - 현재가) + 현재이익
                price_delta = r.recommended_price - r.current_price
                simulated_total_profit += (snapshot.profit + price_delta)

        return {
            "pending_reco_count": len(recos),
            "current_base_profit": current_total_profit,
            "simulated_profit": simulated_total_profit,
            "expected_lift": simulated_total_profit - current_total_profit,
            "lift_percentage": ((simulated_total_profit / current_total_profit) - 1.0) * 100 if current_total_profit > 0 else 0
        }

    def get_inventory_health(self) -> dict:
        """재고 및 수익성 건전성 요약을 반환합니다."""
        total_products = self.session.query(ProductDim).count()
        at_risk = self.session.query(ProfitSnapshotFact).filter_by(is_risk=True).distinct(ProfitSnapshotFact.product_id).count()
        
        return {
            "total_active_products": total_products,
            "risk_product_count": at_risk,
            "risk_ratio": (at_risk / total_products) * 100 if total_products > 0 else 0
        }
