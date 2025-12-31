from typing import Annotated, List, Dict, Any, Optional, TypedDict
import operator

class CSAgentState(TypedDict, total=False):
    """
    CSWorkflowAgent 전용 상태 클래스
    """
    # 기본 메타데이터
    inquiry_id: str
    target_id: str  # DB ID (UUID)
    market_code: str
    account_id: str
    
    # 데이터 영역
    raw_content: str
    inquiry_type: str
    product_info: Dict[str, Any]
    policy_context: str
    
    # 분석 결과
    intent: str
    sentiment: str
    urgency: str  # high, medium, low
    
    # 답변 생성 영역
    draft_answer: str
    confidence_score: float
    
    # 워크플로우 제어
    current_step: str
    next_step: str
    status: str # PENDING, AI_DRAFTED, HUMAN_REVIEW, COMPLETED
    errors: Annotated[List[str], operator.add]
    logs: Annotated[List[str], operator.add]
    
    # 최종 결과물
    final_output: Optional[Dict[str, Any]]
