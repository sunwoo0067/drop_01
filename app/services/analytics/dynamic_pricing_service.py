import asyncio
import logging
import uuid
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.models import MarketListing, Product
from app.services.analytics.competitor_analyzer import CompetitorAnalyzer
from app.services.ai.agents.pricing_agent import PricingAgent

logger = logging.getLogger(__name__)

class DynamicPricingService:
    """
    인지적 자율 가격 결정 서비스
    시장 경쟁 상황과 내부 ROI 목표를 결합하여 최적의 가격을 산출합니다.
    """
    def __init__(self, db: Session):
        self.db = db
        self.analyzer = CompetitorAnalyzer(db)

    def calculate_optimal_price(self, listing_id: uuid.UUID, target_roi: float = 0.2) -> Dict[str, Any]:
        """
        특정 리스팅에 대한 최적의 가격 제안
        
        Args:
            listing_id: MarketListing ID
            target_roi: 목표 ROI (기본 20%)
        """
        listing = self.db.get(MarketListing, listing_id)
        if not listing:
            return {"status": "error", "message": "Listing not found"}

        product = self.db.get(Product, listing.product_id)
        if not product:
            return {"status": "error", "message": "Product not found"}
            
        supply_price = product.cost_price or 0
        
        # 1. 경쟁사 포지셔닝 분석
        position_report = self.analyzer.analyze_product_position(listing_id)
        market_stats = position_report["market_stats"]
        
        # 2. 하한선 결정 (Minimum ROI 가드레일)
        # TODO: 마켓별 수수료(MarketFeePolicy) 연동 필요
        estimated_fee_rate = 0.12 # 임시 12%
        min_price = supply_price / (1 - estimated_fee_rate - target_roi)
        
        # 3. 전략적 가격 결정 (현재는 단순 최저가 대응 전략)
        # 시장 최저가보다 100원 낮게 제안하되, min_price보다는 높아야 함
        suggested_price = max(min_price, market_stats["min_price"] - 100)
        
        # 4. 가격 단위 정규화 (쿠팡/네이버 10원 단위 절사 권장)
        suggested_price = (int(suggested_price) // 10) * 10
        
        return {
            "listing_id": str(listing_id),
            "product_name": product.name,
            "supply_price": supply_price,
            "min_safe_price": int(min_price),
            "market_min_price": market_stats["min_price"],
            "suggest_price": int(suggested_price),
            "expected_roi": ((suggested_price * (1 - estimated_fee_rate)) - supply_price) / supply_price if supply_price > 0 else 0,
            "strategy": "COMPETITIVE_MIN" if suggested_price > min_price else "ROI_PROTECTION"
        }

    async def suggest_agent_price(self, listing_id: uuid.UUID, target_roi: float = 0.15) -> Dict[str, Any]:
        """
        PricingAgent를 사용하여 AI 기반 최적 가격 제안
        """
        product = self.db.query(Product).join(MarketListing, Product.id == MarketListing.product_id).filter(MarketListing.id == listing_id).first()
        if not product:
            return {"status": "error", "message": "Product not found for listing"}

        agent = PricingAgent(self.db)
        input_data = {
            "product_name": product.name,
            "target_roi": target_roi
        }

        try:
            result = await asyncio.wait_for(agent.run(str(listing_id), input_data), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("PricingAgent timeout for listing %s", listing_id)
            return {"status": "error", "message": "PricingAgent timeout"}
        except Exception as e:
            logger.error("PricingAgent failed for listing %s: %s", listing_id, e)
            return {"status": "error", "message": "PricingAgent failed"}
        
        if result.status == "COMPLETED" and result.final_output:
            return {
                "status": "success",
                "original_price": product.selling_price,
                **result.final_output
            }
        else:
            return {
                "status": "error",
                "message": result.error_message or "Agent execution failed"
            }
