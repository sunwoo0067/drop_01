"""
Processing Agent

제품 가공을 담당하는 AI 에이전트
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
    
    상세페이지 추출, OCR, SEO 최적화, 이미지 처리 단계를 수행합니다.
    """
    
    def __init__(self, db: Session):
        super().__init__(db, "ProcessingAgent")
        self.router = create_processing_router()
    
    def _name_only_processing(self) -> bool:
        """이름 전용 처리 모드 여부"""
        return settings.product_processing_name_only
    
    def _create_workflow(self) -> StateGraph:
        """워크플로우 생성"""
        workflow = StateGraph(AgentState)
        
        # 노드 등록
        workflow.add_node("extract_details", self.extract_details)
        workflow.add_node("extract_ocr_details", self.extract_ocr_details)
        workflow.add_node("optimize_seo", self.optimize_seo)
        workflow.add_node("process_images", self.process_images)
        workflow.add_node("save_product", self.save_product)
        
        # 진입점 설정
        workflow.set_entry_point("extract_details")
        
        # 엣지 연결
        workflow.add_edge("extract_details", "extract_ocr_details")
        workflow.add_edge("extract_ocr_details", "optimize_seo")
        
        # 조건부 엣지: 이름 전용 처리 모드
        if self._name_only_processing():
            workflow.add_edge("optimize_seo", "save_product")
        else:
            workflow.add_edge("optimize_seo", "process_images")
            workflow.add_edge("process_images", "save_product")
        
        workflow.add_edge("save_product", END)
        
        return workflow.compile()
    
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
