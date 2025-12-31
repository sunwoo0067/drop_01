import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models import Product, Order, OrderItem, ProfitSnapshot, PricingRecommendation, CostComponent
from app.models_analytics import ProductDim, OrdersFact, ProfitSnapshotFact, PricingRecoFact, AnalyticsSyncState

logger = logging.getLogger(__name__)

class ETLManager:
    """
    운영 DB의 데이터를 분석용 Fact/Dim 테이블로 이관 및 변환하는 관리자입니다.
    """
    def __init__(self, session: Session):
        self.session = session

    def sync_all(self):
        """전체 분석 데이터 동기화"""
        logger.info("[ETL] Starting incremental analytics sync")
        self.sync_product_dims()
        self.sync_orders_fact()
        self.sync_profit_snapshots_fact()
        self.sync_pricing_reco_fact()
        self.session.commit()
        logger.info("[ETL] Incremental analytics sync completed")

    def _get_last_sync(self, sync_type: str) -> datetime:
        state = self.session.query(AnalyticsSyncState).filter_by(sync_type=sync_type).first()
        if not state:
            return datetime(2000, 1, 1, tzinfo=timezone.utc)
        return state.last_sync_at

    def _update_last_sync(self, sync_type: str, last_at: datetime):
        state = self.session.query(AnalyticsSyncState).filter_by(sync_type=sync_type).first()
        if not state:
            import uuid
            state = AnalyticsSyncState(sync_type=sync_type, id=uuid.uuid4())
            self.session.add(state)
        state.last_sync_at = last_at

    def sync_product_dims(self):
        """Product -> ProductDim 동기화 (Upsert)"""
        products = self.session.query(Product).all()
        for p in products:
            stmt = insert(ProductDim).values(
                product_id=p.id,
                name=p.name,
                brand=p.brand if hasattr(p, 'brand') else None,
                category_code=p.category_code if hasattr(p, 'category_code') else None,
                supplier_code=p.supplier_code if hasattr(p, 'supplier_code') else None,
                base_supply_price=p.cost_price if hasattr(p, 'cost_price') else 0
            ).on_conflict_do_update(
                index_elements=['product_id'],
                set_={
                    'name': p.name,
                    'brand': p.brand if hasattr(p, 'brand') else None,
                    'category_code': p.category_code if hasattr(p, 'category_code') else None,
                    'base_supply_price': p.cost_price if hasattr(p, 'cost_price') else 0,
                    'updated_at': datetime.now(timezone.utc)
                }
            )
            self.session.execute(stmt)
        logger.info(f"[ETL] Synced {len(products)} products to ProductDim")

    def sync_orders_fact(self):
        """Orders & OrderItems -> OrdersFact 동기화 (Incremental)"""
        last_sync = self._get_last_sync("orders")
        
        # 신규 주문 아이템 조회
        new_items = self.session.query(OrderItem).join(Order).filter(
            Order.created_at > last_sync
        ).all()
        
        count = 0
        latest_at = last_sync
        
        for item in new_items:
            if not item.product_id:
                logger.warning(f"[ETL] Skipping OrderItem {item.id} due to missing product_id")
                continue

            order = self.session.get(Order, item.order_id)
            if not order: continue
            
            # 수익성 데이터 계산
            supply_price = 0
            cost = self.session.query(CostComponent).filter_by(product_id=item.product_id).first()
            if cost:
                supply_price = cost.supply_price * item.quantity
            
            # 가상 수수료 (추후 정책 연동)
            platform_fee = int(item.total_price * 0.1) 
            profit = item.total_price - (supply_price + platform_fee)
            margin_rate = (profit / item.total_price) if item.total_price > 0 else 0.0
            
            fact = OrdersFact(
                order_id=order.vendor_order_id if order.vendor_order_id else str(order.id),
                product_id=item.product_id,
                channel=order.marketplace if order.marketplace else "UNKNOWN",
                sell_price=item.total_price,
                supply_price=supply_price,
                platform_fee=platform_fee,
                profit=profit,
                margin_rate=margin_rate,
                ordered_at=order.ordered_at if order.ordered_at else order.created_at
            )
            self.session.add(fact)
            count += 1
            if order.created_at > latest_at:
                latest_at = order.created_at
        
        if count > 0:
            self._update_last_sync("orders", latest_at)
        logger.info(f"[ETL] Incremental synced {count} order facts")

    def sync_profit_snapshots_fact(self):
        """ProfitSnapshot -> ProfitSnapshotFact (Incremental)"""
        last_sync = self._get_last_sync("snapshots")
        
        new_snapshots = self.session.query(ProfitSnapshot).filter(
            ProfitSnapshot.created_at > last_sync
        ).all()
        
        count = 0
        latest_at = last_sync
        
        for s in new_snapshots:
            fact = ProfitSnapshotFact(
                id=s.id,
                product_id=s.product_id,
                channel=s.channel,
                price=s.current_price,
                profit=s.estimated_profit,
                margin_rate=s.margin_rate,
                is_risk=s.is_risk,
                snapshot_at=s.created_at
            )
            self.session.add(fact)
            count += 1
            if s.created_at > latest_at:
                latest_at = s.created_at
                
        if count > 0:
            self._update_last_sync("snapshots", latest_at)
        logger.info(f"[ETL] Incremental synced {count} profit snapshots")

    def sync_pricing_reco_fact(self):
        """PricingRecommendation -> PricingRecoFact (Incremental)"""
        last_sync = self._get_last_sync("recommendations")
        
        new_recos = self.session.query(PricingRecommendation).filter(
            PricingRecommendation.created_at > last_sync
        ).all()
        
        count = 0
        latest_at = last_sync
        
        for r in new_recos:
            fact = PricingRecoFact(
                recommendation_id=r.id,
                product_id=r.product_id,
                current_price=r.current_price,
                recommended_price=r.recommended_price,
                expected_profit_delta=0, # TODO: 산출 로직
                status=r.status,
                created_at=r.created_at,
                processed_at=None
            )
            self.session.add(fact)
            count += 1
            if r.created_at > latest_at:
                latest_at = r.created_at
                
        if count > 0:
            self._update_last_sync("recommendations", latest_at)
        logger.info(f"[ETL] Incremental synced {count} pricing recommendations")
