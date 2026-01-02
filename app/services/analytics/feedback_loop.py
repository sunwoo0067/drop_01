import logging
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Product, SourcingCandidate

logger = logging.getLogger(__name__)

class CoupangFeedbackLoopService:
    """
    쿠팡 등록 결과를 분석하여 소싱 정책 엔진에 피드백을 전달하는 서비스입니다.
    (Adaptive Intelligence Phase)
    """
    
    @staticmethod
    def report_registration_result(
        session: Session, 
        product_id: uuid.UUID, 
        status: str, 
        error_reason: Optional[str] = None
    ):
        """
        등록 시점의 성공/실패 데이터를 처리합니다.
        """
        product = session.get(Product, product_id)
        if not product:
            return

        from app.models import SupplierItemRaw
        
        # 1. 원본 소싱 후보(Candidate) 정보 추출
        # product.supplier_item_id is UUID linking to SupplierItemRaw.id
        raw_item = session.get(SupplierItemRaw, product.supplier_item_id) if product.supplier_item_id else None
        
        candidate = None
        if raw_item and raw_item.item_code:
            candidate = session.execute(
                select(SourcingCandidate)
                .where(SourcingCandidate.supplier_item_id == raw_item.item_code)
                .limit(1)
            ).scalar_one_or_none()

        keyword = candidate.sourcing_policy.get("keyword") if candidate and candidate.sourcing_policy else None
        category_code = candidate.sourcing_policy.get("category_code") if candidate and candidate.sourcing_policy else None

        if status == "SUCCESS":
            logger.info(f"Feedback [SUCCESS]: Product {product_id} (Keyword: {keyword}, Category: {category_code}) registered successfully.")
            # 마켓 등록 결과 임계치 조정을 위해 추가 로직 확장 가능 (예: keyword 성공 카운트 증가)
        else:
            logger.warning(f"Feedback [FAILURE]: Product {product_id} (Category: {category_code}) failed: {error_reason}")
            # '카테고리 거절'이나 '이미지 반려' 등 특정 에러 유형에 따른 자동 등급 하향 트리거 가능
            
        # 2. MarketListing 수동 생성이 아닌 싱크 레이어에서 이미 listing.status를 공유하고 있으므로,
        # 이 시점에는 시스템 로그 및 트리거 지점으로서의 역할을 수행합니다.
        # (Future: Redis에 최근 실패 키워드로 등록하여 1시간 동안 해당 키워드 소싱 자동 차단 등 가능)
