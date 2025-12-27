"""
Sourcing Agent

공급처 검색 및 소싱을 담당하는 AI 에이전트
"""
import logging
import uuid
import asyncio
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.services.ai.agents.state import AgentState
from app.services.ai.agents.base import BaseAgent, ValidationMixin
from app.services.ai.agents.types import (
    BenchmarkAnalysisInput,
    BenchmarkAnalysisOutput,
    SupplierItem,
    SupplierSearchInput,
    SupplierSearchOutput,
    CandidateScoringInput,
    CandidateScoringOutput,
    CandidateRankingInput,
    CandidateRankingOutput,
    RankingResult,
    SourcingAgentOutput,
    ProcessingStatus,
    to_dict_safe,
    from_dict_safe
)
from app.services.ai.agents.router import create_sourcing_router
from app.services.ai.exceptions import (
    ValidationError,
    AIError,
    APIError,
    DatabaseError,
    wrap_exception
)
from app.services.ai import AIService
from app.ownerclan_client import OwnerClanClient
from app.settings import settings

logger = logging.getLogger(__name__)

# OwnerClan 클라이언트 캐시 (TTL 10분)
_client_cache = {"client": None, "timestamp": 0}
_CLIENT_CACHE_TTL = 600  # 10분


class SourcingAgent(BaseAgent, ValidationMixin):
    """
    공급처 소싱 에이전트
    
    벤치마크 분석, 공급처 검색, 후보 점수 부여, 랭킹 단계를 수행합니다.
    """
    
    def __init__(self, db: Session):
        super().__init__(db, "SourcingAgent")
        self.client = self._get_client()
        self.router = create_sourcing_router()
    
    def _get_client(self) -> OwnerClanClient:
        """
        OwnerClan 클라이언트 초기화 (캐시 사용)
        
        Returns:
            OwnerClanClient 인스턴스
        """
        import time
        current_time = time.time()
        
        # 캐시 유효성 확인
        if _client_cache["client"] is not None and (current_time - _client_cache["timestamp"]) < _CLIENT_CACHE_TTL:
            return _client_cache["client"]
        
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
            logger.warning(
                "오너클랜 대표 계정이 설정되어 있지 않아 "
                "서비스 계정 없이 클라이언트를 초기화합니다."
            )
            client = OwnerClanClient(
                auth_url=settings.ownerclan_auth_url,
                api_base_url=settings.ownerclan_api_base_url,
                graphql_url=settings.ownerclan_graphql_url
            )
            _client_cache["client"] = client
            _client_cache["timestamp"] = current_time
            return client
        
        client = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url,
            access_token=account.access_token,
        )
        _client_cache["client"] = client
        _client_cache["timestamp"] = current_time
        return client
    
    def _create_workflow(self) -> StateGraph:
        """워크플로우 생성"""
        workflow = StateGraph(AgentState)
        
        # 노드 등록
        workflow.add_node("analyze_benchmark", self.analyze_benchmark)
        workflow.add_node("search_supplier", self.search_supplier)
        workflow.add_node("score_candidates", self.score_candidates)
        workflow.add_node("rank_candidates", self.rank_candidates)
        workflow.add_node("finalize", self.finalize)
        
        # 진입점 설정
        workflow.set_entry_point("analyze_benchmark")
        
        # 엣지 연결
        workflow.add_edge("analyze_benchmark", "search_supplier")
        workflow.add_edge("search_supplier", "score_candidates")
        workflow.add_edge("score_candidates", "rank_candidates")
        workflow.add_edge("rank_candidates", "finalize")
        workflow.add_edge("finalize", END)
        
        return workflow.compile()
    
    def _get_entry_point(self) -> str:
        """진입점 반환"""
        return "analyze_benchmark"
    
    def _get_nodes(self) -> Dict[str, callable]:
        """노드 매핑 반환"""
        return {
            "analyze_benchmark": self.analyze_benchmark,
            "search_supplier": self.search_supplier,
            "score_candidates": self.score_candidates,
            "rank_candidates": self.rank_candidates,
            "finalize": self.finalize
        }
    
    def _create_initial_state(self, target_id: str, input_data: Dict[str, Any], **kwargs) -> AgentState:
        """초기 상태 생성"""
        return {
            "job_id": f"sourcing_{target_id}",
            "target_id": target_id,
            "input_data": input_data,
            "benchmark_data": {
                "name": input_data.get("name"),
                "detail_html": input_data.get("detail_html"),
                "price": input_data.get("price"),
                "images": input_data.get("images", []),
                "reviews": input_data.get("reviews", [])
            },
            "collected_items": [],
            "candidate_results": [],
            "pain_points": [],
            "specs": {},
            "visual_analysis": "",
            "seasonality": {},
            "rank_explanation": "",
            "next_step": "",
            "errors": [],
            "logs": [],
            "final_output": None
        }
    
    def _extract_items(self, data: dict) -> List[dict]:
        """
        API 응답에서 항목 추출
        
        Args:
            data: API 응답 데이터
        
        Returns:
            항목 목록
        """
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
    
    async def analyze_benchmark(self, state: AgentState) -> Dict[str, Any]:
        """
        벤치마크 분석 노드
        
        벤치마크 제품의 pain points, specs, visual analysis를 추출합니다.
        """
        self.log_step("analyze_benchmark", "Analyzing benchmark...")
        
        try:
            benchmark = state.get("benchmark_data")
            
            # 입력 유효성 검사
            if not benchmark:
                raise ValidationError(
                    "No benchmark data provided",
                    context={"state_keys": list(state.keys())}
                )
            
            self._validate_required_fields(benchmark, ["name"])
            
            name = benchmark.get("name")
            detail = benchmark.get("detail_html") or name
            images = benchmark.get("images") or []
            reviews = benchmark.get("reviews") or []
            
            # 분석 컨텍스트 구성
            analysis_context = (
                f"Product Detail: {detail}\n\n"
                f"Customer Reviews: " + "\n".join(reviews)
            )
            
            # NLP 분석
            pain_points = await self.ai_service.analyze_pain_points(
                analysis_context, 
                provider="auto"
            )
            specs = await self.ai_service.extract_specs(
                detail, 
                provider="auto"
            )
            
            # 시각적 분석 (첫 번째 이미지)
            visual_analysis = ""
            if images:
                try:
                    import httpx
                    logger.info(f"[Agent] Attempting visual analysis for image: {images[0]}")
                    
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(images[0], timeout=10)
                        if resp.status_code == 200:
                            visual_analysis = await self.ai_service.analyze_visual_layout(
                                resp.content,
                                prompt="Identify the main product features, logo position, and design style in this image.",
                                provider="auto"
                            )
                            logger.info(
                                f"[Agent] Visual analysis result length: {len(visual_analysis)}"
                            )
                        else:
                            logger.warning(
                                f"[Agent] Benchmark image fetch failed: HTTP {resp.status_code}"
                            )
                except Exception as e:
                    error = wrap_exception(e, APIError, url=images[0] if images else None)
                    logger.error(f"[Agent] Visual analysis failed: {error}")
            
            output = BenchmarkAnalysisOutput(
                pain_points=pain_points,
                specs=specs,
                visual_analysis=visual_analysis,
                analysis_timestamp=self._get_current_timestamp()
            )
            
            result = {
                "pain_points": pain_points,
                "specs": specs,
                "visual_analysis": visual_analysis,
                "logs": ["Benchmark analysis completed (NLP + Spatial)"]
            }
            
            # DB 저장
            target_id = state.get("target_id")
            if target_id:
                try:
                    self.save_benchmark_analysis(str(target_id), output)
                    result["logs"].append(f"Analysis persisted for benchmark: {target_id}")
                except Exception as e:
                    error = wrap_exception(e, DatabaseError)
                    logger.error(f"[Agent] Failed to persist benchmark analysis: {error}")
                    result["logs"].append(f"Failed to persist analysis: {error}")
            
            return result
            
        except Exception as e:
            error = wrap_exception(e, AIError, provider="benchmark_analysis")
            self.handle_error(error, "analyze_benchmark")
            return {"errors": [str(error)]}
    
    def save_benchmark_analysis(
        self,
        benchmark_id: str,
        analysis: BenchmarkAnalysisOutput
    ) -> None:
        """
        벤치마크 분석 결과 저장 (commit 제거 - 호출자가 처리)
        
        Args:
            benchmark_id: 벤치마크 ID
            analysis: 분석 결과
        """
        from app.models import BenchmarkProduct
        
        try:
            bid = uuid.UUID(benchmark_id)
        except (ValueError, TypeError) as e:
            raise DatabaseError(
                f"Invalid benchmark_id: {benchmark_id}",
                table_name="benchmark_products",
                operation="update"
            ) from e
        
        product = self.db.get(BenchmarkProduct, bid)
        if product:
            product.pain_points = analysis.pain_points
            product.specs = analysis.specs
            product.visual_analysis = analysis.visual_analysis
            # commit 제거 - 호출자가 처리하도록 변경
            logger.info(f"Benchmark analysis prepared for {benchmark_id}")
        else:
            logger.warning(
                f"BenchmarkProduct not found for saving analysis: {benchmark_id}"
            )
    
    async def search_supplier(self, state: AgentState) -> Dict[str, Any]:
        """
        공급처 검색 노드
        
        OwnerClan API와 Vector DB 하이브리드 검색을 수행합니다.
        """
        self.log_step("search_supplier", "Searching supplier (Hybrid: Keyword + Vector)...")
        
        try:
            benchmark_data = state.get("benchmark_data", {})
            query = benchmark_data.get("name")
            target_id = state.get("target_id")
            
            if not query:
                raise ValidationError(
                    "No search query provided",
                    context={"benchmark_data_keys": list(benchmark_data.keys())}
                )
            
            # 1. 외부 API 검색 (OwnerClan)
            status_code, data = self.client.get_products(keyword=query, limit=30)
            api_items = []
            if status_code == 200:
                api_items = self._extract_items(data)
            
            # 2. 로컬 벡터 검색
            vector_items = []
            from app.models import BenchmarkProduct, SourcingCandidate
            
            benchmark = None
            benchmark_id = None
            
            if target_id:
                try:
                    benchmark_id = uuid.UUID(str(target_id))
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid benchmark UUID provided to sourcing agent: {target_id}"
                    )
            
            if benchmark_id:
                benchmark = (
                    self.db.execute(
                        select(BenchmarkProduct).where(
                            BenchmarkProduct.id == benchmark_id
                        )
                    ).scalar_one_or_none()
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
            
            # 중복 제거 후 병합
            seen_codes = set()
            final_items = []
            for it in api_items + vector_items:
                code = it.get("item_code") or it.get("itemCode")
                if code and code not in seen_codes:
                    final_items.append(it)
                    seen_codes.add(code)
            
            return {
                "collected_items": final_items,
                "logs": [
                    f"Found {len(api_items)} items from API, "
                    f"{len(vector_items)} from vector DB. "
                    f"Total merged: {len(final_items)}"
                ]
            }
            
        except Exception as e:
            error = wrap_exception(e, APIError, operation="supplier_search")
            self.handle_error(error, "search_supplier")
            return {"errors": [str(error)]}
    
    async def score_candidates(self, state: AgentState) -> Dict[str, Any]:
        """
        후보 점수 부여 노드 (병렬 시즌성 예측 개선)
        
        시즌성 점수를 부여하고 후보를 정렬합니다.
        """
        self.log_step("score_candidates", "Scoring candidates with vector similarity...")
        
        try:
            items = state.get("collected_items", [])
            target_id = state.get("target_id")
            
            # 벤치마크 로드
            from app.models import BenchmarkProduct
            benchmark = None
            
            if target_id:
                try:
                    benchmark_uuid = uuid.UUID(str(target_id))
                except (TypeError, ValueError):
                    benchmark_uuid = None
                
                if benchmark_uuid:
                    benchmark = (
                        self.db.execute(
                            select(BenchmarkProduct).where(
                                BenchmarkProduct.id == benchmark_uuid
                            )
                        ).scalar_one_or_none()
                    )
            
            # 병렬 시즌성 예측
            async def predict_seasonality_for_item(item: dict) -> dict:
                name = item.get("name") or item.get("item_name") or ""
                season_data = await self.ai_service.predict_seasonality(name)
                item["seasonal_score"] = season_data.get("current_month_score", 0.0)
                return item
            
            # 병렬 처리 (세마포어로 동시성 제어)
            sem = asyncio.Semaphore(10)  # 최대 10개 동시 예측
            async def limited_predict(item: dict):
                async with sem:
                    return await predict_seasonality_for_item(item)
            
            tasks = [limited_predict(item) for item in items]
            scored_items = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 예외 처리
            scored_items_clean = []
            for item in scored_items:
                if isinstance(item, Exception):
                    logger.warning(f"Seasonality prediction failed: {item}")
                    continue
                scored_items_clean.append(item)
            
            # 벡터 유사도 유지
            for item in scored_items_clean:
                if benchmark and benchmark.embedding is not None and not item.get("similarity_score"):
                    # 벡터 유사도 계산 로직은 search_supplier에서 이미 수행됨
                    pass
            
            # 시즌성 점수로 정렬
            scored_items_clean.sort(key=lambda x: x.get("seasonal_score", 0), reverse=True)
            
            return {
                "candidate_results": scored_items_clean,
                "logs": [f"Scoring completed for {len(scored_items_clean)} items"]
            }
            
        except Exception as e:
            error = wrap_exception(e, AIError, provider="seasonality")
            self.handle_error(error, "score_candidates")
            return {"errors": [str(error)]}
    
    async def rank_candidates(self, state: AgentState) -> Dict[str, Any]:
        """
        후보 랭킹 노드
        
        Reasoning 모델로 전문가 랭킹을 수행합니다.
        """
        self.log_step("rank_candidates", "Expert ranking of candidates using Reasoning model...")
        
        try:
            candidates = state.get("candidate_results", [])
            benchmark_specs = state.get("specs", {})
            benchmark_visual = state.get("visual_analysis", "")
            
            if not candidates:
                return {"logs": ["No candidates to rank"]}
            
            # 상위 7개 후보만 분석
            top_candidates = candidates[:7]
            
            candidates_summary = "\n".join([
                f"- ID: {c.get('item_code') or c.get('itemCode')}, "
                f"Name: {c.get('name') or c.get('item_name')}, "
                f"Price: {c.get('supply_price')}"
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
            
            # AIService.generate_json 사용 (기본값: logic model)
            ranking_result = await self.ai_service.generate_json(prompt, provider="ollama")
            rankings = ranking_result.get("rankings", [])
            rank_map = {str(r.get("id")): r for r in rankings if r.get("id")}
            
            for cand in candidates:
                code = str(cand.get("item_code") or cand.get("itemCode"))
                if code in rank_map:
                    cand["expert_match_score"] = rank_map[code].get("score", 0.0)
                    cand["expert_match_reason"] = rank_map[code].get("reason", "")
                else:
                    cand["expert_match_score"] = 0.0
            
            # 전문가 점수로 재정렬
            candidates.sort(key=lambda x: x.get("expert_match_score", 0), reverse=True)
            
            return {
                "candidate_results": candidates,
                "rank_explanation": ranking_result.get("expert_summary", ""),
                "logs": ["Expert ranking completed with specialized logic model"]
            }
            
        except Exception as e:
            error = wrap_exception(e, AIError, provider="ollama")
            self.handle_error(error, "rank_candidates")
            return {"errors": [str(error)]}
    
    async def finalize(self, state: AgentState) -> Dict[str, Any]:
        """
        최종화 노드
        
        최종 결과를 생성합니다.
        """
        self.log_step("finalize", "Finalizing sourcing...")
        
        try:
            candidates = state.get("candidate_results", [])
            errors = state.get("errors", [])
            
            # 처리 상태 확인
            status = ProcessingStatus.FAILED if errors else ProcessingStatus.COMPLETED
            
            output = SourcingAgentOutput(
                candidates=candidates,
                candidate_count=len(candidates),
                expert_summary=state.get("rank_explanation", ""),
                status=status,
                error_message="; ".join(errors) if errors else None
            )
            
            return {
                "final_output": to_dict_safe(output),
                "logs": ["Workflow finished successfully"]
            }
            
        except Exception as e:
            error = wrap_exception(e, ValidationError)
            self.handle_error(error, "finalize")
            return {"errors": [str(error)]}
    
    def find_cleanup_targets(self, outdated_keywords: List[str]) -> List[Dict[str, Any]]:
        """
        비인기/오프시즌 키워드에 해당하는 상품들을 찾아 삭제 대상으로 반환합니다.
        
        Args:
            outdated_keywords: 제외할 키워드 목록
            
        Returns:
            삭제 대상 상품 정보 목록
        """
        from app.models import Product, MarketListing, MarketAccount
        from sqlalchemy import or_
        
        if not outdated_keywords:
            return []
            
        logger.info(f"Finding cleanup targets for keywords: {outdated_keywords}")
        
        try:
            # 상품명에 키워드가 포함된 상품 찾기
            filters = [Product.name.ilike(f"%{kw}%") for kw in outdated_keywords]
            
            stmt = (
                select(
                    MarketListing.market_item_id,
                    MarketListing.market_account_id,
                    MarketAccount.market_code,
                    Product.name
                )
                .join(Product, MarketListing.product_id == Product.id)
                .join(MarketAccount, MarketListing.market_account_id == MarketAccount.id)
                .where(or_(*filters))
                .where(MarketListing.status == "ACTIVE")
            )
            
            rows = self.db.execute(stmt).all()
            
            targets = []
            for row in rows:
                targets.append({
                    "market_item_id": row.market_item_id,
                    "market_account_id": str(row.market_account_id),
                    "market_code": row.market_code,
                    "reason": f"시즌 종료 키워드 포함: {row.name}"
                })
                
            logger.info(f"Found {len(targets)} cleanup targets.")
            return targets
        except Exception as e:
            logger.error(f"Failed to find cleanup targets: {e}")
            return []

    def _get_current_timestamp(self) -> str:
        """
        현재 타임스탬프 반환
        
        Returns:
            ISO 8601 형식 타임스탬프
        """
        import datetime
        return datetime.datetime.now().isoformat()


# ============================================================================
# Helper Functions
# ============================================================================

def create_sourcing_agent(db: Session) -> SourcingAgent:
    """
    SourcingAgent 인스턴스 생성 헬퍼
    
    Args:
        db: 데이터베이스 세션
    
    Returns:
        SourcingAgent 인스턴스
    """
    return SourcingAgent(db)
