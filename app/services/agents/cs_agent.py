import logging
from sqlalchemy.orm import Session
from app.models import QnaThread, QnaMessage, Product
from app.services.ai.service import AIService
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class CSAgent:
    """
    고객 문의(QnA)에 대한 AI 답변 초안 생성 에이전트.
    """
    def __init__(self, session: Session):
        self.session = session
        self.ai_service = AIService()

    async def process_pending_threads(self):
        """답변이 필요한(OPEN) 스레드 중 초안이 없는 항목에 대해 AI 초안 생성"""
        threads = self.session.query(QnaThread).filter(
            QnaThread.status == "OPEN"
        ).all()
        
        logger.info(f"[CSAgent] Found {len(threads)} OPEN threads to process.")
        
        count = 0
        for thread in threads:
            # 이미 초안이 있는지 확인
            raw = thread.raw or {}
            if "ai_draft" in raw:
                continue
                
            try:
                draft = await self._generate_draft(thread)
                if draft:
                    # 새로운 딕셔너리 객체로 만들어 변경 감지 보장
                    new_raw = dict(raw)
                    new_raw["ai_draft"] = {
                        "content": draft,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "model": self.ai_service.default_provider_name
                    }
                    thread.raw = new_raw
                    thread.updated_at = datetime.now(timezone.utc)
                    count += 1
            except Exception as e:
                logger.error(f"Failed to generate AI draft for thread {thread.id}: {e}")
                
        self.session.commit()
        logger.info(f"[CSAgent] Generated {count} AI drafts.")
        return count

    async def _generate_draft(self, thread: QnaThread) -> str | None:
        # 1. 메시지 이력 수집 (주로 최신 질문)
        messages = self.session.query(QnaMessage).filter_by(thread_id=thread.id).order_by(QnaMessage.id).all()
        if not messages:
            return None
            
        context = ""
        for msg in messages:
            sender = "고객" if msg.direction == "IN" else "판매자"
            context += f"{sender}: {msg.body}\n"
            
        # 2. 관련 상품 정보 수집
        product_info = ""
        if thread.product_id:
            product = self.session.query(Product).get(thread.product_id)
            if product:
                product_info = f"상품명: {product.name}\n설명: {product.description[:200]}..."

        # 3. 프롬프트 구성
        prompt = f"""
        당신은 친절하고 전문적인 이커머스 고객센터 담당자입니다. 
        다음 고객의 문의에 대해 정중하고 도움이 되는 답변 초안을 작성해주세요.
        
        [상품 정보]
        {product_info}
        
        [대화 내역]
        {context}
        
        [지침]
        - 반드시 한국어로 답변할 것.
        - 브랜드 규칙에 따라 정중한 어조(해요체 또는 하십시오체)를 사용할 것.
        - 답변할 수 없는 개인정보(전화번호 등)나 불확실한 배송일정은 '확인 후 안내드리겠다'고 답변할 것.
        - 초안이므로 최종 확인이 필요함을 명시하지 않아도 됨.
        - 금지어: 최고, 제일, 무조건 등 허위/과장 광고 표현 금지.
        
        답변 내용만 출력하세요.
        """
        
        try:
            answer = await self.ai_service.generate_text(prompt)
            return answer.strip()
        except Exception as e:
            logger.error(f"AI generation error: {e}")
            return None
