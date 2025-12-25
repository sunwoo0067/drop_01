"""
Processing Agent

제품 가공을 담당하는 AI 에이전트

3단계 드롭쉬핑 전략에 따라 가공 레벨을 조정합니다:
- STEP 1: 상품명만 최소 가공 (경량 텍스트)
- STEP 2: 상품명·옵션·상세 설명 개선 (qwen3:8b 텍스트/SEO)
- STEP 3: 이미지·상세페이지 완전 교체 (qwen3-vl:8b + 외부 API)
"""
import logging
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.services.ai.agents.state import AgentState
from app.services.ai.agents.base import BaseAgent, ValidationMixin
from app.services.ai.agents.types import (
    ExtractDetailsInput,
    ExtractDetailsOutput,
    OCRExtractionInput,
    OCRExtractionOutput,
    SEOOptimizationInput,
    SEOOptimizationOutput,
    ImageProcessingInput,
    ImageProcessingOutput,
    ProcessingAgentOutput,
    ProcessingStatus,
    MarketType,
    to_dict_safe,
    from_dict_safe
)
from app.services.ai.agents.router import create_processing_router
from app.services.ai.exceptions import (
    ValidationError,
    AIError,
    APIError,
    wrap_exception
)
from app.services.ai import AIService
from app.services.image_processing import image_processing_service
from app.services.name_processing import apply_market_name_rules
from app.settings import settings

logger = logging.getLogger(__name__)

# Few-shot 예제 캐시 (TTL 5분)
_few_shot_cache = {"data": None, "timestamp": 0}
_FEW_SHOT_CACHE_TTL = 300  # 5분


class ProcessingAgent(BaseAgent, ValidationMixin):
    """
    제품 가공 에이전트
    
    3단계 전략에 따른 가공:
    - STEP 1: 상품명만 최소 가공
    - STEP 2: 텍스트 중심 가공 (상품명·옵션·상세 설명)
    - STEP 3: 완전 브랜딩 (이미지·상세페이지 완전 교체)
    """
    
    def __init__(self, db: Session):
        super().__init__(db, "ProcessingAgent")
        self.router = create_processing_router()
    
    def _get_lifecycle_stage(self, target_id: str) -> str:
        """상품의 라이프사이클 단계 조회"""
        try:
            import uuid
            from app.models import Product
            
            product_id = uuid.UUID(target_id)
            product = self.db.get(Product, product_id)
            
            if product:
                return product.lifecycle_stage or "STEP_1"
            return "STEP_1"
        except Exception as e:
            logger.warning(f"Failed to get lifecycle stage for {target_id}: {e}")
            return "STEP_1"
    
    def _get_processing_scope(self, lifecycle_stage: str) -> Dict[str, Any]:
        """
        라이프사이클 단계별 가공 범위 반환
        
        Args:
            lifecycle_stage: "STEP_1", "STEP_2", "STEP_3"
            
        Returns:
            {
                "name_processing": bool,
                "ocr_processing": bool,
                "image_processing": bool,
                "ai_model": str,
                "description": str
            }
        """
        if lifecycle_stage == "STEP_1":
            return {
                "name_processing": True,
                "ocr_processing": False,
                "image_processing": False,
                "ai_model": "qwen3:8b",  # 경량 텍스트
                "description": "STEP 1: 상품명만 최소 가공"
            }
        elif lifecycle_stage == "STEP_2":
            return {
                "name_processing": True,
                "ocr_processing": True,
                "image_processing": False,
                "ai_model": "qwen3:8b",  # 텍스트/SEO
                "description": "STEP 2: 텍스트 중심 가공 (상품명·옵션·상세 설명)"
            }
        elif lifecycle_stage == "STEP_3":
            return {
                "name_processing": True,
                "ocr_processing": True,
                "image_processing": True,
                "ai_model": "qwen3-vl:8b",  # 비전 + 텍스트
                "description": "STEP 3: 완전 브랜딩 (이미지·상세페이지 완전 교체)"
            }
        else:
            # 기본값 (이름 전용 처리)
            return {
                "name_processing": True,
                "ocr_processing": False,
                "image_processing": False,
                "ai_model": "qwen3:8b",
                "description": "Default processing"
            }
    
    def _name_only_processing(self) -> bool:
        """이름 전용 처리 모드 여부 (레거시 설정)"""
        return settings.product_processing_name_only
    
    def _create_workflow(self) -> StateGraph:
        """워크플로우 생성 (라이프사이클 단계별 조건부 라우팅)"""
        workflow = StateGraph(AgentState)
        
        # 노드 등록
        workflow.add_node("extract_details", self.extract_details)
        workflow.add_node("extract_ocr_details", self.extract_ocr_details)
        workflow.add_node("optimize_seo", self.optimize_seo)
        workflow.add_node("process_images", self.process_images)
        workflow.add_node("save_product", self.save_product)
        
        # 진입점 설정
        workflow.set_entry_point("extract_details")
        
        # 기본 엣지 연결
        workflow.add_edge("extract_details", "extract_ocr_details")
        workflow.add_edge("extract_ocr_details", "optimize_seo")
        workflow.add_edge("optimize_seo", "save_product")  # 기본: 이미지 처리 생략
        workflow.add_edge("process_images", "save_product")
        workflow.add_edge("save_product", END)
        
        # 조건부 엣지: 이미지 처리 스킵 여부
        # 라이프사이클 단계가 STEP_1 또는 STEP_2면 이미지 처리 스킵
        # 라이프사이클 단계가 STEP_3이면 이미지 처리 수행
        # 이미 이 `_create_workflow`는 모든 노드가 등록된 상태에서 실행됨
        # 실제 런타임에 단계별 처리는 `_process_by_lifecycle_stage`에서 수행
        
        return workflow.compile()
    
    async def process_by_lifecycle_stage(self, target_id: str, input_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        라이프사이클 단계별 가공 수행
        
        Args:
            target_id: 상품 ID
            input_data: 입력 데이터
            **kwargs: 추가 인자
            
        Returns:
            가공 결과
        """
        lifecycle_stage = self._get_lifecycle_stage(target_id)
        processing_scope = self._get_processing_scope(lifecycle_stage)
        
        logger.info(f"Processing product {target_id} at stage {lifecycle_stage}: {processing_scope['description']}")
        
        # 상태 초기화
        state = self._create_initial_state(target_id, input_data, **kwargs)
        state["lifecycle_stage"] = lifecycle_stage
        state["processing_scope"] = processing_scope
        
        try:
            # 단계별 가공 흐름
            
            # 1. 상세페이지 추출 (모든 단계 공통)
            result1 = await self.extract_details(state)
            if result1.get("errors"):
                return result1
            state.update(result1)
            
            # 2. OCR 추출 (STEP 2, 3에서만 수행)
            if processing_scope["ocr_processing"]:
                result2 = await self.extract_ocr_details(state)
                if result2.get("errors"):
                    return result2
                state.update(result2)
            else:
                logger.info("Skipping OCR extraction (not required for current stage)")
            
            # 3. SEO 최적화 (모든 단계 공통, 단계별 모델 사용)
            state["ai_model_override"] = processing_scope["ai_model"]
            result3 = await self.optimize_seo(state)
            if result3.get("errors"):
                return result3
            state.update(result3)
            
            # 4. 이미지 처리 (STEP 3에서만 수행)
            if processing_scope["image_processing"]:
                result4 = await self.process_images(state)
                if result4.get("errors"):
                    return result4
                state.update(result4)
            else:
                logger.info("Skipping image processing (not required for current stage)")
            
            # 5. 저장 (모든 단계 공통)
            result5 = await self.save_product(state)
            
            # 가공 이력 기록 (ProcessingHistoryService)
            if not result5.get("errors") and lifecycle_stage in ["STEP_2", "STEP_3"]:
                await self._record_processing_history(
                    target_id,
                    lifecycle_stage,
                    input_data,
                    state
                )
            
            return result5
            
        except Exception as e:
            error = wrap_exception(e, AIError, step="lifecycle_processing")
            logger.error(f"Lifecycle processing failed for {target_id}: {error}")
            return {"errors": [str(error)]}
    
    async def _record_processing_history(
        self,
        target_id: str,
        lifecycle_stage: str,
        input_data: Dict[str, Any],
        state: AgentState
    ):
        """가공 이력 기록 (STEP 2, 3에서만)"""
        try:
            import uuid
            from app.services.processing_history_service import ProcessingHistoryService
            
            history_service = ProcessingHistoryService(self.db)
            
            # 가공 전 데이터
            before_data = {
                "name": input_data.get("name", ""),
                "description": input_data.get("description", ""),
                "images": input_data.get("images", [])
            }
            
            # 가공 후 데이터
            final_output = state.get("final_output", {})
            after_data = {
                "name": final_output.get("processed_name", ""),
                "keywords": final_output.get("processed_keywords", []),
                "images": final_output.get("processed_image_urls", [])
            }
            
            # 가공 유형 결정
            if lifecycle_stage == "STEP_2":
                processing_type = "DESCRIPTION"  # 텍스트 중심 가공
            elif lifecycle_stage == "STEP_3":
                processing_type = "FULL_BRANDING"  # 완전 브랜딩
            else:
                processing_type = "NAME"
            
            # 가공 이력 기록
            history_service.record_processing(
                product_id=uuid.UUID(target_id),
                processing_type=processing_type,
                before_data=before_data,
                after_data=after_data,
                ai_model=state.get("processing_scope", {}).get("ai_model", ""),
                ai_processing_time_ms=None,  # 추후 측정 필요
                ai_cost_estimate=None  # 추후 계산 필요
            )
            
            logger.info(f"Processing history recorded for product {target_id} (stage: {lifecycle_stage})")
            
        except Exception as e:
            logger.error(f"Failed to record processing history: {e}")
            # 가공 실패로 인해 전체 프로세스를 중단하지 않음
    
    def _get_entry_point(self) -> str:
        """진입점 반환"""
        return "extract_details"
    
    def _get_nodes(self) -> Dict[str, callable]:
        """노드 매핑 반환"""
        return {
            "extract_details": self.extract_details,
            "extract_ocr_details": self.extract_ocr_details,
            "optimize_seo": self.optimize_seo,
            "process_images": self.process_images,
            "save_product": self.save_product
        }
    
    def _create_initial_state(self, target_id: str, input_data: Dict[str, Any], **kwargs) -> AgentState:
        """초기 상태 생성"""
        return {
            "job_id": f"proc_{target_id}",
            "target_id": target_id,
            "input_data": input_data,
            "benchmark_data": kwargs.get("benchmark_data"),
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
    
    def _get_few_shot_examples(
        self,
        category: str = "일반",
        limit: int = 3
    ) -> List[Dict[str, str]]:
        """
        Few-shot 예제 가져오기 (캐시 사용)
        
        성공적으로 가공된 상품들의 예제를 가져옵니다.
        
        Args:
            category: 카테고리
            limit: 가져올 예제 수
        
        Returns:
            Few-shot 예제 목록
        """
        import time
        current_time = time.time()
        
        # 캐시 유효성 확인
        if _few_shot_cache["data"] is not None and (current_time - _few_shot_cache["timestamp"]) < _FEW_SHOT_CACHE_TTL:
            return _few_shot_cache["data"]
        
        # 캐시 갱신
        from app.models import Product
        from sqlalchemy import select
        
        try:
            stmt = (
                select(Product.name, Product.processed_name)
                .where(Product.processing_status == "COMPLETED")
                .limit(limit)
            )
            results = self.db.execute(stmt).all()
            examples = [
                {"original": r[0], "processed": r[1]}
                for r in results
                if r[0] and r[1]
            ]
            _few_shot_cache["data"] = examples
            _few_shot_cache["timestamp"] = current_time
            return examples
        except Exception as e:
            logger.warning(f"Failed to fetch few-shot examples: {e}")
            return []
    
    async def extract_details(self, state: AgentState) -> Dict[str, Any]:
        """
        상세페이지 추출 노드
        
        입력 데이터에서 상세페이지 내용을 추출하고 정규화합니다.
        """
        self.log_step("extract_details", "Extracting details for processing...")
        
        try:
            input_data = state.get("input_data", {})
            
            # 입력 유효성 검사
            self._validate_required_fields(input_data, ["name"])
            
            # 입력 데이터 파싱
            detail_text = (
                input_data.get("description") or 
                input_data.get("content") or 
                ""
            )
            
            output = ExtractDetailsOutput(
                normalized_detail=detail_text,
                extracted_fields={},
                original_text_length=len(detail_text),
                normalized_text_length=len(detail_text)
            )
            
            # 상태 업데이트
            updated_input = {**input_data, "normalized_detail": detail_text}
            
            return {
                "input_data": updated_input,
                "logs": ["Details extracted and normalized"]
            }
            
        except Exception as e:
            error = wrap_exception(e, ValidationError)
            self.handle_error(error, "extract_details")
            return {"errors": [str(error)]}
    
    async def extract_ocr_details(self, state: AgentState) -> Dict[str, Any]:
        """
        OCR 추출 노드 (병렬 처리 개선)
        
        이미지에서 텍스트를 추출하여 상세페이지에 추가합니다.
        """
        self.log_step("extract_ocr_details", "Extracting OCR details from images...")
        
        try:
            input_data = state.get("input_data", {})
            images = input_data.get("images", [])
            
            if not images:
                return {
                    "input_data": input_data,
                    "logs": ["No images to process for OCR"]
                }
            
            # 최대 2개 이미지 처리
            images_to_process = images[:2]
            ocr_texts = []
            failed_count = 0
            
            async def process_single_image(img_url: str) -> tuple[str | None, str | None]:
                """단일 이미지 OCR 처리"""
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.get(img_url, timeout=10)
                        if resp.status_code == 200:
                            text = await self.ai_service.extract_text_from_image(
                                resp.content,
                                format="text"
                            )
                            if text:
                                return (text, None)
                            return (None, "no_text")
                        return (None, f"http_{resp.status_code}")
                except Exception as e:
                    error = wrap_exception(e, APIError, url=img_url)
                    logger.error(f"OCR failed for {img_url}: {error}")
                    return (None, str(error))
            
            # 병렬 OCR 처리
            tasks = [process_single_image(url) for url in images_to_process]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failed_count += 1
                    continue
                
                text, error = result
                if text:
                    ocr_texts.append(f"Image Text: {text}")
                else:
                    failed_count += 1
                    if error and error != "no_text":
                        logger.warning(f"OCR failed: {error}")
            
            combined_ocr = "\n".join(ocr_texts)
            if combined_ocr:
                current_detail = input_data.get("normalized_detail", "")
                input_data["normalized_detail"] = f"{current_detail}\n\n[OCR Data]\n{combined_ocr}"
            
            return {
                "input_data": input_data,
                "logs": [
                    f"OCR extraction completed for {len(ocr_texts)} images",
                    f"Failed: {failed_count} images"
                ]
            }
            
        except Exception as e:
            error = wrap_exception(e, AIError, provider="ocr")
            self.handle_error(error, "extract_ocr_details")
            return {"errors": [str(error)]}
    
    async def optimize_seo(self, state: AgentState) -> Dict[str, Any]:
        """
        SEO 최적화 노드
        
        제품명을 최적화하고 키워드를 추출합니다.
        """
        self.log_step("optimize_seo", "Optimizing SEO...")
        
        try:
            input_data = state.get("input_data", {})
            
            # 입력 유효성 검사
            self._validate_required_fields(input_data, ["name"])
            
            name = input_data.get("name")
            brand = input_data.get("brand", "")
            context = input_data.get("normalized_detail")
            benchmark_name = (state.get("benchmark_data") or {}).get("name")
            category = input_data.get("category") or "일반"
            market = input_data.get("target_market") or "Coupang"
            
            # Few-shot 예제 가져오기
            examples = self._get_few_shot_examples(category=category)
            
            processed_name = name
            keywords = []
            confidence_score = 0.0
            
            try:
                seo_result = await self.ai_service.optimize_seo(
                    name,
                    [brand],
                    context=context,
                    benchmark_name=benchmark_name,
                    category=category,
                    market=market,
                    examples=examples,
                    provider="auto"
                )
                
                if isinstance(seo_result, dict):
                    raw_title = seo_result.get("title")
                    keywords = seo_result.get("tags") or []
                    confidence_score = seo_result.get("confidence", 0.0)
                    
                    if raw_title:
                        processed_name = apply_market_name_rules(
                            raw_title,
                            forbidden_keywords=settings.product_name_forbidden_keywords,
                            replacements=settings.product_name_replacements,
                            max_length=100,
                        )
                        
            except Exception as e:
                error = wrap_exception(e, AIError, provider="auto")
                logger.error(f"SEO optimization failed: {error}")
                
                # AI 실패 시 기본 규칙만 적용
                processed_name = apply_market_name_rules(
                    name,
                    forbidden_keywords=settings.product_name_forbidden_keywords,
                    replacements=settings.product_name_replacements,
                    max_length=100,
                )
            
            output = SEOOptimizationOutput(
                processed_name=processed_name,
                processed_keywords=keywords,
                confidence_score=confidence_score,
                original_name=name,
                used_examples_count=len(examples)
            )
            
            return {
                "final_output": to_dict_safe(output),
                "logs": ["SEO optimization completed (with fallback if needed)"]
            }
            
        except Exception as e:
            error = wrap_exception(e, AIError, provider="seo")
            self.handle_error(error, "optimize_seo")
            return {"errors": [str(error)]}
    
    async def process_images(self, state: AgentState) -> Dict[str, Any]:
        """
        이미지 처리 노드
        
        이미지를 다운로드하고 Supabase에 업로드합니다.
        """
        self.log_step("process_images", "Processing images...")
        
        try:
            if self._name_only_processing():
                return {
                    "final_output": state.get("final_output") or {},
                    "logs": ["Skipped image processing (PROCESS_NAME_ONLY=1)"],
                }
            
            input_data = state.get("input_data", {})
            product_id = state.get("target_id")
            raw_images = input_data.get("images", [])
            detail_html = input_data.get("detail_html") or input_data.get("normalized_detail", "")
            
            if not raw_images:
                return {
                    "final_output": state.get("final_output") or {},
                    "logs": ["No images to process"]
                }
            
            processed_urls = await image_processing_service.process_and_upload_images_async(
                image_urls=raw_images,
                detail_html=detail_html,
                product_id=product_id
            )
            
            # 이전 결과 유지하면서 이미지 결과 추가
            current_output = state.get("final_output") or {}
            current_output["processed_image_urls"] = processed_urls
            
            return {
                "final_output": current_output,
                "logs": [f"Processed {len(processed_urls)} images"]
            }
            
        except Exception as e:
            error = wrap_exception(e, APIError, operation="image_upload")
            self.handle_error(error, "process_images")
            return {"errors": [str(error)]}
    
    async def save_product(self, state: AgentState) -> Dict[str, Any]:
        """
        저장 노드
        
        처리된 결과를 반환합니다. 실제 DB 저장은 서비스 레이어에서 처리합니다.
        """
        self.log_step("save_product", "Saving processed results...")
        
        try:
            # 최종 출력 생성
            final_output = state.get("final_output") or {}
            
            # 처리 상태 확인
            errors = state.get("errors", [])
            status = ProcessingStatus.FAILED if errors else ProcessingStatus.COMPLETED
            
            output = ProcessingAgentOutput(
                processed_name=final_output.get("processed_name", ""),
                processed_keywords=final_output.get("processed_keywords", []),
                processed_image_urls=final_output.get("processed_image_urls", []),
                status=status,
                error_message="; ".join(errors) if errors else None
            )
            
            return {
                "final_output": to_dict_safe(output),
                "logs": ["Processing workflow completed and ready to save"]
            }
            
        except Exception as e:
            error = wrap_exception(e, ValidationError)
            self.handle_error(error, "save_product")
            return {"errors": [str(error)]}


# ============================================================================
# Helper Functions
# ============================================================================

def create_processing_agent(db: Session) -> ProcessingAgent:
    """
    ProcessingAgent 인스턴스 생성 헬퍼
    
    Args:
        db: 데이터베이스 세션
    
    Returns:
        ProcessingAgent 인스턴스
    """
    return ProcessingAgent(db)
