import logging
import os
import operator
from typing import Dict, Any, List, Optional, Annotated, TypedDict
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.services.ai.agents.base import BaseAgent, ValidationMixin
from app.services.ai.agents.types import (
    InquiryAnalysis,
    CSResult,
    to_dict_safe,
    from_dict_safe
)
from app.services.ai.agents.router import create_cs_router
from app.services.ai.agents.automation_policy import policy_engine
from app.services.ai.exceptions import wrap_exception
from app.services.ai import AIService
from app.models import MarketInquiryRaw, Product, MarketListing, MarketAccount
from app.settings import settings
from app.coupang_client import CoupangClient
from app.smartstore_client import SmartStoreClient
import asyncio
from datetime import datetime, time
import pytz

class CSAgentState(TypedDict, total=False):
    """
    CS 에이전트 전용 상태 (인라인 정의)
    """
    inquiry_id: str
    current_step: str
    next_step: str
    raw_content: str
    market_code: str
    account_id: str
    product_info: Dict[str, Any]
    policy_context: str
    intent: str
    sentiment: str
    urgency: str
    summary: str
    draft_answer: str
    confidence_score: float
    status: str
    errors: Annotated[List[str], operator.add]
    logs: Annotated[List[str], operator.add]
    final_output: Optional[Dict[str, Any]]

logger = logging.getLogger(__name__)

class CSWorkflowAgent(BaseAgent, ValidationMixin):
    """
    지능형 CS 응대 워크플로우 에이전트
    """
    
    def __init__(self, db: Session):
        self.router = create_cs_router()
        super().__init__(db, "CSWorkflowAgent")
        self.ai_service = AIService()
        self.policy_path = os.path.join(
            os.path.dirname(__file__), "..", "context", "cs_policy.md"
        )

    async def analyze_inquiry(self, state: CSAgentState) -> Dict[str, Any]:
        """문의 내용 분석 노드"""
        print(f"[Node] analyze_inquiry started with state keys: {list(state.keys())}")
        content = state.get("raw_content", "")
        
        prompt = f"""
        고객의 문의 내용을 분석하여 아래 JSON 형식으로 응답하세요.
        
        [문의 내용]
        {content}
        
        [출력 형식]
        {{
            "intent": "배송문의", "취소문의", "반품문의", "상품문의", "단순문의" 중 하나,
            "sentiment": "긍정", "부정", "중립" 중 하나,
            "urgency": "high", "medium", "low" 중 하나,
            "summary": "1문장 요약"
        }}
        """
        
        try:
            # 30초 타임아웃 적용 (가드레일)
            analysis_dict = await asyncio.wait_for(
                self.ai_service.generate_json(prompt, provider="auto"),
                timeout=30.0
            )
            analysis = InquiryAnalysis(**analysis_dict)
            
            return {
                "intent": analysis.intent,
                "sentiment": analysis.sentiment,
                "urgency": analysis.urgency,
                "summary": analysis.summary,
                "logs": ["Inquiry analysis completed"],
                "current_step": "analyze_inquiry"
            }
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {"errors": [f"Analysis failed: {str(e)}"], "current_step": "analyze_inquiry"}

    async def retrieve_knowledge(self, state: CSAgentState) -> Dict[str, Any]:
        """지식 검색 노드 (정책 + 상품 정보)"""
        policy_context = ""
        try:
            if os.path.exists(self.policy_path):
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    policy_context = f.read()
            else:
                policy_context = "기본 CS 정책을 따릅니다."
        except Exception as e:
            policy_context = "정책 로드 실패"

        return {
            "policy_context": policy_context,
            "logs": ["Knowledge retrieval completed"],
            "current_step": "retrieve_knowledge"
        }

    async def generate_draft(self, state: CSAgentState) -> Dict[str, Any]:
        """답변 초안 생성 노드"""
        intent = state.get("intent", "일반문의")
        content = state.get("raw_content", "")
        product_info = state.get("product_info", {})
        policy = state.get("policy_context", "")
        sentiment = state.get("sentiment", "중립")
        
        product_context = f"- 상품명: {product_info.get('name', 'N/A')}\n- 상세: {str(product_info.get('description', ''))[:200]}"
        
        prompt = f"""
        당신은 쇼핑몰 CS 전문 상담원입니다. 정책과 상품 정보를 바탕으로 고객님께 정중하게 답변 초안을 작성해주세요.
        
        [고객 문의]
        내용: {content}
        의도: {intent}
        감정: {sentiment}
        
        [상품 정보]
        {product_context}
        
        [CS 정책]
        {policy}
        
        [가이드라인]
        - 정중한 문체를 사용하세요 (~입니다, ~해요).
        - 정책에 없는 내용은 확답하지 말고 '확인 후 안내드리겠다'고 하세요.
        - 한국어로만 응답하세요.
        - 답변 초안만 출력하세요.
        """
        
        try:
            # 답변 생성은 60초 타임아웃 (가드레일)
            draft = await asyncio.wait_for(
                self.ai_service.generate_text(prompt, provider="auto"),
                timeout=60.0
            )
            return {
                "draft_answer": draft.strip(),
                "logs": ["Draft answer generated"],
                "current_step": "generate_draft"
            }
        except Exception as e:
            return {"errors": [f"Draft generation failed: {e}"], "current_step": "generate_draft"}

    async def self_review(self, state: CSAgentState) -> Dict[str, Any]:
        """자가 검토 노드 (신뢰도 산출)"""
        draft = state.get("draft_answer", "")
        content = state.get("raw_content", "")
        
        prompt = f"""
        작성된 CS 답변이 적절한지 검토하고 0.0 ~ 1.0 사이의 신뢰도 점수를 부여하세요.
        
        [고객 문의]: {content}
        [작성된 답변]: {draft}
        
        [출력 형식]
        {{
            "score": 0.95,
            "comment": "답변이 매우 적절함"
        }}
        """
        
        try:
            # 30초 타임아웃 적용 (가드레일)
            review = await asyncio.wait_for(
                self.ai_service.generate_json(prompt, provider="auto"),
                timeout=30.0
            )
            score = review.get("score", 0.5)
            
            # v1.7.1: 정책 엔진 기반 자동 승격 여부 결정 (Multi-vector)
            state["confidence_score"] = score
            can_automate, reason, policy_metadata = policy_engine.evaluate(state)
            
            # v1.8.0: Partial Auto 전송 여부 결정 (Operational Gate)
            final_score = policy_metadata.get("final_score", 0.0)
            status = "HUMAN_REVIEW"
            
            if can_automate:
                # 1. 업무 시간 체크 (KST 09:00 ~ 18:00)
                kst = pytz.timezone('Asia/Seoul')
                now_kst = datetime.now(kst).time()
                is_business_hours = time(9, 0) <= now_kst <= time(18, 0)
                
                # 2. 전송 플래그 및 점수 체크
                if settings.enable_cs_partial_auto and final_score >= settings.cs_auto_send_threshold and is_business_hours:
                    status = "AUTO_SEND"
                else:
                    status = "AI_DRAFTED"
            
            return {
                "confidence_score": score,
                "status": status,
                "logs": [f"Self-review completed (Score: {score}, Status: {status})", f"Policy: {reason}"],
                "policy_evaluation": policy_metadata,
                "current_step": "self_review"
            }
        except Exception as e:
            return {"errors": [f"Self-review failed: {e}"], "current_step": "self_review"}

    async def finalize(self, state: CSAgentState) -> Dict[str, Any]:
        """최종 데이터베이스 반영 및 정리"""
        db_id = state.get("inquiry_id") # 내부 PK
        draft = state.get("draft_answer")
        status = state.get("status")
        score = state.get("confidence_score")
        
        try:
            # v1.8.0: 내부 ID(db_id)와 마켓 ID(market_inquiry_id) 명확히 구분하여 조회
            inquiry = self.db.query(MarketInquiryRaw).filter(MarketInquiryRaw.id == db_id).first()
            if inquiry:
                # 데이터 정합성 강화: 중복 전송 방지 (Idempotency)
                if inquiry.sent_at or inquiry.send_status == "SENT":
                    logger.warning(f"Inquiry {db_id} already sent. Skipping final update.")
                    return {"status": inquiry.send_status, "current_step": "finalize"}

                inquiry.ai_suggested_answer = draft
                inquiry.status = status
                inquiry.confidence_score = score
                inquiry.cs_metadata = {
                    "logs": state.get("logs", []),
                    "intent": state.get("intent"),
                    "sentiment": state.get("sentiment"),
                    "policy_evaluation": state.get("policy_evaluation", {})
                }
                self.db.commit()
                logger.info(f"Finalized CS inquiry {db_id} in DB with status {status}")

                # v1.8.0: 실마켓 전송 (AUTO_SEND 일 때만)
                if status == "AUTO_SEND":
                    await self._send_to_market(inquiry, draft)
            
            return {
                "final_output": {
                    "status": status,
                    "confidence_score": score
                },
                "logs": ["Finalized in database"],
                "current_step": "finalize"
            }
        except Exception as e:
            logger.error(f"Finalize failed: {e}")
            return {"errors": [f"Finalize failed: {e}"], "current_step": "finalize"}

    def _get_entry_point(self) -> str:
        return "analyze_inquiry"

    def _get_nodes(self) -> Dict[str, Any]:
        return {
            "analyze_inquiry": self.analyze_inquiry,
            "retrieve_knowledge": self.retrieve_knowledge,
            "generate_draft": self.generate_draft,
            "self_review": self.self_review,
            "finalize": self.finalize
        }

    def _create_initial_state(self, target_id: str, input_data: Dict[str, Any], **kwargs) -> CSAgentState:
        return {
            "inquiry_id": target_id,
            "current_step": "",
            "raw_content": input_data.get("content", ""),
            "market_code": input_data.get("market_code", "COUPANG"),
            "product_info": input_data.get("product_info", {}),
            "logs": ["Started CS workflow"],
            "errors": []
        }

    def _create_workflow(self) -> StateGraph:
        """워크플로우 그래프 생성"""
        workflow = StateGraph(CSAgentState)
        nodes = self._get_nodes()
        for name, handler in nodes.items():
            workflow.add_node(name, handler)
        
        from app.services.ai.agents.router import ConditionalEdge
        edge = ConditionalEdge(self.router)
        
        # Path mapping for LangGraph string routes
        path_map = {name: name for name in nodes.keys()}
        path_map["END"] = END
        
        workflow.set_entry_point(self._get_entry_point())
        for node in nodes.keys():
            workflow.add_conditional_edges(node, edge, path_map)
            
        return workflow.compile()

    async def _send_to_market(self, inquiry: MarketInquiryRaw, answer: str):
        """실제 마켓 API를 통해 답변 전송 및 상태 기록"""
        account = self.db.query(MarketAccount).filter(MarketAccount.id == inquiry.account_id).first()
        if not account:
            logger.error(f"Account {inquiry.account_id} not found for auto-send.")
            return

        # 시도 횟수 증가
        inquiry.send_attempts += 1
        self.db.commit()

        try:
            success = False
            error_msg = None
            
            if inquiry.market_code == "COUPANG":
                creds = account.credentials
                client = CoupangClient(
                    access_key=creds.get("access_key"),
                    secret_key=creds.get("secret_key"),
                    vendor_id=creds.get("vendor_id")
                )
                wing_id = creds.get("wing_id", "admin")
                code, data = client.reply_to_customer_inquiry(
                    inquiry_id=inquiry.inquiry_id,
                    content=answer,
                    reply_by=wing_id
                )
                if code == 200:
                    success = True
                else:
                    error_msg = f"Coupang API Error (Code {code}): {data}"

            elif inquiry.market_code == "SMARTSTORE":
                creds = account.credentials
                client = SmartStoreClient(
                    client_id=creds.get("client_id"),
                    client_secret=creds.get("client_secret")
                )
                res = client.answer_customer_inquiry(
                    inquiry_id=inquiry.inquiry_id,
                    content=answer
                )
                if res.get("errorCode"):
                    error_msg = f"SmartStore API Error: {res}"
                else:
                    success = True

            # 결과 업데이트
            if success:
                inquiry.send_status = "SENT"
                inquiry.sent_at = datetime.now(pytz.UTC)
                inquiry.last_send_error = None
                logger.info(f"Successfully auto-sent inquiry {inquiry.id}")
            else:
                inquiry.send_status = "SEND_FAILED"
                inquiry.last_send_error = error_msg
                logger.error(f"Auto-send failed for inquiry {inquiry.id}: {error_msg}")
            
            self.db.commit()

        except Exception as e:
            error_msg = f"System Error during auto-send: {str(e)}"
            inquiry.send_status = "SEND_FAILED"
            inquiry.last_send_error = error_msg
            self.db.commit()
            logger.error(error_msg, exc_info=True)

    async def run_cs(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        CS 워크플로우 실행 (BaseAgent.run을 래핑)
        """
        target_id = str(input_data.get("inquiry_id", ""))
        result = await self.run(target_id, input_data)
        
        if result.status == "COMPLETED":
            return {
                "status": result.final_output.get("status") if result.final_output else "AI_DRAFTED",
                "final_output": result.final_output
            }
        else:
            return {"error": result.error_message, "status": "FAILED"}
