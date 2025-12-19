import logging
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.services.ai.agents.state import AgentState
from app.services.ai import AIService
from app.ownerclan_client import OwnerClanClient
from app.settings import settings

logger = logging.getLogger(__name__)

class SourcingAgent:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.client = self._get_client()
        self.workflow = self._create_workflow()

    def _get_client(self):
        # Implementation similar to SourcingService._get_ownerclan_primary_client
        # For simplicity in this prototype, we'll use a placeholder or assume setup
        return OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url
        )

    def _create_workflow(self):
        workflow = StateGraph(AgentState)

        # 노드 등록
        workflow.add_node("analyze_benchmark", self.analyze_benchmark)
        workflow.add_node("search_supplier", self.search_supplier)
        workflow.add_node("score_candidates", self.score_candidates)
        workflow.add_node("finalize", self.finalize)

        # 엣지 연결
        workflow.set_entry_point("analyze_benchmark")
        workflow.add_edge("analyze_benchmark", "search_supplier")
        workflow.add_edge("search_supplier", "score_candidates")
        workflow.add_edge("score_candidates", "finalize")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def analyze_benchmark(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Analyzing benchmark...")
        benchmark = state.get("benchmark_data")
        if not benchmark:
            return {"errors": ["No benchmark data provided"]}
        
        name = benchmark.get("name")
        detail = benchmark.get("detail_html") or name
        
        pain_points = self.ai_service.analyze_pain_points(detail, provider="gemini")
        specs = self.ai_service.extract_specs(detail, provider="auto")
        
        return {
            "pain_points": pain_points,
            "specs": specs,
            "logs": ["Benchmark analysis completed"]
        }

    def search_supplier(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Searching supplier...")
        benchmark = state.get("benchmark_data")
        query = benchmark.get("name")
        
        # 실제 검색 로직 (OwnerClanClient 호출)
        # 1-shot prototype에서는 Mock 처리하거나 간단히 구현
        # status, data = self.client.get_products(keyword=query, limit=20)
        items = [] # Assume we call client here
        
        return {
            "collected_items": items,
            "logs": [f"Found {len(items)} items from supplier"]
        }

    def score_candidates(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Scoring candidates...")
        items = state.get("collected_items", [])
        
        scored_items = []
        for item in items:
            # 기존 sourcing_service의 점수 로직 이전
            name = item.get("name", "")
            season_data = self.ai_service.predict_seasonality(name)
            
            item["seasonal_score"] = season_data.get("current_month_score", 0.0)
            scored_items.append(item)
            
        return {
            "candidate_results": scored_items,
            "logs": ["Scoring completed"]
        }

    def finalize(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Finalizing sourcing...")
        # DB 저장 등 마무리 작업
        return {
            "final_output": {"status": "success", "candidate_count": len(state.get("candidate_results", []))},
            "logs": ["Workflow finished successfully"]
        }

    async def run(self, benchmark_id: str, input_data: Dict[str, Any]):
        # DB에서 벤치마크 데이터 로드 (실제 구현 시)
        initial_state: AgentState = {
            "job_id": "test_job",
            "target_id": benchmark_id,
            "input_data": input_data,
            "benchmark_data": {"name": input_data.get("name")}, # Placeholder
            "collected_items": [],
            "candidate_results": [],
            "pain_points": [],
            "specs": {},
            "seasonality": {},
            "next_step": "",
            "errors": [],
            "logs": [],
            "final_output": None
        }
        
        return self.workflow.invoke(initial_state)
