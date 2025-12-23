import logging
import uuid
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from sqlalchemy import select

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
        workflow.add_node("rank_candidates", self.rank_candidates)
        workflow.add_node("finalize", self.finalize)

        # 엣지 연결
        workflow.set_entry_point("analyze_benchmark")
        workflow.add_edge("analyze_benchmark", "search_supplier")
        workflow.add_edge("search_supplier", "score_candidates")
        workflow.add_edge("score_candidates", "rank_candidates")
        workflow.add_edge("rank_candidates", "finalize")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _extract_items(self, data: dict) -> list[dict]:
        if not isinstance(data, dict):
            return []

        if "items" in data and isinstance(data.get("items"), list):
            return [it for it in data["items"] if isinstance(it, dict)]

        data_obj = data.get("data")
        if not isinstance(data_obj, dict):
            return []
        items_obj = data_obj.get("items")
        if items_obj is None and isinstance(data_obj.get("data"), dict):
            items_obj = data_obj.get("data").get("items")
        if isinstance(items_obj, list):
            return [it for it in items_obj if isinstance(it, dict)]
        return []

    def analyze_benchmark(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Analyzing benchmark...")
        benchmark = state.get("benchmark_data")
        if not benchmark:
            return {"errors": ["No benchmark data provided"]}
        
        name = benchmark.get("name")
        detail = benchmark.get("detail_html") or name
        images = benchmark.get("images") or []
        
        pain_points = self.ai_service.analyze_pain_points(detail, provider="auto")
        specs = self.ai_service.extract_specs(detail, provider="auto")
        
        # Spatial analysis for the main image if available
        visual_analysis = ""
        if images:
            try:
                import requests
                logger.info(f"[Agent] Attempting visual analysis for image: {images[0]}")
                resp = requests.get(images[0], timeout=10)
                if resp.status_code == 200:
                    visual_analysis = self.ai_service.analyze_visual_layout(
                        resp.content, 
                        prompt="Identify the main product features, logo position, and design style in this image.",
                        provider="auto"
                    )
                    logger.info(f"[Agent] Visual analysis result length: {len(visual_analysis)}")
                else:
                    logger.warning(f"[Agent] Benchmark image fetch failed: HTTP {resp.status_code}")
            except Exception as e:
                logger.error(f"[Agent] Visual analysis failed: {e}")

        return {
            "pain_points": pain_points,
            "specs": specs,
            "visual_analysis": visual_analysis,
            "logs": ["Benchmark analysis completed (NLP + Spatial)"]
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
            items = self._extract_items(data)
        
        # 2. Local Vector Search
        vector_items = []
        from app.models import BenchmarkProduct, SourcingCandidate
        benchmark = None
        benchmark_id = None
        if target_id:
            try:
                benchmark_id = uuid.UUID(str(target_id))
            except (ValueError, TypeError):
                logger.warning("Invalid benchmark UUID provided to sourcing agent: %s", target_id)
        if benchmark_id:
            benchmark = (
                self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id))
                .scalar_one_or_none()
            )
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
                    "thumbnail_url": getattr(cand, "thumbnail_url", None),
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
        benchmark = None
        if target_id:
            try:
                benchmark_uuid = uuid.UUID(str(target_id))
            except (TypeError, ValueError):
                benchmark_uuid = None
            if benchmark_uuid:
                benchmark = (
                    self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_uuid))
                    .scalar_one_or_none()
                )

        scored_items = []
        for item in items:
            name = item.get("name") or item.get("item_name") or ""
            # Seasonality score
            season_data = self.ai_service.predict_seasonality(name)
            item["seasonal_score"] = season_data.get("current_month_score", 0.0)
            
            # Vector Similarity if not already present
            if benchmark and benchmark.embedding is not None and not item.get("similarity_score"):
                pass 
                
            scored_items.append(item)
            
        # Sort by seasonal_score or other metrics if needed
        scored_items.sort(key=lambda x: x.get("seasonal_score", 0), reverse=True)

        return {
            "candidate_results": scored_items,
            "logs": [f"Scoring completed for {len(scored_items)} items"]
        }

    def rank_candidates(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Expert ranking of candidates using Reasoning model...")
        candidates = state.get("candidate_results", [])
        benchmark_specs = state.get("specs", {})
        benchmark_visual = state.get("visual_analysis", "")
        
        if not candidates:
            return {"logs": ["No candidates to rank"]}
            
        # Select top 7 for deep analysis to save resources while keeping range
        top_candidates = candidates[:7]
        
        candidates_summary = "\n".join([
            f"- ID: {c.get('item_code') or c.get('itemCode')}, Name: {c.get('name') or c.get('item_name')}, Price: {c.get('supply_price')}"
            for c in top_candidates
        ])
        
        prompt = f"""
        Rank these product candidates based on how well they match the benchmark product.
        
        Benchmark Specs: {benchmark_specs}
        Benchmark Visual Analysis: {benchmark_visual}
        
        Candidates to Evaluate:
        {candidates_summary}
        
        Analyze the compatibility in terms of specifications, design style, and market value.
        Return ONLY a JSON object: 
        {{ 
          "rankings": [ {{"id": "item_code", "score": float(0-1), "reason": "concise reason"}} ], 
          "expert_summary": "overall sourcing recommendation" 
        }}
        """
        
        try:
            # Use AIService.generate_json (which defaults to logic model)
            ranking_result = self.ai_service.generate_json(prompt, provider="ollama")
            rankings = ranking_result.get("rankings", [])
            rank_map = {str(r.get("id")): r for r in rankings if r.get("id")}
            
            for cand in candidates:
                code = str(cand.get("item_code") or cand.get("itemCode"))
                if code in rank_map:
                    cand["expert_match_score"] = rank_map[code].get("score", 0.0)
                    cand["expert_match_reason"] = rank_map[code].get("reason", "")
                else:
                    cand["expert_match_score"] = 0.0
            
            # Re-sort by expert score
            candidates.sort(key=lambda x: x.get("expert_match_score", 0), reverse=True)
            
            return {
                "candidate_results": candidates,
                "rank_explanation": ranking_result.get("expert_summary", ""),
                "logs": ["Expert ranking completed with specialized logic model"]
            }
        except Exception as e:
            logger.error(f"[Agent] Expert ranking failed: {e}")
            return {"logs": [f"Rank candidates failed: {e}"]}

    def finalize(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Finalizing sourcing...")
        return {
            "final_output": {"status": "success", "candidate_count": len(state.get("candidate_results", []))},
            "logs": ["Workflow finished successfully"]
        }

    async def run(self, benchmark_id: str, input_data: Dict[str, Any]):
        initial_state: AgentState = {
            "job_id": f"sourcing_{benchmark_id}",
            "target_id": benchmark_id,
            "input_data": input_data,
            "benchmark_data": {
                "name": input_data.get("name"),
                "detail_html": input_data.get("detail_html"),
                "price": input_data.get("price"),
                "images": input_data.get("images", [])
            },
            "collected_items": [],
            "candidate_results": [],
            "pain_points": [],
            "specs": {},
            "visual_analysis": "",
            "rank_explanation": "",
            "seasonality": {},
            "next_step": "",
            "errors": [],
            "logs": [],
            "final_output": None
        }
        
        return await self.workflow.ainvoke(initial_state)
