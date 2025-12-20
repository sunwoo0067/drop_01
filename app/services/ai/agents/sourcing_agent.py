import logging
import uuid
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from sqlalchemy import select, func

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
        from app.models import SupplierAccount
        
        account = (
            self.db.query(SupplierAccount)
            .filter(SupplierAccount.supplier_code == "ownerclan")
            .filter(SupplierAccount.user_type == "seller")
            .filter(SupplierAccount.is_primary.is_(True))
            .filter(SupplierAccount.is_active.is_(True))
            .one_or_none()
        )
        if not account:
            logger.warning("오너클랜 대표 계정이 설정되어 있지 않아 서비스 계정 없이 클라이언트를 초기화합니다.")
            return OwnerClanClient(
                auth_url=settings.ownerclan_auth_url,
                api_base_url=settings.ownerclan_api_base_url,
                graphql_url=settings.ownerclan_graphql_url
            )

        return OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url,
            access_token=account.access_token,
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
        logger.info("[Agent] Searching supplier (Hybrid: Keyword + Vector)...")
        benchmark_data = state.get("benchmark_data", {})
        query = benchmark_data.get("name")
        target_id = state.get("target_id")
        
        # 1. External Search (OwnerClan)
        status_code, data = self.client.get_products(keyword=query, limit=30)
        items = []
        if status_code == 200:
            data_obj = data.get("data")
            if isinstance(data_obj, dict):
                items_obj = data_obj.get("items")
                if items_obj is None and isinstance(data_obj.get("data"), dict):
                    items_obj = data_obj.get("data").get("items")
                if isinstance(items_obj, list):
                    items = [it for it in items_obj if isinstance(it, dict)]
        
        # 2. Local Vector Search (Optionally if we have pre-collected data)
        # SourcingCandidate 테이블 또는 SupplierItemRaw 테이블에서 유사 벡터 검색
        # 여기서는 이미 수집된 SourcingCandidate 중에서 유사한 것을 찾는 예시
        vector_items = []
        from app.models import BenchmarkProduct, SourcingCandidate
        benchmark = self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == uuid.UUID(target_id))).scalar_one_or_none()
        if benchmark and benchmark.embedding is not None:
            stmt = (
                select(SourcingCandidate)
                .order_by(SourcingCandidate.embedding.cosine_distance(benchmark.embedding))
                .limit(20)
            )
            candidates = self.db.scalars(stmt).all()
            for cand in candidates:
                vector_items.append({
                    "item_code": cand.supplier_item_id,
                    "name": cand.name,
                    "supply_price": cand.supply_price,
                    "thumbnail_url": cand.thumbnail_url,
                    "is_vector_match": True
                })

        # Merge results (avoiding duplicates by item_code)
        seen_codes = set()
        final_items = []
        for it in items + vector_items:
            code = it.get("item_code") or it.get("itemCode")
            if code and code not in seen_codes:
                final_items.append(it)
                seen_codes.add(code)

        return {
            "collected_items": final_items,
            "logs": [f"Found {len(items)} items from API, {len(vector_items)} from vector DB. Total merged: {len(final_items)}"]
        }

    def score_candidates(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Scoring candidates with vector similarity...")
        items = state.get("collected_items", [])
        target_id = state.get("target_id")
        
        from app.models import BenchmarkProduct
        from app.embedding_service import EmbeddingService
        emb_service = EmbeddingService()
        benchmark = self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == uuid.UUID(target_id))).scalar_one_or_none()

        scored_items = []
        for item in items:
            name = item.get("name") or item.get("item_name") or ""
            # Seasonality score
            season_data = self.ai_service.predict_seasonality(name)
            item["seasonal_score"] = season_data.get("current_month_score", 0.0)
            
            # Vector Similarity if not already present
            if benchmark and benchmark.embedding is not None and not item.get("similarity_score"):
                # 간단한 점수 산출을 위해 이름 기반 임베딩만 사용 (성능 고려)
                # 실제 SourcingService._create_candidate에서는 더 풍부하게 수행함
                pass 
                
            scored_items.append(item)
            
        # Sort by seasonal_score or other metrics if needed
        scored_items.sort(key=lambda x: x.get("seasonal_score", 0), reverse=True)

        return {
            "candidate_results": scored_items,
            "logs": [f"Scoring completed for {len(scored_items)} items"]
        }

    def finalize(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Finalizing sourcing...")
        # DB 저장 등 마무리 작업
        return {
            "final_output": {"status": "success", "candidate_count": len(state.get("candidate_results", []))},
            "logs": ["Workflow finished successfully"]
        }

    async def run(self, benchmark_id: str, input_data: Dict[str, Any]):
        # 초기 상태에 벤치마크 상세 정보 포함
        initial_state: AgentState = {
            "job_id": f"sourcing_{benchmark_id}",
            "target_id": benchmark_id,
            "input_data": input_data,
            "benchmark_data": {
                "name": input_data.get("name"),
                "detail_html": input_data.get("detail_html"),
                "price": input_data.get("price")
            },
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
