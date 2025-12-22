import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.services.ai.agents.state import AgentState
from app.services.ai import AIService
from app.services.image_processing import image_processing_service
from app.services.name_processing import apply_market_name_rules
from app.settings import settings

logger = logging.getLogger(__name__)

class ProcessingAgent:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = AIService()
        self.workflow = self._create_workflow()

    def _create_workflow(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("extract_details", self.extract_details)
        workflow.add_node("optimize_seo", self.optimize_seo)
        workflow.add_node("process_images", self.process_images)
        workflow.add_node("save_product", self.save_product)

        workflow.set_entry_point("extract_details")
        workflow.add_edge("extract_details", "optimize_seo")
        workflow.add_edge("optimize_seo", "process_images")
        workflow.add_edge("process_images", "save_product")
        workflow.add_edge("save_product", END)

        return workflow.compile()

    def extract_details(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Extracting details for processing...")
        input_data = state.get("input_data", {})
        # 원본 데이터 파싱 및 정규화
        detail_text = input_data.get("description") or input_data.get("content") or ""
        return {
            "input_data": {**input_data, "normalized_detail": detail_text},
            "logs": ["Details extracted and normalized"]
        }

    def optimize_seo(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Optimizing SEO...")
        input_data = state.get("input_data", {})
        name = input_data.get("name")
        brand = input_data.get("brand", "")
        
        processed_name = name
        keywords = []
        
        try:
            seo_result = self.ai_service.optimize_seo(name, [brand], provider="auto")
            if isinstance(seo_result, dict):
                raw_title = seo_result.get("title")
                keywords = seo_result.get("tags") or []
                if raw_title:
                    processed_name = apply_market_name_rules(
                        raw_title,
                        forbidden_keywords=settings.product_name_forbidden_keywords,
                        replacements=settings.product_name_replacements,
                        max_length=100,
                    )
        except Exception as e:
            logger.error(f"[Agent] SEO optimization failed: {e}")
            # AI 실패 시 기본 규칙만 적용하거나 원본 유지
            processed_name = apply_market_name_rules(
                name,
                forbidden_keywords=settings.product_name_forbidden_keywords,
                replacements=settings.product_name_replacements,
                max_length=100,
            )
        
        return {
            "final_output": {
                "processed_name": processed_name,
                "processed_keywords": keywords
            },
            "logs": ["SEO optimization completed (with fallback if needed)"]
        }

    def process_images(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Processing images...")
        input_data = state.get("input_data", {})
        product_id = state.get("target_id")
        raw_images = input_data.get("images", [])
        detail_html = input_data.get("detail_html") or input_data.get("normalized_detail", "")
        
        processed_urls = image_processing_service.process_and_upload_images(
            image_urls=raw_images,
            detail_html=detail_html,
            product_id=product_id
        )
        
        # 이전 노드 결과 유지하면서 이미지 결과 추가
        current_output = state.get("final_output") or {}
        current_output["processed_image_urls"] = processed_urls
        
        return {
            "final_output": current_output,
            "logs": [f"Processed {len(processed_urls)} images"]
        }

    def save_product(self, state: AgentState) -> Dict[str, Any]:
        logger.info("[Agent] Saving processed results...")
        # DB 저장 로직은 호출하는 Service에서 처리하도록 결과만 반환하거나
        # 여기서 직접 Session commit 가능
        return {
            "logs": ["Processing workflow completed and ready to save"]
        }

    async def run(self, product_id: str, input_data: Dict[str, Any]):
        initial_state: AgentState = {
            "job_id": f"proc_{product_id}",
            "target_id": product_id,
            "input_data": input_data,
            "benchmark_data": None,
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
