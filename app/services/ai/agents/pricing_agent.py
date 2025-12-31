"""
Pricing Agent

시장 분석과 ROI 계산을 통해 최적의 판매 가격을 결정하는 AI 에이전트
"""
import logging
import uuid
import asyncio
from typing import Dict, Any, List, Callable
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.services.ai.agents.state import AgentState
from app.services.ai.agents.base import BaseAgent, ValidationMixin
from app.services.ai.agents.types import (
    PricingDecisionInput,
    PricingDecisionOutput,
    PricingAgentOutput,
    ProcessingStatus,
    to_dict_safe
)
from app.services.ai.exceptions import (
    AgentError,
    AIError,
    DatabaseError,
    wrap_exception
)
from app.models import MarketListing, Product
from app.services.analytics.competitor_analyzer import CompetitorAnalyzer

logger = logging.getLogger(__name__)

class PricingAgent(BaseAgent, ValidationMixin):
    """
    지능형 가격 결정 에이전트
    
    시장 상황 분석, 비용 검토, 최종 가격 결정 단계를 수행합니다.
    """
    
    def __init__(self, db: Session):
        super().__init__(db, "PricingAgent")
        self.analyzer = CompetitorAnalyzer(db)
    
    def _create_workflow(self) -> StateGraph:
        """워크플로우 그래프 생성"""
        workflow = StateGraph(AgentState)
        
        # 노드 추가
        workflow.add_node("analyze_market", self.analyze_market)
        workflow.add_node("evaluate_constraints", self.evaluate_constraints)
        workflow.add_node("make_decision", self.make_decision)
        
        # 엣지 연결
        workflow.set_entry_point("analyze_market")
        workflow.add_edge("analyze_market", "evaluate_constraints")
        workflow.add_edge("evaluate_constraints", "make_decision")
        workflow.add_edge("make_decision", END)
        
        return workflow.compile()
    
    def _get_entry_point(self) -> str:
        return "analyze_market"
    
    def _get_nodes(self) -> Dict[str, Callable]:
        return {
            "analyze_market": self.analyze_market,
            "evaluate_constraints": self.evaluate_constraints,
            "make_decision": self.make_decision
        }
    
    def _create_initial_state(self, target_id: str, input_data: Dict[str, Any], **kwargs) -> AgentState:
        return AgentState(
            job_id=str(uuid.uuid4()),
            target_id=target_id,
            input_data=input_data,
            errors=[],
            logs=[],
            collected_items=[],
            candidate_results=[]
        )

    def analyze_market(self, state: AgentState) -> AgentState:
        """시장 경쟁 상황 분석 노드"""
        listing_id = uuid.UUID(state["target_id"])
        self.log_step("analyze_market", f"Analyzing market for listing {listing_id}")
        
        try:
            position_report = self.analyzer.analyze_product_position(listing_id)
            
            return self._merge_state_updates(state, {
                "benchmark_data": position_report,
                "logs": [f"Market analysis completed: Position={position_report.get('position')}"]
            })
        except Exception as e:
            wrapped_error = wrap_exception(e, AgentError, context={"step": "analyze_market"})
            return self._merge_state_updates(state, {"errors": [str(wrapped_error)]})

    def evaluate_constraints(self, state: AgentState) -> AgentState:
        """비용 및 ROI 가드레일 평가 노드"""
        listing_id = uuid.UUID(state["target_id"])
        listing = self.db.get(MarketListing, listing_id)
        if not listing:
            return self._merge_state_updates(state, {"errors": ["Listing not found"]})
            
        product = self.db.get(Product, listing.product_id)
        if not product:
            return self._merge_state_updates(state, {"errors": ["Product not found"]})

        supply_price = product.cost_price or 0
        target_roi = state["input_data"].get("target_roi", 0.15) # 기본 15%
        
        # 마켓별 수수료 정책 (간소화)
        market_code = listing.market_account.market_code if listing.market_account else "COUPANG"
        fee_rate = 0.13 # 쿠팡/네이버 평균 수준
        
        # 최소 안전 가격 계산: (공급가 / (1 - 수수료율 - 목표ROI))
        # ROI = ((SellingPrice * (1-Fee)) - Supply) / Supply
        # SellingPrice * (1-Fee) = Supply * (1 + ROI)
        # SellingPrice = Supply * (1 + ROI) / (1 - Fee)
        min_safe_price = supply_price * (1 + target_roi) / (1 - fee_rate)
        
        constraints = {
            "supply_price": supply_price,
            "fee_rate": fee_rate,
            "target_roi": target_roi,
            "min_safe_price": int(min_safe_price)
        }
        
        return self._merge_state_updates(state, {
            "specs": constraints,
            "logs": [f"Constraints evaluated: Min Safe Price = {int(min_safe_price)}"]
        })

    async def make_decision(self, state: AgentState) -> AgentState:
        """최종 가격 결정 노드 (AI 활용)"""
        market_data = state.get("benchmark_data", {})
        constraints = state.get("specs", {})
        product_name = state["input_data"].get("product_name", "Unknown Product")
        
        market_stats = market_data.get("market_stats", {})
        
        decision_input = PricingDecisionInput(
            product_name=product_name,
            supply_price=constraints.get("supply_price", 0),
            market_stats=market_stats,
            min_safe_price=constraints.get("min_safe_price", 0),
            market_code=market_data.get("market_code", "COUPANG")
        )
        
        prompt = f"""
        당신은 이커머스 가격 전략 전문가입니다. 다음 데이터를 바탕으로 최적의 판매 가격을 결정해주세요.
        
        [상품 정보]
        - 상품명: {decision_input.product_name}
        - 공급가: {decision_input.supply_price}원
        - 최소 안전 가격(목표 ROI 반영): {decision_input.min_safe_price}원
        
        [시장 상황 ({decision_input.market_code})]
        - 시장 평균가: {market_stats.get('avg_price')}원
        - 시장 최저가: {market_stats.get('min_price')}원
        - 우리 상품의 현재 포지션: {market_data.get('position')}
        
        [가이드라인]
        1. '최소 안전 가격' 아래로 가격을 책정하지 마세요. (마진 확보 원칙)
        2. 시장 최저가와 경쟁이 가능하다면 최저가 근처 혹은 약간 아래로 책정하여 판매량을 극대화하세요.
        3. 시장가가 너무 정체되어 있거나 우리 상품의 품질 점수가 높다면 평균가 근처로 책정하여 마진을 확보하세요.
        4. 가격은 10원 단위로 절사하세요 (예: 15432원 -> 15430원).
        
        결과를 JSON 형식으로 반환하세요:
        {{
            "suggested_price": 정수,
            "strategy": "전략 이름(영문대문자)",
            "reasoning": "결정 근거 (한국어)",
            "expected_roi": 예상ROI(소수점)
        }}
        """
        
        try:
            # AIService를 통해 AI 결정 수행
            decision_dict = await self.ai_service.generate_json(prompt)
            decision = PricingDecisionOutput(**decision_dict)
            
            final_output = PricingAgentOutput(
                listing_id=state["target_id"],
                suggested_price=decision.suggested_price,
                strategy=decision.strategy,
                reasoning=decision.reasoning,
                expected_roi=decision.expected_roi,
                status=ProcessingStatus.COMPLETED
            )
            
            return self._merge_state_updates(state, {
                "final_output": to_dict_safe(final_output),
                "logs": [f"Price decision made: {decision.suggested_price} ({decision.strategy})"]
            })
            
        except Exception as e:
            wrapped_error = wrap_exception(e, AIError, context={"step": "make_decision"})
            return self._merge_state_updates(state, {"errors": [str(wrapped_error)]})
