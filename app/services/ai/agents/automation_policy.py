import logging
from typing import Dict, Any, List, Tuple
from app.settings import settings

logger = logging.getLogger(__name__)

# 의도별 리스크 가중치 (Final_Score에서 차감)
INTENT_RISK_MAP = {
    # LOW Risk: 적극 자동화
    "배송조회": 0.0,
    "배송기간": 0.0,
    "사용법": 0.0,
    "재고확인": 0.0,
    "배송문의": 0.0, # 일반적인 배송 관련
    
    # MEDIUM Risk: 조건부 자동화
    "취소문의": 0.1,
    "옵션변경": 0.1,
    "상품상세": 0.05,
    "가격문의": 0.05,
    
    # HIGH Risk: 수동 검토 필수 (가중치 대폭 상향으로 차단)
    "반품요청": 0.5,
    "교환요청": 0.5,
    "파손클레임": 0.5,
    "오배송클레임": 0.5,
    "불만족": 0.4,
}

# 카테고리별 리스크 가중치
CATEGORY_RISK_MAP = {
    "생활잡화": 0.0,
    "사무용품": 0.0,
    "인테리어": 0.0,
    
    "주방가전": 0.1,
    "생활가전": 0.1,
    "의류": 0.1,
    "완구": 0.1,
    
    "의료기기": 1.0, # 무조건 수동
    "식품": 0.3,
    "화장품": 0.2,
    "명품": 0.5
}

# 법적/분쟁 키워드 (강제 수동 전환)
CRITICAL_KEYWORDS = ["고소", "변호사", "공정위", "소비자원", "신고", "법적", "legal", "lawsuit"]

class AutomationPolicyEngine:
    """
    CS 자동화 정책 엔진
    
    다중 벡터(신뢰도, 의도, 카테고리, 키워드)를 평가하여 
    자동 승인(AI_DRAFTED) 여부를 결정합니다.
    """
    
    def __init__(self, threshold: float = None):
        self.base_threshold = threshold or settings.cs_auto_approval_threshold

    def evaluate(self, state: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        자동화 여부 평가
        
        Returns:
            (should_automate, reason, metadata)
        """
        confidence = state.get("confidence_score", 0.0)
        intent = state.get("intent", "알수없음")
        category = state.get("product_info", {}).get("category", "일반")
        raw_content = state.get("raw_content", "").lower()
        
        # 1. 크리티컬 키워드 검사 (강제 차단)
        for kw in CRITICAL_KEYWORDS:
            if kw in raw_content:
                return False, f"Critical keyword detected: {kw}", {"risk_factor": "keyword"}
        
        # 2. 의도 리스크 가중치 계산
        intent_penalty = INTENT_RISK_MAP.get(intent, 0.2) # 정의되지 않은 의도는 보수적으로
        
        # 3. 카테고리 리스크 가중치 계산
        category_penalty = 0.0
        for cat_key, penalty in CATEGORY_RISK_MAP.items():
            if cat_key in category:
                category_penalty = max(category_penalty, penalty)
                
        # 4. 최종 점수 계산
        final_score = confidence - intent_penalty - category_penalty
        
        # 5. 최종 판정
        should_automate = final_score >= self.base_threshold
        
        reason = "Automated" if should_automate else "Low Final Score"
        if not should_automate:
            if final_score < self.base_threshold:
                reason = f"Score insufficient: {final_score:.2f} (Conf:{confidence:.2f}, Pen:{-intent_penalty-category_penalty:.2f})"
        
        evaluation_metadata = {
            "final_score": round(final_score, 3),
            "base_confidence": round(confidence, 3),
            "intent_penalty": intent_penalty,
            "category_penalty": category_penalty,
            "threshold": self.base_threshold
        }
        
        return should_automate, reason, evaluation_metadata

# 싱글톤 인스턴스
policy_engine = AutomationPolicyEngine()
