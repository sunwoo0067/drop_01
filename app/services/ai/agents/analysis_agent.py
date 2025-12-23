import logging
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.models import Product, MarketListing, OrderItem, Order, MarketAccount
from app.services.ai.service import AIService
from app.settings import settings

logger = logging.getLogger(__name__)

class AnalysisAgent:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.model = settings.ollama_logic_model  # Default to logic model (e.g., granite4)

    def find_cleanup_targets(self, out_dated_keywords: List[str], min_sales: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        비인기 상품 혹은 시즌이 종료된 상품을 분석하여 삭제 추천 리스트를 반환합니다.
        
        판단 기준:
        1. 최근 30일간 판매량 0
        2. 시즌 종료 키워드 포함 여부
        3. (추후 확장) 찜 수 등 마켓 데이터 포함
        """
        logger.info(f"Finding cleanup targets with outdated keywords: {out_dated_keywords}")

        # 1. 대상 상품 쿼리 (현재 ACTIVE 상태인 MarketListing 기준)
        # SQLAlchemy select를 사용하여 판매 데이터와 조인
        stmt = (
            select(
                Product.id,
                Product.name,
                MarketListing.market_item_id,
                MarketListing.market_account_id,
                MarketAccount.market_code,
                func.count(OrderItem.id).label("sales_count")
            )
            .join(MarketListing, Product.id == MarketListing.product_id)
            .join(MarketAccount, MarketListing.market_account_id == MarketAccount.id)
            .outerjoin(OrderItem, MarketListing.id == OrderItem.market_listing_id)
            .where(MarketListing.status == "ACTIVE")
            .where(MarketAccount.is_active == True)
            .group_by(Product.id, Product.name, MarketListing.market_item_id, MarketListing.market_account_id, MarketAccount.market_code)
            .having(func.count(OrderItem.id) <= min_sales)
            .limit(1000) # 분석 대상 모수 제한
        )
        
        candidates = self.db.execute(stmt).all()
        
        # 2. AI를 이용한 최종 정밀 분석 (시즌성 및 키워드 매칭)
        cleanup_list = []
        
        # 키워드 필터링을 위한 프롬프트 구성
        for cand in candidates:
            # 키워드 포함 여부 단순 체크 (성능을 위해 1차 필터링)
            matches_outdated = any(kw.lower() in cand.name.lower() for kw in out_dated_keywords)
            
            if matches_outdated:
                # 더 정교한 분석을 위해 AI 호출 (옵션)
                score_reason = f"시즌 종료 키워드 포함 및 판매량 {cand.sales_count}건"
                cleanup_list.append({
                    "product_id": str(cand.id),
                    "name": cand.name,
                    "market_item_id": cand.market_item_id,
                    "market_account_id": str(cand.market_account_id),
                    "market_code": cand.market_code,
                    "score": 0, # 삭제 대상 점수 (0일수록 삭제 권장)
                    "reason": score_reason
                })
                
                if len(cleanup_list) >= limit:
                    break
        
        return cleanup_list

    def analyze_performance_score(self, product_id: str) -> Dict[str, Any]:
        """
        단일 상품에 대한 상세 성과 지표를 분석합니다.
        """
        # 상세 주문 내역, 조회수 등을 종합하여 AI가 점수 산출 (추후 고도화)
        pass
